"""Integration test (spec 007 / T015): exercises the real subscribe/consume path
over a disposable Redis provided by Testcontainers. Requires Docker."""
import json

import redis
from testcontainers.redis import RedisContainer

import main


class _Counter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1


class _Metrics:
    def __init__(self):
        self.processed = _Counter()
        self.failed = _Counter()


def _await_message(pubsub, timeout=5.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if message is not None:
            return message
    raise AssertionError("no message received on log_channel")


def test_consumes_published_log_channel_event_over_real_redis():
    with RedisContainer("redis:7-alpine") as container:
        client = redis.Redis(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(6379)),
            db=0,
        )
        channel = "it-log-channel"
        pubsub = client.pubsub()
        pubsub.subscribe(channel)

        payload = json.dumps({"opName": "CREATE", "username": "alice", "todoId": 3})
        client.publish(channel, payload)

        message = _await_message(pubsub)
        item = {"data": message["data"]}  # bytes, as delivered by redis pub/sub

        metrics = _Metrics()
        logged = []
        main.process_item(item, "", metrics=metrics, logger=logged.append)

        assert metrics.processed.count == 1
        assert metrics.failed.count == 0
        assert logged and logged[0]["opName"] == "CREATE"
        assert logged[0]["username"] == "alice"

        pubsub.close()
        client.close()
