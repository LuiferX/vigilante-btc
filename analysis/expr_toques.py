#!/usr/bin/env python3
"""
expr_toques.py - H3: expectativa NETA (dinero) del signal "toques" del modelo
congelado toques-wf-1, sobre el replay historico 2023-2026.

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H3 - expectativa NETA del
signal toques" (commiteado ANTES de correr esto).

Reglas duras:
  - Entrada al OPEN de la vela siguiente al timestamp de la muestra.
  - Coste SIEMPRE: ~0,23% por viaje (fee + slippage + 0,25*ATR).
  - Independencia: un trade a la vez, cooldown de 4h tras el cierre.
  - Bootstrap 10.000 con semilla fija. Resultado negativo se publica igual.
  - NO toca el modelo: solo lee prob_modelo ya registrado en el replay.

La infraestructura (cargadores, bootstrap, maquina de independencia, evaluacion)
vive en analysis/laboratorio.py, compartida por H3-H6. AquÃ­ solo la politica de
este experimento: quÃ© salidas se prueban y con quÃ© convicciÃ³n.

stdlib puro. Uso: python analysis/expr_toques.py
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from laboratorio import (  # noqa: E402,F401
    CACHE,
    FEE_PCT,
    P_TOP,
    SLIP_BASE,
    SLIP_K,
    atr_pct,
    bootstrap_ci,
    cargar_klines,
    cargar_muestras,
    coste_viaje,
    evaluar,
    motor_secuencia,
    veredicto,
)

COOLDOWN_H = 4
TP_PCT = 0.5  # salida gestionada
SL_PCT = 0.3
H4, H24 = 48, 288  # barras 5m

# salidas x convicciones = 6 celdas (pre-registradas)
SALIDAS = ["E1_h4", "E2_gest", "E3_h24"]
CONVICCIONES = ["todas", "top"]


# -------------------------------------------------------------- operaciÃ³n --
def operar(muestra, kl, tiempos, salida):
    """Retorno NETO de una muestra, o None si no hay datos suficientes."""
    t = datetime.datetime.fromisoformat(muestra["t"].replace("Z", "+00:00"))
    j = bisect.bisect_right(tiempos, t)  # open de la vela siguiente
    if j >= len(kl):
        return None
    corto = muestra["lado"] == "resistencia"
    entrada = kl[j]["o"]
    atrp = atr_pct(kl, j) or 0.05
    coste = coste_viaje(atrp)
    t_ent = kl[j]["t"]

    if salida == "E1_h4":
        k = j + H4
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
        barras = H4
    elif salida == "E3_h24":
        k = j + H24
        if k >= len(kl):
            return None
        salida_px = kl[k]["c"]
        barras = H24
    elif salida == "E2_gest":
        # gestionada: TP 0,5% / SL 0,3%, cierre forzoso a 4h.
        # corto: TP si low <= entrada*(1-0,005); SL si high >= entrada*(1+0,003)
        # si ambas en la misma vela -> se asume SL primero (conservador)
        fin = min(j + H4, len(kl) - 1)
        tp = entrada * (1 - TP_PCT / 100) if corto else entrada * (1 + TP_PCT / 100)
        sl = entrada * (1 + SL_PCT / 100) if corto else entrada * (1 - SL_PCT / 100)
        salida_px = None
        for i in range(j + 1, fin + 1):
            v = kl[i]
            toco_sl = v["h"] >= sl if corto else v["l"] <= sl
            if toco_sl:
                salida_px = sl
                break
            toco_tp = v["l"] <= tp if corto else v["h"] >= tp
            if toco_tp:
                salida_px = tp
                break
        if salida_px is None:
            salida_px = kl[fin]["c"]
        barras = H4
    else:
        raise ValueError(salida)

    if corto:
        bruto = (entrada - salida_px) / entrada * 100.0
    else:
        bruto = (salida_px - entrada) / entrada * 100.0
    return {
        "neto": bruto - coste,
        "bruto": bruto,
        "coste": coste,
        "t": t_ent,
        "atr_pct": atrp,
        "prob": muestra.get("prob_modelo"),
        "vol": muestra.get("volatilidad"),
        "sesion": muestra.get("sesion"),
        "hold_barras": barras,
    }


def secuencia_independiente(muestras, kl, tiempos, salida, conviccion):
    """Una operacion a la vez + cooldown -> retornos netos independientes."""
    return motor_secuencia(
        muestras,
        lambda m: operar(m, kl, tiempos, salida),
        conviccion=conviccion,
        cooldown_h=COOLDOWN_H,
        hold_fn=lambda r: r["hold_barras"],
    )


def costes_x2(detalle):
    return round(sum(d["neto"] - d["coste"] for d in detalle) / len(detalle), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", default=None, help="salida:conviccion, p.ej. E2_gest:todas")
    a = ap.parse_args()

    muestras = cargar_muestras()
    kl = cargar_klines()
    tiempos = [v["t"] for v in kl]
    print(f"muestras: {len(muestras)} | klines: {len(kl)}")

    celdas = {}
    for salida in SALIDAS:
        for conv in CONVICCIONES:
            rets, detalle = secuencia_independiente(muestras, kl, tiempos, salida, conv)
            if not rets:
                continue
            c = evaluar(rets, detalle)
            celdas[f"{salida}:{conv}"] = {"resumen": c, "costes_x2_media": costes_x2(detalle)}
            cc = celdas[f"{salida}:{conv}"]
            print(
                f"  {salida:9s} {conv:7s} n={c['n']:5d} neta={c['media']:+.4f}% "
                f"ic95=[{c['ic95'][0]:+.4f},{c['ic95'][1]:+.4f}] "
                f"hit={c['hit_rate']:.2f} -> {veredicto(c, cc['costes_x2_media'])}"
            )

    veredictos = {k: veredicto(v["resumen"], v["costes_x2_media"]) for k, v in celdas.items()}
    ps = [v["resumen"]["p_boot"] for v in celdas.values()]
    p_corr = min(1.0, min(ps) * len(ps)) if ps else 1.0

    out = {
        "hipotesis": "H3",
        "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "parametros": {
            "ventana_dias": 30,
            "p_alto": 0.95,
            "p_bajo": 0.05,
            "horizontes": list(SALIDAS),
            "cooldown_h": COOLDOWN_H,
            "fee_pct": FEE_PCT,
            "slip_base_pct": SLIP_BASE,
            "slip_k": SLIP_K,
            "bootstrap": 10000,
            "semilla": 42,
        },
        "variantes_probadas": len(ps),
        "p_corregido": round(p_corr, 5),
        "celdas": {
            k: dict(v["resumen"], costes_x2_media=v["costes_x2_media"], veredicto=veredictos[k])
            for k, v in celdas.items()
        },
        "veredicto": "sin_edge",
    }
    if any(v == "edge" for v in veredictos.values()):
        out["veredicto"] = "edge"
    p = os.path.join(AQUI, "data", "edge_toques.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {len(ps)} celdas): {p_corr:.5f}")
    print(f"veredicto global: {out['veredicto']}")
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
