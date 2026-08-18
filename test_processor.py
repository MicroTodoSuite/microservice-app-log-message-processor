"""Unit tests for the log_channel message-handling logic (spec 006 / T016)."""
import json

import pytest

import processor


def test_decode_message_parses_valid_json_bytes():
    raw = json.dumps({"opName": "CREATE", "username": "alice", "todoId": 3}).encode("utf-8")

    message = processor.decode_message(raw)

    assert message["opName"] == "CREATE"
    assert message["username"] == "alice"
    assert message["todoId"] == 3


def test_decode_message_raises_on_malformed_payload():
    with pytest.raises(json.JSONDecodeError):
        processor.decode_message(b"not-json")


@pytest.mark.parametrize(
    "message,zipkin_url,expected",
    [
        ({"zipkinSpan": {}}, "http://zipkin:9411", True),
        ({"zipkinSpan": {}}, "", False),          # tracing not configured
        ({"opName": "CREATE"}, "http://zipkin", False),  # no span data
        ("a-string", "http://zipkin", False),      # non-dict message
    ],
)
def test_has_trace(message, zipkin_url, expected):
    assert processor.has_trace(message, zipkin_url) is expected


def test_log_message_prints_message_without_real_delay(monkeypatch, capsys):
    monkeypatch.setattr(processor.random, "randrange", lambda *_: 0)
    monkeypatch.setattr(processor.time, "sleep", lambda *_: None)

    processor.log_message({"opName": "DELETE", "todoId": "2"})

    out = capsys.readouterr().out
    assert "message received after waiting for 0ms" in out
    assert "DELETE" in out
