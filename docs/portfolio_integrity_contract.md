# Portfolio integration safeguards

Private portfolio state and Quant WatchStore are independent inputs. No generic stock list is installed. Candidate and ISM commands read active numeric Quant watches when portfolio-local watches are absent. Non-price responsibilities remain in watch output for separate evaluation; a price check does not discharge A1/A2/A4.

`nave portfolio review --refresh-ledger --json` refreshes the private ONDO ledger before reading it, without orders or signing. A failed refresh stops review. Review without refresh remains available for fixtures/offline work, but missing/undated/stale state or price and missing company/technical evidence produce REVIEW_REQUIRED, not HOLD. The default freshness ceiling is three days; this is a daily-data review, not an intraday execution quote.

`nave portfolio watch --prices-file FILE` accepts `{"prices":{"ABC":100},"observed_at":{"ABC":"2026-09-06T00:00:00Z"}}`. Missing, stale, nonfinite and nonpositive prices are unavailable. ABOVE/BELOW/ZONE alert on entry and re-arm after an accepted price clears the condition. CROSS conditions require a prior observation. Accepted prices are saved only after the research result. The delivery layer must retain undelivered results: watch state is not proof of Discord delivery.

No live wallet identity, portfolio, watch conditions, jobs or schedules are installed by merging this PR.
