"""M3 forward-observation data-integrity regressions."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone


def _module():
    from pathlib import Path
    path = Path(__file__).parents[2] / "var/memecoin_m3/resolve_outcomes.py"
    spec = importlib.util.spec_from_file_location("m3_resolve", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_malformed_pair_does_not_discard_valid_solana_pair():
    m3 = _module()
    best = m3.best_solana_pair([
        None,
        "malformed pair",
        {"chainId": "solana", "liquidity": {"usd": "not-a-number"}},
        {"chainId": "solana", "priceUsd": "1.25", "liquidity": {"usd": 4200}},
    ])
    assert best[0]["priceUsd"] == "1.25"
    assert best[1] == 4200


def test_systemic_temporary_provider_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    m3 = _module()
    journal = {
        "entries": {
            "mint": {
                "logged_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "market": {"price_usd": 1.0, "liquidity_usd": 50000},
                "outcomes": {},
            }
        }
    }
    journal_path = tmp_path / "signal_journal.json"
    journal_path.write_text(json.dumps(journal))
    monkeypatch.setattr(m3, "JOURNAL", str(journal_path))
    monkeypatch.setattr(m3, "fetch_pairs", lambda _mint: {
        "error_kind": m3.TEMPORARY_FAILURE,
        "error": "provider timeout",
    })
    assert m3.main() == 1
    saved = json.loads(journal_path.read_text())
    outcome = saved["entries"]["mint"]["outcomes"]["24h"]
    assert outcome["resolution_status"] == m3.PROVIDER_UNAVAILABLE
    assert outcome["ret_pct"] is None


def _due_journal(tmp_path, market=None):
    return_path = tmp_path / "signal_journal.json"
    return_path.write_text(json.dumps({"entries": {"mint": {
        "logged_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "market": market or {"price_usd": 1.0, "liquidity_usd": 50000},
        "outcomes": {},
    }}}))
    return return_path


def test_no_pair_is_counted_as_dead_loss(tmp_path, monkeypatch):
    m3 = _module()
    path = _due_journal(tmp_path)
    monkeypatch.setattr(m3, "JOURNAL", str(path))
    monkeypatch.setattr(m3, "fetch_pairs", lambda _mint: [])
    assert m3.main() == 0
    outcome = json.loads(path.read_text())["entries"]["mint"]["outcomes"]["24h"]
    assert outcome["resolution_status"] == m3.DEAD
    assert outcome["cls"] == m3.DEAD
    assert outcome["ret_pct"] == -100.0


def test_migrated_venue_does_not_substitute_current_pair(tmp_path, monkeypatch):
    m3 = _module()
    path = _due_journal(tmp_path, {"price_usd": 1.0, "liquidity_usd": 50000,
                                  "pair_address": "entry-pair"})
    monkeypatch.setattr(m3, "JOURNAL", str(path))
    monkeypatch.setattr(m3, "fetch_pairs", lambda _mint: [{
        "chainId": "solana", "pairAddress": "migrated-pair", "priceUsd": "2",
        "liquidity": {"usd": 50000},
    }])
    assert m3.main() == 0
    outcome = json.loads(path.read_text())["entries"]["mint"]["outcomes"]["24h"]
    assert outcome["resolution_status"] == m3.UNEXITABLE
    assert outcome["ret_pct"] == -100.0


def test_legacy_entry_does_not_select_current_best_pair(tmp_path, monkeypatch):
    m3 = _module()
    path = _due_journal(tmp_path)
    monkeypatch.setattr(m3, "JOURNAL", str(path))
    monkeypatch.setattr(m3, "fetch_pairs", lambda _mint: [{
        "chainId": "solana", "pairAddress": "current", "priceUsd": "2",
        "liquidity": {"usd": 50000},
    }])
    assert m3.main() == 0
    outcome = json.loads(path.read_text())["entries"]["mint"]["outcomes"]["24h"]
    assert outcome["resolution_status"] == m3.LEGACY_UNKNOWN
    assert outcome["ret_pct"] is None


def test_adjacent_replay_does_not_duplicate_resolved_outcome(tmp_path, monkeypatch):
    m3 = _module()
    path = _due_journal(tmp_path)
    calls = []
    monkeypatch.setattr(m3, "JOURNAL", str(path))
    monkeypatch.setattr(m3, "fetch_pairs", lambda _mint: calls.append(1) or [])
    assert m3.main() == 0
    first = json.loads(path.read_text())
    assert m3.main() == 0
    second = json.loads(path.read_text())
    assert len(calls) == 2
    assert first["entries"]["mint"]["outcomes"] == second["entries"]["mint"]["outcomes"]
