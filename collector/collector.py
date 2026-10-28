#!/usr/bin/env python3
"""Colector de datos publicos de trading (Binance Futures + RSS).

Uso:
    python collector.py

No usa claves de API. Solo endpoints publicos y feeds RSS.
Los datos se guardan en data/btcusdt/*.jsonl (append-only, con dedup por clave).
"""
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "btcusdt"
DATA.mkdir(parents=True, exist_ok=True)
HEALTH = BASE / "data" / "health.json"

UA = "trading-data-collector/1.1 (+https://github.com/LuiferX/vigilante-btc)"
MAX_LINES = {"klines_5m.jsonl": 200_000, "news.jsonl": 5_000}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_get_json(url: str, timeout: int = 30) -> Any:
    """JSON publico de un endpoint. `Any` a proposito: la forma depende del origen."""
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
        f.flush()
        os.fsync(f.fileno())
    return added


def trim_jsonl(path: Path, max_lines: int) -> int:
    """Recorta un JSONL a las ultimas `max_lines`. Devuelve cuantas borro."""
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    if len(lines) <= max_lines:
        return 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.writelines(lines[-max_lines:])
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(lines) - max_lines


def write_health(payload: dict) -> None:
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HEALTH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, HEALTH)


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


def okx_data(url: str) -> list:
    raw = http_get_json(url)
    if str(raw.get("code")) != "0":
        raise RuntimeError(f"OKX error {raw.get('code')}: {raw.get('msg')}")
    return raw.get("data") or []


def okx_value(row) -> list:
    if isinstance(row, dict):
        return row.get("value") or []
    return row or []


def fetch_funding_okx(limit: int = 100) -> list[dict]:
    rows = okx_data(
        "https://www.okx.com/api/v5/public/funding-rate-history"
        f"?instId=BTC-USDT-SWAP&limit={min(limit, 100)}"
    )
    out = []
    for r in rows:
        out.append({
            "source": "okx_funding",
            "symbol": "BTCUSDT",
            "fundingRate": r.get("realizedRate") or r.get("fundingRate"),
            "fundingTime": int(r["fundingTime"]),
            "markPrice": None,
            "collected_at": now_iso(),
        })
    return out


def fetch_open_interest_okx() -> list[dict]:
    rows = okx_data(
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume"
        "?ccy=BTC&period=5m"
    )
    out = []
    for r in rows:
        value = okx_value(r)
        if len(value) < 2:
            continue
        out.append({
            "source": "okx_oi",
            "symbol": "BTCUSDT",
            "sumOpenInterest": value[1],
            "sumOpenInterestValue": value[1],
            "oi_unit": "usd",
            "timestamp": int(value[0]),
            "collected_at": now_iso(),
        })
    return out


def fetch_long_short_okx() -> list[dict]:
    rows = okx_data(
        "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
        "?ccy=BTC&period=5m"
    )
    out = []
    for r in rows:
        value = okx_value(r)
        if len(value) < 2:
            continue
        ratio = float(value[1])
        long_account = ratio / (1.0 + ratio) if ratio > 0 else 0.5
        out.append({
            "source": "okx_global_ls",
            "symbol": "BTCUSDT",
            "timestamp": int(value[0]),
            "longShortRatio": f"{ratio:.6f}",
            "longAccount": f"{long_account:.6f}",
            "shortAccount": f"{1.0 - long_account:.6f}",
            "collected_at": now_iso(),
        })
    return out


def fetch_long_short_bybit() -> list[dict]:
    """Fallback de razon largas/cortas de cuentas (Bybit).

    Binance bloquea con HTTP 451 (razones legales) los endpoints de top-traders
    desde IP de EE.UU. (GitHub Actions). Bybit publica la razon de cuentas
    largas/cortas de perpetuos BTC, que NO es exactamente "top traders" pero es
    la mejor fuente publica alternativa. Se etiqueta con su propio `source`
    (`bybit_account_ratio`) para no confundirla con la de Binance.
    """
    url = ("https://api.bybit.com/v5/market/account-ratio"
           "?category=linear&symbol=BTCUSDT&period=5min&limit=100")
    raw = http_get_json(url)
    lista = (raw.get("result") or {}).get("list") or []
    out = []
    for r in lista:
        try:
            buy = float(r.get("buyRatio"))
            sell = float(r.get("sellRatio"))
        except (TypeError, ValueError):
            continue
        ratio = buy / sell if sell > 0 else None
        out.append({
            "source": "bybit_account_ratio",
            "symbol": r.get("symbol"),
            "timestamp": int(r["timestamp"]),
            "longShortRatio": f"{ratio:.6f}" if ratio is not None else None,
            "longAccount": f"{buy:.6f}",
            "shortAccount": f"{sell:.6f}",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    if not out:
        raise RuntimeError("bybit account-ratio sin filas")
    return out


def fetch_taker_okx() -> list[dict]:
    rows = okx_data(
        "https://www.okx.com/api/v5/rubik/stat/taker-volume"
        "?ccy=BTC&instType=CONTRACTS&period=5m"
    )
    out = []
    for r in rows:
        value = okx_value(r)
        if len(value) < 3:
            continue
        buy, sell = float(value[1]), float(value[2])
        ratio = buy / sell if sell > 0 else None
        out.append({
            "source": "okx_taker_ls",
            "symbol": "BTCUSDT",
            "timestamp": int(value[0]),
            "buySellRatio": f"{ratio:.6f}" if ratio is not None else None,
            "buyVol": f"{buy:.6f}",
            "sellVol": f"{sell:.6f}",
            "collected_at": now_iso(),
        })
    return out


def with_fallback(
    label: str, primary: Callable[[], list[dict]], fallback: Callable[[], list[dict]]
) -> list[dict]:
    try:
        return primary()
    except Exception as e:
        print(f"{label}: fuente primaria error {e}; probando fallback")
        return fallback()


def only_closed(records: list[dict]) -> list[dict]:
    """Descarta la vela en curso; el motor solo debe ver velas cerradas."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    out = []
    for row in records:
        close_time = row.get("closeTime")
        if close_time is None or int(close_time) <= now_ms:
            out.append(row)
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
        print(f"Binance klines {interval} error: {e}; probando data-api.binance.vision")
        try:
            return fetch_klines_vision(interval, limit)
        except Exception as e2:
            print(f"Binance Vision klines {interval} error: {e2}; probando Bybit")
            try:
                return fetch_klines_bybit(interval, limit)
            except Exception as e3:
                print(f"Bybit klines {interval} error: {e3}; probando Kraken")
                return fetch_klines_kraken(interval, limit)


def fetch_klines_vision(interval: str, limit: int = 1000) -> list[dict]:
    """Klines spot publicas de Binance Vision; suele funcionar donde fapi da 451."""
    url = (
        "https://data-api.binance.vision/api/v3/klines"
        f"?symbol=BTCUSDT&interval={interval}&limit={min(limit, 1000)}"
    )
    raw = http_get_json(url)
    out = []
    for k in raw:
        out.append({
            "source": f"binance_vision_klines_{interval}",
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


def fetch_klines_kraken(interval: str, limit: int = 720) -> list[dict]:
    """Fallback final: Kraken spot XBTUSD."""
    kraken_interval = {"5m": 5, "1h": 60, "4h": 240, "1d": 1440}.get(interval, 5)
    interval_ms = {"5m": 300000, "1h": 3600000, "4h": 14400000, "1d": 86400000}.get(interval, 300000)
    url = (
        "https://api.kraken.com/0/public/OHLC"
        f"?pair=XBTUSD&interval={kraken_interval}"
    )
    raw = http_get_json(url)
    if raw.get("error"):
        raise RuntimeError(str(raw["error"]))
    result = raw.get("result") or {}
    rows: list = next((v for k, v in result.items() if k != "last"), [])
    out = []
    for k in rows[-min(limit, 720):]:
        out.append({
            "source": f"kraken_klines_{interval}",
            "interval": interval,
            "openTime": int(k[0]) * 1000,
            "open": k[1],
            "high": k[2],
            "low": k[3],
            "close": k[4],
            "volume": k[6],
            "closeTime": int(k[0]) * 1000 + interval_ms,
            "quoteVolume": None,
            "trades": int(k[7]) if len(k) > 7 else None,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


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


def main() -> int:
    started = now_iso()
    jobs = [
        ("funding.jsonl", lambda: with_fallback("funding", fetch_funding, fetch_funding_okx), "fundingTime"),
        ("open_interest.jsonl", lambda: with_fallback("open_interest", fetch_open_interest, fetch_open_interest_okx), "timestamp"),
        ("global_ls.jsonl", lambda: with_fallback("global_ls", lambda: fetch_long_short("binance_global_ls", "globalLongShortAccountRatio"), fetch_long_short_okx), "timestamp"),
        ("top_ls_account.jsonl", lambda: with_fallback("top_ls_account", lambda: fetch_long_short("binance_top_ls_account", "topLongShortAccountRatio"), fetch_long_short_bybit), "timestamp"),
        # Mismo fallback para posiciones: si Binance bloquea (451), se publica la
        # razon de cuentas de Bybit CON SU PROPIO source. No es la metrica de
        # top-traders por posicion, pero queda trazable y la vela no se pierde.
        ("top_ls_position.jsonl", lambda: with_fallback("top_ls_position", lambda: fetch_long_short("binance_top_ls_position", "topLongShortPositionRatio"), fetch_long_short_bybit), "timestamp"),
        ("taker_ls.jsonl", lambda: with_fallback("taker_ls", lambda: fetch_long_short("binance_taker_ls", "takerlongshortRatio"), fetch_taker_okx), "timestamp"),
        ("klines_5m.jsonl", lambda: fetch_klines("5m", 1500), "openTime"),
        ("klines_1h.jsonl", lambda: fetch_klines("1h", 1000), "openTime"),
        ("klines_4h.jsonl", lambda: fetch_klines("4h", 500), "openTime"),
        ("klines_1d.jsonl", lambda: fetch_klines("1d", 200), "openTime"),
    ]
    # dict[str, Any]: el payload de salud mezcla bool/str/contadores y sub-dicts
    # por trabajo; sin la anotacion mypy lo cierra como dict[str, object] y luego
    # rechaza cada asignacion indexada (health["jobs"][fname] = ...).
    health: dict[str, Any] = {
        "run_at": started,
        "ok": False,
        "kline_ok": False,
        "data_dir": "data/btcusdt",
        "jobs": {},
        "news": {},
    }
    kline_ok = False
    for fname, fn, key in jobs:
        try:
            records = fn()
            if fname.startswith("klines_"):
                records = only_closed(records)
            added = append_jsonl(DATA / fname, records, key)
            trimmed = trim_jsonl(DATA / fname, MAX_LINES[fname]) if fname in MAX_LINES else 0
            source = records[-1].get("source") if records else None
            last_key = records[-1].get(key) if records else None
            health["jobs"][fname] = {
                "ok": True,
                "fetched": len(records),
                "added": added,
                "trimmed": trimmed,
                "source": source,
                "last_key": last_key,
            }
            if fname.startswith("klines_") and records:
                kline_ok = True
            print(f"{fname}: +{added} (total fetched {len(records)}, source {source})")
        except Exception as e:
            health["jobs"][fname] = {"ok": False, "error": str(e)}
            print(f"{fname}: error {e}")

    feeds = [
        ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("cointelegraph", "https://cointelegraph.com/rss"),
        ("bitcoinmagazine", "https://bitcoinmagazine.com/feed"),
    ]
    news = []
    for name, url in feeds:
        try:
            got = fetch_rss(name, url)
            news.extend(got)
            health["news"][name] = {"ok": True, "fetched": len(got)}
        except Exception as e:
            health["news"][name] = {"ok": False, "error": str(e)}
            print(f"RSS {name} error: {e}")
    try:
        added = append_jsonl(DATA / "news.jsonl", news, "link")
        trimmed = trim_jsonl(DATA / "news.jsonl", MAX_LINES["news.jsonl"])
        health["news"]["ok"] = any(
            row.get("ok") for row in health["news"].values() if isinstance(row, dict)
        )
        health["news"]["added"] = added
        health["news"]["trimmed"] = trimmed
        print(f"news.jsonl: +{added} (total fetched {len(news)})")
    except Exception as e:
        health["news"]["ok"] = False
        health["news"]["error"] = str(e)
        print(f"news.jsonl: error {e}")

    health["kline_ok"] = kline_ok
    health["ok"] = kline_ok
    health["finished_at"] = now_iso()
    write_health(health)
    return 0 if kline_ok else 1


if __name__ == "__main__":
    sys.exit(main())

