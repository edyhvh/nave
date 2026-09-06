import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from subprocess import CompletedProcess

import pytest

from research.dune.materializer import DuneMaterializer
from research.memecoin_workflow import MemecoinResearchWorkflow
from research.core.store import ResearchStore
from research.nave.resource_guard import check


def test_concurrent_materializers_only_execute_once_and_keep_limit_identity(tmp_path):
    materializer = DuneMaterializer()
    output = tmp_path / "cache.json"
    response = CompletedProcess([], 0, json.dumps({"rows": [{"mint": "fixture"}]}), "")
    with patch("research.dune.materializer.subprocess.run", return_value=response) as run:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: materializer.materialize(query_id="123", query_text="SELECT 1", budget=budget(10), output=output, limit=10), range(2)))
        assert run.call_count == 1
        assert sum(row["query_executed"] for row in results) == 1
        with pytest.raises(ValueError, match="incompatible"):
            materializer.materialize(query_id="123", query_text="SELECT 1", budget=budget(20), output=output, limit=20)
        assert run.call_count == 1


def test_stale_cache_requires_explicit_refresh_and_failed_refresh_preserves_file(tmp_path):
    output = tmp_path / "cache.json"
    materializer = DuneMaterializer()
    old = {"query_identity": materializer.query_identity("123", "SELECT 1"), "rows": [], "row_count": 0,
           "fetched_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}
    output.write_text(json.dumps(old))
    with patch("research.dune.materializer.subprocess.run") as run:
        with pytest.raises(ValueError, match="stale"):
            materializer.materialize(query_id="123", query_text="SELECT 1", budget=budget(), output=output)
        run.assert_not_called()
        run.return_value = CompletedProcess([], 0, '{"error":"provider failure"}', "")
        with pytest.raises(ValueError, match="no result rows"):
            materializer.materialize(query_id="123", query_text="SELECT 1", budget=budget(), output=output, force=True)
        assert json.loads(output.read_text()) == old


def test_discovery_cannot_bypass_cache_freshness_and_nan_cannot_authorize_credits(tmp_path):
    output = tmp_path / "cache.json"
    output.write_text(json.dumps({"provider": "dune", "rows": [], "row_count": 0,
                                  "fetched_at": "2020-01-01T00:00:00Z"}))
    with pytest.raises(ValueError, match="stale"):
        MemecoinResearchWorkflow(store=ResearchStore(tmp_path / "state")).discover([], dune_cache=output)
    assert not check(credits_used=0, credits_included=2500, checkpoint_used=0, estimate=float("nan"), free_disk_gb=20).allowed


def budget(limit=10000):
    return {"approved": True, "query_identity": DuneMaterializer.query_identity("123", "SELECT 1", limit=limit),
            "observed_at": datetime.now(UTC).isoformat(), "credits_used": 0, "credits_included": 2500,
            "checkpoint_used": 0, "estimate": 1, "free_disk_gb": 20}


@pytest.mark.parametrize('estimate', [None, float('nan'), float('inf'), 76, 3000])
def test_actual_spend_path_refuses_invalid_budget(tmp_path, estimate):
    approval = budget()
    approval['estimate'] = estimate
    with patch('research.dune.materializer.subprocess.run') as run:
        with pytest.raises(ValueError, match='budget|HARD_STOP'):
            DuneMaterializer().materialize(query_id='123', query_text='SELECT 1', budget=approval, output=tmp_path / 'cache.json')
        run.assert_not_called()


def test_unscoped_cache_is_rejected(tmp_path):
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'rows': [], 'fetched_at': '2020-01-01T00:00:00Z'}))
    with pytest.raises(ValueError, match='untrusted'):
        MemecoinResearchWorkflow(store=ResearchStore(tmp_path)).discover([], dune_cache=path)


def test_changed_frozen_sql_invalidates_identity():
    assert DuneMaterializer.query_identity('1', 'SELECT 1') != DuneMaterializer.query_identity('1', 'SELECT 2')
