import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from subprocess import CompletedProcess

import pytest

from research.dune.materializer import DuneMaterializer


def test_concurrent_materializers_only_execute_once_and_keep_limit_identity(tmp_path):
    materializer = DuneMaterializer()
    output = tmp_path / "cache.json"
    response = CompletedProcess([], 0, json.dumps({"rows": [{"mint": "fixture"}]}), "")
    with patch("research.dune.materializer.subprocess.run", return_value=response) as run:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: materializer.materialize(query_id="123", output=output, limit=10), range(2)))
        assert run.call_count == 1
        assert sum(row["query_executed"] for row in results) == 1
        with pytest.raises(ValueError, match="incompatible"):
            materializer.materialize(query_id="123", output=output, limit=20)
        assert run.call_count == 1


def test_stale_cache_requires_explicit_refresh_and_failed_refresh_preserves_file(tmp_path):
    output = tmp_path / "cache.json"
    materializer = DuneMaterializer()
    old = {"query_identity": materializer.query_identity("123"), "rows": [], "row_count": 0,
           "fetched_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}
    output.write_text(json.dumps(old))
    with patch("research.dune.materializer.subprocess.run") as run:
        with pytest.raises(ValueError, match="stale"):
            materializer.materialize(query_id="123", output=output)
        run.assert_not_called()
        run.return_value = CompletedProcess([], 0, '{"error":"provider failure"}', "")
        with pytest.raises(ValueError, match="no result rows"):
            materializer.materialize(query_id="123", output=output, force=True)
        assert json.loads(output.read_text()) == old
