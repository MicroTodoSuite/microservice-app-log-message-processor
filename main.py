import time
import redis
import os
import json
import requests
from py_zipkin.zipkin import zipkin_span, ZipkinAttrs, generate_random_64bit_string
import random
from prometheus_client import start_http_server, Counter, Histogram

# Prometheus metrics
MESSAGE_PROCESSED = Counter('log_messages_processed_total', 'Total number of log messages processed')
MESSAGE_FAILED = Counter('log_messages_failed_total', 'Total number of log messages failed')
MESSAGE_PROCESSING_TIME = Histogram('log_message_processing_duration_seconds', 'Duration of message processing in seconds')

def log_message(message):
    """
    Simulates processing of a log message by introducing a random delay and then printing the message.

    Args:
        message (str): The log message to be processed.
    """
    time_delay = random.randrange(0, 2000)  # Random delay between 0 and 2000 milliseconds
    time.sleep(time_delay / 1000)  # Convert milliseconds to seconds
    print(f'message received after waiting for {time_delay}ms: {message}')

if __name__ == '__main__':
    # Start Prometheus HTTP server
    start_http_server(int(os.environ['PORT']))

    # Retrieve configuration from environment variables
    redis_host = os.environ['REDIS_HOST']
    redis_port = int(os.environ['REDIS_PORT'])
    redis_channel = os.environ['REDIS_CHANNEL']
    zipkin_url = os.environ['ZIPKIN_URL'] if 'ZIPKIN_URL' in os.environ else ''
    def http_transport(encoded_span):
        """
        Send the encoded span data to Zipkin.

        Args:
            encoded_span (bytes): Encoded span data to be sent to Zipkin.
        """
        requests.post(
            zipkin_url,
            data=encoded_span,
            headers={'Content-Type': 'application/x-thrift'},
        )

    # Initialize Redis client and subscribe to the specified channel
    pubsub = redis.Redis(host=redis_host, port=redis_port, db=0).pubsub()
    pubsub.subscribe([redis_channel])

    # Process messages from the Redis channel
    for item in pubsub.listen():
        try:
            # Decode and parse the message
            message = json.loads(str(item['data'].decode("utf-8")))
        except Exception as e:
            log_message(e)
            MESSAGE_FAILED.inc()
            continue

        # Check for Zipkin tracing data
        if not zipkin_url or 'zipkinSpan' not in message:
            log_message(message)
            MESSAGE_PROCESSED.inc()
            continue

        # Extract span data and perform tracing
        span_data = message['zipkinSpan']
        try:
            with MESSAGE_PROCESSING_TIME.time():
                with zipkin_span(
                    service_name='log-message-processor',
                    zipkin_attrs=ZipkinAttrs(
                        trace_id=span_data['_traceId']['value'],
                        span_id=generate_random_64bit_string(),
                        parent_span_id=span_data['_spanId'],
                        is_sampled=span_data['_sampled']['value'],
                        flags=None
                    ),
                    span_name='save_log',
                    transport_handler=http_transport,
                    sample_rate=100
                ):
                    log_message(message)
                    MESSAGE_PROCESSED.inc()
        except Exception as e:
            print(f'did not send data to Zipkin: {e}')
            log_message(message)
            MESSAGE_FAILED.inc()
