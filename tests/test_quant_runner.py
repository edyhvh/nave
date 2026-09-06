from datetime import UTC, datetime
from unittest.mock import patch
import subprocess

import pytest

from research.quant_runner import run


def test_cli_failure_is_journaled_without_leaking_provider_stderr(tmp_path):
    failure = subprocess.CalledProcessError(1, "nave", stderr="SECRET_PROVIDER_TOKEN")
    with patch("research.quant_runner.subprocess.run", side_effect=failure) as command:
        view = run("cava", state_dir=tmp_path, channel_id="1514695031901126727", now=datetime(2026, 9, 7, tzinfo=UTC))
    assert command.call_args.args[0][2:6] == ["cli.main", "intel", "cava", "daily"]
    assert "SECRET" not in str(view)
    assert view["status"] == "DATA_UNAVAILABLE"
    assert len(list(tmp_path.glob("quant_runs/*/result.json"))) == 1


def test_shabbat_and_missing_snapshot_do_not_execute(tmp_path):
    with patch("research.quant_runner.subprocess.run") as command:
        view = run("cava", state_dir=tmp_path, channel_id="1514695031901126727", now=datetime(2026, 9, 5, 12, tzinfo=UTC))
        assert view["discord_text"] == "[SILENT]"
        with pytest.raises(ValueError, match="snapshot"):
            run("memecoin", state_dir=tmp_path, channel_id="1514695031901126727", now=datetime(2026, 9, 7, tzinfo=UTC))
        command.assert_not_called()


def test_short_manifest_has_runner_and_options_stay_disabled():
    import json
    from pathlib import Path
    from research.quant_runner import COMMANDS
    manifest = json.loads((Path(__file__).parents[1] / 'ops/quant_nave_jobs.json').read_text())
    for job in manifest['jobs']:
        assert job['enabled'] is False
        if job['runner_workflow'] is not None:
            assert job['runner_workflow'] in COMMANDS
    assert COMMANDS['shorts'] == ('stocks', 'short', 'scan')
    assert 'options' not in COMMANDS
    assert '--refresh-ledger' not in COMMANDS['portfolio']


def test_interactive_origin_and_scheduled_destination_are_distinct():
    from research.orchestration import delivery_destination
    parent, thread = '1514695031901126727', '1514695031901126728'
    assert delivery_destination(parent)['chat_id'] == parent
    for kind, field in [('thread', 'thread_id'), ('forum_post', 'forum_post_id')]:
        origin = {'origin_type': kind, 'channel_id': parent, field: thread, 'message_id': '123'}
        result = delivery_destination(parent, origin)
        assert result['chat_id'] == thread
        assert result['origin'] == origin
        with pytest.raises(ValueError):
            delivery_destination(parent, {'origin_type': kind, 'channel_id': parent})
