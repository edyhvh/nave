"""X (Twitter) market view: entry/target prices, opinion, engagement from cached snapshots."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_BULLISH = re.compile(
    r"\b(bullish|breakout|buy the dip|buying|calls|long|moon|rip|squeeze|undervalued)\b",
    re.IGNORECASE,
)
_BEARISH = re.compile(
    r"\b(bearish|puts|short|dump|crash|overvalued|sell|top is in)\b",
    re.IGNORECASE,
)
_DOLLAR = re.compile(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)")
_ENTRY_CTX = re.compile(
    r"(?:entry|enter|buy(?:ing)?|add|accumulate|dip|support).{0,40}?\$?\s*(\d{2,4}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_TARGET_CTX = re.compile(
    r"(?:target|price target|\bPT\b|upside|goal|resistance).{0,40}?\$?\s*(\d{2,4}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_UNDER = re.compile(
    r"(?:under|below|<\s*)\s*\$?\s*(\d{2,4}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class XInterestProfile:
    """Backward-compatible summary for gem scoring."""

    ticker: str
    post_count: int
    engagement: int
    sentiment: str
    bullish_hits: int
    bearish_hits: int
    top_post_url: str | None
    snapshot_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "post_count": self.post_count,
            "engagement": self.engagement,
            "sentiment": self.sentiment,
            "bullish_hits": self.bullish_hits,
            "bearish_hits": self.bearish_hits,
            "top_post_url": self.top_post_url,
            "snapshot_date": self.snapshot_date,
        }


@dataclass(frozen=True)
class XMarketView:
    """Rich X layer: prices traders discuss + crowd opinion."""

    ticker: str
    post_count: int
    engagement: int
    sentiment: str
    opinion: str
    entry_prices: tuple[float, ...]
    target_prices: tuple[float, ...]
    entry_zone: str | None
    target_zone: str | None
    top_post_url: str | None
    snapshot_date: str | None
    sample_quotes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "post_count": self.post_count,
            "engagement": self.engagement,
            "sentiment": self.sentiment,
            "opinion": self.opinion,
            "entry_prices": list(self.entry_prices),
            "target_prices": list(self.target_prices),
            "entry_zone": self.entry_zone,
            "target_zone": self.target_zone,
            "top_post_url": self.top_post_url,
            "snapshot_date": self.snapshot_date,
            "sample_quotes": list(self.sample_quotes),
        }


def default_snapshot_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "stocks_history"


def _parse_price(token: str) -> float | None:
    try:
        value = float(str(token).replace(",", ""))
    except ValueError:
        return None
    if 5 <= value <= 50_000:
        return value
    return None


def _extract_prices_from_text(text: str) -> tuple[list[float], list[float], list[float]]:
    entries: list[float] = []
    targets: list[float] = []
    generic: list[float] = []

    for match in _DOLLAR.findall(text):
        p = _parse_price(match)
        if p is not None:
            generic.append(p)
    for match in _ENTRY_CTX.findall(text):
        p = _parse_price(match)
        if p is not None:
            entries.append(p)
    for match in _TARGET_CTX.findall(text):
        p = _parse_price(match)
        if p is not None:
            targets.append(p)
    for match in _UNDER.findall(text):
        p = _parse_price(match)
        if p is not None:
            entries.append(p)

    return entries, targets, generic


def _price_zone(prices: list[float]) -> str | None:
    if not prices:
        return None
    if len(prices) == 1:
        return f"${prices[0]:,.2f}"
    lo, hi = min(prices), max(prices)
    if abs(hi - lo) < 0.01:
        return f"${lo:,.2f}"
    return f"${lo:,.0f}–${hi:,.0f}"


def _top_prices(prices: list[float], limit: int = 5) -> tuple[float, ...]:
    if not prices:
        return ()
    counts = Counter(round(p, 2) for p in prices)
    ordered = [p for p, _ in counts.most_common(limit)]
    return tuple(ordered)


def _sentiment_from_posts(posts: list[Mapping[str, Any]]) -> tuple[str, int, int]:
    bull = bear = 0
    for post in posts:
        text = str(post.get("text") or "")
        bull += len(_BULLISH.findall(text))
        bear += len(_BEARISH.findall(text))
    if bull > bear * 1.25 and bull >= 2:
        return "bullish", bull, bear
    if bear > bull * 1.25 and bear >= 2:
        return "bearish", bull, bear
    if bull or bear:
        return "mixed", bull, bear
    return "neutral", bull, bear


def _opinion_label(sentiment: str, bull: int, bear: int) -> str:
    if sentiment == "bullish":
        return f"Crowd leans bullish ({bull} bullish cues vs {bear} bearish)."
    if sentiment == "bearish":
        return f"Crowd leans bearish ({bear} bearish cues vs {bull} bullish)."
    if sentiment == "mixed":
        return "Mixed chatter — confirm with price levels before sizing."
    return "Low directional signal in recent posts."


def build_x_market_view(
    ticker: str,
    posts: list[Mapping[str, Any]],
    stats: Mapping[str, Any],
    *,
    snapshot_date: str | None = None,
) -> XMarketView:
    """Parse posts for entry/target prices and opinion."""
    sym = ticker.upper()
    all_entries: list[float] = []
    all_targets: list[float] = []
    quotes: list[str] = []

    for post in posts:
        text = str(post.get("text") or "").strip()
        if not text:
            continue
        ent, tgt, _ = _extract_prices_from_text(text)
        all_entries.extend(ent)
        all_targets.extend(tgt)
        if ent or tgt or _BULLISH.search(text) or _BEARISH.search(text):
            snippet = text[:140].replace("\n", " ")
            if snippet:
                quotes.append(snippet)

    sentiment, bull, bear = _sentiment_from_posts(posts)
    engagement = int(stats.get("total_likes") or 0) + int(stats.get("total_replies") or 0) + int(
        stats.get("total_retweets") or 0
    )
    post_count = int(stats.get("post_count") or len(posts))

    return XMarketView(
        ticker=sym,
        post_count=post_count,
        engagement=engagement,
        sentiment=sentiment,
        opinion=_opinion_label(sentiment, bull, bear),
        entry_prices=_top_prices(all_entries),
        target_prices=_top_prices(all_targets),
        entry_zone=_price_zone(list(all_entries)),
        target_zone=_price_zone(list(all_targets)),
        top_post_url=stats.get("top_post_url"),
        snapshot_date=snapshot_date,
        sample_quotes=tuple(quotes[:4]),
    )


def _engagement_from_stats(stats: Mapping[str, Any]) -> int:
    return int(stats.get("total_likes") or 0) + int(stats.get("total_replies") or 0) + int(
        stats.get("total_retweets") or 0
    )


def load_x_market_index(
    *,
    snapshot_dir: str | Path | None = None,
) -> dict[str, XMarketView]:
    """Merge cached snapshots into per-ticker X market views."""
    root = Path(snapshot_dir) if snapshot_dir is not None else default_snapshot_dir()
    if not root.is_dir():
        return {}

    index: dict[str, XMarketView] = {}
    for path in sorted(root.glob("x_analysis_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        date_part = path.stem.replace("x_analysis_", "")[:10]
        summary = payload.get("summary_stats") or {}
        posts_by = payload.get("posts_by_ticker") or {}
        for ticker, stats in summary.items():
            sym = str(ticker).strip().upper()
            if not sym:
                continue
            posts = list(posts_by.get(sym) or posts_by.get(ticker) or [])
            candidate = build_x_market_view(sym, posts, stats, snapshot_date=date_part)
            prev = index.get(sym)
            if prev is None or candidate.engagement > prev.engagement:
                index[sym] = candidate
    return index


def load_x_interest_index(
    *,
    snapshot_dir: str | Path | None = None,
) -> dict[str, XInterestProfile]:
    """Legacy index for gem scoring (derived from market views)."""
    views = load_x_market_index(snapshot_dir=snapshot_dir)
    out: dict[str, XInterestProfile] = {}
    for sym, view in views.items():
        bull = 1 if view.sentiment == "bullish" else 0
        bear = 1 if view.sentiment == "bearish" else 0
        out[sym] = XInterestProfile(
            ticker=sym,
            post_count=view.post_count,
            engagement=view.engagement,
            sentiment=view.sentiment,
            bullish_hits=bull,
            bearish_hits=bear,
            top_post_url=view.top_post_url,
            snapshot_date=view.snapshot_date,
        )
    return out


def interest_score(profile: XInterestProfile | None, *, median_engagement: float) -> float:
    if profile is None or profile.post_count <= 0:
        return 0.0
    base = min(100.0, profile.post_count * 4.0)
    if median_engagement > 0 and profile.engagement > 0:
        ratio = profile.engagement / median_engagement
        base += min(40.0, ratio * 20.0)
    return min(100.0, base)