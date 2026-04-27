# Memecoin scanner — planning doc

Branch: `experiment/memecoin-scanner` (off `feat/stocks`).
Status: **planning only — no code yet, do not implement until scope is signed off.**

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
- Data providers: Helius (RPC + token metadata), Birdeye (market data,
  liquidity), Jupiter (route/quote simulation for honeypot check),
  Pump.fun API (new launches feed).
- A `safety_check.py` implementing the 5 canonical SPL checks.
- A `scoring.py` implementing the transparent rubric.
- A `scanner.py` that pulls new launches, applies safety filter, scores
  survivors, returns a ranked list.
- MCP tools exposed to Hermes: `memecoin_scan`, `memecoin_safety_report`,
  `memecoin_score`.
- CLI: `nave memecoin scan`, `nave memecoin check <mint>`.
- Tests with recorded fixtures (don't hammer Helius/Birdeye in CI).

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

## Open questions for the user — answer before any code lands

1. **Data provider budget** — Helius has paid tiers; Birdeye is metered.
   What's the realistic monthly budget? Scan rate (every 60s? 5min?
   on-demand only?) drives cost.
2. **Wallet handling** — nave's existing vault is EVM-only (Hyperliquid).
   v1 is read-only so no key needed, but if v2 adds execution, do we
   add a Solana keypair to the vault, or use a separate burner flow?
3. **Universe** — Pump.fun-only, or all Solana SPL tokens above some
   liquidity floor? Pump.fun is the most rug-heavy but also the most
   "100% in minutes" venue.
4. **Holder-concentration threshold** — start at 30% top-10, or stricter?
5. **Position sizing rule** — for the eventual v2, what's the per-trade
   R cap and total memecoin allocation cap? (My suggestion: 0.25R per
   trade, 5% portfolio cap on the asset class as a whole.)

## Next step

Get sign-off on:
- The "safe = anti-rug, not low-vol" framing.
- The 5-check + scoring rubric scope.
- Read-only v1 (no execution).
- Answers to the 5 open questions above.

Then iterate the doc, then implement.
