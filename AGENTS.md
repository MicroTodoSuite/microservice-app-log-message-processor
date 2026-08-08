## Overview
This Python service is a long-running Redis Pub/Sub consumer that parses JSON messages, waits for a randomized processing delay, and writes them to standard output.
It also serves Prometheus metrics and can forward trace spans to Zipkin when a message contains tracing data and a Zipkin endpoint is configured.

## Stack
- Runtime: Python 3.6, verified by both `FROM python:3.6` and the README.
- Framework: none; the service is a standalone Python script.
- Runtime packages: `redis==2.10.6`; `prometheus_client`, `py_zipkin`, `requests`, and `cython` are declared without versions.
- Release tooling: Node.js 22 in CI, with locked Semantic Release 24.2.3, `@semantic-release/changelog` 6.0.3, and `@semantic-release/git` 10.0.1.

## Commands
- Install/build dependencies: `pip3 install -r requirements.txt`
- Build the CI container image: `docker build -t $ACR_NAME/${{ env.SERVICE_NAME }}:${{ steps.get-version.outputs.version }} -t $ACR_NAME/${{ env.SERVICE_NAME }}:latest .`
- Local run documented in the README: `REDIS_HOST=127.0.0.1 REDIS_PORT=6379 REDIS_CHANNEL=log_channel python3 main.py`
- The documented local-run command is incomplete: `main.py` also requires `PORT`, and the repository defines no default or corrected command.
- Test script: `npm test`; it runs `echo "Error: no test specified" && exit 1`. No test files or functional test command exist.

## Structure
- `main.py`: application entrypoint, Redis subscription loop, metrics, message processing, and optional Zipkin transport.
- `.github/workflows/`: Semantic Release automation and the current Azure Container Apps image build/deployment pipeline.
- `requirements.txt`: Python runtime dependencies.
- `package.json` and `package-lock.json`: Node-based release tooling; they do not define the application runtime.
- `Dockerfile`: Python 3.6 image that installs requirements and runs `python3 -u main.py` from `/app`.
- The repository has no source package directory, Kubernetes manifests, Azure Container Apps manifest, or test directory.

## Conventions
- The application is a single synchronous script, not an HTTP framework application; its only HTTP listener is the Prometheus server.
- Redis database 0 and Pub/Sub are hard-coded; the host, port, and channel come from environment variables.
- Message processing intentionally sleeps for a random 0-1999 ms before logging to standard output.
- Zipkin submission is optional and occurs only when `ZIPKIN_URL` is set and the message has a `zipkinSpan` field.
- Node dependencies are used only for Semantic Release; application dependencies are managed with `requirements.txt`.

## Notes for the Kubernetes migration
- The only exposed runtime port is the Prometheus HTTP server port from required `PORT`; the Dockerfile has no `EXPOSE`, and the code provides no default port.
- Required runtime variables are `PORT`, `REDIS_HOST`, `REDIS_PORT`, and `REDIS_CHANNEL`; `ZIPKIN_URL` is optional and defaults to disabled.
- Redis is the required external service, using database 0 and the configured Pub/Sub channel. The README records Redis 7.0 as tested.
- Zipkin is optional; spans are sent with an HTTP POST using `application/x-thrift`. No database or other outbound HTTP service is present.
- There is no health endpoint, Docker `HEALTHCHECK`, readiness check, or liveness check; Prometheus metrics alone do not verify the Redis subscription.
- Review the Python 3.6 base image, mostly unpinned Python dependencies, root container user, broad `COPY . .`, and missing `.dockerignore` before producing the Kubernetes image.
- The Azure workflow currently pushes release and `latest` tags to ACR, then runs `az containerapp update` and restarts a revision using Azure credentials, resource-group, and subscription secrets.
- Replace that direct Azure deployment with a commit to `microservice-app-gitops` reconciled by ArgoCD; do not use direct `kubectl apply` against the GitOps-managed cluster.
