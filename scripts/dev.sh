#!/usr/bin/env sh
# Starts the backend (port 8000) and the Vite dev server (port 5173) for development.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && .venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
cd "$ROOT/frontend" && npm run dev
