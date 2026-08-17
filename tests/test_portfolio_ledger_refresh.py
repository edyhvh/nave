import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "portfolio_ledger_refresh.py"
_spec = importlib.util.spec_from_file_location("portfolio_ledger_refresh", SCRIPT)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def test_existing_fills_are_normalized_and_deduplicated_by_signature():
    fills = [
        {"symbol": "AMZNON", "side": "BUY", "signature": "sig-1", "usdc_delta": "-100"},
        {
            "symbol": "AMZNON",
            "side": "BUY",
            "mint": "14Tqdo8V1FhzKsE3W2pFsZCzYPQxxupXRcqw9jv6ondo",
            "signature": "sig-1",
            "usdc_delta": "-100",
        },
    ]
    normalized = _module._normalize_existing_fills(fills)
    assert len(normalized) == 1
    assert normalized[0]["mint"].endswith("ondo")
    assert normalized[0]["underlying"] == "AMZN"
