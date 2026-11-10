#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m pip install --no-cache-dir -r requirements-dev.txt
.venv/bin/python -m pytest -q
(cd frontend && npm run build)
