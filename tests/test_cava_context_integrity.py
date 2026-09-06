from datetime import timedelta

import pytest

from research.cava.corroboration import CavaCorroborator
from research.cava.pipeline import CavaWorkflow
from research.cava.transcript import Transcript
from research.core.context import context_is_usable
from research.core.store import ResearchStore
from test_cava_intelligence import NOW, RSS, FixtureTranscriptProvider


def series(_):
    return {"retrieved_at": NOW.isoformat(), "records": [
        {"date": "2026-09-04", "value": 101}, {"date": "2026-09-03", "value": 100}]}


def test_unsorted_observations_and_expiring_context_keep_source_times(tmp_path):
    store = ResearchStore(tmp_path)
    result = CavaWorkflow(store=store).run(rss_xml=RSS, now=NOW,
        transcript_provider=FixtureTranscriptProvider(Transcript("La inflación sube.", "es", "fixture", NOW)),
        corroborate=CavaCorroborator(series_fetcher=series))
    assert result.payload["corroboration_indicators"][-1]["latest"] == 101
    saved = store.load_context("cava")
    assert context_is_usable(saved, now=NOW)
    assert not context_is_usable(saved, now=NOW + timedelta(days=4))
    assert saved["corroboration"][0]["metadata"]["retrieved_at"] == NOW.isoformat()


def test_context_failure_cannot_advance_cursor_and_contradictions_invalidate_old_context(tmp_path, monkeypatch):
    store = ResearchStore(tmp_path)
    save = store.save_context
    def fail_context(name, payload):
        if name == "cava":
            raise OSError("simulated interruption")
        return save(name, payload)
    monkeypatch.setattr(store, "save_context", fail_context)
    workflow = CavaWorkflow(store=store)
    provider = FixtureTranscriptProvider(Transcript("La inflación sube.", "es", "fixture", NOW))
    with pytest.raises(OSError):
        workflow.run(rss_xml=RSS, now=NOW, transcript_provider=provider,
                     corroborate=CavaCorroborator(series_fetcher=series))
    assert store.load_context("cava_cursor") is None
    monkeypatch.setattr(store, "save_context", save)
    save("cava", {"validated": True})
    provider = FixtureTranscriptProvider(Transcript("La inflación baja.", "es", "fixture", NOW))
    result = workflow.run(rss_xml=RSS, now=NOW, transcript_provider=provider,
                          corroborate=CavaCorroborator(series_fetcher=series))
    assert result.payload["contradictions"]
    assert store.load_context("cava")["validated"] is False
    assert store.load_context("cava_cursor") is None
