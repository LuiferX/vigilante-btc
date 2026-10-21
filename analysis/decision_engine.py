"""Motor de decision por contexto. No ejecuta ordenes.

Conecta el modelo de aguante (`hold_model`) con:
- deteccion de pivotes y zonas (ancho ATR),
- perfil de volumen (POC / value area),
- sesgo de 1h/4h,
- clasificacion de sweep / ruptura confirmada,
- escenario base, alternativo, trigger, invalidacion y riesgos.

La salida es un diccionario serializable. No hay claves, no hay ordenes,
no hay llamadas a exchanges desde este modulo.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

import hold_model as hm
import paths


MIN_KLINES = 300
PIVOT_K = 5
ZONE_LOOKBACK = 288          # 24h de velas 5m
TOUCH_WINDOW = 72            # 6h: misma ventana del evento de aguante
MIN_TOUCHES = 3
ZONE_MIN_PCT = 0.003         # 0,30% minimo
ZONE_ATR_MULT = 0.30         # 0,30 * ATR 4h

VIGILANTE_ESTADO_URL = (
    "https://raw.githubusercontent.com/LuiferX/vigilante-btc/estado/estado.json"
)


# ---------------------------------------------------------------------------
# Indicadores basicos
# ---------------------------------------------------------------------------

def _true_ranges(kl: list[dict]) -> list[float]:
    out = []
    for i in range(1, len(kl)):
        h, l, prev_c = kl[i]["h"], kl[i]["l"], kl[i - 1]["c"]
        out.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return out


def atr_price(kl: list[dict], bars: int) -> Optional[float]:
    """ATR en precio (no normalizado) de las ultimas `bars` velas."""
    trs = _true_ranges(kl)
    if len(trs) < bars:
        return None
    return sum(trs[-bars:]) / bars


def ema_last(values: list[float], span: int) -> float:
    k = 2.0 / (span + 1.0)
    e = values[0]
    for x in values[1:]:
        e = x * k + e * (1.0 - k)
    return e


def fmt_miles(x: float) -> str:
    """82.500 en vez de 82500."""
    return f"{x:,.0f}".replace(",", ".")


def _zone_label(z: dict) -> str:
    return f"{fmt_miles(z['zone_low'])}–{fmt_miles(z['zone_high'])}"


# ---------------------------------------------------------------------------
# Adaptador del estado publicado del Vigilante
# ---------------------------------------------------------------------------

def levels_from_vigilante_state(state: dict) -> list[dict]:
    """Adapta el `estado.json` del Vigilante a `extra_levels`.

    OJO: `n` es numero de origenes/confluencia, NO numero de toques.
    No se usa como toques para no inventar aguante.
    """
    snap = state.get("snapshot", state) if isinstance(state, dict) else {}
    niv = snap.get("niv") or {}
    out = []
    for raw in niv.get("sop") or []:
        try:
            out.append(
                {
                    "precio": float(raw["precio"]),
                    "tipo": "soporte",
                    "toques": int(raw.get("toques", 0) or 0),
                    "confluencia": int(raw.get("n", 0) or 0),
                    "origen": raw.get("origen", "vigilante"),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    for raw in niv.get("res") or []:
        try:
            out.append(
                {
                    "precio": float(raw["precio"]),
                    "tipo": "resistencia",
                    "toques": int(raw.get("toques", 0) or 0),
                    "confluencia": int(raw.get("n", 0) or 0),
                    "origen": raw.get("origen", "vigilante"),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def load_vigilante_levels(path: str) -> list[dict]:
    """Lee un estado.json local y devuelve los niveles del snapshot."""
    with open(path, encoding="utf-8-sig") as fh:
        return levels_from_vigilante_state(json.load(fh))


def fetch_vigilante_levels(url: str = VIGILANTE_ESTADO_URL, timeout: float = 20.0) -> list[dict]:
    """Lee el estado publicado del Vigilante (raw JSON, sin token).

    Es solo lectura. Si falla la red, devuelve una lista vacia para no
    romper el motor de decision.
    """
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "trading-analysis"})
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            data = json.loads(fh.read().decode("utf-8-sig"))
        return levels_from_vigilante_state(data)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Agregacion y sesgo de mayor temporalidad
# ---------------------------------------------------------------------------

def aggregate(kl: list[dict], bars: int) -> list[dict]:
    """Agrupa velas de 5m en barras de `bars` velas (12=1h, 48=4h)."""
    out = []
    for i in range(0, len(kl) - bars + 1, bars):
        chunk = kl[i : i + bars]
        out.append(
            {
                "t": chunk[0]["t"],
                "o": chunk[0]["o"],
                "h": max(x["h"] for x in chunk),
                "l": min(x["l"] for x in chunk),
                "c": chunk[-1]["c"],
                "v": sum(x["v"] for x in chunk),
            }
        )
    return out


def _trend_from_bars(bars: list[dict], fast: int, slow: int) -> Optional[str]:
    if len(bars) < slow + 1:
        return None
    c = [x["c"] for x in bars]
    ef = ema_last(c, fast)
    es = ema_last(c, slow)
    slope = c[-1] - c[-min(len(c), slow)]
    if c[-1] > es and ef > es and slope > 0:
        return "ALZA"
    if c[-1] < es and ef < es and slope < 0:
        return "BAJA"
    return "LATERAL"


def htf_bias(kl: list[dict]) -> dict:
    """Sesgo de 1h y 4h. Si estan en conflicto, LATERAL."""
    t1 = _trend_from_bars(aggregate(kl, 12), 12, 26)
    t4 = _trend_from_bars(aggregate(kl, 48), 3, 8)
    if t1 in ("ALZA", "BAJA") and t4 in ("ALZA", "BAJA") and t1 == t4:
        bias = t1
    elif t1 in ("ALZA", "BAJA") and t4 is None:
        bias = t1
    elif t4 in ("ALZA", "BAJA") and t1 is None:
        bias = t4
    else:
        bias = "LATERAL"
    return {"h1": t1, "h4": t4, "bias": bias}


def htf_bias_from_klines(htf_klines: Optional[dict[str, list[dict]]]) -> dict:
    """Sesgo con velas nativas de 1h, 4h y 1D.

    Si hay 4h y 1D, manda esa combinacion (swing). Si no, usa 1h/4h.
    Si 4h y 1D estan en conflicto, LATERAL.
    """
    if not htf_klines:
        return {"h1": None, "h4": None, "d1": None, "bias": "LATERAL"}
    t1 = _trend_from_bars(htf_klines.get("1h") or [], 20, 50)
    t4 = _trend_from_bars(htf_klines.get("4h") or [], 8, 21)
    t1d = _trend_from_bars(htf_klines.get("1d") or [], 20, 50)

    if t4 in ("ALZA", "BAJA") and t1d in ("ALZA", "BAJA"):
        bias = t4 if t4 == t1d else "LATERAL"
    elif t4 in ("ALZA", "BAJA"):
        bias = t4
    elif t1d in ("ALZA", "BAJA"):
        bias = t1d
    elif t1 in ("ALZA", "BAJA"):
        bias = t1
    else:
        bias = "LATERAL"
    return {"h1": t1, "h4": t4, "d1": t1d, "bias": bias}


def load_htf_klines(data_dir: str) -> dict[str, list[dict]]:
    """Carga klines_1h/4h/1d.jsonl del colector si existen."""
    out = {}
    for tf in ("1h", "4h", "1d"):
        path = os.path.join(data_dir, f"klines_{tf}.jsonl")
        if os.path.exists(path):
            out[tf] = hm.load_klines_jsonl(path)
    return out


def htf_pivots_from_klines(htf_klines: Optional[dict[str, list[dict]]]) -> list[dict]:
    """Pivotes nativos de 1h/4h/1D para confluencia."""
    if not htf_klines:
        return []
    out = []
    for tf, k, lookback in (("1h", 3, 168), ("4h", 2, 84), ("1d", 2, 60)):
        bars = htf_klines.get(tf) or []
        if len(bars) < 2 * k + 2:
            continue
        for p in find_pivots(bars, k=k, lookback=lookback):
            out.append(
                {
                    "price": p["price"],
                    "tf": tf,
                    "origin": p["origin"],
                    "t": p["t"],
                }
            )
    return out


def htf_pivots(kl: list[dict]) -> list[dict]:
    """Pivotes de 1h y 4h para confluencia de zonas.

    No son toques de 5m: no se usan para calcular aguante. Solo suman
    contexto de mayor temporalidad a la calidad de una zona.
    """
    out = []
    for tf, bars, k, lookback in (("1h", 12, 3, 96), ("4h", 48, 2, 48)):
        agg = aggregate(kl, bars)
        n = len(agg)
        if n < 2 * k + 2:
            continue
        start = max(k, n - lookback)
        end = n - k
        for i in range(start, end):
            win = agg[i - k : i + k + 1]
            if agg[i]["h"] >= max(x["h"] for x in win):
                out.append(
                    {
                        "price": float(agg[i]["h"]),
                        "tf": tf,
                        "origin": f"pivote_{tf}_alto",
                        "t": agg[i]["t"],
                    }
                )
            if agg[i]["l"] <= min(x["l"] for x in win):
                out.append(
                    {
                        "price": float(agg[i]["l"]),
                        "tf": tf,
                        "origin": f"pivote_{tf}_bajo",
                        "t": agg[i]["t"],
                    }
                )
    return out


# ---------------------------------------------------------------------------
# Perfil de volumen
# ---------------------------------------------------------------------------

def volume_profile(kl: list[dict], lookback: int = ZONE_LOOKBACK, bins: int = 40) -> dict:
    """POC y value area (70%) por precio, usando el precio tipico de cada vela."""
    rows = kl[-lookback:]
    if not rows:
        return {}
    lo = min(x["l"] for x in rows)
    hi = max(x["h"] for x in rows)
    if hi <= lo:
        return {}
    step = (hi - lo) / bins
    buckets = [0.0] * bins
    for x in rows:
        tp = (x["h"] + x["l"] + x["c"]) / 3.0
        idx = min(bins - 1, max(0, int((tp - lo) / step)))
        buckets[idx] += x["v"]

    poc_idx = max(range(bins), key=lambda i: buckets[i])
    total = sum(buckets)
    target = total * 0.70
    left = right = poc_idx
    acc = buckets[poc_idx]
    while acc < target and (left > 0 or right < bins - 1):
        lv = buckets[left - 1] if left > 0 else -1.0
        rv = buckets[right + 1] if right < bins - 1 else -1.0
        if rv >= lv:
            right += 1
            acc += buckets[right]
        else:
            left -= 1
            acc += buckets[left]
    return {
        "poc": lo + (poc_idx + 0.5) * step,
        "val": lo + left * step,
        "vah": lo + (right + 1) * step,
        "bins": bins,
        "step": step,
    }


def zone_volume_share(kl: list[dict], low: float, high: float, lookback: int = ZONE_LOOKBACK) -> float:
    """Fraccion del volumen reciente cuyo precio tipico cae dentro de la zona."""
    rows = kl[-lookback:]
    total = sum(x["v"] for x in rows)
    if total <= 0:
        return 0.0
    inside = sum(
        x["v"]
        for x in rows
        if low <= (x["h"] + x["l"] + x["c"]) / 3.0 <= high
    )
    return inside / total


# ---------------------------------------------------------------------------
# Niveles y zonas
# ---------------------------------------------------------------------------

def find_pivots(kl: list[dict], k: int = PIVOT_K, lookback: int = ZONE_LOOKBACK) -> list[dict]:
    """Pivotes locales de 5m. El ultimo pivote necesita k velas a la derecha."""
    n = len(kl)
    if n < 2 * k + 1:
        return []
    start = max(k, n - lookback)
    end = n - k
    out = []
    for i in range(start, end):
        hi = kl[i]["h"]
        lo = kl[i]["l"]
        win = kl[i - k : i + k + 1]
        if hi >= max(x["h"] for x in win):
            out.append({"i": i, "price": float(hi), "origin": "pivote_alto", "t": kl[i]["t"]})
        if lo <= min(x["l"] for x in win):
            out.append({"i": i, "price": float(lo), "origin": "pivote_bajo", "t": kl[i]["t"]})
    return out


def _cluster_one_side(pivots: list[dict], width: float) -> list[list[dict]]:
    if not pivots:
        return []
    pivots = sorted(pivots, key=lambda x: x["price"])
    clusters = [[pivots[0]]]
    for p in pivots[1:]:
        cur = clusters[-1]
        center = sum(x["price"] for x in cur) / len(cur)
        if abs(p["price"] - center) <= width:
            cur.append(p)
        else:
            clusters.append([p])
    return clusters


def build_zones(
    kl: list[dict],
    price: float,
    width: float,
    extra_levels: Optional[list[dict]] = None,
    vp: Optional[dict] = None,
    htf: Optional[list[dict]] = None,
) -> list[dict]:
    """Agrupa pivotes cercanos en zonas y les asigna rol segun el precio."""
    pivots = find_pivots(kl)
    highs = [p for p in pivots if p["origin"] == "pivote_alto"]
    lows = [p for p in pivots if p["origin"] == "pivote_bajo"]
    n = len(kl)

    zones = []
    for origin, group in (("pivote_alto", highs), ("pivote_bajo", lows)):
        for cl in _cluster_one_side(group, width):
            center = sum(x["price"] for x in cl) / len(cl)
            touches_6h = sum(1 for x in cl if x["i"] >= n - TOUCH_WINDOW)
            role = "soporte" if center <= price else "resistencia"
            zones.append(
                {
                    "center": center,
                    "zone_low": center - width / 2.0,
                    "zone_high": center + width / 2.0,
                    "width": width,
                    "touches": len(cl),
                    "touches_6h": touches_6h,
                    "confluence": 0,
                    "origin": origin,
                    "role": role,
                    "last_touch": max(x["t"] for x in cl),
                    "source": "pivotes_5m",
                }
            )

    # Niveles externos (por ejemplo, la rejilla publicada del Vigilante).
    for raw in extra_levels or []:
        try:
            level = float(raw.get("precio", raw.get("price", raw.get("level"))))
        except (TypeError, ValueError):
            continue
        if level <= 0:
            continue
        role_raw = str(raw.get("tipo", raw.get("role", ""))).lower()
        role = "soporte" if ("sop" in role_raw or level <= price) else "resistencia"
        touches = int(raw.get("toques", raw.get("touches", 0)) or 0)
        confluence = int(raw.get("confluencia", raw.get("confluence", 0)) or 0)
        merged = False
        for z in zones:
            if z["role"] == role and abs(z["center"] - level) <= width:
                z["center"] = (z["center"] + level) / 2.0
                z["zone_low"] = z["center"] - width / 2.0
                z["zone_high"] = z["center"] + width / 2.0
                z["touches"] = max(z["touches"], touches)
                z["touches_6h"] = max(z["touches_6h"], touches)
                z["confluence"] = max(z.get("confluence", 0), confluence)
                z["source"] = z["source"] + "+vigilante"
                merged = True
                break
        if not merged:
            zones.append(
                {
                    "center": level,
                    "zone_low": level - width / 2.0,
                    "zone_high": level + width / 2.0,
                    "width": width,
                    "touches": touches,
                    "touches_6h": touches,
                    "confluence": confluence,
                    "origin": "nivel_externo",
                    "role": role,
                    "last_touch": None,
                    "source": "vigilante",
                }
            )

    # POC del perfil de volumen como nivel de contexto.
    if vp and vp.get("poc"):
        poc = float(vp["poc"])
        role = "soporte" if poc <= price else "resistencia"
        merged = False
        for z in zones:
            if z["role"] == role and abs(z["center"] - poc) <= width:
                z["source"] = z["source"] + "+poc"
                merged = True
                break
        if not merged:
            zones.append(
                {
                    "center": poc,
                    "zone_low": poc - width / 2.0,
                    "zone_high": poc + width / 2.0,
                    "width": width,
                    "touches": 0,
                    "touches_6h": 0,
                    "confluence": 0,
                    "origin": "perfil_volumen",
                    "role": role,
                    "last_touch": None,
                    "source": "volume_profile",
                }
            )

    htf = htf or []
    for z in zones:
        z["vol_share"] = zone_volume_share(kl, z["zone_low"], z["zone_high"])
        z["htf_confluence"] = len(
            {
                p["tf"]
                for p in htf
                if abs(p["price"] - z["center"]) <= width
            }
        )
        if z["htf_confluence"] and "htf" not in z["source"]:
            z["source"] = z["source"] + "+htf"
    return zones


# ---------------------------------------------------------------------------
# Clasificacion y calidad
# ---------------------------------------------------------------------------

def classify_zone(kl: list[dict], zone: dict) -> dict:
    """Posicion actual, sweep reciente y ruptura confirmada por cierres."""
    low, high = zone["zone_low"], zone["zone_high"]
    last = kl[-1]["c"]
    if low <= last <= high:
        position = "dentro"
    elif last > high:
        position = "arriba"
    else:
        position = "abajo"

    sweep = False
    sweep_i = None
    for j in range(max(0, len(kl) - 12), len(kl)):
        x = kl[j]
        if zone["role"] == "resistencia" and x["h"] > high and x["c"] < high:
            sweep = True
            sweep_i = j
        elif zone["role"] == "soporte" and x["l"] < low and x["c"] > low:
            sweep = True
            sweep_i = j

    def outside(x):
        return x["c"] > high if zone["role"] == "resistencia" else x["c"] < low

    break_bars = 0
    for x in reversed(kl[-5:]):
        if outside(x):
            break_bars += 1
        else:
            break

    return {
        "position": position,
        "recent_sweep": sweep,
        "sweep_age_min": (len(kl) - 1 - sweep_i) * 5 if sweep_i is not None else None,
        "break_bars": break_bars,
        "break_confirmed": break_bars >= 2,
    }


def round_level(center: float, width: float) -> tuple[Optional[float], int, float]:
    """Nivel redondo dentro de la zona. Es confluencia psicologica, no magia."""
    for step, score in ((1000, 0.5), (500, 0.25), (100, 0.1)):
        nearest = round(center / step) * step
        if abs(center - nearest) <= width / 2.0:
            return float(nearest), step, score
    return None, 0, 0.0


def zone_quality(zone: dict, now: datetime) -> float:
    """Calidad 0-10 de una zona. No es probabilidad de ganar.

    Componentes: toques 6h (3), aguante (3), volumen en zona (2),
    recencia (1), confluencia 1h/4h/1D + Vigilante (1), nivel redondo (0.5).
    """
    touch_score = min(zone.get("touches_6h", 0), 4) / 4.0 * 3.0
    hold = zone.get("hold")
    hold_score = (hold["prob"] if hold else 0.5) * 3.0
    vol_score = min(zone.get("vol_share", 0.0) / 0.12, 1.0) * 2.0
    last = zone.get("last_touch")
    if last is None:
        recency = 0.5
    else:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (now - last).total_seconds() / 3600.0)
        recency = math.exp(-age_h / 12.0)
    conf_score = min(
        zone.get("confluence", 0) + zone.get("htf_confluence", 0), 4
    ) / 4.0
    round_score = zone.get("round_score", 0.0)
    return round(
        min(10.0, touch_score + hold_score + vol_score + recency + conf_score + round_score),
        1,
    )


# ---------------------------------------------------------------------------
# Estado de mercado
# ---------------------------------------------------------------------------

def market_state(
    kl: list[dict],
    price: float,
    htf_klines: Optional[dict[str, list[dict]]] = None,
) -> dict:
    c = [float(x["c"]) for x in kl]
    ema50 = ema_last(c, min(50, len(c)))
    ema200 = ema_last(c, min(200, len(c)))
    ret24 = price / c[-288] - 1.0 if len(c) >= 289 else None
    atr4h = atr_price(kl, 48)
    atr24h = atr_price(kl, 288)
    atr14 = atr_price(kl, 14)
    atr4h_pct = atr4h / price if atr4h else None
    atr24h_pct = atr24h / price if atr24h else None
    vol_ratio = (atr14 / atr24h) if atr14 and atr24h else None

    if ret24 is not None and price > ema200 and ema50 > ema200 and ret24 > 0.002:
        bias5 = "ALZA"
    elif ret24 is not None and price < ema200 and ema50 < ema200 and ret24 < -0.002:
        bias5 = "BAJA"
    else:
        bias5 = "LATERAL"

    native = htf_bias_from_klines(htf_klines)
    if htf_klines and any(native.get(k) for k in ("h1", "h4", "d1")):
        htf = native
        htf_source = "nativo_1h_4h_1d"
    else:
        htf = htf_bias(kl)
        htf["d1"] = None
        htf_source = "agregado_desde_5m"

    if htf["bias"] in ("ALZA", "BAJA"):
        bias = htf["bias"]
        bias_source = htf_source
    elif htf["h1"] is None and htf["h4"] is None and htf.get("d1") is None:
        bias = bias5
        bias_source = "5m"
    else:
        bias = "LATERAL"
        bias_source = htf_source

    if vol_ratio is None:
        volatility = "sin_datos"
    elif vol_ratio > 1.4:
        volatility = "expansion"
    elif vol_ratio < 0.7:
        volatility = "compresion"
    else:
        volatility = "normal"

    vp = volume_profile(kl)
    return {
        "bias": bias,
        "bias_source": bias_source,
        "bias_5m": bias5,
        "bias_htf": htf["bias"],
        "htf": {
            "h1": htf.get("h1"),
            "h4": htf.get("h4"),
            "d1": htf.get("d1"),
            "source": htf_source,
        },
        "volatility": volatility,
        "ema50": ema50,
        "ema200": ema200,
        "ret24_pct": ret24 * 100.0 if ret24 is not None else None,
        "atr4h_pct": atr4h_pct * 100.0 if atr4h_pct is not None else None,
        "atr24h_pct": atr24h_pct * 100.0 if atr24h_pct is not None else None,
        "vol_ratio": vol_ratio,
        "poc": vp.get("poc"),
        "val": vp.get("val"),
        "vah": vp.get("vah"),
    }


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

def _nearest(zones: list[dict], role: str, price: float) -> Optional[dict]:
    if role == "soporte":
        cands = [z for z in zones if z["role"] == "soporte" and z["center"] <= price * 1.002]
        return max(cands, key=lambda z: z["center"]) if cands else None
    cands = [z for z in zones if z["role"] == "resistencia" and z["center"] >= price * 0.998]
    return min(cands, key=lambda z: z["center"]) if cands else None


def _hold_for(kl, zone, price, event_time):
    # El evento de aguante se define con 3+ toques en 6h. Si no los hay,
    # se muestra la zona pero no se inventa una probabilidad.
    if zone["touches_6h"] < MIN_TOUCHES:
        return None
    return hm.score_level(kl, zone["center"], price, event_time, zone["role"])


def _normalize_bias(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper()
    if v in ("ALZA", "ALCISTA", "UP", "BULL"):
        return "ALZA"
    if v in ("BAJA", "BAJISTA", "DOWN", "BEAR"):
        return "BAJA"
    if v in ("LATERAL", "RANGO", "RANGE", "SIDEWAYS"):
        return "LATERAL"
    return None


def decide(
    kl: list[dict],
    price: Optional[float] = None,
    now: Optional[datetime] = None,
    extra_levels: Optional[list[dict]] = None,
    htf_bias_override: Optional[str] = None,
    htf_klines: Optional[dict[str, list[dict]]] = None,
) -> dict:
    """Construye el contexto de decision. No ejecuta nada.

    `kl`: velas 5m cerradas, dicts con t/o/h/l/c/v.
    `extra_levels`: niveles opcionales, por ejemplo del Vigilante.
    `htf_bias_override`: "ALZA"/"BAJA"/"LATERAL" para usar el sesgo del
    Vigilante u otra fuente de mayor temporalidad.
    `htf_klines`: dict opcional {"1h": [...], "4h": [...], "1d": [...]}.
    Si existe, manda el sesgo nativo 1h/4h/1D y sus pivotes.
    """
    if not kl or len(kl) < 50:
        return {
            "ok": False,
            "error": "faltan_velas",
            "detail": "Se necesitan al menos 50 velas de 5m; idealmente 300+.",
            "disclaimer": "Contexto, no ejecucion.",
        }

    price = float(price if price is not None else kl[-1]["c"])
    event_time = kl[-1]["t"]
    now = now or event_time
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    data_age_min = max(0.0, (now - event_time).total_seconds() / 60.0)

    atr4h = atr_price(kl, 48)
    width = max(ZONE_MIN_PCT * price, ZONE_ATR_MULT * (atr4h or 0.0))
    state = market_state(kl, price, htf_klines=htf_klines)

    override = _normalize_bias(htf_bias_override)
    if override is not None:
        state["bias"] = override
        state["bias_source"] = "override"

    vp = volume_profile(kl)
    htf_levels = (
        htf_pivots_from_klines(htf_klines) if htf_klines else htf_pivots(kl)
    )
    state["htf_pivots"] = len(htf_levels)
    zones = build_zones(kl, price, width, extra_levels, vp, htf_levels)

    for z in zones:
        z["distance_pct"] = (z["center"] - price) / price * 100.0
        z["hold"] = _hold_for(kl, z, price, event_time)
        if z["hold"] is not None:
            z["hold"] = {
                "prob": z["hold"]["prob"],
                "tier": z["hold"]["tier"],
                "drivers": z["hold"]["drivers"],
            }
        z.update(classify_zone(kl, z))
        z["round_level"], z["round_step"], z["round_score"] = round_level(
            z["center"], z["width"]
        )
        z["quality"] = zone_quality(z, event_time)

    zones.sort(key=lambda z: (-z["quality"], abs(z["center"] - price)))
    support = _nearest(zones, "soporte", price)
    resistance = _nearest(zones, "resistencia", price)
    in_zone = next((z for z in zones if z["zone_low"] <= price <= z["zone_high"]), None)
    recent_sweep = next((z for z in zones if z["recent_sweep"]), None)
    best_quality = max((z["quality"] for z in zones), default=0.0)

    risks = []
    if len(kl) < MIN_KLINES:
        risks.append("Menos de 300 velas: el modelo de aguante puede no calcularse.")
    if data_age_min > 20:
        risks.append(f"Datos con {data_age_min:.0f} min de antiguedad; verificar que el colector este al dia.")
    if not zones:
        risks.append("Sin niveles validados en la ventana reciente.")
    if in_zone is not None:
        risks.append(f"Precio dentro de la zona {_zone_label(in_zone)}; el trigger no esta activo.")
    if recent_sweep is not None:
        risks.append(
            f"Sweep reciente en {_zone_label(recent_sweep)} hace "
            f"{recent_sweep['sweep_age_min']} min; esperar cierre de confirmacion."
        )
    if state["volatility"] == "expansion":
        risks.append("Volatilidad en expansion: mas riesgo de mecha y falso quiebre.")
    if support is None and resistance is None:
        risks.append("Sin soporte ni resistencia cercanos para armar escenario.")

    base = "Sin escenario claro: faltan niveles o direccion."
    trigger = "Sin trigger: esperar a que se forme una zona con 3+ toques y cierre de confirmacion."
    invalidation = "Sin escenario, no hay invalidacion operativa."
    confidence = "baja"
    action = "sin_escenario"
    ref = None

    if state["bias"] == "ALZA":
        if support is not None:
            base = (
                f"Sesgo al alza mientras el precio cierre por encima de la zona "
                f"{_zone_label(support)}."
            )
        else:
            base = "Sesgo al alza, pero sin soporte cercano validado."
        if resistance is not None:
            trigger = (
                f"Cierre de 5m por encima de {fmt_miles(resistance['zone_high'])} "
                f"y retest que no vuelva a entrar en la zona."
            )
            ref = resistance
        elif support is not None:
            trigger = (
                f"Retest de {_zone_label(support)} con cierre dentro de la zona "
                f"y aguante >= 0.70."
            )
            ref = support
        if support is not None:
            invalidation = (
                f"Cierre de 5m por debajo de {fmt_miles(support['zone_low'])}. "
                f"Una mecha que vuelve a entrar no invalida."
            )
        elif resistance is not None:
            invalidation = (
                f"Cierre de 5m por encima de {fmt_miles(resistance['zone_high'])} "
                f"sin retest: el escenario de rango cambia."
            )
        action = "esperar_confirmacion"

    elif state["bias"] == "BAJA":
        if resistance is not None:
            base = (
                f"Sesgo a la baja mientras el precio cierre por debajo de la zona "
                f"{_zone_label(resistance)}."
            )
        else:
            base = "Sesgo a la baja, pero sin resistencia cercana validada."
        if support is not None:
            trigger = (
                f"Cierre de 5m por debajo de {fmt_miles(support['zone_low'])} "
                f"y retest que no vuelva a entrar en la zona."
            )
            ref = support
        elif resistance is not None:
            trigger = (
                f"Rechazo en {_zone_label(resistance)} con cierre dentro de la zona "
                f"y aguante >= 0.70."
            )
            ref = resistance
        if resistance is not None:
            invalidation = (
                f"Cierre de 5m por encima de {fmt_miles(resistance['zone_high'])}. "
                f"Una mecha que vuelve a entrar no invalida."
            )
        elif support is not None:
            invalidation = (
                f"Cierre de 5m por debajo de {fmt_miles(support['zone_low'])} "
                f"sin retest: el escenario de rango cambia."
            )
        action = "esperar_confirmacion"

    else:  # LATERAL
        if support is not None and resistance is not None:
            base = (
                f"Rango entre {_zone_label(support)} y {_zone_label(resistance)}. "
                f"Solo los extremos con confirmacion."
            )
            trigger = (
                f"Cierre de 5m fuera del rango (arriba de {fmt_miles(resistance['zone_high'])} "
                f"o abajo de {fmt_miles(support['zone_low'])}) y retest que no vuelva a entrar."
            )
            invalidation = (
                "Si el precio cierra fuera y luego vuelve dentro del rango, "
                "es sweep/falso quiebre, no continuidad."
            )
            ref = support if support.get("hold") else resistance
            action = "esperar_confirmacion"
        else:
            base = "Rango sin ambos bordes claros; no hay escenario de continuidad."
            trigger = "Sin trigger: falta un extremo validado del rango."
            invalidation = "Sin escenario, no hay invalidacion operativa."
            ref = support or resistance
            action = "sin_escenario"

    if ref is None:
        action = "sin_escenario"

    # Confianza: no es probabilidad de ganar; es calidad del contexto.
    ref_prob = None
    if ref is not None and ref.get("hold"):
        ref_prob = ref["hold"]["prob"]
        if ref["hold"]["tier"] == "fragil":
            risks.append(f"Nivel de referencia fragil ({ref_prob * 100:.0f}% de aguante).")
    else:
        risks.append("El nivel de referencia no tiene 3+ toques en 6h; no se calculo aguante.")

    if ref_prob is None:
        confidence = "baja"
    elif state["bias"] == "LATERAL":
        confidence = "media" if ref_prob >= 0.70 else "baja"
    elif ref_prob >= 0.80:
        confidence = "alta"
    elif ref_prob >= 0.60:
        confidence = "media"
    else:
        confidence = "baja"

    if ref is not None and ref.get("quality", 0) >= 8.0 and confidence == "media":
        confidence = "alta"
    if state["volatility"] == "expansion" and confidence == "alta":
        confidence = "media"
    if in_zone is not None and confidence == "alta":
        confidence = "media"

    if not zones:
        action = "sin_escenario"
    if in_zone is not None and action != "sin_escenario":
        action = "observar"

    # Escenario alternativo: el otro lado del rango o la perdida del nivel.
    alt_trigger = "Sin escenario alternativo."
    alt_invalidation = "Sin invalidacion."
    if state["bias"] == "ALZA" and support is not None:
        alt_trigger = f"Cierre de 5m por debajo de {fmt_miles(support['zone_low'])}."
        alt_invalidation = f"Recupera y cierra arriba de {fmt_miles(support['zone_high'])}."
    elif state["bias"] == "BAJA" and resistance is not None:
        alt_trigger = f"Cierre de 5m por encima de {fmt_miles(resistance['zone_high'])}."
        alt_invalidation = f"Vuelve y cierra abajo de {fmt_miles(resistance['zone_low'])}."
    elif support is not None and resistance is not None:
        alt_trigger = (
            f"Cierre de 5m fuera de {_zone_label(support)} o {_zone_label(resistance)} "
            f"con retest que no vuelva a entrar."
        )
        alt_invalidation = "Si vuelve dentro del rango, es sweep/falso quiebre."

    scenarios = [
        {
            "name": "base",
            "condition": base,
            "trigger": trigger,
            "invalidation": invalidation,
            "quality": ref.get("quality") if ref else None,
        },
        {
            "name": "alternativo",
            "condition": "Si el precio pierde el nivel de referencia o rompe el otro extremo.",
            "trigger": alt_trigger,
            "invalidation": alt_invalidation,
            "quality": None,
        },
        {
            "name": "no_hacer_nada",
            "condition": "Precio dentro de la zona o sin cierre de confirmacion.",
            "trigger": "No operar.",
            "invalidation": "N/A.",
            "quality": None,
        },
    ]

    # Calidad del motor: completitud/coherencia, no probabilidad.
    data_score = 1.5 * min(len(kl) / 500.0, 1.0)
    zone_score = 1.5 * min(best_quality / 10.0, 1.0)
    hold_score = 2.0 if any(z.get("hold") for z in zones) else 0.0
    scenario_score = 1.5 if trigger and "Sin trigger" not in trigger else 0.5
    # La cobertura de riesgos se mide por haber evaluado el contexto, no
    # porque siempre haya un riesgo. Un setup limpio no se penaliza.
    risk_score = 1.0 if zones else 0.5
    fresh_score = 1.0 if data_age_min <= 20 else 0.2
    structure_score = 1.0 if zones else 0.0
    engine_quality = round(
        min(10.0, data_score + zone_score + hold_score + scenario_score + risk_score + fresh_score + structure_score),
        1,
    )

    def _lvl_txt(z, label):
        if z is None:
            return f"sin {label}"
        h = z.get("hold")
        extra = f" ({h['prob'] * 100:.0f}%)" if h else ""
        return f"{label} {fmt_miles(z['center'])}{extra} [q{z['quality']:.1f}]"

    summary = (
        f"{state['bias']} | vol {state['volatility']} | "
        f"precio {fmt_miles(price)} | "
        f"{_lvl_txt(support, 'soporte')} | {_lvl_txt(resistance, 'resistencia')} | "
        f"{action} | calidad {engine_quality:.1f}/10"
    )

    composite_quality = round((engine_quality + best_quality) / 2.0, 1)
    target_quality = 8.5
    quality_grade = (
        "A" if composite_quality >= target_quality
        else "B" if composite_quality >= 7.5
        else "C" if composite_quality >= 6.5
        else "D"
    )
    return {
        "ok": True,
        "as_of": now.isoformat(),
        "event_time": event_time.isoformat(),
        "data_age_min": round(data_age_min, 1),
        "price": price,
        "summary": summary,
        "engine_quality": engine_quality,
        "setup_quality": round(best_quality, 1),
        "quality": {
            "engine": engine_quality,
            "setup": round(best_quality, 1),
            "composite": composite_quality,
            "target": target_quality,
            "gap": round(max(0.0, target_quality - composite_quality), 1),
            "grade": quality_grade,
            "note": (
                "Promedio de completitud del motor y calidad de la mejor zona. "
                "No es probabilidad de ganar. El objetivo 8,5 es una meta de "
                "calidad de contexto, no una garantia."
            ),
        },
        "state": state,
        "zone_width": width,
        "zone_width_pct": width / price * 100.0,
        "levels": zones,
        "scenarios": scenarios,
        "decision": {
            "action": action,
            "base_scenario": base,
            "trigger": trigger,
            "invalidation": invalidation,
            "confidence": confidence,
            "risks": risks,
            "do_nothing": (
                "No hacer nada si el precio esta dentro de la zona o si no hay cierre "
                "de confirmacion. Una mecha no alcanza."
            ),
        },
        "disclaimer": "Contexto y analisis. No es orden de compra/venta ni ejecucion.",
    }


def decide_from_jsonl(path: str, price: Optional[float] = None, **kwargs) -> dict:
    """Carga el JSONL del colector y construye la decision.

    Si existen `klines_1h/4h/1d.jsonl` en la misma carpeta, los usa para
    sesgo y confluencia. Si no, cae al calculo agregado desde 5m.
    """
    kl = hm.load_klines_jsonl(path)
    if "htf_klines" not in kwargs:
        kwargs["htf_klines"] = load_htf_klines(os.path.dirname(path))
    return decide(kl, price=price, **kwargs)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Motor de decision (solo contexto)")
    ap.add_argument(
        "klines",
        nargs="?",
        default=paths.default_klines_path(),
        help="ruta al klines_5m.jsonl",
    )
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--vigilante", default=None, help="ruta a estado.json o URL raw del Vigilante")
    ap.add_argument("--json", action="store_true", help="salida JSON completa")
    args = ap.parse_args()
    if args.vigilante and args.vigilante.startswith(("http://", "https://")):
        extra = fetch_vigilante_levels(args.vigilante)
    else:
        extra = load_vigilante_levels(args.vigilante) if args.vigilante else None
    out = decide_from_jsonl(args.klines, price=args.price, extra_levels=extra)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
