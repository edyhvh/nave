#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "❌ Missing virtualenv at $VENV_DIR"
  echo "Run: python3 setup.py"
  exit 1
fi

export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

echo "🚀 NAVE dev shell (python/pip from .venv)"
exec "${SHELL:-/bin/bash}"
