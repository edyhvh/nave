#!/bin/bash
# Nave run script - quick access to common workflows

set -euo pipefail

cd \"$(dirname \"${BASH_SOURCE[0]}\")\"

case \"${1:-}\" in
  \"openbb_tools\")
    python scripts/openbb_tools.py
    ;;
  \"trading\")
    python -m trading.strategy --dry-run
    ;;
  \"weekly-cot\")
    python scripts/weekly_cot_analysis.py
    ;;
  \"*\")
    echo \"Usage: ./run.sh [openbb_tools|trading|weekly-cot]\" >&2
    exit 1
    ;;
esac