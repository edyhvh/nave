"""Bounded CLI execution and durable artifacts for Hermes no-agent jobs.

No scheduler, transport, order execution, or live job mutation lives here.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
from typing import Any
import json

from research.core.contracts import ResearchResult, ResearchStatus, RunMetadata
from research.core.store import ResearchStore
from research.orchestration import present_result
from trading.stocks.operational_calendar import operational_now


COMMANDS = {
    "cava": ("intel", "cava", "daily"),
    "watch": ("portfolio", "watch"),
    "portfolio": ("portfolio", "review"),
    "ism": ("portfolio", "ism"),
    "disclosures": ("disclosures", "sync"),
    "crypto": ("crypto", "futures", "scan"),
    "memecoin": ("memecoin", "discover"),
    "shorts": ("stocks", "short", "scan"),
}
WORKFLOWS = {"cava": "intel.cava.daily", "watch": "portfolio.watch", "portfolio": "portfolio.review",
             "ism": "portfolio.ism", "disclosures": "disclosures.sync", "crypto": "crypto.futures.scan", "memecoin": "memecoin.discover", "shorts": "stocks.short.scan"}


def run(workflow: str, *, state_dir: Path, channel_id: str, input_file: Path | None = None,
        now: datetime | None = None) -> dict[str, Any]:
    if workflow not in COMMANDS:
        raise ValueError("unsupported Quant workflow")
    if not channel_id.isdigit() or len(channel_id) < 15:
        raise ValueError("explicit numeric parent channel required")
    if not operational_now(now):
        return {"discord_text": "[SILENT]", "delivery": {"silent": True}, "reason": "shabbat"}
    if workflow == "memecoin" and (input_file is None or not input_file.is_file()):
        raise ValueError("memecoin requires an explicit frozen snapshot file")
    command = [sys.executable, "-m", "cli.main", *COMMANDS[workflow], "--state-dir", str(state_dir.resolve()), "--json"]
    if workflow in {"memecoin", "shorts"} and input_file is not None:
        command.extend(["--input-file", str(input_file.resolve())])
    started = datetime.now(UTC)
    try:
        completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                   text=True, timeout=300, check=True)
        result = ResearchResult.from_dict(json.loads(completed.stdout))
        if result.workflow != WORKFLOWS[workflow]:
            raise ValueError("CLI returned the wrong workflow")
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        # Do not dump provider stderr, env, prompts, or credential-bearing URLs.
        now_utc = datetime.now(UTC)
        import uuid
        result = ResearchResult(workflow=WORKFLOWS[workflow], status=ResearchStatus.DATA_UNAVAILABLE,
                                metadata=RunMetadata(strategy_name="quant-cli-executor", strategy_version="1", run_id=str(uuid.uuid4()),
                                                     decision_time=now_utc, started_at=started, completed_at=now_utc),
                                payload={"execution_enabled": False, "failure_kind": type(exc).__name__},
                                warnings=("El CLI no produjo un resultado válido; revisar datos/configuración antes de repetir.",))
    view = present_result(result, channel_id=channel_id)
    # Unique artifacts survive later runs and failed delivery. No automatic replay.
    journal = state_dir / "quant_runs" / result.metadata.run_id
    ResearchStore._atomic_write(journal / "result.json", result.to_dict())
    ResearchStore._atomic_write(journal / "presentation.json", view)
    return view
