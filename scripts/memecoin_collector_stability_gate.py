#!/usr/bin/env python3
"""Run the frozen 30-minute operational gate; no model, strategy or outcome reads."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.nave.collector_health_gate import run_gate
from research.nave.prospective_runtime import CONTRACT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--contract', type=Path, default=CONTRACT_PATH)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        parser.error('run-id must be one path component')
    result = run_gate(args.data_root.resolve(), args.contract.resolve(), args.run_id)
    print(result['status'])
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
