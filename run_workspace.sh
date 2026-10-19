#!/usr/bin/env bash
# Build the web workspace if web/dist is missing or older than its sources,
# then serve it (and the API) on http://localhost:8000.
set -e
cd "$(dirname "$0")"
if [ ! -f web/dist/index.html ] || \
   [ -n "$(find web/src web/index.html web/package.json web/vite.config.ts \
           -newer web/dist/index.html -print -quit)" ]; then
  echo "Building web workspace..."
  [ -d web/node_modules ] || (cd web && npm install)
  (cd web && npm run build)
fi
exec venv/bin/uvicorn api.server:app --port 8000 "$@"
