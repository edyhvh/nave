#!/bin/bash
# Simple script runner for NAVE
# Usage: ./run.sh <script_name> [args...]

if [ $# -eq 0 ]; then
    echo "Usage: ./run.sh <script_name> [args...]"
    echo "Available scripts:"
    ls scripts/*.py 2>/dev/null || echo "No scripts found"
    exit 1
fi

SCRIPT_NAME="$1"
shift

if [ -f "scripts/${SCRIPT_NAME}.py" ]; then
    python "scripts/${SCRIPT_NAME}.py" "$@"
elif [ -f "scripts/${SCRIPT_NAME}" ]; then
    python "scripts/${SCRIPT_NAME}" "$@"
else
    echo "Script '${SCRIPT_NAME}' not found in scripts/ directory"
    exit 1
fi
