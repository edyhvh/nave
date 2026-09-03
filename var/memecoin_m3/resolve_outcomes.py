#!/usr/bin/env python3
"""M3 forward-observation: resolve 24h / 48h / 7d outcomes for journal signals.

For every signal-journal entry whose horizon has elapsed but has not yet
been resolved, fetch the live DexScreener state and record the return and
a RUG/DEAD/ALIVE classification.

Horizon is measured from each signal's scan timestamp. Because this runs on
a recurring schedule, the fetch happens at (or just after) the horizon —
the actual elapsed time is stored alongside so timing slack is visible.

Outcome conventions (same as M2):
  - Return  = (price_at_horizon - scan_price) / scan_price * 100
              on the most-liquid solana pair.
  - ALIVE   = a liquid solana pair exists with retained liquidity.
  - RUG     = had > $20k liquidity at scan, now < $3k (pull/collapse to dust).
  - DEAD    = no liquid solana pair now, or below floor.

Read-only. Writes only to the M3 signal journal.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
from trading.memecoin.m3_resolution import (  # noqa: E402
    DEAD,
    DATA_UNAVAILABLE,
    INVALID_RESPONSE,
    LEGACY_UNKNOWN,
    PROVIDER_UNAVAILABLE,
    RESOLVED,
    TEMPORARY_FAILURE,
    UNEXITABLE,
    UNRESOLVED,
)
from trading.memecoin.m3_resolution import best_solana_pair as _governed_best_solana_pair  # noqa: E402

JOURNAL = os.path.join(REPO, "var", "memecoin_m3", "signal_journal.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

HORIZONS = {
    "24h": 24 * 3600,
    "48h": 48 * 3600,
    "7d": 7 * 24 * 3600,
}
RUG_LIQ_AT_SCAN = 20_000.0
RUG_LIQ_NOW = 3_000.0



def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_pairs(mint: str) -> list | dict | None:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
    except Exception as exc:
        return {"error_kind": TEMPORARY_FAILURE, "error": str(exc)}
    if not isinstance(data, dict):
        return {"error_kind": INVALID_RESPONSE, "error": "response root is not an object"}
    pairs = data.get("pairs")
    if pairs is None:
        return {"error_kind": DATA_UNAVAILABLE, "error": "response contains no pairs"}
    if not isinstance(pairs, list):
        return {"error_kind": INVALID_RESPONSE, "error": "pairs is not a list"}
    return pairs


def best_solana_pair(pairs) -> tuple | None:
    return _governed_best_solana_pair(pairs)


def pair_for_resolution(pairs, expected_pair_address=None):
    valid = [p for p in (pairs or []) if isinstance(p, dict)]
    from trading.memecoin.m3_resolution import pair_for_resolution as select
    return select(valid, expected_pair_address)


def classify(scan_liq, now_price, now_liq, has_pair) -> str:
    if not has_pair or now_liq is None or now_liq < RUG_LIQ_NOW:
        if scan_liq and scan_liq > RUG_LIQ_AT_SCAN:
            return "RUG"
        return "DEAD"
    return "ALIVE"


def _terminal_outcome(oc) -> bool:
    return isinstance(oc, dict) and oc.get("resolution_status") in (
        RESOLVED, DEAD, UNEXITABLE, LEGACY_UNKNOWN, INVALID_RESPONSE,
    )


def main() -> int:
    if not os.path.exists(JOURNAL):
        print("no journal yet; nothing to resolve", file=sys.stderr)
        return 0
    with open(JOURNAL, "r", encoding="utf-8") as fh:
        journal = json.load(fh)

    now = _utcnow()
    entries = journal["entries"]
    resolved = 0
    errors = 0
    attempted = 0

    for mint, entry in entries.items():
        scanned_at = _parse(entry.get("logged_at") or entry.get("scanned_at") or "")
        scan_market = entry.get("market") or {}
        scan_price = scan_market.get("price_usd")
        scan_liq = scan_market.get("liquidity_usd")
        expected_pair = (scan_market.get("pair_address") or
                         scan_market.get("pairAddress"))
        for hname, hsecs in HORIZONS.items():
            oc = entry["outcomes"].get(hname)
            if _terminal_outcome(oc):
                continue  # already resolved
            horizon_dt = scanned_at + timedelta(seconds=hsecs)
            if now < horizon_dt:
                continue  # not due yet
            attempted += 1
            try:
                pairs = fetch_pairs(mint)
            except Exception as exc:
                errors += 1
                continue
            if isinstance(pairs, dict) and pairs.get("error_kind"):
                kind = str(pairs.get("error_kind"))
                if kind == TEMPORARY_FAILURE:
                    errors += 1
                    entry["outcomes"][hname] = {
                        "resolved_at": _iso(now),
                        "elapsed_h": round((now - scanned_at).total_seconds() / 3600.0, 1),
                        "resolution_status": PROVIDER_UNAVAILABLE,
                        "resolution_reason": str(pairs.get("error") or "provider unavailable"),
                        "price_usd": None, "liquidity_usd": None,
                        "ret_pct": None, "cls": None, "pairs": 0,
                    }
                    print(f"  {mint[:10]} {hname}: {kind} {pairs.get('error', '')}", file=sys.stderr)
                    continue
                entry["outcomes"][hname] = {
                    "resolved_at": _iso(now),
                    "elapsed_h": round((now - scanned_at).total_seconds() / 3600.0, 1),
                    "resolution_status": kind,
                    "resolution_reason": str(pairs.get("error") or "provider returned no usable data"),
                    "price_usd": None,
                    "liquidity_usd": None,
                    "ret_pct": None,
                    "cls": None,
                    "pairs": 0,
                }
                resolved += 1
                continue
            if not isinstance(pairs, list):
                errors += 1
                continue
            selected = pair_for_resolution(pairs, expected_pair)
            has_pair = selected is not None
            has_solana_pair = any(
                isinstance(pair, dict) and pair.get("chainId") == "solana"
                for pair in pairs
            )
            if selected:
                p = selected
                try:
                    pliq = float((p.get("liquidity") or {}).get("usd"))
                except (TypeError, ValueError):
                    pliq = None
                try:
                    now_price = float(p.get("priceUsd"))
                    now_liq = pliq
                except (TypeError, ValueError):
                    now_price = None
                    now_liq = None
            else:
                now_price = None
                now_liq = None
            if not has_pair:
                if expected_pair:
                    resolution_status = UNEXITABLE
                    resolution_reason = "entry pair is no longer present in provider response"
                elif has_solana_pair:
                    resolution_status = LEGACY_UNKNOWN
                    resolution_reason = "legacy entry has no recorded pair_address; current pair not used"
                else:
                    resolution_status = DEAD
                    resolution_reason = "no valid Solana pair in provider response"
                cls = resolution_status
                ret = -100.0 if resolution_status in (DEAD, UNEXITABLE) else None
            elif now_price is None or now_liq is None:
                resolution_status = INVALID_RESPONSE
                resolution_reason = "best Solana pair lacks numeric price/liquidity"
                cls = None
                ret = None
            else:
                resolution_status = RESOLVED
                resolution_reason = None
                cls = classify(scan_liq, now_price, now_liq, has_pair)
                if scan_price:
                    ret = (now_price - scan_price) / scan_price * 100.0
                else:
                    ret = None
            if scan_price and resolution_status == RESOLVED:
                ret = (now_price - scan_price) / scan_price * 100.0 if now_price else -100.0
            elapsed_h = (now - scanned_at).total_seconds() / 3600.0
            entry["outcomes"][hname] = {
                "resolved_at": _iso(now),
                "elapsed_h": round(elapsed_h, 1),
                "price_usd": now_price,
                "liquidity_usd": now_liq,
                "ret_pct": round(ret, 2) if ret is not None else None,
                "cls": cls,
                "resolution_status": resolution_status,
                "resolution_reason": resolution_reason,
                "pairs": len(pairs) if isinstance(pairs, list) else 0,
            }
            resolved += 1
            print(f"  {mint[:10]} {hname}: cls={cls} ret={ret if ret is None else round(ret,1)}% "
                  f"liq={now_liq} elapsed={elapsed_h:.1f}h")
            time.sleep(0.35)

    journal["entries"] = entries
    journal["last_resolve_at"] = _iso(now)
    with open(JOURNAL, "w", encoding="utf-8") as fh:
        json.dump(journal, fh, indent=2, ensure_ascii=False)

    print(f"resolve pass done: newly_resolved={resolved} fetch_errors={errors} "
          f"journal_total={len(entries)}")
    # A provider outage affecting every due observation is not a successful
    # cycle.  Leave temporary observations unresolved for the next retry, but
    # make the scheduler record the systemic run failure honestly.
    if attempted and errors == attempted and resolved == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
