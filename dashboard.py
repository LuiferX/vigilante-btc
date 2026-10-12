#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dashboard.py v3 - genera docs/index.html (GitHub Pages).
Bonito + animado + robusto: ningun campo rompe el render."""
import datetime
import json
import os

VERSION = "v3-bonito"

_uid = [0]


def _num(x, default=0):
    try:
        v = float(x)
        if v != v:  # NaN
            return default
        return v
    except Exception:
        return default


def _txt(x, default="?"):
    if isinstance(x, str) and x.strip():
        return x
    return default


def miles(x):
    try:
        return f"{float(x):,.0f}".replace(",", ".")
    except Exception:
        return "?"


def _bias_class(bias):
    b = (bias or "").upper()
    if b == "ALZA":
        return "alza"
    if b == "BAJA":
        return "baja"
    return "lateral"


def svg_linea(vals, w=560, h=160, color="#38bdf8", marcas=None):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if len(vals) < 2:
        return "<p>sin datos aún</p>"
    _uid[0] += 1
    gid = f"g{_uid[0]}"
    lo, hi = min(vals), max(vals)
    rg = (hi - lo) or 1
    n = len(vals)
    xs = [10 + i * (w - 20) / (n - 1) for i in range(n)]
    ys = [h - 14 - (v - lo) / rg * (h - 34) for v in vals]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"M{xs[0]:.1f},{h - 14} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in zip(xs, ys)) + f" L{xs[-1]:.1f},{h - 14} Z"
    dots = []
    for i in (marcas or []):
        if 0 <= i < n:
            dots.append(
                f'<circle class="alert" cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="4.5">'
                f"<title>alerta · pasada {i} · {vals[i]:,.0f}</title></circle>")
    dots.append(
        f'<circle class="last" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4.5">'
        f"<title>cierre · {vals[-1]:,.0f}</title></circle>")
    return (
        f'<svg class="resp draw" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f"<defs><linearGradient id=\"{gid}\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
        f"<stop offset=\"0\" stop-color=\"{color}\" stop-opacity=\".35\"/>"
        f"<stop offset=\"1\" stop-color=\"{color}\" stop-opacity=\"0\"/></linearGradient></defs>"
        f"<path d=\"{area}\" fill=\"url(#{gid})\"/>"
        f"<polyline class=\"linea\" points=\"{pts}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2.5\" stroke-linejoin=\"round\"/>"
        + "".join(dots) +
        f"<text x=\"12\" y=\"18\" class=\"tag\">máx {hi:,.0f}</text>"
        f"<text x=\"12\" y=\"{h - 4}\" class=\"tag\">mín {lo:,.0f}</text></svg>")


def svg_barras(vals, etiquetas, w=560, h=170):
    pares = [(v, e) for v, e in zip(vals, etiquetas) if isinstance(v, (int, float))]
    if not pares:
        return "<p>sin datos aún</p>"
    n = len(pares)
    top, bot = 16, h - 24
    bw = (w - 20) / n
    y_of = lambda v: bot - max(0, min(100, v)) / 100 * (bot - top)
    y45, y55 = y_of(45), y_of(55)
    s = [f'<svg class="resp bars" viewBox="0 0 {w} {h}">']
    s.append(f'<line x1="10" y1="{y45:.1f}" x2="{w - 10}" y2="{y45:.1f}" class="umbral"/>')
    s.append(f'<text x="{w - 8}" y="{y45 - 4:.1f}" text-anchor="end" class="tag">45 registra</text>')
    s.append(f'<line x1="10" y1="{y55:.1f}" x2="{w - 10}" y2="{y55:.1f}" class="umbral fuerte"/>')
    s.append(f'<text x="{w - 8}" y="{y55 - 4:.1f}" text-anchor="end" class="tag">55 fuerte</text>')
    for i, (v, e) in enumerate(pares):
        vc = max(0, min(100, v))
        y = y_of(vc)
        x = 10 + i * bw + 1.5
        cls = "b-green" if vc >= 55 else ("b-amber" if vc >= 40 else "b-slate")
        s.append(
            f'<rect class="bar {cls}" x="{x:.1f}" y="{y:.1f}" width="{bw - 3:.1f}" '
            f'height="{bot - y:.1f}" rx="3" style="animation-delay:{min(i * 25, 700)}ms">'
            f"<title>pasada {e} · confianza {v:g}</title></rect>")
        if n <= 12 or i % 5 == 0 or i == n - 1:
            s.append(f'<text x="{x + 2:.1f}" y="{h - 8}" class="tag">{e}</text>')
        if vc >= 55:
            s.append(f'<text x="{x + (bw - 3) / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="tag hi">{v:g}</text>')
    s.append("</svg>")
    return "".join(s)


CSS = """
:root{--bg:#020617;--card:rgba(30,41,59,.82);--line:rgba(148,163,184,.16);
--txt:#e2e8f0;--mut:#94a3b8;--acc:#38bdf8;--grn:#22c55e;--amb:#f59e0b;--red:#ef4444}
*{box-sizing:border-box}
body{background:radial-gradient(1200px 500px at 20% -10%,#0c4a6e55,transparent),
radial-gradient(1000px 500px at 90% 0%,#4c1d9555,transparent),var(--bg);
color:var(--txt);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0;padding:16px}
.wrap{max-width:1120px;margin:0 auto}
header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
header h1{font-size:21px;margin:0}
.live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);
border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--grn);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;
box-shadow:0 10px 30px #0006;backdrop-filter:blur(6px);animation:up .55s both}
.card:nth-child(2){animation-delay:.06s}.card:nth-child(3){animation-delay:.12s}
.card:nth-child(4){animation-delay:.18s}.card:nth-child(5){animation-delay:.24s}
.card:nth-child(6){animation-delay:.3s}.card:nth-child(7){animation-delay:.36s}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
h2{font-size:13px;letter-spacing:.4px;text-transform:uppercase;color:#93c5fd;margin:0 0 10px}
p{color:var(--mut);font-size:13px;margin:6px 0}
.big{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums}
.badge{display:inline-block;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;
vertical-align:middle;margin-left:6px}
.badge.alza{background:#052e16;color:#4ade80;border:1px solid #22c55e55}
.badge.baja{background:#450a0a;color:#fca5a5;border:1px solid #ef444455}
.badge.lateral{background:#1e293b;color:#cbd5e1;border:1px solid var(--line)}
.pill{height:8px;border-radius:99px;background:#0f172a;overflow:hidden;margin-top:8px}
.pill i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--amb),var(--grn));
width:0;animation:fill 1.1s .2s forwards}
@keyframes fill{to{width:var(--w,30%)}}
.sub{font-size:12px;color:var(--mut);margin-top:6px}
svg.resp{width:100%;height:auto;display:block;background:#0f172a;border-radius:10px}
svg .tag{fill:#94a3b8;font-size:11px}
svg .umbral{stroke:#f59e0b;stroke-dasharray:5 4;stroke-width:1;opacity:.7}
svg .umbral.fuerte{stroke:#22c55e}
svg .bar{transform-origin:bottom;transform-box:fill-box;animation:grow .5s both}
@keyframes grow{from{transform:scaleY(.1)}to{transform:scaleY(1)}}
.b-green{fill:#22c55e}.b-amber{fill:#f59e0b}.b-slate{fill:#475569}
svg .linea{stroke-dasharray:1400;stroke-dashoffset:1400;animation:draw 1.4s .1s forwards}
@keyframes draw{to{stroke-dashoffset:0}}
svg circle.alert{fill:var(--red);animation:blink 1.6s infinite}
svg circle.last{fill:var(--grn);filter:drop-shadow(0 0 4px #22c55e)}
.kv{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:#cbd5e1;background:#0f172a}
.chip b{color:#fff}
footer{color:#64748b;font-size:12px;margin:14px 2px}
@media(max-width:480px){.big{font-size:24px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def _contexto_html(snap):
    if not isinstance(snap, dict):
        return ""
    reg = _txt(snap.get("regimen"), "?")
    grade = _txt(snap.get("grade"), "?")
    tf = snap.get("tf") or {}
    chips = []
    for k, lbl in (("h1", "1H"), ("h4", "4H"), ("d1", "1D"), ("w1", "1S")):
        d = tf.get(k) or {}
        t = _txt(d.get("tend"), "?")
        r = d.get("rsi", "?")
        chips.append(f"<span class='chip'><b>{lbl}</b> {t} · RSI {r}</span>")
    fg = snap.get("fg") or {}
    senti = snap.get("senti") or {}
    chips.append(f"<span class='chip'>😨🤑 <b>{fg.get('valor', '?')}</b> {fg.get('etiqueta', '')}</span>")
    chips.append(f"<span class='chip'>funding <b>{senti.get('funding', '?')}</b></span>")
    pres = snap.get("pres") or {}
    if pres.get("txt"):
        chips.append(f"<span class='chip'>📰 {pres.get('txt')}</span>")
    niv = snap.get("niv") or {}
    try:
        sop = (niv.get("sop") or [{}])[0].get("precio", "?")
        res = (niv.get("res") or [{}])[0].get("precio", "?")
        chips.append(f"<span class='chip'>🛡 <b>{sop}</b> · 🧲 <b>{res}</b></span>")
    except Exception:
        pass
    evs = snap.get("evs") or []
    if evs:
        e0 = evs[0]
        chips.append(f"<span class='chip'>📅 {e0.get('titulo', '?')}</span>")
    return (f"<div class='card'><h2>Contexto</h2>"
            f"<p>Régimen <b style='color:#e2e8f0'>{reg}</b> · grado <b style='color:#e2e8f0'>{grade}</b></p>"
            f"<div class='kv'>{''.join(chips)}</div></div>")


def build_dashboard(est, hist):
    if not isinstance(est, dict):
        est = {}
    if not isinstance(hist, list):
        hist = []
    ahora = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m %H:%M UTC")
    ult = [h for h in hist[-30:] if isinstance(h, dict)]
    px = [_num(h.get("precio")) for h in ult]
    cf = [h.get("conf", 0) for h in ult]
    marcas = [i for i, h in enumerate(ult) if h.get("tipo") == "alerta"]
    alza = est.get("alza") or []
    baja = est.get("baja") or []
    pa = f"{round(sum(alza) / len(alza) * 100)}% ({sum(alza)}/{len(alza)})" if len(alza) >= 5 else "s/d"
    pb = f"{round(sum(baja) / len(baja) * 100)}% ({sum(baja)}/{len(baja)})" if len(baja) >= 5 else "s/d"
    banco = est.get("banco")
    eq = [10000.0]
    for c in est.get("paper_cerradas", []) or []:
        try:
            eq.append(eq[-1] + float((c or {}).get("pnl", 0)))
        except Exception:
            continue
    eq_txt = f"{miles(banco)} USDT" if banco is not None else "10.000 USDT (sin empezar)"
    bias = _txt(est.get("ultimo_bias"))
    _conf = est.get("ultima_conf")
    conf = _conf if isinstance(_conf, (int, float)) else "?"
    conf_w = max(0, min(100, _conf)) if isinstance(_conf, (int, float)) else 0
    precio = (ult[-1].get("precio", 0) if ult else 0) or 0
    if len(px) >= 2 and px[0]:
        d = px[-1] - px[0]
        dpct = d / px[0] * 100
        delta_txt = f"{'+' if d >= 0 else ''}{miles(d)} ({'+' if dpct >= 0 else ''}{dpct:.2f}%) en ventana"
        rango_txt = f"rango {miles(min(px))} – {miles(max(px))}"
    else:
        delta_txt, rango_txt = "sin ventana aún", ""
    n_alertas = len(marcas)
    ctx = _contexto_html(est.get("snapshot"))
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="300">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vigilante BTC</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>🤖 Vigilante BTC</h1>
<span class="live"><span class="dot"></span>actualizado {ahora} · se refresca solo</span></header>
<div class="grid">
<div class="card"><h2>Precio y sesgo</h2>
<div class="big">{miles(precio)}<span class="badge {_bias_class(bias)}">{bias} {conf}%</span></div>
<div class="pill"><i style="--w:{conf_w}%"></i></div>
<div class="sub">{delta_txt} · {rango_txt} · 🔴 {n_alertas} alertas en ventana</div></div>
<div class="card"><h2>Precio (últimas {len(px)}) + alertas 🔴</h2>{svg_linea(px, marcas=marcas)}</div>
<div class="card"><h2>Confianza (escala 0–100)</h2>{svg_barras(cf, [str(i) for i in range(len(cf))])}
<p>Verde ≥55 (fuerte) · ámbar ≥40 · gris debajo. Líneas: 45 registra / 55 fuerte.</p></div>
{ctx}
<div class="card"><h2>Banco papel</h2><div class="big" style="font-size:22px">{eq_txt}</div>{svg_linea(eq, color="#22c55e")}</div>
<div class="card"><h2>Precisión</h2><p>ALZA {pa} · BAJA {pb}</p>
<p>Se evalúa a 8h: objetivo 2R antes que stop 1R.</p></div>
<div class="card"><h2>Actividad</h2><p>{len(hist)} pasadas guardadas · run {est.get("runs", "?")}</p>
<p>Sesión NY 13–20 UTC · avisos sólo con cambio real.</p></div>
</div><footer>Análisis probabilístico. No es asesoramiento financiero. v3.</footer>
</div>
<script>setTimeout(function(){{location.reload()}},300000);</script>
</body></html>"""


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
