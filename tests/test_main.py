from contextlib import nullcontext

import main


class FakeCounter:
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1


class FakeDuration:
    def __init__(self):
        self.entries = 0

    def time(self):
        self.entries += 1
        return nullcontext()


class FakeMetrics:
    def __init__(self):
        self.processed = FakeCounter()
        self.failed = FakeCounter()
        self.duration = FakeDuration()


def test_log_message_preserves_bounded_delay(capsys):
    sleeps = []
    main.log_message("hello", randrange=lambda start, end: 125, sleep=sleeps.append)

    assert sleeps == [0.125]
    assert "message received after waiting for 125ms: hello" in capsys.readouterr().out


def test_untraced_event_is_processed_without_zipkin():
    metrics = FakeMetrics()
    logged = []

    main.process_message({"opName": "CREATE"}, "", metrics=metrics, logger=logged.append)

    assert logged == [{"opName": "CREATE"}]
    assert metrics.processed.value == 1
    assert metrics.failed.value == 0


def test_traced_event_preserves_parent_span_and_transport():
    metrics = FakeMetrics()
    span_arguments = {}
    logged = []

    def span_factory(**kwargs):
        span_arguments.update(kwargs)
        return nullcontext()

    event = {
        "opName": "DELETE",
        "zipkinSpan": {
            "_traceId": {"value": "trace-id"},
            "_spanId": "parent-id",
            "_sampled": {"value": True},
        },
    }
    main.process_message(
        event,
        "http://zipkin/api/v1/spans",
        metrics=metrics,
        logger=logged.append,
        span_factory=span_factory,
    )

    assert logged == [event]
    assert metrics.processed.value == 1
    assert metrics.duration.entries == 1
    assert span_arguments["zipkin_attrs"].trace_id == "trace-id"
    assert span_arguments["zipkin_attrs"].parent_span_id == "parent-id"
    assert span_arguments["span_name"] == "save_log"


def test_malformed_redis_item_is_counted_as_failed():
    metrics = FakeMetrics()
    logged = []

    main.process_item({"data": b"not-json"}, "", metrics=metrics, logger=logged.append)

    assert len(logged) == 1
    assert isinstance(logged[0], Exception)
    assert metrics.failed.value == 1
    assert metrics.processed.value == 0


def test_http_transport_posts_thrift_with_timeout():
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raised")

    class Session:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    main.http_transport(b"span", "http://zipkin", session=Session())

    assert calls[0] == (
        "http://zipkin",
        {
            "data": b"span",
            "headers": {"Content-Type": "application/x-thrift"},
            "timeout": 5,
        },
    )
    assert calls[1] == "raised"
