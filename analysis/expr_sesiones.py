#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""expr_sesiones.py - H7: sesiones y rango asiatico (Tokio/Londres/NY).

Pre-registro: analysis/EXPERIMENTOS.md, seccion "H7 - SESIONES y RANGO
ASIATICO" (commiteado ANTES de correr esto).

Dos partes, separadas a proposito:

  A) DESCRIPTIVO (no es una senal): perfil de cada sesion sobre 4 anos
     (rango mediano, cuerpo mediano, cuantas veces hace el maximo/minimo del
     dia) y distribucion del tamano del rango asiatico.

  B) EXPERIMENTO (con criterio de muerte): la sesion de Londres barre el
     extremo del rango asiatico >= 0,03% y vuelve a meterse dentro; se mide si
     el lado de la REVERSION o el del control (continuacion) pagan el peaje.

Infraestructura compartida: analysis/laboratorio.py (costes, bootstrap,
maquina de independencia, evaluacion, veredicto).

Reglas duras:
  - El rango asiatico solo se usa con la sesion Asia CERRADA (cero look-ahead).
  - La entrada es el open de la vela siguiente a la que CONFIRMA el barrido.
  - Costes siempre. Un trade a la vez + cooldown 1 h.
  - El resultado negativo se publica igual.

stdlib puro. Uso: python analysis/expr_sesiones.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from laboratorio import (  # noqa: E402
    atr_pct,
    cargar_klines,
    coste_viaje,
    evaluar,
    motor_secuencia,
    veredicto,
)

# ---- parametros del pre-registro (no se tocan tras ver resultados) ----
MIN_BARRIDO = 0.0003  # 0,03%: mecha minima sobre el extremo asiatico
VENTANA_CONF = 6  # 30 min para cerrar de vuelta dentro del rango
HORIZONTES = {"1h": 12, "2h": 24, "4h": 48}
DIRECCIONES = ["reversion", "control"]
COOLDOWN_H = 1
SEMILLA = 42

# limites de sesion en horas UTC (coinciden con vigilante/indicadores.py)
ASIA = (0.0, 8.0)
LONDRES = (8.0, 13.5)


def hora(vela) -> float:
    return vela["t"].hour + vela["t"].minute / 60.0


def en_sesion(vela, rango) -> bool:
    return rango[0] <= hora(vela) < rango[1]


def dia(vela) -> datetime.date:
    return vela["t"].date()


# ----------------------------------------------------------- descriptivo --
def perfil_sesiones(kl: list[dict]) -> dict:
    """Perfil por sesion + quien hace el maximo/minimo del dia.

    Puramente descriptivo: no hay direccion ni expectativa.
    """
    ses = {}
    for v in kl:
        h = hora(v)
        if h < 8:
            nombre = "Asia"
        elif h < 13.5:
            nombre = "Londres"
        elif h < 16.5:
            nombre = "solape"
        elif h < 21:
            nombre = "NY"
        else:
            nombre = "noche"
        d = ses.setdefault(nombre, {"rangos": [], "cuerpos": []})
        rango = (v["h"] - v["l"]) / v["c"] * 100
        cuerpo = abs(v["c"] - v["o"]) / v["c"] * 100
        d["rangos"].append(rango)
        d["cuerpos"].append(cuerpo)

    # maximo/minimo del dia: en que sesion cae
    por_dia: dict = {}
    for v in kl:
        d = por_dia.setdefault(dia(v), {"h": v["h"], "l": v["l"], "quien_h": 0, "quien_l": 0})
        if v["h"] >= d["h"]:
            d["h"] = v["h"]
            d["quien_h"] = int(hora(v))
        if v["l"] <= d["l"]:
            d["l"] = v["l"]
            d["quien_l"] = int(hora(v))

    def bucket_h(h):
        if h < 8:
            return "Asia"
        if h < 13.5:
            return "Londres"
        if h < 16.5:
            return "solape"
        if h < 21:
            return "NY"
        return "noche"

    cuenta_h, cuenta_l = {}, {}
    for d in por_dia.values():
        b = bucket_h(d["quien_h"])
        cuenta_h[b] = cuenta_h.get(b, 0) + 1
        b = bucket_h(d["quien_l"])
        cuenta_l[b] = cuenta_l.get(b, 0) + 1
    n_dias = max(1, len(por_dia))

    out = {}
    for nombre, d in sorted(ses.items()):
        r = sorted(d["rangos"])
        c = sorted(d["cuerpos"])
        out[nombre] = {
            "n": len(r),
            "rango_mediano_pct": round(r[len(r) // 2], 4),
            "rango_p90_pct": round(r[int(len(r) * 0.9)], 4),
            "cuerpo_mediano_pct": round(c[len(c) // 2], 4),
            "hace_max_del_dia_pct": round(100.0 * cuenta_h.get(nombre, 0) / n_dias, 1),
            "hace_min_del_dia_pct": round(100.0 * cuenta_l.get(nombre, 0) / n_dias, 1),
        }
    return out


def rangos_asiaticos(kl: list[dict]) -> list[dict]:
    """Un registro por dia UTC con el rango completo de la sesion Asia.

    Solo se devuelve si la sesion Asia tiene velas suficientes (evita dias
    incompletos al principio o al final de la historia).
    """
    por_dia: dict = {}
    for v in kl:
        if not en_sesion(v, ASIA):
            continue
        d = por_dia.setdefault(dia(v), {"h": v["h"], "l": v["l"], "n": 0, "fin": v["t"]})
        d["h"] = max(d["h"], v["h"])
        d["l"] = min(d["l"], v["l"])
        d["n"] += 1
        d["fin"] = max(d["fin"], v["t"])
    # 8h = 96 velas de 5m; se pide >=90 para no usar dias con huecos
    return [
        {"fecha": f, "high": d["h"], "low": d["l"], "n": d["n"], "fin_asia": d["fin"]}
        for f, d in sorted(por_dia.items())
        if d["n"] >= 90
    ]


# ------------------------------------------------------------- el evento --
def eventos_barrido(kl: list[dict], rangs: list[dict]) -> list[dict]:
    """Eventos de barrido del rango asiatico por Londres, con confirmacion.

    Devuelve uno por dia: {fecha, lado (alto|bajo), idx_confirma, ...}. Si
    Londres no barre o no confirma, ese dia no aporta evento.
    """
    tiempos = [v["t"] for v in kl]
    eventos = []
    for r in rangs:
        i0 = tiempos.index(r["fin_asia"]) + 1 if r["fin_asia"] in tiempos else None
        if i0 is None:
            continue
        # buscar la primera mecha que supere el extremo, dentro de Londres
        i = i0
        barrido = None
        while i < len(kl) and en_sesion(kl[i], LONDRES):
            v = kl[i]
            if v["h"] > r["high"] * (1 + MIN_BARRIDO):
                barrido = ("alto", i)
                break
            if v["l"] < r["low"] * (1 - MIN_BARRIDO):
                barrido = ("bajo", i)
                break
            i += 1
        if barrido is None:
            continue
        lado, i_b = barrido
        # confirmacion: cierre de vuelta DENTRO del rango, en <=6 velas
        extremo = r["high"] if lado == "alto" else r["low"]
        i_conf = None
        for k in range(i_b + 1, min(i_b + 1 + VENTANA_CONF, len(kl))):
            c = kl[k]["c"]
            dentro = (c < extremo) if lado == "alto" else (c > extremo)
            if dentro:
                i_conf = k
                break
        if i_conf is None:
            continue
        eventos.append(
            {
                "fecha": r["fecha"],
                "lado": lado,
                "t": kl[i_conf]["t"].isoformat(),
                "idx_barrido": i_b,
                "idx_confirma": i_conf,
                "high_asia": r["high"],
                "low_asia": r["low"],
                "mecha": (kl[i_b]["h"] if lado == "alto" else kl[i_b]["l"]),
            }
        )
    return eventos


def resolver_barrido(kl, direccion, barras):
    """Resolver de una celda: entra tras la confirmacion y sale a `barras`.

    La direccion depende del lado del barrido:
      barrido ALTO  -> reversion = CORTO, control (continuacion) = LARGO
      barrido BAJO  -> reversion = LARGO, control = CORTO
    """

    def resolver(muestra):
        i = muestra["idx_confirma"]
        j = i + 1  # entrada: open de la vela siguiente
        if j + barras >= len(kl):
            return None
        entrada = kl[j]["o"]
        sube = muestra["lado"] == "alto"
        largo = (not sube) if direccion == "reversion" else sube
        atrp = atr_pct(kl, j) or 0.05
        coste = coste_viaje(atrp)
        k = j + barras
        salida = kl[k]["c"]
        if largo:
            bruto = (salida - entrada) / entrada * 100.0
        else:
            bruto = (entrada - salida) / entrada * 100.0
        return {
            "neto": bruto - coste,
            "bruto": bruto,
            "coste": coste,
            "t": kl[j]["t"],
            "atr_pct": atrp,
            "largo": largo,
            "vol": muestra.get("vol"),
            "hold_barras": barras,
        }

    return resolver


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-descriptivo", action="store_true")
    a = ap.parse_args()

    kl = cargar_klines()
    print(f"velas: {len(kl)} | {kl[0]['t']:%Y-%m-%d} -> {kl[-1]['t']:%Y-%m-%d}")

    # ---------- A) descriptivo ----------
    perfil = perfil_sesiones(kl)
    print("\n=== A) Perfil por sesion (descriptivo, no es senal) ===")
    print(
        f"{'sesion':8s} {'n':>8s} {'rango med':>10s} {'rango p90':>10s} "
        f"{'cuerpo':>8s} {'max dia':>8s} {'min dia':>8s}"
    )
    for nombre, d in perfil.items():
        print(
            f"{nombre:8s} {d['n']:>8d} {d['rango_mediano_pct']:>9.3f}% "
            f"{d['rango_p90_pct']:>9.3f}% {d['cuerpo_mediano_pct']:>7.3f}% "
            f"{d['hace_max_del_dia_pct']:>7.1f}% {d['hace_min_del_dia_pct']:>7.1f}%"
        )

    rangs = rangos_asiaticos(kl)
    tamanos = sorted((r["high"] - r["low"]) / r["low"] * 100 for r in rangs)
    asia = {
        "dias": len(rangs),
        "rango_mediano_pct": round(tamanos[len(tamanos) // 2], 4) if tamanos else None,
        "rango_p25_pct": round(tamanos[len(tamanos) // 4], 4) if tamanos else None,
        "rango_p75_pct": round(tamanos[int(len(tamanos) * 0.75)], 4) if tamanos else None,
    }
    print(
        f"\nRango asiatico (00-08 UTC): {asia['dias']} dias | mediana "
        f"{asia['rango_mediano_pct']}% | p25 {asia['rango_p25_pct']}% | "
        f"p75 {asia['rango_p75_pct']}%"
    )

    if a.solo_descriptivo:
        return 0

    # ---------- B) experimento ----------
    evs = eventos_barrido(kl, rangs)
    print("\n=== B) Barridos de Londres sobre el rango asiatico ===")
    print(
        f"eventos con barrido + confirmacion: {len(evs)} "
        f"({len(evs) / max(1, asia['dias']) * 100:.1f}% de los dias)"
    )
    altos = sum(1 for e in evs if e["lado"] == "alto")
    print(f"  por lado: {altos} altos / {len(evs) - altos} bajos")

    celdas = {}
    for direccion in DIRECCIONES:
        for hnombre, barras in HORIZONTES.items():
            muestras = [dict(e, barras=barras, vol=None) for e in evs]
            rets, detalle = motor_secuencia(
                muestras,
                resolver_barrido(kl, direccion, barras),
                conviccion="todas",
                cooldown_h=COOLDOWN_H,
                hold_fn=lambda r: r["hold_barras"],
            )
            if not rets:
                continue
            c = evaluar(rets, detalle)
            x2 = round(sum(d["neto"] - d["coste"] for d in detalle) / len(detalle), 4)
            celdas[f"{direccion}:{hnombre}"] = {"resumen": c, "x2": x2}
            print(
                f"  {direccion:10s} {hnombre:3s} n={c['n']:4d} "
                f"neta={c['media']:+.4f}% ic95=[{c['ic95'][0]:+.4f},"
                f"{c['ic95'][1]:+.4f}] hit={c['hit_rate']:.2f} "
                f"-> {veredicto(c, x2)}"
            )

    ps = [v["resumen"]["p_boot"] for v in celdas.values()]
    p_corr = min(1.0, min(ps) * len(ps)) if ps else 1.0
    veredictos = {k: veredicto(v["resumen"], v["x2"]) for k, v in celdas.items()}

    out = {
        "hipotesis": "H7",
        "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "parametros": {
            "min_barrido": MIN_BARRIDO,
            "ventana_conf": VENTANA_CONF,
            "horizontes": list(HORIZONTES),
            "direcciones": DIRECCIONES,
            "cooldown_h": COOLDOWN_H,
            "bootstrap": 10000,
            "semilla": SEMILLA,
            "velas": len(kl),
        },
        "descriptivo": {"perfil_sesiones": perfil, "rango_asiatico": asia},
        "eventos": {"n": len(evs), "altos": altos, "bajos": len(evs) - altos},
        "variantes_probadas": len(ps),
        "p_corregido": round(p_corr, 5),
        "celdas": {
            k: dict(v["resumen"], x2=v["x2"], veredicto=veredictos[k]) for k, v in celdas.items()
        },
        "veredicto": "sin_edge",
    }
    if any(v == "edge" for v in veredictos.values()):
        out["veredicto"] = "edge"
    p = os.path.join(AQUI, "data", "edge_sesiones.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\np_corregido (Bonferroni {len(ps)} celdas): {p_corr:.5f}")
    print(f"veredicto global: {out['veredicto']}")
    print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
