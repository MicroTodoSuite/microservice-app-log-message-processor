import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import redis
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Reconnection is normal operation for a pub/sub consumer, not an exceptional
# condition: a broker restart must not end this process.
MAX_RECONNECT_BACKOFF_SECONDS = 30

SERVICE_NAME = "log-message-processor"


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


# --- tracing (spec 010) ----------------------------------------------------


def is_export_enabled(env=None):
    """Trace export is on only when an OTLP endpoint is configured."""
    env = os.environ if env is None else env
    return bool(env.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def configure_tracing(env=None):
    """Install a tracer provider that exports over OTLP/gRPC, or nothing.

    The exporter reads OTEL_EXPORTER_OTLP_ENDPOINT itself, and the batch
    processor exports off the consuming thread, so an unreachable collector
    costs spans and never a message. Without an endpoint the global tracer
    stays a no-op.
    """
    env = os.environ if env is None else env
    if not is_export_enabled(env):
        return None

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": env.get("OTEL_SERVICE_NAME") or SERVICE_NAME})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def _trace_context(message):
    """The W3C fields of the log_channel contract, when well-typed."""
    if not isinstance(message, dict):
        return {}
    return {
        field: message[field]
        for field in ("traceparent", "tracestate")
        if isinstance(message.get(field), str)
    }


def process_message(
    message,
    *,
    channel="log_channel",
    metrics=METRICS,
    logger=log_message,
    tracer=None,
):
    """Process one decoded Redis event inside a CONSUMER span.

    The span continues the publisher's trace when the message carries W3C trace
    context and starts a new trace when it does not; a missing, invalid, or
    legacy field never stops the message from being logged.
    """
    tracer = tracer or trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span(
        f"{channel} process",
        context=propagate.extract(_trace_context(message)),
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "redis",
            "messaging.destination.name": channel,
            "messaging.operation.type": "process",
        },
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            with metrics.duration.time():
                logger(message)
            metrics.processed.inc()
        except Exception as exception:  # noqa: BLE001 - one bad message must not stop consumption
            span.set_status(Status(StatusCode.ERROR, str(exception)))
            print(json.dumps({"level": "error", "msg": "log_message_failed", "error": str(exception)}))
            metrics.failed.inc()


def process_item(item, **kwargs):
    """Decode one Redis item and account for malformed messages."""
    try:
        message = json.loads(item["data"].decode("utf-8"))
    except Exception as exception:
        logger = kwargs.get("logger", log_message)
        metrics = kwargs.get("metrics", METRICS)
        logger(exception)
        metrics.failed.inc()
        return
    process_message(message, **kwargs)


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
    configure_tracing()

    print(json.dumps({"level": "info", "msg": "runtime_configuration", "config": config}))

    consume(
        pubsub_factory=lambda: redis.Redis(host=redis_host, port=redis_port, db=0).pubsub(),
        channel=redis_channel,
        health=health,
        max_reconnects=config["redis"]["max_reconnects"],
    )


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
                handler(item, channel=channel)
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


if __name__ == "__main__":
    run()
