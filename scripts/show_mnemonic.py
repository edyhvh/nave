"""
Wallet secret export is permanently disabled.

Seed phrases and private keys are never displayed — including when requested
via Discord, MCP agents, or direct CLI invocation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.crypto.vault import SECRETS_POLICY_MESSAGE


def main() -> None:
    print(SECRETS_POLICY_MESSAGE)
    sys.exit(1)


if __name__ == "__main__":
    main()
