import json

import pytest

from scripts.verify_stage1_cached_day import verify


def test_complete_tape_does_not_make_intraday_launch_sample_full_day(tmp_path):
    manifest = {"rows": [{"mint": "fixture", "launch_ts": "2026-09-01 20:00:00 UTC"}], "sample_size": 1,
                "selection": {"frozen_before_event_replay": True}, "execution_id": "inline:2026-09-01T21:02:37Z",
                "date": "2026-09-01", "denominator": 1}
    (tmp_path / "launch_manifest.json").write_text(json.dumps(manifest))
    hours = {}
    for hour in range(24):
        key = f"{hour:02d}"
        directory = tmp_path / f"hour={key}"
        directory.mkdir()
        (directory / "events.jsonl").write_text("{}\n")
        (directory / "metrics.json").write_text(json.dumps({"metrics": {"retained_lines": 1}}))
        hours[key] = {"status": "COMPLETE", "curl_returncode": 0, "zstd_returncode": 0, "consumer_returncode": 0, "output_bytes": 3}
    (tmp_path / "checkpoint.json").write_text(json.dumps({"hours": hours}))
    audit = verify(tmp_path)
    assert audit["complete_hours"] == 24
    assert audit["full_calendar_day_sample"] is False
    hours["23"]["zstd_returncode"] = 1
    (tmp_path / "checkpoint.json").write_text(json.dumps({"hours": hours}))
    with pytest.raises(ValueError, match="unverified"):
        verify(tmp_path)
