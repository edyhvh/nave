from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from cli.main import app
from options.eth_weekly import EthWeeklyOptionsProfile, build_eth_weekly_decision


runner = CliRunner()


def _scan_payload(
    *,
    max_loss: float = 18.0,
    confidence: float = 94.0,
    side: str = "long",
    tradeable: bool = True,
    executable_key: str = "best_overall_executable_setup",
) -> dict:
    return {
        "summary": {"coins_requested": 1, "momentum_allowed": 1, "options_ready": 1},
        "opportunities": {
            "ETH": {
                "status": "ready",
                "momentum": {
                    "side": side,
                    "tradeable": tradeable,
                    "confidence_score": confidence,
                    "entry_zone": [3400.0, 3450.0],
                    "invalidation": 3300.0,
                    "rr_estimated": 2.1,
                    "setup_status": "confirmed",
                },
                "options": {
                    "analysis_overlay": {
                        "final_recommendations": {
                            executable_key: {
                                "strategy_name": "bull_call_debit_spread",
                                "metrics": {
                                    "composite_score": 76.0,
                                    "pop": 58.0,
                                    "expected_value": 4.5,
                                    "probability_of_touch": 62.0,
                                    "max_loss": max_loss,
                                    "risk_reward": 1.8,
                                },
                            }
                        }
                    },
                    "recommendations": [],
                },
            }
        },
    }


def test_eth_weekly_decision_enters_for_small_account_valid_structure() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=90),
    )

    assert decision["decision"] == "ENTER"
    assert decision["option"]["strategy_name"] == "bull_call_debit_spread"
    assert decision["option"]["metrics"]["max_loss"] == 18.0


def test_eth_weekly_decision_watches_when_option_risk_is_too_large() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(max_loss=45.0),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=90),
    )

    assert decision["decision"] == "WATCH"
    assert "no_small_account_option_structure" in decision["blockers"]
    assert decision["watch"][0]["blockers"] == ["max_loss_above_20_usd"]


def test_eth_weekly_decision_keeps_a_plus_oversize_as_manual_review() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(max_loss=25.0, confidence=96.0),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, max_a_plus_loss_usd=30.0),
    )

    assert decision["decision"] == "WATCH"
    assert decision["momentum"]["a_plus"] is True
    assert decision["watch"][0]["blockers"] == ["requires_a_plus_manual_review"]


def test_eth_weekly_decision_rejects_modeled_only_setup() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(executable_key="best_modeled_setup"),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=90),
    )

    assert decision["decision"] == "WATCH"
    assert "no_side_aligned_executable_structure" in decision["blockers"]


def test_eth_weekly_decision_reports_side_alignment_failure() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(side="short"),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=90),
    )

    assert decision["decision"] == "WATCH"
    assert "no_side_aligned_executable_structure" in decision["blockers"]


def test_eth_weekly_decision_compares_fractional_confidence_without_truncation() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(confidence=89.9),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=89.9),
    )

    assert decision["decision"] == "ENTER"
    assert decision["momentum"]["confidence_score"] == 89.9


def test_eth_weekly_decision_watches_when_momentum_is_not_tradeable() -> None:
    decision = build_eth_weekly_decision(
        _scan_payload(tradeable=False),
        profile=EthWeeklyOptionsProfile(max_loss_usd=20.0, min_confidence=90),
    )

    assert decision["decision"] == "WATCH"
    assert "momentum_not_tradeable" in decision["blockers"]


def test_eth_weekly_cli_outputs_json(monkeypatch, tmp_path) -> None:
    from cli.commands import options as options_cmd

    class _DummyAnalyzer:
        def __init__(self, *args, **kwargs) -> None:
            self.config = SimpleNamespace(reports_dir=tmp_path)

        def scan_crypto_opportunities(self, **kwargs):
            assert kwargs["coins"] == ["ETH"]
            assert kwargs["days_to_exp"] == 10
            assert kwargs["score_threshold"] == 90
            return _scan_payload()

    monkeypatch.setattr(options_cmd, "OptionsAnalyzer", _DummyAnalyzer)

    result = runner.invoke(
        app,
        [
            "options",
            "eth-weekly",
            "--json",
            "--json-path",
            str(tmp_path / "eth_weekly.json"),
        ],
    )

    assert result.exit_code == 0
    assert '"decision": "ENTER"' in result.stdout
    assert '"strategy_name": "bull_call_debit_spread"' in result.stdout
    assert (tmp_path / "eth_weekly.json").exists()


def test_hyperliquid_client_without_wallet_does_not_create_vault(monkeypatch) -> None:
    import trading.crypto.client as client_module

    class _ExplodingVault:
        def __init__(self) -> None:
            raise AssertionError("WalletVault should not be created for read-only client")

    monkeypatch.setattr(client_module, "WalletVault", _ExplodingVault)

    client = client_module.HyperliquidClient(wallet_name=None, testnet=False)

    assert client.address == ""
    assert client._vault is None
