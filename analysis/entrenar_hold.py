
# NOTA: El modelo publicado (toques-wf-1) está CONGELADO.
# Cualquier re-entrenamiento debe seguir los criterios de EXPERIMENTOS.md.
#!/usr/bin/env python3
"""
entrenar_hold.py - WALK-FORWARD honesto del modelo de aguante (stdlib puro).

El modelo publicado (analysis/hold_model.py) tiene los coeficientes pegados a
mano: se entreno fuera del repo y nadie puede reproducirlo ni mejorarlo con
evidencia. Este script cierra ese hueco:

  1. REPLAY sin mirada al futuro (misma disciplina que backtest.py):
     paso = horizonte = 48 velas 5m (ventanas NO solapadas), warm-up 300,
     contexto solo con velas <= corte, HTF cortado por bisect.
  2. El mismo target que el modelo: hold_4h_0.5pct sobre niveles con 3+ toques.
  3. WALK-FORWARD con folds temporales y embargo de 24 h (288 velas 5m):
     el train de cada fold sale del MISMO replay (la ventana que precede al
     fold dentro del embargo), asi que nunca se ve el futuro.
  4. Logistica L1 por gradiente proximal (ISTA), C=0.03 por defecto (el C
     documentado del modelo original), Estandarizacion con mean/scale del train.
  5. Recalibracion opcional de SOLO el intercepto sobre el train (Platt-lite):
     no toca la pendiente, no colapsa a la tasa base.
  6. Metricas por fold y consolidadas: Brier, Brier skill, ECE, muestras,
     cortes por lado / volatilidad / sesion.

No ejecuta ordenes, no usa claves, no usa red siya estan las velas.

Uso:
  python entrenar_hold.py --datadir <dir con klines_5m/1h/4h/1d.jsonl> \
      --desde 2023-01-01 --hasta 2026-09-30 --test-dias 90 --train-dias 365 \
      --embargo-horas 24 --out-folds data/wf_folds.json
"""

from __future__ import annotations

import argparse
import bisect
import datetime
import json
import math
import os
import sys
from collections.abc import Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_engine as de  # noqa: E402
import evaluate_decisions as ev  # noqa: E402
import hold_model as hm  # noqa: E402

UTC = datetime.UTC
FEATURES: tuple[str, ...] = tuple(hm.MODEL["features"])
EMBARGO_VELAS = 288  # 24 h de 5 m
WARMUP = 300
PASO = 48
HORIZONTE = 48
# Ventana de trabajo acotada. Con 3000 velas 5m (10 dias) la EMA200 del modelo
# ya esta convergida: el efecto de la semilla decae como (1-1/200)^2800 ~ 8e-7,
# es decir <0,0001% sobre el valor. Acotar no cambia las features de forma
# medible (verificado contra backfill sobre la ventana completa) y evita el
# coste O(n^2) de rebanar la serie entera en cada corte. Las ETIQUETAS no
# dependen de la ventana: se calculan con las 48 velas siguientes.
VENTANA = 3000
HTF_COLA = 300  # barras recientes por temporalidad (1d: 300 dias)
CTX_DIAS = 5  # margen extra sobre el inicio del train


# --------------------------------------------------------------------------- #
# carga de datos
# --------------------------------------------------------------------------- #
def cargar_velas(datadir: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """5m + {1h,4h,1d}, ordenados por tiempo."""
    kl = hm.load_klines_jsonl(os.path.join(datadir, "klines_5m.jsonl"))
    kl.sort(key=lambda v: v["t"])
    htf: dict[str, list[dict]] = {}
    for iv in ("1h", "4h", "1d"):
        p = os.path.join(datadir, f"klines_{iv}.jsonl")
        if os.path.exists(p):
            barras = hm.load_klines_jsonl(p)
            barras.sort(key=lambda v: v["t"])
            htf[iv] = barras
    return kl, htf


def _idx_paraFecha(tiempos: list[datetime.datetime], cuando: datetime.datetime) -> int:
    return bisect.bisect_left(tiempos, cuando)


def cortar_htf(
    htf: dict[str, list[dict]],
    tiempos_htf: dict[str, list[datetime.datetime]],
    cutoff: datetime.datetime,
) -> dict[str, list[dict]]:
    """HTF sin futuro y acotado a las ultimas HTF_COLA barras (O(log n + HTF_COLA))."""
    out: dict[str, list[dict]] = {}
    for iv, barras in htf.items():
        if not barras:
            continue
        idx = bisect.bisect_right(tiempos_htf[iv], cutoff)
        if idx <= 0:
            continue
        out[iv] = barras[max(0, idx - HTF_COLA) : idx]
    return out


# --------------------------------------------------------------------------- #
# replay: muestras etiquetadas sin mirada al futuro
# --------------------------------------------------------------------------- #
def _regimen(out: dict, ahora: datetime.datetime) -> dict:
    state = out.get("state") if isinstance(out.get("state"), dict) else {}
    h = ahora.hour + ahora.minute / 60.0
    ses = (
        "NY"
        if 13 <= h < 20
        else ("Londres" if 8 <= h < 13 else ("Asia" if 0 <= h < 8 else "noche"))
    )
    return {
        "bias": state.get("bias"),
        "volatilidad": state.get("volatility"),
        "sesion": ses,
    }


def replay(
    kl: list[dict],
    htf: dict[str, list[dict]],
    i0: int,
    i1: int,
    step: int = PASO,
    horizon: int = HORIZONTE,
    warmup: int = WARMUP,
) -> list[dict]:
    """Muestras etiquetadas con evento en kl[i0..i1]. Solo usa velas <= corte."""
    tiempos_htf = {iv: [b["t"] for b in barras] for iv, barras in htf.items()}
    muestras: list[dict] = []
    i = max(i0, warmup)
    while i < i1 and i + horizon < len(kl):
        corte = kl[i]["t"]
        base = max(0, i + 1 - VENTANA)
        ventana = kl[base : i + 1]
        out = de.decide(
            ventana,
            price=kl[i]["c"],
            now=corte,
            htf_klines=cortar_htf(htf, tiempos_htf, corte),
        )
        if out.get("ok"):
            future = kl[i + 1 : i + 1 + horizon]
            for lv in out.get("levels", []):
                if not isinstance(lv, dict) or not isinstance(lv.get("hold"), dict):
                    continue
                rol = lv.get("role") or "soporte"
                fd = hm.features(ventana, lv["center"], kl[i]["c"], corte, rol)
                if fd is None:
                    continue
                feats = [float(fd[name]) for name in FEATURES]
                y = 1 if ev.level_holds(future, lv["center"], rol) else 0
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
                        **_regimen(out, corte),
                    }
                )
        i += step
    return muestras


# --------------------------------------------------------------------------- #
# logistica L1 (stdlib, gradiente proximal)
# --------------------------------------------------------------------------- #
def _sig(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-min(z, 30.0)))
    e = math.exp(max(z, -30.0))
    return e / (1.0 + e)


def entrenar(
    muestras: Sequence[dict],
    C: float = 0.03,
    iters: int = 400,
    features_idx: Sequence[int] | None = None,
    l1: bool = True,
    lr: float = 0.5,
) -> dict:
    """Logistica L1 proximal. Modelo = {coef, intercept, mean, scale, features_idx}."""
    idx = list(range(len(FEATURES))) if features_idx is None else list(features_idx)
    n = len(muestras)
    if n == 0:
        raise ValueError("train vacio")
    k = len(idx)
    X = [[s["feats"][j] for j in idx] for s in muestras]
    y = [float(s["y"]) for s in muestras]
    mean = [sum(x[j] for x in X) / n for j in range(k)]
    var = [sum((x[j] - mean[j]) ** 2 for x in X) / n for j in range(k)]
    scale = [math.sqrt(v) if v > 1e-18 else 1.0 for v in var]
    Z = [[(x[j] - mean[j]) / scale[j] for j in range(k)] for x in X]
    w = [0.0] * k
    pos = max(sum(y), 1e-9)
    b = math.log(pos / max(n - sum(y), 1e-9))
    thr = lr * (1.0 / (C * n)) if l1 else 0.0
    for _ in range(iters):
        gw = [0.0] * k
        gb = 0.0
        for zi, yi in zip(Z, y, strict=True):
            d = _sig(sum(w[j] * zi[j] for j in range(k)) + b) - yi
            for j in range(k):
                gw[j] += d * zi[j]
            gb += d
        delta = 0.0
        nw = []
        for j in range(k):
            v = w[j] - lr * gw[j] / n
            if l1:
                v = math.copysign(max(abs(v) - thr, 0.0), v)
            delta = max(delta, abs(v - w[j]))
            nw.append(v)
        b -= lr * gb / n
        w = nw
        if delta < 1e-10:
            break
    return {
        "coef": w,
        "intercept": b,
        "mean": mean,
        "scale": scale,
        "features_idx": idx,
        "n_train": n,
        "C": C,
        "l1": l1,
    }


def predecir(modelo: dict, feats: Sequence[float]) -> float:
    idx = modelo.get("features_idx") or list(range(len(FEATURES)))
    z = modelo["intercept"]
    for j, k in enumerate(idx):
        z += (
            modelo["coef"][j] * (float(feats[k]) - modelo["mean"][j]) / (modelo["scale"][j] + 1e-12)
        )
    return _sig(z)


def recalibrar_intercepto(
    modelo: dict, muestras: Sequence[dict], iters: int = 300, lr: float = 0.5
) -> dict:
    """Platt-lite: mueve SOLO el intercepto sobre el train (pendiente fija)."""
    idx = modelo.get("features_idx") or list(range(len(FEATURES)))
    Z: list[float] = []
    for s in muestras:
        z = 0.0
        for j, k in enumerate(idx):
            z += (
                modelo["coef"][j]
                * (s["feats"][k] - modelo["mean"][j])
                / (modelo["scale"][j] + 1e-12)
            )
        Z.append(z)
    y = [float(s["y"]) for s in muestras]
    b = modelo["intercept"]
    n = max(len(Z), 1)
    for _ in range(iters):
        g = sum(_sig(zi + b) - yi for zi, yi in zip(Z, y, strict=True))
        paso = lr * g / n
        b -= paso
        if abs(paso) < 1e-11:
            break
    nuevo = dict(modelo)
    nuevo["intercept"] = b
    nuevo["recalibrado"] = True
    return nuevo


# --------------------------------------------------------------------------- #
# metricas
# --------------------------------------------------------------------------- #
EDGES = (0.0, 0.60, 0.70, 0.80, 1.01)


def ece(probs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Error de calibracion ponderado por tamano de bin."""
    grupos: list[list[tuple[float, float]]] = [[], [], [], []]
    for p, yv in zip(probs, ys, strict=True):
        p = min(1.0, max(0.0, p))
        for i in range(4):
            if EDGES[i] <= p < EDGES[i + 1] or (i == 3 and p == 1.0):
                grupos[i].append((p, yv))
                break
    acc = 0.0
    n = 0
    for g in grupos:
        if not g:
            continue
        mp = sum(x[0] for x in g) / len(g)
        mr = sum(x[1] for x in g) / len(g)
        acc += abs(mp - mr) * len(g)
        n += len(g)
    return round(acc / n, 4) if n else None


def metricas(muestras: Sequence[dict], probs: Sequence[float]) -> dict:
    n = len(muestras)
    if n == 0:
        return {"n": 0}
    ys = [float(s["y"]) for s in muestras]
    brier = sum((p - yv) ** 2 for p, yv in zip(probs, ys, strict=True)) / n
    base = sum(ys) / n
    bb = base * (1 - base)
    skill = 1 - brier / bb if bb > 0 else None
    return {
        "n": n,
        "brier": round(brier, 4),
        "brier_base": round(bb, 4),
        "base_rate": round(base, 4),
        "brier_skill": round(skill, 4) if skill is not None else None,
        "mean_prob": round(sum(probs) / n, 4),
        "ece": ece(list(probs), ys),
    }


def cortes(muestras: Sequence[dict], probs: Sequence[float], clave: str) -> dict:
    grupos: dict[str, list[int]] = {}
    for i, s in enumerate(muestras):
        grupos.setdefault(str(s.get(clave)), []).append(i)
    return {
        k: metricas([muestras[i] for i in ix], [probs[i] for i in ix])
        for k, ix in grupos.items()
        if ix
    }


# --------------------------------------------------------------------------- #
# folds
# --------------------------------------------------------------------------- #
def folds(
    desde: datetime.datetime,
    hasta: datetime.datetime,
    test_dias: int,
    train_dias: int,
    embargo_horas: int,
) -> list[tuple[datetime.datetime, datetime.datetime, datetime.datetime]]:
    """(corte_train, test_ini, test_fin): el train usa muestras <= corte_train."""
    out: list[tuple[datetime.datetime, datetime.datetime, datetime.datetime]] = []
    t = desde + datetime.timedelta(days=train_dias)
    while t + datetime.timedelta(days=test_dias) <= hasta:
        out.append(
            (
                t - datetime.timedelta(hours=embargo_horas),
                t,
                t + datetime.timedelta(days=test_dias),
            )
        )
        t += datetime.timedelta(days=test_dias)
    return out


def _racha_positiva(vals: Sequence[float | None]) -> int:
    mejor = actual = 0
    for v in vals:
        if v is not None and v > 0:
            actual += 1
            mejor = max(mejor, actual)
        else:
            actual = 0
    return mejor


# --------------------------------------------------------------------------- #
# orquestacion
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward honesto del modelo de aguante")
    ap.add_argument("--datadir", required=True)
    ap.add_argument("--desde", default="2023-01-01")
    ap.add_argument("--hasta", default="2026-09-30")
    ap.add_argument("--test-dias", type=int, default=90)
    ap.add_argument("--train-dias", type=int, default=365)
    ap.add_argument("--embargo-horas", type=int, default=24)
    ap.add_argument("--C", type=float, default=0.03)
    ap.add_argument("--iters", type=int, default=400)
    ap.add_argument("--recalibrar", action="store_true", help="H2: intercepto sobre train")
    ap.add_argument("--features", default=None, help="H4: subconjuto p.ej. 0,1,6,7,8")
    ap.add_argument("--out-folds", default="data/wf_folds.json")
    ap.add_argument("--out-muestras", default="data/wf_muestras.jsonl")
    ap.add_argument("--etiqueta", default=None, help="id del experimento (scoreboard)")
    ap.add_argument(
        "--holdout-ini",
        default=None,
        help="modo holdout: entrena TODO lo anterior a esta fecha y prueba el periodo",
    )
    ap.add_argument("--holdout-fin", default=None, help="fin del periodo de holdout")
    ap.add_argument(
        "--guardar-modelo",
        default=None,
        help="ruta para guardar el modelo final (JSON)",
    )
    args = ap.parse_args()

    desde = datetime.datetime.fromisoformat(args.desde).replace(tzinfo=UTC)
    hasta = datetime.datetime.fromisoformat(args.hasta).replace(tzinfo=UTC)
    f_idx = [int(x) for x in args.features.split(",")] if args.features else None

    kl, htf = cargar_velas(args.datadir)
    tiempos = [v["t"] for v in kl]
    print(f"velas 5m: {len(kl)} ({tiempos[0].date()} -> {tiempos[-1].date()})")

    if args.holdout_ini:
        h_ini = datetime.datetime.fromisoformat(args.holdout_ini).replace(tzinfo=UTC)
        h_fin = (
            datetime.datetime.fromisoformat(args.holdout_fin).replace(tzinfo=UTC)
            if args.holdout_fin
            else tiempos[-1]
        )
        lista = [(h_ini - datetime.timedelta(hours=args.embargo_horas), h_ini, h_fin)]
        print(
            f"modo HOLDOUT: train < {h_ini.date()} (embargo {args.embargo_horas}h) "
            f"-> test {h_ini.date()}..{h_fin.date()}"
        )
    else:
        lista = folds(desde, hasta, args.test_dias, args.train_dias, args.embargo_horas)
        print(f"folds: {len(lista)}")

    filas: list[dict] = []
    todas: list[dict] = []
    modelo_final: dict | None = None
    for corte_train, t_ini, t_fin in lista:
        # replay una sola vez por fold: desde (corte_train - train_dias - ctx) hasta t_fin
        # -> las muestras con t <= corte_train son TRAIN; las demas, TEST.
        i0 = _idx_paraFecha(
            tiempos,
            corte_train
            - datetime.timedelta(days=args.train_dias)
            - datetime.timedelta(days=CTX_DIAS),
        )
        i1 = _idx_paraFecha(tiempos, t_fin)
        muestras = replay(kl, htf, i0, i1)
        train = [m for m in muestras if datetime.datetime.fromisoformat(m["t"]) <= corte_train]
        test = [
            m for m in muestras if corte_train < datetime.datetime.fromisoformat(m["t"]) <= t_fin
        ]
        if len(train) < 200 or len(test) < 20:
            print(f"fold {t_ini.date()}: train={len(train)} test={len(test)} -> salta")
            continue
        modelo = entrenar(train, C=args.C, iters=args.iters, features_idx=f_idx)
        usado = recalibrar_intercepto(modelo, train) if args.recalibrar else modelo
        probs = [predecir(usado, m["feats"]) for m in test]
        mwf = metricas(test, probs)
        mpub = metricas(test, [m["prob_modelo"] for m in test])
        fila = {
            "fold": f"{t_ini.date()}..{t_fin.date()}",
            "train_n": len(train),
            "test_n": len(test),
            "wf": mwf,
            "publicado_in_sample": mpub,
            "por_lado": cortes(test, probs, "lado"),
            "por_volatilidad": cortes(test, probs, "volatilidad"),
            "por_sesion": cortes(test, probs, "sesion"),
        }
        filas.append(fila)
        todas.extend(
            {"fold": fila["fold"], "p": round(p, 4), **m} for m, p in zip(test, probs, strict=True)
        )
        modelo_final = usado
        print(
            f"fold {fila['fold']}: n={mwf['n']} skill_wf={mwf['brier_skill']} "
            f"ECE={mwf['ece']} | publicado={mpub['brier_skill']}"
        )

    skills = [f["wf"]["brier_skill"] for f in filas]
    resumen = {
        "generado": datetime.datetime.now(UTC).isoformat(),
        "folds": len(filas),
        "muestras_oos": sum(f["test_n"] for f in filas),
        "skill_wf_folds": skills,
        "skill_wf_medio": round(sum(skills) / len(skills), 4) if skills else None,
        "publicado_folds": [f["publicado_in_sample"]["brier_skill"] for f in filas],
        "racha_positiva": _racha_positiva(skills),
        "cumple_dos_seguidos": _racha_positiva(skills) >= 2,
        "etiqueta": args.etiqueta,
        "C": args.C,
        "recalibrado": bool(args.recalibrar),
        "features": args.features,
        "holdout": (
            {"ini": args.holdout_ini, "fin": args.holdout_fin} if args.holdout_ini else None
        ),
    }
    if args.guardar_modelo and modelo_final:
        os.makedirs(os.path.dirname(args.guardar_modelo) or ".", exist_ok=True)
        paquete = {
            "version": f"hold-wf-{resumen['generado'][:10]}",
            "target": "hold_4h_0.5pct",
            "C": args.C,
            "l1": modelo_final.get("l1", True),
            "recalibrado_intercepto": bool(args.recalibrar),
            "features": [
                FEATURES[i] for i in (modelo_final.get("features_idx") or range(len(FEATURES)))
            ],
            "coef": modelo_final["coef"],
            "intercept": modelo_final["intercept"],
            "mean": modelo_final["mean"],
            "scale": modelo_final["scale"],
            "entrenado_hasta": (args.holdout_ini or resumen["folds"] and "ver folds"),
            "holdout": resumen.get("holdout"),
            "skill_holdout": filas[-1]["wf"]["brier_skill"] if filas else None,
            "ece_holdout": filas[-1]["wf"]["ece"] if filas else None,
        }
        with open(args.guardar_modelo, "w", encoding="utf-8") as fh:
            json.dump(paquete, fh, ensure_ascii=False, indent=1)
        print(f"modelo guardado en {args.guardar_modelo}")
    os.makedirs(os.path.dirname(args.out_folds) or ".", exist_ok=True)
    with open(args.out_folds, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen, "folds": filas}, fh, ensure_ascii=False, indent=1)
    with open(args.out_muestras, "w", encoding="utf-8") as fh:
        for m in todas[-20000:]:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
