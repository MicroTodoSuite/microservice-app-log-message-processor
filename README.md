# Log Message Processor
This service is written in Python. This is a consumer that listens for
new messages in Redis queue and prints message content to the standard output.

## Configuration

The service scans environment for variables:
- `REDIS_HOST` - host of Redis
- `REDIS_PORT` - port of Redis
- `REDIS_CHANNEL` - channel the processor is going to listen to

## Metrics

Metrics are recorded through OpenTelemetry. An OpenTelemetry Prometheus reader
writes into its own registry, which the operational server serves at
`GET /metrics` on `PORT`, without scope labels, `target_info`, or `process_` and
`python_` runtime metrics.

- `log_messages_processed_total` - messages processed
- `log_messages_failed_total` - messages that failed processing
- `log_message_processing_duration_seconds` - processing duration histogram

## Building 

```
pip3 install -r requirements.txt
```
## Running
```
REDIS_HOST=127.0.0.1 REDIS_PORT=6379 REDIS_CHANNEL=log_channel python3 main.py
```
## Dependencies
The software required to run this microservice, and the version that was tested:
|  Dependency | Version  |
|-------------|----------|
| Redis       | 7.0      |
| Python      | 3.6      |
| Pip         | default  |

`default` is the one comes with Python<!-- test/gate-prod-notification-e2e: harmless trigger to verify the prod-environment gate now notifies Slack instead of pausing silently -->
