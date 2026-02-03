#!/usr/bin/env bash
# Local build and deploy: build frontend, then run backend (serves API + built app)
# Run from project root. Requires: Node, npm, Python, Postgres (for DB).

set -e
cd "$(dirname "$0")/.."

echo "Building frontend..."
cd frontend && npm run build && cd ..

echo "Frontend built to frontend/dist"
echo ""
echo "To run the app (backend serves API + frontend):"
echo "  cd backend"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Then open: http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
