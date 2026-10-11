#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard.py - genera docs/index.html (GitHub Pages) con el estado del bot.

Lee estado.json + historial.jsonl (ya en disco tras la pasada) y dibuja
SVG a mano (sin dependencias): precio+alertas, confianza, precision y
banco papel. Nunca revienta: ante cualquier error deja pagina de aviso.
"""
import datetime
import json
import os


def svg_linea(vals, w=560, h=150, color="#1f77b4", marcas=None):
    if len(vals) < 2:
        return "<p>sin datos aún</p>"
    lo, hi = min(vals), max(vals)
    rg = (hi - lo) or 1
    pts = " ".join(f"{10 + i * (w - 20) / (len(vals) - 1):.1f},{h - 10 - (v - lo) / rg * (h - 20):.1f}"
                   for i, v in enumerate(vals))
    s = [f'<svg width="{w}" height="{h}" style="background:#0f172a;border-radius:8px">',
         f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>']
    for i in (marcas or []):
        if 0 <= i < len(vals):
            x = 10 + i * (w - 20) / (len(vals) - 1)
            y = h - 10 - (vals[i] - lo) / rg * (h - 20)
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ef4444"/>')
    s.append(f'<text x="12" y="18" fill="#94a3b8" font-size="12">{hi:,.0f}</text>')
    s.append(f'<text x="12" y="{h - 4}" fill="#94a3b8" font-size="12">{lo:,.0f}</text>')
    s.append("</svg>")
    return "".join(s)


def svg_barras(vals, etiquetas, w=560, h=150):
    if not vals:
        return "<p>sin datos aún</p>"
    mx = max(vals) or 1
    n = len(vals)
    bw = (w - 20) / n
    s = [f'<svg width="{w}" height="{h}" style="background:#0f172a;border-radius:8px">']
    for i, (v, e) in enumerate(zip(vals, etiquetas)):
        bh = (v / mx) * (h - 40)
        x = 10 + i * bw + 2
        col = "#22c55e" if v >= 50 else "#f59e0b"
        s.append(f'<rect x="{x:.1f}" y="{h - 20 - bh:.1f}" width="{bw - 4:.1f}" height="{bh:.1f}" fill="{col}" rx="3"/>')
        s.append(f'<text x="{x + 2:.1f}" y="{h - 6}" fill="#94a3b8" font-size="10">{e}</text>')
    s.append("</svg>")
    return "".join(s)


def miles(x):
    try:
        return f"{x:,.0f}".replace(",", ".")
    except Exception:
        return "?"


def build_dashboard(est, hist):
    ahora = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m %H:%M UTC")
    ult = hist[-30:] if len(hist) > 30 else hist
    px = [h.get("precio", 0) for h in ult]
    cf = [h.get("conf", 0) for h in ult]
    marcas = [i for i, h in enumerate(ult) if h.get("tipo") == "alerta"]
    alza = est.get("alza", []) or []
    baja = est.get("baja", []) or []
    pa = f"{round(sum(alza) / len(alza) * 100)}% ({sum(alza)}/{len(alza)})" if len(alza) >= 5 else "s/d"
    pb = f"{round(sum(baja) / len(baja) * 100)}% ({sum(baja)}/{len(baja)})" if len(baja) >= 5 else "s/d"
    banco = est.get("banco")
    eq = [10000.0]
    for c in est.get("paper_cerradas", [])[-100:]:
        try:
            eq.append(eq[-1] + float(c.get("pnl", 0)))
        except Exception:
            continue
    if banco is not None:
        eq_txt = f"{miles(banco)} USDT"
    else:
        eq_txt = "10.000 USDT (sin empezar)"
    bias = est.get("ultimo_bias", "?")
    conf = est.get("ultimo_conf", "?")
    precio = ult[-1] if ult else 0
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="300">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vigilante BTC</title>
<style>body{{background:#020617;color:#e2e8f0;font-family:system-ui;margin:0;padding:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}
.card{{background:#1e293b;border-radius:12px;padding:14px}}
h1{{font-size:20px}}h2{{font-size:15px;color:#93c5fd;margin:0 0 8px}}p{{color:#94a3b8;font-size:13px}}
.big{{font-size:26px;font-weight:bold}}</style></head><body>
<h1>🤖 Vigilante BTC <small style="color:#64748b">actualizado {ahora}</small></h1>
<div class="grid">
<div class="card"><h2>Precio y sesgo</h2><div class="big">{miles(precio)} · {bias} {conf}%</div></div>
<div class="card"><h2>Precio (últimas {len(px)}) + alertas 🔴</h2>{svg_linea(px, marcas=marcas)}</div>
<div class="card"><h2>Confianza</h2>{svg_barras(cf, [str(i) for i in range(len(cf))])}</div>
<div class="card"><h2>Banco papel</h2><div class="big">{eq_txt}</div>{svg_linea(eq, color="#22c55e")}</div>
<div class="card"><h2>Precisión</h2><p>ALZA {pa} · BAJA {pb}</p></div>
<div class="card"><h2>Actividad</h2><p>{len(hist)} pasadas guardadas · run {est.get("runs", "?")}</p></div>
</div><p>Análisis probabilístico. No es asesoramiento financiero.</p></body></html>"""


def main():
    try:
        with open("estado.json", encoding="utf-8") as fh:
            est = json.load(fh)
    except Exception:
        est = {}
    hist = []
    try:
        with open("historial.jsonl", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    hist.append(json.loads(line))
    except Exception:
        pass
    try:
        html = build_dashboard(est, hist)
    except Exception as e:  # noqa: BLE001
        html = f"<html><body><h1>Vigilante BTC</h1><p>Dashboard en construccion ({e}).</p></body></html>"
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("dashboard OK")


if __name__ == "__main__":
    main()
