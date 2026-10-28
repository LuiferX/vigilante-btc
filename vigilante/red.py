#!/usr/bin/env python3
"""
red.py - COSTURA DE RED del Vigilante (Fase 4 de modularizacion).

Unico sitio que habla con Binance (futuros + espejo Vision). Extraido 1:1 de
vigilante_cloud.py. `MERCADO`/`FUENTE` siguen siendo diccionarios compartidos:
el fallback futuros->spot sigue pegando dentro del mismo proceso.

vigilante_cloud.py re-exporta estos nombres (API publica intacta).

OJO con los tests: test_vigilante.py parchea `fetch` para simular fallos de red.
Al vivir aqui, el parcheo se hace en los DOS sitios (v.fetch y vigilante.red.fetch)
para que la costura use el fetch simulado. Ver test_vigilante.py, bloque "red".
"""

import datetime
import json
import time
import urllib.request
from typing import Any

FAPI = "https://fapi.binance.com/fapi/v1"


FDATA = "https://fapi.binance.com/futures/data"


VISION = "https://data-api.binance.vision/api/v3"


FUENTE = {"nombre": "futuros"}


# base: la URL elegida para toda la pasada (None = aun sin elegir).
MERCADO: dict[str, str | None] = {"base": None}


def _elegir_fuente():
    """Fija FAPI (futuros) o VISION (spot) para TODA la pasada. Devuelve la base."""
    if MERCADO.get("base"):
        return MERCADO["base"]
    try:
        fetch(f"{FAPI}/ping", tries=1)
        MERCADO["base"] = FAPI
        FUENTE["nombre"] = "futuros"
    except Exception:
        MERCADO["base"] = VISION
        FUENTE["nombre"] = "spot"
    return MERCADO["base"]


def fetch(url, timeout=20, tries=3) -> Any:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vigilante-cloud/3.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    if last is not None:
        raise last
    # Solo se llega aqui con tries<=0 (ningun llamador lo hace): antes hacia
    # `raise None` -> TypeError oscuro. Ahora el motivo es explicito.
    raise RuntimeError(f"fetch sin intentos: {url}")


def klines(interval, limit):
    base = MERCADO.get("base") or FAPI
    try:
        data = fetch(f"{base}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    except Exception:
        alt = VISION if base == FAPI else FAPI
        data = fetch(f"{alt}/klines?symbol=BTCUSDT&interval={interval}&limit={limit}", tries=2)
        MERCADO["base"] = alt
        FUENTE["nombre"] = "spot" if alt == VISION else "futuros"
    if not isinstance(data, list) or not data:
        raise ValueError("klines vacías o error API")
    data = [k for k in data if isinstance(k, (list, tuple)) and len(k) >= 6]
    if not data:
        raise ValueError("klines sin filas válidas")
    return [
        {
            "t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        }
        for k in data
    ]


def ticker24():
    base = MERCADO.get("base") or FAPI
    try:
        t = fetch(f"{base}/ticker/24hr?symbol=BTCUSDT")
    except Exception:
        alt = VISION if base == FAPI else FAPI
        t = fetch(f"{alt}/ticker/24hr?symbol=BTCUSDT", tries=2)
        MERCADO["base"] = alt
        FUENTE["nombre"] = "spot" if alt == VISION else "futuros"
    try:
        last = float(t.get("lastPrice"))
        chg = float(t.get("priceChangePercent"))
        hi = float(t.get("highPrice"))
        lo = float(t.get("lowPrice"))
    except Exception:
        raise ValueError("ticker24 sin claves")
    return {
        "last": last,
        "chg": chg,
        "hi": hi,
        "lo": lo,
        "vol": float(t.get("volume", 0) or 0),
    }


def sentiment() -> dict[str, float | None]:
    # None = metrica no disponible; cada fetch llena su clave o la deja en None.
    out: dict[str, float | None] = {"funding": None, "oi": None, "taker": None, "spread": None}
    try:
        f = fetch(f"{FAPI}/premiumIndex?symbol=BTCUSDT", tries=1)
        out["funding"] = round(float(f["lastFundingRate"]) * 100, 4)
    except Exception:
        pass
    try:
        oi = fetch(f"{FAPI}/openInterest?symbol=BTCUSDT", tries=1)
        out["oi"] = float(oi["openInterest"])
    except Exception:
        pass
    try:
        t = fetch(f"{FDATA}/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=1", tries=1)
        if t:
            out["taker"] = round(float(t[-1]["buySellRatio"]), 3)
    except Exception:
        pass
    try:
        b = fetch(f"{VISION}/ticker/bookTicker?symbol=BTCUSDT", tries=1)
        bid, ask = float(b["bidPrice"]), float(b["askPrice"])
        mid = (bid + ask) / 2
        if mid > 0:
            out["spread"] = round((ask - bid) / mid * 10000, 2)
    except Exception:
        pass
    return out
