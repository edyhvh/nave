"""M3 forward-observation data-integrity regressions."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone


def _module():
    path = "/home/david/nave/var/memecoin_m3/resolve_outcomes.py"
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
    assert saved["entries"]["mint"]["outcomes"] == {}
