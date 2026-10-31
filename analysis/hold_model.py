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

MODEL = {'version': 'toques-wf-1', 'target': 'hold_4h_0.5pct', 'trained_until': '2026-09-30 22:55:00+00:00', 'holdout_2026': {'auc': None, 'brier': 0.1237, 'skill': 0.0093, 'base': 0.8538, 'n': 212}, 'wf': {'folds': 11, 'muestras_oos': 7757, 'skill_medio': 0.0168, 'racha_positiva': 6, 'skill_folds': [0.0111, 0.0104, 0.0028, 0.019, 0.0304, 0.0231, -0.0055, 0.0204, 0.0348, 0.0132, 0.0251]}, 'features': ['dist', 'atr', 'ema200', 'rng', 'hourc', 'dow', 'x_atr48', 'x_atr144', 'x_atr288'], 'mean': [-0.00014471902899527983, 0.0013422890357383682, -0.00015422267700606877, 0.0015690369453809844, 0.0011800404585300068, -0.08165292068442347, 0.0013385479332434255, 0.0014126025893459204, 0.0014580719082939986], 'scale': [0.006663299240638484, 0.0009287107880874037, 0.007077131053340157, 0.0013562768488327192, 0.7156957839129136, 0.7213757356393746, 0.0007378356425407469, 0.0006942695553991874, 0.0006551650795141382], 'coef': [-0.0, 0.0, -0.0, -0.0, 0.09829794261377577, -0.19040384269895175, 0.0, -0.0, -0.2073024131403363], 'intercept': 1.5426070329136758, 'congelado': {'congelado': True, 'fecha_congelacion': '2026-10-24', 'descongelar_si': ['PSI estable < 0.25 durante 1 semana completa con este modelo en produccion', '>= 300 muestras efectivas nuevas posteriores a la congelacion (~5-6 semanas)', 'Hipotesis registrada en EXPERIMENTOS.md ANTES de entrenar', 'El candidato supera a toques-wf-1 en el MISMO walk-forward (mismos folds, mismo embargo)'], 'excepciones_inmediatas': ['Bug en features o scoring (correccion > congelacion)', 'Cambio estructural en la fuente de datos que altere la semantica de las features']}}


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
