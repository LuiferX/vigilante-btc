#!/usr/bin/env python3
"""
archivo_micro.py - archivo DURABLE de microestructura (OI, taker, ballenas,
funding).

Por que existe: la API publica de Binance solo sirve ~30 dias de
`openInterestHist` y `takerlongshortRatio` (probado: startTime de 31 dias ->
HTTP 400). Todo lo que no se archive hoy se pierde para siempre. El funding si
tiene historial profundo (4 anos) y se archiva completo.

Reglas:
  - NUNCA recorta: append-only con dedup por timestamp. Idempotente: correrlo
    dos veces no duplica nada.
  - Escritura atomica: se escribe a .tmp y se renombra, para que un corte a
    mitad no corrompa el archivo.
  - Cero dependencias externas (stdlib puro).

Uso:
    python analysis/archivo_micro.py --todo          # todas las series
    python analysis/archivo_micro.py --serie oi      # una serie
    python analysis/archivo_micro.py --diario        # modo CI: solo lo nuevo
    python analysis/archivo_micro.py --estado        # cobertura del archivo
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

UTC = datetime.timezone.utc
AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(AQUI, "data", "archivo")
# El colector vive un nivel arriba, en collector/. Se anade al path para poder
# reusar SUS fuentes alternativas (OKX/Bybit) cuando Binance bloquea con 451.
_COLECTOR = os.path.join(os.path.dirname(AQUI), "collector")
if _COLECTOR not in sys.path:
    sys.path.insert(0, _COLECTOR)
UA = "vigilante-archivo/1.0 (+https://github.com/LuiferX/vigilante-btc)"
PASO_MS = 5 * 60 * 1000  # las series son de 5 minutos
LIMITE = 500  # maximo por pagina de la API
TOPE_DIAS = 30  # tope duro de la API para OI/taker/ballenas

# nombre -> (endpoint, clave de tiempo, campos a conservar)
SERIES = {
    "oi": ("openInterestHist", "timestamp", ("sumOpenInterest", "sumOpenInterestValue")),
    "taker": ("takerlongshortRatio", "timestamp", ("buySellRatio", "buyVol", "sellVol")),
    "top_cuentas": (
        "topLongShortAccountRatio",
        "timestamp",
        ("longShortRatio", "longAccount", "shortAccount"),
    ),
    "top_posiciones": (
        "topLongShortPositionRatio",
        "timestamp",
        ("longShortRatio", "longPosition", "shortPosition"),
    ),
    "global_cuentas": (
        "globalLongShortAccountRatio",
        "timestamp",
        ("longShortRatio", "longAccount", "shortAccount"),
    ),
}


# ------------------------------------------------------------------- red ----
def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get_seguro(url: str):
    """Devuelve la lista o None si la API rechaza (p. ej. mas alla del tope)."""
    try:
        d = http_get_json(url)
    except urllib.error.HTTPError as e:
        if e.code in (400, 451):
            return None  # fuera del tope / bloqueado: no es error
        raise
    return d if isinstance(d, list) else None


def ms(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1000)


def dt_ms(v) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(v) / 1000, tz=UTC)


# -------------------------------------------------------------- descarga ----
def descargar_serie(
    endpoint: str,
    campo_tiempo: str,
    campos,
    dias: int,
    symbol: str = "BTCUSDT",
):
    """Baja todo el histÃ³rico disponible (hasta `dias` o el tope de la API).

    Pagina hacia atras desde ahora. Devuelve lista de dicts normalizados.
    """
    fin = datetime.datetime.now(UTC)
    inicio = fin - datetime.timedelta(days=dias)
    out: dict[int, dict] = {}
    end = ms(fin)
    paginas = 0
    while paginas < 400:  # techo de seguridad
        url = (
            f"https://fapi.binance.com/futures/data/{endpoint}"
            f"?symbol={symbol}&period=5m&limit={LIMITE}&endTime={end}"
        )
        raw = _get_seguro(url)
        if not raw:
            break
        paginas += 1
        for r in raw:
            t = r.get(campo_tiempo)
            if t is None:
                continue
            rec = {"source": f"binance_{endpoint}", "symbol": r.get("symbol"), campo_tiempo: t}
            for c in campos:
                if c in r:
                    rec[c] = r[c]
            out[int(t)] = rec
        # OJO: la API devuelve las filas en orden ASCENDENTE: el mas viejo de
        # la pagina es raw[0]. Usar raw[-1] (el mas nuevo) hacia que cada
        # pagina retrocediera 5 minutos en vez de 41 horas -> bucle infinito.
        oldest = int(raw[0][campo_tiempo])
        if oldest >= end - 1:  # la pagina no avanzo: cortar
            break
        if dt_ms(oldest) <= inicio:
            break
        end = oldest - 1  # siguiente pagina hacia atras
        time.sleep(0.15)
    return [out[k] for k in sorted(out)]


def descargar_funding(dias: int = 1500, symbol: str = "BTCUSDT"):
    """El funding no tiene el tope de 30 dias: se baja todo el histÃ³rico."""
    fin = datetime.datetime.now(UTC)
    inicio = fin - datetime.timedelta(days=dias)
    out: dict[int, dict] = {}
    end = ms(fin)
    paginas = 0
    while paginas < 400:  # techo de seguridad
        url = (
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
            f"&limit=1000&endTime={end}"
        )
        raw = _get_seguro(url)
        if not raw:
            break
        paginas += 1
        for r in raw:
            t = r.get("fundingTime")
            if t is None:
                continue
            out[int(t)] = {
                "source": "binance_fundingRate",
                "symbol": r.get("symbol"),
                "fundingTime": t,
                "fundingRate": r.get("fundingRate"),
            }
        # mismo detalle que en descargar_serie: raw[0] es el mas viejo
        oldest = int(raw[0]["fundingTime"])
        if oldest >= end - 1:  # la pagina no avanzo: cortar
            break
        if dt_ms(oldest) <= inicio:
            break
        end = oldest - 1
        time.sleep(0.15)
    return [out[k] for k in sorted(out)]


# --------------------------------------------------------- fallback (451) ---
# Binance devuelve HTTP 451 (bloqueo legal/geografico) a las IPs de los runners
# de GitHub Actions: el trabajo automatico se quedaria sin datos todos los dias.
# El colector ya tiene fallbacks que SI funcionan desde ahi (OKX/Bybit), con el
# mismo esquema de campos y su propio `source`. Se reutilizan: el archivo crece
# igual, y la procedencia queda en cada fila.
FALLBACK = {
    "oi": "fetch_open_interest_okx",
    "taker": "fetch_taker_okx",
    "top_cuentas": "fetch_long_short_okx",
    "global_cuentas": "fetch_long_short_okx",
    "top_posiciones": "fetch_long_short_bybit",
}


def descargar_alterno(nombre: str) -> list[dict]:
    """Registros de la fuente alternativa (OKX/Bybit) para una serie."""
    fn_nombre = FALLBACK.get(nombre)
    if fn_nombre is None:
        return []
    try:
        import collector as co  # noqa: E402  (script hermano)

        fn = getattr(co, fn_nombre, None)
        if fn is None:
            return []
        return fn() or []
    except Exception as e:
        print(f"    (fallback {nombre}: {type(e).__name__} {str(e)[:50]})")
        return []


def descargar_funding_alterno() -> list[dict]:
    """Funding historico de OKX (hasta 100 pagos por llamada)."""
    try:
        import collector as co  # noqa: E402

        return co.fetch_funding_okx(100) or []
    except Exception as e:
        print(f"    (fallback funding: {type(e).__name__} {str(e)[:50]})")
        return []


# ------------------------------------------------------------ persistencia --
def ruta_serie(nombre: str) -> str:
    return os.path.join(ARCHIVO, f"{nombre}.jsonl")


def fusionar(nombre: str, nuevos: list[dict], campo: str) -> tuple[int, int]:
    """Idempotente y CANONICO: anade solo lo que no este y deja el archivo
    ordenado por `campo` (timestamp) y sin duplicados.

    El orden no es cosmÃ©tico: los consumidores hacen bisect sobre el archivo, y
    un archivo desordenado da resultados silenciosamente falsos. Por eso se
    reescribe ordenado en cada pasada (a esta escala, ~9.000 filas, es barato).
    Lineas que no son JSON se conservan al final: nunca se pierde informacion.

    Escritura atomica (.tmp + os.replace): un corte a mitad no corrompe nada.
    """
    path = ruta_serie(nombre)
    os.makedirs(ARCHIVO, exist_ok=True)
    vistos: set = set()
    buenos: list[tuple] = []  # (clave, linea)
    corruptas: list[str] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for linea in fh:
                s = linea.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                    k = rec.get(campo)
                except Exception:
                    corruptas.append(s)
                    continue
                if k in vistos:
                    continue
                vistos.add(k)
                buenos.append((k, s))
    previos = len(buenos)
    agregados = 0
    for rec in nuevos:
        k = rec.get(campo)
        if k in vistos:
            continue
        vistos.add(k)
        buenos.append((k, json.dumps(rec, ensure_ascii=False)))
        agregados += 1
    # orden canonico: por timestamp; las filas sin clave, al final
    buenos.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        for _, linea in buenos:
            out.write(linea + "\n")
        for s in corruptas:
            out.write(s + "\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)
    return agregados, previos


# ------------------------------------------------------------------ main ----
def estado() -> int:
    print("=== cobertura del archivo de microestructura ===")
    if not os.path.isdir(ARCHIVO):
        print("  (vacio: aun no se ha archivado nada)")
        return 0
    for fname in sorted(os.listdir(ARCHIVO)):
        if not fname.endswith(".jsonl"):
            continue
        p = os.path.join(ARCHIVO, fname)
        n = 0
        primero = ultimo = None
        campo = None
        with open(p, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                r = json.loads(linea)
                n += 1
                if campo is None:
                    campo = "fundingTime" if "fundingTime" in r else "timestamp"
                t = int(r[campo])
                primero = t if primero is None else min(primero, t)
                ultimo = t if ultimo is None else max(ultimo, t)
        if primero is None:
            continue
        d0, d1 = dt_ms(primero), dt_ms(ultimo)
        print(
            f"  {fname:22s} {n:7d} filas | {d0:%Y-%m-%d %H:%M} -> "
            f"{d1:%Y-%m-%d %H:%M} | {(d1-d0).days} dias"
        )
    return 0


def recompactar() -> int:
    """Reordena y deduplica los archivos existentes sin tocar la red.

    Util para reparar un archivo que quedo desordenado por una version
    anterior (consumidores con bisect necesitan el orden canonico).
    """
    if not os.path.isdir(ARCHIVO):
        print("  (no hay archivo que recompactar)")
        return 0
    for fname in sorted(os.listdir(ARCHIVO)):
        if not fname.endswith(".jsonl"):
            continue
        nombre = fname[: -len(".jsonl")]
        p = os.path.join(ARCHIVO, fname)
        campo = "fundingTime" if nombre == "funding" else "timestamp"
        with open(p, encoding="utf-8") as fh:
            regs = []
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    regs.append(json.loads(linea))
                except Exception:
                    continue
        _, previos = fusionar(nombre, regs, campo)
        print(f"  {nombre:18s} {previos} filas -> ordenadas y sin duplicados")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todo", action="store_true")
    ap.add_argument("--serie", choices=sorted(SERIES))
    ap.add_argument(
        "--diario", action="store_true", help="modo CI: solo baja lo ultimo (2 dias de margen)"
    )
    ap.add_argument("--estado", action="store_true")
    ap.add_argument(
        "--recompactar", action="store_true", help="reordena y deduplica lo que ya existe, sin red"
    )
    ap.add_argument("--dias", type=int, default=TOPE_DIAS)
    a = ap.parse_args()

    if a.estado:
        return estado()
    if a.recompactar:
        return recompactar()

    dias = 2 if a.diario else a.dias
    os.makedirs(ARCHIVO, exist_ok=True)
    total = 0

    # funding: historico profundo (no tiene el tope de 30 dias)
    if a.todo or a.serie == "funding" or (a.diario and not a.serie):
        regs = descargar_funding(dias=1500 if not a.diario else 3)
        origen = "binance"
        if not regs:
            regs = descargar_funding_alterno()
            origen = "okx (alterno)"
        agr, prev = fusionar("funding", regs, "fundingTime")
        total += agr
        if regs:
            d0 = dt_ms(regs[0]["fundingTime"])
            d1 = dt_ms(regs[-1]["fundingTime"])
            print(
                f"  funding [{origen:^18s}] +{agr:6d} nuevos ({prev} previos) | "
                f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d}"
            )
        else:
            print(f"  funding [{origen:^18s}] sin datos")

    objetivos = [a.serie] if a.serie else sorted(SERIES)
    if a.diario:
        objetivos = sorted(SERIES)
    for nombre in objetivos:
        endpoint, campo, campos = SERIES[nombre]
        regs = descargar_serie(endpoint, campo, campos, dias)
        origen = "binance"
        if not regs:
            regs = descargar_alterno(nombre)
            origen = "okx/bybit (alterno)"
        if not regs:
            print(f"  {nombre:18s} sin datos (binance bloqueado y sin alterno)")
            continue
        agr, prev = fusionar(nombre, regs, campo)
        total += agr
        d0, d1 = dt_ms(regs[0][campo]), dt_ms(regs[-1][campo])
        print(
            f"  {nombre:18s} [{origen:>18s}] +{agr:6d} nuevos ({prev} previos) | "
            f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d}"
        )
    print(f"OK -> {total} registros nuevos en {ARCHIVO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
