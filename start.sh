#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  echo "请先执行 ./setup.sh"
  exit 1
fi

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd "$PROJECT_DIR/backend" && "$PROJECT_DIR/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!
cd "$PROJECT_DIR/frontend"
npm run dev -- --host 127.0.0.1

