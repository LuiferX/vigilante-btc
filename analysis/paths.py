"""Rutas por defecto para correr local o desde el repo unificado."""

from __future__ import annotations

import os


def default_klines_path() -> str:
    candidates = [
        os.environ.get("BTC_KLINES"),
        "../collector/data/btcusdt/klines_5m.jsonl",
        "../trading-data-collector/data/btcusdt/klines_5m.jsonl",
        "collector/data/btcusdt/klines_5m.jsonl",
        "data/btcusdt/klines_5m.jsonl",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return "../collector/data/btcusdt/klines_5m.jsonl"


def default_decisions_path() -> str:
    return os.environ.get("BTC_DECISIONS", "data/decisions.jsonl")
