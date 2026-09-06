from dataclasses import replace
from datetime import UTC, datetime

from research.core.contracts import ResearchResult, ResearchStatus, RunMetadata
from research.orchestration import discord_chunks, present_result


def result(workflow="memecoin.discover", **payload):
    now = datetime(2026, 9, 6, tzinfo=UTC)
    return ResearchResult(workflow=workflow, status=ResearchStatus.STRATEGY_NOT_VALIDATED,
                          metadata=RunMetadata(strategy_name="test", strategy_version="1", run_id="test", decision_time=now, started_at=now),
                          payload=payload)


def test_presentation_is_lossless_and_crypto_is_not_stocks():
    artifact = result(candidates=[{"mint": "canonical-identity", "reason": "x" * 4001}], custom_detail={"must": "survive"})
    view = present_result(artifact, channel_id="1514695031901126727")
    assert view["result"] == artifact.to_dict()
    assert view["payload"]["custom_detail"] == {"must": "survive"}
    assert view["discord_text"].startswith("CRYPTO:")
    assert "sin operar" in view["discord_text"]
    assert "".join(view["discord_chunks"]) == view["discord_text"]
    assert all(len(part.encode("utf-16-le")) // 2 <= 2000 for part in view["discord_chunks"])
    assert view["delivery"]["surface"] == "parent"


def test_unicode_chunks_and_silence_never_hide_provider_failure():
    text = "á🚀" * 2500
    assert "".join(discord_chunks(text)) == text
    assert all(len(part.encode("utf-16-le")) // 2 <= 2000 for part in discord_chunks(text))
    silent = replace(result("portfolio.watch", silent=True), status=ResearchStatus.NO_SETUP)
    assert present_result(silent)["discord_text"] == "[SILENT]"
    unavailable = replace(silent, status=ResearchStatus.DATA_UNAVAILABLE)
    assert present_result(unavailable)["discord_text"].startswith("STOCKS:")
    assert present_result(unavailable)["delivery"]["ready"] is False
