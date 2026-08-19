# Portfolio reporting, event tracking, and research gate

## Report destinations

Formal portfolio, price, congressional, ISM, and ONDO reports use the `STOCKS:` prefix and are delivered as posts to the parent `#quant` channel (`1514695031901126727`). They must not be delivered to the originating Discord thread. Ordinary conversation does not require the prefix.

## Daily and scheduled coverage

- Continuous price review: the cron may run every 30 minutes, including weekends, except during the seasonal Shabbat pause in Buenos Aires.
- Congressional disclosures: every 30 minutes outside the Shabbat pause; the report elevates presidential positions and large-capital disclosures from the STOCK Act feed.
- ISM: release-day Manufacturing and Services reports plus monthly context. Services remains paused until report-month freshness is verified.
- Monthly portfolio review: on or after the 26th, including weekends when due, except during the Shabbat pause.

### Shabbat operational pause

The default fixed rule is Friday 18:30 ART through Saturday 18:30 ART. The implementation calculates Buenos Aires sunset seasonally with a conservative boundary (18 minutes before Friday sunset through 42 minutes after Saturday sunset). If the calculation fails, it falls back to the fixed 18:30–18:30 rule. This is an operational pause only; no trade execution exists in the system.

Each report must separate:

1. Observation — what the source says.
2. Alert — why it deserves attention.
3. Recommendation — HOLD, WATCH, REVIEW, or EXIT proposal.
4. Proposed action — for example, research, partial profit-taking, or no action.
5. Human decision pending — Joni executes any trade manually.

## Event journal

Material disclosures and portfolio events are persisted in the local state file:

```text
~/.hermes/state/portfolio_manager/event_journal.json
```

Each row records:

- event date and disclosure/observation date;
- ticker, event type, source, and source URL;
- importance (`low`, `medium`, `high`);
- status (`new`, `watching`, `reviewed`, `closed`);
- next review date and review note.

The journal intentionally preserves old events. A historical event can remain relevant after a large subsequent move; it is not discarded merely because it is no longer new.

Useful commands:

```bash
nave stocks events-list --due-only
nave stocks events-list --ticker MRNA --json
nave stocks events-mark '<event-id>' --status watching --note 'Review thesis and performance'
```

The journal is read/write local state only and cannot place an order.

## Research gate before a new position

A candidate cannot become `ENTER` unless `Evidence.research_verified` is true. Before setting that field, the monthly human-gated workflow must:

1. fetch and read a current primary web source in the browser/web tool;
2. search X using the underlying ticker cashtag (for example `$MRNA`, not `MRNAon`);
3. record source URLs and timestamps;
4. distinguish verified facts, indicative prices, sentiment, and unavailable evidence;
5. confirm entry zone, invalidation, liquidity, and direct-defense exclusion.

If either web research or X evidence is missing/stale, the Portfolio Manager emits `WATCH` with `fresh_web_and_x_research_required` instead of `ENTER`. One congressional disclosure, ISM result, X trend, or tokenized listing is never sufficient by itself.
