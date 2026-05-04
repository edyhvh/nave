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
    project_root = tmp_path / "project"
    raw_dir = project_root / "docs" / "analysis" / "raw"
    raw_dir.mkdir(parents=True)

    monkeypatch.setattr(module, "PROJECT_ROOT", project_root)

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
    assert captured_paths["raw_dir"] == raw_dir
    written = json.loads((raw_dir / "momentum_review_latest.json").read_text())
    assert written["total_trades"] == 10
    assert captured.err == ""


def test_momentum_theory_overlay_review_script_json_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    module = _load_script_module("momentum_theory_overlay_review_script", "scripts/momentum_theory_overlay_review.py")
    summary = {"generated_at": "2026-05-01T00:00:00+00:00", "mode": "replay", "pooled": {"kept_trades": 10}}
    captured_paths: dict[str, object] = {}
    project_root = tmp_path / "project"
    raw_dir = project_root / "docs" / "analysis" / "raw"
    raw_dir.mkdir(parents=True)

    monkeypatch.setattr(module, "PROJECT_ROOT", project_root)

    def evaluate_overlay_replay(raw_dir: Path, periods=None):
        captured_paths["raw_dir"] = raw_dir
        captured_paths["periods"] = periods
        return summary

    def sweep_overlay_parameters(*args, **kwargs):
        raise AssertionError("sweep helper should not be called in replay mode")

    def write_overlay_review_markdown(payload: dict, output_path: Path):
        captured_paths["markdown"] = output_path
        return output_path

    monkeypatch.setattr(
        module,
        "_load_overlay_review_helpers",
        lambda: (evaluate_overlay_replay, sweep_overlay_parameters, write_overlay_review_markdown),
    )

    exit_code = module.main(["--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    decoded = json.loads(captured.out)
    assert decoded["summary"]["pooled"]["kept_trades"] == 10
    assert decoded["artifacts"]["markdown"] == "docs/analysis/momentum_theory_overlay_replay.md"
    assert decoded["artifacts"]["json"] == "docs/analysis/raw/momentum_theory_overlay_replay_latest.json"
    assert captured_paths["raw_dir"] == raw_dir
    written = json.loads((raw_dir / "momentum_theory_overlay_replay_latest.json").read_text())
    assert written["pooled"]["kept_trades"] == 10
    assert captured.err == ""


def test_momentum_theory_overlay_review_script_sweep_json_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    module = _load_script_module("momentum_theory_overlay_review_script_sweep", "scripts/momentum_theory_overlay_review.py")
    summary = {"generated_at": "2026-05-01T00:00:00+00:00", "mode": "sweep", "top_candidates": [{"kept_win_rate": 0.81}]}
    captured_paths: dict[str, object] = {}
    project_root = tmp_path / "project"
    raw_dir = project_root / "docs" / "analysis" / "raw"
    raw_dir.mkdir(parents=True)

    monkeypatch.setattr(module, "PROJECT_ROOT", project_root)

    def evaluate_overlay_replay(*args, **kwargs):
        raise AssertionError("replay helper should not be called in sweep mode")

    def sweep_overlay_parameters(raw_dir: Path, periods=None, chase_min_retrace_values=None, chase_min_expected_move_pct_values=None):
        captured_paths["raw_dir"] = raw_dir
        captured_paths["retrace_values"] = chase_min_retrace_values
        captured_paths["move_values"] = chase_min_expected_move_pct_values
        return summary

    def write_overlay_review_markdown(payload: dict, output_path: Path):
        captured_paths["markdown"] = output_path
        return output_path

    monkeypatch.setattr(
        module,
        "_load_overlay_review_helpers",
        lambda: (evaluate_overlay_replay, sweep_overlay_parameters, write_overlay_review_markdown),
    )

    exit_code = module.main([
        "--json",
        "--sweep",
        "--chase-min-retrace-values",
        "0.1,0.2",
        "--chase-min-expected-move-pct-values",
        "0.08,0.1",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    decoded = json.loads(captured.out)
    assert decoded["summary"]["top_candidates"][0]["kept_win_rate"] == 0.81
    assert decoded["artifacts"]["markdown"] == "docs/analysis/momentum_theory_overlay_sweep.md"
    assert decoded["artifacts"]["json"] == "docs/analysis/raw/momentum_theory_overlay_sweep_latest.json"
    assert captured_paths["raw_dir"] == raw_dir
    assert captured_paths["retrace_values"] == [0.1, 0.2]
    assert captured_paths["move_values"] == [0.08, 0.1]
    written = json.loads((raw_dir / "momentum_theory_overlay_sweep_latest.json").read_text())
    assert written["mode"] == "sweep"
    assert captured.err == ""
