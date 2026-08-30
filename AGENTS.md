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
- Write everything in English — branch names, commit messages, pull-request titles and bodies, review comments, code comments, documentation, and specification text. No bilingual sections. Changing this rule takes a recorded decision in `microservice-app-docs`, not a remark in conversation.
- Open every pull request through `.github/pull_request_template.md` and follow `microservice-app-docs/docs/Pull request and task tracking conventions.md`: one concern per short-lived `<type>/<summary>` branch, a Conventional Commit title with a scope, and every template section filled. Constitution principle 13 makes this binding, not advisory.
- Keep the Spec-Driven Development commit pair intact: `test(<scope>): specify ...` must be committed failing before `feat(<scope>): implement ...`. Never squash the pair; the failing-test commit is the evidence the cycle was followed.
- Track every task. Name in the pull-request body the task IDs it advances, qualified by repository and spec, and update `tasks.md` in that same pull request rather than a follow-up. Mark a task `[X]` only after locating and inspecting its named artifact — never from a summary, a green check, a rendered manifest, or recollection. Annotate partial delivery instead of ticking it; work no register covers either gains a task or records in the PR body why none applies.
- Reconcile, never quietly edit, when a register and reality disagree: a specification that pins a version nobody shipped is a maintainer decision, and `microservice-app-docs/full-platform/plan-reconciliation.md` is the worked example.
- Never merge with `--admin`, force-push to `main`, disable a branch protection rule to land your own work, or approve your own pull request. As an AI agent you may open, describe, and update a pull request; you may never approve one and never author an acceptance or approval artifact — only a named human unlocks a gate.
- Report outcomes faithfully in commits and pull-request bodies: name what is red, say what was skipped, and correct an earlier claim that turns out to be wrong rather than leaving the record wrong.

## Notes for the Kubernetes migration
- The only exposed runtime port is the Prometheus HTTP server port from required `PORT`; the Dockerfile has no `EXPOSE`, and the code provides no default port.
- Required runtime variables are `PORT`, `REDIS_HOST`, `REDIS_PORT`, and `REDIS_CHANNEL`; `ZIPKIN_URL` is optional and defaults to disabled.
- Redis is the required external service, using database 0 and the configured Pub/Sub channel. The README records Redis 7.0 as tested.
- Zipkin is optional; spans are sent with an HTTP POST using `application/x-thrift`. No database or other outbound HTTP service is present.
- There is no health endpoint, Docker `HEALTHCHECK`, readiness check, or liveness check; Prometheus metrics alone do not verify the Redis subscription.
- Review the Python 3.6 base image, mostly unpinned Python dependencies, root container user, broad `COPY . .`, and missing `.dockerignore` before producing the Kubernetes image.
- The Azure workflow currently pushes release and `latest` tags to ACR, then runs `az containerapp update` and restarts a revision using Azure credentials, resource-group, and subscription secrets.
- Replace that direct Azure deployment with a commit to `microservice-app-gitops` reconciled by ArgoCD; do not use direct `kubectl apply` against the GitOps-managed cluster.
