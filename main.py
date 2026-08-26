import json
import os
import random
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import redis
import requests
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from py_zipkin.zipkin import ZipkinAttrs, generate_random_64bit_string, zipkin_span

# Reconnection is normal operation for a pub/sub consumer, not an exceptional
# condition: a broker restart must not end this process.
MAX_RECONNECT_BACKOFF_SECONDS = 30


class ProcessingMetrics:
    def __init__(self, processed, failed, duration):
        self.processed = processed
        self.failed = failed
        self.duration = duration


METRICS = ProcessingMetrics(
    Counter("log_messages_processed_total", "Total number of log messages processed"),
    Counter("log_messages_failed_total", "Total number of log messages failed"),
    Histogram("log_message_processing_duration_seconds", "Duration of message processing in seconds"),
)


def log_message(message, *, randrange=random.randrange, sleep=time.sleep):
    """Simulate the original message-processing delay and emit the message."""
    delay_ms = randrange(0, 2000)
    sleep(delay_ms / 1000)
    print(f"message received after waiting for {delay_ms}ms: {message}")


def http_transport(encoded_span, zipkin_url, *, session=requests):
    """Send one encoded span to the configured Zipkin endpoint."""
    response = session.post(
        zipkin_url,
        data=encoded_span,
        headers={"Content-Type": "application/x-thrift"},
        timeout=5,
    )
    response.raise_for_status()


def process_message(
    message,
    zipkin_url,
    *,
    metrics=METRICS,
    logger=log_message,
    span_factory=zipkin_span,
    transport=http_transport,
):
    """Process one decoded Redis event while preserving the pub/sub contract."""
    if not zipkin_url or "zipkinSpan" not in message:
        logger(message)
        metrics.processed.inc()
        return

    span_data = message["zipkinSpan"]
    try:
        with metrics.duration.time():
            with span_factory(
                service_name="log-message-processor",
                zipkin_attrs=ZipkinAttrs(
                    trace_id=span_data["_traceId"]["value"],
                    span_id=generate_random_64bit_string(),
                    parent_span_id=span_data["_spanId"],
                    is_sampled=span_data["_sampled"]["value"],
                    flags=None,
                ),
                span_name="save_log",
                transport_handler=partial(transport, zipkin_url=zipkin_url),
                sample_rate=100,
            ):
                logger(message)
                metrics.processed.inc()
    except Exception as exception:
        print(f"did not send data to Zipkin: {exception}")
        logger(message)
        metrics.failed.inc()


def process_item(item, zipkin_url, **kwargs):
    """Decode one Redis item and account for malformed messages."""
    try:
        message = json.loads(item["data"].decode("utf-8"))
    except Exception as exception:
        logger = kwargs.get("logger", log_message)
        metrics = kwargs.get("metrics", METRICS)
        logger(exception)
        metrics.failed.inc()
        return
    process_message(message, zipkin_url, **kwargs)


def run():
    config = load_runtime_config()
    health = HealthState()

    # Probes and metrics share one port. The exporter alone would leave
    # Kubernetes with nothing to ask but "is the process running", which stays
    # true even when the subscriber has stopped consuming.
    start_operational_server(int(os.environ["PORT"]), health)

    redis_host = os.environ["REDIS_HOST"]
    redis_port = int(os.environ["REDIS_PORT"])
    redis_channel = os.environ["REDIS_CHANNEL"]
    zipkin_url = os.environ.get("ZIPKIN_URL", "")

    print(json.dumps({"level": "info", "msg": "runtime_configuration", "config": config}))

    consume(
        pubsub_factory=lambda: redis.Redis(host=redis_host, port=redis_port, db=0).pubsub(),
        channel=redis_channel,
        zipkin_url=zipkin_url,
        health=health,
        max_reconnects=config["redis"]["max_reconnects"],
    )


if __name__ == "__main__":
    run()


# --- health ---------------------------------------------------------------


class HealthState:
    """The three separate answers Kubernetes needs.

    Collapsing readiness into liveness is an outage here: while this consumer is
    reconnecting to Redis it is genuinely not ready, but restarting the pod only
    lengthens the interruption and hands it to CrashLoopBackOff.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._started = True
        self._ready = True

    def set_started(self, value):
        with self._lock:
            self._started = value

    def set_ready(self, value):
        with self._lock:
            self._ready = value

    def is_started(self):
        with self._lock:
            return self._started

    def is_ready(self):
        with self._lock:
            return self._ready


def _operational_handler(health):
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status, payload, content_type="application/json"):
            body = payload.encode() if isinstance(payload, str) else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/metrics":
                return self._respond(200, generate_latest(), CONTENT_TYPE_LATEST)

            if self.path == "/health/startup":
                ok = health.is_started()
                return self._respond(
                    200 if ok else 503,
                    json.dumps({"status": "ok" if ok else "starting"}),
                )

            if self.path == "/health/ready":
                ok = health.is_ready()
                return self._respond(
                    200 if ok else 503,
                    json.dumps({"status": "ok" if ok else "not-ready"}),
                )

            # Liveness answers only "is this process wedged". It deliberately
            # ignores the Redis connection: a broker outage must not restart
            # every consumer, because a restart cannot fix the broker and the
            # resulting backoff delays recovery once it returns.
            if self.path == "/health/live":
                return self._respond(200, json.dumps({"status": "ok"}))

            return self._respond(404, json.dumps({"status": "not-found"}))

        def log_message(self, *args):
            # The default handler writes to stderr on every scrape, which at a
            # 15s scrape interval is pure noise in the log aggregator.
            return

    return Handler


def start_operational_server(port, health):
    """Serve metrics and probes on one port, in a background thread."""
    server = ThreadingHTTPServer(("", port), _operational_handler(health))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# --- configuration --------------------------------------------------------


def _env_bool(name, fallback):
    raw = os.environ.get(name, "")
    if raw == "":
        return fallback
    return raw.lower() in ("1", "true", "yes")


def _env_int(name, fallback):
    raw = os.environ.get(name, "")
    if raw == "":
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return fallback if value < 0 else value


def load_runtime_config():
    """Non-secret operational values only.

    This is logged at startup so an operator can see what the pod loaded, which
    is exactly why no secret may appear in it.
    """
    return {
        "features": {
            # Off by default: a toggle that defaults on ships its behaviour to
            # production the moment it merges.
            "verbose_payload": _env_bool("LOG_PROCESSOR_FEATURE_VERBOSE_PAYLOAD", False),
        },
        "redis": {
            # -1 means "retry forever", which is the right default for a pub/sub
            # consumer: the alternative is giving up on a broker that is merely
            # slow to come back.
            "max_reconnects": _env_int("LOG_PROCESSOR_MAX_RECONNECTS", -1),
        },
    }


# --- correlation ----------------------------------------------------------


def log_message_structured(message, *, randrange=random.randrange, sleep=time.sleep):
    """Emit one structured line carrying the publisher's correlation id.

    todos-api stamps every audit line with the X-Request-Id of the request that
    produced it. Surfacing it here is what lets one HTTP request be followed all
    the way from the ingress to this consumer.
    """
    delay_ms = randrange(0, 2000)
    sleep(delay_ms / 1000)

    correlation_id = ""
    if isinstance(message, dict):
        correlation_id = message.get("correlationId", "")

    print(json.dumps({
        "level": "info",
        "msg": "log_message_processed",
        "correlationId": correlation_id,
        "delayMs": delay_ms,
        "payload": message if isinstance(message, dict) else str(message),
    }, default=str))


# --- resilient consumption ------------------------------------------------


def reconnect_backoff(attempt):
    """Exponential backoff, capped.

    Uncapped growth would leave the consumer asleep for minutes after Redis was
    already healthy; no backoff at all would hammer a broker that is starting up.
    """
    return min(2 ** (attempt - 1), MAX_RECONNECT_BACKOFF_SECONDS)


def consume(
    *,
    pubsub_factory,
    channel,
    zipkin_url,
    handler=None,
    health=None,
    backoff=reconnect_backoff,
    max_reconnects=-1,
):
    """Consume the channel, surviving broker restarts.

    Every Redis call in this loop raises when the broker is unavailable. Letting
    those propagate ends the process, and Kubernetes then applies
    CrashLoopBackOff — whose exponential delay outlasts the outage it was
    reacting to. Reconnecting in-process keeps recovery immediate and keeps the
    readiness signal honest while it happens.
    """
    if handler is None:
        handler = process_item
    if health is None:
        health = HealthState()

    attempt = 0
    while True:
        consumed_anything = False
        try:
            pubsub = pubsub_factory()
            pubsub.subscribe([channel])
            health.set_ready(True)

            for item in pubsub.listen():
                # Progress, not merely a successful connect, is what proves the
                # subscription works. Resetting the counter on connect alone
                # would let a broker that accepts subscriptions and immediately
                # closes them spin forever at the shortest backoff.
                consumed_anything = True
                handler(item, zipkin_url)
        except Exception as exception:  # noqa: BLE001 - any broker error must retry
            health.set_ready(False)
            attempt = 0 if consumed_anything else attempt + 1
            print(json.dumps({
                "level": "error",
                "msg": "redis_subscription_lost",
                "attempt": attempt,
                "error": str(exception),
            }))

            if 0 <= max_reconnects < attempt:
                raise

            time.sleep(backoff(attempt))
            continue

        # listen() returned without raising: the iterator was exhausted, which
        # means the connection closed cleanly. Treated the same as an error,
        # because from this consumer's point of view it is the same situation —
        # it is no longer receiving anything.
        health.set_ready(False)
        attempt = 0 if consumed_anything else attempt + 1

        if 0 <= max_reconnects < attempt:
            return

        time.sleep(backoff(attempt))
