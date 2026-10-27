#!/usr/bin/env python3
"""
expr_candidatos.py - laboratorio de candidatos al proximo modelo (stdlib puro).

Pre-registro: analysis/EXPERIMENTOS.md, seccion "Candidatos al proximo modelo
(pre-registro 2026-10-26)". Protocolo comun: MISMO replay sin mirada al futuro,
MISMOS folds temporales, MISMO embargo; comparacion contra toques-wf-1
congelado (prob_modelo de cada muestra) en los MISMOS folds.

FASE 1 (cara, una sola vez): replay extendido -> analysis/data/cache/expr_muestras.jsonl
   Copia fiel de entrenar_hold.replay (mismas etiquetas y features) mas campos
   de recorrido para el target graduado (E2): mfe/mae, hold-margen, y_estricto.
FASE 2 (barata, reproducible): evalua candidatos sobre las muestras en cache:
   baseline (congelado), C0 (re-entrenado = control de protocolo),
   E1 (regimen de volatilidad + estado sin senal),
   E3 (recalibracion rodante del intercepto),
   E4 (interacciones hora/dia x volatilidad sobre la misma clase de modelo).

Uso:
  python expr_candidatos.py --datadir analysis/data/cache --replay
  python expr_candidatos.py --datadir analysis/data/cache --eval

No ejecuta ordenes, no usa claves, no toca el modelo publicado.
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import os
import sys
from collections.abc import Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_engine as de  # noqa: E402
import entrenar_hold as eh  # noqa: E402
import evaluate_decisions as ev  # noqa: E402
import hold_model as hm  # noqa: E402

UTC = datetime.UTC
FEATURES: tuple[str, ...] = tuple(hm.MODEL["features"])
IDX_ATR288 = FEATURES.index("x_atr288")
IDX_HOURC = FEATURES.index("hourc")
IDX_DOW = FEATURES.index("dow")
IDX_ATR = FEATURES.index("atr")

SCOREBOARD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "experimentos", "scoreboard.jsonl")


# --------------------------------------------------------------------------- #
# FASE 1: replay extendido (copia fiel de eh.replay + campos de recorrido)
# --------------------------------------------------------------------------- #
def _recorrido(future: Sequence[dict], nivel: float, lado: str) -> dict:
    """MFE/MAE (% del nivel) y holgura del aguante, para el target graduado."""
    if not future:
        return {"mfe_pct": None, "mae_pct": None, "holgura": None, "barras_ruptura": None}
    hi = max(x["h"] for x in future)
    lo = min(x["l"] for x in future)
    if lado == "soporte":
        mfe = (nivel - lo) / nivel * 100.0     # cuanto entro a favor (bajada)
        mae = (hi - nivel) / nivel * 100.0     # cuanto fue en contra (subida)
        barras = next((i + 1 for i, x in enumerate(future)
                       if x["c"] < nivel * 0.995), None)
    else:
        mfe = (hi - nivel) / nivel * 100.0
        mae = (nivel - lo) / nivel * 100.0
        barras = next((i + 1 for i, x in enumerate(future)
                       if x["c"] > nivel * 1.005), None)
    cierres = [x["c"] for x in future]
    if lado == "soporte":
        holgura = (min(cierres) / nivel - 1.0) * 100.0
        y_estricto = 1 if min(cierres) >= nivel * 0.998 else 0
    else:
        holgura = (1.0 - max(cierres) / nivel) * 100.0
        y_estricto = 1 if max(cierres) <= nivel * 1.002 else 0
    return {"mfe_pct": round(mfe, 4), "mae_pct": round(mae, 4),
            "holgura": round(holgura, 4), "barras_ruptura": barras,
            "y_estricto": y_estricto}


def replay_ext(kl, htf, i0, i1):
    """Igual que eh.replay (mismas etiquetas) + campos de recorrido (E2)."""
    tiempos_htf = {iv: [b["t"] for b in barras] for iv, barras in htf.items()}
    muestras: list[dict] = []
    i = max(i0, eh.WARMUP)
    while i < i1 and i + eh.HORIZONTE < len(kl):
        corte = kl[i]["t"]
        base = max(0, i + 1 - eh.VENTANA)
        ventana = kl[base:i + 1]
        out = de.decide(
            ventana,
            price=kl[i]["c"],
            now=corte,
            htf_klines=eh.cortar_htf(htf, tiempos_htf, corte),
        )
        if out.get("ok"):
            future = kl[i + 1:i + 1 + eh.HORIZONTE]
            for lv in out.get("levels", []):
                if not isinstance(lv, dict) or not isinstance(lv.get("hold"), dict):
                    continue
                rol = lv.get("role") or "soporte"
                fd = hm.features(ventana, lv["center"], kl[i]["c"], corte, rol)
                if fd is None:
                    continue
                feats = [float(fd[name]) for name in FEATURES]
                y = 1 if ev.level_holds(future, lv["center"], rol) else 0
                rec = _recorrido(future, lv["center"], rol)
                muestras.append(
                    {
                        "t": corte.isoformat(),
                        "nivel": lv.get("center"),
                        "lado": rol,
                        "y": y,
                        "feats": [round(float(x), 8) for x in feats],
                        "prob_modelo": lv["hold"].get("prob"),
                        "calidad": lv.get("quality"),
                        "toques": lv.get("touches_6h"),
                        "confluencia": lv.get("htf_confluence"),
                        "sweep": bool(lv.get("recent_sweep")),
                        "quiebre": bool(lv.get("break_confirmed")),
                        **eh._regimen(out, corte),
                        # E2: target graduado / recorrido (viene de _recorrido)
                        **rec,
                    }
                )
        i += eh.PASO
    return muestras


def selftest(datadir: str) -> None:
    """Verifica que replay_ext produce las MISMAS etiquetas que eh.replay."""
    kl, htf = eh.cargar_velas(datadir)
    if len(kl) < eh.WARMUP + 200:
        raise SystemExit("pocas velas para el selftest")
    i0 = len(kl) - 400
    ref = eh.replay(kl, htf, i0, len(kl))
    ext = replay_ext(kl, htf, i0, len(kl))
    assert len(ref) == len(ext), f"selftest: {len(ref)} vs {len(ext)} muestras"
    for a, b in zip(ref, ext, strict=True):
        assert a["t"] == b["t"] and a["nivel"] == b["nivel"], "selftest: evento distinto"
        assert a["y"] == b["y"], "selftest: etiqueta distinta"
        assert a["feats"] == b["feats"], "selftest: features distintas"
        assert a["prob_modelo"] == b["prob_modelo"], "selftest: prob del modelo distinta"
    print(f"selftest OK: {len(ref)} muestras identicas a entrenar_hold.replay")


def fase_replay(datadir: str, desde: str, hasta: str) -> str:
    kl, htf = eh.cargar_velas(datadir)
    if not kl:
        raise SystemExit(f"sin klines en {datadir}")
    tiempos = [v["t"] for v in kl]
    i0 = bisect.bisect_left(tiempos, datetime.datetime.fromisoformat(desde))
    i1 = bisect.bisect_left(tiempos, datetime.datetime.fromisoformat(hasta))
    print(f"replay extendido: velas {len(kl)} | rango [{i0}:{i1}] | "
          f"pasos ~{(i1 - i0) // eh.PASO} ...", flush=True)
    muestras = replay_ext(kl, htf, i0, i1)
    out = os.path.join(datadir, "expr_muestras.jsonl")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": True, "desde": desde, "hasta": hasta,
                             "n": len(muestras)}, ensure_ascii=False) + "\n")
        for s in muestras:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"OK -> {out} | {len(muestras)} muestras")
    return out


# --------------------------------------------------------------------------- #
# FASE 2: candidatos sobre las mismas muestras
# --------------------------------------------------------------------------- #
def _cargar_muestras(datadir: str) -> list[dict]:
    out = os.path.join(datadir, "expr_muestras.jsonl")
    if not os.path.exists(out):
        raise SystemExit(f"falta {out}: corre primero --replay")
    muestras = []
    with open(out, encoding="utf-8") as fh:
        for linea in fh:
            r = json.loads(linea)
            if not r.get("_meta"):
                r["dt"] = datetime.datetime.fromisoformat(r["t"])
                muestras.append(r)
    return muestras


def _m(muestras: Sequence[dict], probs: Sequence[float]) -> dict:
    return eh.metricas(muestras, probs)


def _interacc(s: dict) -> list[float]:
    """Features base + interacciones manuales (E4)."""
    f = s["feats"]
    atr288 = f[IDX_ATR288]
    terc = [f[IDX_ATR] ** 2, f[IDX_ATR] * f[IDX_HOURC], f[IDX_ATR] * f[IDX_DOW],
            atr288 * f[IDX_HOURC], atr288 * f[IDX_DOW]]
    return f + terc


def _regimen_de(s: dict, cortes: Sequence[float]) -> int:
    atr288 = s["feats"][IDX_ATR288]
    if atr288 <= cortes[0]:
        return 0
    if atr288 <= cortes[1]:
        return 1
    return 2


def evaluar(muestras: list[dict], desde: str, hasta: str,
            test_dias: int = 90, train_dias: int = 365,
            embargo_horas: int = 24) -> dict:
    folds = eh.folds(datetime.datetime.fromisoformat(desde),
                     datetime.datetime.fromisoformat(hasta),
                     test_dias, train_dias, embargo_horas)
    if not folds:
        raise SystemExit("sin folds: revisa rango")

    cand: dict[str, list[dict]] = {"baseline": [], "c0": [], "e1": [],
                                    "e3": [], "e4": []}
    e1_sinsenal: list[float] = []
    detalle: dict[str, list] = {k: [] for k in cand}
    pool: dict[str, tuple[list, list]] = {}

    for n, (corte, tini, tfin) in enumerate(folds, 1):
        train = [s for s in muestras if s["dt"] <= corte]
        test = [s for s in muestras if tini <= s["dt"] < tfin]
        if len(train) < 200 or len(test) < 30:
            continue
        ytr = [float(s["y"]) for s in train]
        base_rate = sum(ytr) / len(ytr)

        # baseline: modelo congelado (prob_modelo ya viene del replay)
        cand["baseline"].append(_m(test, [s["prob_modelo"] for s in test]))

        # C0: re-entrenado, mismo protocolo (control)
        m0 = eh.entrenar(train, C=0.03)
        cand["c0"].append(_m(test, [eh.predecir(m0, s["feats"]) for s in test]))

        # E1: regimen de volatilidad (terciles de x_atr288 del TRAIN)
        vals = sorted(s["feats"][IDX_ATR288] for s in train)
        cortes = [vals[int(len(vals) / 3)], vals[int(2 * len(vals) / 3)]]
        sub = {r: eh.entrenar([s for s in train
                               if _regimen_de(s, cortes) == r], C=0.03)
               for r in range(3)
               if any(_regimen_de(s, cortes) == r for s in train)}
        p_e1, sin = [], 0
        for s in test:
            r = _regimen_de(s, cortes)
            m_r = sub.get(r) or m0
            p = eh.predecir(m_r, s["feats"])
            if abs(p - base_rate) < 0.05:
                sin += 1
            p_e1.append(p)
        cand["e1"].append(_m(test, p_e1))
        e1_sinsenal.append(sin / len(test))

        # E3: C0 recalibrado solo con los ultimos 90 dias del train
        ventana_ini = corte - datetime.timedelta(days=90)
        train_reciente = [s for s in train if s["dt"] >= ventana_ini]
        m3 = eh.recalibrar_intercepto(m0, train_reciente) if len(train_reciente) >= 50 \
            else eh.recalibrar_intercepto(m0, train)
        cand["e3"].append(_m(test, [eh.predecir(m3, s["feats"]) for s in test]))

        # E4: interacciones sobre la misma clase de modelo (logistica)
        m4 = _entrenar_ext(train)
        cand["e4"].append(_m(test, [_predecir_ext(m4, s) for s in test]))

        # pool para cortes por regimen/lado (todos los folds juntos, OOS)
        for nombre, probs in (("baseline", [s["prob_modelo"] for s in test]),
                              ("e1", p_e1), ("e3", [eh.predecir(m3, s["feats"]) for s in test]),
                              ("e4", [_predecir_ext(m4, s) for s in test])):
            pool.setdefault(nombre, ([], []))
            pool[nombre][0].extend(test)
            pool[nombre][1].extend(probs)

        detalle["baseline"].append({"fold": n, "n": len(test)})
    cortes_rg = {}
    for nombre, (ms, ps) in pool.items():
        cortes_rg[nombre] = {
            "volatilidad": eh.cortes(ms, ps, "volatilidad"),
            "lado": eh.cortes(ms, ps, "lado"),
        }
    return {"candidatos": cand, "e1_sinsenal": e1_sinsenal,
            "folds": len(cand["baseline"]), "cortes": cortes_rg}


def _entrenar_ext(train: list[dict]) -> dict:
    """Logistica L1 sobre features extendidas (reusa eh.entrenar por dentro)."""
    muestras_ext = []
    for s in train:
        t = dict(s)
        t["feats"] = _interacc(s)
        muestras_ext.append(t)
    idx = list(range(len(muestras_ext[0]["feats"])))
    # eh.entrenar usa FEATURES global solo para el default de idx; pasamos idx explicito
    return eh.entrenar(muestras_ext, C=0.03, features_idx=idx)


def _predecir_ext(modelo: dict, s: dict) -> float:
    return eh.predecir(modelo, _interacc(s))


def _consolidar(evals: list[dict]) -> dict:
    if not evals:
        return {"folds": 0}
    skills = [e.get("brier_skill") for e in evals if e.get("brier_skill") is not None]
    eces = [e.get("ece") for e in evals if e.get("ece") is not None]
    n = sum(e.get("n", 0) for e in evals)
    pos = sum(1 for v in skills if v > 0)
    return {
        "folds": len(evals),
        "n": n,
        "skill_medio": round(sum(skills) / len(skills), 4) if skills else None,
        "skill_min": round(min(skills), 4) if skills else None,
        "folds_positivos": f"{pos}/{len(skills)}",
        "racha": eh._racha_positiva(skills),
        "ece_medio": round(sum(eces) / len(eces), 4) if eces else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "data", "cache"))
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--desde", default="2023-01-01T00:00:00+00:00")
    ap.add_argument("--hasta", default="2026-09-30T22:55:00+00:00")
    ap.add_argument("--scoreboard", action="store_true",
                    help="anade filas al scoreboard de experimentos")
    a = ap.parse_args()

    if a.selftest:
        selftest(a.datadir)
        return 0
    if a.replay:
        fase_replay(a.datadir, a.desde, a.hasta)
        return 0
    if a.eval:
        pass
    else:
        ap.print_help()
        return 1

    muestras = _cargar_muestras(a.datadir)
    print(f"muestras en cache: {len(muestras)} | evaluando ...")
    res = evaluar(muestras, a.desde, a.hasta)

    print("\n=== RESULTADOS (mismos folds, mismo embargo) ===")
    tabla = {}
    for k, evs in res["candidatos"].items():
        c = _consolidar(evs)
        tabla[k] = c
        print(f"{k:9s} | skill {str(c['skill_medio']):>8s} | min {str(c['skill_min']):>8s} "
              f"| + {c['folds_positivos']:>5s} | racha {c['racha']} | ece {c['ece_medio']}")
    if res["e1_sinsenal"]:
        media = sum(res["e1_sinsenal"]) / len(res["e1_sinsenal"])
        print(f"E1 estado 'sin senal': {round(media * 100, 1)}% de las muestras de test")

    # corte por regimen de volatilidad (la pregunta del colapso: compresion)
    print("\n=== skill por regimen de volatilidad (OOS agrupado) ===")
    regs = sorted({r for v in res["cortes"].values()
                   for r in (v.get("volatilidad") or {})})
    for nombre in ("baseline", "c0", "e1", "e3", "e4"):
        cv = res["cortes"].get(nombre, {}).get("volatilidad", {})
        if not cv:
            continue
        vals = [f"{r}={cv[r]['brier_skill']:+.4f}" for r in regs if r in cv]
        ns = [f"{r}={cv[r]['n']}" for r in regs if r in cv]
        print(f"{nombre:9s} | " + "  ".join(vals))
        print(f"{'':9s} | n: " + ", ".join(ns))

    if a.scoreboard:
        os.makedirs(os.path.dirname(SCOREBOARD), exist_ok=True)
        base = tabla["baseline"]["skill_medio"]
        fila = {
            "fecha": datetime.datetime.now(UTC).isoformat(),
            "experimento": "candidatos E1/E3/E4 vs toques-wf-1",
            "protocolo": f"replay ext + {res['folds']} folds WF (test 90d, train 365d, embargo 24h)",
            "muestras": len(muestras),
            "skill_baseline_congelado": base,
            "resultados": {k: v for k, v in tabla.items()},
            "e1_sinsenal_pct": round(sum(res["e1_sinsenal"]) / len(res["e1_sinsenal"]) * 100, 1),
            "skill_por_regimen": {k: v.get("volatilidad") for k, v in res["cortes"].items()},
            "decision": "pendiente (corrida completa con el cache sin huecos)",
        }
        with open(SCOREBOARD, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"\nOK -> {SCOREBOARD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
