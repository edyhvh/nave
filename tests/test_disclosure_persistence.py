from unittest.mock import patch

import pytest

from research.core.store import ResearchStore
from research.disclosures import DisclosureWorkflow


def test_failed_result_write_does_not_consume_disclosure(tmp_path):
    store = ResearchStore(tmp_path)
    workflow = DisclosureWorkflow(store=store)
    record = {"symbol": "ABC", "type": "Purchase", "link": "https://example.test/filing"}
    with patch.object(store, "save_result", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            workflow.sync_payload(congress_records=[record])
    assert store.load_context("disclosures_seen") is None
    result = workflow.sync_payload(congress_records=[record])
    assert result.payload["new_total"] == 1
    assert result.metadata.input_available_at is None
    assert result.evidence[0].point_in_time.availability == "UNKNOWN"
