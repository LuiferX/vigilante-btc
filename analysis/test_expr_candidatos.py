#!/usr/bin/env python3
"""test_expr_candidatos.py - tests del laboratorio de candidatos.

Hermeticos: NO descargan datos ni dependen del cache. Verifican el cableado
(folds, regimen, interacciones, recalibracion) contra muestras sinteticas.
"""
import datetime
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import entrenar_hold as eh  # noqa: E402
import expr_candidatos as ex  # noqa: E402

UTC = datetime.UTC


def _muestra(t, y, atr288=0.001, hourc=0.0, dow=0.0, atr=0.005, prob=0.86):
    feats = [0.0] * len(eh.FEATURES)
    i_atr288 = eh.FEATURES.index("x_atr288")
    i_hourc = eh.FEATURES.index("hourc")
    i_dow = eh.FEATURES.index("dow")
    i_atr = eh.FEATURES.index("atr")
    feats[i_atr288] = atr288
    feats[i_hourc] = hourc
    feats[i_dow] = dow
    feats[i_atr] = atr
    return {
        "t": t.isoformat(), "dt": t, "nivel": 80000.0, "lado": "soporte",
        "y": y, "feats": feats, "prob_modelo": prob, "calidad": 0.5,
        "toques": 4, "confluencia": 1, "sweep": False, "quiebre": False,
        "bias": "ALZA", "volatilidad": "media", "sesion": "NY",
        "mfe_pct": 0.5, "mae_pct": 0.2, "holgura": -0.1, "barras_ruptura": None,
        "y_estricto": y,
    }


def test_folds_no_solapan_y_con_embargo():
    f = eh.folds(datetime.datetime(2023, 6, 1, tzinfo=UTC),
                 datetime.datetime(2025, 1, 1, tzinfo=UTC),
                 test_dias=90, train_dias=365, embargo_horas=24)
    assert len(f) == 2, f"esperaba 2 folds, vinieron {len(f)}"
    for corte, ini, _fin in f:
        assert corte < ini, "el embargo debe separar train de test"
    # un fold no invade el siguiente
    for i in range(len(f) - 1):
        assert f[i][2] <= f[i + 1][1], "los tests se solapan"


def test_regimen_terciles_ordenados():
    cortes = [0.0008, 0.0012]
    s_bajo = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1, atr288=0.0002)
    s_medio = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1, atr288=0.001)
    s_alto = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1, atr288=0.009)
    assert ex._regimen_de(s_bajo, cortes) == 0
    assert ex._regimen_de(s_medio, cortes) == 1
    assert ex._regimen_de(s_alto, cortes) == 2


def test_interacciones_extienden_features():
    s = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1,
                 atr288=0.002, hourc=0.7, dow=-0.1, atr=0.01)
    ext = ex._interacc(s)
    assert len(ext) == len(s["feats"]) + 5, "deben anadirse 5 interacciones"
    # atr288*hourc es la 4a interaccion (penultima), atr288*dow la ultima
    i_atr288 = eh.FEATURES.index("x_atr288")
    i_hourc = eh.FEATURES.index("hourc")
    i_dow = eh.FEATURES.index("dow")
    assert math.isclose(ext[-2], s["feats"][i_atr288] * s["feats"][i_hourc])
    assert math.isclose(ext[-1], s["feats"][i_atr288] * s["feats"][i_dow])


def test_entrenar_ext_predice_rango_valido():
    train = [_muestra(datetime.datetime(2024, 1, 1, tzinfo=UTC) + datetime.timedelta(days=i),
                      1 if i % 5 else 0, atr288=0.001 + 0.00001 * (i % 7),
                      hourc=0.3 if i % 2 else -0.3, atr=0.005 + 0.0001 * (i % 3))
             for i in range(120)]
    m = ex._entrenar_ext(train)
    p = ex._predecir_ext(m, train[0])
    assert 0.0 <= p <= 1.0, f"probabilidad fuera de rango: {p}"
    assert len(m["coef"]) == len(ex._interacc(train[0])), "coef por feature extendida"


def test_consolidar_resume_folds():
    evs = [{"n": 100, "brier_skill": 0.02, "ece": 0.05},
           {"n": 90, "brier_skill": -0.01, "ece": 0.06},
           {"n": 80, "brier_skill": 0.03, "ece": 0.04}]
    c = ex._consolidar(evs)
    assert c["folds"] == 3
    assert c["skill_medio"] == round((0.02 - 0.01 + 0.03) / 3, 4)
    assert c["folds_positivos"] == "2/3"
    assert c["racha"] == 1, "la racha positiva mas larga es 1"


def test_y_estricto_es_mas_duro_que_y():
    # soporte: closes en 0.3% por debajo del nivel -> y=0 (rompe 0.5)? no,
    # 0.3% < 0.5% aguanta (y=1) peroNO pasa el estricto (0.2%) -> y_estricto=0
    nivel = 80000.0
    c = nivel * 0.997
    future = [{"h": c, "l": c, "c": c} for _ in range(10)]
    import evaluate_decisions as ev
    assert ev.level_holds(future, nivel, "soporte") is True
    assert sum(1 for x in future if x["c"] < nivel * 0.998) == 10
    rec = ex._recorrido(future, nivel, "soporte")
    assert rec["y_estricto"] == 0, "con 0.3% de penetracion el estricto debe fallar"


def test_y_atr_barrera_escalada():
    # holgura en % de nivel; atr=0.005 (fraccion) -> barrera k*0.5%
    s = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1, atr=0.005)
    s["holgura"] = -0.2           # penetro 0.2%
    assert ex._y_atr(s, 0.25) == 0    # barrera 0.125% -> 0.2% la rompe
    assert ex._y_atr(s, 0.5) == 1     # barrera 0.25% -> 0.2% NO la rompe
    s["holgura"] = -0.6
    assert ex._y_atr(s, 0.5) == 0     # 0.6% rompe 0.25%
    assert ex._y_atr(s, 1.5) == 1     # barrera 0.75% -> 0.6% no la rompe


def test_calibrar_k_apunta_a_la_tasa_del_train():
    train = []
    for i in range(300):
        atr = 0.005
        s = _muestra(datetime.datetime(2024, 1, 1, tzinfo=UTC) + datetime.timedelta(days=i), 1, atr=atr)
        s["holgura"] = -0.6 if i % 5 == 0 else 0.0   # 20% penetra 1.2*ATR
        train.append(s)
    k = ex._calibrar_k(train, 0.8)   # tasa de aguante del binario = 0.8
    hold = sum(1 for s in train if ex._y_atr(s, k)) / len(train)
    assert abs(hold - 0.8) < 0.10, f"k={k} deja tasa {hold}"


def test_pbo_detecta_overfitting():
    n_folds = 11
    # familia sintetica: uno gana en IS por azar, otro es estable
    skills = {
        "suerte": [0.05 if i % 2 == 0 else -0.02 for i in range(n_folds)],
        "estable": [0.02] * n_folds,
        "malo": [-0.01] * n_folds,
    }
    p = ex._pbo(skills, n_folds)
    assert p["splits"] > 0
    assert 0 <= p["tasa_fallo"] <= 1
    assert set(p["rank_medio_oos"]) == {"suerte", "estable", "malo"}


def test_features_meta_extiende_y_codifica_metadatos():
    s = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1, prob=0.9)
    s["calidad"] = 7.5
    s["toques"] = 6
    s["confluencia"] = 3
    s["sweep"] = True
    s["quiebre"] = True
    s["lado"] = "resistencia"
    s["sesion"] = "Londres"
    f = ex._features_meta(s)
    assert len(f) == len(eh.FEATURES) + 11, "9 base + 11 metadatos"
    base = f[:len(eh.FEATURES)]
    assert base == s["feats"], "las 9 base van primero y sin tocar"
    meta = f[len(eh.FEATURES):]
    assert meta[0] == 0.9, "la prob del primario es la primera meta"
    assert meta[1:4] == [7.5, 6.0, 3.0], "calidad/toques/confluencia like numerics"
    assert meta[4] == 1.0 and meta[5] == 1.0, "sweep y quiebre como dummies"
    assert meta[6] == 0.0, "lado resistencia -> dummy soporte en 0"
    assert meta[7:11] == [0.0, 1.0, 0.0, 0.0], "one-hot de sesion: solo Londres"
    # sesion desconocida -> todas las dummies a 0 (no inventa categoria)
    s2 = _muestra(datetime.datetime(2024, 5, 1, tzinfo=UTC), 1)
    s2["sesion"] = None
    assert ex._features_meta(s2)[len(eh.FEATURES) + 7:] == [0.0, 0.0, 0.0, 0.0]


def test_y_meta_mide_el_acierto_del_primario():
    t = datetime.datetime(2024, 5, 1, tzinfo=UTC)
    assert ex._y_meta(_muestra(t, 1, prob=0.9)) == 1    # dice aguanta y aguanta
    assert ex._y_meta(_muestra(t, 0, prob=0.9)) == 0    # dice aguanta y rompe
    assert ex._y_meta(_muestra(t, 0, prob=0.2)) == 1    # dice rompe y rompe
    assert ex._y_meta(_muestra(t, 1, prob=0.2)) == 0    # dice rompe y aguanta
    # frontera exacta: 0.5 cuenta como "el primario dice aguanta"
    assert ex._y_meta(_muestra(t, 1, prob=0.5)) == 1
    assert ex._y_meta(_muestra(t, 0, prob=0.5)) == 0


def test_confia_es_umbral_estricto():
    assert ex._confia(0.5) is False, "en 0.5 exacto NO confia (umbral estricto)"
    assert ex._confia(0.500001) is True
    assert ex._confia(0.99) is True
    assert ex._confia(0.0) is False


def test_entrenar_meta_reusa_eh_entrenar():
    train = [_muestra(datetime.datetime(2024, 1, 1, tzinfo=UTC)
                      + datetime.timedelta(days=i),
                      1 if i % 5 else 0,
                      prob=0.9 if i % 5 else 0.55)
             for i in range(200)]
    m = ex._entrenar_meta(train)
    assert len(m["coef"]) == len(ex._features_meta(train[0])), "coef por feature del secundario"
    assert m["features_idx"] == list(range(len(ex._features_meta(train[0]))))
    for s in train[:10]:
        p = ex._predecir_meta(m, s)
        assert 0.0 <= p <= 1.0, f"probabilidad fuera de rango: {p}"


def test_evaluar_meta_combina_secundario_y_filtro():
    """El secundario debe aprender a desconfiar justo donde el primario falla."""
    train, test = [], []
    for i in range(240):
        # grupo A: p alta y acierta; grupo B: p media y FALLA (y=0 con p>=0.5)
        bueno = i % 4 != 0
        t = datetime.datetime(2024, 1, 1, tzinfo=UTC) + datetime.timedelta(days=i)
        (train if i < 180 else test).append(
            _muestra(t, 1 if bueno else 0, prob=0.92 if bueno else 0.62,
                     atr288=0.001 if bueno else 0.006))
    r = ex._evaluar_meta(train, test)
    d = r["detalle"]
    assert d["n_test"] == len(test)
    assert d["n_confia"] == len(r["trusted"]), "confiadas = muestras con p_meta > 0.5"
    assert d["cobertura"] == round(d["n_confia"] / d["n_test"], 4)
    # tasa base del secundario = tasa de acierto real del primario en el test
    aciertos = sum(ex._y_meta(s) for s in test)
    assert d["secundario"]["base_rate"] == round(aciertos / len(test), 4)
    # el combinado se calcula SOLO sobre las confiadas, con la prob del primario
    assert d["combinado"]["n"] == d["n_confia"]
    # el secundario jerarquiza: mas confianza media en el grupo que acierta
    probs = [ex._predecir_meta(ex._entrenar_meta(train), s) for s in test]
    buen = [p for p, s in zip(probs, test, strict=True) if s["prob_modelo"] > 0.8]
    mal = [p for p, s in zip(probs, test, strict=True) if s["prob_modelo"] < 0.7]
    assert buen and mal, "el sintetico debe tener ambos grupos"
    assert sum(buen) / len(buen) > sum(mal) / len(mal), "el secundario no separa acierto/fallo"


def test_decision_meta_aplica_el_liston_pre_registrado():
    folds = 11
    res = {
        "candidatos": {
            "baseline": [{"brier_skill": 0.02} for _ in range(folds)],
            "meta": [{"brier_skill": 0.03} for _ in range(folds)],
        },
        "pbo": {"rank_medio_oos": {"meta": 1.5}},
        "meta_detalle": [
            {"n_test": 100, "n_confia": 80, "cobertura": 0.8,
             "secundario": {"brier_skill": 0.01}, "combinado": {"brier_skill": 0.03}}
            for _ in range(folds)
        ],
    }
    tabla = {"baseline": {"skill_medio": 0.02}, "meta": {"skill_medio": 0.03}}
    gana = ex._decision_meta(res, tabla)
    assert gana["gano"] is True, "cumple las 5 condiciones del liston"
    assert all(gana["checks"].values())

    # ahora una cada vez: cobertura < 50% debe tumbar el veredicto
    res["meta_detalle"] = [dict(d, cobertura=0.3, n_confia=30) for d in res["meta_detalle"]]
    mal = ex._decision_meta(res, tabla)
    assert mal["gano"] is False
    assert mal["checks"]["cobertura_>=50%"] is False

    # skill combinado por debajo del campeon + 0.005 tambien
    res["meta_detalle"] = [dict(d, cobertura=0.8, n_confia=80) for d in res["meta_detalle"]]
    res["candidatos"]["meta"] = [{"brier_skill": 0.021} for _ in range(folds)]
    tabla["meta"]["skill_medio"] = 0.021
    flojo = ex._decision_meta(res, tabla)
    assert flojo["gano"] is False
    assert flojo["checks"]["combinado_supera_campeon_+0.005"] is False


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FALLO {nombre}: {e}")
            except Exception as e:  # noqa: BLE001
                fallos += 1
                print(f"ERROR {nombre}: {type(e).__name__}: {e}")
    print(f"\n{fallos} fallos")
    sys.exit(1 if fallos else 0)
