from types import SimpleNamespace

from research.crypto_cot import COTContextProvider
from research.crypto_futures import build_funnel
from test_crypto_futures_research import NOW, candidate, macro, replay


def test_one_market_or_future_release_never_becomes_neutral():
    bias = SimpleNamespace(bias="bullish", confidence=0.7, historical_percentile=60, metadata={})
    provider = COTContextProvider(fetcher=lambda: {"BTC": {"as_of_date": "2026-09-01", "release_date": "2026-09-04"}},
                                  analyzer=SimpleNamespace(analyze=lambda _: {"BTC": bias}))
    context = provider.fetch(now=NOW)
    assert context["status"] == "PARTIAL"
    assert context["regime"] == "unknown"
    assert context["missing_markets"] == ["ETH"]
    assert not build_funnel(replay(candidate()), macro_context=macro(), cot_context=context)[1]


def test_missing_observation_and_boolean_only_macro_cannot_pass():
    payload = replay(candidate())
    payload["observations"][0].pop("observation_timestamp")
    funnel, candidates, _ = build_funnel(payload, macro_context=macro(), cot_regime="neutral")
    assert not candidates
    assert funnel["invalid_observations"] == 1
    assert not build_funnel(replay(candidate()), macro_context={"validated": True}, cot_regime="neutral")[1]
