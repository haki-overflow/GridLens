#!/usr/bin/env bash
# Build the workspace (web/) if needed, then serve it with the API on :8000.
cd "$(dirname "$0")"
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html -newer web/dist/index.html -print -quit 2>/dev/null)" ]; then
  (cd web && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build) || exit 1
fi
PY=python3; [ -x venv/bin/python ] && PY=venv/bin/python
exec "$PY" -m uvicorn api.server:app --port 8000 "$@"
