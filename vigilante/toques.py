#!/usr/bin/env python3
"""
toques.py - MODELO DE TOQUES del Vigilante (Fase 3 de modularizacion).

Extraido 1:1 de vigilante_cloud.py: pivotes micro de 5m, conteo de toques,
features, score logistico (MODELO_TOQUES, el modelo validado toques-wf-1) y el
detector de "nivel probado N veces" (contexto, nunca entrada).
vigilante_cloud.py re-exporta estos nombres: la API publica no cambia.
"""

import math

from vigilante.estado import enfriar
from vigilante.indicadores import fmt_miles

UMBRAL_TOQUE = 0.0025  # 0.25% del nivel = "tocando"


def pivotes_micro(kl, k=5, tol=0.0015):
    """Niveles locales de corto plazo a partir de pivotes (por defecto 5m).
    Agrupa pivotes cercanos para que un triple toque sea UN nivel, no tres."""
    try:
        if not kl or len(kl) < 2 * k + 3:
            return []
        crudos = []
        for i in range(k, len(kl) - k):
            ventana = kl[i - k : i + k + 1]
            if kl[i]["h"] >= max(x["h"] for x in ventana):
                crudos.append(kl[i]["h"])
            if kl[i]["l"] <= min(x["l"] for x in ventana):
                crudos.append(kl[i]["l"])
        out = []
        for p in sorted(crudos):
            hit = next((o for o in out if abs(o["precio"] - p) / p <= tol), None)
            if hit is None:
                out.append({"precio": p, "n": 1})
            else:
                n = hit["n"]
                hit["precio"] = (hit["precio"] * n + p) / (n + 1)
                hit["n"] = n + 1
        return out
    except Exception:
        return []


def toques_en_nivel(kl, nivel, tol=0.0015, salida=0.003, sep=12):
    """Cuenta visitas DISTINTAS: entra en la zona, se aleja 0.3%, y vuelve
    al menos `sep` velas despues (1 h en 5m). Un rango pegado al nivel no cuenta."""
    try:
        n, dentro, last = 0, False, -999
        for i, x in enumerate(kl):
            en_zona = x["l"] <= nivel * (1 + tol) and x["h"] >= nivel * (1 - tol)
            if en_zona and not dentro and (i - last) >= sep:
                n += 1
                dentro = True
                last = i
            elif not en_zona and abs(x["c"] - nivel) / nivel >= salida:
                dentro = False
        return n
    except Exception:
        return 0


MODELO_TOQUES = {
    "version": "toques-wf-1",
    "target": "hold_4h_0.5pct",
    "trained_until": "2026-09-30 22:55:00+00:00",
    "holdout_2026": {"auc": None, "brier": 0.1237, "skill": 0.0093, "base": 0.8538, "n": 212},
    "wf": {
        "folds": 11,
        "muestras_oos": 7757,
        "skill_medio": 0.0168,
        "racha_positiva": 6,
        "skill_folds": [
            0.0111,
            0.0104,
            0.0028,
            0.019,
            0.0304,
            0.0231,
            -0.0055,
            0.0204,
            0.0348,
            0.0132,
            0.0251,
        ],
    },
    "features": ["dist", "atr", "ema200", "rng", "hourc", "dow", "x_atr48", "x_atr144", "x_atr288"],
    "mean": [
        -0.00014471902899527983,
        0.0013422890357383682,
        -0.00015422267700606877,
        0.0015690369453809844,
        0.0011800404585300068,
        -0.08165292068442347,
        0.0013385479332434255,
        0.0014126025893459204,
        0.0014580719082939986,
    ],
    "scale": [
        0.006663299240638484,
        0.0009287107880874037,
        0.007077131053340157,
        0.0013562768488327192,
        0.7156957839129136,
        0.7213757356393746,
        0.0007378356425407469,
        0.0006942695553991874,
        0.0006551650795141382,
    ],
    "coef": [
        -0.0,
        0.0,
        -0.0,
        -0.0,
        0.09829794261377577,
        -0.19040384269895175,
        0.0,
        -0.0,
        -0.2073024131403363,
    ],
    "intercept": 1.5426070329136758,
}


def _ema_ultimo(vals, span):
    k = 2.0 / (span + 1.0)
    e = vals[0]
    for x in vals[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _std_muestral(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def features_toque(kl, nivel, precio, ahora, lado):
    """Features del modelo de aguante, calculadas igual que en entrenamiento.
    `kl` son velas de 5m ya cerradas; `precio` es el precio actual."""
    try:
        n = len(kl)
        if n < 300 or nivel <= 0 or precio <= 0:
            return None
        c = [x["c"] for x in kl]
        h = [x["h"] for x in kl]
        l = [x["l"] for x in kl]
        o = [x["o"] for x in kl]
        v = [max(0.0, x["v"]) for x in kl]
        trs = []
        for i in range(1, n):
            trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        atr = (sum(trs[-14:]) / max(1, min(14, len(trs)))) / precio
        atr48 = (sum(trs[-48:]) / max(1, min(48, len(trs)))) / precio
        atr144 = (sum(trs[-144:]) / max(1, min(144, len(trs)))) / precio
        atr288 = (sum(trs[-288:]) / max(1, min(288, len(trs)))) / precio
        gains, losses = [], []
        for i in range(1, n):
            d = c[i] - c[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        ag = sum(gains[:14]) / 14.0
        al = sum(losses[:14]) / 14.0
        for i in range(14, len(gains)):
            ag = (ag * 13.0 + gains[i]) / 14.0
            al = (al * 13.0 + losses[i]) / 14.0
        rsi = 100.0 - 100.0 / (1.0 + ag / (al + 1e-12))
        ema50 = _ema_ultimo(c, 50)
        ema200 = _ema_ultimo(c, 200)
        lv = [math.log1p(x) for x in v]
        w = lv[-96:]
        mu = sum(w) / len(w)
        volz = (lv[-1] - mu) / (_std_muestral(w) + 1e-12)
        rets = [math.log(c[i] / c[i - 1]) for i in range(1, n) if c[i - 1] > 0]
        rv12 = _std_muestral(rets[-12:])
        rv288 = _std_muestral(rets[-288:])
        # pivotes del mismo lado en las ultimas 72 velas (k=5)
        start = max(0, n - 82)
        sub = kl[start:]
        pivs = []
        for i in range(5, len(sub) - 5):
            if lado == "Soporte":
                if sub[i]["l"] <= min(sub[j]["l"] for j in range(i - 5, i + 6)):
                    pivs.append((start + i, sub[i]["l"]))
            elif sub[i]["h"] >= max(sub[j]["h"] for j in range(i - 5, i + 6)):
                pivs.append((start + i, sub[i]["h"]))
        cl72 = [(j, p) for (j, p) in pivs if j >= n - 72 and abs(p - nivel) / nivel <= 0.0015]
        if not cl72:
            return None
        first = cl72[0][0]
        npiv = len(cl72)
        span = (n - 1 - first) * 5.0 / 60.0
        if lado == "Soporte":
            bounce = max(h[first:n]) / nivel - 1.0
        else:
            bounce = 1.0 - min(l[first:n]) / nivel
        volpiv = (sum(v[j] for j, _ in cl72) / len(cl72)) / (sum(v[-96:]) / len(v[-96:]) + 1e-12)
        rango = h[-1] - l[-1]
        rng = rango / c[-1] if c[-1] else 0.0
        body = (c[-1] - o[-1]) / (rango + 1e-12)
        if lado == "Soporte":
            wick = (min(o[-1], c[-1]) - l[-1]) / (rango + 1e-12)
        else:
            wick = (h[-1] - max(o[-1], c[-1])) / (rango + 1e-12)
        hh = ahora.hour + ahora.minute / 60.0
        return {
            "npiv": float(npiv),
            "span": span,
            "bounce": bounce,
            "dist": (precio - nivel) / nivel,
            "atr": atr,
            "rsi": rsi,
            "ema50": precio / ema50 - 1.0 if ema50 else 0.0,
            "ema200": precio / ema200 - 1.0 if ema200 else 0.0,
            "x_atr48": atr48,
            "x_atr144": atr144,
            "x_atr288": atr288,
            "volz": volz,
            "volpiv": volpiv,
            "rng": rng,
            "body": body,
            "wick": wick,
            "rvratio": rv12 / (rv288 + 1e-12),
            "trend48": precio / c[-48] - 1.0 if n >= 48 and c[-48] else 0.0,
            "trend288": precio / c[-288] - 1.0 if n >= 288 and c[-288] else 0.0,
            "round500": 1.0 if abs(nivel / 500.0 - round(nivel / 500.0)) < 0.002 else 0.0,
            "round1000": 1.0 if abs(nivel / 1000.0 - round(nivel / 1000.0)) < 0.001 else 0.0,
            "hour": math.sin(2 * math.pi * hh / 24.0),
            "hourc": math.cos(2 * math.pi * hh / 24.0),
            "dow": math.sin(2 * math.pi * ahora.weekday() / 7.0),
            "dowc": math.cos(2 * math.pi * ahora.weekday() / 7.0),
            "side": 1.0 if lado == "Soporte" else 0.0,
        }
    except Exception:
        return None


def score_toque(f):
    """Probabilidad estimada de que el nivel aguante 4h (sin cierre 0,5% fuera)."""
    try:
        z = MODELO_TOQUES["intercept"]
        for name, mu, sd, co in zip(
            MODELO_TOQUES["features"],
            MODELO_TOQUES["mean"],
            MODELO_TOQUES["scale"],
            MODELO_TOQUES["coef"],
        ):
            z += co * (f[name] - mu) / (sd + 1e-12)
        if z > 30:
            return 1.0
        if z < -30:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        return None


def detectar_toques_multiples(
    kl, precio, ahora, est, niv=None, min_toques=3, horas=6, cerca=0.003, por_hora=12
):
    """Avisa cuando un nivel local se prueba varias veces seguidas.
    Es CONTEXTO, no entrada: sirve para ver defensa o desgaste del nivel.
    Si se pasa `niv`, exige que el nivel micro este cerca de la rejilla mayor
    (asi no avisa de cualquier ruido de 5m). Por defecto asume velas de 5m."""
    try:
        if not kl or not precio:
            return None
        mayores = []
        if isinstance(niv, dict):
            for _k in ("soportes", "resistencias"):
                for _x in niv.get(_k) or []:
                    try:
                        mayores.append(float(_x["precio"]))
                    except Exception:
                        continue
        n_win = max(24, int(horas * por_hora))
        klw = kl[-n_win:]
        klp = kl[-max(2 * n_win, 144) :]
        cands = []
        for nv in pivotes_micro(klp):
            p = nv["precio"]
            if nv.get("n", 1) < 3:  # nivel formado por al menos 3 pivotes
                continue
            if mayores and min(abs(p - m) / p for m in mayores) > 0.006:
                continue  # nivel micro lejos de la rejilla mayor = ruido
            if abs(precio - p) / precio > cerca:
                continue
            n = toques_en_nivel(klw, p)
            if n < min_toques:
                continue
            ult = None
            for x in reversed(klw):
                if x["l"] <= p * (1 + UMBRAL_TOQUE) and x["h"] >= p * (1 - UMBRAL_TOQUE):
                    ult = x
                    break
            if not ult:
                continue
            lado = "Soporte" if p <= precio else "Resistencia"
            # Si el ultimo toque cerro del otro lado, el nivel se rompio: no es defensa.
            if lado == "Soporte" and ult["c"] < p * (1 - UMBRAL_TOQUE):
                continue
            if lado == "Resistencia" and ult["c"] > p * (1 + UMBRAL_TOQUE):
                continue
            cands.append((n, abs(precio - p) / precio, p, lado))
        cands.sort(key=lambda z: (-z[0], z[1]))
        for n, _, p, lado in cands[:4]:
            feat = features_toque(kl, p, precio, ahora, lado)
            if not feat or feat.get("npiv", 0) < 3:
                continue
            sc = score_toque(feat)
            if sc is None:
                continue
            if not enfriar(est, f"toques:{int(p / 500) * 500}", 6, ahora):
                continue
            if sc >= 0.80:
                tier = "alto"
            elif sc >= 0.60:
                tier = "medio"
            else:
                tier = "frágil, posible ruptura"
            return (
                f"🧱 {lado} {fmt_miles(p)} probado {n} veces en {horas}h. "
                f"Aguante 4h (0,5%): {sc * 100:.0f}% ({tier}). No es entrada."
            )
        return None
    except Exception:
        return None
