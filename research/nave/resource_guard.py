"""Fail-closed preflight for bounded NAVE Dune work.

This is deliberately a small, explicit check rather than a second scheduler or
provider client. The caller must supply a fresh provider usage snapshot; an
unknown snapshot is not permission to spend.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


TASK_TARGET = 25.0
WARNING = 50.0
HARD_STOP = 75.0
CHECKPOINT_CAP = 200.0
MIN_FREE_DISK_GB = 15.0


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    level: str
    reasons: tuple[str, ...]
    credits_used: float
    credits_included: float
    estimate: float
    checkpoint_used: float
    projected_checkpoint_used: float
    remaining_included: float


def check(
    *,
    credits_used: float,
    credits_included: float,
    checkpoint_used: float,
    estimate: float,
    free_disk_gb: float | None = None,
) -> GuardResult:
    """Check one proposed Dune operation against the NAVE policy.

    ``credits_used`` and ``checkpoint_used`` must be fresh, trusted readings
    from the provider/account surface. Negative or contradictory inputs fail
    closed. This function does not make a Dune call and does not reserve
    credits; the caller must run it immediately before a provider call.
    """
    values = (credits_used, credits_included, checkpoint_used, estimate)
    reasons: list[str] = []
    if any(value < 0 for value in values):
        reasons.append("negative budget input")
    if credits_included <= 0:
        reasons.append("credits_included must be positive")
    if checkpoint_used > credits_used:
        reasons.append("checkpoint_used exceeds current credits_used")
    if free_disk_gb is not None and free_disk_gb < MIN_FREE_DISK_GB:
        reasons.append(f"free disk below {MIN_FREE_DISK_GB:g} GiB safety floor")

    checkpoint_delta = credits_used - checkpoint_used
    projected_checkpoint_used = checkpoint_delta + estimate
    remaining = credits_included - credits_used
    if estimate > HARD_STOP:
        reasons.append(f"single operation exceeds hard stop ({HARD_STOP:g} credits)")
    if projected_checkpoint_used > CHECKPOINT_CAP:
        reasons.append(f"checkpoint cap exceeded ({CHECKPOINT_CAP:g} credits)")
    if estimate > remaining:
        reasons.append("estimate exceeds included credits remaining")

    if reasons:
        level = "HARD_STOP"
    elif estimate > WARNING:
        level = "WARNING"
    elif estimate > TASK_TARGET:
        level = "REVIEW"
    else:
        level = "OK"

    return GuardResult(
        allowed=not reasons,
        level=level,
        reasons=tuple(reasons),
        credits_used=credits_used,
        credits_included=credits_included,
        estimate=estimate,
        checkpoint_used=checkpoint_used,
        projected_checkpoint_used=projected_checkpoint_used,
        remaining_included=remaining,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NAVE Dune credit preflight")
    parser.add_argument("--credits-used", type=float, required=True)
    parser.add_argument("--credits-included", type=float, required=True)
    parser.add_argument("--checkpoint-used", type=float, required=True)
    parser.add_argument("--estimate", type=float, required=True)
    parser.add_argument("--free-disk-gb", type=float)
    args = parser.parse_args()
    result = check(
        credits_used=args.credits_used,
        credits_included=args.credits_included,
        checkpoint_used=args.checkpoint_used,
        estimate=args.estimate,
        free_disk_gb=args.free_disk_gb,
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
