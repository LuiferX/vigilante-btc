"""Tests sin red del colector. Ejecutar: python collector/test_collector.py"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collector as c


class CollectorTest(unittest.TestCase):
    def test_append_jsonl_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.jsonl"
            rows = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
            self.assertEqual(c.append_jsonl(path, rows, "id"), 2)
            self.assertEqual(c.append_jsonl(path, rows, "id"), 0)
            self.assertEqual(c.append_jsonl(path, [{"id": 3}], "id"), 1)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual(json.loads(lines[-1])["id"], 3)

    def test_trim_jsonl_keeps_last(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.jsonl"
            path.write_text(
                "".join(json.dumps({"id": i}) + "\n" for i in range(10)),
                encoding="utf-8",
            )
            self.assertEqual(c.trim_jsonl(path, 4), 6)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)
            self.assertEqual(json.loads(lines[0])["id"], 6)
            self.assertEqual(json.loads(lines[-1])["id"], 9)

    def test_vision_mapping(self):
        raw = [[1700000000000, "1", "2", "0.5", "1.5", "10", 1700000299999, "15", 3]]
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_klines_vision("5m", 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "binance_vision_klines_5m")
        self.assertEqual(rows[0]["openTime"], 1700000000000)
        self.assertEqual(rows[0]["close"], "1.5")
        self.assertEqual(rows[0]["trades"], 3)

    def test_kraken_mapping(self):
        raw = {
            "error": [],
            "result": {
                "XXBTZUSD": [[1700000000, "1", "2", "0.5", "1.5", "1.4", "10", 5]],
                "last": 1700000000,
            },
        }
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_klines_kraken("5m", 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "kraken_klines_5m")
        self.assertEqual(rows[0]["openTime"], 1700000000000)
        self.assertEqual(rows[0]["close"], "1.5")

    def test_okx_funding_mapping(self):
        raw = {
            "code": "0",
            "data": [{"fundingTime": "1700000000000", "realizedRate": "0.0001"}],
        }
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_funding_okx(5)
        self.assertEqual(rows[0]["source"], "okx_funding")
        self.assertEqual(rows[0]["fundingTime"], 1700000000000)
        self.assertEqual(rows[0]["fundingRate"], "0.0001")

    def test_okx_oi_mapping(self):
        raw = {"code": "0", "data": [["1700000000000", "1000", "500"]]}
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_open_interest_okx()
        self.assertEqual(rows[0]["source"], "okx_oi")
        self.assertEqual(rows[0]["timestamp"], 1700000000000)
        self.assertEqual(rows[0]["sumOpenInterest"], "1000")

    def test_okx_long_short_mapping(self):
        raw = {"code": "0", "data": [["1700000000000", "1.5"]]}
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_long_short_okx()
        self.assertEqual(rows[0]["source"], "okx_global_ls")
        self.assertEqual(rows[0]["longShortRatio"], "1.500000")
        self.assertAlmostEqual(float(rows[0]["longAccount"]), 0.6, places=5)

    def test_okx_taker_mapping(self):
        raw = {"code": "0", "data": [["1700000000000", "60", "40"]]}
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_taker_okx()
        self.assertEqual(rows[0]["source"], "okx_taker_ls")
        self.assertEqual(rows[0]["buySellRatio"], "1.500000")

    def test_bybit_long_short_mapping(self):
        raw = {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "buyRatio": "0.6088", "sellRatio": "0.3912",
             "timestamp": "1792653600000"},
        ]}}
        with patch.object(c, "http_get_json", return_value=raw):
            rows = c.fetch_long_short_bybit()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "bybit_account_ratio")
        self.assertEqual(rows[0]["timestamp"], 1792653600000)
        self.assertAlmostEqual(float(rows[0]["longAccount"]), 0.6088, places=4)
        self.assertAlmostEqual(float(rows[0]["shortAccount"]), 0.3912, places=4)
        self.assertAlmostEqual(float(rows[0]["longShortRatio"]), 0.6088 / 0.3912, places=4)

    def test_bybit_long_short_sin_filas_falla(self):
        with patch.object(c, "http_get_json", return_value={"retCode": 0, "result": {"list": []}}):
            with self.assertRaises(RuntimeError):
                c.fetch_long_short_bybit()

    def test_with_fallback(self):
        with patch.object(c, "fetch_funding", side_effect=RuntimeError("451")):
            rows = c.with_fallback("funding", c.fetch_funding, lambda: [{"source": "okx"}])
        self.assertEqual(rows[0]["source"], "okx")

    def test_only_closed_drops_current_candle(self):
        now_ms = int(c.datetime.now(c.timezone.utc).timestamp() * 1000)
        rows = [
            {"openTime": now_ms - 600_000, "closeTime": now_ms - 300_001},
            {"openTime": now_ms - 300_000, "closeTime": now_ms + 299_999},
        ]
        closed = c.only_closed(rows)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["openTime"], now_ms - 600_000)


    def test_append_jsonl_indice_incremental(self):
        """P1-2.4: indice incremental; fallback correcto si el fichero
        cambio por fuera."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'datos.jsonl')
            self.assertEqual(c.append_jsonl(p, [{'openTime': 1, 'v': 'a'}], 'openTime'), 1)
            self.assertEqual(c.append_jsonl(p, [{'openTime': 1, 'v': 'a'}], 'openTime'), 0)
            self.assertEqual(c.append_jsonl(p, [{'openTime': 2, 'v': 'b'}], 'openTime'), 1)
            self.assertTrue(os.path.exists(p + '.idx'), 'debe crear el indice')
            self.assertEqual(c.append_jsonl(p, [{'openTime': 1, 'v': 'a'}], 'openTime'), 0)
            self.assertEqual(c.append_jsonl(p, [{'openTime': 3, 'v': 'c'}], 'openTime'), 1)
            with open(p, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps({'openTime': 4, 'v': 'd'}) + '\n')
            self.assertEqual(c.append_jsonl(p, [{'openTime': 4}, {'openTime': 5}], 'openTime'), 1)
            filas = [json.loads(l) for l in open(p, encoding='utf-8')]
            self.assertEqual(sorted(f['openTime'] for f in filas), [1, 2, 3, 4, 5])
            self.assertEqual(len(filas), 5, 'ni duplicados ni perdidos')

if __name__ == '__main__':
    unittest.main(verbosity=2)
