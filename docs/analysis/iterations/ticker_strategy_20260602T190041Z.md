# Ticker strategy iteration — 20260602T190041Z

- Replay: `docs/analysis/raw/options_yearly_20260602T181813Z.json`
- Journal rows merged: 0
- Registry: `/Users/jhonny/nave/var/registry/sp500_top40`
- **Merge ready:** False

## Merge readiness

- Approved: 3 (need 8)
- Watch: 2 (need 20)
- Reject: 35

**Blockers:**
- need 8 approved tickers (have 3)
- need 20 watch tickers (have 2)

**Approved tickers:** BAC, JPM, WFC

## Walk-forward OOS (top 15)

| Ticker | OOS win | OOS n | Primary | Stable |
|--------|---------|-------|---------|--------|
| BAC | 100% | 2 | bear_call_credit_spread | False |
| WFC | 60% | 5 | bull_put_credit_spread | False |
| JPM | 33% | 3 | bull_put_credit_spread | True |
| ABBV | 33% | 3 | bull_put_credit_spread | True |
| PLTR | 20% | 5 | bear_call_credit_spread | False |
| META | 14% | 7 | bull_put_credit_spread | True |
| HD | 0% | 6 | bull_put_credit_spread | True |
| NOW | 0% | 6 | bear_call_credit_spread | False |
| MSFT | 0% | 5 | bear_call_credit_spread | False |
| MA | 0% | 5 | bull_put_credit_spread | True |
| ORCL | 0% | 5 | bear_call_credit_spread | True |
| CRM | 0% | 4 | bear_call_credit_spread | False |
| V | 0% | 3 | bear_call_credit_spread | False |
| COST | 0% | 3 | bull_put_credit_spread | True |
| NFLX | 0% | 3 | bear_call_credit_spread | False |

## Learned primary per ticker

- **AAPL** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS 0.0)
- **ABBV** [reject]: bull_put_credit_spread (edge 2.9, conf high, replay WR 0.2, OOS 0.3333333333333333)
- **ABT** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **AMZN** [reject]: bear_call_credit_spread (edge 0.0, conf low, replay WR 0.0, OOS 0.0)
- **AVGO** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS 0.0)
- **BAC** [approved]: bull_put_credit_spread (edge 53.3, conf medium, replay WR 1.0, OOS 1.0)
- **BRK-B** [reject]: bull_put_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS None)
- **COST** [reject]: bull_put_credit_spread (edge 14.7, conf high, replay WR 0.4, OOS 0.0)
- **CRM** [reject]: bull_put_credit_spread (edge 0.0, conf medium, replay WR 0.5, OOS 0.0)
- **CSCO** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS None)
- **CVX** [reject]: bear_call_credit_spread (edge 17.1, conf low, replay WR 1.0, OOS None)
- **GE** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **GOOG** [reject]: bear_call_credit_spread (edge 0.0, conf low, replay WR 0.0, OOS None)
- **GOOGL** [reject]: bull_put_credit_spread (edge 15.3, conf low, replay WR 1.0, OOS None)
- **HD** [reject]: bull_put_credit_spread (edge 0.0, conf high, replay WR 0.0, OOS 0.0)
- **IBM** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS None)
- **ISRG** [reject]: bull_put_credit_spread (edge 0.0, conf low, replay WR 0.0, OOS None)
- **JNJ** [reject]: bull_put_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS 0.0)
- **JPM** [approved]: bull_put_credit_spread (edge 56.9, conf high, replay WR 0.6, OOS 0.3333333333333333)
- **KO** [reject]: bear_call_credit_spread (edge 0.0, conf low, replay WR 0.0, OOS None)
- **LIN** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **LLY** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **MA** [reject]: bull_put_credit_spread (edge 0.0, conf high, replay WR 0.0, OOS 0.0)
- **MCD** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **META** [reject]: bull_put_credit_spread (edge 0.1, conf low, replay WR 0.1111111111111111, OOS 0.14285714285714285)
- **MRK** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS None)
- **MSFT** [reject]: bull_put_credit_spread (edge 3.1, conf medium, replay WR 0.3333333333333333, OOS 0.0)
- **NFLX** [reject]: bear_call_credit_spread (edge 17.5, conf low, replay WR 0.0, OOS 0.0)
- **NOW** [reject]: bull_put_credit_spread (edge 0.0, conf high, replay WR 0.0, OOS 0.0)
- **NVDA** [reject]: bear_call_credit_spread (edge 0.0, conf medium, replay WR 0.0, OOS None)
- **ORCL** [watch]: bear_call_credit_spread (edge 23.7, conf medium, replay WR 0.5, OOS 0.0)
- **PG** [reject]: bull_put_credit_spread (edge 0.0, conf high, replay WR 0.0, OOS 0.0)
- **PLTR** [reject]: bull_put_credit_spread (edge 14.7, conf medium, replay WR 0.6666666666666666, OOS 0.2)
- **PM** [reject]: None (edge None, conf low, replay WR None, OOS None)
- **TSLA** [reject]: bull_put_credit_spread (edge 0.0, conf high, replay WR 0.5, OOS 0.0)
- **UNH** [reject]: bear_call_credit_spread (edge 0.0, conf high, replay WR 0.0, OOS 0.0)
- **V** [reject]: bull_put_credit_spread (edge 0.0, conf low, replay WR 0.16666666666666666, OOS 0.0)
- **WFC** [approved]: bull_put_credit_spread (edge 55.3, conf high, replay WR 0.75, OOS 0.6)
- **WMT** [reject]: bull_put_credit_spread (edge 6.2, conf medium, replay WR 0.25, OOS 0.0)
- **XOM** [watch]: bull_put_credit_spread (edge 7.8, conf medium, replay WR 0.5, OOS None)

## Hidden gems today

_No gems passed filters._