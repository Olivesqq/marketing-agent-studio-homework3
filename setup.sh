#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/backend/requirements-dev.txt"
npm --prefix "$PROJECT_DIR/frontend" ci
echo "安装完成。执行 ./start.sh 启动，或 ./test.sh 运行测试。"

