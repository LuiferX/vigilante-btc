#!/usr/bin/env python3
"""test_etiquetas.py - las etiquetas de "aguante" son honestas y coinciden.

Doble veredicta:
  1. Semantica: un soporte que nadie traspasa 0.5% etiqueta 1; si algun cierre
     lo traspasa, etiqueta 0 (y idem resistencia, espejado). Etiquetas
     esperadas CALCULADAS A MANO sobre velas sinteticas.
  2. Diferencial: los agregados de evaluate_decisions (brier/skill/base/ECE)
     coinciden con una reimplementacion INDEPENDIENTE sobre los mismos eventos.
     Si alguna etiqueta mudara entre componentes, el brier no cerraria.

Hermetico: no descarga nada, no toca el cache ni la red.
"""
import bisect
import datetime
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import evaluate_decisions as ev  # noqa: E402
import hold_model as hm  # noqa: E402

UTC = datetime.UTC
BASE_MS = 1735689600000  # 2025-01-01T00:00Z, multiple de 5 min
PASO_MS = 5 * 60 * 1000


def _klines(tmp, cierres):
    """Escribe klines_5m.jsonl (formato colector) y devuelve la ruta."""
    p = os.path.join(tmp, "klines_5m.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for i, c in enumerate(cierres):
            fh.write(json.dumps({
                "source": "test", "interval": "5m",
                "openTime": BASE_MS + i * PASO_MS,
                "open": str(c), "high": str(max(c, c)), "low": str(min(c, c)),
                "close": str(c), "volume": "1",
                "closeTime": BASE_MS + (i + 1) * PASO_MS - 1,
            }) + "\n")
    return p


def _evento(i_barra, nivel, rol, prob):
    t = datetime.datetime.fromtimestamp(
        (BASE_MS + i_barra * PASO_MS) / 1000.0, tz=UTC).isoformat()
    return {"event_time": t,
            "levels": [{"center": nivel, "role": rol, "hold_prob": prob}]}


class TestEtiquetas(unittest.TestCase):
    def test_semantica_y_diferencial(self):
        # 4 episodios de 50 velas = 200 velas 5m (8h20m).
        # A: soporte 100 plano            -> aguanta (1), prob 0.9
        # B: soporte 100, barra 125 @99.2 -> rompe   (0), prob 0.8
        # C: resistencia 100, barra 175 @100.6 -> rompe (0), prob 0.7
        # D: resistencia 100 plana        -> aguanta (1), prob 0.85
        cierres = [100.0] * 200
        cierres[75] = 99.2    # dentro del futuro de B (evento en barra 50)
        cierres[125] = 100.6  # dentro del futuro de C (evento en barra 100)
        eventos = [
            _evento(1, 100.0, "soporte", 0.9),
            _evento(50, 100.0, "soporte", 0.8),
            _evento(100, 100.0, "resistencia", 0.7),
            _evento(150, 100.0, "resistencia", 0.85),
        ]
        with tempfile.TemporaryDirectory() as td:
            kl = _klines(td, cierres)
            dec = os.path.join(td, "decisions.jsonl")
            with open(dec, "w", encoding="utf-8") as fh:
                for e in eventos:
                    fh.write(json.dumps(e) + "\n")

            r = ev.evaluate(dec, kl, horizon=48)

            # --- semantica: agregados a mano sobre etiquetas [1,0,0,1] ---
            probs = [0.9, 0.8, 0.7, 0.85]
            ys = [1, 0, 0, 1]
            n = 4
            brier = sum((p - y) ** 2 for p, y in zip(probs, ys, strict=True)) / n
            base = sum(ys) / n
            skill = 1 - brier / (base * (1 - base))
            ece = (abs(0.9 + 0.8 + 0.85 - 2) + abs(0.7 - 0)) / n
            self.assertEqual(r["samples"], 4)
            # evaluate redondea a 4 decimales (documentado en su salida)
            self.assertAlmostEqual(r["brier"], round(brier, 4), places=9)
            self.assertAlmostEqual(r["base_rate"], round(base, 4), places=9)
            self.assertAlmostEqual(r["brier_skill"], round(skill, 4), places=9)
            self.assertAlmostEqual(r["calibration_error"], round(ece, 4), places=9)

            # --- diferencial: mi reimplementacion independiente ---
            kl_barras = hm.load_klines_jsonl(kl)
            kl_barras.sort(key=lambda v: v["t"])
            tiempos = [v["t"] for v in kl_barras]
            mias = []
            vistos = set()
            for linea in open(dec, encoding="utf-8"):
                rec = json.loads(linea)
                et = str(rec["event_time"])
                if et in vistos:
                    continue
                vistos.add(et)
                ev_dt = datetime.datetime.fromisoformat(et.replace("Z", "+00:00"))
                idx = bisect.bisect_right(tiempos, ev_dt) - 1
                fut = kl_barras[idx + 1:idx + 1 + 48]
                self.assertGreaterEqual(len(fut), 48)
                for lv in rec["levels"]:
                    nivel = float(lv["center"])
                    if lv["role"] == "soporte":
                        y = 1 if all(v["c"] >= nivel * 0.995 for v in fut) else 0
                    else:
                        y = 1 if all(v["c"] <= nivel * 1.005 for v in fut) else 0
                    mias.append((float(lv["hold_prob"]), y))
            self.assertEqual([y for _, y in mias], [1, 0, 0, 1])
            mi_brier = sum((p - y) ** 2 for p, y in mias) / len(mias)
            self.assertAlmostEqual(round(mi_brier, 4), r["brier"], places=9)
            # si alguna etiqueta difiriera, los brier no cerrarian


if __name__ == "__main__":
    unittest.main(verbosity=2)
