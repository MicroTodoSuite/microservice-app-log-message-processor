"""Metrics contract for log-message-processor (gitops spec 011 T003).

The golden-signal recording rules read these series, so their names, labels,
and histogram buckets must survive the move to OpenTelemetry, and nothing the
specification drops (runtime families, scope labels, target_info) may leak into
the exposition. The traffic rule adds rate(processed) and rate(failed), so both
counters must be exposed from the start, before any message fails.
"""
import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import main

# prometheus_client 0.26.0's DEFAULT_BUCKETS, preserved by spec 011 research R3.
BOUNDARIES = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf")]


@pytest.fixture
def exposition():
    main.process_message({"opName": "CREATE", "username": "metrics", "todoId": 1}, logger=lambda message: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), main._operational_handler(main.HealthState()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
            assert response.status == 200
            return response.read().decode()
    finally:
        server.shutdown()
        server.server_close()


def samples(body, name):
    return [line for line in body.splitlines() if line.startswith(name + "{") or line.startswith(name + " ")]


def labels(line):
    inner = re.match(r"^[^{\s]+\{([^}]*)\}", line)
    return dict(re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', inner.group(1))) if inner else {}


def test_both_counters_are_exposed_without_labels_before_any_failure(exposition):
    for name in ("log_messages_processed_total", "log_messages_failed_total"):
        lines = samples(exposition, name)
        assert lines, f"{name} must be exposed even before it is incremented"
        for line in lines:
            assert labels(line) == {}, line


def test_the_duration_histogram_keeps_its_name_and_buckets(exposition):
    buckets = samples(exposition, "log_message_processing_duration_seconds_bucket")
    assert [set(labels(line)) for line in buckets] == [{"le"}] * len(buckets)
    assert [float(labels(line)["le"]) for line in buckets] == BOUNDARIES
    for suffix in ("_sum", "_count"):
        lines = samples(exposition, "log_message_processing_duration_seconds" + suffix)
        assert lines, f"log_message_processing_duration_seconds{suffix} is missing"
        assert all(labels(line) == {} for line in lines)


def test_the_exposition_has_no_scope_labels_target_info_or_runtime_families(exposition):
    assert "otel_scope_" not in exposition
    offending = [
        line for line in exposition.splitlines()
        if line.startswith(("target_info", "process_", "python_"))
    ]
    assert offending == []


def test_no_metric_is_recorded_through_the_prometheus_client_api():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert not re.search(r"^from prometheus_client import .*\b(Counter|Histogram|Gauge|Summary)\b", source, re.MULTILINE)
    assert not re.search(r"prometheus_client\.(Counter|Histogram|Gauge|Summary)\(", source)
