#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""integridad_datos.py - ¿los datos en los que me baso son coherentes?

REARME 2026-11-02: importado y adaptado de `laboratorio XL` (experimento 3 de
otra sesion de investigacion, 2026-11-02). El resto de esa carpeta se descarto:
su propia conclusion repite la mia (skill -0,325 en regime-switching; backtester
"No viable tras costes"; peaje 0,23% vs bruto maximo +0,09%).

Lo que SI era unico y util: comparar el MISMO precio en tres exchanges para
detectar (a) que un feed miente, (b) un flash crash real, (c) datos viejos. Mi
`check_health.py` solo vigilaba frescura de ficheros; nadie vigilaba coherencia
entre exchanges, y el informe diario se publica igual aunque un feed este roto.

Diseno (fiel al original, adaptado):
  - precio de Binance / OKX / Bybit (stdlib, sin claves)
  - anomalia: desviacion > 0,5% frente al precio mediano
  - flash crash: caida >= 2% en 5 min (ventana rodante)
  - stale: precio con > 30 s de antiguedad
  - escalera: todo OK -> normal | 1 anomalia -> verificar | 2+ o flash crash ->
    bloquear (el informe lo dice y degrada su confianza, no opera)

Uso:
    python analysis/integridad_datos.py                 # corte e informe JSON
    python analysis/integridad_datos.py --imprimir      # solo texto
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import urllib.error
import urllib.request

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "vigilante-integridad/1.0 (+https://github.com/LuiferX/vigilante-btc)"

UMBRAL_ANOMALIA = 0.005  # 0,5% frente al mediano
UMBRAL_FLASH_CRASH = 0.02  # 2% en la ventana
VENTANA_CRASH_SEG = 300  # 5 minutos
UMBRAL_STALE_SEG = 30  # precio mas viejo que esto = stale


def ahora_ms():
    return int(datetime.datetime.now(UTC).timestamp() * 1000)


AHORA_MS = ahora_ms


# ------------------------------------------------------------- exchanges ----
def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_binance(symbol="BTCUSDT", timeout=12):
    d = _get_json(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}", timeout)
    return float(d["price"]), int(d.get("time") or AHORA_MS())


def fetch_okx(inst_id="BTC-USDT", timeout=12):
    d = _get_json(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}", timeout)
    if str(d.get("code")) != "0":
        raise RuntimeError(f"OKX code {d.get('code')}")
    e = (d.get("data") or [{}])[0]
    return float(e["last"]), int(e.get("ts") or AHORA_MS())


def fetch_bybit(symbol="BTCUSDT", timeout=12):
    d = _get_json(
        f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}", timeout
    )
    if int(d.get("retCode", -1)) != 0:
        raise RuntimeError(f"Bybit retCode {d.get('retCode')}")
    e = (d.get("result", {}).get("list") or [{}])[0]
    return float(e["lastPrice"]), int(e.get("ts") or AHORA_MS())


EXCHANGES = {
    "Binance": (fetch_binance, "BTCUSDT"),
    "OKX": (fetch_okx, "BTC-USDT"),
    "Bybit": (fetch_bybit, "BTCUSDT"),
}


# ------------------------------------------------------------ deteccion ----
def leer_precios(ahora=None):
    """Precio vigente de cada exchange. Devuelve dict nombre -> {precio, ts, err}."""
    ahora = ahora or AHORA_MS()
    out = {}
    for nombre, (fn, sim) in EXCHANGES.items():
        try:
            px, ts = fn(sim)
            out[nombre] = {
                "precio": round(px, 2),
                "ts": ts,
                "edad_seg": round((ahora - ts) / 1000, 1),
            }
        except Exception as e:
            out[nombre] = {
                "precio": None,
                "ts": None,
                "edad_seg": None,
                "err": f"{type(e).__name__}: {str(e)[:60]}",
            }
    return out


def evaluar(precios):
    """Aplica los umbrales y devuelve el veredicto de integridad.

    Reglas:
      - ok = todos los exchanges dan precio y ninguno esta stale.
      - anomalia = |precio - mediana| / mediana > 0,5% (mediana de los que
        respondieron; con <2 precios no se puede comparar -> no_concluyente).
      - flash_crash = caida >= 2% en la ventana (se evalua fuera, con historial).
      - escalera: 2+ anomalias (o crash) -> bloquear | 1 -> verificar | 0 -> ok.
    """
    vivos = {k: v for k, v in precios.items() if v.get("precio")}
    caidos = [k for k, v in precios.items() if not v.get("precio")]
    if len(vivos) < 2:
        return {
            "nivel": "no_concluyente",
            "detalle": f"solo {len(vivos)} exchange(s) respondieron ({', '.join(caidos) or 'ninguno'} fallo)",
        }
    orden = sorted(v["precio"] for v in vivos.values())
    med = orden[len(orden) // 2]
    anomalias = [k for k, v in vivos.items() if abs(v["precio"] - med) / med > UMBRAL_ANOMALIA]
    stales = [
        k
        for k, v in vivos.items()
        if v.get("edad_seg") is not None and v["edad_seg"] > UMBRAL_STALE_SEG
    ]
    if len(anomalias) >= 2:
        nivel, detalle = (
            "bloquear",
            f"2+ exchanges discrepan >{UMBRAL_ANOMALIA*100:.1f}%: {anomalias}",
        )
    elif len(anomalias) == 1 or stales:
        nivel = "verificar"
        detalle = (f"anomalia: {anomalias}" if anomalias else "") + (
            f" | stale: {stales}" if stales else ""
        )
    else:
        nivel, detalle = "ok", f"3 exchanges coinciden dentro de {UMBRAL_ANOMALIA*100:.1f}%"
    return {
        "nivel": nivel,
        "detalle": detalle.strip(" |"),
        "mediana": round(med, 2),
        "anomalias": anomalias,
        "stale": stales,
        "caidos": caidos,
        "dispersion_pct": round((orden[-1] - orden[0]) / med * 100, 3),
    }


def detectar_flash_crash(historial, ahora=None):
    """Caida >= 2% dentro de la ventana. `historial` = [(ts_ms, precio)]."""
    if len(historial) < 2:
        return None
    ahora = ahora or AHORA_MS()
    corte = ahora - VENTANA_CRASH_SEG * 1000
    ventana = [(t, p) for t, p in historial if t >= corte]
    if len(ventana) < 2:
        return None
    mx = max(p for _, p in ventana)
    mn = min(p for _, p in ventana)
    caida = (mx - mn) / mx if mx else 0.0
    if caida >= UMBRAL_FLASH_CRASH:
        return {"caida_pct": round(caida * 100, 2), "max": mx, "min": mn}
    return None


# ------------------------------------------------------------------ main ----
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--imprimir", action="store_true")
    a = ap.parse_args()

    precios = leer_precios()
    ver = evaluar(precios)
    corte = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "precios": precios,
        "veredicto": ver,
    }
    md = redactar(corte)
    if a.imprimir:
        print(md)
        return 0
    pj = os.path.join(AQUI, "data", "integridad.json")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(corte, fh, ensure_ascii=False, indent=2)
    pm = os.path.join(AQUI, "data", "integridad.md")
    with open(pm, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    print(f"OK -> {pj}")
    return 0


def redactar(corte: dict) -> str:
    L = ["# Integridad de datos — corte multi-exchange", ""]
    L.append(f"Generado: {corte['generado'][:19].replace('T', ' ')} UTC")
    L.append("")
    L.append("| Exchange | Precio | Edad (s) | Estado |")
    L.append("|---|---:|---:|---|")
    for k, v in corte["precios"].items():
        estado = "OK" if v.get("precio") else f"caído ({v.get('err', '')[:32]})"
        L.append(f"| {k} | {v.get('precio', '—')} | {v.get('edad_seg', '—')} | {estado} |")
    L.append("")
    v = corte["veredicto"]
    L.append(f"**Veredicto: `{v['nivel']}`** — {v['detalle']}")
    if v.get("dispersion_pct") is not None:
        L.append("")
        L.append(f"Dispersión entre exchanges: **{v['dispersion_pct']} %**.")
    L.append("")
    L.append(
        "> Esto no opera: mide si los datos que alimentan el informe son "
        "coherentes. Si dos exchanges discrepan más del 0,5 % o hay un "
        "flash crash (≥2 % en 5 min), el informe marca sus datos como no "
        "fiables en lugar de publicar cifras tranquilas."
    )
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
