#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
"$PY" tools/install_demo.py
printf '\nZum Schließen Enter drücken.\n'
if [ -t 0 ]; then read -r; fi
