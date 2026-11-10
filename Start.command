#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
if [ ! -x .venv/bin/python ] || [ ! -f frontend/dist/index.html ]; then
  bash Installation.command
fi
if .venv/bin/python launcher.py; then
  exit 0
else
  status=$?
  printf '\nStart fehlgeschlagen. Zum Schließen Enter drücken.\n'
  if [ -t 0 ]; then read -r; fi
  exit "$status"
fi
