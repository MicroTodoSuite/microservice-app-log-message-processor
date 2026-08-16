import json
import os
import random
import time
from functools import partial

import redis
import requests
from prometheus_client import Counter, Histogram, start_http_server
from py_zipkin.zipkin import ZipkinAttrs, generate_random_64bit_string, zipkin_span


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
    start_http_server(int(os.environ["PORT"]))
    redis_host = os.environ["REDIS_HOST"]
    redis_port = int(os.environ["REDIS_PORT"])
    redis_channel = os.environ["REDIS_CHANNEL"]
    zipkin_url = os.environ.get("ZIPKIN_URL", "")

    pubsub = redis.Redis(host=redis_host, port=redis_port, db=0).pubsub()
    pubsub.subscribe([redis_channel])
    for item in pubsub.listen():
        process_item(item, zipkin_url)


if __name__ == "__main__":
    run()
