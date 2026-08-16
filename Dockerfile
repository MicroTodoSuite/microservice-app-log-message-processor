FROM python:3.13-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS dependencies

WORKDIR /src
COPY requirements.txt ./
RUN python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --no-compile \
      --require-hashes \
      --target /opt/runtime \
      -r requirements.txt

FROM python:3.13-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

RUN python -m pip uninstall --yes msgpack setuptools wheel pip \
    && groupadd --gid 10001 logproc \
    && useradd --uid 10001 --gid logproc --no-create-home --shell /usr/sbin/nologin logproc

WORKDIR /app
COPY --from=dependencies --chown=logproc:logproc /opt/runtime /opt/runtime
COPY --chown=logproc:logproc main.py /app/main.py

ENV PYTHONPATH=/opt/runtime \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
CMD ["python3", "/app/main.py"]
