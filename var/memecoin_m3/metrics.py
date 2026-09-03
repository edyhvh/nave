#!/usr/bin/env python3
"""M3 forward-observation: precision/recall + momentum/age hypothesis + status.

Reads the M3 signal journal and writes:
  - metrics_report.md   (per-horizon precision/recall + momentum/age test)
  - metrics.json        (machine-readable numbers for the reassessment gate)

Gate: when >= 200 candidates have a 7d outcome, the report flags that the
M3 verdict (EDGE CANDIDATE vs NO EDGE) is due.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

REPO = "/home/david/nave"
JOURNAL = os.path.join(REPO, "var", "memecoin_m3", "signal_journal.json")
REPORT = os.path.join(REPO, "var", "memecoin_m3", "metrics_report.md")
METRICS_JSON = os.path.join(REPO, "var", "memecoin_m3", "metrics.json")

HORIZONS = ["24h", "48h", "7d"]
TERMINAL_STATUSES = ("RESOLVED", "DEAD", "UNEXITABLE")
UNAVAILABLE_STATUSES = ("DATA_UNAVAILABLE", "PROVIDER_UNAVAILABLE",
                        "TEMPORARY_FAILURE", "INVALID_RESPONSE", "LEGACY_UNKNOWN")
THRESHOLDS = [0, 5, 10, 20]
GATE_MIN_CANDIDATES_7D = 200
RISK_MOMENTUM_1H_PCT = 25.0
RISK_AGE_MAX_MIN = 180


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ret_of(oc) -> float | None:
    if not isinstance(oc, dict):
        return None
    r = oc.get("ret_pct")
    return float(r) if r is not None else None


def main() -> int:
    if not os.path.exists(JOURNAL):
        print("no journal yet")
        return 0
    with open(JOURNAL, "r", encoding="utf-8") as fh:
        journal = json.load(fh)
    entries = list(journal["entries"].values())

    passed = [e for e in entries if e.get("passed")]
    rejected = [e for e in entries if not e.get("passed")]
    metrics = {"generated_at": _utcnow(), "journal_total": len(entries),
               "passed": len(passed), "rejected": len(rejected),
               "horizons": {}}

    lines = []
    lines.append("# M3 Memecoin Forward Observation — Metrics Report")
    lines.append("")
    lines.append(f"**Generated**: {_utcnow()}")
    lines.append(f"**Journal**: {len(entries)} signals "
                 f"({len(passed)} passed GOOD/WATCH, {len(rejected)} rejected)")
    lines.append("")

    for h in HORIZONS:
        hres = {"n_passed": 0, "n_all": 0, "n_data_unavailable": 0,
                "n_unresolved": 0, "precision": {}, "rug_dead_pct": None,
                "risk_filter": {}, "n_7d_gate": 0}
        # DATA_UNAVAILABLE / INVALID_RESPONSE records are retained for audit,
        # but are not scientific outcomes and must not enter precision, recall,
        # or the reassessment gate.
        passed_resolved = [
            e for e in passed
            if isinstance(e["outcomes"].get(h), dict)
            and e["outcomes"][h].get("resolution_status", "RESOLVED")
            in TERMINAL_STATUSES
        ]
        all_resolved = [
            e for e in entries
            if isinstance(e["outcomes"].get(h), dict)
            and e["outcomes"][h].get("resolution_status", "RESOLVED")
            in TERMINAL_STATUSES
        ]
        hres["n_data_unavailable"] = sum(
            1 for e in entries
            if isinstance(e["outcomes"].get(h), dict)
            and e["outcomes"][h].get("resolution_status")
            in UNAVAILABLE_STATUSES
        )
        hres["n_unresolved"] = len(entries) - len(all_resolved) - hres["n_data_unavailable"]
        hres["n_passed"] = len(passed_resolved)
        hres["n_all"] = len(all_resolved)

        # Precision among passed candidates.
        for thr in THRESHOLDS:
            n = sum(1 for e in passed_resolved if (ret_of(e["outcomes"].get(h)) or -9999) > thr)
            prec = n / len(passed_resolved) if passed_resolved else None
            hres["precision"][f"ret>{thr}%"] = round(prec, 4) if prec is not None else None

        # Recall: of all tokens that pumped above threshold, what fraction were passed?
        for thr in THRESHOLDS:
            pumped_all = [e for e in all_resolved if (ret_of(e["outcomes"].get(h)) or -9999) > thr]
            pumped_passed = [e for e in pumped_all if e.get("passed")]
            rec = len(pumped_passed) / len(pumped_all) if pumped_all else None
            hres.setdefault("recall", {})[f"ret>{thr}%"] = round(rec, 4) if rec is not None else None

        # Loss / death rate among passed.
        loss = [e for e in passed_resolved
                if e["outcomes"][h].get("cls") in ("RUG", "DEAD", "UNEXITABLE")]
        hres["rug_dead_pct"] = round(len(loss) / len(passed_resolved) * 100, 1) if passed_resolved else None

        # Momentum/age hypothesis: does the risk filter predict more rugs?
        risk_yes = [e for e in passed_resolved if e.get("risk_flags", {}).get("matches_risk_filter")]
        risk_no = [e for e in passed_resolved if not e.get("risk_flags", {}).get("matches_risk_filter")]
        for grp_name, grp in (("filter_matched", risk_yes), ("filter_not_matched", risk_no)):
            gl = [e for e in grp
                  if e["outcomes"][h].get("cls") in ("RUG", "DEAD", "UNEXITABLE")]
            hres["risk_filter"][grp_name] = {
                "n": len(grp),
                "rug_dead": len(gl),
                "rug_dead_pct": round(len(gl) / len(grp) * 100, 1) if grp else None,
            }

        if h == "7d":
            hres["n_7d_gate"] = len(passed_resolved)

        metrics["horizons"][h] = hres

        lines.append(f"## Horizon {h}")
        lines.append("")
        lines.append(f"Resolved: {len(passed_resolved)} passed / {len(all_resolved)} all; "
                     f"provider/data unavailable: {hres['n_data_unavailable']}; "
                     f"unresolved: {hres['n_unresolved']}")
        lines.append("")
        lines.append("| Threshold | Precision (passed) | Recall (passed/pumped) |")
        lines.append("|---|---|---|")
        for thr in THRESHOLDS:
            k = f"ret>{thr}%"
            p = hres["precision"].get(k)
            r = hres["recall"].get(k)
            lines.append(f"| {k} | {p if p is not None else '-'} | {r if r is not None else '-'} |")
        lines.append("")
        lines.append(f"Loss (RUG+DEAD) among passed: "
                     f"{hres['rug_dead_pct'] if hres['rug_dead_pct'] is not None else '-'}%")
        rf = hres["risk_filter"]
        lines.append("Momentum/age risk filter (1h>25% AND age<3h):")
        for k in ("filter_matched", "filter_not_matched"):
            v = rf[k]
            lines.append(f"  - {k}: n={v['n']}, rug/dead={v['rug_dead']} "
                         f"({v['rug_dead_pct'] if v['rug_dead_pct'] is not None else '-'}%)")
        lines.append("")

    # Reassessment gate.
    n_7d = metrics["horizons"]["7d"]["n_passed"]
    gate_met = n_7d >= GATE_MIN_CANDIDATES_7D
    metrics["gate_7d"] = {"n_passed_with_7d": n_7d, "gate_min": GATE_MIN_CANDIDATES_7D, "met": gate_met}
    lines.append(f"## Reassessment gate")
    lines.append("")
    lines.append(f"Passed candidates with a 7d outcome: **{n_7d}** / "
                 f"required {GATE_MIN_CANDIDATES_7D}")
    lines.append("")
    if gate_met:
        lines.append("**GATE MET** — the M3 verdict (EDGE CANDIDATE vs NO EDGE) is now due. "
                     "Compute final precision/recall and the momentum/age test, then "
                     "issue the verdict.")
    else:
        lines.append("Gate NOT met yet — keep scanning. Verdict deferred until "
                     ">= 200 passed candidates have a 7d outcome.")
    lines.append("")

    report_text = "\n".join(lines) + "\n"
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(report_text)
    with open(METRICS_JSON, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    if gate_met:
        write_verdict_draft(metrics)

    print(report_text)
    return 0


def write_verdict_draft(metrics: dict) -> None:
    """Write a data-driven M3 verdict draft once the reassessment gate is met.

    The final verdict (EDGE CANDIDATE vs NO EDGE) is a human-gated decision
    (Joni ratifies). This surfaces the numbers and a preliminary read only.
    """
    h7 = metrics["horizons"]["7d"]
    prec0 = h7["precision"].get("ret>0%")
    prec10 = h7["precision"].get("ret>10%")
    loss = h7.get("rug_dead_pct")
    rf_m = h7["risk_filter"].get("filter_matched", {}).get("rug_dead_pct")
    rf_n = h7["risk_filter"].get("filter_not_matched", {}).get("rug_dead_pct")
    n = h7.get("n_passed")

    lines = []
    lines.append("# M3 VERDICT DRAFT (for Joni ratification)")
    lines.append("")
    lines.append(f"**Generated**: {_utcnow()}")
    lines.append(f"**Sample**: {n} passed candidates with a 7d outcome "
                 f"(gate = {GATE_MIN_CANDIDATES_7D})")
    lines.append("")
    lines.append("| Metric @7d | Value |")
    lines.append("|---|---|")
    lines.append(f"| Precision ret>0% | {prec0 if prec0 is not None else '-'} |")
    lines.append(f"| Precision ret>10% | {prec10 if prec10 is not None else '-'} |")
    lines.append(f"| Loss (RUG+DEAD) among passed | {loss if loss is not None else '-'}% |")
    lines.append(f"| Risk-filter rug/dead (matched) | {rf_m if rf_m is not None else '-'}% |")
    lines.append(f"| Risk-filter rug/dead (not matched) | {rf_n if rf_n is not None else '-'}% |")
    lines.append("")

    if n is None or n < GATE_MIN_CANDIDATES_7D:
        rec = "INSUFFICIENT DATA — gate not actually met."
    elif (prec0 is not None and prec0 >= 0.60
          and loss is not None and loss <= 0.20
          and rf_m is not None and rf_n is not None and rf_m > rf_n):
        rec = ("PRELIMINARY: EDGE CANDIDATE — passed gate shows >=60% profitable at 7d, "
               "loss rate <=20%, and the momentum/age risk filter discriminates rugs "
               "(matched rug rate > unmatched). MUST be ratified by Joni; the "
               "wallet-early question remains open.")
    else:
        rec = ("PRELIMINARY: NO EDGE (or inconclusive) — criteria not met: need "
               ">=60% precision at ret>0, <=20% loss, and the risk filter must "
               "discriminate. Ratify with Joni.")
    lines.append(f"**Preliminary recommendation**: {rec}")
    lines.append("")
    lines.append("This is a DRAFT for human ratification. Joni decides final verdict.")

    with open(os.path.join(REPO, "var", "memecoin_m3", "VERDICT_DRAFT.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
