#!/usr/bin/env bash
# Unit gate entrypoint (spec 006 / T016) consumed by the reusable CI `unit` job.
# Installs the test toolchain and runs pytest with coverage over the pure
# message-handling logic (processor.py); main.py is the subscribe-loop bootstrap
# and excluded from the denominator (research D2). Fails under 70%.
set -euo pipefail
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dev.txt
python -m pytest --cov=processor --cov-report=xml --cov-report=term-missing --cov-fail-under=70
