#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entrenar.py - LABORATORIO DE MERCADO: mide como se mueve BTCUSDT.

Lee velas reales de Binance y mide, con percentiles honestos:
  1. Volatilidad por hora (percentiles)
  2. Movimiento tipico a 8h
  3. Sesiones: cual se mueve (Asia/Londres/NY/noche)
  4. Regimen ADX 4H: % de tiempo en tendencia vs rango
  5. Compresion -> expansion (el fuelle se abre?)

REARME 2026-11-01: antes se llamaba "entrenar" y proponia calibracion del bot
que operaba. Ahora es un laboratorio de MEDICION del mercado, sin ninguna
relacion con operar. Ademas reutiliza la fuente unica de velas
(`vigilante/red.py`) en lugar de traer su propia copia de `klines`/`ema`.

Solo mide. No toca nada. Uso: python entrenar.py
"""

from __future__ import annotations

import datetime
import json
import os
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from vigilante.indicadores import adx  # noqa: E402
from vigilante.red import klines  # noqa: E402


def percentil(vals, q):
    s = sorted(v for v in vals if v is not None)
    if not s:
        return None
    return s[min(len(s) - 1, max(0, int(q * len(s))))]


def medir() -> dict:
    kl_h1 = klines("1h", 500)
    kl_h4 = klines("4h", 200)
    if not kl_h1:
        return {"ok": False, "motivo": "sin velas 1H (¿Binance bloquea?)"}
    out = {"ok": True, "generado": datetime.datetime.now(UTC).isoformat()}

    # 1) volatilidad por hora
    por_hora = {}
    for v in kl_h1:
        h = v["t"].hour
        por_hora.setdefault(h, []).append((v["h"] - v["l"]) / v["c"] * 100)
    out["volatilidad_por_hora_pct"] = {
        str(h): {
            "n": len(r),
            "p50": round(percentil(r, 0.5), 4),
            "p95": round(percentil(r, 0.95), 4),
        }
        for h, r in sorted(por_hora.items())
        if len(r) >= 5
    }

    # 2) movimiento tipico a 8h
    cierres = [v["c"] for v in kl_h1]
    mov8 = []
    for i in range(len(cierres) - 8):
        mov8.append(abs(cierres[i + 8] - cierres[i]) / cierres[i] * 100)
    out["movimiento_8h_pct"] = {
        "n": len(mov8),
        "p50": round(percentil(mov8, 0.5), 4),
        "p95": round(percentil(mov8, 0.95), 4),
    }

    # 3) sesiones
    sesiones = {
        "Asia": range(0, 8),
        "Londres": range(8, 14),
        "NY": range(14, 21),
        "noche": range(21, 24),
    }
    out["movimiento_por_sesion_pct"] = {}
    for nombre, horas in sesiones.items():
        r = [(v["h"] - v["l"]) / v["c"] * 100 for v in kl_h1 if v["t"].hour in horas]
        if r:
            out["movimiento_por_sesion_pct"][nombre] = {
                "n": len(r),
                "p50": round(percentil(r, 0.5), 4),
            }

    # 4) régimen ADX 4H
    a4 = adx(kl_h4) if kl_h4 else None
    out["adx_4h"] = a4
    out["regimen"] = "tendencia" if (a4 or 0) >= 20 else "rango"

    # 5) compresion -> expansion
    if len(kl_h4) >= 60:
        ult = abs(kl_h4[-1]["h"] - kl_h4[-1]["l"])
        antes = [abs(v["h"] - v["l"]) for v in kl_h4[-60:]]
        p95 = percentil(antes, 0.95)
        out["fuelle"] = {
            "ultimo_rango": round(ult, 2),
            "p95_60v": round(p95, 2),
            "expansion": bool(p95 and ult > p95),
        }
    return out


def main() -> int:
    got = medir()
    print(json.dumps(got, ensure_ascii=False, indent=2))
    return 0 if got.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
