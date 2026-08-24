#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "未找到 .venv。请先在项目根目录执行 ./setup.sh"
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

