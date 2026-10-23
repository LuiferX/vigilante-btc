"""Tests del validation bot. Sin red, sin ordenes."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import validation as v


START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def _write_klines(path, n=6500):
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(n):
            t = START + timedelta(minutes=5 * i)
            price = 80000.0 + 100.0 * ((i % 24) - 12) / 12.0
            fh.write(
                json.dumps(
                    {
                        "openTime": int(t.timestamp() * 1000),
                        "open": str(price),
                        "high": str(price + 40),
                        "low": str(price - 40),
                        "close": str(price),
                        "volume": "100",
                    }
                )
                + "\n"
            )


def _setup(
    td,
    *,
    events=10,
    spacing=48,
    levels=1,
    eval_samples=None,
    brier=0.12,
    skill=0.15,
    ece=0.03,
    prob=0.80,
    backtest_samples=120,
    backtest_skill=0.10,
    write_klines=True,
):
    kpath = os.path.join(td, "klines_5m.jsonl")
    dpath = os.path.join(td, "decisions.jsonl")
    epath = os.path.join(td, "eval.json")
    bpath = os.path.join(td, "backtest.json")
    now = START + timedelta(minutes=5 * 6500)

    if write_klines:
        _write_klines(kpath)

    with open(dpath, "w", encoding="utf-8") as fh:
        for k in range(events):
            idx = 300 + k * spacing
            event = START + timedelta(minutes=5 * idx)
            fh.write(
                json.dumps(
                    {
                        "event_time": event.isoformat(),
                        "levels": [
                            {
                                "center": 80000.0,
                                "role": "soporte",
                                "hold_prob": prob,
                                "quality": 8.0,
                            }
                            for _ in range(levels)
                        ],
                    }
                )
                + "\n"
            )

    if eval_samples is None:
        eval_samples = events * levels
    _write_json(
        epath,
        {
            "ok": True,
            "samples": eval_samples,
            "status": "ok" if eval_samples >= 30 else "muestra_chica",
            "brier": brier,
            "base_rate": 0.80,
            "mean_prob": prob,
            "brier_skill": skill,
            "calibration_error": ece,
            "bins": [
                {
                    "bin": "0.80-1.01",
                    "n": eval_samples,
                    "pred": prob,
                    "real": 0.80,
                }
            ]
            if eval_samples
            else [],
        },
    )
    _write_json(
        bpath,
        {
            "ok": True,
            "samples": backtest_samples,
            "brier": 0.16,
            "brier_skill": backtest_skill,
            "mean_prob": prob,
            "bins": [{"bin": "0.80-1.01", "n": backtest_samples}],
        },
    )
    return {
        "klines": kpath,
        "decisions": dpath,
        "eval": epath,
        "backtest": bpath,
        "now": now,
    }


class ValidationTest(unittest.TestCase):
    def test_sin_muestras(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=5, eval_samples=0)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "sin_muestras")
            self.assertEqual(out["sample_status"], "sin_muestras")
            self.assertIn("Sin muestras", out["headline"])
            self.assertTrue(any("4h de futuro" in w for w in out["warnings"]))

    def test_ok_with_enough_independent_samples(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=120, spacing=48, eval_samples=120)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "ok")
            self.assertTrue(out["healthy"])
            self.assertEqual(out["samples"]["eval"], 120)
            self.assertEqual(out["samples"]["effective"], 120)
            self.assertEqual(out["sample_status"], "suficiente")
            # H6: los eventos sinteticos quedan fuera de la ventana de 48h ->
            # la deriva es indeterminada (no "ok"); con eventos recientes es 0.
            self.assertEqual(out["drift"]["status"], "sin_datos")

    def test_drift_ok_con_eventos_recientes(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=120, spacing=48, eval_samples=120)
            # comprimir los eventos sinteticos dentro de la ventana de 48h
            # (120 eventos cada 20 min = 40 h, todos recientes)
            with open(paths["decisions"], encoding="utf-8") as fh:
                filas = [json.loads(l) for l in fh if l.strip()]
            base = paths["now"] - timedelta(hours=40)
            with open(paths["decisions"], "w", encoding="utf-8") as fh:
                for i, r in enumerate(filas):
                    r["event_time"] = (base + timedelta(minutes=20 * i)).isoformat()
                    fh.write(json.dumps(r) + "\n")
            out = v.validate(
                paths["eval"], paths["backtest"], paths["decisions"],
                paths["klines"], now=paths["now"],
            )
            self.assertEqual(out["drift"]["status"], "ok")
            self.assertAlmostEqual(out["drift"]["psi"], 0.0, places=2)

    def test_overlap_reduces_effective_sample(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=120, spacing=12, eval_samples=120)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "muestra_media")
            self.assertEqual(out["sample_status"], "muestra_media")
            self.assertLess(out["samples"]["effective"], out["samples"]["eval"])
            self.assertEqual(out["samples"]["independent_events"], 30)
            self.assertTrue(
                any("solapamiento" in w for w in out["warnings"])
            )

    def test_degraded_when_skill_is_negative(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(
                td,
                events=120,
                spacing=48,
                eval_samples=120,
                skill=-0.20,
                ece=0.02,
            )
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "degradado")
            self.assertFalse(out["healthy"])
            self.assertTrue(any("Brier skill negativo" in w for w in out["warnings"]))

    def test_roto_without_klines(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, write_klines=False)
            out = v.validate(
                paths["eval"],
                paths["backtest"],
                paths["decisions"],
                paths["klines"],
                now=paths["now"],
            )
            self.assertEqual(out["status"], "roto")
            self.assertFalse(out["ok"])
            self.assertFalse(out["data"]["klines"]["ok"])

    def test_psi(self):
        equal = [10, 10, 10, 10]
        self.assertEqual(v.psi(equal, equal), 0.0)
        shifted = v.psi([100, 0, 0, 0], [0, 0, 0, 100])
        self.assertIsNotNone(shifted)
        self.assertGreater(shifted, 1.0)
        self.assertIsNone(v.psi([], [1, 2, 3, 4]))

    def test_history_dedup_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "history.jsonl")
            v._append_history(path, {"checked_at": "2026-10-21T00:00:00+00:00", "x": 1})
            v._append_history(path, {"checked_at": "2026-10-21T00:00:00+00:00", "x": 2})
            v._append_history(path, {"checked_at": "2026-10-21T00:05:00+00:00", "x": 3})
            rows = v._load_jsonl(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1]["x"], 3)

    def test_does_not_contain_order_or_network_calls(self):
        path = os.path.join(os.path.dirname(__file__), "validation.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read().lower()
        self.assertNotIn("place_order", source)
        self.assertNotIn("api.binance", source)
        self.assertNotIn("requests.", source)


class OosChannelTest(unittest.TestCase):
    """Canal OOS: el backtest purgado como evidencia alternativa (noche 9)."""

    def test_oos_summary_sin_solapamiento(self):
        bt = {
            "ok": True, "samples": 189, "decisions": 127,
            "step_bars": 48, "horizon_bars": 48,
            "brier": 0.13, "brier_skill": 0.0019,
            "base_rate": 0.84, "mean_prob": 0.77,
            "start": "2026-10-01T00:00:00+00:00",
            "bins": [{"bin": "0.80-1.01", "n": 89, "pred": 0.846, "real": 0.888}],
        }
        oos = v.oos_summary(bt)
        self.assertTrue(oos["available"])
        self.assertEqual(oos["effective"], 189)
        self.assertFalse(oos["solape_descontado"])
        self.assertAlmostEqual(oos["ece"], abs(0.846 - 0.888), places=3)

    def test_oos_summary_descuenta_solapamiento(self):
        bt = {"ok": True, "samples": 60, "decisions": 30,
              "step_bars": 16, "horizon_bars": 48, "brier_skill": 0.02}
        oos = v.oos_summary(bt)
        self.assertEqual(oos["effective"], 20)
        self.assertTrue(oos["solape_descontado"])

    def test_oos_valido(self):
        oos = {"available": True, "effective": 189, "brier_skill": 0.0019, "ece": 0.0655}
        self.assertTrue(v.oos_valido(oos, {"status": "ok"}))
        self.assertFalse(v.oos_valido(oos, {"status": "alert"}))
        self.assertFalse(v.oos_valido(
            {"available": True, "effective": 39, "brier_skill": 0.02, "ece": 0.06},
            {"status": "ok"}))
        self.assertFalse(v.oos_valido(
            dict(oos, brier_skill=0.0), {"status": "ok"}))
        self.assertFalse(v.oos_valido(
            dict(oos, ece=0.09), {"status": "ok"}))
        self.assertFalse(v.oos_valido({}, {"status": "ok"}))

    def test_validate_abre_canal_oos_cuando_el_vivo_es_chico(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, spacing=48, eval_samples=8,
                           backtest_samples=189, backtest_skill=0.0019)
            # decisiones vivas con distribucion coherente al backtest (sin drift)
            probs = [0.65, 0.65, 0.75, 0.75, 0.75, 0.85, 0.85, 0.85, 0.85, 0.85]
            with open(paths["decisions"], "w", encoding="utf-8") as fh:
                for k, pr in enumerate(probs):
                    idx = 300 + k * 48
                    event = START + timedelta(minutes=5 * idx)
                    fh.write(json.dumps({
                        "event_time": event.isoformat(),
                        "levels": [{"center": 80000.0, "role": "soporte",
                                    "hold_prob": pr, "quality": 8.0}],
                    }) + "\n")
            _write_json(paths["backtest"], {
                "ok": True, "samples": 189, "decisions": 127,
                "step_bars": 48, "horizon_bars": 48,
                "brier": 0.13, "brier_skill": 0.0019, "mean_prob": 0.77,
                "start": "2026-10-01T00:00:00+00:00",
                "bins": [
                    {"bin": "0.60-0.70", "n": 34, "pred": 0.656, "real": 0.706},
                    {"bin": "0.70-0.80", "n": 63, "pred": 0.753, "real": 0.841},
                    {"bin": "0.80-1.01", "n": 92, "pred": 0.846, "real": 0.888},
                ],
            })
            out = v.validate(
                paths["eval"], paths["backtest"], paths["decisions"],
                paths["klines"], now=paths["now"],
            )
            self.assertEqual(out["status"], "muestra_chica")
            self.assertTrue(out["oos"]["available"])
            self.assertEqual(out["oos"]["effective"], 189)
            self.assertEqual(out["gate"]["canal"], "oos")
            self.assertTrue(out["gate"]["ok"])

    def test_validate_no_abre_oos_con_skill_negativo(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, spacing=48, eval_samples=8,
                           backtest_samples=189, backtest_skill=-0.02)
            _write_json(paths["backtest"], {
                "ok": True, "samples": 189, "decisions": 127,
                "step_bars": 48, "horizon_bars": 48,
                "brier_skill": -0.02,
                "bins": [{"bin": "0.80-1.01", "n": 189, "pred": 0.8, "real": 0.75}],
            })
            out = v.validate(
                paths["eval"], paths["backtest"], paths["decisions"],
                paths["klines"], now=paths["now"],
            )
            self.assertEqual(out["gate"]["canal"], "ninguno")
            self.assertFalse(out["gate"]["ok"])

    def test_auxiliar_bloqueado_no_rompe_la_validacion(self):
        # Un derivado bloqueado legal/geografico (HTTP 451) no debe volver roto
        # al validador: solo las velas (lo que usa el motor) son criticas.
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, spacing=48, eval_samples=8)
            chp = os.path.join(td, "health.json")
            _write_json(chp, {"ok": False, "kline_ok": True, "run_at": "2026-10-22T05:20:00+00:00",
                              "jobs": {"top_ls_account.jsonl": {"ok": False},
                                       "top_ls_position.jsonl": {"ok": False}}})
            out = v.validate(
                paths["eval"], paths["backtest"], paths["decisions"],
                paths["klines"], now=paths["now"], collector_health_path=chp,
            )
            self.assertNotEqual(out["status"], "roto")
            self.assertTrue(out["data"]["collector"]["available"])
            self.assertEqual(
                sorted(out["data"]["collector"]["failed_jobs"]),
                ["top_ls_account.jsonl", "top_ls_position.jsonl"])

    def test_klines_fallidas_si_rompen_la_validacion(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _setup(td, events=10, spacing=48, eval_samples=8)
            chp = os.path.join(td, "health.json")
            _write_json(chp, {"ok": False, "kline_ok": False,
                              "run_at": "2026-10-22T05:20:00+00:00", "jobs": {}})
            out = v.validate(
                paths["eval"], paths["backtest"], paths["decisions"],
                paths["klines"], now=paths["now"], collector_health_path=chp,
            )
            self.assertEqual(out["status"], "roto")

    def test_deriva_ventana_reciente(self):
        # H6: la deriva se mide sobre una ventana reciente, no sobre todo el
        # historico (decisiones viejas nunca salen del log).
        viejo = datetime(2026, 10, 1, tzinfo=timezone.utc)
        ahora = datetime(2026, 10, 23, tzinfo=timezone.utc)
        decisions = [
            # viejas: muchas prob bajas (distribucion del modelo anterior)
            *[{"event_time": (viejo + timedelta(minutes=5 * i)).isoformat(),
               "levels": [{"hold_prob": 0.65}]} for i in range(50)],
            # recientes: todas altas (modelo nuevo)
            *[{"event_time": (ahora - timedelta(minutes=5 * i)).isoformat(),
               "levels": [{"hold_prob": 0.85}]} for i in range(50)],
        ]
        backtest = {"ok": True, "bins": [{"bin": "0.80-1.01", "n": 100,
                                          "pred": 0.85, "real": 0.87}]}
        con_ventana = v._drift_summary(decisions, backtest, ahora=ahora,
                                       ventana_horas=48)
        sin_ventana = v._drift_summary(decisions, backtest, ahora=ahora,
                                       ventana_horas=100000)
        # recientes == backtest (PSI ~0; el suavizado de psi() deja un residuo)
        self.assertLess(con_ventana["psi"], 0.05)
        self.assertGreater(sin_ventana["psi"], 0.25)  # mezcla vieja+reciente


if __name__ == "__main__":
    unittest.main(verbosity=2)
