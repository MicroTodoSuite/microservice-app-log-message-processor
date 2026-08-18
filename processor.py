"""Pure message-handling logic for the log-message-processor.

Split out from main.py so the log_channel consumer's business logic is
unit-testable without Redis, Zipkin, or Prometheus (spec 006 / T016). main.py
imports these helpers and keeps only process bootstrap + the subscribe loop.
"""
import json
import random
import time


def decode_message(data):
    """Decode a Redis pub/sub payload into a message object.

    Args:
        data (bytes): raw payload received on the log_channel.

    Returns:
        The parsed message (a dict for a well-formed todo event).

    Raises:
        json.JSONDecodeError: if the payload is not valid JSON.
        UnicodeDecodeError: if the payload is not valid UTF-8.
    """
    return json.loads(str(data.decode("utf-8")))


def has_trace(message, zipkin_url):
    """Whether a message should be processed inside a Zipkin span.

    True only when tracing is configured and the message carries span data.
    """
    return bool(zipkin_url) and isinstance(message, dict) and 'zipkinSpan' in message


def log_message(message):
    """Simulate processing by waiting a random short delay, then printing.

    Args:
        message: the decoded log message (or an error) to report.
    """
    time_delay = random.randrange(0, 2000)  # 0..2000 ms
    time.sleep(time_delay / 1000)
    print(f'message received after waiting for {time_delay}ms: {message}')
