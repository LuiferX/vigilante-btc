#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_vigilante.py - suite del ANALIZADOR (no del operador).

REARME 2026-11-01: este archivo antes contenia 711 pruebas de la capa de
operacion (decidir_alerta, paper trading, comandos por chat, planes 2R,
trailing...), que se retiro del sistema. Las pruebas de esa capa se archivaron
en `tests_operacion_archivados/` para consulta historica y NO se ejecutan.

Lo que se prueba aqui es lo que el sistema hace: matematica de indicadores,
deteccion de estructura, niveles, regimen, sesgo, sesion y el veredicto
ANALITICO (que mide, no propone).

Uso: python -m unittest test_vigilante
"""
from __future__ import annotations

import datetime
import importlib.util
import os
import sys

UTC = datetime.timezone.utc
_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

# el modulo se carga por ruta: es LA MISMA instancia que usa el entry point
_spec = importlib.util.spec_from_file_location(
    "v", os.path.join(_AQUI, "vigilante_cloud.py"))
v = importlib.util.module_from_spec(_spec)
sys.modules["v"] = v
try:
    _spec.loader.exec_module(v)
    _CARGO = True
except Exception as _e:                                   # red caida a mitad
    _CARGO = False
    print("aviso: vigilante_cloud no se importo completo (%s); "
          "se prueban solo las partes sin red" % type(_e).__name__)

import vigilante.analisis as an  # noqa: E402
import vigilante.indicadores as ind  # noqa: E402
import vigilante.mercado as mc  # noqa: E402
import vigilante.precision as pr  # noqa: E402

FALLOS: list[str] = []
OKS = 0


def t(nombre: str, cond) -> None:
    """Registra una asercion legible (sin unittest.assert* para no abortar)."""
    global OKS
    if cond:
        OKS += 1
    else:
        FALLOS.append(nombre)
        print("  FALLA:", nombre)


# --------------------------------------------------------------- utilidades --
def vela(o, h, l, c, mins=60, vol=100.0, t0=None):
    base = t0 or (datetime.datetime(2026, 1, 1, tzinfo=UTC)
                  - datetime.timedelta(minutes=60 * 400))
    return {"t": base + datetime.timedelta(minutes=mins), "o": o, "h": h,
            "l": l, "c": c, "v": vol}


def serie(n=80, base=80000.0, paso=10.0, mins=60):
    """Serie de velas creciente y tranquila (con volumen y timestamps)."""
    t0 = datetime.datetime.now(UTC) - datetime.timedelta(minutes=mins * (n + 5))
    return [vela(base + paso * i, base + paso * i + 5,
                 base + paso * i - 5, base + paso * i, mins=i * mins,
                 t0=t0) for i in range(n)]


AH = datetime.datetime(2026, 10, 31, 12, tzinfo=UTC)


# --------------------------------------------------- 1) matematicas puras --
def test_indicadores():
    t("miles", ind.fmt_miles(83000) == "83.000" and ind.fmt_miles(0) == "0")
    t("ema const", ind.ema([5.0] * 30, 20) == 5.0)
    t("ema lag", 1 < ind.ema([float(i) for i in range(1, 31)], 20) < 30)
    t("ema corta", ind.ema([1.0, 2.0, 3.0], 20) == 3.0)
    t("rsi sube", ind.rsi([float(100 + i) for i in range(20)]) == 100.0)
    t("rsi baja", ind.rsi([float(100 - i) for i in range(20)]) == 0.0)
    t("rsi plano neutro", 40 <= ind.rsi([100.0] * 20) <= 60)
    t("rsi pocos datos no rompe", ind.rsi([1.0, 2.0]) == 50.0
      and ind.rsi([100.0] * 20) == 50.0)
    t("clamp", ind.clamp(5, 0, 3) == 3 and ind.clamp(-1, 0, 3) == 0
      and ind.clamp(1.5, 0, 3) == 1.5)
    t("atr positivo", ind.atr(serie()) > 0)
    t("atr plano cero", ind.atr([vela(100, 100, 100, 100)] * 30) == 0.0)
    t("adx rango", 0 <= ind.adx(serie()) <= 100)
    t("slope subiendo", ind.slope([float(i) for i in range(30)]) > 0)
    t("slope bajando", ind.slope([float(30 - i) for i in range(30)]) < 0)
    t("eficiencia rango", ind.eficiencia([100.0, 101.0, 102.0]) is None
      or 0 <= ind.eficiencia([100.0, 101.0, 102.0]) <= 1)
    t("eficiencia serie real", ind.eficiencia([b["c"] for b in serie()]) is not None)
    t("zscore extremo alto", ind.zscore([100.0] * 19 + [200.0]) > 2)
    # structure() devuelve (score, etiqueta)
    st = ind.structure(serie())
    t("estructura tupla", isinstance(st, tuple) and len(st) == 2)
    t("estructura etiqueta str", isinstance(st[1], str))


# --------------------------------------------- 2) estructura y regimen ------
def test_estructura():
    kl = serie()
    q = ind.quiebre_estructura(kl)
    t("quiebre no rompe", isinstance(q, (dict, type(None))))
    # find_swing_points devuelve (idx_max, idx_min)
    r = ind.find_swing_points([b["h"] for b in kl], [b["l"] for b in kl], 3)
    t("swings tupla", isinstance(r, tuple) and len(r) == 2)
    t("swings listas", all(isinstance(x, list) for x in r))
    t("swings vacio no rompe", ind.find_swing_points([], []) == ([], []))
    t("niveles iguales busca", isinstance(
        ind.find_equal_levels(ind.find_swing_points([b["h"] for b in kl],
                                                    [b["l"] for b in kl], 3)), list))
    t("mecha o None", ind.mecha_rechazo(kl) is None or isinstance(
        ind.mecha_rechazo(kl), dict))
    sl = ind.sl_estructura(83000, "ALZA", 82000, 200)
    t("sl estructura largo", isinstance(sl, tuple) and sl[0] < 83000)
    sl2 = ind.sl_estructura(83000, "BAJA", 84000, 200)
    t("sl estructura corto", isinstance(sl2, tuple) and sl2[0] > 83000)


def test_regimen():
    subida = serie(60, paso=50.0)
    t("regimen operativo str", isinstance(
        an.regimen_operativo(subida, subida), str))
    t("regimen posibles", an.regimen_operativo(subida, subida)
      in ("tendencia", "rango", "chop"))
    t("analyze devuelve dict", isinstance(an.analyze(serie(), 60, "1H"), dict))
    a = an.analyze(serie(), 60, "1H")
    t("analyze tiene atr", "atr" in a and a["atr"] >= 0)
    t("analyze tiene adx", "adx" in a)
    t("analyze vacio no rompe", isinstance(an.analyze([], 60, "1H"), dict))


# ------------------------------------------------ 3) niveles y confluencia --
def test_niveles():
    h1 = an.analyze(serie(), 60, "1H")
    h4 = an.analyze(serie(60, 90000.0), 240, "4H")
    d1 = an.analyze(serie(40, 95000.0), 1440, "1D")
    w1 = an.analyze(serie(30, 99000.0), 10080, "1S")
    niv = an.niveles(h1, h4, d1, w1, [], [], 90000.0)
    t("niveles dict", isinstance(niv, dict))
    t("tiene soportes", isinstance(niv.get("soportes"), list))
    t("tiene resistencias", isinstance(niv.get("resistencias"), list))
    t("soportes por debajo", all(n.get("precio", 0) <= 90000.0 + 1e-6
                                  for n in niv.get("soportes", [])))
    t("resistencias por encima", all(n.get("precio", 0) >= 90000.0 - 1e-6
                                      for n in niv.get("resistencias", [])))
    t("nivel trae origen", all("origen" in n for n in
                                niv.get("soportes", []) + niv.get("resistencias", [])))


# ------------------------------------------------------- 4) sesgo/analisis --
def test_direccion():
    h1 = an.analyze(serie(), 60, "1H")
    h4 = an.analyze(serie(60, 90000.0), 240, "4H")
    d1 = an.analyze(serie(40, 95000.0), 1440, "1D")
    w1 = an.analyze(serie(30, 99000.0), 10080, "1S")
    d = an.direccion(h1, h4, d1, w1)
    t("direccion dict", isinstance(d, dict))
    t("direccion sesgo valido", d.get("bias") in ("ALZA", "BAJA", "LATERAL"))
    t("direccion confianza 0-100", 0 <= (d.get("confianza") or 0) <= 100)
    t("fear greed dict", isinstance(
        an.fear_greed(d1, {"funding": 0.01, "taker": 1.0}, 1.0), dict))
    t("proxima sesion", isinstance(an.proxima_sesion(), (str, dict, type(None))))


# ------------------------------------------------- 5) veredicto ANALITICO --
def test_veredicto_analitico():
    if not _CARGO or not hasattr(v, "_veredicto_analitico"):
        t("veredicto analitico existe", False)
        return
    niv = {"resistencias": [{"precio": 30050}], "soportes": [{"precio": 29950}]}
    e, motivo, tipo = v._veredicto_analitico(
        30000, niv, {"bias": "ALZA"}, "tendencia", 1, 0.3, 0.1, None, None,
        None, {}, AH)
    t("veredicto tipo es analisis", tipo == "analisis")
    t("veredicto motivo con regimen", "gimen=" in motivo)
    t("veredicto motivo con bias", "bias=" in motivo)
    t("veredicto motivo con nivel", "nivel cercano=" in motivo)
    t("veredicto motivo sin R multiple", "R:" not in motivo)
    t("veredicto motivo sin plan", "plan" not in motivo.lower())
    t("veredicto motivo sin objetivo", "objetivo" not in motivo.lower())
    t("veredicto motivo sin stop", "stop" not in motivo.lower())

    # sin niveles: no se rompe
    e2, m2, _ = v._veredicto_analitico(30000, {}, {"bias": "LATERAL"}, "rango",
                                       0, None, None, None, None, None, None, None)
    t("veredicto sin niveles vivo", isinstance(m2, str))

    # el estado registra lo ultimo (para no repetir)
    est = {}
    v._veredicto_analitico(30000, niv, {"bias": "ALZA"}, "tendencia", 1, 0.3,
                           0.1, None, None, None, est, AH)
    t("veredicto registra estado", "ultimo_veredicto" in est)


def test_grado_analitico():
    if not _CARGO or not hasattr(v, "_grado_analitico"):
        t("grado analitico existe", False)
        return
    t("grado A con tendencia y confl", v._grado_analitico(
        {"grado": "A"}, "tendencia", 2) == "A")
    t("grado rango baja a C", v._grado_analitico({"grado": "A"}, "rango", 2) == "C")
    t("grado sin confl degrada", v._grado_analitico({"grado": "A"}, "tendencia", 0)
      in ("B", "C"))
    t("grado vacio en rango", v._grado_analitico({}, "rango", 0) == "C")
    t("grado nunca propone entrada", isinstance(
        v._grado_analitico({"grado": "A"}, "tendencia", 3), str))


def test_cerca_etiqueta():
    if not _CARGO or not hasattr(v, "cerca_etiqueta"):
        t("cerca etiqueta existe", False)
        return
    niv = {"resistencias": [{"precio": 30050}], "soportes": [{"precio": 29950}]}
    t("cerca R", v.cerca_etiqueta(niv, 30000).startswith("R "))
    t("cerca S", v.cerca_etiqueta(niv, 29998).startswith("S "))
    t("cerca sin niveles", v.cerca_etiqueta({}, 30000) == "s/d")


# ------------------------------------------------ 6) el archivo no opera --
def test_no_hay_operacion():
    """Guardian: el rearme se comprueba, no se promete."""
    if not _CARGO:
        t("modulo cargado para el guardian", False)
        return
    src = open(os.path.join(_AQUI, "vigilante_cloud.py"), encoding="utf-8").read()
    t("sin importar paper", "from vigilante.paper import" not in src)
    t("sin importar comandos", "from vigilante.comandos import" not in src)
    t("sin importar alertas", "from vigilante.alertas import" not in src)
    t("sin decidir_alerta", "decidir_alerta" not in src.replace("# ", ""))
    t("sin plan_trade", "plan_trade" not in src.replace("# ", ""))
    t("sin abrir_papel", "abrir_papel" not in src.replace("# ", ""))
    t("sin score_senal", "score_senal" not in src.replace("# ", ""))
    t("docstring dice NO OPERA", "NO OPERA" in src[:600])
    for mod in ("paper", "comandos", "alertas"):
        p = os.path.join(_AQUI, "vigilante", mod + ".py")
        t("modulo retirado: vigilante/" + mod + ".py", not os.path.exists(p))


# ------------------------------------------------------------------- main --
def main() -> int:
    print("=== suite del analizador (rearme 2026-11-01) ===")
    for fn in (test_indicadores, test_estructura, test_regimen, test_niveles,
               test_direccion, test_veredicto_analitico, test_grado_analitico,
               test_cerca_etiqueta, test_no_hay_operacion):
        try:
            fn()
        except Exception as e:                    # una seccion rota no aborta
            FALLOS.append(f"{fn.__name__}: {type(e).__name__}: {e}")
            print(f"  EXCEPCION en {fn.__name__}: {type(e).__name__} {e}")
    print(f"\nOK {OKS} | FALLOS {len(FALLOS)}")
    for f in FALLOS:
        print("  -", f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    raise SystemExit(main())
