#!/usr/bin/env python3
"""Colector de datos publicos de trading (Binance Futures + RSS).

Uso:
    python collector.py

No usa claves de API. Solo endpoints publicos y feeds RSS.
Los datos se guardan en data/btcusdt/*.jsonl (append-only, con dedup por clave).
"""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "btcusdt"
DATA.mkdir(parents=True, exist_ok=True)

UA = "trading-data-collector/1.0 (+https://github.com)"


def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_get_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def append_jsonl(path: Path, records: list[dict], key: str) -> int:
    """Agrega registros nuevos (dedup por `key`). Devuelve cuantos se agregaron."""
    existing = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing.add(json.loads(line).get(key))
                except Exception:
                    continue
    added = 0
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            k = rec.get(key)
            if k in existing:
                continue
            existing.add(k)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    return added


def fetch_funding() -> list[dict]:
    url = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=100"
    raw = http_get_json(url)
    out = []
    for r in raw:
        out.append({
            "source": "binance_funding",
            "symbol": r.get("symbol"),
            "fundingRate": r.get("fundingRate"),
            "fundingTime": r.get("fundingTime"),
            "markPrice": r.get("markPrice"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def fetch_open_interest() -> list[dict]:
    url = ("https://fapi.binance.com/futures/data/openInterestHist"
           "?symbol=BTCUSDT&period=5m&limit=500")
    raw = http_get_json(url)
    out = []
    for r in raw:
        out.append({
            "source": "binance_oi",
            "symbol": r.get("symbol"),
            "sumOpenInterest": r.get("sumOpenInterest"),
            "sumOpenInterestValue": r.get("sumOpenInterestValue"),
            "timestamp": r.get("timestamp"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def fetch_long_short(name: str, endpoint: str) -> list[dict]:
    url = (f"https://fapi.binance.com/futures/data/{endpoint}"
           f"?symbol=BTCUSDT&period=5m&limit=500")
    raw = http_get_json(url)
    out = []
    for r in raw:
        rec = {
            "source": name,
            "symbol": r.get("symbol"),
            "timestamp": r.get("timestamp"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        for k, v in r.items():
            if k not in ("symbol", "timestamp"):
                rec[k] = v
        out.append(rec)
    return out


def fetch_klines(interval: str = "5m", limit: int = 1500) -> list[dict]:
    """Klines de Binance Futures con fallback a Bybit si Binance da 451/403."""
    url = (
        "https://fapi.binance.com/fapi/v1/klines"
        f"?symbol=BTCUSDT&interval={interval}&limit={limit}"
    )
    try:
        raw = http_get_json(url)
        out = []
        for k in raw:
            out.append({
                "source": f"binance_klines_{interval}",
                "interval": interval,
                "openTime": k[0],
                "open": k[1],
                "high": k[2],
                "low": k[3],
                "close": k[4],
                "volume": k[5],
                "closeTime": k[6],
                "quoteVolume": k[7],
                "trades": k[8],
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
        return out
    except Exception as e:
        print(f"Binance klines {interval} error: {e}; probando Bybit")
        return fetch_klines_bybit(interval, limit)


def fetch_klines_bybit(interval: str, limit: int = 1000) -> list[dict]:
    """Fallback oficial Bybit linear. Mismo esquema que el colector."""
    bybit_interval = {"5m": "5", "1h": "60", "4h": "240", "1d": "D"}.get(interval, "5")
    interval_ms = {"5m": 300000, "1h": 3600000, "4h": 14400000, "1d": 86400000}.get(interval, 300000)
    url = (
        "https://api.bybit.com/v5/market/kline"
        f"?category=linear&symbol=BTCUSDT&interval={bybit_interval}"
        f"&limit={min(limit, 1000)}"
    )
    raw = http_get_json(url)
    rows = (raw.get("result") or {}).get("list") or []
    out = []
    for k in rows:
        # Bybit: start, open, high, low, close, volume, turnover; newest first.
        out.append({
            "source": f"bybit_klines_{interval}",
            "interval": interval,
            "openTime": int(k[0]),
            "open": k[1],
            "high": k[2],
            "low": k[3],
            "close": k[4],
            "volume": k[5],
            "closeTime": int(k[0]) + interval_ms,
            "quoteVolume": k[6] if len(k) > 6 else None,
            "trades": None,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    out.sort(key=lambda x: x["openTime"])
    return out


def fetch_rss(name: str, url: str) -> list[dict]:
    text = http_get_text(url)
    root = ET.fromstring(text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if not link:
            continue
        out.append({
            "source": name,
            "title": title,
            "link": link,
            "pubDate": pub,
            "description": desc[:500],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def main():
    jobs = [
        ("funding.jsonl", fetch_funding, "fundingTime"),
        ("open_interest.jsonl", fetch_open_interest, "timestamp"),
        ("global_ls.jsonl", lambda: fetch_long_short("binance_global_ls", "globalLongShortAccountRatio"), "timestamp"),
        ("top_ls_account.jsonl", lambda: fetch_long_short("binance_top_ls_account", "topLongShortAccountRatio"), "timestamp"),
        ("top_ls_position.jsonl", lambda: fetch_long_short("binance_top_ls_position", "topLongShortPositionRatio"), "timestamp"),
        ("taker_ls.jsonl", lambda: fetch_long_short("binance_taker_ls", "takerlongshortRatio"), "timestamp"),
        ("klines_5m.jsonl", lambda: fetch_klines("5m", 1500), "openTime"),
        ("klines_1h.jsonl", lambda: fetch_klines("1h", 1000), "openTime"),
        ("klines_4h.jsonl", lambda: fetch_klines("4h", 500), "openTime"),
        ("klines_1d.jsonl", lambda: fetch_klines("1d", 200), "openTime"),
    ]
    for fname, fn, key in jobs:
        try:
            records = fn()
            n = append_jsonl(DATA / fname, records, key)
            print(f"{fname}: +{n} (total fetched {len(records)})")
        except Exception as e:
            print(f"{fname}: error {e}")

    feeds = [
        ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("cointelegraph", "https://cointelegraph.com/rss"),
        ("bitcoinmagazine", "https://bitcoinmagazine.com/feed"),
    ]
    news = []
    for name, url in feeds:
        try:
            news.extend(fetch_rss(name, url))
        except Exception as e:
            print(f"RSS {name} error: {e}")
    n = append_jsonl(DATA / "news.jsonl", news, "link")
    print(f"news.jsonl: +{n} (total fetched {len(news)})")


if __name__ == "__main__":
    main()
