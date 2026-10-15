#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest.py - BACKTEST honesto del Vigilante BTC.

Repite TU historial real (rama 'estado' -> historial.jsonl, publico en GitHub)
con la MISMA regla de evaluacion del bot (umbral ATR, 8 h, plan 2R) y reporta:
 - in-sample (primera mitad) vs out-of-sample (segunda mitad): sin autoenganos
 - precision, R total, profit factor, expectancy, drawdown maximo en R

Uso:  python backtest.py   (lee el historial de la nube; si no hay, usa demo)
"""
import datetime
import json
import math
import statistics
import urllib.request

HIST_URL = "https://raw.githubusercontent.com/LuiferX/vigilante-btc/estado/historial.jsonl"
BASE = "https://fapi.binance.com/fapi/v1"
VISION = "https://data-api.binance.vision/api/v3"


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "vigilante-bt/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def cargar_historial():
    try:
        req = urllib.request.Request(HIST_URL, headers={"User-Agent": "vigilante-bt/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
        hist = [json.loads(line) for line in txt.splitlines() if line.strip()]
        print(f"Historial real: {len(hist)} pasadas")
        return hist
    except Exception as e:  # noqa: BLE001
        print(f"[DEMO] Sin historial en la nube ({e}). Modo demo con datos de ejemplo.")
        ahora = datetime.datetime.now(datetime.timezone.utc)
        return [
            {"t": (ahora - datetime.timedelta(hours=30 - i)).isoformat(),
             "precio": 83000, "bias": ("ALZA" if i % 2 == 0 else "BAJA"),
             "conf": 60, "motivo": "demo", "tipo": "alerta", "grade": "B"}
            for i in range(12)
        ]


def velas_1h():
    for base, path in ((BASE, "/klines?symbol=BTCUSDT&interval=1h&limit=1000"),
                       (VISION, "/klines?symbol=BTCUSDT&interval=1h&limit=1000")):
        try:
            data = fetch(base + path)
            return [
                {"t": datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc),
                 "c": float(k[4]), "h": float(k[2]), "l": float(k[3])}
                for k in data
            ]
        except Exception:
            continue
    raise SystemExit("Sin velas: ni fapi ni vision responden")


CIERRE_1H = datetime.timedelta(hours=1)


def precio_en(velas, cuando):
    """Precio de la última vela CERRADA a `cuando` (sin lookahead)."""
    ant = None
    for v in velas:
        if v["t"] + CIERRE_1H <= cuando:
            ant = v
        else:
            break
    return ant["c"] if ant else None


def atr_en(velas, cuando):
    prev = [v for v in velas if v["t"] + CIERRE_1H <= cuando][-14:]
    if len(prev) < 5:
        return None
    trs = [v["h"] - v["l"] for v in prev]
    return sum(trs) / len(trs)


def metricas(res):
    n = len(res)
    if not n:
        return None
    hits = [x["hit"] for x in res]
    rs = [x["r"] for x in res]
    gan = sum(x for x in rs if x > 0)
    per = -sum(x for x in rs if x < 0)
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in rs:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n": n, "pct": round(sum(hits) / n * 100, 1),
            "r": round(eq, 1), "pf": (round(gan / per, 2) if per else None),
            "exp": round(eq / n, 2), "dd": round(dd, 1)}


def sharpe_ratio(rs):
    """Sharpe por trade (media / stdev muestral) de una lista de R.

    Pura/stdlib. Devuelve None si n<5 o si la desv. es 0
    (muestra insuficiente para un Sharpe estable).
    """
    rs = list(rs)
    if len(rs) < 5:
        return None
    mu = statistics.mean(rs)
    sd = statistics.stdev(rs)
    if not sd:
        return None
    return mu / sd


def costo_bps(atr_pct, spread_bps=3.0):
    """Estimador dinamico simple de costos en bps. Puro.

    Formula: spread_bps/2 + K*sqrt(atr_pct), con atr_pct en tanto por uno
    (p.ej. 0.005 = 0.5%) y K=120 bps.

    Calibracion: atr 0.5% -> 1.5 + 120*sqrt(0.005) ~= 10.0 bps totales,
    dentro del rango 8-12 bps buscado.
    Limites: modelo didactico, no microestructura; valido aprox. para
    atr_pct en [0, 0.05]; si atr_pct<=0 devuelve solo spread/2; ignora
    funding/fees fijos y slippage extremo en saltos de volatilidad.
    """
    k = 120.0
    base = float(spread_bps) / 2.0
    try:
        a = float(atr_pct)
    except (TypeError, ValueError):
        return round(base, 2)
    if a <= 0:
        return round(base, 2)
    return round(base + k * math.sqrt(a), 2)


def _norm_cdf(x):
    """CDF normal estandar via math.erf. Pura/interna."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    """Inversa de la CDF normal (aprox. de Acklam). Pura/interna.

    Valida para p en (0,1); clamp interno a [1e-12, 1-1e-12].
    """
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    a1, a2, a3, a4, a5, a6 = (-3.969683028665376e+01, 2.209460984245205e+02,
                              -2.759285104469687e+02, 1.383577518672690e+02,
                              -3.066479806614716e+01, 2.506628277459239e+00)
    b1, b2, b3, b4, b5 = (-5.447609879822406e+01, 1.615858368580409e+02,
                          -1.556989798598866e+02, 6.680131188771972e+01,
                          -1.328068155288572e+01)
    c1, c2, c3, c4, c5, c6 = (-7.784894002430293e-03, -3.223964580411365e-01,
                              -2.400758277161838e+00, -2.549732539343734e+00,
                              4.374664141464968e+00, 2.938163982698783e+00)
    d1, d2, d3, d4 = (7.784695709041462e-03, 3.224671290700398e-01,
                      2.445134137142996e+00, 3.754408661907416e+00)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / \
               ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / \
                ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q / \
           (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0)


def deflated_sharpe(sr, T, skew, kurt, n_trials):
    """Deflated Sharpe Ratio (Bailey-Lopez de Prado 2014). Pura.

    PROXY DOCUMENTADO: sin la matriz de retornos de los K trials no se
    puede estimar V (varianza entre los Sharpe de los trials) ni sus
    correlaciones; se usa V ~= 1/T (Sharpe nulo ~ N(0, 1/T)). Es solo
    una referencia informativa contra data-mining, no una puerta de trading.

    Args:
        sr: Sharpe observado (mismo periodo que T).
        T: n. observaciones (trades). Requiere T>=5.
        skew: asimetria (gamma3) de los R.
        kurt: curtosis CRUDA (gamma4; 3.0 = normal). No exceso.
        n_trials: K, n. de configuraciones probadas. K<=1 -> SR0=0.

    Formula:
        SR0 = sqrt(V)*((1-g)*ppf(1-1/K) + g*ppf(1-1/(K*e))),
        con g=0.5772 (Euler-Mascheroni), e=2.718...
        DSR = Phi((sr-SR0)*sqrt(T-1) / sqrt(1-skew*sr+(kurt-1)/4*sr^2)).
        Phi via math.erf. Devuelve None si inputs insuficientes.
    """
    try:
        sr = float(sr)
        T = int(T)
        skew = float(skew)
        kurt = float(kurt)
        k = int(n_trials)
    except (TypeError, ValueError):
        return None
    if T < 5 or k < 1:
        return None
    if k <= 1:
        sr0 = 0.0
    else:
        gamma = 0.5772156649015329
        v = 1.0 / T
        q1 = _norm_ppf(1.0 - 1.0 / k)
        q2 = _norm_ppf(1.0 - 1.0 / (k * math.e))
        sr0 = math.sqrt(v) * ((1.0 - gamma) * q1 + gamma * q2)
    denom2 = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom2 <= 1e-12:
        return None
    stat = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom2)
    dsr = _norm_cdf(stat)
    return min(max(dsr, 0.0), 1.0)


def partir_purgado(n, train_frac=0.5, embargo=2):
    """Split purgado con embargo: train = primeros int(n*frac), salta embargo, test = resto."""
    n_train = int(n * train_frac)
    train = list(range(max(0, n_train)))
    inicio_test = n_train + max(0, embargo)
    test = list(range(inicio_test, n)) if inicio_test < n else []
    return train, test


def puerta_trials(n_trials, mejor_sharpe):
    """Puerta anti-overfit: pocos trials / exigir DSR / ok (informativo)."""
    if n_trials < 5:
        return f"pocos trials: n={n_trials} insuficiente para concluir"
    if n_trials >= 10 or mejor_sharpe < 1.0:
        return (f"exigir DSR antes de tocar umbrales "
                f"(Deflated Sharpe Ratio DSR pendiente, n={n_trials}, sharpe={mejor_sharpe})")
    return f"ok: n={n_trials} sharpe={mejor_sharpe} suficiente para evaluar"


def pf_por_grupo(res, clave):
    """PF por grupo (sesion o grade). Pura/informativa.

    Si clave=="sesion": agrupa por sesion buscando NY|Asia|Londres|noche
    en motivo (si no aparece, "s/d"). Si clave=="grade": agrupa por
    grade (grade o "?"). Devuelve {grupo: metricas(sub)}.
    """
    grupos = {}
    for x in res:
        if clave == "sesion":
            motivo = str(x.get("motivo", "") or "")
            g = "s/d"
            for ses in ("NY", "Asia", "Londres", "noche"):
                if ses in motivo:
                    g = ses
                    break
        elif clave == "grade":
            g = x.get("grade") or "?"
        else:
            g = "s/d"
        grupos.setdefault(g, []).append(x)
    return {g: metricas(sub) for g, sub in grupos.items()}


def main():
    hist = cargar_historial()
    senales = [h for h in hist if h.get("bias") in ("ALZA", "BAJA")
               and h.get("conf", 0) >= 45 and h.get("precio")]
    print(f"Senales evaluables: {len(senales)}")
    if len(senales) < 4:
        print("Muy pocas para backtest serio. Vuelve en unos dias.")
        return
    velas = velas_1h()
    senales = sorted(senales, key=lambda s: str(s.get("t", "")))
    res = []
    atr_pcts = []
    for s in senales:
        try:
            t0 = datetime.datetime.fromisoformat(str(s["t"]).strip().replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
        p0 = precio_en(velas, t0)
        p1 = precio_en(velas, t0 + datetime.timedelta(hours=8))
        at = atr_en(velas, t0)
        if p0 is None or p1 is None or not at:
            continue
        umbral = max(0.002, (at / p0) * 0.5)
        mov = (p1 - p0) / p0
        hit = 1 if ((mov >= umbral) if s["bias"] == "ALZA" else (mov <= -umbral)) else 0
        res.append({"t": s["t"], "bias": s["bias"], "hit": hit, "r": 2 if hit else -1,
                    "motivo": s.get("motivo", ""), "grade": s.get("grade", "?")})
        atr_pcts.append(at / p0)
    if len(res) < 4:
        print("Velas insuficientes para evaluar. Intenta mas tarde.")
        return
    if len(res) >= 4:
        _tr, _te = partir_purgado(len(res))
        try:
            import statistics as _st
            _rs = [x["r"] for x in res]
            _sh = _st.mean(_rs) / _st.stdev(_rs) if len(_rs) >= 5 and _st.stdev(_rs) else 0.0
        except Exception:
            _sh = 0.0
        print(f"Split purgado: train={len(_tr)} test={len(_te)} | Puerta: {puerta_trials(len(res), round(_sh, 2))}")
    idx_tr, idx_te = partir_purgado(len(res))
    m_in, m_out, m_all = metricas([res[i] for i in idx_tr]), metricas([res[i] for i in idx_te]), metricas(res)
    print("\n===== BACKTEST (regla del bot, plan 2R) =====")
    for nombre, m in (("IN-SAMPLE ", m_in), ("OUT-SAMPLE", m_out), ("TOTAL     ", m_all)):
        print(f"{nombre}: n={m['n']} acierto={m['pct']}% R={m['r']:+} PF={m['pf'] if m['pf'] is not None else 'n/d'} "
              f"exp={m['exp']}R dd={m['dd']}R")
    print("\nRegla honesta: si OUT es parecido a IN, el sistema es real. "
          "Si OUT se derrumba, era suerte del pasado.")
    # --- Informativo (no cambia regla 2R ni corte IN/OOS) ---
    rs_in = [x["r"] for x in [res[i] for i in idx_tr]]
    rs_out = [x["r"] for x in [res[i] for i in idx_te]]
    rs_all = [x["r"] for x in res]
    sh_in, sh_out, sh_all = sharpe_ratio(rs_in), sharpe_ratio(rs_out), sharpe_ratio(rs_all)
    fmt = lambda v: f"{v:+.2f}" if v is not None else "n/d"
    print(f"Sharpe R: IN={fmt(sh_in)} OUT={fmt(sh_out)} ALL={fmt(sh_all)} (n>=5 o n/d)")
    n_trials = len(res)  # proxy documentado: n senales evaluadas (sin matriz de trials)
    if sh_out is None:
        print(f"DSR OUT=n/d (n_trials={n_trials} como proxy: n senales evaluadas; T={len(rs_out)})")
    else:
        mu_o = statistics.mean(rs_out)
        sd_o = statistics.stdev(rs_out) if len(rs_out) >= 2 else 0.0
        skew_o = sum((x - mu_o) ** 3 for x in rs_out) / len(rs_out) / (sd_o ** 3) if sd_o else 0.0
        kurt_o = sum((x - mu_o) ** 4 for x in rs_out) / len(rs_out) / (sd_o ** 4) if sd_o else 3.0
        dsr = deflated_sharpe(sh_out, len(rs_out), skew_o, kurt_o, n_trials)
        txt = f"{dsr:.2f}" if dsr is not None else "n/d"
        print(f"DSR OUT={txt} (n_trials={n_trials} como proxy: n senales evaluadas; T={len(rs_out)})")
    if atr_pcts:
        atr_medio = statistics.mean(atr_pcts)
        costo = costo_bps(atr_medio)
        umbral_medio = statistics.mean(max(0.002, a * 0.5) for a in atr_pcts)
        costo_r = costo / (umbral_medio * 10000.0)
        print(f"Con costos ~{costo:.1f}bps (ATR medio {atr_medio * 100:.2f}%) "
              f"el expectancy cae ~{costo_r:.2f}R por trade (informativo, no resta al R publicado).")
    # --- PF por grupo (informativo, no cambia regla 2R ni corte IN/OOS) ---
    print("PF por sesion:")
    for g, m in pf_por_grupo(res, "sesion").items():
        if m["n"] >= 4:
            print(f"  {g}: n={m['n']} acierto={m['pct']}% PF={m['pf'] if m['pf'] is not None else 'n/d'}")
        else:
            print(f"  {g}: pocos (n={m['n']})")
    print("PF por grado:")
    for g, m in pf_por_grupo(res, "grade").items():
        if m["n"] >= 4:
            print(f"  {g}: n={m['n']} acierto={m['pct']}% PF={m['pf'] if m['pf'] is not None else 'n/d'}")
        else:
            print(f"  {g}: pocos (n={m['n']})")


if __name__ == "__main__":
    main()
