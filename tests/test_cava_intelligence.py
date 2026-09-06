from datetime import UTC, datetime

import httpx

from research.cava.corroboration import CavaCorroborator
from research.cava.pipeline import CavaWorkflow, _transcript_claims, parse_rss
from research.cava.transcript import SupadataTranscriptProvider, Transcript, TranscriptUnavailable
from research.core.contracts import EvidenceKind, EvidenceReference, ResearchStatus, PointInTime
from research.core.store import ResearchStore


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
RSS = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>yt:video:new-video</id><title>Nuevo análisis macro</title>
    <published>2026-09-04T10:00:00Z</published>
  </entry>
  <entry>
    <id>yt:video:new-video</id><title>Nuevo análisis macro</title>
    <published>2026-09-04T10:00:00Z</published>
  </entry>
  <entry>
    <id>yt:video:old-video</id><title>Video anterior</title>
    <published>2026-09-03T10:00:00Z</published>
  </entry>
</feed>"""


class FixtureTranscriptProvider:
    def __init__(self, transcript: Transcript | None = None, error: str | None = None):
        self.transcript = transcript
        self.error = error
        self.calls: list[str] = []

    def fetch(self, video_id: str) -> Transcript:
        self.calls.append(video_id)
        if self.error:
            raise TranscriptUnavailable(self.error)
        assert self.transcript is not None
        return self.transcript


def test_rss_deduplicates_video_ids_and_sorts_newest_first():
    videos = parse_rss(RSS)
    assert [video.video_id for video in videos] == ["new-video", "old-video"]


def test_transcript_unavailable_does_not_advance_cursor(tmp_path):
    store = ResearchStore(tmp_path)
    provider = FixtureTranscriptProvider(error="quota temporarily unavailable")
    result = CavaWorkflow(store=store).run(rss_xml=RSS, transcript_provider=provider, now=NOW)

    assert result.status is ResearchStatus.DATA_UNAVAILABLE
    assert result.payload["cursor_advanced"] is False
    assert store.load_context("cava_cursor") is None
    assert provider.calls == ["new-video"]


def test_validated_context_is_persisted_and_cursor_advances(tmp_path):
    store = ResearchStore(tmp_path)
    transcript = Transcript(
        text="La inflación podría mantenerse alta. Esto significa que la liquidez importa.",
        language="es",
        source="supadata",
        available_at=NOW,
    )
    provider = FixtureTranscriptProvider(transcript=transcript)

    def corroborate(video, claims, decision_time):
        return [
            EvidenceReference(
                reference_id=f"macro-source-{topic}",
                source="official.example",
                claim="Official macro series is available",
                kind=EvidenceKind.FACT,
                confidence=0.95,
                citation="https://official.example/macro",
                point_in_time=PointInTime(event_time=NOW, available_at=NOW, decision_time=NOW),
                metadata={"topic": topic},
            )
            for topic in ("inflation", "liquidity")
        ]

    result = CavaWorkflow(store=store).run(
        rss_xml=RSS,
        transcript_provider=provider,
        corroborate=corroborate,
        now=NOW,
    )
    assert result.status is ResearchStatus.SETUP_FOUND
    assert result.payload["evidence_quality"] == "VALIDATED"
    assert store.load_context("cava")["source_video_id"] == "new-video"
    assert "new-video" in store.load_context("cava_cursor")["processed_video_ids"]


def test_transcript_only_result_is_explicitly_not_validated_when_source_is_unavailable(tmp_path):
    store = ResearchStore(tmp_path)
    provider = FixtureTranscriptProvider(
        transcript=Transcript("El dólar es relevante.", "es", "supadata", NOW)
    )
    result = CavaWorkflow(store=store).run(
        rss_xml=RSS,
        transcript_provider=provider,
        corroborate=lambda *_args: [],
        now=NOW,
    )
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.payload["evidence_quality"] == "TRANSCRIPT_ONLY"
    assert store.load_context("cava") is None
    assert store.load_context("cava_cursor") is None


def test_supadata_uses_runtime_key_and_supports_synchronous_payload():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-api-key"] == "test-key"
        assert request.url.params["url"] == "https://www.youtube.com/watch?v=new-video"
        return httpx.Response(200, json={"content": "Transcript text", "lang": "es"})

    provider = SupadataTranscriptProvider(
        api_key="test-key",
        language="es",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    transcript = provider.fetch("new-video")
    assert transcript.text == "Transcript text"
    assert requests[0].url.params["text"] == "true"
    assert requests[0].url.params["mode"] == "auto"


def test_supadata_async_job_is_polled_without_exposing_key():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/transcript"):
            return httpx.Response(202, json={"jobId": "job-1"})
        return httpx.Response(200, json={"content": [{"text": "Ready"}], "lang": "es"})

    provider = SupadataTranscriptProvider(
        api_key="test-key",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_attempts=1,
        poll_wait_seconds=0,
    )
    assert provider.fetch("new-video").text == "Ready"
    assert paths == ["/v1/transcript", "/v1/transcript/job-1"]


def test_default_corroborator_uses_authoritative_series_and_marks_fact():
    calls: list[str] = []

    def series(series_id: str):
        calls.append(series_id)
        return {"retrieved_at": NOW.isoformat(), "records": [{"date": "2026-09-03", "value": 100}, {"date": "2026-09-04", "value": 101}]}

    transcript = Transcript("La inflación sube y las tasas bajan.", "es", "supadata", NOW)
    # Exercise the production callback directly so the test never depends on a live endpoint.
    video = parse_rss(RSS)[0]
    claims = _transcript_claims(video, transcript, NOW)
    corroboration = CavaCorroborator(series_fetcher=series)(video, claims, NOW)

    assert calls == ["CPIAUCSL", "DFF"]
    assert len(corroboration.evidence) == 2
    assert all(item.kind is EvidenceKind.FACT for item in corroboration.evidence)
    assert all(item.metadata["provider_path"] == "injected" for item in corroboration.evidence)


def test_corroborator_records_contradiction_without_inventing_support():
    def series(_series_id: str):
        return {"retrieved_at": NOW.isoformat(), "records": [{"date": "2026-09-03", "value": 101}, {"date": "2026-09-04", "value": 100}]}

    transcript = Transcript("La inflación sube.", "es", "supadata", NOW)
    video = parse_rss(RSS)[0]
    claims = _transcript_claims(video, transcript, NOW)
    corroboration = CavaCorroborator(series_fetcher=series)(video, claims, NOW)

    assert corroboration.contradictions[0]["classification"] == "FACT"
    assert corroboration.indicators[0]["relationship"] == "contradicts"
    assert corroboration.evidence[0].metadata["relationship"] == "contradicts"


def test_cava_partial_source_failure_never_persists_qualified_context(tmp_path):
    def series(series_id: str):
        if series_id == "DFF":
            raise RuntimeError("temporary source outage")
        return {"retrieved_at": NOW.isoformat(), "records": [{"date": "2026-09-03", "value": 100}, {"date": "2026-09-04", "value": 101}]}

    transcript = Transcript("La inflación sube y las tasas suben.", "es", "supadata", NOW)
    result = CavaWorkflow(store=ResearchStore(tmp_path)).run(
        rss_xml=RSS,
        transcript_provider=FixtureTranscriptProvider(transcript=transcript),
        corroborate=CavaCorroborator(series_fetcher=series),
        now=NOW,
    )

    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.payload["corroboration_status"] == "PARTIAL"
    assert result.payload["contradictions"] == []
    assert result.payload["cursor_advanced"] is False
    assert "rates" in " ".join(result.warnings)


def test_plain_commentary_has_no_known_speaker_or_fact():
    claims = _transcript_claims(parse_rss(RSS)[0], Transcript('El mercado está complicado.', 'es', 'supadata', NOW), NOW)
    assert claims[0].kind is EvidenceKind.UNKNOWN
    assert claims[0].metadata['speaker_attributed'] is False


def test_failed_latest_does_not_starve_older_or_advance_cursor(tmp_path):
    provider = FixtureTranscriptProvider(error='removed')
    workflow = CavaWorkflow(store=ResearchStore(tmp_path))
    for _ in range(3):
        workflow.run(rss_xml=RSS, transcript_provider=provider, now=NOW)
    assert provider.calls == ['new-video', 'old-video', 'new-video']
    assert workflow.store.load_context('cava_cursor') is None


def test_direct_fred_actual_csv_shape_and_separate_clocks():
    from research.cava.corroboration import _direct_fred, _SERIES
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, text='observation_date,CPIAUCSL\n2026-08-01,324.5\n')))
    data = _direct_fred('CPIAUCSL', http)
    assert data['records'][0]['CPIAUCSL'] == '324.5'
    assert data['latest_observation_at'] == data['as_of'] == '2026-08-01'
    assert data['retrieved_at'] != data['as_of']
    assert 'gold' not in _SERIES
