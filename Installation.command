#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
printf 'Master Learning Hub – lokale Installation\n'
if ! command -v python3 >/dev/null; then
  printf 'Python 3.9 oder neuer wird benötigt. Bitte Python installieren und erneut starten.\n'
  exit 1
fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --no-cache-dir -r requirements.txt
if ! command -v npm >/dev/null; then
  printf 'Node.js mit npm wird einmal zum Bauen der Oberfläche benötigt.\n'
  exit 1
fi
(cd frontend && npm ci --ignore-scripts --no-audit --no-fund --cache ../.npm-cache && npm run build)
printf '\nInstallation abgeschlossen. Zum Lernen Start.command öffnen.\n'
