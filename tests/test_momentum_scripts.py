from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_script_module(name: str, relative_path: str):
    script_path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_momentum_backtest_script_json_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    module = _load_script_module("momentum_backtest_script", "scripts/momentum_backtest.py")
    payload = {"period": "2022-bear", "pooled": {"trade_count": 3}, "automation": {"ready": False, "warnings": []}}
    artifact_path = tmp_path / "artifact.json"
    iteration_path = tmp_path / "iter_1.md"

    monkeypatch.setattr(
        module,
        "_load_workflow_helpers",
        lambda: (
            lambda *args, **kwargs: "human summary",
            lambda *args, **kwargs: payload,
            lambda *args, **kwargs: iteration_path,
            lambda *args, **kwargs: artifact_path,
        ),
    )

    exit_code = module.main(["--period", "2022-bear", "--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    decoded = json.loads(captured.out)
    assert decoded["artifacts"]["backtest_json"] == str(artifact_path)
    assert decoded["artifacts"]["iteration_report"] == str(iteration_path)
    assert decoded["result"]["period"] == "2022-bear"
    assert decoded["result"]["automation"]["ready"] is False
    assert captured.err == ""


def test_momentum_review_script_json_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    module = _load_script_module("momentum_review_script", "scripts/momentum_review.py")
    summary = {"generated_at": "2026-04-28T00:00:00+00:00", "total_trades": 10, "automation": {"ready": False, "warnings": []}}
    captured_paths: dict[str, Path] = {}

    def build_review_summary(raw_dir: Path):
        captured_paths["raw_dir"] = raw_dir
        return summary

    def write_review_markdown(payload: dict, output_path: Path):
        captured_paths["markdown"] = output_path
        return output_path

    monkeypatch.setattr(module, "_load_review_helpers", lambda: (build_review_summary, write_review_markdown))

    exit_code = module.main(["--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    decoded = json.loads(captured.out)
    assert decoded["summary"]["total_trades"] == 10
    assert decoded["summary"]["automation"]["ready"] is False
    assert decoded["artifacts"]["markdown"] == "docs/analysis/momentum_historical_review.md"
    assert decoded["artifacts"]["json"] == "docs/analysis/raw/momentum_review_latest.json"
    assert captured_paths["raw_dir"] == PROJECT_ROOT / "docs" / "analysis" / "raw"
    assert captured.err == ""
