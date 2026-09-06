from datetime import UTC, datetime, timedelta

import pytest

from research.core.contracts import (
    EvidenceKind,
    EvidenceReference,
    PointInTime,
    ProvenanceCategory,
    ResearchResult,
    ResearchStatus,
    RunMetadata,
)
from research.core.strategy import UnsupportedPhase, run_phase
from research.core.store import ResearchStore


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def metadata() -> RunMetadata:
    return RunMetadata(
        strategy_name="fixture",
        strategy_version="1.0.0",
        run_id="run-1",
        decision_time=NOW,
        started_at=NOW - timedelta(seconds=1),
        completed_at=NOW,
        input_available_at=NOW - timedelta(minutes=1),
    )


def evidence(*, available_at: datetime | None = NOW - timedelta(minutes=2)) -> EvidenceReference:
    return EvidenceReference(
        reference_id="e-1",
        source="fixture",
        claim="A source-backed claim",
        kind=EvidenceKind.FACT,
        confidence=0.9,
        point_in_time=PointInTime(
            event_time=NOW - timedelta(hours=1),
            available_at=available_at,
            decision_time=NOW,
        ),
        citation="https://example.test/e-1",
    )


def test_status_serialization_and_json_round_trip():
    result = ResearchResult(
        workflow="fixture.scan",
        status=ResearchStatus.NO_SETUP,
        metadata=metadata(),
        payload={"universe_scanned": 10},
        evidence=(evidence(),),
    )

    payload = result.to_dict()
    assert payload["status"] == "NO_SETUP"
    assert payload["safety_boundary"] == "READ_ONLY_RESEARCH_ONLY_HUMAN_GATED"
    assert ResearchResult.from_dict(payload).to_dict() == payload


def test_markdown_report_exposes_status_and_timestamp_semantics():
    result = ResearchResult(
        workflow="fixture.scan",
        status=ResearchStatus.INSUFFICIENT_EVIDENCE,
        metadata=metadata(),
        evidence=(evidence(available_at=None),),
        warnings=("availability could not be established",),
    )

    markdown = result.to_markdown()
    assert "INSUFFICIENT_EVIDENCE" in markdown
    assert "Decision time:" in markdown
    assert "UNKNOWN" in markdown
    assert "availability could not be established" in markdown


def test_point_in_time_does_not_fake_missing_availability():
    point = PointInTime(event_time=NOW - timedelta(days=1), decision_time=NOW)
    assert point.availability == "UNKNOWN"
    late = PointInTime(available_at=NOW + timedelta(seconds=1), decision_time=NOW)
    assert late.availability == "LATE"


def test_evidence_requires_nonempty_provenance_owner_and_lifecycle():
    reference = evidence()
    assert reference.provenance_category == ProvenanceCategory.UNKNOWN.value
    assert reference.state_owner == "UNKNOWN"
    assert reference.lifecycle == "UNKNOWN"
    with pytest.raises(ValueError, match="provenance_category"):
        EvidenceReference(reference_id="x", source="fixture", claim="claim", provenance_category="")


def test_incomplete_state_is_rejected():
    with pytest.raises(ValueError, match="requires at least one evidence"):
        ResearchResult(
            workflow="fixture.scan",
            status=ResearchStatus.SETUP_FOUND,
            metadata=metadata(),
        ).to_dict()

    with pytest.raises(ValueError, match="requires a visible warning"):
        ResearchResult(
            workflow="fixture.scan",
            status=ResearchStatus.ERROR,
            metadata=metadata(),
        ).to_dict()


def test_store_persists_results_and_contexts_atomically(tmp_path):
    store = ResearchStore(tmp_path)
    result = ResearchResult(
        workflow="fixture.scan",
        status=ResearchStatus.DATA_UNAVAILABLE,
        metadata=metadata(),
        warnings=("provider unavailable",),
    )
    path = store.save_result(result)
    assert path.exists()
    assert store.load_result("fixture.scan").status is ResearchStatus.DATA_UNAVAILABLE
    store.save_context("macro", {"regime": "unknown"})
    assert store.load_context("macro") == {"regime": "unknown"}


class PartialStrategy:
    name = "partial"
    version = "1"

    def scan(self, value: int) -> int:
        return value + 1


def test_strategy_phases_are_optional():
    strategy = PartialStrategy()
    assert run_phase(strategy, "scan", 2) == 3
    with pytest.raises(UnsupportedPhase):
        run_phase(strategy, "evaluate")


def test_missing_identity_remains_unknown():
    row = EvidenceReference.from_dict({'reference_id': 'x', 'source': 's', 'claim': 'c'})
    assert row.kind is EvidenceKind.UNKNOWN
    assert (row.provenance_category, row.state_owner, row.lifecycle) == ('UNKNOWN',) * 3


@pytest.mark.parametrize('available,event', [(NOW, NOW + timedelta(seconds=1)), (None, NOW), (NOW + timedelta(seconds=1), NOW)])
def test_ineligible_evidence_cannot_license_setup(available, event):
    ref = EvidenceReference(reference_id='x', source='s', claim='c',
                            point_in_time=PointInTime(event, available, NOW))
    assert ref.point_in_time.availability != 'ELIGIBLE'
    with pytest.raises(ValueError, match='eligible'):
        ResearchResult('fixture', ResearchStatus.SETUP_FOUND, metadata(), evidence=(ref,)).to_json()


def test_generation_time_is_not_invented_on_reload():
    row = ResearchResult('fixture', ResearchStatus.NO_SETUP, metadata()).to_dict()
    del row['generated_at']
    with pytest.raises(ValueError, match='generated_at'):
        ResearchResult.from_dict(row)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_machine_result_rejects_nonfinite_nested_payload(value):
    with pytest.raises(ValueError):
        ResearchResult('fixture', ResearchStatus.NO_SETUP, metadata(), payload={'nested': [value]}).to_json()


def test_store_rejects_colliding_names(tmp_path):
    with pytest.raises(ValueError, match='canonical'):
        ResearchStore(tmp_path).save_context('a/b', {})


def test_shared_context_filters_invalid_macro_but_preserves_private_state(tmp_path):
    from research.core.context import FileResearchContext
    context = FileResearchContext(tmp_path)
    context.store.save_context('cava', {'validated': False})
    context.store.save_context('macro', {'validated': True})
    context.store.save_context('portfolio', {'holdings': []})
    assert context.latest_macro_context() is None
    assert context.latest_cava_context() is None
    assert context.portfolio_state() == {'holdings': []}
