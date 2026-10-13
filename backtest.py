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
        print(f"Sin historial en la nube ({e}). Modo demo con datos de ejemplo.")
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


def precio_en(velas, cuando):
    ant = None
    for v in velas:
        if v["t"] <= cuando:
            ant = v
        else:
            break
    return ant["c"] if ant else None


def atr_en(velas, cuando):
    prev = [v for v in velas if v["t"] <= cuando][-15:-1]
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
            "r": round(eq, 1), "pf": round(gan / per, 2) if per else float("inf"),
            "exp": round(eq / n, 2), "dd": round(dd, 1)}


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


def main():
    hist = cargar_historial()
    senales = [h for h in hist if h.get("bias") in ("ALZA", "BAJA")
               and h.get("conf", 0) >= 45 and h.get("precio")]
    print(f"Senales evaluables: {len(senales)}")
    if len(senales) < 4:
        print("Muy pocas para backtest serio. Vuelve en unos dias.")
        return
    velas = velas_1h()
    res = []
    for s in senales:
        try:
            t0 = datetime.datetime.fromisoformat(s["t"])
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
    if len(res) < 4:
        print("Velas insuficientes para evaluar. Intenta mas tarde.")
        return
    if len(res) >= 4:
        _tr, _te = partir_purgado(len(res))
        try:
            import statistics as _st
            _rs = [x["r"] for x in res]
            _sh = _st.mean(_rs) / (_st.pstdev(_rs) or 1.0)
        except Exception:
            _sh = 0.0
        print(f"Split purgado: train={len(_tr)} test={len(_te)} | Puerta: {puerta_trials(len(res), round(_sh, 2))}")
    corte = len(res) // 2
    m_in, m_out, m_all = metricas(res[:corte]), metricas(res[corte:]), metricas(res)
    print("\n===== BACKTEST (regla del bot, plan 2R) =====")
    for nombre, m in (("IN-SAMPLE ", m_in), ("OUT-SAMPLE", m_out), ("TOTAL     ", m_all)):
        print(f"{nombre}: n={m['n']} acierto={m['pct']}% R={m['r']:+} PF={m['pf']} "
              f"exp={m['exp']}R dd={m['dd']}R")
    print("\nRegla honesta: si OUT es parecido a IN, el sistema es real. "
          "Si OUT se derrumba, era suerte del pasado.")


if __name__ == "__main__":
    main()
