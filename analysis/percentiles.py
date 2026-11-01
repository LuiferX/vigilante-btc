#!/usr/bin/env python3
"""
percentiles.py - percentiles CAUSALES sobre series largas de mercado.

La pieza que da la precision: en vez de "el funding esta alto", dice
"el funding esta en el percentil 96 de 1.399 dias". Cero look-ahead: cada
percentil se calcula SOLO con observaciones anteriores al instante consultado.

Regla de oro del rearme (2026-11-01): esta pieza NO opera. Mide y publica.

Uso:
    python analysis/percentiles.py --serie funding --dias 400
    python analysis/percentiles.py --serie oi --dias 30
    python analysis/percentiles.py --todo
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import os

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(AQUI, "data", "archivo")

# serie -> (archivo, campo de tiempo, campo de valor)
SERIES = {
    "funding": ("funding.jsonl", "fundingTime", "fundingRate"),
    "oi": ("oi.jsonl", "timestamp", "sumOpenInterest"),
    "oi_valor": ("oi.jsonl", "timestamp", "sumOpenInterestValue"),
    "taker": ("taker.jsonl", "timestamp", "buySellRatio"),
    "top_cuentas": ("top_cuentas.jsonl", "timestamp", "longShortRatio"),
    "top_posiciones": ("top_posiciones.jsonl", "timestamp", "longShortRatio"),
    "global_cuentas": ("global_cuentas.jsonl", "timestamp", "longShortRatio"),
}


def cargar(nombre: str, incluir_alternas: bool = False) -> tuple[list[int], list[float]]:
    """Devuelve (timestamps, valores) ordenados. Castea a float sin fallar.

    Por defecto solo usa la fuente primaria (`binance_*`): las fuentes
    alternativas (OKX/Bybit, que se usan cuando Binance bloquea con 451) miden
    en otra escala (el OI de OKX viene en dolares, el de Binance en contratos)
    y mezclarlas corromperia el percentil. Se piden explicitamente con
    `incluir_alternas=True`.
    """
    archivo, campo_t, campo_v = SERIES[nombre]
    p = os.path.join(ARCHIVO, archivo)
    ts: list[int] = []
    vs: list[float] = []
    with open(p, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                r = json.loads(linea)
            except Exception:
                continue
            if not incluir_alternas:
                src = r.get("source")
                # solo se descartan las filas que declaran una fuente NO primaria;
                # las legacy (sin etiqueta) se mantienen
                if src is not None and not str(src).startswith("binance"):
                    continue
            t = r.get(campo_t)
            v = r.get(campo_v)
            if t is None or v is None:
                continue
            try:
                vs.append(float(v))
            except (TypeError, ValueError):
                continue
            ts.append(int(t))
    pares = sorted(zip(ts, vs))
    return [p[0] for p in pares], [p[1] for p in pares]


def dt_ms(v) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(v) / 1000, tz=UTC)


def percentil_causal(ts: list[int], vs: list[float], t_ref: int,
                      ventana: datetime.timedelta) -> dict | None:
    """Percentil de `t_ref` DENTRO de su ventana trailing causal.

    Solo mira observaciones en [t_ref - ventana, t_ref]. Devuelve el valor, su
    percentil dentro de esa ventana, cuantas obs lo respaldan y el rango.
    """
    i = bisect.bisect_right(ts, t_ref)
    if i == 0:
        return None
    t0 = t_ref - int(ventana.total_seconds() * 1000)
    i0 = bisect.bisect_left(ts, t0)
    ventana_vals = vs[i0:i]
    n = len(ventana_vals)
    if n < 30:
        return None
    valor = vs[i - 1]
    orden = sorted(ventana_vals)
    # Percentil = fraccion de la ventana que queda POR DEBAJO del valor, con el
    # propio valor incluido en su percentil (por eso bisect_right y no left):
    # en una serie plana, el valor debe quedar en el 1.0 (el maximo de su
    # ventana), no en 0. Contar los empates como "por debajo" subestima.
    debajo = bisect.bisect_right(orden, valor)
    pct = debajo / n
    return {
        "t": dt_ms(t_ref).isoformat(),
        "valor": valor,
        "percentil": round(pct, 4),
        "n_ventana": n,
        "min": orden[0],
        "max": orden[-1],
        "mediana": orden[n // 2],
        "desde": dt_ms(ts[i0]).isoformat(),
        "hasta": dt_ms(ts[i - 1]).isoformat(),
    }


def estado_serie(nombre: str, ventana_dias: int) -> dict | None:
    """Corte actual de una serie con su percentil causal."""
    ts, vs = cargar(nombre)
    if len(ts) < 30:
        return None
    ultimo = percentil_causal(ts, vs, ts[-1],
                              datetime.timedelta(days=ventana_dias))
    if ultimo is None:
        return None
    # contexto breve: donde estan los extremos historicos de la ventana
    extremo = "alto" if ultimo["percentil"] >= 0.95 else \
        "bajo" if ultimo["percentil"] <= 0.05 else "normal"
    return {
        "serie": nombre,
        "ventana_dias": ventana_dias,
        "corte": ultimo,
        "lectura": extremo,
        "n_total": len(ts),
        "cobertura_dias": round((ts[-1] - ts[0]) / 86_400_000, 1),
    }


def serie_completa(nombre: str, ventana_dias: int) -> list[dict]:
    """Percentil causal en cada observacion (para graficar/auditar)."""
    ts, vs = cargar(nombre)
    out = []
    for t in ts:
        r = percentil_causal(ts, vs, t, datetime.timedelta(days=ventana_dias))
        if r:
            out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serie", choices=sorted(SERIES))
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--todo", action="store_true")
    a = ap.parse_args()

    nombres = sorted(SERIES) if a.todo else ([a.serie] if a.serie
                                            else ["funding", "oi", "taker"])
    informe = {}
    for n in nombres:
        vd = 30 if n in ("oi", "taker", "top_cuentas", "top_posiciones",
                         "global_cuentas", "oi_valor") else 400
        try:
            r = estado_serie(n, vd)
        except FileNotFoundError:
            print(f"  {n:16s} sin archivo (corre analysis/archivo_micro.py --todo)")
            continue
        if not r:
            print(f"  {n:16s} sin datos suficientes")
            continue
        informe[n] = r
        c = r["corte"]
        print(f"  {n:16s} valor={c['valor']:<18} pct={c['percentil']*100:5.1f}% "
              f"({r['lectura']}) | n_ventana={c['n_ventana']:5d} "
              f"| rango [{c['min']:.4g}, {c['max']:.4g}] | "
              f"cobertura {r['cobertura_dias']}d")

    if informe:
        out = {"generado": datetime.datetime.now(UTC).isoformat(),
               "nota": "percentiles causales: sin look-ahead",
               "series": informe}
        p = os.path.join(AQUI, "data", "percentiles_hoy.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"OK -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

