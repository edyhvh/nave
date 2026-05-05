"""Politician trades — provider parsing, store dedup, scanner diff."""

from __future__ import annotations

import json

import httpx
import pytest

from trading.stocks.politicians.provider import (
    FMPPoliticianTradesProvider,
    PoliticianTrade,
    PoliticianTradesError,
    _parse_row,
)
from trading.stocks.politicians.scanner import run_daily_scan
from trading.stocks.politicians.store import SeenStore


# ─── Provider: row parsing ──────────────────────────────────────────────


def test_parse_row_house_full_payload():
    row = {
        "symbol": "FMAO",
        "disclosureDate": "2026-04-24",
        "transactionDate": "2026-04-20",
        "firstName": "Robert E",
        "lastName": "Latta",
        "office": "Robert E Latta",
        "district": "OH 05",
        "owner": "Spouse",
        "assetDescription": "Farmers & Merchants Bancorp Inc",
        "assetType": "Stock",
        "type": "Purchase",
        "amount": "$1,001 - $15,000",
        "link": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034401.pdf",
    }
    trade = _parse_row("house", row)
    assert trade.chamber == "house"
    assert trade.symbol == "FMAO"
    assert trade.politician == "Robert E Latta"
    assert trade.state == "OH"
    assert trade.district == "OH 05"
    assert trade.owner == "Spouse"
    assert trade.transaction_type == "Purchase"
    assert trade.amount_range == "$1,001 - $15,000"
    assert trade.transaction_date == "2026-04-20"
    assert trade.disclosure_date == "2026-04-24"
    assert trade.unique_id == trade.link


def test_parse_row_senate_compact_district():
    row = {
        "symbol": "SBUX",
        "firstName": "James",
        "lastName": "Banks",
        "district": "IN03",
        "type": "Sale",
        "amount": "$1,001 - $15,000",
        "link": "https://efdsearch.senate.gov/search/view/ptr/abc/",
    }
    trade = _parse_row("senate", row)
    assert trade.state == "IN"
    assert trade.district == "IN03"


def test_parse_row_synthesizes_link_when_missing():
    row = {
        "symbol": "AAPL",
        "firstName": "Jane",
        "lastName": "Doe",
        "transactionDate": "2026-04-01",
        "disclosureDate": "2026-04-15",
        "amount": "$50,001 - $100,000",
        "type": "Purchase",
    }
    trade = _parse_row("house", row)
    assert trade.link.startswith("missing-link::house::2026-04-15::AAPL::")
    # Must remain stable for dedup — same input → same surrogate.
    assert _parse_row("house", row).unique_id == trade.unique_id


def test_parse_row_falls_back_to_office_when_names_missing():
    trade = _parse_row("house", {"office": "Some Office", "link": "x"})
    assert trade.politician == "Some Office"


# ─── Provider: HTTP layer ───────────────────────────────────────────────


def _stub_provider(handler) -> FMPPoliticianTradesProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        base_url="https://example.test", transport=transport, timeout=2.0
    )
    return FMPPoliticianTradesProvider(api_key="test-key", http=client)


def test_provider_fetch_all_combines_chambers():
    house_row = {
        "symbol": "NVDA",
        "firstName": "A",
        "lastName": "B",
        "type": "Purchase",
        "link": "https://house/1.pdf",
    }
    senate_row = {
        "symbol": "MSFT",
        "firstName": "C",
        "lastName": "D",
        "type": "Sale",
        "link": "https://senate/1.html",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "/house-latest" in request.url.path:
            return httpx.Response(200, json=[house_row])
        if "/senate-latest" in request.url.path:
            return httpx.Response(200, json=[senate_row])
        return httpx.Response(404)

    provider = _stub_provider(handler)
    trades = provider.fetch_all()
    assert {t.chamber for t in trades} == {"house", "senate"}
    assert {t.symbol for t in trades} == {"NVDA", "MSFT"}


def test_provider_raises_on_403():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    provider = _stub_provider(handler)
    with pytest.raises(PoliticianTradesError):
        provider.fetch_house()


def test_provider_raises_on_non_list_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = _stub_provider(handler)
    with pytest.raises(PoliticianTradesError):
        provider.fetch_house()


def test_provider_raises_on_non_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>maintenance</html>")

    provider = _stub_provider(handler)
    with pytest.raises(PoliticianTradesError, match="non-JSON"):
        provider.fetch_house()


def test_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(PoliticianTradesError):
        FMPPoliticianTradesProvider()


# ─── Store: round-trip ──────────────────────────────────────────────────


def test_store_persists_and_reloads(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path=path)
    assert store.size() == 0
    assert store.last_scan_at is None
    assert not store.contains("link-a")

    store.add_many(["link-a", "link-b"])
    store.save()
    assert store.last_scan_at is not None

    reloaded = SeenStore(path=path)
    assert reloaded.contains("link-a")
    assert reloaded.contains("link-b")
    assert reloaded.size() == 2
    assert reloaded.last_scan_at == store.last_scan_at


def test_store_handles_corrupt_file(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{not valid json")
    store = SeenStore(path=path)
    assert store.size() == 0  # silently recovers


def test_store_legacy_list_format(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps(["link-a", "link-b"]))
    store = SeenStore(path=path)
    assert store.contains("link-a")
    assert store.size() == 2
    assert store.last_scan_at is None


# ─── Scanner: diff logic ────────────────────────────────────────────────


class _StaticProvider:
    def __init__(self, trades):
        self._trades = trades

    def fetch_all(self):
        return list(self._trades)


def _make_trade(link: str, **kwargs) -> PoliticianTrade:
    base = dict(
        chamber="house",
        symbol="NVDA",
        politician="Jane Doe",
        party=None,
        state="CA",
        district="CA 12",
        owner="Self",
        asset_description="NVIDIA Corp",
        asset_type="Stock",
        transaction_type="Purchase",
        amount_range="$1,001 - $15,000",
        transaction_date="2026-04-15",
        disclosure_date="2026-04-28",
        link=link,
    )
    base.update(kwargs)
    return PoliticianTrade(**base)


def test_scanner_first_run_returns_everything(tmp_path):
    store = SeenStore(path=tmp_path / "seen.json")
    provider = _StaticProvider(
        [_make_trade("link-a"), _make_trade("link-b", symbol="AAPL")]
    )
    result = run_daily_scan(provider=provider, store=store)
    assert result["fetched_total"] == 2
    assert result["new_total"] == 2
    assert result["previous_scan_at"] is None
    assert result["seen_total_after"] == 2


def test_scanner_subsequent_run_filters_seen(tmp_path):
    store_path = tmp_path / "seen.json"
    provider = _StaticProvider([_make_trade("link-a"), _make_trade("link-b")])
    run_daily_scan(provider=provider, store=SeenStore(path=store_path))

    # Second run: same two trades plus one new one.
    provider2 = _StaticProvider(
        [
            _make_trade("link-a"),
            _make_trade("link-b"),
            _make_trade("link-c", symbol="MSFT", transaction_type="Sale"),
        ]
    )
    result = run_daily_scan(provider=provider2, store=SeenStore(path=store_path))
    assert result["fetched_total"] == 3
    assert result["new_total"] == 1
    assert result["new_trades"][0]["link"] == "link-c"
    assert result["previous_scan_at"] is not None


def test_scanner_dry_run_does_not_persist(tmp_path):
    store_path = tmp_path / "seen.json"
    provider = _StaticProvider([_make_trade("link-a")])

    result = run_daily_scan(
        provider=provider, store=SeenStore(path=store_path), persist=False
    )
    assert result["new_total"] == 1
    assert not store_path.exists()

    # Re-run with persist=False — still all new.
    result2 = run_daily_scan(
        provider=provider, store=SeenStore(path=store_path), persist=False
    )
    assert result2["new_total"] == 1


def test_scanner_summary_aggregates_correctly(tmp_path):
    store = SeenStore(path=tmp_path / "seen.json")
    provider = _StaticProvider(
        [
            _make_trade("l1", chamber="house", symbol="NVDA", transaction_type="Purchase"),
            _make_trade("l2", chamber="house", symbol="NVDA", transaction_type="Sale"),
            _make_trade("l3", chamber="senate", symbol="AAPL", transaction_type="Purchase"),
        ]
    )
    result = run_daily_scan(provider=provider, store=store)
    summary = result["summary"]
    assert summary["by_chamber"] == {"house": 2, "senate": 1}
    assert summary["by_type"] == {"Purchase": 2, "Sale": 1}
    assert summary["top_symbols"][0] == {"symbol": "NVDA", "count": 2}
    assert summary["unique_politicians"] == 1
