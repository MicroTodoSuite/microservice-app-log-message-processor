# Build stage. Pinned Python, not the Python 3.6 EOL image used before.
FROM python:3.11.10-slim-bookworm AS build

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage. Same base, only the venv and source, no pip cache or build tooling.
FROM python:3.11.10-slim-bookworm AS runtime

RUN groupadd --gid 10001 logproc \
    && useradd --uid 10001 --gid logproc --no-create-home --shell /usr/sbin/nologin logproc

WORKDIR /app

COPY --from=build --chown=logproc:logproc /opt/venv /opt/venv
COPY --chown=logproc:logproc . .

ENV PATH="/opt/venv/bin:$PATH"

USER 10001:10001

# No EXPOSE: PORT has no default in application code (os.environ['PORT'], no fallback).

# Pure-stdlib healthcheck: avoids installing curl/wget just for this.
# hadolint ignore=DL3025
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['PORT'] + '/metrics', timeout=2)" || exit 1

CMD ["python3", "-u", "main.py"]
