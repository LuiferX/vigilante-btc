#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""carry.py - la unica palanca estructural que no se habia medido: el CARRY.

Las 7 hipotesis anteriores buscaron PREDECIR direccion, y todas fallaron porque
el movimiento (mejor caso +0,10 %) no paga el viaje (0,23 %).

El carry es distinto: no predice nada. En perpetuos, cuando el funding es
positivo, el que está CORTO COBRA y el que está largo PAGA, cada 8 h. Con spot
comprado + perpetuo vendido (cash & carry) se cobra ese funding sin exposicion
al precio. Es la unica estructura donde el coste se INVIERTE: en vez de pagar
0,23 % por viaje, te pagan por esperar.

Este modulo mide, sobre 4,6 anos de funding real (5.000 pagos):
  - funding medio y mediano por pago (8 h) y su traduccion anual
  - cuantos pagos fueron positivos/negativos
  - el mejor y el peor ano
  - el neto tras coste de entrada/salida amortizado por dias de hold
  - la distribucion por trimestre (¿es estable o depende del regimen?)

NO opera: solo mide. Uso: python analysis/carry.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics as st
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import percentiles as pc  # noqa: E402

PAGOS_DIA = 3  # el funding se paga cada 8 h
FEE_IDA_VUELTA = 0.23  # % por entrar y salir (medido: taker + slippage)


def cargar():
    ts, vs = pc.cargar("funding")
    return [(pc.dt_ms(t), v) for t, v in zip(ts, vs)]


def peor_ventana(datos, dias):
    """Peor ventana rodante de N dias: el riesgo REAL del carry.

    No basta con la media: si la peor ventana de 90 dias fuera -5 %, la
    estructura seria inaguantable aunque la media sea +6 %.
    """
    vals = [v for _, v in datos]
    ts = [t for t, _ in datos]
    n = dias * PAGOS_DIA
    if n >= len(vals):
        return None
    ini = 0
    s = sum(vals[:n])
    peor = s
    for i in range(1, len(vals) - n + 1):
        s += vals[i + n - 1] - vals[i - 1]
        if s < peor:
            peor, ini = s, i
    return {
        "inicio": ts[ini].date().isoformat(),
        "fin": ts[ini + n - 1].date().isoformat(),
        "suma_pct": round(peor * 100, 3),
    }


def medir(holds=(7, 30, 90)):
    datos = cargar()
    vals = [v for _, v in datos]
    positivos = [v for v in vals if v > 0]
    negativos = [v for v in vals if v < 0]
    medios = sum(vals) / len(vals)
    anual = medios * PAGOS_DIA * 365 * 100  # en %

    # por ano calendario
    por_ano = {}
    for f, v in datos:
        por_ano.setdefault(f.year, []).append(v)
    anos = {
        a: {
            "n": len(v),
            "medio_pct": round(sum(v) / len(v) * 100, 4),
            "anualizado_pct": round(sum(v) / len(v) * PAGOS_DIA * 365 * 100, 2),
            "pct_pagos_positivos": round(100.0 * sum(1 for x in v if x > 0) / len(v), 1),
        }
        for a, v in sorted(por_ano.items())
        if len(v) > 100
    }

    # neto por hold (el coste de entrada/salida se amortiza en los dias)
    netos = {}
    for h in holds:
        bruto = medios * PAGOS_DIA * h * 100
        coste = FEE_IDA_VUELTA
        netos[f"{h}d"] = {
            "bruto_pct": round(bruto, 3),
            "coste_pct": coste,
            "neto_pct": round(bruto - coste, 3),
            "anualizado_neto_pct": round((bruto - coste) * 365 / h, 2),
        }

    # riesgo: peores ventanas rodantes y meses negativos (la media no basta)
    por_mes = {}
    for f, v in datos:
        por_mes.setdefault((f.year, f.month), []).append(v)
    meses = sorted(sum(v) for v in por_mes.values())
    riesgo = {
        "peor_7d": peor_ventana(datos, 7),
        "peor_30d": peor_ventana(datos, 30),
        "peor_90d": peor_ventana(datos, 90),
        "meses_negativos": sum(1 for m in meses if m < 0),
        "meses_totales": len(meses),
        "peor_mes_pct": round(meses[0] * 100, 3) if meses else None,
        "mejor_mes_pct": round(meses[-1] * 100, 3) if meses else None,
        "mediana_mes_pct": round(meses[len(meses) // 2] * 100, 3) if meses else None,
    }

    return {
        "pagos": len(vals),
        "desde": datos[0][0].isoformat(),
        "hasta": datos[-1][0].isoformat(),
        "funding_medio_por_pago_pct": round(medios * 100, 5),
        "funding_mediano_por_pago_pct": round(st.median(vals) * 100, 5),
        "anualizado_bruto_pct": round(anual, 2),
        "pct_pagos_positivos": round(100.0 * len(positivos) / len(vals), 1),
        "pagos_positivos": len(positivos),
        "pagos_negativos": len(negativos),
        "mejor_pago_pct": round(max(vals) * 100, 4),
        "peor_pago_pct": round(min(vals) * 100, 4),
        "por_ano": anos,
        "neto_por_hold": netos,
        "riesgo": riesgo,
    }


def redactar(m: dict) -> str:
    L = []
    L.append("# Carry del perpetuos BTCUSDT — 4,6 años de funding real")
    L.append("")
    L.append(f"{m['pagos']} pagos · {m['desde'][:10]} → {m['hasta'][:10]}")
    L.append("")
    L.append("| Métrica | Valor |")
    L.append("|---|---:|")
    L.append(f"| Funding medio por pago (8 h) | {m['funding_medio_por_pago_pct']:.5f} % |")
    L.append(f"| Funding **mediano** por pago | {m['funding_mediano_por_pago_pct']:.5f} % |")
    L.append(f"| **Anualizado bruto** (cash & carry) | **{m['anualizado_bruto_pct']:.2f} %** |")
    L.append(f"| Pagos positivos (cobra el corto) | {m['pct_pagos_positivos']:.1f} % |")
    L.append(f"| Mejor pago | {m['mejor_pago_pct']:.4f} % |")
    L.append(f"| Peor pago | {m['peor_pago_pct']:.4f} % |")
    L.append("")
    L.append("## Por año (¿es estable o depende del régimen?)")
    L.append("")
    L.append("| Año | Pagos | Anualizado | % pagos positivos |")
    L.append("|---|---:|---:|---:|")
    for a, d in m["por_ano"].items():
        L.append(
            f"| {a} | {d['n']} | {d['anualizado_pct']:+.2f} % | "
            f"{d['pct_pagos_positivos']:.1f} % |"
        )
    L.append("")
    L.append("## Neto tras coste de entrada/salida")
    L.append("")
    L.append(
        "El coste (0,23 % ida y vuelta) se amortiza entre los días que " "aguantes la posición:"
    )
    L.append("")
    L.append("| Hold | Bruto | Coste | **Neto** | Anualizado neto |")
    L.append("|---|---:|---:|---:|---:|")
    for h, d in m["neto_por_hold"].items():
        L.append(
            f"| {h} | {d['bruto_pct']:.3f} % | {d['coste_pct']:.2f} % | "
            f"**{d['neto_pct']:+.3f} %** | {d['anualizado_neto_pct']:+.2f} % |"
        )
    L.append("")
    r = m.get("riesgo") or {}
    if r.get("peor_30d"):
        L.append("## 4. Riesgo real (la media no basta)")
        L.append("")
        L.append(
            "La peor ventana rodante fue **{:+.3f} %** a 7 días ({} → {}), "
            "**{:+.3f} %** a 30 días y **{:+.3f} %** a 90 días. Meses negativos: "
            "{} de {} ({:.0f} %). Peor mes {:+.3f} %, mediana {:+.3f} %.".format(
                r["peor_7d"]["suma_pct"],
                r["peor_7d"]["inicio"],
                r["peor_7d"]["fin"],
                r["peor_30d"]["suma_pct"],
                r["peor_90d"]["suma_pct"],
                r["meses_negativos"],
                r["meses_totales"],
                100.0 * r["meses_negativos"] / max(1, r["meses_totales"]),
                r["peor_mes_pct"],
                r["mediana_mes_pct"],
            )
        )
        L.append("")
    L.append("---")
    L.append("")
    L.append(
        "**Qué es esto:** comprar spot BTC + vender el perpetuo (mismo "
        "tamaño). Cobrás el funding cada 8 h sin exposición al precio. "
        "**Qué no es:** una señal. No predice nada."
    )
    L.append("")
    L.append(
        "**Riesgos reales (declarados):** el funding puede pasar a "
        "negativo y entonces *pagás* por estar corto; el basis se mueve; "
        "necesitás mantener el hedge (margen, riesgo de liquidación del "
        "perp); y en un exchange real hay costes de transferencia y "
        "límites. Es una estructura de meses, no de minutos."
    )
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    m = medir()
    md = redactar(m)
    pj = os.path.join(AQUI, "data", "carry.json")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=2)
    pm = os.path.join(AQUI, "data", "carry.md")
    with open(pm, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    print(f"OK -> {pj} y {pm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
