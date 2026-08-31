"""Write compact audit/manifest artifacts without embedding raw Dune rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/dune")
    parser.add_argument("--ending-credits", type=float, required=True)
    args = parser.parse_args()
    root = Path(args.root)
    launches = pd.read_parquet(root / "launches.parquet")
    completeness = json.loads((root / "completeness.json").read_text())

    critical = ["mint", "creator", "launch_ts", "launch_slot", "launch_tx_id", "quote_mint", "token_total_supply", "token_program"]
    null_rates = {column: float(launches[column].isna().mean()) for column in critical}
    schema_audit = {
        "selected_tables": {
            "pumpdotfun_solana.pump_evt_createevent": {
                "purpose": "Pump.fun launch and protocol state",
                "partition": "evt_block_time",
                "fields": ["mint", "creator", "evt_block_time", "evt_block_slot", "evt_tx_id", "quote_mint", "token_total_supply", "virtual_sol_reserves", "virtual_token_reserves", "real_token_reserves", "is_mayhem_mode", "is_cashback_enabled", "token_program"],
            },
            "pumpdotfun_solana.pump_evt_tradeevent": {
                "purpose": "Pump.fun bonding-curve trade events",
                "partition": "evt_block_time",
                "fields": ["mint", "user", "is_buy", "sol_amount", "token_amount", "virtual_sol_reserves", "virtual_token_reserves", "real_sol_reserves", "real_token_reserves", "fee", "creator_fee", "buyback_fee", "evt_block_time", "evt_block_slot", "evt_tx_id", "evt_outer_instruction_index", "evt_inner_instruction_index"],
            },
            "pumpdotfun_solana.pump_evt_completeevent": {
                "purpose": "completion/graduation",
                "partition": "evt_block_time",
                "fields": ["mint", "bonding_curve", "evt_block_time", "evt_block_slot", "evt_tx_id", "user"],
            },
            "pumpdotfun_solana.pump_call_migrate": {
                "purpose": "migration and PumpSwap pool accounts",
                "partition": "call_block_time",
                "fields": ["account_mint", "account_pool", "account_pump_amm", "account_user", "account_pool_base_token_account", "account_pool_quote_token_account", "call_block_time", "call_block_slot", "call_tx_id", "call_outer_instruction_index", "call_inner_instruction_index", "call_log_messages"],
            },
            "dex_solana.trades": {
                "purpose": "PumpSwap post-migration trade continuation",
                "partition": "block_time",
                "filter": "project = 'pumpswap'",
                "fields": ["block_time", "block_slot", "tx_id", "tx_index", "outer_instruction_index", "inner_instruction_index", "trader_id", "token_bought_mint_address", "token_sold_mint_address", "token_bought_amount", "token_sold_amount", "amount_usd", "fee_tier", "fee_usd", "token_bought_vault", "token_sold_vault", "project_main_id"],
            },
            "prices.usd": {
                "purpose": "historical SOL/USD conversion for Pump.fun quote prices",
                "partition": "minute",
                "filter": "blockchain = 'solana' AND symbol = 'SOL'",
                "fields": ["minute", "price", "blockchain", "symbol"],
            },
        },
        "field_capabilities": {
            "launch_timestamp": "DIRECT",
            "launch_slot_transaction_order": "DIRECT",
            "creator_quote_asset_supply": "DIRECT",
            "pumpfun_side_amounts_wallet": "DIRECT",
            "pumpfun_reserves": "DIRECT",
            "historical_pumpfun_price_usd": "DERIVABLE",
            "pumpfun_fee_fields": "DIRECT",
            "completion": "DIRECT",
            "migration_timestamp_pool_identity": "DIRECT",
            "pumpswap_trades_wallet_amounts_usd": "DIRECT",
            "pumpswap_pool_identity": "DERIVABLE_WITH_CAVEAT",
            "pumpswap_historical_reserves_depth": "NOT_AVAILABLE_IN_SELECTED_TABLES",
            "wallet_inventory": "DERIVABLE_FROM_TRADE_EVENTS",
            "funding_and_sybil_clusters": "NOT_AVAILABLE",
            "historical_failed_transactions_priority_jito": "NOT_AVAILABLE_IN_SELECTED_TABLES",
        },
        "local_launch_null_rates": null_rates,
        "evidence": "bounded Dune probes and completed 2026-08-27 cohort denominator query",
    }
    (root / "schema_audit.json").write_text(json.dumps(schema_audit, indent=2, sort_keys=True) + "\n")

    protocol_state = {
        "Mayhem": {"status": "AVAILABLE_DIRECTLY", "field": "is_mayhem_mode"},
        "cashback": {"status": "AVAILABLE_DIRECTLY", "field": "is_cashback_enabled / cashback"},
        "Token-2022": {"status": "AVAILABLE_DIRECTLY", "field": "token_program"},
        "quote_asset": {"status": "AVAILABLE_DIRECTLY", "field": "quote_mint"},
        "fee_regime": {"status": "DIRECT_AND_PARTIAL", "field": "fee, fee_basis_points, creator_fee, buyback_fee"},
        "migration_state": {"status": "AVAILABLE_DIRECTLY", "field": "completeevent + migrate call"},
        "PumpSwap_pool": {"status": "AVAILABLE_DIRECTLY_FOR_MIGRATION_CALL", "field": "account_pool"},
        "Raydium_Meteora_secondary": {"status": "PARTIAL", "field": "dex_solana.trades can identify project trades"},
        "BOOST": {"status": "MISSING", "field": None, "reason": "No verified BOOST/generated-flow discriminator was present in the selected Dune tables."},
        "protocol_generated_flow": {"status": "MISSING", "field": None, "reason": "Cannot reliably separate mechanical buys from organic buys from the selected decoded/spellbook fields alone."},
    }
    (root / "protocol_state_audit.json").write_text(json.dumps(protocol_state, indent=2, sort_keys=True) + "\n")

    execution = {
        "bonding_curve": "DERIVABLE from Pump.fun reserves and amounts",
        "pumpswap_amm": "APPROXIMABLE from trade amounts; historical reserves/depth are not present in the selected trade table",
        "historical_fees": "DIRECT for Pump.fun; PARTIAL for PumpSwap where fee_tier/fee_usd is non-null",
        "creator_fees": "DIRECT on Pump.fun trade events; not proven complete for every post-migration route",
        "slippage_fixed_notional": "DERIVABLE only when historical reserves/depth are available; otherwise UNKNOWN",
        "failed_transactions": "NOT AVAILABLE in the selected event/trade tables",
        "failed_exits": "NOT AVAILABLE as a complete historical outcome state",
        "priority_fees": "NOT AVAILABLE in the selected tables",
        "same_block_ordering": "DIRECT via slot, tx index, outer/inner instruction indexes where populated",
        "Jito_bundle_effects": "NOT AVAILABLE / no bundle attribution",
        "decision": "Dune supports historical mark/flow discovery and partial execution approximation, not realistic execution validation by itself.",
    }
    (root / "execution_capability.json").write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n")

    query_files = sorted(Path("research/dune").rglob("*.sql"))
    query_manifest = []
    for path in query_files:
        query_manifest.append({
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "executed": path.name in {"01_selected_tables.sql", "01_cohort_candidates.sql", "02_cohort_completeness.sql", "03_launches.sql", "01_proof_token.sql", "01_token_windows_and_outcomes.sql"},
        })
    (root / "manifest.json").write_text(json.dumps({
        "manifest_version": "nave.dune.historical-panel.v1",
        "status": "DUNE_PANEL_PARTIALLY_VALIDATED",
        "period": {"launch_date_utc": "2026-08-27", "observation_end_utc": "2026-08-30", "lookahead_hours": 72},
        "source_tables": list(schema_audit["selected_tables"]),
        "launches_rows": int(len(launches)),
        "cohort_completeness": completeness,
        "proof_token": "7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump",
        "large_window_query": {"submitted": True, "completed": True, "result_fetch": "blocked_by_credit_limit", "execution_id": "01M1CP4YZMQAYD2JAWQZK49SHC"},
        "dune_usage": {"starting_credits": 0.0, "ending_credits_observed": args.ending_credits, "hard_stop": 500.0, "trial_included": 2500.0},
        "raw_data_gitignored": True,
        "queries": query_manifest,
    }, indent=2, sort_keys=True) + "\n")

    (root / "credit_usage.json").write_text(json.dumps({
        "starting_credits": 0.0,
        "trial_included": 2500.0,
        "hard_stop": 500.0,
        "ending_credits_observed": args.ending_credits,
        "credits_consumed_observed": args.ending_credits,
        "query_count": 22,
        "largest_query": "50_windows/01_token_windows_and_outcomes.sql",
        "largest_query_result": "QUERY_STATE_COMPLETED but result retrieval returned HTTP 402 after the configured credit limit was exceeded",
        "checkpoints": [
            {"stage": "initial", "credits_used": 0.0},
            {"stage": "schema_probes", "credits_used": 0.125},
            {"stage": "real_row_probes", "credits_used": 5.371},
            {"stage": "cohort_and_launch_exports", "credits_used": 83.559},
            {"stage": "large_window_query_status", "credits_used": args.ending_credits},
        ],
        "note": "The full-window query was an unintentional budget overrun; no additional Dune query is authorized in this iteration.",
    }, indent=2, sort_keys=True) + "\n")

    (root / "README.md").write_text("""# NAVE Dune historical panel\n\nLocal, gitignored artifacts for the bounded 2026-08-27 UTC Dune proof. The\nlaunch denominator and one-token lifecycle proof are materialized. The full\ncohort window query completed server-side but its result could not be fetched\nafter the account's configured credit limit was exceeded; no raw dataset is\nclaimed from that query.\n\nRaw CLI JSON is under `raw/` and SQL is tracked under `research/dune/`.\n""")


if __name__ == "__main__":
    main()
