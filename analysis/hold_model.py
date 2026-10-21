"""Modelo de aguante de niveles (4h, 0.5%) - v2 L1.

No es una senal de entrada ni un win rate. Responde una sola pregunta:
tras 3+ toques de un nivel, que probabilidad hay de que NO cierre 0,5%
mas alla del nivel en las siguientes 4 horas.

Entrenado con 3.009 eventos (BTCUSDT 5m, 2023-01 a 2026-09-30).
Holdout 2026: AUC 0,665 | Brier 0,175 | base 75,7%.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Iterable, Optional


MODEL = {
    "version": "toques-v2-l1",
    "target": "hold_4h_0.5pct",
    "trained_until": "2026-09-30 22:55:00+00:00",
    "holdout_2026": {"auc": 0.6653, "brier": 0.1746, "base": 0.7568, "n": 625},
    "features": [
        "dist",
        "atr",
        "ema200",
        "rng",
        "hourc",
        "dow",
        "x_atr48",
        "x_atr144",
        "x_atr288",
    ],
    "mean": [
        -8.546268804369033e-05,
        0.0012000579557684252,
        0.0004963299106516157,
        0.0010392189356920438,
        0.043842656299459284,
        -0.006173390032633996,
        0.0013875336400404408,
        0.0015687230818928234,
        0.0015906247087185664,
    ],
    "scale": [
        0.0018015047618306992,
        0.000520342193712222,
        0.005920197797069548,
        0.0006111665918583048,
        0.7106055800635263,
        0.7100371501988535,
        0.0005729831953626893,
        0.0006597288533857807,
        0.0006304620030828924,
    ],
    "coef": [
        0.009940294168822193,
        -0.036754966846978654,
        -0.03508442038409148,
        -0.13193430915386675,
        0.21059897795931476,
        -0.12170128376030045,
        -0.07212928375890257,
        -0.03776435526113883,
        -0.14003873498124078,
    ],
    "intercept": 1.1201115168295646,
}


def _ema_last(values: Iterable[float], span: int) -> float:
    """EMA recursiva, igual que pandas ewm(span=..., adjust=False)."""
    k = 2.0 / (span + 1.0)
    it = iter(values)
    e = next(it)
    for x in it:
        e = x * k + e * (1.0 - k)
    return e


def _true_ranges(kl: list[dict]) -> list[float]:
    out = []
    for i in range(1, len(kl)):
        h, l, prev_c = kl[i]["h"], kl[i]["l"], kl[i - 1]["c"]
        out.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return out


def features(
    kl: list[dict],
    level: float,
    price: float,
    now: datetime,
    side: str = "Soporte",
) -> Optional[dict]:
    """Calcula las 9 features del modelo.

    `kl` son velas de 5m ya cerradas, con claves t/o/h/l/c/v.
    `price` es el precio actual. Devuelve None si faltan velas o datos.
    """
    try:
        n = len(kl)
        if n < 300 or level <= 0 or price <= 0:
            return None
        c = [float(x["c"]) for x in kl]
        h = [float(x["h"]) for x in kl]
        l = [float(x["l"]) for x in kl]
        trs = _true_ranges(kl)
        if len(trs) < 288:
            return None

        atr14 = (sum(trs[-14:]) / 14.0) / price
        atr48 = (sum(trs[-48:]) / 48.0) / price
        atr144 = (sum(trs[-144:]) / 144.0) / price
        atr288 = (sum(trs[-288:]) / 288.0) / price
        ema200 = _ema_last(c, 200)

        hh = now.hour + now.minute / 60.0
        return {
            "dist": (price - level) / level,
            "atr": atr14,
            "ema200": price / ema200 - 1.0 if ema200 else 0.0,
            "rng": (h[-1] - l[-1]) / c[-1] if c[-1] else 0.0,
            "hourc": math.cos(2.0 * math.pi * hh / 24.0),
            "dow": math.sin(2.0 * math.pi * now.weekday() / 7.0),
            "x_atr48": atr48,
            "x_atr144": atr144,
            "x_atr288": atr288,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def score(feats: dict) -> Optional[float]:
    """Probabilidad de aguante 4h/0,5% (0..1), o None si faltan features."""
    try:
        z = MODEL["intercept"]
        for name, mu, sd, co in zip(
            MODEL["features"], MODEL["mean"], MODEL["scale"], MODEL["coef"]
        ):
            z += co * (feats[name] - mu) / (sd + 1e-12)
        if z > 30:
            return 1.0
        if z < -30:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))
    except (KeyError, TypeError, ValueError):
        return None


def tier(prob: float) -> str:
    """Etiqueta cualitativa del score. No cambia la probabilidad."""
    if prob >= 0.80:
        return "alto"
    if prob >= 0.60:
        return "medio"
    return "fragil"


def contributions(feats: dict) -> list[dict]:
    """Aporte de cada feature al logit, de mayor a menor valor absoluto.

    Positivo = empuja el aguante hacia arriba.
    Negativo = empuja el aguante hacia abajo (mas riesgo de ruptura).
    """
    out = []
    for name, mu, sd, co in zip(
        MODEL["features"], MODEL["mean"], MODEL["scale"], MODEL["coef"]
    ):
        z = co * (feats[name] - mu) / (sd + 1e-12)
        out.append({"feature": name, "contribution": z})
    out.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return out


def explain(feats: dict) -> dict:
    """Score + tier + drivers principales, para interpretacion."""
    prob = score(feats)
    if prob is None:
        return {}
    return {
        "prob": prob,
        "tier": tier(prob),
        "drivers": contributions(feats)[:4],
    }


def score_level(
    kl: list[dict],
    level: float,
    price: float,
    now: datetime,
    side: str = "Soporte",
) -> Optional[dict]:
    """Atajo: features + score + explicacion para un nivel concreto."""
    f = features(kl, level, price, now, side)
    if f is None:
        return None
    return {"features": f, **explain(f)}


def load_klines_jsonl(path: str) -> list[dict]:
    """Carga el JSONL del colector (klines_5m.jsonl) en el formato del modelo."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            out.append(
                {
                    "t": datetime.fromtimestamp(
                        int(raw["openTime"]) / 1000.0, tz=timezone.utc
                    ),
                    "o": float(raw["open"]),
                    "h": float(raw["high"]),
                    "l": float(raw["low"]),
                    "c": float(raw["close"]),
                    "v": float(raw["volume"]),
                }
            )
    return out
