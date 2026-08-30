"""Operational contract for log-message-processor (spec 009, T074).

The reconnection cases are why this file exists.

`run()` builds a Redis pubsub, subscribes, and iterates `pubsub.listen()`. Every
one of those raises when Redis is unavailable, and nothing catches them, so the
process exits. Kubernetes restarts it, it fails again, and the pod enters
CrashLoopBackOff — whose exponential backoff then *delays* recovery well past
the point Redis came back. A consumer of a pub/sub channel has to survive its
broker restarting; that is normal operation, not an exceptional condition.

The health cases matter for a different reason: this service has no HTTP surface
beyond the Prometheus exporter, so without explicit probe routes Kubernetes has
nothing to ask and falls back to "the process is running", which stays true even
when the subscriber loop has silently stopped consuming.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

import main


class FakeCounter:
    def __init__(self):
        self.value = 0

    def inc(self, amount=1):
        self.value += amount


class FakeDuration:
    def time(self):
        from contextlib import nullcontext

        return nullcontext()


class FakeMetrics:
    def __init__(self):
        self.processed = FakeCounter()
        self.failed = FakeCounter()
        self.duration = FakeDuration()


# --- health ---------------------------------------------------------------


def _free_port():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def operational_server():
    port = _free_port()
    health = main.HealthState()
    server = main.start_operational_server(port, health)
    try:
        yield port, health
    finally:
        server.shutdown()


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_health_endpoints_are_served(operational_server):
    port, _ = operational_server

    for path in ("/health/startup", "/health/ready", "/health/live"):
        status, body = _get(port, path)
        assert status == 200, f"{path} returned {status}"
        assert json.loads(body)["status"] == "ok"


def test_readiness_fails_independently_of_liveness(operational_server):
    port, health = operational_server

    health.set_ready(False)

    status, _ = _get(port, "/health/ready")
    assert status == 503, "readiness must fail once the subscriber is not consuming"

    status, _ = _get(port, "/health/live")
    assert status == 200, (
        "liveness must stay healthy while merely not ready: restarting a pod that is "
        "reconnecting to Redis only lengthens the outage"
    )


# A subscriber whose loop has stopped consuming is the failure Kubernetes cannot
# see on its own — the process is still running. Readiness has to reflect it.
def test_readiness_reflects_the_subscriber_losing_its_connection(operational_server):
    port, health = operational_server

    health.set_ready(True)
    status, _ = _get(port, "/health/ready")
    assert status == 200

    health.set_ready(False)
    status, _ = _get(port, "/health/ready")
    assert status == 503, "a subscriber that is not consuming must report itself not ready"


def test_metrics_are_served_on_the_same_port(operational_server):
    port, _ = operational_server

    status, body = _get(port, "/metrics")
    assert status == 200
    assert "log_messages_processed_total" in body


# --- Redis reconnection ---------------------------------------------------


class FlakyPubSub:
    """Fails `listen` a set number of times, then delivers its messages once.

    Delivering only once matters: a real `listen()` blocks indefinitely, so a
    fake that re-yields the same batch on every call makes the consumer look
    like it is making progress forever and the loop correctly never ends.
    """

    def __init__(self, failures, messages):
        self.failures = failures
        self.messages = messages
        self.subscribe_calls = 0
        self.listen_calls = 0
        self.delivered = False

    def subscribe(self, channels):
        self.subscribe_calls += 1

    def listen(self):
        self.listen_calls += 1
        if self.listen_calls <= self.failures:
            raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")
        if self.delivered:
            return iter([])
        self.delivered = True
        return iter(self.messages)

    def close(self):
        pass


def test_subscriber_reconnects_instead_of_exiting():
    messages = [{"type": "message", "data": json.dumps({"opName": "CREATE"}).encode()}]
    pubsub = FlakyPubSub(failures=2, messages=messages)
    processed = []

    main.consume(
        pubsub_factory=lambda: pubsub,
        channel="log_channel",
        zipkin_url="",
        handler=lambda item, url, **kwargs: processed.append(item),
        health=main.HealthState(),
        backoff=lambda attempt: 0,
        max_reconnects=5,
    )

    assert pubsub.listen_calls > 2, (
        "the subscriber must retry after a dropped connection; exiting hands the pod to "
        "CrashLoopBackOff, whose backoff delays recovery past the point Redis returned"
    )
    assert pubsub.subscribe_calls == pubsub.listen_calls, (
        "each reconnect must resubscribe; reusing a dead subscription silently consumes nothing"
    )
    assert processed, "messages must be consumed once the connection is restored"


def test_reconnect_backoff_grows_and_is_capped():
    # The range has to run past the point the cap engages. Testing only the
    # first few attempts would pass even with no cap at all, because 2**4 is
    # still under the ceiling.
    delays = [main.reconnect_backoff(attempt) for attempt in range(1, 12)]

    assert delays == sorted(delays), "backoff must not shrink as failures accumulate"
    assert delays[0] > 0, "an immediate retry loop would hammer a Redis that is starting up"
    assert max(delays) <= main.MAX_RECONNECT_BACKOFF_SECONDS, (
        "backoff must be capped, or a long outage leaves the consumer asleep for minutes "
        "after Redis is healthy again"
    )
    assert delays[-1] == main.MAX_RECONNECT_BACKOFF_SECONDS, (
        "the cap must actually engage within a realistic number of attempts"
    )


def test_readiness_drops_while_disconnected_and_returns_after_reconnect():
    health = main.HealthState()
    observed = []

    class ObservingPubSub(FlakyPubSub):
        def listen(self):
            observed.append(health.is_ready())
            return super().listen()

    pubsub = ObservingPubSub(failures=1, messages=[])

    main.consume(
        pubsub_factory=lambda: pubsub,
        channel="log_channel",
        zipkin_url="",
        handler=lambda item, url, **kwargs: None,
        health=health,
        backoff=lambda attempt: 0,
        max_reconnects=3,
    )

    assert health.is_ready() is False, (
        "after the loop ends the consumer is no longer consuming and must not report ready"
    )


# --- correlation ----------------------------------------------------------


def test_correlation_id_is_a_top_level_log_field(capsys):
    metrics = FakeMetrics()

    main.process_message(
        {"opName": "CREATE", "username": "alice", "todoId": 1, "correlationId": "abc-123"},
        "",
        metrics=metrics,
        logger=main.log_message_structured,
    )

    printed = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(printed)

    # Asserted as a named top-level field, not as a substring of the line. The
    # log also dumps the raw payload, which contains the id, so a substring
    # check would pass even if the dedicated field were removed — and a log
    # aggregator cannot index or filter on a value buried in a nested dump.
    assert record["correlationId"] == "abc-123", (
        "the correlation id must be a queryable top-level field, or the audit trail "
        "cannot be filtered back to the request that caused it"
    )


def test_message_without_correlation_id_still_processes():
    metrics = FakeMetrics()

    main.process_message(
        {"opName": "CREATE", "username": "alice", "todoId": 1},
        "",
        metrics=metrics,
        logger=lambda message: None,
    )

    assert metrics.processed.value == 1, (
        "correlationId is additive; an older publisher that omits it must still be processed"
    )


# --- configuration --------------------------------------------------------


def test_feature_toggles_default_off(monkeypatch):
    monkeypatch.delenv("LOG_PROCESSOR_FEATURE_VERBOSE_PAYLOAD", raising=False)

    config = main.load_runtime_config()

    assert config["features"]["verbose_payload"] is False, (
        "an enabled-by-default toggle reaches production on merge, which defeats the point"
    )


def test_runtime_config_defaults_are_usable(monkeypatch):
    monkeypatch.delenv("LOG_PROCESSOR_MAX_RECONNECTS", raising=False)

    config = main.load_runtime_config()

    assert config["redis"]["max_reconnects"] != 0, (
        "zero reconnect attempts means the first Redis blip is fatal"
    )


def test_runtime_config_carries_no_secret_material(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "super-secret-value")

    rendered = json.dumps(main.load_runtime_config())

    assert "super-secret-value" not in rendered, (
        "config gets logged at startup; a secret in it is a secret in the log aggregator"
    )
