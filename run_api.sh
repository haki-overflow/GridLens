#!/usr/bin/env bash
cd "$(dirname "$0")"
exec venv/bin/uvicorn api.server:app --port 8000 --reload "$@"
