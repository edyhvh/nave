# Multi-chain memecoin feasibility — 2026-08-31

This is a low-cost catalog/count discovery, not a historical panel. The one
bounded Dune probe used 0.121 credits. Counts are not comparable graduations:
BNB and TON had zero rows in the selected probe, Base had 7 Clanker
`TokenCreated` events and 1,501,010 Base DEX trade rows, while Solana’s prior
denominator had 53,956 Pump.fun launches on 2026-08-27.

| Network | Launch | Trades / wallets | Liquidity / lifecycle | Research status |
|---|---|---|---|---|
| Solana | Pump.fun decoded create events | Pump.fun user + `dex_solana.trades` trader | Pump.fun reserves and migration direct; PumpSwap depth missing | Burst ready on compact sample; Runner/identity partial |
| BNB / Four.meme | Generic `four_bnb` proxy tables; no verified Four.meme launch event | DEX data may exist, but launch-linked trade semantics unproven | Graduation/migration not identified | Partial catalog candidates; insufficient for a panel |
| Base / Clanker | Clanker v4 decoded `TokenCreated` with token, pool, paired-token fields | Base DEX trades available | Pool identity is promising; no Pump.fun-style graduation assumed | Partial; ready for a bounded future proof |
| TON | No launchpad/jetton source identified | Tiny `dex.trades` probe returned zero | TONCO pool init/mint/burn exists | Insufficient / not yet data-sufficient |

## Catalog results

BNB returned `four_bnb.bep20upgradeableproxy_evt_transfer` and related
generic proxy calls, plus a community Four.meme view candidate. These do not
yet expose a verified token-create, bonding-curve trade, or migration event.
No BNB panel should be built from generic ERC-20 transfers.

Base returned `clanker_v4_base.clanker_evt_tokencreated` (and v1/v3 variants).
The v4 schema includes `tokenAddress`, `pairedToken`, `poolId`, `msgSender`,
metadata, and event block/time fields. That is enough to justify a future
small lifecycle proof using `dex.trades`, but not to assume all Base launches
are Clanker or that a Clanker pool has Pump.fun-like graduation.

TON returned `tonco_ton.pool_init`, `pool_mint`, and `pool_burn`, plus a
community swap view candidate. No dominant launchpad/jetton creation source
was established, and the bounded DEX count was zero. TON is therefore not yet
data-sufficient for equivalent Burst/Runner/Early Participant research.

## BOOST and PumpSwap depth

The catalog surfaced community candidates for Pump buy-back data and pool
balances, but no bounded, verified source was established for BOOST-generated
flow or PumpSwap historical reserves. BOOST remains **UNKNOWN**. PumpSwap
depth is classified **HELIUS_LIKELY_NEEDED** for independent reserve/account
validation, while Helius is still not required for Dune-based discovery.

## Chain-neutral contract

The reusable conceptual schema is:

`Launch → TradeEvent → ParticipantEpisode → LiquidityState → LifecycleTransition → VenueMigration → TrajectoryMark → Outcome → ProtocolState`.

The existing PumpFun adapter is the only implemented source path. Future
`FourMemeAdapter`, `BaseLaunchAdapter`, and `TonLaunchAdapter` should normalize
into that schema; separate strategy code is deliberately out of scope.

The future Network Opportunity Index is documented only. It will compare
qualified Burst/Runner opportunity density, false runners, trader breadth,
liquidity, volume, and after-cost executable opportunities only after each
network’s lifecycle semantics are proven. No profitability ranking is made.
