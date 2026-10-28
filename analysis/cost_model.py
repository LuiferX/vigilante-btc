#!/usr/bin/env python3
"""cost_model.py - el puente entre la skill medida y el dinero.

Skill sin costos es media verdad. El edge del modelo se mide en error de
probabilidad; el dinero se mide DESPUES de comisiones y slippage. Este modulo
hace esa conversion explicita, con la matematica a la vista:

Marco simetrico por operacion (unidades de R, Marco = movimiento que define el
trade, p.ej. el 0.5% del target de aguante):

    EV(R) = p*(+1) - (1-p)*(-1) - c
          = 2p - 1 - c          c = coste de ida y vuelta en unidades del marco

Con eso se contesta lo que importa:
  - prob_minima(c)     -> que tasa de acierto hace falta para no perder dinero
  - ev_por_operacion   -> cuanto gana (o pierde) cada operacion, en R y en bp
  - prob_ajustada      -> que significa la probabilidad del modelo YA con costos
  - edge_neto_bp       -> el edge en puntos basicos sobre el precio

Regla de honestidad del proyecto: si el edge neto no supera 0, el modelo NO es
una estrategia, por bueno que sea su Brier. Este modulo existe para que ese
numero este siempre a la vista.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

# Binance USD-M futuros, taker por lado (referencia 2025-04: 0.05% / 0.04%).
FEE_TAKER_PCT = 0.05
FEE_MAKER_PCT = 0.02


def coste_rt_pct(fee_pct_por_lado: float, slip_pct_por_lado: float) -> float:
    """Coste de ida y vuelta en % del precio (dos lados)."""
    return 2.0 * (fee_pct_por_lado + slip_pct_por_lado)


def slippage_pct(atr_pct: float, base_pct: float = 0.01,
                 k: float = 0.25) -> float:
    """Slippage por lado: componente fija (spread) + impacto proporcional al ATR.

    k=0.25: una cuarta parte del ATR del marco como impacto conservador; si no
    hay datos de volatilidad, devuelve solo la base.
    """
    if atr_pct <= 0:
        return base_pct
    return base_pct + k * atr_pct


def prob_minima(c_rt: float) -> float:
    """Probabilidad de acierto minima para no perder dinero tras costos."""
    return (1.0 + c_rt) / 2.0


def ev_por_operacion(p: float, c_rt: float) -> float:
    """Valor esperado por operacion en unidades de R (1 = tamano del marco)."""
    return 2.0 * p - 1.0 - c_rt


def edge_neto_bp(p: float, c_rt: float, marco_pct: float) -> float:
    """Edge neto en puntos basicos de precio por operacion."""
    if marco_pct <= 0:
        raise ValueError("marco_pct debe ser > 0")
    return ev_por_operacion(p, c_rt) * marco_pct * 100.0


def prob_ajustada(p: float, c_rt: float) -> float:
    """La probabilidad tal como queda DESPUES de que los costos se cobren su
    parte: p' con el mismo EV neto que p sin costos -> p' = p - c/2."""
    return p - c_rt / 2.0


def coste_en_marco(c_rt_pct: float, marco_pct: float) -> float:
    """Convierte el coste (% del precio) a unidades del marco (R)."""
    return c_rt_pct / marco_pct


def tabla_breakeven(marcos: Sequence[float] = (0.25, 0.5, 1.0, 2.0),
                    fee_pct: float = FEE_TAKER_PCT,
                    slip_pct: float = 0.02) -> list[dict]:
    """Para cada marco: coste en R, prob minima, y prob minima 'con margen'
    (exigiendo 2x el coste como colchon, que es la practica sana)."""
    filas = []
    c_pct = coste_rt_pct(fee_pct, slip_pct)
    for m in marcos:
        c_rt = coste_en_marco(c_pct, m)
        pmin = prob_minima(c_rt)
        filas.append({
            "marco_pct": m,
            "coste_rt_pct": round(c_pct, 4),
            "coste_en_R": round(c_rt, 4),
            "prob_minima": round(pmin, 4),
            "prob_minima_colchon": round(prob_minima(2 * c_rt), 4),
        })
    return filas


def evaluar_senal(prob_modelo: float, marco_pct: float = 0.5,
                  fee_pct: float = FEE_TAKER_PCT,
                  atr_pct: float = 0.0, base_slip: float = 0.02,
                  k_slip: float = 0.25, colchon: float = 1.0) -> dict:
    """Veredicto honesto sobre una senal con probabilidad prob_modelo.

    colchon: multiplicador del coste exigido como margen de seguridad (1 = solo
    cubrir costos; 2 = practica sana).
    """
    slip = slippage_pct(atr_pct, base_slip, k_slip)
    c_pct = coste_rt_pct(fee_pct, slip)
    c_rt = coste_en_marco(c_pct, marco_pct)
    p_min = prob_minima(c_rt * colchon)
    ev = ev_por_operacion(prob_modelo, c_rt)
    return {
        "prob_modelo": round(prob_modelo, 4),
        "marco_pct": marco_pct,
        "coste_rt_pct": round(c_pct, 4),
        "slippage_pct": round(slip, 4),
        "coste_en_R": round(c_rt, 4),
        "prob_minima": round(p_min, 4),
        "ev_R": round(ev, 4),
        "edge_neto_bp": round(edge_neto_bp(prob_modelo, c_rt, marco_pct), 3),
        "prob_ajustada": round(prob_ajustada(prob_modelo, c_rt), 4),
        "viable": prob_modelo >= p_min and ev > 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--marco", type=float, default=0.5,
                    help="marco del trade en %% (0.5 = target de aguante)")
    ap.add_argument("--prob", type=float, default=0.85,
                    help="probabilidad del modelo a evaluar")
    ap.add_argument("--fee", type=float, default=FEE_TAKER_PCT,
                    help="comision por lado en %%")
    ap.add_argument("--base-rate", type=float, default=None,
                    help="tasa base observada (para el informe)")
    ap.add_argument("--json", action="store_true", help="salida JSON")
    a = ap.parse_args()

    base = a.base_rate if a.base_rate is not None else a.prob
    senal = evaluar_senal(base, a.marco, a.fee)
    brechas = tabla_breakeven(fee_pct=a.fee)

    if a.json:
        print(json.dumps({"senal": senal, "breakeven": brechas}, ensure_ascii=False))
        return 0

    print("=== MODELO DE COSTOS: de la skill al dinero ===\n")
    print(f"marco del trade        : {a.marco:.2f}% del precio")
    print(f"comision por lado      : {a.fee:.3f}%  -> ida y vuelta {senal['coste_rt_pct']:.3f}%")
    print(f"coste en unidades R    : {senal['coste_en_R']:.4f} del marco")
    print(f"probabilidad minima    : {senal['prob_minima']:.4f} para no perder dinero")
    print()
    print(f"si el modelo dice {base:.0%} -> EV {senal['ev_R']:+.4f} R por operacion "
          f"= {senal['edge_neto_bp']:+.2f} bp de precio")
    print(f"   (equivale a una prob ajustada por costos de {senal['prob_ajustada']:.4f})")
    print()
    print("=== breakeven por tamano de marco (taker, slip 0.02%/lado) ===")
    for f in brechas:
        print(f"  marco {f['marco_pct']:>4.2f}% | coste {f['coste_en_R']:>6.3f}R | "
              f"prob minima {f['prob_minima']:.3f} | con colchon x2 {f['prob_minima_colchon']:.3f}")
    print()
    if senal["viable"]:
        print("VEREDICTO: la senal cubre costos. Mientras la muestra viva no "
              "cierre (n>=100-300 efectivas), esto es PROMESA, no resultado.")
    else:
        print("VEREDICTO: la senal NO cubre costos: mas vale no operarla. "
              "Sube el marco, baja los costos (maker/limit), o consigue mas skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
