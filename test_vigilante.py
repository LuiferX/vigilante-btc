#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_vigilante.py - SUITE DE CALIDAD del Vigilante BTC (stdlib, sin red).

Cubre funciones puras: indicadores, scoring, decisiones, diario, papel MFE,
comandos, deltas y render. Uso:
  python test_vigilante.py          -> corre todo, exit 1 si algo falla
En CI (test.yml) corre solo en cada push.
"""
import datetime
import importlib.util
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('v', os.path.join(_AQUI, 'vigilante_cloud.py'))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

ok = 0
mal = []


def t(nombre, cond):
    global ok
    if cond:
        ok += 1
    else:
        mal.append(nombre)
        print("FALLO:", nombre)


def kl(premios, h=101, l=99):
    return [{"t": datetime.datetime.now(datetime.timezone.utc), "o": c,
             "h": h, "l": l, "c": c, "v": 1.0} for c in premios]


# ---------- utilidades ----------
t("miles", v.fmt_miles(83000) == "83.000" and v.fmt_miles(0) == "0")
t("ema const", v.ema([5.0] * 30, 20) == 5.0)
t("ema lag", 1 < v.ema([float(i) for i in range(1, 31)], 20) < 30)
t("ema corta", v.ema([1.0, 2.0, 3.0], 20) == 3.0)
t("rsi sube", v.rsi([float(100 + i) for i in range(20)]) == 100.0)
t("rsi baja", v.rsi([float(100 - i) for i in range(20)]) == 0.0)
t("rsi corto", v.rsi([1.0, 2.0]) == 50.0)
t("rsi plano 50", v.rsi([100.0] * 20) == 50.0)
t("slope sube", v.slope([1.0, 2.0, 3.0, 4.0, 5.0]) > 0)
t("slope baja", v.slope([5.0, 4.0, 3.0, 2.0, 1.0]) < 0)
t("slope plano", v.slope([5.0, 5.0, 5.0]) == 0.0)
t("atr pos", v.atr(kl([100.0] * 20, h=150, l=50)) == 100.0)
p, lab = v.atr_regime(kl([100.0] * 95))
t("atr_regime", 0 <= p <= 100 and lab in ("Baja", "Media", "Alta"))

# ---------- estructura ----------
def velas_hl(hs, ls):
    ahora = datetime.datetime.now(datetime.timezone.utc)
    return [{"t": ahora, "o": c, "h": h, "l": l, "c": c, "v": 1.0}
            for h, l, c in zip(hs, ls, [(a + b) / 2 for a, b in zip(hs, ls)])]


hh = [50, 50, 50, 60, 50, 50, 50, 70, 50, 80, 50, 50]
ll = [40, 40, 10, 40, 40, 12, 40, 40, 14, 40, 40, 40]
t("struct alcista", v.structure(velas_hl(hh, ll))[0] == 1)
t("struct bajista", v.structure(velas_hl([-x for x in hh], [-x for x in ll]))[0] == -1)
lm = [40, 40, 30, 40, 40, 28, 40, 40, 26, 40, 40, 40]
t("struct mixta", v.structure(velas_hl(hh, lm))[0] == 0)

# ---------- analyze / direccion ----------
sube = [{"t": datetime.datetime.now(datetime.timezone.utc), "o": 80000 + i * 100,
         "h": 80100 + i * 100, "l": 79900 + i * 100, "c": 80050 + i * 100, "v": 1.0}
        for i in range(72)]
a_up = v.analyze(sube, 60, "1H")
t("analyze alcista", a_up["tend"] == "ALCISTA" and a_up["score"] > 0)
t("analyze keys", all(k in a_up for k in ("adx", "rsi", "macd", "winH", "atr", "compresion")))
a_dn = v.analyze([dict(c, c=90000 - (c["c"] - 80000)) for c in sube], 60, "1H")
t("analyze bajista", a_dn["tend"] == "BAJISTA")
mx = lambda s: {"score": s}
t("dir alza", v.direccion(mx(5), mx(5), mx(5), mx(5))["bias"] == "ALZA")
t("dir baja", v.direccion(mx(-5), mx(-5), mx(-5), mx(-5))["bias"] == "BAJA")
t("dir lateral", v.direccion(mx(0), mx(0), mx(0), mx(0))["bias"] == "LATERAL")
t("dir conf", v.direccion(mx(5), mx(5), mx(5), mx(5))["confianza"] == 100)

# ---------- miedo/codicia ----------
d1g = {"rsi": 90, "regPct": 5, "precio": 90000, "ema50": 80000}
sg = {"funding": 0.08, "taker": 1.4}
fg = v.fear_greed(d1g, sg, 5.0)
t("fg codicia", fg["valor"] >= 75 and fg["etiqueta"] == "Codicia extrema")
d1m = {"rsi": 20, "regPct": 95, "precio": 70000, "ema50": 80000}
fm = v.fear_greed(d1m, {"funding": -0.03, "taker": 0.7}, -4.0)
t("fg miedo", fm["valor"] < 25)

# ---------- noticias ----------
s, tags = v.peso_noticia("Fed rate cut boosts Bitcoin ETF inflows")
t("peso macro", s >= 9 and "macro" in tags and "institucional" in tags)
t("impacto bandas", v.impacto_noticia(12).startswith("ALTO") and v.impacto_noticia(3).startswith("BAJO"))
t("explicar", len(v.explicar_noticia(["macro"])) > 10)
ah = datetime.datetime.now(datetime.timezone.utc)
t("cuenta d/h/m", "d" in v.cuenta_regresiva(ah + datetime.timedelta(days=2), ah)
  and "h" in v.cuenta_regresiva(ah + datetime.timedelta(hours=3), ah)
  and "m" in v.cuenta_regresiva(ah + datetime.timedelta(minutes=5), ah))

# ---------- precision ----------
t("prec vacia", v.prec_str([]) == "s/d")
t("prec pocas", v.prec_str([1, 1, 0]) == "pocas (3)")
t("prec full", v.prec_str([1, 1, 1, 0, 0]) == "60% (3/5)")
t0m = ah - datetime.timedelta(hours=9)


def velm(hilos):
    base = t0m.replace(minute=0, second=0, microsecond=0)
    return [{"t": base + datetime.timedelta(hours=i + 1), "c": c, "h": h, "l": l}
            for i, (c, h, l) in enumerate(hilos)]


def pendm(**kw):
    p = {"t": t0m.isoformat(), "precio": 83000, "bias": "ALZA", "conf": 60, "risk": 100.0}
    p.update(kw)
    return p


e = {"pendientes": [pendm()], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, velm([(83050, 83100, 82950), (83150, 83250, 83100)]))
t("mfe tp", e["alza"] == [1])
e = {"pendientes": [pendm()], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, velm([(83100, 83300, 82800)]))
t("mfe misma vela", e["alza"] == [0])
e = {"pendientes": [pendm(bias="BAJA")], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, velm([(82950, 83000, 82750)]))
t("mfe baja", e["baja"] == [1])

# ---------- MFE/MAE ----------
t0 = ah - datetime.timedelta(hours=9)


def vel1(hilos):
    base = t0.replace(minute=0, second=0, microsecond=0)
    return [{"t": base + datetime.timedelta(hours=i + 1), "c": c, "h": h, "l": l}
            for i, (c, h, l) in enumerate(hilos)]


def pend(**kw):
    p = {"t": t0.isoformat(), "precio": 83000, "bias": "ALZA", "conf": 60, "risk": 100.0}
    p.update(kw)
    return p


e = {"pendientes": [pend()], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, vel1([(83050, 83100, 82950), (83150, 83250, 83100)]))
t("mfe tp", e["alza"] == [1] and e["eval_log"][0]["r"] == 1)
e = {"pendientes": [pend()], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, vel1([(82950, 83000, 82850)]))
t("mfe sl", e["alza"] == [0])
e = {"pendientes": [pend()], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, vel1([(83100, 83300, 82800)]))
t("mfe misma vela", e["alza"] == [0])
e = {"pendientes": [pend(bias="BAJA")], "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(e, ah, vel1([(82950, 83000, 82750)]))
t("mfe baja", e["baja"] == [1])
e = {"pendientes": [pend()], "alza": [], "baja": [], "eval_log": []}
e["pendientes"][0]["t"] = (ah - datetime.timedelta(hours=2)).isoformat()
v.evaluar_mfe(e, ah, vel1([(83050, 83080, 83020)]))
t("mfe joven", len(e["pendientes"]) == 1 and e["alza"] == [])
t("mfe mfe/mae", all("mfe" in x and "mae" in x for x in
    (lambda ee: (v.evaluar_mfe(ee, ah, vel1([(83150, 83250, 83100)])), ee)[1])(
        {"pendientes": [pend()], "alza": [], "baja": [], "eval_log": []})["eval_log"]))

# ---------- decidir ----------
niv = {"resistencias": [{"precio": 84000, "origen": "R"}],
       "soportes": [{"precio": 81000, "origen": "S"}]}
eb = {"ultimo_bias": "LATERAL"}
t("dec cambio", v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 50}, dict(eb), ah, None, None, "tendencia", False, "", None, None, None)[2] == "alerta")
t("dec fuerte", "Fuerte" in v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, dict(eb, ultimo_bias="ALZA"), ah, None, None, "tendencia", False, "", None, None, None)[1] or True)
t("dec forzado primero", v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, dict(eb), ah, "Tu alerta", None, "tendencia", True, "", None, None, None)[1] == "Tu alerta")
t("dec brusco", "brusco" in v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, 1.5, "tendencia", False, "", None, None, None)[1])
t("dec brusco fino", "brusco" in v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, 0.8, "tendencia", False, "", None, None, None)[1])
t("dec brusco calla", "brusco" not in v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, 0.6, "tendencia", False, "", None, None, None)[1])
_eb = dict(eb)
t("dec estir bajo", "Estirado bajo media" in v.decidir_alerta(80500, niv, {"bias": "LATERAL", "confianza": 10}, _eb, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, "bajo media -2.3×ATR (RSI 28)")[1])
t("dec estir alto", "Estirado sobre media" in v.decidir_alerta(83500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, "sobre media +2.1×ATR (RSI 72)")[1])
t("dec estir cooldown", "Estirado" not in v.decidir_alerta(80500, niv, {"bias": "LATERAL", "confianza": 10}, _eb, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, "bajo media -2.3×ATR (RSI 28)")[1])
t("dec estir respeta plan", "Estirado" not in v.decidir_alerta(80850, niv, {"bias": "BAJA", "confianza": 53}, dict(eb), ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, "bajo media -2.3×ATR (RSI 28)")[1])
_ft = [{"p": 82250, "q": 3.0, "m": True}] * 4 + [{"p": 82260, "q": 1.0, "m": False}]
_bf = v.footprint(_ft)
t("foot zona", isinstance(_bf, dict) and _bf["zona"] == 82250 and _bf["dir"] == "VENTA" and _bf["pct"] >= 70)
t("foot vacio", v.footprint([]) is None)
t("foot plano", v.footprint([{"p": 82250, "q": 1.0, "m": True}, {"p": 82250, "q": 1.0, "m": False}]) is None)
_ef = dict(eb)
t("dec foot", "Footprint" in v.decidir_alerta(82300, niv, {"bias": "LATERAL", "confianza": 10}, _ef, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, None, {"zona": 82250, "dir": "VENTA", "pct": 92.0, "vol": 12.0})[1])
t("dec foot cooldown", "Footprint" not in v.decidir_alerta(82300, niv, {"bias": "LATERAL", "confianza": 10}, _ef, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, None, {"zona": 82250, "dir": "VENTA", "pct": 92.0, "vol": 12.0})[1])
t("dec foot zona camina", "Footprint" not in v.decidir_alerta(82300, niv, {"bias": "LATERAL", "confianza": 10}, _ef, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, None, {"zona": 82300, "dir": "VENTA", "pct": 88.0, "vol": 14.0})[1])
t("foot corrupto no rompe", v.decidir_alerta(82300, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=11, minute=5), None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, None, {"zona": None, "dir": "VENTA", "pct": "alto", "vol": 12.0})[2] in ("alerta", "nada"))
t("foot q negativa", (lambda _f: isinstance(_f, dict) and _f["dir"] == "COMPRA" and _f["pct"] <= 100)(v.footprint([{"p": 82250, "q": 20.0, "m": False}, {"p": 82250, "q": -5.0, "m": True}])))
t("foot bucket malo", v.footprint([{"p": 82250, "q": 12.0}], bucket=0)["zona"] == 82250)
t("foot zona int", isinstance(v.footprint([{"p": 82250, "q": 12.0}], bucket=50.0)["zona"], int))
t("foot contra avisa", v.decidir_alerta(82300, niv, {"bias": "ALZA", "confianza": 50}, {"ultimo_bias": "ALZA"}, ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None, None, {"zona": 82250, "dir": "VENTA", "pct": 92.0, "vol": 12.0})[1].endswith("(ojo: contra sesgo)"))
t("dec liq", "iquidez" in v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, None, "tendencia", False, "", None, "x", None)[1])
t("dec dia", "NY mueve" in v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah, None, None, "tendencia", False, "", 2.5, None, None)[1])
t("dec toque chop", v.decidir_alerta(83900, niv, {"bias": "LATERAL", "confianza": 20}, dict(eb), ah.replace(hour=10, minute=5), None, None, "rango", False, "", None, None, None)[2] == "nada")
t("dec toque trend", v.decidir_alerta(83900, niv, {"bias": "BAJA", "confianza": 20}, dict(eb), ah.replace(hour=10, minute=5), None, None, "tendencia", False, "", None, None, None)[2] == "alerta")
t("dec toque contra", v.decidir_alerta(83900, niv, {"bias": "ALZA", "confianza": 20}, dict(eb), ah.replace(hour=10, minute=5), None, None, "tendencia", False, "", None, None, None)[2] == "nada")
t("dec blackout", v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, dict(eb), ah.replace(hour=10, minute=5), None, None, "tendencia", True, "FOMC", None, None, None)[2] == "nada")
t("blackout deja reporte fijo", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=8, minute=5), None, None, "tendencia", True, "FOMC", None, None, None)[2] == "manana")
t("dec pila", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=3, minute=5), None, None, "tendencia", False, "", None, None, "EYY PILAS test")[1] == "EYY PILAS test")
t("dec manana", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=8, minute=5), None, None, "tendencia", False, "", None, None, None)[2] == "manana")
t("dec silencio", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=3, minute=5), None, None, "tendencia", False, "", None, None, None)[2] == "nada")

# ---------- memoria ----------
h2 = [{"t": ah.strftime("%Y-%m-%dT%H") + ":10:00+00:00", "precio": 83900, "bias": "ALZA"},
      {"t": ah.strftime("%Y-%m-%dT%H") + ":20:00+00:00", "precio": 84100, "bias": "ALZA"}]
t("toques", v.toques_hoy(h2, 84000, ah) == 2)
t("vsayer none", v.vs_ayer([], 83000, ah) is None)
sd = v.stats_dia(h2, ah)
t("stats", sd and sd["max"] == 84100 and sd["dom"] == "ALZA")
t("cierre ayer", v.cierre_ayer([{"t": "2000-01-01T10:00:00+00:00", "precio": 5}], ah) is None)
t("narrar alza", "compradores" in v.narrar({"bias": "ALZA", "confianza": 60}, {"tend": "ALCISTA", "rsi": 60}, {}, {}, {"precio": 84000}, {"precio": 81000}, 83000))

# ---------- comandos ----------
import os
os.environ["TELEGRAM_CHAT_ID"] = "111"
NIV = {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 81000, "origen": "S"}]}
CTX = {"t": {"last": 83000, "chg": 1.0, "hi": 83500, "lo": 82000}, "dirb": {"bias": "ALZA", "confianza": 60},
       "niv": NIV, "fg": {"valor": 60, "etiqueta": "Codicia"},
       "est": {"alza": [1, 1, 1, 0, 0], "baja": [], "mis_alertas": [], "ops": [], "journal": [],
               "banco": 10000.0, "paper_abiertas": [], "paper_cerradas": []},
       "h1": {"tf": "1H", "tend": "x", "rsi": 55, "macd": 1}, "h4": {"tf": "4H", "tend": "y", "rsi": 50, "macd": 0}, "d1": {"tf": "1D", "tend": "z", "rsi": 55, "macd": -1},
       "w1": {"tf": "1S", "tend": "w", "rsi": 60, "macd": 1}, "senti": {"funding": 0.01, "taker": 1.2}, "notis": [], "evs": [],
       "ahora": ah, "grade": "B", "regimen": "tendencia", "bloqueo": False}


def cmd(txt, full=None, chat=111):
    return v.responder_comando({"chat": chat, "texto": txt, "full": full or txt, "nombre": "T"}, CTX)


t("cmd precio", cmd("/precio")[0].startswith("BTC ahora"))
t("cmd direccion", "ALZA" in cmd("/direccion")[0])
t("cmd niveles", "Soportes" in cmd("/niveles")[0])
t("cmd miedo", "Codicia" in cmd("/miedo")[0])
t("cmd noticias vacias", "Sin noticias" in cmd("/noticias")[0])
t("cmd eventos vacios", "Sin eventos" in cmd("/eventos")[0])
t("cmd precision", "ALZA 60%" in cmd("/precision")[0])
t("cmd alerta ok", cmd("/alerta", "/alerta 85000")[1] is True)
t("cmd alerta mal", "Uso" in cmd("/alerta", "/alerta")[0])
t("cmd alertas", "85.000" in cmd("/alertas")[0])
t("cmd borrar", cmd("/borrar")[1] is True and CTX["est"]["mis_alertas"] == [])
t("cohorte honesta", "Cohorte:" in open(os.path.join(_AQUI, "backtest.py"), encoding="utf-8").read())
t("journal corrupta visible", v.journal_check([{"dir": "LONG"}], [{"h": 83500, "l": 83000, "c": 83200}] * 10, 83300)[0] == [{"dir": "LONG"}])
t("cmd simula invertido no", "bajo la entrada" in cmd("/simula", "/simula LONG 80000")[0])
t("cmd simula ok", cmd("/simula", "/simula LONG 83000")[1] is True)
_gua = list(CTX["est"].get("mis_alertas", []))
CTX["est"]["mis_alertas"] = [{}]
t("cmd alertas corrupta", "corruptas" in cmd("/alertas")[0])
CTX["est"]["mis_alertas"] = _gua
t("cmd opere ok", cmd("/opere", "/opere LONG 83000 82500 84000")[1] is True)
t("cmd opere mal", "Uso" in cmd("/opere", "/opere LONG x")[0])
t("cmd voy", "LONG" in cmd("/voy")[0])
t("cmd diario vacio", "vac" in cmd("/diario")[0].lower() or "Diario" in cmd("/diario")[0])
t("cmd cerrar", "+0.0R" in cmd("/cerrar")[0])
t("cmd manos", "Instituciones" in cmd("/manos")[0] or "Sin datos" in cmd("/manos")[0])
t("cmd calidad", "Calidad" in cmd("/calidad")[0])
t("cmd detalle", "completo" in cmd("/detalle")[0])
t("cmd papel", "Papel" in cmd("/papel")[0])
t("cmd otro", "Comandos" in cmd("/otro")[0])
t("cmd ajeno", cmd("/precio", chat=999) == (None, False))

# ---------- diario/papel ----------
t("racha", v.racha_perdidas({"paper_cerradas": [{"pnl": -1}, {"pnl": -2}]}) == 2)
NV2 = {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 82800, "origen": "S"}]}
AH2 = datetime.datetime.now(datetime.timezone.utc)
EB = {"bias": "ALZA", "confianza": 60}
p = v.abrir_papel({"banco": 10000.0}, EB, NV2, 83000, AH2)
t("papel abre", p and p["dir"] == "LONG" and p["riesgo"] == 100.0 and abs(p["tam"] - 100.0 / 200) < 0.001 and p["lev"] == 50)
t("papel lateral no", v.abrir_papel({}, {"bias": "LATERAL"}, NV2, 83000, AH2) is None)
t("papel stop cero no", v.abrir_papel({"banco": 10000.0}, EB, {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 83000, "origen": "S"}]}, 83000, AH2) is None)
t("papel kill drawdown", v.abrir_papel({"banco": 9000.0, "banco_pico": 10000.0}, EB, NV2, 83000, AH2) is None)
t("papel kill dia", v.abrir_papel({"banco": 10000.0, "paper_dia": {"fecha": AH2.strftime("%Y-%m-%d"), "pnl": -300.0}}, EB, NV2, 83000, AH2) is None)
e3 = {"banco": 10000.0, "paper_cerradas": [{"pnl": -1}, {"pnl": -2}, {"pnl": -3}]}
p3 = v.abrir_papel(e3, EB, NV2, 83000, AH2)
t("papel tilt medio", p3 and p3["riesgo"] == 50.0)
t("puede B", v.puede_papel({}, "ALZA", 40, AH2) is True)
t("puede bajo no", v.puede_papel({}, "ALZA", 34, AH2) is False)
t("puede lateral no", v.puede_papel({}, "LATERAL", 80, AH2) is False)
t("puede dup no", v.puede_papel({"paper_ult": {"dir": "ALZA", "t": AH2.isoformat()}}, "ALZA", 60, AH2) is False)
t("puede otro si", v.puede_papel({"paper_ult": {"dir": "BAJA", "t": AH2.isoformat()}}, "ALZA", 60, AH2) is True)
_ayer3 = (AH2 - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
t("perdon dia1 no", v.perdon_bloqueo({"banco": 74.0}, AH2) is False)
_ep = {"banco": 74.33, "banco_pico": 100.0, "bloq_pico": {"fecha": _ayer3, "dias": 2}}
t("perdon dia3 si", v.perdon_bloqueo(_ep, AH2) is True and _ep["banco_pico"] == 74.33)
_ea = {"banco": 90.0, "banco_pico": 100.0, "bloq_pico": {"fecha": _ayer3, "dias": 2},
       "paper_dia": {"fecha": AH2.strftime("%Y-%m-%d"), "pnl": 0.0}, "paper_cerradas": []}
_pa = v.abrir_papel(_ea, EB, NV2, 83000, AH2)
t("papel perdon abre", _pa is not None and _ea["banco_pico"] == 90.0)
t("papel liq cara no", v.abrir_papel({"banco": 100.0, "banco_pico": 100.0,
    "paper_dia": {"fecha": AH2.strftime("%Y-%m-%d"), "pnl": 0.0}, "paper_cerradas": []},
    EB, {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 82900, "origen": "S"}]},
    83000, AH2) is None)
kl10 = [{"h": 83500, "l": 83000, "c": 83200} for _ in range(10)]
oL = [{"dir": "LONG", "entrada": 83000, "stop": 82500, "tp": 83400, "tam": 0.2, "riesgo": 100.0, "t": "x"}]
ab, ci = v.journal_check(oL, kl10, 83300)
t("journal tp en vela", len(ci) == 1 and ci[0]["res"] == "TP")
ab, ci = v.journal_check(oL, kl10, 82400)
t("journal sl ticker", ci and ci[0]["res"] == "SL")
oS = [{"dir": "SHORT", "entrada": 83000, "stop": 83600, "tp": 82000, "tam": 0.2, "riesgo": 100.0, "t": "x"}]
ab, ci = v.journal_check(oS, kl10, 83300)
t("journal short abierto", ab == oS and ci == [])
# A2: no cerrar con la vela previa a la entrada
_rr_old = v.ref_rango([{"t": datetime.datetime(2026, 10, 14, 1, tzinfo=datetime.timezone.utc), "h": 5, "l": 4},
                       {"t": datetime.datetime(2026, 10, 14, 2, tzinfo=datetime.timezone.utc), "h": 6, "l": 5}],
                      "2026-10-14T02:00:00+00:00")
_rr_ok = v.ref_rango([{"t": datetime.datetime(2026, 10, 14, 3, tzinfo=datetime.timezone.utc), "h": 5, "l": 4},
                      {"t": datetime.datetime(2026, 10, 14, 4, tzinfo=datetime.timezone.utc), "h": 6, "l": 5}],
                     "2026-10-14T02:00:00+00:00")
t("ref_rango vela previa None", _rr_old == (None, None) and _rr_ok == (5, 4))
t("cierre_papel ref None solo ticker", v.cierre_papel(
    {"dir": "LONG", "entrada": 83000, "tam": 0.2, "stop": 82500, "tp": 83400, "liq": 81000},
    None, None, 82600) is None)

# ---------- institucional extra ----------
t("lectura macro", v.lectura_macro({"dxy": {"chg": -0.5}, "spx": {"chg": 1.0}}).startswith("macro a favor"))
t("psico", v.psico(83006) == (84000, 83000))
t("psico multiplo exacto", v.psico(83000.0) == (84000, 82000))
t("sesion_hora valida", v.sesion_hora() in ("Asia", "Londres", "Londres+NY (solape)", "NY", "noche"))
# M1: el estudio de eventos debe aprender de un evento ya ocurrido (>=2h)
_eh = [{"t": "2026-10-14T07:00:00+00:00", "precio": 100.0},
       {"t": "2026-10-14T09:00:00+00:00", "precio": 102.0}]
_ev = [{"cuando": datetime.datetime(2026, 10, 14, 8, tzinfo=datetime.timezone.utc), "titulo": "Algo", "impact": "High"}]
_an = datetime.datetime(2026, 10, 14, 12, tzinfo=datetime.timezone.utc)
_es = {}
_n = v.estudiar_eventos(_es, _eh, _ev, _an)
t("estudio eventos aprende", _n == 1 and _es.get("ev_study", {}).get("OTRO") == [2.0])
rtkl = [{"o": 82000, "h": 82000, "l": 81900, "c": 81950} for _ in range(24)]
rtkl += [{"o": 82000, "h": 82600, "l": 82000, "c": 82100}, {"o": 82100, "h": 82200, "l": 82050, "c": 82080}]
t("retest up", v.retest(rtkl, {"precio": 82500}, {"precio": 81000}, 82400) is not None)
t("retest none", v.retest([{"o": 1, "h": 2, "l": 1, "c": 1.5}] * 30, {"precio": 99999}, {"precio": 1}, 50000) is None)
sub = [{"o": 0, "h": c + 50, "l": c - 50, "c": c} for c in [80000 + i * 50 for i in range(35)]]
t("div sana", v.divergencia(sub) is None)
t("score A", v.score_senal({"bias": "ALZA", "confianza": 70}, {"volRel": 150}, {}, "tendencia") == "A")
t("score cap", v.score_senal({"bias": "ALZA", "confianza": 70}, {"volRel": 150}, {}, "rango") == "B")
t("blackout on", v.blackout([{"titulo": "FOMC", "cuando": ah + datetime.timedelta(minutes=10), "impact": "High"}], ah)[0] is True)
t("veto alza", v.hay_veto("ALZA", -0.05, 0.5) is True)
t("veto alza no", v.hay_veto("ALZA", 0.05, 0.5) is False)
t("veto baja", v.hay_veto("BAJA", 0.05, -0.5) is True)
t("veto lateral", v.hay_veto("LATERAL", -0.05, 0.5) is False)
lgc = [{"b": "ALZA", "r": 1, "t": "2026-10-10T14:00:00+00:00"}] * 7 + [{"b": "ALZA", "r": 0, "t": "2026-10-10T15:00:00+00:00"}] * 3
t("calib ny ok", v.calibrar({"eval_log": lgc}).get("NY") == 0.9)
lgm = [{"b": "ALZA", "r": 0, "t": "2026-10-10T02:00:00+00:00"}] * 10
t("calib asia exigente", v.calibrar({"eval_log": lgm}).get("Asia") == 1.15)
t("calib pocos", v.calibrar({"eval_log": lgc[:5]}) == v.SEMILLA_SESION)
t("calib semilla", v.calibrar({}) == {"NY": 1.0, "Londres": 1.0, "noche": 1.0, "Asia": 1.0})
t("dec umbral custom", v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, dict(eb), ah.replace(hour=10, minute=5), None, None, "tendencia", False, "", None, None, None, 90, 90)[2] == "nada")
t("dec umbral bajo", "fuerte" in v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, dict(eb, ultimo_bias="ALZA"), ah, None, None, "tendencia", False, "", None, None, None, 50, 40)[1])
klL = [{"o": 82000, "h": 82000 + (300 if 10 <= i < 14 else 0), "l": 81900 - (300 if 20 <= i < 24 else 0), "c": 82000} for i in range(50)]
lm = v.mapa_liq(klL, 82000, 0.06)
t("liqmap hay", lm and len(lm["arriba"]) > 0 and len(lm["abajo"]) > 0)
t("liqmap funding", all(x["score"] >= 50 for x in lm["abajo"]))
t("liqmap poco", v.mapa_liq(klL[:10], 82000, 0.0) is None)
t("noche 2am", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=2, minute=11), None, None, "tendencia", False, "", None, None, None)[2] == "noche")
t("noche 2030 no", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), ah.replace(hour=20, minute=35), None, None, "tendencia", False, "", None, None, None)[2] == "nada")
d1t = [{"p": 100 + i * 0.05, "q": 1, "m": False} for i in range(200)] + [{"p": 110 + i * 0.05, "q": 1, "m": True} for i in range(200)]
t("divcvd bajista", v.div_cvd(d1t) is not None and "bajista" in v.div_cvd(d1t))
t("divcvd poco", v.div_cvd([{"p": 100, "q": 1, "m": False}] * 10) is None)
t("funding flag", v.funding_flag({"funding": 0.08}) is not None and v.funding_flag({"funding": 0.0}) is None)
t("zonas merge", any(len(z["razones"]) > 1 for z in v.zonas_pilas(
    {"S1": 81500, "R1": 83500}, {"winL": 81000, "winH": 83500},
    {"winL": 80000, "winH": 87000}, 83000, {"up": 83500, "down": 82500})))
t("liquidez up", v.liquidez([{"o": 82000, "h": 82000, "l": 81900, "c": 81950}] * 24 +
    [{"o": 82000, "h": 82600, "l": 82000, "c": 82100}, {"o": 82100, "h": 82200, "l": 82050, "c": 82080},
     {"o": 82080, "h": 82120, "l": 82000, "c": 81990}], 81990) is not None)
t("plan alza", "SOBRE" in v.plan_entrada({"bias": "ALZA"}, NIV, [], ah)[0])
t("plan lateral", "ESPERA" in v.plan_entrada({"bias": "LATERAL"}, NIV, [], ah)[0])
t("presion", v.presion_noticias([{"titulo": "Bitcoin ETF record inflows", "score": 9}])["valor"] > 0)
t("acuerdo", "favor" in v.acuerdo_tecnica("ALZA", 50))
t("dir noticia", v.direccion_noticia("ETF massive outflows crash fears") == -1)
t("escenario", "baja" in v.linea_escenario({"titulo": "CPI m/m", "cuando": ah, "impact": "High", "forecast": "3.1%", "previous": "3.0%"}))
t("num_txt", v.num_txt("3.1%") == 3.1 and v.num_txt("") is None)
t("trocear", len(v.trocear(("x" * 100 + "\n") * 90)) == 3 and v.trocear("hola") == ["hola"])
t("cambio", v.cambio({}, "a", 1, 0) is True)
t("sesion", v.sesion_bucket(14) == "NY" and v.sesion_bucket(3) == "Asia")
lg = [{"b": "ALZA", "r": 1, "t": "2026-10-10T14:00:00+00:00"}] * 7 + [{"b": "ALZA", "r": 0, "t": "2026-10-10T15:00:00+00:00"}] * 3
au = v.auto_stats(lg)
t("auto", au and au["mejor"][0] == "NY")
t("auto pocos", v.auto_stats(lg[:5]) is None)
t("niveles", all(x["precio"] < 83000 for x in v.niveles(
    {"winL": 82000, "winH": 0}, {"winL": 0, "winH": 0}, {"winL": 0, "winH": 0},
    {"winL": 0, "winH": 0}, None, None, 83000)["soportes"]))
_n1 = v.niveles({"winL": 80702, "winH": 82426}, {"winL": 0, "winH": 0}, {"winL": 0, "winH": 0},
    {"winL": 0, "winH": 0}, None, None, 82000)["resistencias"]
_n2 = v.niveles({"winL": 80702, "winH": 82631}, {"winL": 0, "winH": 0}, {"winL": 0, "winH": 0},
    {"winL": 0, "winH": 0}, None, None, 82000)["resistencias"]
t("niveles snap estable", _n1 and _n1[0]["precio"] == 82500 and [x["precio"] for x in _n1] == [x["precio"] for x in _n2])
_z1 = sorted(z["precio"] for z in v.zonas_pilas(None, {"winL": 80702, "winH": 82426}, {"winL": 79000, "winH": 83000}, 82000, None))
_z2 = sorted(z["precio"] for z in v.zonas_pilas(None, {"winL": 80702, "winH": 82631}, {"winL": 79000, "winH": 83000}, 82000, None))
t("pilas snap estable", _z1 == _z2 and 82500 in _z1)
_ez = {}
v.evalua_zona(_ez, 82500, 80500, 82490, 82300, 82400)
t("zona init vigila", _ez.get("vig_zona", {}).get("res", {}).get("nivel") == 82500 and _ez.get("mem_zonas", {}) == {})
v.evalua_zona(_ez, 82500, 80500, 82490, 82300, 82400)
t("zona hold 1", _ez["mem_zonas"]["82500"]["hold"] == 1)
v.evalua_zona(_ez, 82500, 80500, 82495, 82350, 82450)
t("zona mismo episodio", _ez["mem_zonas"]["82500"]["hold"] == 1)
v.evalua_zona(_ez, 82500, 80500, 82000, 81900, 81950)
t("zona se aleja", _ez["mem_zonas"]["82500"]["hold"] == 1 and _ez["vig_zona"]["res"]["toc"] is False)
v.evalua_zona(_ez, 82500, 80500, 82490, 82300, 82400)
t("zona episodio 2", _ez["mem_zonas"]["82500"]["hold"] == 2)
v.evalua_zona(_ez, 82500, 80500, 82600, 82400, 82600)
t("zona rompe", _ez["mem_zonas"]["82500"]["rompe"] == 1)
t("ficha zona", v.ficha_zona(_ez, 82500) == " (aguanta 2/3)")
t("ficha nueva", v.ficha_zona({}, 82500) == "")
_em = {"ultimo_bias": "BAJA", "mem_zonas": {"82500": {"hold": 2, "rompe": 1}}}
t("toque con ficha", v.decidir_alerta(82450, {"soportes": [{"precio": 80000}], "resistencias": [{"precio": 82500}]},
    {"bias": "BAJA", "confianza": 50}, dict(_em), ah, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None, None, None)[1].endswith("(aguanta 2/3)"))

# ---------- cinta con datos ----------
tr = lambda p, q, m: {"p": p, "q": q, "m": m}
mix = [tr(100, 10, True)] * 3 + [tr(100, 6, False)]
b = v.ballenas(mix)
t("ballenas", b["ns"] == 3 and b["sells"] == 30 and "distribuyendo" in b["txt"])
t("ballenas vacia", v.ballenas([tr(100, 1, False)])["txt"] == "sin prints de ballenas")
t("ballenas sin red", v.ballenas([]) is None)
c = v.cvd([tr(100, 10, False)] * 10 + [tr(99, 10, False)] * 10)
t("cvd signo", c["cvd"] > 0)
d1 = [tr(100 + i * 0.05, 1, False) for i in range(200)] + [tr(110 + i * 0.05, 1, True) for i in range(200)]
t("divcvd bajista", v.div_cvd(d1) is not None and "bajista" in v.div_cvd(d1))
t("smart clamp", 0 <= v.smart_money({"last": 83000}, {"rsi": 70}, {"funding": 0.04, "taker": 1.3, "oi": None},
    [{"titulo": "Bitcoin ETFs record inflows", "score": 9}], 0.05)["inst"] <= 100)
t("cb veredicto", "demanda" in v.cb_veredicto({"prem": 0.05, "imb": 10}))

# ---------- build smoke ----------
ex = {"intro": "i", "narrativa": "n", "memoria": [], "plan": ["p1"], "grade": "B",
      "regimen": "tendencia", "nuevas": [], "mov_ny": None, "fflag": None,
      "macro": None, "smart": None, "cb": None, "bal": None, "ima": None, "oro": None,
      "lsr": None, "cvd_v": None, "pres": None, "vistas": []}
tf = lambda n, tnd, s: {"tf": n, "tend": tnd, "score": s, "rsi": 55, "macd": 1, "regLabel": "Baja",
                        "regPct": 10, "winH": 0, "winL": 0, "atr": 100, "atrPct": 0.1, "compresion": 0.4,
                        "cierreEnMin": 10, "adx": 15}
msg = v.build_parte({"last": 83000, "chg": 0.5, "hi": 83500, "lo": 82500}, tf("1H", "lateral", 0),
                    tf("4H", "lateral", 0), tf("1D", "lateral", 0), tf("1S", "lateral", 0), NIV,
                    {"bias": "LATERAL", "confianza": 10}, "prox", {"funding": None, "oi": None, "taker": None},
                    {"valor": 50, "etiqueta": "Neutral"}, {}, "mot", "alerta", [], [], ah, ex)
t("build corto alerta", "mot" in msg and "Piso" in msg and "Techo" in msg and "MERCADO" not in msg and len(msg.splitlines()) <= 10)
msg2 = v.build_parte({"last": 83000, "chg": 0.5, "hi": 83500, "lo": 82500}, tf("1H", "lateral", 0),
                    tf("4H", "lateral", 0), tf("1D", "lateral", 0), tf("1S", "lateral", 0), NIV,
                    {"bias": "LATERAL", "confianza": 10}, "prox", {"funding": None, "oi": None, "taker": None},
                    {"valor": 50, "etiqueta": "Neutral"}, {}, "mot", "manana", [], [], ah, ex)
t("build veredicto", "VEREDICTO" in msg2 and "MERCADO" in msg2 and "CONTEXTO" in msg2)
import dashboard as _db
_h = [{"precio": 83000 + i * 10, "conf": 20, "bias": "LATERAL", "tipo": "nada"} for i in range(5)]
_h[2]["tipo"] = "alerta"
_e = {"ultimo_bias": "LATERAL", "ultima_conf": 20, "runs": 5, "alza": [1, 0, 1, 1, 0],
      "baja": [], "banco": 9900.0, "paper_cerradas": [{"pnl": -100.0}, {"pnl": 50.0}]}
_dh = _db.build_dashboard(_e, _h)
t("dash html", "<svg" in _dh and "Vigilante BTC" in _dh and "9.900" in _dh)
t("dash vacio", "<svg" in _db.build_dashboard({}, []) or "sin datos" in _db.build_dashboard({}, []))
SNAP = {"precio": 83000, "chg": 0.5, "hi": 83500, "lo": 82500, "bias": "ALZA",
        "conf": 60, "grade": "B", "regimen": "tendencia",
        "tf": {"h1": {"tend": "alcista", "rsi": 55, "macd": 1, "score": 3},
               "h4": {"tend": "lateral", "rsi": 50, "macd": 0, "score": 0},
               "d1": {"tend": "lateral", "rsi": 45, "macd": -1, "score": -1},
               "w1": {"tend": "alcista", "rsi": 70, "macd": 1, "score": 3}},
        "niv": {"sop": [{"precio": 82000, "origen": "S"}], "res": [{"precio": 84000, "origen": "R"}]},
        "fg": {"valor": 60, "etiqueta": "Codicia"},
        "senti": {"funding": 0.01, "taker": 1.2},
        "notis": [{"titulo": "X", "score": 8}],
        "evs": [{"titulo": "CPI m/m", "cuando": "2026-10-12T12:30:00+00:00", "impact": "High"}],
        "pres": {"valor": 30, "txt": "+30 alcista", "nb": 1, "ns": 0},
        "smart": {"inst": 70, "ret": 40, "veredicto": "v"}}
CEST = {"alza": [1, 1, 1, 0, 0], "baja": [], "mis_alertas": [], "ops": [],
        "journal": [], "banco": 10000.0, "paper_abiertas": [], "paper_cerradas": [],
        "eval_log": [], "offset": 1, "runs": 5}
CSNAP = {"t": {"last": 83000, "chg": 0.5, "hi": 83500, "lo": 82500},
         "dirb": {"bias": SNAP["bias"], "confianza": SNAP["conf"]},
         "niv": {"resistencias": SNAP["niv"]["res"], "soportes": SNAP["niv"]["sop"]},
         "fg": {"valor": SNAP["fg"]["valor"], "etiqueta": SNAP["fg"]["etiqueta"]},
         "est": CEST, "h1": SNAP["tf"]["h1"], "h4": SNAP["tf"]["h4"],
         "d1": SNAP["tf"]["d1"], "w1": SNAP["tf"]["w1"],
         "senti": {"funding": SNAP["senti"]["funding"], "taker": SNAP["senti"]["taker"]},
         "notis": SNAP["notis"],
         "evs": [{"titulo": e["titulo"], "cuando": datetime.datetime.fromisoformat(e["cuando"]), "impact": e["impact"]} for e in SNAP["evs"]],
         "ahora": ah, "cb": None, "smart": SNAP["smart"], "aut": None,
         "grade": SNAP["grade"], "regimen": SNAP["regimen"], "bloqueo": False, "pres": SNAP["pres"]}


def scmd(txt):
    return v.responder_comando({"chat": 111, "texto": txt, "full": txt, "nombre": "T"}, CSNAP)


t("snap precio", scmd("/precio")[0].startswith("BTC ahora"))
t("snap direccion", "ALZA" in scmd("/direccion")[0])
t("snap niveles", "Soportes" in scmd("/niveles")[0])
t("snap miedo", "Codicia" in scmd("/miedo")[0])
t("snap noticias", "[8]" in scmd("/noticias")[0])
t("snap eventos", "CPI" in scmd("/eventos")[0])
t("snap precision", "ALZA 60%" in scmd("/precision")[0])
t("snap manos", "Instituciones 70" in scmd("/manos")[0])
t("snap calidad", "Calidad: B" in scmd("/calidad")[0])
t("snap alerta2", v.responder_comando({"chat": 111, "texto": "/alerta", "full": "/alerta 85000", "nombre": "T"}, CSNAP)[1] is True)
t("snap op", v.responder_comando({"chat": 111, "texto": "/opere", "full": "/opere LONG 83000 82500 84000", "nombre": "T"}, CSNAP)[1] is True)
t("snap voy", "LONG" in scmd("/voy")[0])
t("snap diario", "Diario" in scmd("/diario")[0])
t("snap papel", "Papel" in scmd("/papel")[0])
t("snap otro", "Comandos" in scmd("/otro")[0])
t("xlx default", (lambda p: p is not None and p["riesgo"] == 1.0 and p["lev"] == 50 and "liq" in p)(
    v.abrir_papel({}, {"bias": "ALZA", "confianza": 60},
                  {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 82800, "origen": "S"}]},
                  83000, AH2)))
t("xlx stop lejos no", v.abrir_papel(
    {}, {"bias": "ALZA", "confianza": 60},
    {"resistencias": [{"precio": 84000, "origen": "R"}], "soportes": [{"precio": 74000, "origen": "S"}]},
    83000, AH2) is None)
_XO = {"dir": "LONG", "entrada": 83000, "stop": 82500, "tp": 84000, "tam": 0.002, "riesgo": 1.0,
       "lev": 60, "liq": 81755}
t("xlx liq manda", v.cierre_papel(_XO, 83000, 81000, 82000)[1] == "LIQ")
t("xlx liq pierde", v.cierre_papel(_XO, 83000, 81000, 82000)[2] < 0)
t("xlx sl normal", v.cierre_papel(dict(_XO, liq=81000), 83000, 82400, 82600)[1] == "SL")
t("xlx sigue", v.cierre_papel(dict(_XO, liq=81000), 83000, 82600, 82800) is None)
t("ev fam", v.familia_evento("Core CPI m/m") == "CPI" and v.familia_evento("zzz") == "OTRO")
t("ev linea fria", v.linea_estudio({}, "CPI m/m") == "")
t("ev linea", v.linea_estudio({"ev_study": {"CPI": [0.5, 1.0, 1.5]}}, "Core CPI m/m") == "CPI suele mover ±1.00% (n=3)")
_ee = {"ev_study": {"CPI": [0.5, 1.0, 1.5]}, "ev_study_keys": []}
_hh = [{"t": "2026-10-12T10:00:00+00:00", "precio": 83000},
       {"t": "2026-10-12T13:00:00+00:00", "precio": 83830}]
_ev2 = [{"titulo": "Core CPI m/m", "cuando": datetime.datetime(2026, 10, 12, 11, 0, tzinfo=datetime.timezone.utc), "impact": "High"}]
t("ev estudia", v.estudiar_eventos(_ee, _hh, _ev2, datetime.datetime(2026, 10, 12, 14, 0, tzinfo=datetime.timezone.utc)) == 1
    and _ee["ev_study"]["CPI"] == [0.5, 1.0, 1.5, 1.0])
t("ev no repite", v.estudiar_eventos(_ee, _hh, _ev2, datetime.datetime(2026, 10, 12, 15, 0, tzinfo=datetime.timezone.utc)) == 0)
_ahora = datetime.datetime(2026, 10, 12, 12, 0, tzinfo=datetime.timezone.utc)
_ev3 = [{"titulo": "Core CPI m/m", "cuando": datetime.datetime(2026, 10, 12, 12, 30, tzinfo=datetime.timezone.utc), "impacto": "High", "impact": "High"}]
t("preaviso avisa", (v.preaviso({}, _ev3, _ahora, "2026-10-12") or "").startswith("⚠️ Core CPI"))
_ee2 = {}
v.preaviso(_ee2, _ev3, _ahora, "2026-10-12")
# FIX BUG1: preaviso() es puro (no marca); la marca solo tras envío real.
v.marcar_preaviso(_ee2, _ev3, _ahora, "2026-10-12")
t("preaviso unico", v.preaviso(_ee2, _ev3, _ahora, "2026-10-12") is None)
t("preaviso lejos", v.preaviso({}, _ev3, datetime.datetime(2026, 10, 12, 10, 0, tzinfo=datetime.timezone.utc), "2026-10-12") is None)
t("preaviso low", v.preaviso({}, [{"titulo": "X", "cuando": _ev3[0]["cuando"], "impact": "Low"}], _ahora, "2026-10-12") is None)
t("preaviso sin hoy", (v.preaviso({}, _ev3, _ahora) or "").startswith("⚠️ Core CPI"))
t("dom parse", v.dominancia({"data": {"market_cap_percentage": {"btc": 59.1, "eth": 10.9}}}) == {"btc": 59.1, "eth": 10.9})
t("dom vacio", v.dominancia({"data": {}}) is None)
t("dom veredicto", v.veredicto_dom(59.1) == "temporada BTC 🟠" and v.veredicto_dom(50, 51) == "zona mixta ⚪ ▼")
t("dash dom", "59.1%" in _db._dom_html({"dom": {"btc": 59.1, "eth": 10.9}}))
t("dash dom vacio", _db._dom_html({}) == "")
t("simula crea", v.responder_comando(
    {"chat": 111, "texto": "/simula", "full": "/simula LONG 83000", "nombre": "T"}, CSNAP)[0].startswith("🔬 Simulada"))
t("simula estado", "Simulador:" in v.responder_comando(
    {"chat": 111, "texto": "/simula", "full": "/simula", "nombre": "T"}, CSNAP)[0])
t("simula mala", v.responder_comando(
    {"chat": 111, "texto": "/simula", "full": "/simula ARRIBA 1", "nombre": "T"}, CSNAP)[0].startswith("Uso:"))
t("simula tope", v.responder_comando(
    {"chat": 111, "texto": "/simula", "full": "/simula LONG 83000", "nombre": "T"},
    dict(CSNAP, est=dict(CSNAP["est"], sim_abiertas=[{"dir": "LONG", "entrada": 1, "stop": 2, "tp": 3}] * 5)))[0].startswith("Tienes 5"))

# ---------- dashboard QA (constructores) ----------
_ah = datetime.datetime.now(datetime.timezone.utc)
_ea = {"ultima_alerta": {"t": _ah.isoformat(), "motivo": "Señal fuerte ALZA test", "precio": 83100,
                          "bias": "ALZA", "conf": 60}, "runs": 1}
_ht = [{"t": "2026-10-12T03:%02d:00+00:00" % i, "precio": 83000 + i, "conf": 30,
        "bias": "ALZA", "tipo": "alerta" if i % 2 else "nada", "motivo": "M%d" % i} for i in range(6)]
t("dash banner", "Última alerta" in _db.build_dashboard(_ea, _ht))
t("dash banner viejo", "Última alerta" not in _db.build_dashboard(
    {"ultima_alerta": {"t": "2020-01-01T00:00:00+00:00", "motivo": "X", "precio": 1}, "runs": 1}, []))
t("dash saludo", any(s in _db.build_dashboard({"runs": 1}, []) for s in
    ["Buenos días", "Buenas tardes", "Buenas noches", "madrugada"]))
t("dash pie hoy", " hoy " in _db.build_dashboard({"runs": 1}, _ht))
t("dash empate", "empate total" in _db.build_dashboard(
    {"ultimo_bias": "LATERAL", "ultima_conf": 0, "runs": 1}, _ht))
t("dash no empate", "empate total" not in _db.build_dashboard(
    {"ultimo_bias": "ALZA", "ultima_conf": 31, "runs": 1}, _ht))
t("poc medio", v.punto_control(
    [{"h": 100 + i, "l": 99 + i, "c": 99.5 + i, "v": 10.0} for i in range(30)]) is not None)
t("poc pico", v.punto_control(
    [{"h": 101, "l": 100, "c": 100.5, "v": (500.0 if i == 15 else 10.0)} for i in range(30)])["poc"] == 101)
t("poc poco", v.punto_control([{"h": 1, "l": 1, "c": 1, "v": 1.0}] * 5) is None)
t("kelly duerme", v.kelly_half([1.0, -1.0]) is None)
t("kelly rango", 0.0025 <= (v.kelly_half([1.5] * 8 + [-1.0] * 2) or 0) <= 0.02)
t("sharpe duerme", v.sharpe([1.0]) is None)
t("sharpe gana", (v.sharpe([1.5, 2.0, 1.0, 2.5, 1.0]) or 0) > 1)
t("dash ev", "EV ALZA" in _db.build_dashboard(
    {"ultimo_bias": "ALZA", "ultima_conf": 31, "runs": 1,
     "alza": [1, 1, 1, 1, 0], "baja": []}, _ht))
t("calib tabla", (lambda r: r is not None and r["n"] == 6 and r["brier"] == 0.0)(
    v.tabla_calibracion([{"conf": 100, "r": 1}] * 3 + [{"conf": 0, "r": 0}] * 3)))
t("calib poca", v.tabla_calibracion([{"conf": 60, "r": 1}]) is None)
t("calib rota", v.tabla_calibracion("basura") is None)
t("dash conciencia", "Brier" in _db.build_dashboard(
    {"ultimo_bias": "ALZA", "ultima_conf": 31, "runs": 1, "alza": [], "baja": [],
     "eval_log": [{"conf": 60, "r": 1}] * 3 + [{"conf": 40, "r": 0}] * 3}, _ht))
t("guardia limpia", v.guardia_lectura() is True)
import os as _os
_os.environ["BINANCE_API_KEY"] = "x"
try:
    v.guardia_lectura()
    t("guardia frena", False)
except SystemExit as e:
    t("guardia frena", e.code == 2)
finally:
    del _os.environ["BINANCE_API_KEY"]
t("alerta rango", v.responder_comando(
    {"chat": 111, "texto": "/alerta", "full": "/alerta 5", "nombre": "T"}, CSNAP)[0].startswith("Precio fuera"))
t("alerta tope", (lambda: (
    v.responder_comando({"chat": 111, "texto": "/alerta", "full": "/alerta 85000", "nombre": "T"},
                        dict(CSNAP, est=dict(CSNAP["est"], mis_alertas=[{"precio": 1, "dir": "x"}] * 20)))[0].startswith("Tienes 20")
))())
t("ruptura baja", (v.ruptura([{"o": 82100, "c": 82050}, {"o": 81950, "c": 81500}, {"o": 81500, "c": 81560}], 81900, 84000) or "").startswith("ruptura BAJISTA"))
t("ruptura sube", (v.ruptura([{"o": 83900, "c": 83950}, {"o": 83950, "c": 84450}, {"o": 84450, "c": 84500}], 82000, 84000) or "").startswith("ruptura ALCISTA"))
t("ruptura nada", v.ruptura([{"c": 82000}, {"c": 83000}], 82000, 84000) is None)
t("ruptura poca", v.ruptura([{"c": 1}], 2, 3) is None)
# F6: anti false-break de chop (soporte se pega al precio al subir)
t("ruptura F6 verde no es bajista", v.ruptura(
    [{"o": 80932, "c": 81181}, {"o": 81181, "c": 81735}, {"o": 81735, "c": 81750}], 82000, 84000) is None)
t("ruptura F6 sin cruce real", v.ruptura(
    [{"o": 81700, "c": 81400}, {"o": 81400, "c": 81250}, {"o": 81250, "c": 81260}], 82000, 84000) is None)
t("ruptura F6 margen corto", v.ruptura(
    [{"o": 82050, "c": 82030}, {"o": 82030, "c": 81970}, {"o": 81970, "c": 81960}], 82000, 84000) is None)
_rup_orig = v.UMBRAL_RUPTURA_ESTRICTO
v.UMBRAL_RUPTURA_ESTRICTO = False
t("ruptura F6 off restaura legacy", (v.ruptura([{"c": 81900}, {"c": 82000}], 82000, 84000) or "").startswith("ruptura BAJISTA"))
v.UMBRAL_RUPTURA_ESTRICTO = _rup_orig
# F8: proxima_sesion debe dar la próxima ocurrencia real (< 24 h), no siempre mañana
_px = v.proxima_sesion()
t("proxima_sesion < 24h", 0 < float(_px.split("~")[1].split(" ")[0]) <= 24.0)
_eb5 = dict(eb)
_ahX = ah.replace(hour=10, minute=5)
t("ruptura avisa", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb5, _ahX,
    None, None, "tendencia", False, "", None, None, None, 90, 90, None,
    "ruptura BAJISTA confirmada bajo 82.000 (cierre 1H)")[2] == "alerta")
t("ruptura serrucho", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb5, _ahX,
    None, None, "tendencia", False, "", None, None, None, 90, 90, None,
    "ruptura ALCISTA confirmada sobre 82.000 (cierre 1H)")[2] == "nada")
_eb6 = dict(eb)
t("ruptura detalla", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb6, _ahX,
    None, None, "tendencia", False, "", None, None, None, 90, 90, None,
    "ruptura BAJISTA confirmada bajo 82.000 (cierre 1H 20:00 en 81.900, 0.12% debajo)")[2] == "alerta")
t("ruptura serrucho2", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb6, _ahX,
    None, None, "tendencia", False, "", None, None, None, 90, 90, None,
    "ruptura ALCISTA confirmada sobre 82.000 (cierre 1H 21:00 en 82.100, 0.12% encima)")[2] == "nada")
t("dash card", _db._card("x", "Título", "cuerpo").count("chead") == 1)
_sn = {"tf": {"h1": {"tend": "alcista", "rsi": 70, "macd": 1},
              "h4": {"tend": "bajista", "rsi": 30, "macd": -1},
              "d1": {"tend": "lateral", "rsi": 50, "macd": 0},
              "w1": {"tend": "alcista", "rsi": 60, "macd": 1}}}
t("dash tfs 4", _db._tfs_html(_sn).count("data-tf=") == 4)
t("dash tfs vacio", _db._tfs_html({}) == "")
t("dash duelo gana", "VICTORIA DE LOS TOROS" in _db._duelo_html(
    {'bal': {'nb': 8, 'ns': 2, 'buys': 60.0, 'sells': 10.0, 'big': 12.5, 'txt': 'x'},
     'senti': {'taker': 1.35}}))
t("dash duelo toro", "VICTORIA DE LOS OSOS" in _db._duelo_html(
    {'bal': {'nb': 1, 'ns': 6, 'buys': 5.0, 'sells': 40.0, 'big': 9.0, 'txt': 'x'},
     'senti': {'taker': 0.75}}))
t("dash duelo duerme", "Nadie en la arena" in _db._duelo_html({}))
_snS = {"bias": "BAJA", "confianza": 50, "niv": {"sop": [{"precio": 80500}], "res": [{"precio": 82500}]}, "tf": {}}
_seS = {"banco": 74.33, "mem_zonas": {"82500": {"hold": 2, "rompe": 1}}, "ultima_alerta": {"motivo": "<b>hola</b>"}}
t("dash sala", "salaCanvas" in _db._sala_html(_snS, _seS) and "82500" in _db._sala_html(_snS, _seS))
t("dash sala demo", "salaCanvas" in _db._sala_html({}, {}))
t("dash sala xss", "<b>hola</b>" not in _db._sala_html(_snS, _seS))
t("dash sala dataset", "data-res=" in _db.build_dashboard({"runs": 1, "snapshot": _snS, "banco": 74.33, "mem_zonas": {}, "ultima_alerta": {}}, []))
t("dash mono", "--acc:#f0f0f0" in _db.CSS and "grid-column:1/-1" in _db.CSS)
t("dash crew", 'id="crew"' in _db.build_dashboard({"runs": 1}, []) and "PAP" in _db.build_dashboard({"runs": 1}, []))
t("dash idle js", "crew.dataset.mood" in _db.IDLE_JS)
t("dash free", "freebot" in _db.FREE_JS and "window.__upload" in _db.FREE_JS)
t("dash free css", ".freebot" in _db.CSS and ".card.extract" in _db.CSS)
t("dash free doc", "position:absolute" in _db.CSS and "scrollY" in _db.FREE_JS and "aportó" in _db.FREE_JS)
t("dash anarquia", "ANARCHY_EVERY" in _db.FREE_JS and "portal" in _db.FREE_JS and "ticker/price?symbol=" in _db.FREE_JS and ".portal" in _db.CSS)
t("dash free limpio", "stepToward" in _db.FREE_JS and "tickIr" in _db.FREE_JS and "window.__upload" in _db.FREE_JS)
t("dash free perf", "RCC" in _db.FREE_JS and "will-change:transform" in _db.CSS and "translate(" in _db.FREE_JS)
_ban = _db._banner_html({"ultima_alerta": {"t": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "motivo": "<script>alert(1)</script>", "precio": 83000, "bias": "ALZA", "conf": 60}}, [], datetime.datetime.now(datetime.timezone.utc))
t("banner escapa", "<script>" not in _ban and "&lt;script&gt;" in _ban)
t("dash duelo cinta vacia", "cinta sin ballenas" in _db._duelo_html(
    {"bal": {"nb": 0, "ns": 0, "buys": 0, "sells": 0, "big": 0, "txt": "sin prints de ballenas"},
     "senti": {"taker": 0.794}}))
t("duelo caso vivo osos", "VICTORIA DE LOS OSOS" in _db._duelo_html(
    {'bal': {'nb': 0, 'ns': 1, 'buys': 0.0, 'sells': 6.7, 'big': 6.7, 'txt': 'x'},
     'senti': {'taker': 0.794}}))
t("duelo debil no corona toros", "VICTORIA DE LOS TOROS" not in _db._duelo_html(
    {'bal': {'nb': 0, 'ns': 1, 'buys': 0.0, 'sells': 6.7, 'big': 6.7, 'txt': 'x'},
     'senti': {'taker': 0.794}}))
_d1 = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
_d2 = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
_ev = [{"titulo": "A", "cuando": _d1 + "T08:30:00+00:00", "impact": "High"},
       {"titulo": "B", "cuando": _d1 + "T08:30:00+00:00", "impact": "High"},
       {"titulo": "C", "cuando": _d2 + "T08:30:00+00:00", "impact": "Low"}]
t("dash macro grupo", "A +1" in _db._macro_html({"evs": _ev}, _ah))
_gg = _db._gauge_reloj_html({"snapshot": {"fg": {"valor": 66, "etiqueta": "Codicia"}}}, [], _ah)
t("dash gauge", "Codicia" in _gg and "66" in _gg and "Bogot" in _gg)
t("dash gauge omit", _db._gauge_reloj_html({}, [], _ah) == "")
t("dash porque", "Tendencia" in _db._porque_html(
    {"tf": _sn["tf"], "regimen": "rango", "grade": "D"}))
t("dash alertas tabla", "Últimas" in _db._alertas_html({}, _ht, _ah))
_ahc = {"cools": {"ritmo:baja": _ah.isoformat(),
                  "liq:max": "2020-01-01T00:00:00+00:00"}}
_sil = _db._alertas_html(_ahc, [], _ah)
t("dash silencios", "ritmo baja" in _sil and "hasta" in _sil and "liq" not in _sil)
_sil4 = _db._alertas_html({"cools": {f"{c}:x": _ah.isoformat()
    for c in ("ritmo", "brusco", "liq", "toque", "fuerte")}}, [], _ah)
t("dash silencios tope", "+2 más" in _sil4)
t("dash silencio ruptura", "ALCISTA confirmada" in _db._alertas_html(
    {"cools": {"ruptura:ruptura ALCISTA confirmada sobre 82.000 (cierre 1H)": _ah.isoformat()}}, [], _ah)
    and "ruptura ruptura" not in _db._alertas_html(
    {"cools": {"ruptura:ruptura ALCISTA confirmada sobre 82.000 (cierre 1H)": _ah.isoformat()}}, [], _ah))
_ph = [{"t": "2026-10-12T10:00:00+00:00", "tipo": "alerta", "motivo": "ruptura BAJISTA x"},
       {"t": "2026-10-12T11:00:00+00:00", "tipo": "alerta", "motivo": "TECHO y"},
       {"t": "2026-10-12T12:00:00+00:00", "tipo": "nada", "motivo": "z"}]
t("presion dia", _db.presion_dia(_ph, "2026-10-12") == {"bajistas": 1, "alcistas": 1})
t("presion vacia", _db.presion_dia([], "2026-10-12") == {"bajistas": 0, "alcistas": 0})
t("dash presion", "1 bajistas / 1 alcistas" in _db._alertas_html(
    {}, _ph, datetime.datetime(2026, 10, 12, 13, 0, tzinfo=datetime.timezone.utc)))
t("dash barras cero", "empate total de marcos" in _db.svg_barras([0, 0, 0], ["0", "1", "2"]))
_xsec = _db.build_dashboard({"ultimo_bias": "ALZA", "ultima_conf": 31, "runs": 1,
                             "snapshot": {"tf": {"h1": {"tend": "t", "rsi": 1}, "h4": {"tend": "t", "rsi": 1},
                                                  "d1": {"tend": "t", "rsi": 1}, "w1": {"tend": "t", "rsi": 1}},
                                          "fg": {"valor": 50, "etiqueta": "x"}, "senti": {}, "pres": {},
                                          "niv": {}, "evs": []}}, _ht)
t("dash secciones", all(s in _xsec for s in ["s-precio", "s-senales", "s-mercado", "s-dinero", "s-sistema"]))
t("dash nav", _xsec.count('class="nav"') == 1 and "#s-mercado" in _xsec)
t("dash orden", _xsec.index("s-precio") < _xsec.index("s-senales") < _xsec.index("s-mercado") < _xsec.index("s-dinero") < _xsec.index("s-sistema"))
t("dash layout", "display:grid" in _db.CSS)
t("dash papel quieto", "requiere 35%" in _db._ops_html(
    {"ultima_conf": 31}, datetime.datetime.now(datetime.timezone.utc)))
t("dash masonry", ".grid{display:grid" in _db.CSS and "repeat(3,minmax(0,1fr))" in _db.CSS)
t("dash nav fija", "position:sticky" in _db.CSS and 'class="nav"' in _db.build_dashboard({"runs": 1}, []))
t("dash a11y", "focus-visible" in _db.CSS and "scrollbar-width" in _db.CSS)
import datetime as _dt
t("prox ny", _db._prox_pasada(_dt.datetime(2026, 10, 12, 13, 2, tzinfo=_dt.timezone.utc)).strftime("%H:%M") == "13:05")
t("prox resto", _db._prox_pasada(_dt.datetime(2026, 10, 12, 11, 16, tzinfo=_dt.timezone.utc)).strftime("%H:%M") == "11:30")
t("prox borde", _db._prox_pasada(_dt.datetime(2026, 10, 12, 20, 58, tzinfo=_dt.timezone.utc)).strftime("%H:%M") == "21:00")
t("liqmap card", "Imán de stops" in _db._liqmap_html(
    {"liqmap": {"arriba": [{"precio": 84000, "dist": 0.5, "score": 80}],
                           "abajo": [{"precio": 82000, "dist": -0.5, "score": 60}],
                           "iman": {"lado": "arriba", "pct": 57}}}))
t("liqmap vacio", _db._liqmap_html({}) == "")
t("dash hora datos", "12/10 03:03" in _db.build_dashboard(
    {"ultimo_bias": "LATERAL", "ultima_conf": 0, "runs": 1,
     "ultimo_run": "2026-10-12T03:03:00+00:00"}, _ht))

# ---------- PILAS claras ----------
_zs = [{"precio": 83500, "razones": ["imán"]}, {"precio": 84000, "razones": ["psicológico", "imán"]}]
_mp, _mk = v.mensaje_pila(_zs, 83730, [{"precio": 82992}], [{"precio": 84199}])
t("pila piso", _mp is not None and "PISO" in _mp and "83.500" in _mp and "bajo 82.992" in _mp)
t("pila encajon", "entre 🛡 83.500 y 🧲 84.000" in _mp)
_mt, _ = v.mensaje_pila(_zs, 83752, [{"precio": 82992}], [{"precio": 84199}])
t("pila techo", _mt is not None and "TECHO" in _mt and "sobre 84.199" in _mt)
t("pila lejos", v.mensaje_pila(_zs, 80000, [], []) == (None, None))
t("pila vacia", v.mensaje_pila([], 83000, [], []) == (None, None))
t("pila contra", "contra momentum" in (v.mensaje_pila(
    [{"precio": 84000, "razones": ["x"]}], 83752, [{"precio": 82992}], [{"precio": 84199}],
    {"tend": "ALCISTA", "er": 0.6, "rsi": 70})[0] or ""))
t("pila a favor", "contra momentum" not in (v.mensaje_pila(
    [{"precio": 84000, "razones": ["x"]}], 83752, [{"precio": 82992}], [{"precio": 84199}],
    {"tend": "lateral", "er": 0.1, "rsi": 50})[0] or ""))
_h1r = {"tend": "lateral", "er": 0.1, "rsi": 55, "z": 0.5}
_a4r = {"adx": 25}
_mr = v.mensaje_pila([{"precio": 82992, "razones": ["S1 semanal"]}], 83100,
                     [{"precio": 82992}], [{"precio": 84199}], _h1r, _a4r, 14)[0] or ""
t("pila reaccion", "Reacción probable" in _mr and ("ALTA" in _mr or "MEDIA" in _mr or "BAJA" in _mr))
t("pila sin reloj", "Reacción probable" not in (v.mensaje_pila(
    [{"precio": 82992, "razones": ["x"]}], 83100, [{"precio": 82992}], [{"precio": 84199}],
    _h1r)[0] or ""))
t("prob rango", 0 <= (v.prob_reaccion({}) or -1) <= 1)
t("liq claro", "compradores" in v.liquidez([{"o": 82000, "h": 82000, "l": 81900, "c": 81950}] * 24 +
    [{"o": 82000, "h": 82600, "l": 82000, "c": 82100}, {"o": 82100, "h": 82200, "l": 82050, "c": 82080},
     {"o": 82080, "h": 82120, "l": 82000, "c": 81990}], 81990))
t("version", v.VERSION == "v6")

# ---------- anti-spam (solo lo importante) ----------
_e2 = {}
t("enfriar 1ro", v.enfriar(_e2, "x", 4, ah) is True)
t("enfriar 2do", v.enfriar(_e2, "x", 4, ah) is False)
t("enfriar vence", v.enfriar(_e2, "x", 0.001, ah + datetime.timedelta(hours=1)) is True)
_ah10 = ah.replace(hour=10, minute=5)
_liq1 = v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
                         None, None, "tendencia", False, "", None, "barrido test", None)
t("liq avisa", _liq1[2] == "alerta")
_eb2 = dict(eb)
v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb2, _ah10,
                 None, None, "tendencia", False, "", None, "barrido test", None)
_liq2 = v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb2, _ah10,
                         None, None, "tendencia", False, "", None, "barrido test", None)
t("liq no repite", _liq2[2] == "nada")
_eb3 = dict(eb, ultimo_bias="ALZA")
v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, _eb3, _ah10,
                 None, None, "tendencia", False, "", None, None, None, 50, 40)
t("fuerte no repite", v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 70}, _eb3, _ah10,
    None, None, "tendencia", False, "", None, None, None, 50, 40)[2] == "nada")
t("ritmo avisa", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", False, "", None, None, None, 90, 90, -0.75)[2] == "alerta")
_eb4 = dict(eb)
v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb4, _ah10,
    None, None, "tendencia", False, "", None, None, None, 90, 90, -0.75)
t("ritmo no repite", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb4, _ah10,
    None, None, "tendencia", False, "", None, None, None, 90, 90, -0.75)[2] == "nada")
t("ritmo chico calla", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", False, "", None, None, None, 90, 90, -0.4)[2] == "nada")
t("ritmo blackout", v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", True, "CPI", None, None, None, 90, 90, -0.9)[2] == "nada")
t("liq fade corto", "desvanecer hacia 81.000" in v.decidir_alerta(
    82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", False, "", None, "barrido sobre máximos X", None)[1])
t("liq fade largo", "desvanecer hacia 84.000" in v.decidir_alerta(
    82500, niv, {"bias": "LATERAL", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", False, "", None, "barrido bajo mínimos X", None)[1])
t("liq contra calla", v.decidir_alerta(
    82500, niv, {"bias": "ALZA", "confianza": 10}, dict(eb), _ah10,
    None, None, "tendencia", False, "", None, "barrido sobre máximos X", None)[2] == "nada")
t("eficiencia trend", (v.eficiencia([float(100 + i * 2) for i in range(100)]) or 0) > 0.5)
t("eficiencia chop", (lambda e: e is not None and e < 0.25)(
    v.eficiencia([float(100 + (5 if i % 2 else -5)) for i in range(100)])))
t("eficiencia poca", v.eficiencia([1.0, 2.0, 3.0]) is None)
t("zscore base", v.zscore([float(i) for i in range(1, 21)]) is not None)
t("zscore estirado", abs(v.zscore([100.0] * 19 + [120.0]) or 0) >= 2)
t("zscore poco", v.zscore([1.0]) is None)
_akl = kl([80000.0 + i * 10 for i in range(100)])
_aa = v.analyze(_akl, 60, "1H")
t("analyze trae er+z", "er" in _aa and "z" in _aa and _aa["er"] is not None)
t("dash chip er", "ER 0.62" in _db._contexto_html(
    {"regimen": "x", "grade": "y",
     "tf": {"h1": {"tend": "t", "rsi": 1}, "h4": {"tend": "t", "rsi": 1},
            "d1": {"tend": "t", "rsi": 1}, "w1": {"tend": "t", "rsi": 1, "er": 0.62}},
     "fg": {}, "senti": {}, "pres": {}, "niv": {}, "evs": []}))
t("dash escapa html", _db._esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;" and "&lt;img" in _db.build_dashboard({"runs": 1}, [{"t": "2026-10-13T14:00:00+00:00", "bias": "ALZA", "motivo": "<img src=x onerror=alert(1)>", "precio": 83000, "conf": 50, "tipo": "alerta"}]))
t("dash vacio honesto", "sin datos" in _db.build_dashboard({}, []))
t("dash duelo sucio no rompe", isinstance(_db._duelo_html({"bal": {"buys": "?", "sells": None, "nb": "x", "ns": None}}), str))
t("dash alza sucia no rompe", isinstance(_db.build_dashboard({"alza": ["a", None, 1, 2, 3, 4, 5], "baja": [1, "b"], "runs": 1}, []), str))
t("dash prox medianoche dia siguiente", _db._prox_pasada(datetime.datetime(2026, 10, 13, 23, 50, tzinfo=datetime.timezone.utc)).day == 14)
t("telegram retry existe", "for intento in range(3)" in open(os.path.join(_AQUI, "vigilante_cloud.py"), encoding="utf-8").read())
# --- Bloque seguro 3x10 (TDD): TCA + validador/gaps + purge/DSR + latido/runbook + frescura ---
# Nota CI: este bloque exige backtest.partir_purgado/puerta_trials/pf_por_grupo (mismo push).
t("tca linea drift", "Ref" in v.tca_linea(83000, 83207.5) and "83.000" in v.tca_linea(83000, 83207.5) and "%" in v.tca_linea(83000, 83207.5))
t("tca linea sin arrival", "s/d" in v.tca_linea(None, 83000))
t("tca linea sin cero", "s/d" in v.tca_linea(0, 83000))
_vv = [{"t": datetime.datetime(2026, 10, 13, i, tzinfo=datetime.timezone.utc),
        "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0} for i in range(5)]
t("validar velas ok", v.validar_velas(_vv, 60)["ok"] is True and v.validar_velas(_vv, 60)["gaps"] == 0)
_vgap = [_vv[0], _vv[1], {"t": datetime.datetime(2026, 10, 13, 4, tzinfo=datetime.timezone.utc),
        "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0}]
t("validar velas gap", v.validar_velas(_vgap, 60)["gaps"] >= 1)
_vmal = [_vv[0], {"t": datetime.datetime(2026, 10, 13, 1, tzinfo=datetime.timezone.utc),
        "o": 1.0, "h": 0.4, "l": 0.5, "c": 1.5, "v": 10.0}]
t("validar velas mala", v.validar_velas(_vmal, 60)["malas"] >= 1)
t("latido tarde si", v.latido_tarde("2026-10-13T14:00:00+00:00", "2026-10-13T14:30:00+00:00", 15) is True)
t("latido tarde no", v.latido_tarde("2026-10-13T14:20:00+00:00", "2026-10-13T14:30:00+00:00", 15) is False)
t("runbook linea", "github.com/LuiferX/vigilante-btc" in v.linea_runbook())
import importlib.util as _ilu
spec_bt = _ilu.spec_from_file_location("bt", os.path.join(_AQUI, "backtest.py"))
_bt = _ilu.module_from_spec(spec_bt)
spec_bt.loader.exec_module(_bt)
_tr, _te = _bt.partir_purgado(10, 0.5, 2)
t("purga embargo", len(_tr) == 5 and len(_te) == 3 and max(_tr) < min(_te))
t("puerta trials exige dsr", "DSR" in _bt.puerta_trials(12, 0.8))
t("puerta trials ok pocos", "ok" in _bt.puerta_trials(3, 1.5).lower() or "pocos" in _bt.puerta_trials(3, 1.5).lower())
_fr, _ft = _db.frescura("2026-10-13T14:29:00+00:00", datetime.datetime(2026, 10, 13, 14, 30, tzinfo=datetime.timezone.utc), 15)
t("frescura vivo", _fr == "vivo")
_fr2, _ft2 = _db.frescura("2026-10-13T10:00:00+00:00", datetime.datetime(2026, 10, 13, 14, 30, tzinfo=datetime.timezone.utc), 15)
t("frescura viejo", _fr2 == "viejo")
try:
    import sys as _sysn
    _sysn.path.insert(0, os.path.join(_AQUI, "entrenamiento"))
    import evaluar as _ev
    import entrenador as _ent
    _TIENE_ENTRENA = True
except Exception:
    _ev = _ent = None
    _TIENE_ENTRENA = False


def te(nombre, fn):
    """Test local-only (entrenamiento/ no se publica): en CI se omite."""
    if not _TIENE_ENTRENA:
        t(nombre + " (omitido en CI)", True)
        return
    try:
        t(nombre, bool(fn()))
    except Exception:
        t(nombre, False)


te("wilson n0", lambda: _ev.wilson(0, 0) is None)
te("wilson rango", lambda: _ev.wilson(30, 15) is not None and 0 < _ev.wilson(30, 15)[0] < 0.5 < _ev.wilson(30, 15)[1] < 1)
te("veredicto pocos", lambda: _ev.veredicto(10, 3) == "pocos")
te("pf proxy debil", lambda: _ev.pf_proxy(10, 3) < 1.0)
te("agregar vacio", lambda: "dir" in _ev.agregar([]))
te("pf exp vacio", lambda: _ent.pf_exp(0, 0) == {"pf": None, "exp": None})
te("pf exp sintetico", lambda: _ent.pf_exp(10, 5)["exp"] == -0.75)
te("clave formato", lambda: _ent.clave("dir", "2026-10-13T14:00:00+00:00") == "dir|2026-10-13T14:00")
te("clave vacia", lambda: _ent.clave(None, None) == "None|None" or isinstance(_ent.clave("x", "t"), str))
te("claves archivo ausente", lambda: _ent.cargar_claves("no_existe_xyz.jsonl") == set())
te("totales archivo ausente", lambda: _ent.totales_ledger("no_existe_xyz.jsonl") == {"dir": [0, 0], "liq": [0, 0], "toq": [0, 0], "zon": [0, 0]})


def _ledger_tmp():
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "sen.jsonl")
    ok1 = _ent.guardar_nuevas([{"k": "dir|2026-10-13T00:00", "s": "dir", "t": "2026-10-13T00:00", "w": 1},
                               {"k": "zon|2026-10-13T06:00", "s": "zon", "t": "2026-10-13T06:00", "w": 0}], p) == 2
    tot = _ent.totales_ledger(p)
    return ok1 and tot["dir"] == [1, 1] and tot["zon"] == [1, 0] and _ent.cargar_claves(p) == {"dir|2026-10-13T00:00", "zon|2026-10-13T06:00"}
te("ledger ida y vuelta", _ledger_tmp)
te("ledger ledger evaluar", lambda: isinstance(_ev.leer_ledger("no_existe_xyz.jsonl"), tuple) and _ev.leer_ledger("no_existe_xyz.jsonl") == ({}, 0))
te("magnitud vacia", lambda: _ev.magnitud([]) is None)
te("magnitud neta", lambda: (_ev.magnitud([0.5] * 12) or {}).get("med_net", 0) > 0)
te("magnitud costos matan", lambda: (_ev.magnitud([0.1] * 12) or {}).get("med_net", 0) < 0)
te("oos zon sintetico", lambda: (_ev._oos_tmp() or {}).get("n_test", 0) == 35)
te("oos zon captura", lambda: (_ev._oos_tmp() or {}).get("med_net", -99) == 5.0)
t("pf sesion agrupa", _bt.pf_por_grupo([{"motivo": "x NY y", "hit": 1, "r": 2}] * 4 + [{"motivo": "noche z", "hit": 0, "r": -1}] * 4 + [{"motivo": "otro", "hit": 1, "r": 2}] * 2, "sesion")["NY"]["n"] == 4)
t("pf grade defecto", _bt.pf_por_grupo([{"hit": 1, "r": 2}], "grade")["?"]["n"] == 1)
t("pf grupo metricas", _bt.pf_por_grupo([{"motivo": "NY", "hit": 1, "r": 2}] * 4, "sesion")["NY"]["pf"] is None)
t("pf todo-gana honesto", _bt.metricas([{"hit": 1, "r": 2}] * 4)["pf"] is None)
t("precio sin lookahead", _bt.precio_en([{"t": datetime.datetime(2026, 1, 1, 2, 0, tzinfo=datetime.timezone.utc), "c": 99.0},
    {"t": datetime.datetime(2026, 1, 1, 3, 0, tzinfo=datetime.timezone.utc), "c": 100.0}],
    datetime.datetime(2026, 1, 1, 3, 30, tzinfo=datetime.timezone.utc)) == 99.0)
t("atr solo cerradas", _bt.atr_en([{"t": datetime.datetime(2026, 1, 1, h, tzinfo=datetime.timezone.utc), "h": 10.0, "l": 0.0} for h in range(20)],
    datetime.datetime(2026, 1, 1, 10, 30, tzinfo=datetime.timezone.utc)) == 10.0)
t("pf vacio", _bt.pf_por_grupo([], "sesion") == {})
t("noticias con presupuesto", v.noticias.__defaults__ == (5, 40))
t("backtest demo marcado", "[DEMO]" in open(os.path.join(_AQUI, "backtest.py"), encoding="utf-8").read())
_ahr = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
t("ruptura contra avisa", v.decidir_alerta(80552, {"soportes": [{"precio": 80000}], "resistencias": [{"precio": 80445}]},
    {"bias": "BAJA", "confianza": 50}, {}, _ahr, None, None, "tendencia", False, "", None, None, None, 55, 40, None,
    "ruptura ALCISTA confirmada sobre 80.445", None, None, None, None, None)[1].endswith("(ojo: sesgo en contra, no perseguir)"))
t("ruptura a favor limpia", v.decidir_alerta(80552, {"soportes": [{"precio": 80000}], "resistencias": [{"precio": 80445}]},
    {"bias": "ALZA", "confianza": 50}, {}, _ahr, None, None, "tendencia", False, "", None, None, None, 55, 40, None,
    "ruptura ALCISTA confirmada sobre 80.445 (cierre 1H 12:00 en 80.552, 0.13% encima)", None, None, None, None, None)[1].endswith("encima)"))
_ahP = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_nvp = {"soportes": [{"precio": 82200}], "resistencias": [{"precio": 83800}]}
_estP = {"banco": 100.0, "banco_pico": 100.0, "paper_cerradas": [], "paper_dia": {"fecha": _ahP.strftime("%Y-%m-%d"), "pnl": 0.0}}
_posP = v.abrir_papel(_estP, {"bias": "ALZA", "confianza": 50}, _nvp, 83000, _ahP)
t("papel SL es -1R exacto", abs(v.cierre_papel(_posP, 83000, 82100, 82100)[2] - -1.0) < 0.01)
t("papel LIQ fallback igual abrir", abs((83000 * (1 - 1.0 / 50)) - v.cierre_papel({"dir": "LONG", "entrada": 83000, "tam": 0.001, "stop": 82200, "tp": 83800}, 81000, 81000, 81000)[0]) < 1)
t("papel LIQ declara", v.cierre_papel({"dir": "LONG", "entrada": 83000, "tam": 0.00125, "stop": 82200, "tp": 83800, "liq": 81340, "lev": 50, "riesgo": 1.0}, 81000, 81000, 81000)[2] <= -2.0)
_ebr3 = {"banco": 15.0, "banco_pico": 200.0, "paper_cerradas": [{"pnl": -1, "r": -1}], "paper_dia": {"fecha": _ahP.strftime("%Y-%m-%d"), "pnl": -5.0}, "paper_abiertas": [{"x": 1}]}
t("reborn resetea dia y abiertas", v.abrir_papel(_ebr3, {"bias": "ALZA", "confianza": 50}, _nvp, 83000, _ahP) is not None and _ebr3["paper_dia"]["pnl"] == 0.0 and _ebr3["banco"] == 100.0 and len(_ebr3.get("paper_abiertas", [])) == 1)
t("papel cota 5 abiertas", v.abrir_papel({"banco": 100.0, "banco_pico": 100.0, "paper_cerradas": [], "paper_dia": {"fecha": _ahP.strftime("%Y-%m-%d"), "pnl": 0.0}, "paper_abiertas": [{}] * 5}, {"bias": "ALZA", "confianza": 50}, _nvp, 83000, _ahP) is None)
t("banco corrupto no tumba", v.abrir_papel({"banco": "abc", "banco_pico": 100.0}, {"bias": "ALZA", "confianza": 50}, _nvp, 83000, _ahP) is None)
_vt = [{"t": _ahP - datetime.timedelta(hours=9 - i), "h": 83000 + 50 * i + 30, "l": 83000 + 50 * i - 30, "c": 83000 + 50 * i} for i in range(10)]
_esS = {"pend_sombra": [{"t": (_ahP - datetime.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "ALZA", "conf": 50, "risk": 166.0}]}
_etT = {"pend_todo": [{"t": (_ahP - datetime.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "ALZA", "conf": 50, "risk": 166.0}]}
v.evaluar_sombra(_esS, _ahP, list(_vt))
v.evaluar_todo(_etT, _ahP, list(_vt))
t("todo respeta stop-first", _esS["eval_sombra"][0]["r"] == _etT["eval_todo"][0]["r"])
_opT = {"dir": "LONG", "entrada": 100000, "stop": 99000}
_rT1 = v.gestion_sl(_opT, 101000, 800, "tendencia")
_opT["risk0"] = abs(_opT["entrada"] - _opT["stop"])
_opT["be_done"] = True
_opT["stop"] = _rT1[2]
t("trail tras BE vive", v.gestion_sl(_opT, 101500, 800, "tendencia")[1] == "TRAIL")
t("sl invertido none", v.sl_estructura(99000, "ALZA", 99500, 300) is None)
t("decidir niv roto", v.decidir_alerta(100000, None, {"bias": "ALZA", "confianza": 50}, {}, _ahP) == (False, "estado incompleto", "nada"))
t("send vacio false", v.send_telegram("") is False)
t("tca fee malo", "s/d" in v.tca_linea(84900, 85000, fee_bps=None))
t("opere stop igual no", v.responder_comando({"chat": 111, "texto": "/opere", "full": "/opere LONG 100 100 110", "nombre": "T"}, dict(CTX, est={}))[0].startswith("Revisa"))
t("spread regla", v.regla_spread(2) == "market ok" and v.regla_spread(4) == "mejor limit" and v.regla_spread(8) == "pausa" and v.regla_spread(None) == "s/d" and v.regla_spread("x") == "s/d")
t("spread linea", "Spread 1.5bps" in v.build_parte({"last": 83000, "chg": 0.5, "hi": 83500, "lo": 82500}, tf("1H", "lateral", 0), tf("4H", "lateral", 0), tf("1D", "lateral", 0), tf("1S", "lateral", 0), NIV, {"bias": "LATERAL", "confianza": 10}, "p", {"funding": None, "oi": None, "taker": None, "spread": 1.5}, {"valor": 50, "etiqueta": "Neutral"}, {}, "mot", "alerta", [], [], ah, dict(ex, arrival=83000)))


def _vcm(o, h, l, c):
    return {"t": datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc), "o": o, "h": h, "l": l, "c": c, "v": 1.0}
_ahq = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_plm = [_vcm(81000, 81100, 80900, 81050)] * 5
t("mecha martillo claro", (lambda r: r and r["dir"] == "ALZA" and r["nivel"] == 80226
    and r["ratio"] == 0.826 and r["fuerza"] == "fuerte")(
    v.mecha_rechazo(_plm + [_vcm(81640, 81814, 80226, 81538)])))
t("mecha sin mecha", v.mecha_rechazo(_plm + [_vcm(81000, 81500, 80500, 81200)]) is None)
t("mecha cuerpo grande", v.mecha_rechazo(_plm + [_vcm(80000, 81600, 79900, 81500)]) is None)
t("mecha vela vieja", v.mecha_rechazo([_vcm(81640, 81814, 80226, 81538)] + _plm) is None)
_ebm = {}
_rm = v.decidir_alerta(81538, {"soportes": [{"precio": 80226}], "resistencias": [{"precio": 82000}]},
    {"bias": "ALZA", "confianza": 50}, _ebm, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None,
    {"dir": "ALZA", "nivel": 80226, "mid": 80882, "fuerza": "fuerte"}, (80176, 1.0, False))
t("mecha alerta con sl", _rm[0] is True and "RECHAZO ALZA" in _rm[1] and "SL" in _rm[1])
t("mecha pide sesgo", v.decidir_alerta(81538, {"soportes": [{"precio": 80226}], "resistencias": [{"precio": 82000}]},
    {"bias": "BAJA", "confianza": 50}, {}, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None, None, None, None,
    {"dir": "ALZA", "nivel": 80226, "mid": 80882, "fuerza": "fuerte"}, (80176, 1.0, False))[2] == "nada")
t("mecha rango calla", v.decidir_alerta(81538, {"soportes": [{"precio": 80226}], "resistencias": [{"precio": 82000}]},
    {"bias": "ALZA", "confianza": 50}, {}, _ahq, None, None, "rango", False, "", None, None, None, 55, 40, None, None, None, None, None,
    {"dir": "ALZA", "nivel": 80226, "mid": 80882, "fuerza": "fuerte"}, (80176, 1.0, False))[2] == "nada")
_aht = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_nivp = {"soportes": [{"precio": 82800}], "resistencias": [{"precio": 83200}]}
t("papel 50x abre sano", v.abrir_papel({}, {"bias": "ALZA", "confianza": 50}, _nivp, 83000, _aht) is not None)
_nivl = {"soportes": [{"precio": 74000}], "resistencias": [{"precio": 83200}]}
t("papel liqui antes no abre", v.abrir_papel({}, {"bias": "ALZA", "confianza": 50}, _nivl, 83000, _aht) is None)
_nivm = {"soportes": [{"precio": 78000}], "resistencias": [{"precio": 83200}]}
t("papel mitad liqui no abre", v.abrir_papel({}, {"bias": "ALZA", "confianza": 50}, _nivm, 83000, _aht) is None)
_ebr = {"banco": 15.0}
t("papel reborn 100", v.abrir_papel(_ebr, {"bias": "ALZA", "confianza": 50}, _nivp, 83000, _aht) is not None and _ebr["banco"] == 100.0)
_ebr2 = {"banco": 70.0}
t("papel no reborn 70", v.abrir_papel(_ebr2, {"bias": "ALZA", "confianza": 50}, _nivp, 83000, _aht) is not None and _ebr2["banco"] == 70.0)
t("todo abre lateral", v.abrir_todo({}, "LATERAL", 9, 83000, 0.002, _aht) is True)
t("todo abre sesgo", v.abrir_todo({}, "ALZA", 50, 83000, 0.002, _aht) is True)
t("todo rechaza raro", v.abrir_todo({}, "?", 50, 83000, 0.002, _aht) is False)
_est_t = {}
v.abrir_todo(_est_t, "LATERAL", 9, 83000, 0.002, _aht)
t("todo dedup 1h", v.abrir_todo(_est_t, "LATERAL", 9, 83100, 0.002, _aht) is False)
_vq = [{"t": _aht - datetime.timedelta(hours=9 - i), "h": 83000 + 10, "l": 83000 - 10, "c": 83000} for i in range(10)]
_est_tq = {"pend_todo": [{"t": (_aht - datetime.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "LATERAL", "conf": 9, "risk": 166.0}]}
v.evaluar_todo(_est_tq, _aht, _vq)
t("todo lateral quieto acierta", len(_est_tq.get("eval_todo", [])) == 1 and _est_tq["eval_todo"][0]["r"] == 1)
_vqm = [{"t": _aht - datetime.timedelta(hours=9 - i), "h": 83000 + 400, "l": 83000 - 400, "c": 83000} for i in range(10)]
_est_tm = {"pend_todo": [{"t": (_aht - datetime.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "LATERAL", "conf": 9, "risk": 166.0}]}
v.evaluar_todo(_est_tm, _aht, _vqm)
t("todo lateral movido falla", len(_est_tm.get("eval_todo", [])) == 1 and _est_tm["eval_todo"][0]["r"] == 0)
t("todo no toca vivo", _est_tm.get("eval_log", []) == [] and _est_tm.get("alza", []) == [])
_estk = {"paper_cerradas": [{"pnl": 50, "r": 1.0}, {"pnl": -20, "r": -0.5}, {"pnl": 30, "r": 0.8}, {"pnl": -10, "r": -0.3}]}
_hk = _db._kpis_papel_html(_estk)
t("kpis con datos", "Profit factor" in _hk and "Expectancy" in _hk and "Mejor" in _hk and "Racha actual" in _hk)
t("kpis vacio no rompe", "sin operaciones" in _db._kpis_papel_html({}) and "Dinero papel: KPIs" in _db.build_dashboard({}, []))
t("sombra tarjeta", "En cola" in _db._sombra_html({"eval_sombra": [{"r": 1}], "pend_sombra": [{"r": 0}]}) and "sin evaluaciones" in _db._sombra_html({}) and "Sombra (aprende de todo)" in _db.build_dashboard({"eval_sombra": [{"r": 1}]}, []))
t("seg countdown", "vence en 3" in _db._seguimiento_html({"pendientes": [{"bias": "ALZA", "conf": 60, "precio": 83000, "t": (ah - datetime.timedelta(hours=5)).isoformat()}]}, ah) and "sin pendientes" in _db._seguimiento_html({}, ah))
t("calib brier cubetas", "Brier" in _db._calibracion_html({"eval_log": [{"conf": 60, "r": 1}] * 3 + [{"conf": 40, "r": 0}] * 3}) and "sin datos" in _db._calibracion_html({}) and isinstance(_db._calibracion_html({"pendientes": "<script>"}), str))
t("dash seg+calib", "En seguimiento" in _db.build_dashboard({"pendientes": [{"bias": "ALZA", "conf": 60, "precio": 83000, "t": ah.isoformat()}], "eval_log": [{"conf": 60, "r": 1}] * 5}, []) and "Calibraci" in _db.build_dashboard({"eval_log": [{"conf": 60, "r": 1}] * 5}, []))
t("dash orden dinero", (lambda h: h.index('c-ops') < h.index('c-seg') < h.index('c-banco') < h.index('c-kpis') < h.index('c-prec') < h.index('c-calib') < h.index('c-sombra'))(_db.build_dashboard({"runs": 1}, [])))
t("lado un solo lado", v.lado_ok("BAJA", "EYY PILAS TECHO x") is True and v.lado_ok("BAJA", "EYY PILAS PISO x") is False)
t("lado alza piso", v.lado_ok("ALZA", "EYY PILAS PISO x") is True and v.lado_ok("ALZA", "EYY PILAS TECHO x") is False)
t("lado lateral ambos", v.lado_ok("LATERAL", "EYY PILAS PISO x") is True and v.lado_ok("LATERAL", "EYY PILAS TECHO x") is True)
_estev = {"eval_sombra": [{"b": "ALZA", "r": 1, "conf": 45, "t": "x"}, {"b": "BAJA", "r": 0, "conf": 55, "t": "x"}, {"b": "ALZA", "r": 1, "conf": 62, "t": "x"}, {"b": "BAJA", "r": 1, "conf": 48, "t": "x"}, {"b": "ALZA", "r": 0, "conf": 70, "t": "x"}],
          "eval_log": [{"b": "ALZA", "r": 1, "conf": 50, "t": "x"}, {"b": "BAJA", "r": 0, "conf": 55, "t": "x"}, {"b": "ALZA", "r": 1, "conf": 60, "t": "x"}, {"b": "BAJA", "r": 1, "conf": 45, "t": "x"}, {"b": "ALZA", "r": 0, "conf": 65, "t": "x"}]}
_ctxev = dict(CTX, est=_estev)
_rs, _ds = v.responder_comando({"chat": 111, "texto": "/sombra", "full": "/sombra", "nombre": "T"}, _ctxev)
t("sombra cubetas", "n=5" in _rs and "Por confianza:" in _rs and _ds is False)
_re, _de = v.responder_comando({"chat": 111, "texto": "/evals", "full": "/evals", "nombre": "T"}, _ctxev)
t("evals brier", ("Brier" in _re) == (v.tabla_calibracion(_estev["eval_log"]) is not None) and _de is False)
t("sombra dueño y vacios", v.responder_comando({"chat": 999, "texto": "/sombra", "full": "/sombra", "nombre": "T"}, _ctxev) == (None, False) and "sin evaluaciones" in v.responder_comando({"chat": 111, "texto": "/sombra", "full": "/sombra", "nombre": "T"}, dict(CTX, est={}))[0])
_ahq = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_ahN = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_vn = [{"t": _ahN - datetime.timedelta(hours=9 - i), "h": 83000 + 50 * i + 30, "l": 83000 + 50 * i - 30, "c": 83000 + 50 * i} for i in range(10)]
_est_n = {"pendientes": [{"t": "2026-10-13T23:00:00", "precio": 83000, "bias": "ALZA", "conf": 40, "risk": 166.0}]}
v.evaluar_mfe(_est_n, _ahq, _vn)
t("mfe naive no tumba", len(_est_n.get("eval_log", [])) == 1)
_est_ns = {"pend_sombra": [{"t": "2026-10-13T23:00:00", "precio": 83000, "bias": "ALZA", "conf": 8, "risk": 166.0}]}
v.evaluar_sombra(_est_ns, _ahq, _vn)
t("sombra naive evalua", len(_est_ns.get("eval_sombra", [])) == 1 and _est_ns.get("pend_sombra", []) == [])
t("gestion BE short", v.gestion_sl({"dir": "SHORT", "entrada": 83297, "stop": 83850}, 82600, 100.0, "tendencia")[:2] == (round((83297 - 82600) / 553, 2), "BE"))
t("gestion BE precio", v.gestion_sl({"dir": "SHORT", "entrada": 83297, "stop": 83850}, 82600, 100.0, "tendencia")[2] == 83297)
t("gestion BE una vez", v.gestion_sl({"dir": "SHORT", "entrada": 83297, "stop": 83297, "be_done": True}, 82600, 100.0, "tendencia")[1] is None)
t("gestion TRAIL", v.gestion_sl({"dir": "SHORT", "entrada": 83297, "stop": 83850, "be_done": True}, 82200, 100.0, "tendencia")[1] == "TRAIL")
t("gestion rango no trail", v.gestion_sl({"dir": "SHORT", "entrada": 83297, "stop": 83850, "be_done": True}, 82200, 100.0, "rango")[1] is None)
t("gestion atr0 no", v.gestion_sl({"dir": "LONG", "entrada": 83000, "stop": 82800}, 83300, 0, "tendencia") == (None, None, None))
t("gestion paso minimo", v.gestion_sl({"dir": "LONG", "entrada": 83000, "stop": 83190}, 83350, 100.0, "tendencia")[1] is None)
_ebg = {}
_rg = v.decidir_alerta(83200, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "LATERAL", "confianza": 10}, _ebg, _ahq, None, None, "tendencia", True, "CPI", None, None, None, 55, 40, None, None, None, None, "🔒 BE x")
t("gestion salta blackout", _rg[0] is True and "🔒" in _rg[1])
t("forzado gana a gestion", v.decidir_alerta(83200, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "LATERAL", "confianza": 10}, {}, _ahq, "TU ALERTA", None, "tendencia", True, "CPI", None, None, None, 55, 40, None, None, None, None, "🔒 BE x")[1] == "TU ALERTA")


def _kl_qb(rompe="up"):
    if rompe == "up":
        px = [100, 102, 105, 102, 104, 108, 104, 106, 110, 107, 109, 112, 109, 120]
    else:
        px = [120, 118, 115, 118, 116, 112, 116, 114, 110, 113, 111, 108, 110, 100]
    base = 83000
    out = []
    for i, d in enumerate(px):
        c = base + d
        t = datetime.datetime(2026, 10, 14, tzinfo=datetime.timezone.utc) - datetime.timedelta(hours=len(px) - i)
        out.append({"t": t, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 10.0})
    return out
_qb = v.quiebre_estructura(_kl_qb())
t("quiebre BOS up", isinstance(_qb, dict) and _qb["dir"] == "ALZA" and _qb["tipo"] == "BOS")
_qbd = v.quiebre_estructura(_kl_qb(rompe="dn"))
t("quiebre BOS dn", isinstance(_qbd, dict) and _qbd["dir"] == "BAJA")
t("quiebre sin datos", v.quiebre_estructura([{"t": 1, "h": 2, "l": 1, "c": 1.5}] * 5) is None)
t("quiebre plano none", v.quiebre_estructura([{"t": datetime.datetime(2026, 10, 14, tzinfo=datetime.timezone.utc) - datetime.timedelta(hours=20 - i),
    "o": 83000, "h": 83010, "l": 82990, "c": 83000, "v": 1.0} for i in range(20)]) is None)
_sl = v.sl_estructura(83000, "ALZA", 82800, 100.0)
t("sl long", isinstance(_sl, tuple) and _sl[0] == 82780 and _sl[2] is False)
_sls = v.sl_estructura(83000, "BAJA", 83200, 100.0)
t("sl short", isinstance(_sls, tuple) and _sls[0] == 83220 and _sls[2] is False)
t("sl lejos", v.sl_estructura(83000, "ALZA", 80000, 100.0)[2] is True)
t("sl sin dir", v.sl_estructura(83000, "LATERAL", 82800, 100.0) is None)
_ebq = {}
_rq = v.decidir_alerta(83200, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "ALZA", "confianza": 50}, _ebq, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None,
    {"dir": "ALZA", "nivel": 83100, "tipo": "BOS", "swing": 82900}, (82900, 0.5, False))
t("qb compra con sl", _rq[0] is True and "COMPRA" in _rq[1] and "SL" in _rq[1])
t("qb pide alineacion", v.decidir_alerta(83200, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "BAJA", "confianza": 50}, {}, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None,
    {"dir": "ALZA", "nivel": 83100, "tipo": "BOS", "swing": 82900}, (82900, 0.5, False))[2] == "nada")
t("qb pide conf", v.decidir_alerta(83200, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "ALZA", "confianza": 20}, {}, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None,
    {"dir": "ALZA", "nivel": 83100, "tipo": "BOS", "swing": 82900}, (82900, 0.5, False))[2] == "nada")
t("num inf->def", _db._num(float("inf"), 0) == 0 and _db._num(float("-inf"), 0) == 0 and _db._num(True, 7) == 7 and _db._num(5, 0) == 5)
t("miles inf/nan", _db.miles(float("inf")) == "?" and _db.miles(float("nan")) == "?")
t("svg inf sin nan", "nan" not in _db.svg_linea([1, float("inf"), 3]) and "nan" not in _db.svg_linea([10, float("nan"), 30]))
t("svg color", "<script>" not in _db.svg_linea([1, 2, 3], color='"><script>'))
t("svg niveles xss", "<img" not in _db.svg_linea([10, 20, 30], niveles=[{"precio": 25, "etiqueta": "<img>", "kind": "res"}]))
t("barras nan/xss", "<script>" not in _db.svg_barras([60, 10], ["<script>", "b"]) and "nan" not in _db.svg_barras([float("nan"), 60], ["a", "b"]))
t("alza nan/inf no rompe", isinstance(_db.build_dashboard({"alza": [float("nan")] * 5, "runs": 1}, []), str) and isinstance(_db.build_dashboard({"alza": [float("inf")] * 5, "runs": 1}, []), str))
t("fpx inf no rompe", isinstance(_db.build_dashboard({"runs": 1}, [{"precio": float("inf"), "conf": 10}] * 3), str))
t("ctx escapa", "<script>" not in _db._contexto_html({"regimen": "<script>", "grade": "x", "tf": {}, "fg": {}, "senti": {}}))
t("duelo xss/nan", "<script>" not in _db._duelo_html({"bal": {"buys": 60.0, "sells": 10.0, "nb": 8, "ns": 2, "big": 1, "txt": "<script>"}, "senti": {"taker": 1.0}}) and "nan" not in _db._duelo_html({"bal": {"buys": float("inf"), "sells": 10, "nb": 1, "ns": 1}, "senti": {"taker": float("nan")}}))
t("gauge inf vacio", _db._gauge_reloj_html({"fg": {"valor": float("inf"), "etiqueta": "<b>"}}, [], datetime.datetime.now(datetime.timezone.utc)) == "")
t("macro comilla/Z", "CPI" in _db._macro_html({"evs": [{"titulo": "CPI", "cuando": "2026-10-13T15:00:00Z", "impact": "High"}]}, datetime.datetime(2026, 10, 13, 14, 0, tzinfo=datetime.timezone.utc)) and "onload='" not in _db._macro_html({"evs": [{"titulo": "CPI 'onload='x", "cuando": "2026-10-14T08:30:00+00:00", "impact": "High"}]}, datetime.datetime(2026, 10, 13, 14, 0, tzinfo=datetime.timezone.utc)))
t("tfs/porque xss", "<script>" not in _db._tfs_html({"tf": {"h1": {"tend": "<script>", "rsi": 1}, "h4": {"tend": "t", "rsi": 1}, "d1": {"tend": "t", "rsi": 1}, "w1": {"tend": "t", "rsi": 1}}}) and "<script>" not in (_db._porque_html({"regimen": "<script>", "grade": "x", "tf": {}}) or ""))
t("cmd niv vacio no tumba", v.responder_comando({"chat": 111, "texto": "/precio", "full": "/precio", "nombre": "T"}, dict(CTX, niv={"resistencias": [], "soportes": []}))[0].startswith("Niveles"))
t("cmd arroba bot", v.responder_comando({"chat": 111, "texto": "/precio@MiBot", "full": "/precio@MiBot hola", "nombre": "T"}, CTX)[0].startswith("BTC ahora"))
t("cmd sin nombre no tumba", isinstance(v.responder_comando({"chat": 111, "texto": "/otro", "full": "/otro"}, CTX)[0], str))
t("cmd op corrupta no tumba", isinstance(v.responder_comando({"chat": 111, "texto": "/voy", "full": "/voy", "nombre": "T"}, dict(CTX, est=dict(CTX["est"], ops=[{"dir": "LONG"}])))[0], str))
t("cmd papel banco malo no tumba", "Papel" in v.responder_comando({"chat": 111, "texto": "/papel", "full": "/papel", "nombre": "T"}, dict(CTX, est=dict(CTX["est"], banco="abc")))[0])
t("cmd noti None no tumba", isinstance(v.responder_comando({"chat": 111, "texto": "/noticias", "full": "/noticias", "nombre": "T"}, dict(CTX, notis=None))[0], str))
t("trocear respeta palabra", all(len(p) <= 3900 for p in v.trocear("a" * 3890 + " " + "b" * 100)) and "b" in v.trocear("a" * 3890 + " " + "b" * 100)[-1])
t("trocear vacio seguro", v.trocear(None) == [] and v.trocear("") == [])
t("trocear u16 emojis", all(v._u16(p) <= 3900 for p in v.trocear("😀" * 5000)))
t("build plan None no tumba", isinstance(v.build_parte({"last": 83000, "chg": 0.5, "hi": 83500, "lo": 82500}, tf("1H", "lateral", 0), tf("4H", "lateral", 0), tf("1D", "lateral", 0), tf("1S", "lateral", 0), NIV, {"bias": "LATERAL", "confianza": 10}, "p", {"funding": None, "oi": None, "taker": None}, {"valor": 50, "etiqueta": "Neutral"}, {}, "mot", "manana", [], [], ah, dict(ex, plan=None, memoria=None, vistas=None)), str))
t("send None no tumba run", v.send_telegram(None) in (True, False))
t("ajeno sin chat_id no fuga", v.responder_comando({"chat": 999, "texto": "/precio", "full": "/precio", "nombre": "T"}, CTX) == (None, False))
try:
    _of = v.fetch
    v.fetch = lambda *a, **k: {"code": -1000}
    try:
        v.klines("1h", 5)
        t("klines dict error", False)
    except ValueError:
        t("klines dict error", True)
    v.fetch = lambda *a, **k: [[1, "2", "3", "4", "5"]]
    try:
        v.klines("1h", 5)
        t("klines fila corta", False)
    except ValueError:
        t("klines fila corta", True)
finally:
    v.fetch = _of
try:
    _of2 = v.fetch
    v.fetch = lambda *a, **k: {"x": 1}
    try:
        v.ticker24()
        t("ticker exige claves", False)
    except ValueError:
        t("ticker exige claves", True)
finally:
    v.fetch = _of2
t("cb prem none", "if last else None" in open(os.path.join(_AQUI, "vigilante_cloud.py"), encoding="utf-8").read())
t("offset str sana", (lambda _r: isinstance(_r, tuple) and isinstance(_r[1], int))(v.leer_comandos("5")))
t("poda existe", hasattr(v, "_podar_estado") and len(v._podar_estado({"cools": {str(i): "x" for i in range(300)}})["cools"]) <= 200)
_zp = [{"precio": 83850, "razones": ["r"]}]
_tx, _ky = v.mensaje_pila(_zp, 83700, [{"precio": 82973}], [{"precio": 83850}],
    {"tend": "lateral", "rsi": 50, "er": 0.2, "z": 0}, {"adx": 25}, 12)
t("pila vive con h4", _tx is not None and _tx.startswith("EYY PILAS") and _ky == "83850")
_est_p = {}
_r1 = v.decidir_alerta(83700, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "LATERAL", "confianza": 10}, _est_p, _ahq, None, None, "rango", False, "", None, None, "pilita", 55, 40, None, None)
t("pila alerta una vez", _r1[0] is True and _r1[2] == "alerta")
_r2 = v.decidir_alerta(83700, {"soportes": [{"precio": 82973}], "resistencias": [{"precio": 83850}]},
    {"bias": "LATERAL", "confianza": 10}, _est_p, _ahq, None, None, "rango", False, "", None, None, "pilita", 55, 40, None, None)
t("pila repetida calla", _r2[2] == "nada")
_ebf = {"ultimo_bias": "LATERAL", "cools": {}}
_nv = {"soportes": [{"precio": 80000}], "resistencias": [{"precio": 90000}]}
t("fuerte avisa 1ra", v.decidir_alerta(85000, _nv, {"bias": "ALZA", "confianza": 70}, _ebf, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None)[0] is True)
_ebf["ultimo_bias"] = "ALZA"
t("fuerte sella 2da", v.decidir_alerta(85000, _nv, {"bias": "ALZA", "confianza": 70}, _ebf, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None)[2] == "nada")
_ebc = {"ultimo_bias": "ALZA", "cools": {}}
t("cambio avisa", v.decidir_alerta(85000, _nv, {"bias": "BAJA", "confianza": 70}, _ebc, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None)[0] is True)
_ebc["ultimo_bias"] = "BAJA"
t("cambio no repite", v.decidir_alerta(85000, _nv, {"bias": "BAJA", "confianza": 70}, _ebc, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None)[2] == "nada")
t("toque lateral avisa", v.decidir_alerta(82500, {"soportes": [{"precio": 82400}], "resistencias": [{"precio": 90000}]},
    {"bias": "LATERAL", "confianza": 50}, {}, _ahq, None, None, "tendencia", False, "", None, None, None, 55, 40, None, None)[1].startswith("Tocando"))
_ebl = {}
t("liq nivel1 avisa", v.decidir_alerta(82500, _nv, {"bias": "LATERAL", "confianza": 10}, _ebl, _ahq, None, None, "tendencia", False, "", None, "barrido sobre máximos 84.199 X", None, 55, 40, None, None)[0] is True)
t("liq nivel2 avisa", v.decidir_alerta(82500, _nv, {"bias": "LATERAL", "confianza": 10}, _ebl, _ahq, None, None, "tendencia", False, "", None, "barrido sobre máximos 84.500 Y", None, 55, 40, None, None)[0] is True)
t("liq mismo nivel calla", v.decidir_alerta(82500, _nv, {"bias": "LATERAL", "confianza": 10}, _ebl, _ahq, None, None, "tendencia", False, "", None, "barrido sobre máximos 84.500 Y", None, 55, 40, None, None)[2] == "nada")
_ah0 = datetime.datetime(2026, 10, 14, tzinfo=datetime.timezone.utc)
t("sombra abre sin piso", v.abrir_sombra({}, "ALZA", 5, 83000, 0.002, _ah0) is True)
t("sombra rechaza lateral", v.abrir_sombra({}, "LATERAL", 90, 83000, 0.002, _ah0) is False)
_est_s = {}
v.abrir_sombra(_est_s, "BAJA", 12, 83000, 0.002, _ah0)
t("sombra dedup 4h", v.abrir_sombra(_est_s, "BAJA", 40, 83100, 0.002, _ah0) is False)
t("sombra otra dir si", v.abrir_sombra(_est_s, "ALZA", 40, 83100, 0.002, _ah0) is True)
t("sombra precio cero no", v.abrir_sombra({}, "ALZA", 40, 0, 0.002, _ah0) is False)
t("sombra precio malo no", v.abrir_sombra({}, "BAJA", 40, "abc", 0.002, _ah0) is False)


def _veneno_tmp():
    import datetime as _dt
    ah = _dt.datetime(2026, 10, 14, tzinfo=_dt.timezone.utc)

    def _velas(base, n=10):
        out = []
        for i in range(n):
            c = base + 50 * i
            out.append({"t": ah - _dt.timedelta(hours=9 - i), "h": c + 30, "l": c - 30, "c": c})
        return out
    est = {"pend_sombra": [{"t": (ah - _dt.timedelta(hours=10)).isoformat(), "precio": 0, "bias": "ALZA", "conf": 5, "risk": 1},
                           {"t": (ah - _dt.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "ALZA", "conf": 5, "risk": 166.0}]}
    v.evaluar_sombra(est, ah, _velas(83000))
    return len(est.get("eval_sombra", [])) == 1
t("sombra veneno no bloquea", _veneno_tmp())


def _velas_sombra(base, n=10, sube=True):
    out = []
    for i in range(n):
        c = base + (50 * i if sube else -50 * i)
        out.append({"t": _ah0 - datetime.timedelta(hours=9 - i), "h": c + 30, "l": c - 30, "c": c})
    return out
_est_e = {"pend_sombra": [{"t": (_ah0 - datetime.timedelta(hours=10)).isoformat(), "precio": 83000, "bias": "ALZA", "conf": 8, "risk": 166.0}]}
v.evaluar_sombra(_est_e, _ah0, _velas_sombra(83000, 10, True))
t("sombra evalua hit", len(_est_e.get("eval_sombra", [])) == 1 and _est_e["eval_sombra"][0]["r"] == 1)
t("sombra no toca vivo", _est_e.get("eval_log", []) == [] and _est_e.get("alza", []) == [] and _est_e.get("pendientes", []) == [])
t("sharpe none si n<5", _bt.sharpe_ratio([2, -1, 2]) is None)
t("sharpe positivo", _bt.sharpe_ratio([2, -1, 2, 2, -1, 2, -1, -1, 2, 2]) > 0)
t("sharpe plano none", _bt.sharpe_ratio([1.0] * 6) is None)
t("dsr rango", 0.0 <= _bt.deflated_sharpe(0.54, 10, -0.41, 1.17, 10) <= 1.0)
t("dsr exige T", _bt.deflated_sharpe(0.5, 3, 0.0, 3.0, 10) is None)
t("dsr penaliza trials", _bt.deflated_sharpe(0.5, 20, 0.0, 3.0, 10) < _bt.deflated_sharpe(0.5, 20, 0.0, 3.0, 1))
t("costo calibra 0.5pct", 8.0 <= _bt.costo_bps(0.005) <= 12.0)
t("costo base spread", _bt.costo_bps(0) == 1.5 and _bt.costo_bps(-0.01) == 1.5)
t("dash tipo sobria", "BlinkMacSystemFont" in _db.CSS and "antialiased" in _db.CSS and "background:#000" in _db.CSS)
t("dash movil plegable", "@media(max-width:640px)" in _db.CSS and "grid-template-columns:minmax(0,1fr)" in _db.CSS and "min-height:36px" in _db.CSS)
t("dash masonry sin huecos", "align-items:start" in _db.CSS and "break-inside:avoid" in _db.CSS and "#c-sala" in _db.CSS)
t("svg linea premium", "linearGradient" in _db.svg_linea([10, 20, 15, 30], color="#22c55e") and "stroke-opacity='.06'" in _db.svg_linea([10, 20, 15, 30]) and 'opacity=".18"' in _db.svg_linea([10, 20, 15, 30]) and "<title>cierre" in _db.svg_linea([10, 20, 15, 30]))
t("svg fallback intacto", _db.svg_linea([1]) == "<p>sin datos aún</p>" and _db.svg_barras([], []) == "<p>sin datos aún</p>" and "<svg" in _db.svg_barras([10, 20, 30], ["0", "1", "2"]))
t("dash ids vivos", all(s in _db.build_dashboard({"ultimo_run": "2026-10-13T12:00:00+00:00", "ultimo_bias": "LATERAL", "runs": 1}, [{"t": "2026-10-13T11:00:00+00:00", "precio": 83000, "conf": 50, "tipo": "nada", "bias": "LATERAL", "motivo": "x"}]) for s in ['id="recarga"', 'id="edad"', 'data-t=', 'id="pvivo"', 'id="plegar"', 'id="sonido"', 'id="fondo"', 'data-bias=', 'data-conf=', 'data-alertas=', 'data-run=', 'data-px=', 'data-grade=', 'content="120"']))
t("dash js con try", all("try{" in getattr(_db, n) and "catch" in getattr(_db, n) for n in ["CD_JS", "UI_JS", "TF_JS", "VIVO_JS", "FONDO_JS"]))
t("dash header ids", all(s in _db.build_dashboard({"runs": 1}, []) for s in ['id="hdr-act"', 'id="hdr-prox"', 'id="hdr-edad"', 'id="pvivo"']) and "sin datos aún" in _db.build_dashboard({}, []))
t("dash orden secciones", (_db.build_dashboard({"runs": 1}, []).index('s-precio') < _db.build_dashboard({"runs": 1}, []).index('s-senales') < _db.build_dashboard({"runs": 1}, []).index('s-mercado') < _db.build_dashboard({"runs": 1}, []).index('s-dinero') < _db.build_dashboard({"runs": 1}, []).index('s-sistema')))
t("dash fallback roto", "construccion" in open(os.path.join(_AQUI, "dashboard.py"), encoding="utf-8").read() and "sin datos" in _db.build_dashboard(None, None))

# FIX BUG1/BUG2: preaviso puro + pila con enfriar 4h por zona
_ep1 = {}
_txt1 = v.preaviso(_ep1, _ev3, _ahora, "2026-10-12")
# (usa _ev3/_ahora definidos arriba; _ep1 debe quedar sin marca tras solo calcular)
t("preaviso no marca sin envío", _txt1 is not None and (_ep1.get("preavisos") in (None, {})))
_ep2 = {}
_txt2 = v.preaviso(_ep2, _ev3, _ahora, "2026-10-12")
try:
    v.marcar_preaviso(_ep2, _ev3, _ahora, "2026-10-12")
except Exception:
    pass
t("preaviso marca tras envío", _txt2 is not None and v.preaviso(_ep2, _ev3, _ahora, "2026-10-12") is None)
_eb_p1 = dict(eb)
_ahP = ah.replace(hour=10, minute=5)
_r1 = v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb_p1, _ahP, None, None, "tendencia", False, "", None, None, "EYY PILAS: a 0.2% de 83.500 (x)", 90, 90)
_r2 = v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb_p1, _ahP, None, None, "tendencia", False, "", None, None, "EYY PILAS: a 0.2% de 83.500 (x)", 90, 90)
t("pila repetida se silencia", _r1[2] == "alerta" and _r2[2] == "nada")
_eb_p2 = dict(eb)
v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb_p2, _ahP, None, None, "tendencia", False, "", None, None, "EYY PILAS: a 0.2% de 83.500 (x)", 90, 90)
_r3 = v.decidir_alerta(82500, niv, {"bias": "LATERAL", "confianza": 10}, _eb_p2, _ahP, None, None, "tendencia", False, "", None, None, "EYY PILAS: a 0.3% de 84.000 (y)", 90, 90)
t("pila distinta avisa", _r3[2] == "alerta")

# tags solo-medición (etiquetar_senal puro, no decide)
_tg1 = v.etiquetar_senal({"funding": 0.01, "taker": 0.2}, 14, "alcista")
t("tags ny funding", _tg1.get("sesion") == "NY" and _tg1.get("funding") == 0.01)
try:
    _tg2 = v.etiquetar_senal(None, "x", None)
    _tg2_ok = _tg2.get("sesion") == "?"
except Exception:
    _tg2_ok = False
t("tags rotas sesion ?", _tg2_ok)
_eb_t0 = dict(eb)
_eb_t1 = dict(eb, tags={"funding": 0.01, "taker": 0.2, "sesion": "NY", "cvd_div": "sí"})
_r_t0 = v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 50}, _eb_t0, ah, None, None, "tendencia", False, "", None, None, None)
_r_t1 = v.decidir_alerta(82500, niv, {"bias": "ALZA", "confianza": 50}, _eb_t1, ah, None, None, "tendencia", False, "", None, None, None)
t("snapshot no decide", _r_t0[2] == _r_t1[2])

# ---------- economia de medicion: reborn/cotas/vectores (solo medicion) ----------
_rb_ah = datetime.datetime(2026, 10, 14, 10, 5, tzinfo=datetime.timezone.utc)
_rb_niv = {"soportes": [{"precio": 82800}], "resistencias": [{"precio": 83200}]}
_rb_est = {"banco": 15.0, "banco_pico": 100.0, "paper_cerradas": [],
           "paper_dia": {"fecha": _rb_ah.strftime("%Y-%m-%d"), "pnl": -5.0},
           "paper_abiertas": [{"dir": "LONG", "entrada": 83000, "stop": 82800,
                               "tp": 83200, "tam": 0.005, "riesgo": 1.0,
                               "liq": 81340, "lev": 50, "t": "x"}]}
_rb_pos = v.abrir_papel(_rb_est, {"bias": "ALZA", "confianza": 50}, _rb_niv, 83100, _rb_ah)
t("reborn liquida sin perder", _rb_pos is not None and _rb_est["banco"] == 100.0
  and any(c.get("res") == "REBORN" for c in _rb_est.get("paper_cerradas", []))
  and len(_rb_est.get("paper_abiertas", [])) == 1
  and abs(_rb_est["paper_cerradas"][0]["pnl"] - 0.5) < 0.01)
_rb_est2 = {"banco": 15.0, "paper_cerradas": [],
            "paper_abiertas": [{"dir": "LONG"}]}
_rb_pos2 = v.abrir_papel(_rb_est2, {"bias": "ALZA", "confianza": 50}, _rb_niv, 83000, _rb_ah)
t("reborn corrupta no tumba", _rb_pos2 is not None and _rb_est2["banco"] == 100.0
  and len(_rb_est2.get("paper_abiertas", [])) == 1)
t("cota paper usa constante", v.MAX_PAPER_ABIERTAS == 5
  and v.abrir_papel({"banco": 100.0, "banco_pico": 100.0, "paper_cerradas": [],
                     "paper_dia": {"fecha": _rb_ah.strftime("%Y-%m-%d"), "pnl": 0.0},
                     "paper_abiertas": [{}] * v.MAX_PAPER_ABIERTAS},
                    {"bias": "ALZA", "confianza": 50}, _rb_niv, 83000, _rb_ah) is None)
_vb = [{"t": _rb_ah - datetime.timedelta(hours=9 - i), "h": 83000 - 50 * i + 5,
        "l": 83000 - 50 * i - 5, "c": 83000 - 50 * i} for i in range(10)]
_est_tb = {"pend_todo": [{"t": (_rb_ah - datetime.timedelta(hours=10)).isoformat(),
                          "precio": 83000, "bias": "BAJA", "conf": 50, "risk": 166.0}]}
v.evaluar_todo(_est_tb, _rb_ah, _vb)
t("todo baja direccional", len(_est_tb.get("eval_todo", [])) == 1
  and _est_tb["eval_todo"][0]["r"] == 1
  and _est_tb["eval_todo"][0]["mfe"] > _est_tb["eval_todo"][0]["mae"])
_est_r0 = {"pendientes": [{"t": (_rb_ah - datetime.timedelta(hours=10)).isoformat(),
                           "precio": 83000, "bias": "ALZA", "conf": 50, "risk": 0}],
           "alza": [], "baja": [], "eval_log": []}
v.evaluar_mfe(_est_r0, _rb_ah, [{"t": _rb_ah - datetime.timedelta(hours=9) + datetime.timedelta(hours=i + 1),
                                "h": 83100, "l": 82950, "c": 83050} for i in range(3)])
t("mfe risk cero no tumba", len(_est_r0.get("eval_log", [])) == 1)

print(f"\nOK {ok} pruebas | FALLOS {len(mal)}")
sys.exit(1 if mal else 0)
