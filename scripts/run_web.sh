#!/usr/bin/env bash
# Start the Researcheus Maximus web server.
#
# The desktop app is unaffected and still runs with `python3 app.py`.
#
# Demo mode is the default. To run live research, export keys before starting:
#   export RESEARCHEUS_API_KEY=...          # synthesis provider key
#   export RESEARCHEUS_TVREMIX_KEY=...      # TV Remix, for Technical reports
#   export RESEARCHEUS_MODEL=...            # optional model override
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Researcheus Maximus -> http://localhost:${PORT}"
exec uvicorn backend.app:app --host "${HOST:-127.0.0.1}" --port "${PORT}"
