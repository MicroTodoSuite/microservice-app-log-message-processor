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


def test_event_is_processed_and_counted():
    metrics = FakeMetrics()
    logged = []

    main.process_message({"opName": "CREATE"}, metrics=metrics, logger=logged.append)

    assert logged == [{"opName": "CREATE"}]
    assert metrics.processed.value == 1
    assert metrics.failed.value == 0


def test_malformed_redis_item_is_counted_as_failed():
    metrics = FakeMetrics()
    logged = []

    main.process_item({"data": b"not-json"}, metrics=metrics, logger=logged.append)

    assert len(logged) == 1
    assert isinstance(logged[0], Exception)
    assert metrics.failed.value == 1
    assert metrics.processed.value == 0

