from __future__ import annotations

import json

from research.quant_state import load_quant_watch_state


def test_quant_watch_adapter_preserves_numeric_watches_and_unparsed_responsibilities(tmp_path):
    path = tmp_path / "watches.json"
    path.write_text(
        json.dumps(
            {
                "watches": [
                    {
                        "id": "A3-SPCX-entry-watch",
                        "subject": "SPCX (Nasdaq)",
                        "state": "active",
                        "kind": "acquisition",
                        "conditions": ["price below $120 (fair-value approach)"],
                        "thesis_ref": "private.thesis",
                    },
                    {
                        "id": "A1-portfolio-alerts",
                        "subject": "portfolio thesis alerts",
                        "state": "active",
                        "kind": "condition",
                        "conditions": ["thesis invalidation condition triggers"],
                    },
                    {
                        "id": "A3-BE-entry-watch",
                        "subject": "BE (NYSE)",
                        "state": "active",
                        "kind": "acquisition",
                        "conditions": ["pullback into $150-$170 support zone"],
                    },
                    {
                        "id": "A3-EQIX-entry-watch",
                        "subject": "EQIX (Nasdaq)",
                        "state": "active",
                        "kind": "acquisition",
                        "conditions": ["pullback into $950-$1000 support zone"],
                    },
                    {
                        "id": "ISM-ETN-candidate",
                        "subject": "ETN / ETNon (NYSE / Ondo tokenized)",
                        "state": "active",
                        "kind": "condition",
                        "conditions": ["conditional watch zone: $380-$395"],
                    },
                    {
                        "id": "ISM-CAT-candidate",
                        "subject": "CAT / CATon (NYSE / Ondo tokenized)",
                        "state": "active",
                        "kind": "condition",
                        "conditions": ["conditional watch zone: $767-$799"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    state = load_quant_watch_state(path)

    assert state is not None
    assert [row["ticker"] for row in state.deterministic_watches] == ["SPCX", "BE", "EQIX", "ETN", "CAT"]
    assert state.deterministic_watches[0]["condition"] == "BELOW"
    assert state.deterministic_watches[0]["threshold"] == 120.0
    assert state.deterministic_watches[1]["zone"] == [150.0, 170.0]
    assert state.deterministic_watches[-1]["zone"] == [767.0, 799.0]
    assert [row["id"] for row in state.unparsed_responsibilities] == ["A1-portfolio-alerts"]
    assert "A1-portfolio-alerts" in state.warnings[0]


def test_canonical_nonprice_responsibilities_stay_distinct(tmp_path):
    # Conditions recovered from canonical Quant watches on 2026-09-06.
    rows = [
        {'id': 'A1-portfolio-alerts', 'state': 'active', 'kind': 'condition',
         'subject': 'ONDO tokenized-equity positions vs thesis levels',
         'conditions': ['price materially approaches/breaches a thesis level recorded in B1.2 fundamental theses', 'thesis invalidation condition of any position triggers']},
        {'id': 'A2-ism-release-monitor', 'state': 'active', 'kind': 'event',
         'subject': 'ISM Manufacturing (1st biz day) / Services (3rd biz day), 10:00 ET',
         'conditions': ['release published on an ISM release day']},
        {'id': 'A4-nave-setup-alerts', 'state': 'active', 'kind': 'event',
         'subject': 'BTC/ETH/SOL NAVE setups meeting quality bar (R:R>=2, MTF alignment)',
         'conditions': ['weekly scan produces a TRADE-quality setup']},
    ]
    path = tmp_path / 'watches.json'
    path.write_text(json.dumps({'watches': rows}))
    result = load_quant_watch_state(path)
    assert result.deterministic_watches == ()
    assert list(result.unparsed_responsibilities) == rows
