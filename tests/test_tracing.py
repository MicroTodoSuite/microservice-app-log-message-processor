"""Tracing contract for log-message-processor (spec 010, T007).

Spans are read from an in-memory exporter through a tracer handed to the
processor, so these tests observe the real spans without touching the global
tracer provider.
"""
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

import main

REPOSITORY = Path(__file__).resolve().parent.parent
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
PARENT_SPAN_ID = "b7ad6b7169203331"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


class Counter:
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1


class Duration:
    def __init__(self):
        self.entries = 0

    def time(self):
        duration = self

        class Timer:
            def __enter__(self):
                duration.entries += 1

            def __exit__(self, *exc):
                return False

        return Timer()


class Metrics:
    def __init__(self):
        self.processed = Counter()
        self.failed = Counter()
        self.duration = Duration()


def in_memory_tracer():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def process(message, logger=None):
    tracer, exporter = in_memory_tracer()
    metrics = Metrics()
    logged = []
    main.process_message(
        message,
        channel="log_channel",
        metrics=metrics,
        logger=logger or logged.append,
        tracer=tracer,
    )
    return exporter.get_finished_spans(), metrics, logged


def test_traced_message_continues_the_publisher_trace():
    message = {"opName": "CREATE", "username": "u", "todoId": 1, "traceparent": TRACEPARENT}

    spans, metrics, logged = process(message)

    assert len(spans) == 1
    span = spans[0]
    assert span.name == "log_channel process"
    assert span.kind == SpanKind.CONSUMER
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert span.parent is not None
    assert format(span.parent.span_id, "016x") == PARENT_SPAN_ID
    assert span.attributes["messaging.system"] == "redis"
    assert span.attributes["messaging.destination.name"] == "log_channel"
    assert span.attributes["messaging.operation.type"] == "process"
    assert logged == [message]
    assert metrics.processed.value == 1
    assert metrics.failed.value == 0


def test_message_without_trace_context_starts_a_new_trace():
    spans, metrics, logged = process({"opName": "DELETE", "username": "u", "todoId": "2"})

    assert len(spans) == 1
    assert spans[0].parent is None
    assert metrics.processed.value == 1


def test_invalid_traceparent_starts_a_new_trace():
    spans, metrics, _ = process({"opName": "CREATE", "traceparent": "not-a-traceparent"})

    assert len(spans) == 1
    assert spans[0].parent is None
    assert metrics.processed.value == 1


def test_legacy_zipkin_span_field_is_ignored():
    legacy = {"opName": "CREATE", "zipkinSpan": {"_traceId": {"value": "abc"}, "_spanId": "def"}}

    spans, metrics, logged = process(legacy)

    assert len(spans) == 1
    assert spans[0].parent is None
    assert logged == [legacy]
    assert metrics.processed.value == 1
    assert metrics.failed.value == 0


def test_processing_failure_is_counted_and_marks_the_span():
    def failing_logger(_message):
        raise RuntimeError("logger broke")

    spans, metrics, _ = process({"opName": "CREATE", "traceparent": TRACEPARENT}, logger=failing_logger)

    assert metrics.failed.value == 1
    assert metrics.processed.value == 0
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR


def test_export_is_enabled_only_with_an_otlp_endpoint():
    assert main.is_export_enabled({}) is False
    assert main.is_export_enabled({"OTEL_EXPORTER_OTLP_ENDPOINT": ""}) is False
    assert main.is_export_enabled(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger-collector.observability.svc:4317"}
    ) is True
    assert main.configure_tracing({}) is None


def test_runtime_requirements_carry_no_zipkin_transport():
    declared = {
        line.split("==")[0].strip().lower()
        for line in (REPOSITORY / "requirements.in").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "py-zipkin" not in declared
    assert "requests" not in declared
    assert "py-zipkin" not in (REPOSITORY / "requirements.txt").read_text().lower()
