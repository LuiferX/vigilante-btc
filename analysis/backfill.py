#!/usr/bin/env python3
"""
backfill.py - REPLAY HISTORICO sin mirada al futuro (canal OOS auditable).

Recorre velas 5m con paso `step` (por defecto 48 = 4h, igual al horizonte, para
que las ventanas de etiquetado NO se solapen) y, en cada corte, construye el
contexto SOLO con velas <= corte (igual que analysis/backtest.py), pero ademas:

  - escribe decisiones compactas (mismo schema que decisions.jsonl) en
    data/decisions_hist.jsonl  -> evaluate_decisions/validation pueden consumirlo
    como canal OOS separado (nunca se mezcla con el flujo vivo).
  - opcionalmente evalua el registro y escribe data/oos_eval.json.

Con `--descargar` baja el el historial 5m/1h/4h/1d que le falte (Binance Vision,
publico, sin clave) a un cache local, para poder refrescar el OOS sin romper la
retencion del colector. El cache NO se versiona.

No opera, no usa claves, no toca el log vivo. Uso:

  python backfill.py --klines ... --start 2026-10-01T00:00:00+00:00 \
      --out data/decisions_hist.jsonl [--evaluar] [--descargar]
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_engine as de  # noqa: E402
import evaluate_decisions as ev  # noqa: E402
import hold_model as hm  # noqa: E402
import run_decision as rd  # noqa: E402

UTC = datetime.UTC
VISION = "https://data-api.binance.vision/api/v3/klines"
_AQUI = os.path.dirname(os.path.abspath(__file__))
# Cache independiente del CWD: analysis/data/cache (no versionado).
CACHE_DEFAULT = os.path.join(_AQUI, "data", "cache")


def descargar_intervalo(interval, path, desde):
    """Baja (o completa) un JSONL de velas desde `desde` hasta ahora."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    vistas = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    vistas.add(int(json.loads(line)["openTime"]))
                except Exception:
                    continue
    ahora_ms = int(datetime.datetime.now(UTC).timestamp() * 1000)
    cur = int(desde.timestamp() * 1000)
    nuevas = 0
    with open(path, "a", encoding="utf-8") as fh:
        while cur < ahora_ms:
            url = f"{VISION}?symbol=BTCUSDT&interval={interval}" f"&startTime={cur}&limit=1000"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "vigilante-backfill/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
            except Exception:
                break
            if not data:
                break
            for k in data:
                if int(k[0]) in vistas:
                    continue
                vistas.add(int(k[0]))
                fh.write(
                    json.dumps(
                        {
                            "source": f"binance_vision_klines_{interval}",
                            "interval": interval,
                            "openTime": int(k[0]),
                            "open": k[1],
                            "high": k[2],
                            "low": k[3],
                            "close": k[4],
                            "volume": k[5],
                            "closeTime": int(k[6]),
                            "quoteVolume": k[7],
                            "trades": k[8],
                            "collected_at": datetime.datetime.now(UTC).isoformat(),
                        }
                    )
                    + "\n"
                )
                nuevas += 1
            cur = int(data[-1][0]) + 1
            if len(data) < 1000:
                break
            time.sleep(0.15)
    return nuevas


def asegurar_datos(cache_dir, desde):
    """Garantiza velas 5m/1h/4h/1d en cache desde `desde`. Devuelve rutas."""
    os.makedirs(cache_dir, exist_ok=True)
    rutas = {}
    planes = {
        "5m": desde,
        "1h": desde - datetime.timedelta(days=3),
        "4h": desde - datetime.timedelta(days=10),
        "1d": desde - datetime.timedelta(days=400),
    }
    for iv, ini in planes.items():
        p = os.path.join(cache_dir, f"klines_{iv}.jsonl")
        n = descargar_intervalo(iv, p, ini)
        print(f"backfill: {iv} +{n} velas nuevas en {p}")
        rutas[iv] = p
    return rutas


def cargar_klines(path):
    kl = hm.load_klines_jsonl(path)
    kl.sort(key=lambda v: v["t"])
    return kl


def _slice_htf(htf, cutoff):
    if not htf:
        return None
    out = {}
    for k, bars in htf.items():
        out[k] = [b for b in bars if b["t"] <= cutoff]
    return out


def replay(kl, htf, start=None, end=None, step=48, warmup=300):
    """Genera (registro_compacto, muestra) por corte, sin lookahead."""
    if not kl or len(kl) < warmup + step:
        return [], None
    ini = datetime.datetime.fromisoformat(start) if start else None
    fin = datetime.datetime.fromisoformat(end) if end else None
    if ini and ini.tzinfo is None:
        ini = ini.replace(tzinfo=datetime.UTC)
    if fin and fin.tzinfo is None:
        fin = fin.replace(tzinfo=datetime.UTC)
    registros = []
    for i in range(warmup, len(kl) - step, step):
        cutoff = kl[i]["t"]
        if ini and cutoff < ini:
            continue
        if fin and cutoff > fin:
            break
        out = de.decide(
            kl[: i + 1],
            price=kl[i]["c"],
            now=cutoff,
            htf_klines=_slice_htf(htf, cutoff),
        )
        if not out.get("ok"):
            continue
        rec = rd.compact_record(out)
        rec["origen"] = "backfill"
        registros.append(rec)
    return registros, None


def escribir_jsonl(path, registros):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    vistos = set()
    if os.path.exists(path) and not os.environ.get("BACKFILL_SOBREESCRIBIR"):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    vistos.add(json.loads(line).get("event_time"))
                except Exception:
                    continue
    nuevos = 0
    with open(path, "a", encoding="utf-8") as fh:
        for r in registros:
            if r.get("event_time") in vistos:
                continue
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            vistos.add(r.get("event_time"))
            nuevos += 1
    return nuevos


def main():
    ap = argparse.ArgumentParser(description="Replay historico OOS (canal auditable)")
    ap.add_argument("--klines", default="", help="klines_5m.jsonl (o vacio si se usa --descargar)")
    ap.add_argument(
        "--datadir",
        default=None,
        help="dir con klines_1h/4h/1d.jsonl (por defecto, el de --klines)",
    )
    ap.add_argument("--out", default=os.path.join("data", "decisions_hist.jsonl"))
    ap.add_argument("--eval-out", default=None, help="si se pasa, evalua el registro y escribe ahi")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--step", type=int, default=48)
    ap.add_argument("--horizon", type=int, default=48)
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--sobreescribir", action="store_true")
    ap.add_argument(
        "--descargar",
        action="store_true",
        help="baja/completa el historico publico en --cache antes de replicar",
    )
    ap.add_argument(
        "--cache",
        default=CACHE_DEFAULT,
        help="dir de cache de velas (no versionado; por defecto analysis/data/cache)",
    )
    ap.add_argument(
        "--vigilante",
        default=None,
        help="estado.json local o URL (niveles del Vigilante)",
    )
    args = ap.parse_args()

    if args.sobreescribir and os.path.exists(args.out):
        os.remove(args.out)

    if args.descargar:
        desde = hm.MODEL.get("trained_until")
        try:
            desde_dt = datetime.datetime.fromisoformat(str(desde).replace("Z", "+00:00"))
            if desde_dt.tzinfo is None:
                desde_dt = desde_dt.replace(tzinfo=UTC)
        except Exception:
            desde_dt = datetime.datetime(2026, 10, 1, tzinfo=UTC)
        rutas = asegurar_datos(args.cache, desde_dt)
        args.klines = rutas["5m"]
        args.datadir = args.cache
    if not args.klines:
        print("backfill: falta --klines (o usa --descargar)")
        return
    kl = cargar_klines(args.klines)
    datadir = args.datadir or os.path.dirname(os.path.abspath(args.klines))
    htf = de.load_htf_klines(datadir)
    registros, _ = replay(kl, htf, args.start, args.end, args.step, args.warmup)
    nuevos = escribir_jsonl(args.out, registros)
    print(f"backfill: {len(registros)} cortes, {nuevos} registros nuevos en {args.out}")
    if args.eval_out:
        res = ev.evaluate(args.out, args.klines, horizon=args.horizon)
        os.makedirs(os.path.dirname(args.eval_out) or ".", exist_ok=True)
        with open(args.eval_out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        m = res.get("overall", {})
        print(
            f"eval OOS: n={m.get('n')} brier={m.get('brier')} skill={m.get('brier_skill')} "
            f"base={m.get('base_rate')} status={res.get('status')}"
        )


if __name__ == "__main__":
    main()
