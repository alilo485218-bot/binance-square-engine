"""Trend Engine — fetch trending coins + crypto news.

Uses free public APIs (no keys required):
- CoinGecko `/search/trending` for hot coins.
- CoinGecko `/coins/markets` for top movers (24h price change).
- RSS from CoinTelegraph + CoinDesk for news.

The output is a small, ranked list of "trend signals" your Content Generator
can pick from to write posts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any

import feedparser
import requests

COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
NEWS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

DEFAULT_TIMEOUT = 10


@dataclass
class TrendCoin:
    symbol: str           # e.g. "BTC"
    name: str             # e.g. "Bitcoin"
    cashtag: str          # e.g. "$BTC"
    price_usd: float | None
    change_24h: float | None
    direction: str        # "up" / "down" / "flat"
    rank: int | None
    source: str           # "coingecko_trending" / "coingecko_movers"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrendNews:
    title: str
    link: str
    published: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_get(url: str, params: dict | None = None) -> dict | list | None:
    try:
        r = requests.get(url, params=params or {}, timeout=DEFAULT_TIMEOUT,
                         headers={"User-Agent": "binance-square-engine/0.1"})
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[trend_engine] GET {url} failed: {exc}")
        return None


def fetch_trending_coins(limit: int = 7) -> list[TrendCoin]:
    """Top searched coins on CoinGecko in the last 24h."""
    data = _safe_get(COINGECKO_TRENDING_URL)
    out: list[TrendCoin] = []
    if not data or "coins" not in data:
        return out
    for entry in data["coins"][:limit]:
        item = entry.get("item", {})
        symbol = (item.get("symbol") or "").upper()
        name = item.get("name") or ""
        if not symbol:
            continue
        price = item.get("data", {}).get("price")
        change = item.get("data", {}).get("price_change_percentage_24h", {}).get("usd")
        out.append(TrendCoin(
            symbol=symbol,
            name=name,
            cashtag=f"${symbol}",
            price_usd=float(price) if price is not None else None,
            change_24h=float(change) if change is not None else None,
            direction=_direction(change),
            rank=item.get("market_cap_rank"),
            source="coingecko_trending",
        ))
    return out


def fetch_top_movers(limit: int = 5) -> list[TrendCoin]:
    """Top 24h gainers from CoinGecko markets (top 100 by market cap)."""
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "24h",
    }
    data = _safe_get(COINGECKO_MARKETS_URL, params=params)
    if not data:
        return []
    rows = sorted(
        [c for c in data if c.get("price_change_percentage_24h_in_currency") is not None],
        key=lambda c: abs(c["price_change_percentage_24h_in_currency"]),
        reverse=True,
    )[:limit]
    out: list[TrendCoin] = []
    for c in rows:
        symbol = (c.get("symbol") or "").upper()
        change = c.get("price_change_percentage_24h_in_currency")
        out.append(TrendCoin(
            symbol=symbol,
            name=c.get("name") or "",
            cashtag=f"${symbol}",
            price_usd=c.get("current_price"),
            change_24h=change,
            direction=_direction(change),
            rank=c.get("market_cap_rank"),
            source="coingecko_movers",
        ))
    return out


def fetch_news(limit_per_feed: int = 5) -> list[TrendNews]:
    """Latest crypto headlines from RSS feeds."""
    out: list[TrendNews] = []
    for url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit_per_feed]:
                out.append(TrendNews(
                    title=getattr(entry, "title", "").strip(),
                    link=getattr(entry, "link", "").strip(),
                    published=getattr(entry, "published", ""),
                    source=feed.feed.get("title", url),
                ))
        except Exception as exc:  # noqa: BLE001
            print(f"[trend_engine] RSS {url} failed: {exc}")
    return out


def _direction(change: float | None) -> str:
    if change is None:
        return "flat"
    if change >= 1:
        return "up"
    if change <= -1:
        return "down"
    return "flat"


def get_full_snapshot() -> dict[str, Any]:
    """One-shot snapshot used by the UI's "Get Trends" button."""
    trending = fetch_trending_coins()
    movers = fetch_top_movers()
    news = fetch_news()

    # Dedup coins by symbol, keep first occurrence (trending takes priority).
    seen: set[str] = set()
    coins: list[TrendCoin] = []
    for c in trending + movers:
        if c.symbol in seen:
            continue
        seen.add(c.symbol)
        coins.append(c)

    return {
        "fetched_at": int(time.time()),
        "coins": [c.to_dict() for c in coins],
        "news": [n.to_dict() for n in news],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_full_snapshot(), indent=2, ensure_ascii=False))
