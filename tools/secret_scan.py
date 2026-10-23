#!/usr/bin/env python3
"""
secret_scan.py - GUARDIAN ANTI-SECRETOS del repo (regla de oro).

Regla de oro del proyecto: NUNCA un token, API key, chat id o secreto
dentro del repositorio. Este eslabon corre:
  - a mano:   python tools/secret_scan.py
  - en CI:    dentro de test.yml (falla el push si detecta algo)

Estrategia: lista blanca de textos permitidos (placeholders documentados)
y patrones de secreto reales. Solo escanea archivos versionables (texto),
ignora binarios, .git y datos grandes.
Exit 1 si encuentra algo. No modifica archivos.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- textos permitidos (no son secretos) -------------------------------------
ALLOW_SUBSTR = [
    "${",  # placeholders tipo ${TELEGRAM_BOT_TOKEN}
    "TELEGRAM_BOT_TOKEN",  # nombre de la variable, no el valor
    "TELEGRAM_CHAT_ID",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "GH_TOKEN",
    "secrets.",
    "${{ secrets.",
    "xxxxxxxx",
    "TU_TOKEN",
    "tu_token",
    "123456789:AA",  # ejemplo documentado en la guia
    "<TU_TOKEN>",
    "nombre de usuario",
]

# --- patrones de secreto real ------------------------------------------------
PATTERNS = [
    ("token github (PAT)", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("token github (clasico)", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("token telegram", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    (
        "clave binance/exchange",
        re.compile(
            r"(?i)\b(?:binance|bingx|bybit|okx|kraken)[ _-]?api[ _-]?(?:key|secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9]{12,}"
        ),
    ),
    (
        "asignacion de secreto",
        re.compile(
            r"(?i)\b(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-./+]{16,}['\"]"
        ),
    ),
    (
        "bearer literal",
        re.compile(r"Authorization\s*[:=]\s*['\"]?Bearer\s+[A-Za-z0-9_\-.]{16,}"),
    ),
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    ".venv-nn",
    "node_modules",
    ".pytest_cache",
}
SKIP_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp4",
    ".mp3",
    ".pdf",
    ".zip",
    ".gz",
    ".pyc",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
}
MAX_BYTES = 3 * 1024 * 1024


def allow(line):
    return any(s in line for s in ALLOW_SUBSTR)


def main():
    hallazgos = []
    revisados = 0
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, HERE).replace("\\", "/")
            if os.path.splitext(f)[1].lower() in SKIP_EXT:
                continue
            try:
                if os.path.getsize(full) > MAX_BYTES:
                    continue
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    lineas = fh.read().splitlines()
            except OSError:
                continue
            revisados += 1
            for n, line in enumerate(lineas, 1):
                if allow(line):
                    continue
                for nombre, rx in PATTERNS:
                    m = rx.search(line)
                    if m:
                        hallazgos.append(f"{rel}:{n}: [{nombre}] {m.group(0)[:40]}...")
    print(f"secret_scan: {revisados} archivos revisados")
    if hallazgos:
        print("SECRETO DETECTADO (regla de oro violada):")
        for h in hallazgos[:20]:
            print("  " + h)
        return 1
    print("secret_scan: OK, ningun secreto encontrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
