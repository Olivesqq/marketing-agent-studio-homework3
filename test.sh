#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
(cd "$PROJECT_DIR/backend" && "$PROJECT_DIR/.venv/bin/python" -m pytest tests --cov=app --cov-report=term-missing)
npm --prefix "$PROJECT_DIR/frontend" run build
