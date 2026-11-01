#!/usr/bin/env python3
"""
informe.py - INFORME DE INTELIGENCIA: lo que la maquina de analisis ve.

REARME 2026-11-01: el repo dejo de operar. Este modulo es la salida principal:
junta lo medido (percentiles, archivo de microestructura, veredicto del analisis
vivo) y escribe UN informe legible + uno maquina-legible. No propone entradas,
no ejecuta nada: informa.

Bloques:
  1. Posicionamiento   - percentiles de funding/OI/taker/ballenas
  2. Estructura        - niveles activos y su distancia al precio
  3. Regimen           - volatilidad, sesion, sesgo
  4. Marcador de edge  - el veredicto de la investigacion (H1..H6), sin adornos
  5. Estado del sistema- cobertura de datos, salud, workflows

Uso:
    python analysis/informe.py                 # escribe data/informe.json + .md
    python analysis/informe.py --solo-imprimir
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(AQUI, "data")
PCT_HOY = os.path.join(DATA, "percentiles_hoy.json")
VALIDACION = os.path.join(DATA, "validation.json")

sys.path.insert(0, AQUI)
try:
    import percentiles as pc  # noqa: E402
except ImportError:                                    # pragma: no cover
    pc = None


def leer_json(p: str, por_defecto=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return por_defecto


# ------------------------------------------------------- 1) posicionamiento --
def bloque_posicionamiento() -> list[dict]:
    if pc is None:
        return []
    if not os.path.exists(os.path.join(pc.ARCHIVO, "funding.jsonl")):
        return []
    filas = []
    for nombre in sorted(pc.SERIES):
        vd = 30 if nombre != "funding" else 400
        try:
            r = pc.estado_serie(nombre, vd)
        except Exception:
            continue
        if not r:
            continue
        c = r["corte"]
        filas.append({
            "serie": nombre,
            "valor": round(c["valor"], 6),
            "percentil": c["percentil"],
            "lectura": r["lectura"],
            "n_ventana": c["n_ventana"],
            "ventana_dias": vd,
            "cobertura_dias": r["cobertura_dias"],
        })
    return filas


# ---------------------------------------------------------- 5) del sistema --
def bloque_sistema() -> dict:
    arch = os.path.join(AQUI, "data", "archivo")
    series = {}
    if os.path.isdir(arch):
        for f in sorted(os.listdir(arch)):
            if not f.endswith(".jsonl"):
                continue
            n = min_conteo(os.path.join(arch, f))
            series[f[:-6]] = {"filas": n}
    val = leer_json(VALIDACION, {})
    gate = val.get("gate", {}) if isinstance(val, dict) else {}
    return {
        "archivo": series,
        "validation": {
            "corte": val.get("checked_at") if isinstance(val, dict) else None,
            "muestras_efectivas": (val.get("samples", {}) or {}).get("effective"),
            "skill_oos": (val.get("oos", {}) or {}).get("brier_skill"),
            "ece": (val.get("oos", {}) or {}).get("ece"),
            "psi": (val.get("drift", {}) or {}).get("psi"),
            "gate": gate.get("canal"),
            "estado": val.get("status"),
        } if val else None,
    }


def min_conteo(p: str, limite: int = 200000) -> int:
    n = 0
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for _ in fh:
                n += 1
                if n >= limite:
                    return n
    except Exception:
        return -1
    return n


# --------------------------------------------------------- redaccion (md) --
def redactar(rep: dict) -> str:
    L = []
    ah = rep["generado"]
    L.append(f"# Informe de inteligencia — {ah[:16].replace('T', ' ')} UTC")
    L.append("")
    L.append("> Este informe **no opera**: mide y publica. No contiene objetivos, "
             "stops ni planes de entrada.")
    L.append("")

    pos = rep["bloques"]["posicionamiento"]
    if pos:
        L.append("## 1. Posicionamiento (percentil causal, sin look-ahead)")
        L.append("")
        L.append("| Serie | Valor | Percentil | Lectura | Obs | Ventana |")
        L.append("|---|---:|---:|---|---:|---:|")
        for r in pos:
            L.append(f"| {r['serie']} | {r['valor']:.6g} | "
                     f"{r['percentil'] * 100:.1f} % | {r['lectura']} | "
                     f"{r['n_ventana']} | {r['ventana_dias']} d |")
        L.append("")
        # Artefacto conocido y declarado: la tasa por defecto de Binance
        # (+0.0001) agrupa ~27% de los pagos, asi que cuando el ultimo pago es
        # el default el percentil marca 100 sin que sea un extremo real.
        L.append("> **Caveat honesto:** cuando el último pago de funding es "
                 "exactamente la tasa por defecto (+0,0001, que agrupa ~27 % de "
                 "los pagos), el percentil marca 100 % **sin que sea un extremo "
                 "real**. Es un empate masivo, no una señal. El motor ya "
                 "descuenta esto en la investigación (H1); aquí se declara para "
                 "que no se lea como 'funding en máximos'.")
        L.append("")
        # lo que el ojo no ve
        oi = next((r for r in pos if r["serie"] == "oi"), None)
        oiv = next((r for r in pos if r["serie"] == "oi_valor"), None)
        if oi and oiv:
            L.append(f"**Lectura cruzada:** el OI en contratos está en el "
                     f"percentil {oi['percentil'] * 100:.0f}, pero el OI **en "
                     f"dólares** en el {oiv['percentil'] * 100:.0f}. Si el "
                     f"primero es alto y el segundo bajo, hay el mismo "
                     f"interés abierto sobre un precio menor: apalancamiento "
                     f"más frágil, no más grande.")
            L.append("")

    L.append("## 5. Estado del sistema")
    L.append("")
    s = rep["bloques"]["sistema"]
    if s.get("archivo"):
        L.append("| Archivo | Filas |")
        L.append("|---|---:|")
        for k, v in s["archivo"].items():
            L.append(f"| {k} | {v['filas']} |")
        L.append("")
    v = s.get("validation")
    if v:
        L.append(f"- Muestra efectiva: **{v.get('muestras_efectivas')}**")
        L.append(f"- Skill OOS: {v.get('skill_oos')} · ECE {v.get('ece')} · "
                 f"PSI {v.get('psi')}")
        L.append(f"- Gate: `{v.get('gate')}` · estado `{v.get('estado')}`")
        L.append("")

    L.append("---")
    L.append("")
    L.append("Marcador de edge (veredicto de la investigación, no opinión): "
             "en este marco (velas 5 m, hold 4-72 h, coste ~0,2 % por viaje) "
             "**no hay edge direccional demostrado** en ninguna de las seis "
             "familias medidas — H1 funding, H3 rebote afinado, H4 entrada "
             "rediseñada, H5 ruptura, H6 horizontes largos. Detalle y datos en "
             "`analysis/EXPERIMENTOS.md` y `docs/audit/`.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-imprimir", action="store_true")
    a = ap.parse_args()

    rep = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "bloques": {
            "posicionamiento": bloque_posicionamiento(),
            "sistema": bloque_sistema(),
        },
    }
    # marcador corto para el informe
    pos = rep["bloques"]["posicionamiento"]
    rep["resumen"] = {
        "percentil_max": max((r["percentil"] for r in pos), default=None),
        "percentil_min": min((r["percentil"] for r in pos), default=None),
        "series": len(pos),
    }

    md = redactar(rep)
    if a.solo_imprimir:
        print(md)
        return 0
    pj = os.path.join(DATA, "informe.json")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    # el .md se publica tal cual (la UI de Pages puede servirlo)
    pmd = os.path.join(DATA, "informe.md")
    with open(pmd, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md[:1400])
    print(f"\nOK -> {pj} y {pmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
