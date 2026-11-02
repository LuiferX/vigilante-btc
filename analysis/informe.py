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
except ImportError:  # pragma: no cover
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
        filas.append(
            {
                "serie": nombre,
                "valor": round(c["valor"], 6),
                "percentil": c["percentil"],
                "lectura": r["lectura"],
                "n_ventana": c["n_ventana"],
                "ventana_dias": vd,
                "cobertura_dias": r["cobertura_dias"],
            }
        )
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
        "validation": (
            {
                "corte": val.get("checked_at") if isinstance(val, dict) else None,
                "muestras_efectivas": (val.get("samples", {}) or {}).get("effective"),
                "skill_oos": (val.get("oos", {}) or {}).get("brier_skill"),
                "ece": (val.get("oos", {}) or {}).get("ece"),
                "psi": (val.get("drift", {}) or {}).get("psi"),
                "gate": gate.get("canal"),
                "estado": val.get("status"),
            }
            if val
            else None
        ),
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
    L.append(f"# Informe de inteligencia â€” {ah[:16].replace('T', ' ')} UTC")
    L.append("")
    L.append(
        "> Este informe **no opera**: mide y publica. No contiene objetivos, "
        "stops ni planes de entrada."
    )
    L.append("")

    pos = rep["bloques"]["posicionamiento"]
    if pos:
        L.append("## 1. Posicionamiento (percentil causal, sin look-ahead)")
        L.append("")
        L.append("| Serie | Valor | Percentil | Lectura | Obs | Ventana |")
        L.append("|---|---:|---:|---|---:|---:|")
        for r in pos:
            L.append(
                f"| {r['serie']} | {r['valor']:.6g} | "
                f"{r['percentil'] * 100:.1f} % | {r['lectura']} | "
                f"{r['n_ventana']} | {r['ventana_dias']} d |"
            )
        L.append("")
        # Artefacto conocido y declarado: la tasa por defecto de Binance
        # (+0.0001) agrupa ~27% de los pagos, asi que cuando el ultimo pago es
        # el default el percentil marca 100 sin que sea un extremo real.
        L.append(
            "> **Caveat honesto:** cuando el Ãºltimo pago de funding es "
            "exactamente la tasa por defecto (+0,0001, que agrupa ~27 % de "
            "los pagos), el percentil marca 100 % **sin que sea un extremo "
            "real**. Es un empate masivo, no una seÃ±al. El motor ya "
            "descuenta esto en la investigaciÃ³n (H1); aquÃ­ se declara para "
            "que no se lea como 'funding en mÃ¡ximos'."
        )
        L.append("")
        # lo que el ojo no ve
        oi = next((r for r in pos if r["serie"] == "oi"), None)
        oiv = next((r for r in pos if r["serie"] == "oi_valor"), None)
        if oi and oiv:
            L.append(
                f"**Lectura cruzada:** el OI en contratos estÃ¡ en el "
                f"percentil {oi['percentil'] * 100:.0f}, pero el OI **en "
                f"dÃ³lares** en el {oiv['percentil'] * 100:.0f}. Si el "
                f"primero es alto y el segundo bajo, hay el mismo "
                f"interÃ©s abierto sobre un precio menor: apalancamiento "
                f"mÃ¡s frÃ¡gil, no mÃ¡s grande."
            )
            L.append("")

    L.extend(seccion_niveles_hist(rep))
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
        L.append(
            f"- Skill OOS: {v.get('skill_oos')} Â· ECE {v.get('ece')} Â· " f"PSI {v.get('psi')}"
        )
        L.append(f"- Gate: `{v.get('gate')}` Â· estado `{v.get('estado')}`")
        L.append("")

    L.append("---")
    L.append("")
    L.append(
        "Marcador de edge (veredicto de la investigaciÃ³n, no opiniÃ³n): "
        "en este marco (velas 5 m, hold 4-72 h, coste ~0,2 % por viaje) "
        "**no hay edge direccional demostrado** en ninguna de las seis "
        "familias medidas â€” H1 funding, H3 rebote afinado, H4 entrada "
        "rediseÃ±ada, H5 ruptura, H6 horizontes largos. Detalle y datos en "
        "`analysis/EXPERIMENTOS.md` y `docs/audit/`."
    )
    L.append("")
    return "\n".join(L)


def bloque_niveles_hist() -> dict | None:
    """Suelos/techos HISTORICOS: 4 anos de velas, no la ventana de 14.

    Devuelve el corte mas reciente de niveles_hist.json, o None si no existe.
    """
    p = os.path.join(DATA, "niveles_hist.json")
    d = leer_json(p)
    if not isinstance(d, dict) or not (d.get("cerca") or d.get("global")):
        return None
    return {
        "generado": d.get("generado"),
        "historia": d.get("historia"),
        "precio": d.get("precio"),
        "cerca": (d.get("cerca") or [])[:5],
        "global": (d.get("global") or [])[:5],
    }


def seccion_niveles_hist(rep: dict) -> list[str]:
    b = rep["bloques"].get("niveles_hist")
    if not b:
        return []
    h = b.get("historia") or {}
    L = []
    L.append("## 4. Estructura histÃ³rica (4 aÃ±os de velas 5m)")
    L.append("")
    L.append(
        f"Historia medida: **{h.get('velas')} velas**, "
        f"{(h.get('desde') or '')[:10]} â†’ {(h.get('hasta') or '')[:10]}."
        f" Un *toque* es una visita distinta (entra, sale 0,3 % y vuelve "
        f"â‰¥1 h despuÃ©s); *aguanta* = ningÃºn cierre 0,5 % mÃ¡s allÃ¡ en 4 h "
        f"(el target del modelo)."
    )
    L.append("")
    cerca = b.get("cerca") or []
    if cerca:
        L.append("### Cerca del precio (los que de verdad importan hoy)")
        L.append("")
        L.append("| Nivel | Lado | Toques 4a | Aguanta | Rebote med. | Barrido med. | Distancia |")
        L.append("|---|---|---:|---:|---:|---:|---:|")
        for f in cerca:
            L.append(
                "| {:,.0f} | {} | {} | {:.1f} % | {:.3f} % | {:.3f} % | "
                "{:+.2f} % |".format(
                    f["nivel"],
                    f.get("lado", "-"),
                    f["toques"],
                    f["aguante_pct"],
                    f.get("rebote_mediano_pct") or 0,
                    f.get("barrido_mediano_pct") or 0,
                    f.get("distancia_pct") or 0,
                )
            )
        L.append("")
    glob = b.get("global") or []
    if glob:
        L.append("### Los mÃ¡s respetados de la historia")
        L.append("")
        L.append("| Nivel | Toques | Aguanta | Rebote | Barrido | Distancia |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for f in glob:
            L.append(
                "| {:,.0f} | {} | {:.1f} % | {:.3f} % | {:.3f} % | "
                "{:+.1f} % |".format(
                    f["nivel"],
                    f["toques"],
                    f["aguante_pct"],
                    f.get("rebote_mediano_pct") or 0,
                    f.get("barrido_mediano_pct") or 0,
                    f.get("distancia_pct") or 0,
                )
            )
        L.append("")
        # la lectura honesta que sacan los datos
        sim = [f for f in glob if f.get("rebote_mediano_pct") and f.get("barrido_mediano_pct")]
        if sim:
            L.append(
                "**Lectura honesta:** en los niveles mÃ¡s probados, el "
                "rebote mediano y el barrido mediano son casi iguales "
                "({:.3f} % vs {:.3f} %). Las excursiones a ambos lados del "
                "nivel son simÃ©tricas: el precio no *respeta* estos niveles "
                "tanto como los atraviesa. Es la firma matemÃ¡tica de por "
                "quÃ© la investigaciÃ³n no encontrÃ³ edge aquÃ­.".format(
                    sum(f["rebote_mediano_pct"] for f in sim) / len(sim),
                    sum(f["barrido_mediano_pct"] for f in sim) / len(sim),
                )
            )
            L.append("")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-imprimir", action="store_true")
    a = ap.parse_args()

    rep = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "bloques": {
            "posicionamiento": bloque_posicionamiento(),
            "sistema": bloque_sistema(),
            "niveles_hist": bloque_niveles_hist(),
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
