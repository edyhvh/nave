# Memecoin scanner — planning doc

Branch: `experiment/memecoin-scanner` (off `feat/stocks`).
Status: **v1 implementation in progress — decisions locked below.**

## v1 decisions (locked 2026-04-27)

| Question                  | Decision                                                                  |
|---------------------------|---------------------------------------------------------------------------|
| Data providers            | Helius (free/starter) + Pump.fun + DexScreener + Jupiter v6. **No Birdeye.** |
| Wallet handling           | Separate Solana burner-wallet flow (do NOT extend the existing EVM vault). |
| v1 execution              | Read-only. Architecture must keep room for v2 burner-wallet swaps.         |
| Universe                  | Pump.fun tokens with on-chain liquidity ≥ **$25,000**.                     |
| Holder concentration      | Top-10 ≤ **25 %**. Flag (not auto-fail) if top-1 > **15-18 %**.            |
| v2 sizing                 | **0.25 R per trade**, **5 %** portfolio cap on the memecoin asset class.   |
| Safety report contract    | Structured JSON: `rug_score`, `honeypot_flags`, `lp_status`, `holder_concentration`, `dev_wallets`, … |

## Goal

Build a third asset class on top of the existing crypto-perps and stocks
stacks: a Solana memecoin scanner that surfaces **safety-filtered**
candidates via the same MCP tool surface nave already exposes to Hermes.

The realistic framing: nave finds and *filters* candidates, sizes small,
and surfaces them. It is **not** a launch-block sniper bot — Python can't
win that arms race against Rust/Go bots already on-chain.

## What "safe" means here (and what it doesn't)

"Safe" can **only** mean *avoiding predictable losses* — rug pulls,
honeypots, and obvious scams (~30-50% of Solana memecoin launches).
It cannot mean low-volatility: a token that 2x's in minutes will also
-90% in minutes; that's the asset class. Position sizing and a hard
per-trade R cap are the only real defense against the volatility itself.

## Synthesis from the three reference repos

| Repo                        | License  | Lang | What we take                                                                |
|-----------------------------|----------|------|------------------------------------------------------------------------------|
| `build23w/fdv.lol`          | MIT      | JS   | Transparent scoring rubric (FDV, vol, liquidity, momentum) + GOOD/WATCH/SHILL labels |
| `tony-42069/solana-mcp`     | none     | JS   | MCP tool shape: `scan_new`, `hype_score`, `whale_track`, `rug_check`         |
| `tony-42069/trader-tony-v4` | MIT      | Rust | Canonical SPL safety checklist (the strongest piece)                         |

We **port concepts**, not code. `solana-mcp` has no license — only use
its tool *shape* as inspiration; do not copy code or strings.

### Canonical SPL safety checks (from trader-tony-v4)

These five are the bar. A token must clear all five to enter the
"WATCH/GOOD" buckets — failing any sends it to "SHILL/skip":

1. **Mint authority renounced** — issuer can no longer print supply.
2. **Freeze authority revoked** — issuer can't freeze user wallets.
3. **LP locked or burned** — liquidity can't be pulled by the deployer.
4. **Honeypot simulation passes** — a small simulated buy + sell round-trips.
5. **Holder concentration** — top-10 holders below a threshold (e.g. <30%).

### fdv.lol-style scoring rubric (transparent)

After a token clears the safety gate, score it on a 0-100 scale:

- **FDV** band — penalize too-low (likely rug-bait) and too-high (no upside).
- **24h volume / FDV** — turnover ratio.
- **Liquidity depth** — slippage simulation at our intended position size.
- **Momentum** — short-window returns + holder-count growth.
- **Age** — newest pumps are the riskiest; bias slightly older.

Score → `GOOD` (>=70) / `WATCH` (40-69) / `SHILL` (<40). Every input
visible in the report so a human can override.

## Realistic scope (what to build, what to skip)

**In scope (v1):**
- Read-only scanner module under `trading/memecoin/`.
- Data providers: **Helius** (RPC + DAS API for token metadata + holders),
  **Pump.fun** (new launches feed + bonding curve), **DexScreener**
  (price/volume/liquidity for graduated tokens — free, no key),
  **Jupiter v6** (route/quote simulation for honeypot check).
- A `safety_check.py` implementing the 5 canonical SPL checks.
- A `scoring.py` implementing the transparent rubric.
- A `scanner.py` that pulls new launches, applies the $25k liquidity
  gate, runs safety filter, scores survivors, returns a ranked list.
- MCP tools exposed to Hermes: `memecoin_scan`, `memecoin_safety_report`,
  `memecoin_score`.
- CLI: `nave memecoin scan`, `nave memecoin check <mint>`.
- Tests with recorded fixtures (don't hammer Helius in CI).

**Out of scope (v1) — explicit non-goals:**
- No order execution. No swap. No Jupiter trades. The output is signal
  only. Trading is a separate v2 once the scanner is trusted.
- No sniper / mempool / pre-LP-add logic. Not winning that race.
- No copy-trading of other wallets.
- No social-signal layer (Twitter/Reddit/TG). Easy to abuse, gives
  false confidence; revisit once the on-chain layer is solid.
- No "Agent Gary"-style AI buy/sell decision-maker. Hermes is the agent;
  nave provides tools.

## Integration shape

```
trading/
├── crypto/      # existing: BTC/ETH theory_v2 + Hyperliquid
├── stocks/      # existing: ISM + FMP
└── memecoin/    # new
    ├── data_provider.py   # Helius + Birdeye + Jupiter clients with caching
    ├── safety_check.py    # 5 canonical SPL checks
    ├── scoring.py         # transparent rubric → GOOD/WATCH/SHILL
    ├── scanner.py         # pipeline: discover → safety → score → rank
    └── mcp_tools.py       # memecoin_scan / safety_report / score
```

Same patterns as `trading/stocks/`: cache-backed data layer, deterministic
scoring, Hermes/MCP surface, `dry_run=True` defaults if/when execution
ever lands.

## Safety report JSON contract

`memecoin_safety_report(mint)` returns:

```json
{
  "mint": "<base58>",
  "verdict": "PASS | WATCH | FAIL",
  "rug_score": 0,
  "checks": {
    "mint_authority_renounced": true,
    "freeze_authority_revoked": true,
    "lp_status": {"locked": true, "burned": false, "lp_provider": "raydium", "details": "..."},
    "honeypot": {"buy_simulates": true, "sell_simulates": true, "flags": []},
    "holder_concentration": {"top_1_pct": 0.0, "top_5_pct": 0.0, "top_10_pct": 0.0, "flagged_top1": false}
  },
  "dev_wallets": [{"address": "...", "balance_pct": 0.0, "notes": "..."}],
  "honeypot_flags": [],
  "raw": {"...": "provider responses for debugging"},
  "fetched_at": "<iso8601>"
}
```

`verdict` is the rollup: `FAIL` if any of the 5 hard checks fail, `WATCH`
if all pass but `flagged_top1` is true, `PASS` otherwise.

## Next step

Doc is locked. Implementation starts in this branch:
1. `trading/memecoin/data_provider.py` — Helius + Pump.fun + DexScreener + Jupiter clients.
2. `trading/memecoin/safety_check.py` — 5 canonical checks → `SafetyReport`.
3. `trading/memecoin/scoring.py` — transparent rubric.
4. `trading/memecoin/scanner.py` — discover → gate → safety → score.
5. `trading/memecoin/mcp_tools.py` + register in `trading/crypto/mcp_server.py`.
6. `cli/commands/memecoin.py` — `nave memecoin scan` + `nave memecoin check`.
7. `tests/test_memecoin/` with recorded fixtures.
