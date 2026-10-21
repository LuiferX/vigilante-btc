#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dashboard.py v3 - genera docs/index.html (GitHub Pages).
Bonito + animado + robusto: ningun campo rompe el render."""
import datetime
import html
import json
import os

VERSION = "v3-bonito"

_uid = [0]


def _num(x, default=0):
    try:
        if isinstance(x, bool):
            return default
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):
            return default
        return v
    except Exception:
        return default


def _txt(x, default="?"):
    if isinstance(x, str) and x.strip():
        return x
    return default


def _esc(x):
    try:
        return html.escape(str(x), quote=True)
    except Exception:
        return "?"


def miles(x):
    try:
        if isinstance(x, bool):
            return "?"
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):
            return "?"
        return f"{v:,.0f}".replace(",", ".")
    except Exception:
        return "?"


def _bias_class(bias):
    try:
        b = str(bias or "").upper()
    except Exception:
        return "lateral"
    if b == "ALZA":
        return "alza"
    if b == "BAJA":
        return "baja"
    return "lateral"


def svg_linea(vals, w=560, h=160, color="#38bdf8", marcas=None, niveles=None):
    try:
        if not isinstance(color, str) or len(color) not in (4, 7) or not color.startswith("#"):
            color = "#38bdf8"
        vals = [float(v) for v in (vals or []) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        vals = [v for v in vals if v == v and v not in (float("inf"), float("-inf"))]
    except Exception:
        return "<p>sin datos aún</p>"
    if len(vals) < 2:
        return "<p>sin datos aún</p>"
    _uid[0] += 1
    gid = f"g{_uid[0]}"
    lo, hi = min(vals), max(vals)
    nvs = []
    for nv in (niveles or []):
        try:
            if isinstance((nv or {}).get("precio"), bool):
                continue
            p = float((nv or {}).get("precio"))
            if p != p or p in (float("inf"), float("-inf")):
                continue
            nvs.append((p, _esc((nv or {}).get("etiqueta", "")), str((nv or {}).get("kind", ""))))
        except Exception:
            continue
    if nvs:
        lo = min(lo, min(p for p, _, _ in nvs))
        hi = max(hi, max(p for p, _, _ in nvs))
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
    try:
        dots.append(
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="9" fill="{color}" opacity=".18">'
            f"<title>cierre · {vals[-1]:,.0f}</title></circle>")
    except Exception:
        pass
    dots.append(
        f'<circle class="last" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4.5">'
        f"<title>cierre · {vals[-1]:,.0f}</title></circle>")
    lvls = []
    y_of = lambda p: h - 14 - (p - lo) / rg * (h - 34)
    last = vals[-1]
    deb = [p for p, _, _ in nvs if p < last]
    enc = [p for p, _, _ in nvs if p > last]
    if deb and enc:
        lvls.append(f"<rect x='10' y='{y_of(min(enc)):.1f}' width='{w - 72}' "
                    f"height='{y_of(max(deb)) - y_of(min(enc)):.1f}' class='canal'/>")
    for p, txt, kind in nvs:
        y = y_of(p)
        cls = "nres" if kind == "res" else "nsop"
        lvls.append(
            f"<line x1='10' y1='{y:.1f}' x2='{w - 62}' y2='{y:.1f}' class='lvl {cls}'>"
            f"<title>{txt} · {p:,.0f}</title></line>"
            f"<circle cx='{w - 62}' cy='{y:.1f}' r='2.6' fill='{'#f87171' if cls == 'nres' else '#4ade80'}'/>"
            f"<text x='{w - 60}' y='{y - 5:.1f}' class='lvlTxt'>{p:,.0f}</text>")
    yl = y_of(last)
    lvls.append(f"<line x1='10' y1='{yl:.1f}' x2='{w - 62}' y2='{yl:.1f}' class='lvlpx'>"
                f"<title>precio actual · {last:,.0f}</title></line>"
                f"<text x='{w - 60}' y='{yl - 5:.1f}' class='lvlTxt'>{last:,.0f}</text>")
    try:
        _grid = "".join(
            f"<line x1='10' y1='{h - 14 - k * (h - 34):.1f}' x2='{w - 10}' y2='{h - 14 - k * (h - 34):.1f}' stroke='#ffffff' stroke-opacity='.06' stroke-width='1'/>"
            for k in (0.25, 0.5, 0.75))
    except Exception:
        _grid = ""
    return (
        f'<svg class="resp draw" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f"<defs><linearGradient id=\"{gid}\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
        f"<stop offset=\"0\" stop-color=\"{color}\" stop-opacity=\".35\"/>"
        f"<stop offset=\"1\" stop-color=\"{color}\" stop-opacity=\"0\"/></linearGradient></defs>"
        f"<path d=\"{area}\" fill=\"url(#{gid})\"/>"
        f"<polyline class=\"linea\" points=\"{pts}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2.5\" stroke-linejoin=\"round\"/>"
        + _grid + "".join(lvls) + "".join(dots) +
        f"<text x=\"12\" y=\"18\" class=\"tag\">máx {hi:,.0f}</text>"
        f"<text x=\"12\" y=\"{h - 4}\" class=\"tag\">mín {lo:,.0f}</text></svg>")


def svg_barras(vals, etiquetas, w=560, h=170):
    try:
        pares = []
        for v, e in zip(vals or [], etiquetas or []):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            fv = float(v)
            if fv != fv or fv in (float("inf"), float("-inf")):
                continue
            pares.append((fv, _esc(e)))
    except Exception:
        return "<p>sin datos aún</p>"
    if not pares:
        return "<p>sin datos aún</p>"
    n = len(pares)
    top, bot = 16, h - 24
    bw = (w - 20) / n
    y_of = lambda v: bot - max(0, min(100, v)) / 100 * (bot - top)
    y45, y55 = y_of(45), y_of(55)
    s = [f'<svg class="resp bars" viewBox="0 0 {w} {h}">']
    for g in (0, 25, 50, 75, 100):
        gy = y_of(g)
        s.append(f'<line x1="10" y1="{gy:.1f}" x2="{w - 10}" y2="{gy:.1f}" class="rejilla"/>')
        s.append(f'<text x="{w - 8}" y="{gy - 3:.1f}" text-anchor="end" class="tag">{g}</text>')
    s.append(f'<line x1="10" y1="{y45:.1f}" x2="{w - 10}" y2="{y45:.1f}" class="umbral"/>')
    s.append(f'<text x="{w - 8}" y="{y45 - 4:.1f}" text-anchor="end" class="tag">45 registra</text>')
    s.append(f'<line x1="10" y1="{y55:.1f}" x2="{w - 10}" y2="{y55:.1f}" class="umbral fuerte"/>')
    s.append(f'<text x="{w - 8}" y="{y55 - 4:.1f}" text-anchor="end" class="tag">55 fuerte</text>')
    ceros = sum(1 for v, _ in pares if v == 0)
    for i, (v, e) in enumerate(pares):
        vc = max(0, min(100, v))
        y = y_of(vc)
        if bot - y < 2:
            y = bot - 2
        x = 10 + i * bw + 1.5
        cls = "b-green" if vc >= 55 else ("b-amber" if vc >= 40 else ("b-zero" if vc == 0 else "b-slate"))
        try:
            s.append(
                f'<rect class="bar {cls}" x="{x:.1f}" y="{y:.1f}" width="{bw - 3:.1f}" '
                f'height="{bot - y:.1f}" rx="3" style="animation-delay:{min(i * 25, 700)}ms">'
                f"<title>pasada {e} · confianza {v:g}</title></rect>")
        except Exception:
            continue
        if n <= 12 or i % 5 == 0 or i == n - 1:
            s.append(f'<text x="{x + 2:.1f}" y="{h - 8}" class="tag">{e}</text>')
        if vc >= 55:
            s.append(f'<text x="{x + (bw - 3) / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="tag hi">{v:g}</text>')
    if ceros == n:
        s.append(f'<text x="{w / 2}" y="{top + 12}" text-anchor="middle" class="tag">todo en 0 = empate total de marcos</text>')
    s.append("</svg>")
    return "".join(s)


CSS = """
:root{--bg:#000;--card:rgba(13,15,19,.92);--card2:#0c0c0e;--line:rgba(148,163,184,.16);--line2:rgba(148,163,184,.32);
--txt:#e8eef6;--mut:#94a3b8;--acc:#38bdf8;--grn:#22c55e;--amb:#f59e0b;--red:#ef4444;
--radius:14px;--shadow:0 8px 28px rgba(0,0,0,.55),0 1px 0 rgba(255,255,255,.04) inset}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:#000;
color:var(--txt);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,"Helvetica Neue",Arial,sans-serif;margin:0;padding:20px 16px 32px;
min-height:100vh;line-height:1.55;font-size:15px;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body::before,body::after{content:"";position:fixed;border-radius:50%;filter:blur(90px);
pointer-events:none;z-index:0}
body::before{width:44vw;height:44vw;left:-12vw;top:-14vw;
background:radial-gradient(circle,#0b1e3a 0%,transparent 70%);opacity:.5;animation:deriva 26s ease-in-out infinite alternate}
body::after{width:40vw;height:40vw;right:-10vw;bottom:-12vw;
background:radial-gradient(circle,#1c1033 0%,transparent 70%);opacity:.45;animation:deriva 32s ease-in-out infinite alternate-reverse}
@keyframes deriva{from{transform:translate(0,0) scale(1)}to{transform:translate(6vw,4vh) scale(1.15)}}
body[data-bias="ALZA"]::before{background:radial-gradient(circle,#052e16 0%,transparent 70%)}
body[data-bias="ALZA"]::after{background:radial-gradient(circle,#0a2e1a 0%,transparent 70%)}
body[data-bias="BAJA"]::before{background:radial-gradient(circle,#3d0d0d 0%,transparent 70%)}
body[data-bias="BAJA"]::after{background:radial-gradient(circle,#2b0808 0%,transparent 70%)}
body[data-bias="LATERAL"]::before{background:radial-gradient(circle,#1c1e24 0%,transparent 70%)}
body[data-bias="LATERAL"]::after{background:radial-gradient(circle,#141519 0%,transparent 70%)}
@keyframes temblor{0%,88%,100%{transform:translate(0,0)}90%{transform:translate(-3px,2px)}
92%{transform:translate(3px,-2px)}94%{transform:translate(-2px,-1px)}96%{transform:translate(2px,1px)}}
.wrap.alerta-max{animation:temblor 3.5s infinite}
#fondo{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.9}
#latido{position:fixed;inset:0;z-index:0;pointer-events:none;background:transparent}
#destello{position:fixed;inset:0;z-index:4;pointer-events:none;opacity:0}
#motor{font-size:11px;color:#64748b}
.saludo{font-size:12px;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.flash{border-color:#ef444488!important;animation:flashB 1.8s ease-in-out infinite}
@keyframes flashB{0%,100%{box-shadow:0 10px 30px #0006,0 0 8px #ef444433}50%{box-shadow:0 10px 30px #0006,0 0 28px #ef444488}}
#pvivo{font-variant-numeric:tabular-nums;transition:color .3s ease}
#pvivo.sub{color:#4ade80}#pvivo.baj{color:#fca5a5}
.wrap{max-width:1120px;margin:0 auto;position:relative;z-index:1}
header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
header h1{font-size:21px;margin:0;display:flex;align-items:center;gap:9px}
.logo{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:9px;
font-weight:800;font-size:16px;color:#fff;background:linear-gradient(135deg,#0ea5e9,#6366f1);
box-shadow:0 0 14px #38bdf855}
.cdot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:5px}
.atag{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.6px;color:#fca5a5;
border:1px solid #ef444455;background:#450a0a;border-radius:5px;padding:2px 7px;margin-right:6px}
.fmono{display:inline-flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%;
font-weight:800;font-size:22px;color:#fff}
.fmono.b{background:linear-gradient(135deg,#0ea5e9,#1e3a8a);box-shadow:0 0 18px #38bdf855}
.fmono.t{background:linear-gradient(135deg,#22c55e,#14532d);box-shadow:0 0 18px #22c55e55}
.fmono.o{background:linear-gradient(135deg,#ef4444,#7f1d1d);box-shadow:0 0 18px #ef444455}
.fighter.dormido .fmono{filter:grayscale(.8);animation:respirar 3.2s ease-in-out infinite}
.simtag{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.6px;color:#93c5fd;
border:1px solid var(--line);background:#0c0c0e;border-radius:5px;padding:2px 7px;margin-right:6px}
ul.pq li{border-left:3px solid #38bdf8}
.live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);
border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--grn);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:14px;align-items:start}
#c-ultima,#c-sala{grid-column:1/-1}
.card{margin-bottom:14px;break-inside:avoid}
#c-sala{break-inside:avoid;grid-column:1/-1}
#salaCanvas{width:100%;height:560px;display:block;background:#020304;border-radius:8px}
.card{background:linear-gradient(180deg,rgba(255,255,255,.024),rgba(255,255,255,0) 120px),var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px 16px 14px;
box-shadow:var(--shadow);backdrop-filter:blur(8px);animation:up .55s both}
.card:hover{border-color:var(--line2)}
.card:nth-child(2){animation-delay:.06s}.card:nth-child(3){animation-delay:.12s}
.card:nth-child(4){animation-delay:.18s}.card:nth-child(5){animation-delay:.24s}
.card:nth-child(6){animation-delay:.3s}.card:nth-child(7){animation-delay:.36s}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
h2{font-size:12px;letter-spacing:.8px;text-transform:uppercase;color:#93c5fd;margin:0 0 10px;font-weight:750}
p{color:var(--mut);font-size:13.5px;line-height:1.6;margin:7px 0;max-width:75ch}
.big{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.8px;line-height:1.05}
.badge{display:inline-block;font-size:11px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;border-radius:999px;padding:4px 11px;
vertical-align:middle;margin-left:8px;white-space:nowrap}
.badge.alza{background:rgba(34,197,94,.12);color:#4ade80;border:1px solid rgba(34,197,94,.35)}
.badge.baja{background:rgba(239,68,68,.12);color:#fca5a5;border:1px solid rgba(239,68,68,.38)}
.badge.lateral{background:rgba(148,163,184,.12);color:#e2e8f0;border:1px solid rgba(148,163,184,.35)}
.pill{height:8px;border-radius:99px;background:#0c0c0e;overflow:hidden;margin-top:8px}
.pill i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--amb),var(--grn));
width:0;animation:fill 1.1s .2s forwards}
@keyframes fill{to{width:var(--w,30%)}}
.sub{font-size:12px;color:var(--mut);margin-top:6px}
svg.resp{width:100%;height:auto;display:block;background:#070709;border-radius:10px}
svg .tag{fill:#94a3b8;font-size:11px}
svg .umbral{stroke:#f59e0b;stroke-dasharray:5 4;stroke-width:1;opacity:.7}
svg .umbral.fuerte{stroke:#22c55e}
svg .bar{transform-origin:bottom;transform-box:fill-box;animation:grow .5s both;
transition:fill .2s ease,filter .2s ease;cursor:pointer}
svg .bar:hover{fill:#f8fafc;filter:drop-shadow(0 0 6px #ffffff99)}
@keyframes grow{from{transform:scaleY(.1)}to{transform:scaleY(1)}}
.b-green{fill:#22c55e}.b-amber{fill:#f59e0b}.b-slate{fill:#475569}.b-zero{fill:#1e293b;stroke:#475569;stroke-width:1}
svg .rejilla{stroke:#ffffff14;stroke-width:1}
svg .linea{stroke-dasharray:1400;stroke-dashoffset:1400;animation:draw 1.4s .1s forwards}
@keyframes draw{to{stroke-dashoffset:0}}
svg circle.alert{fill:var(--red);animation:blink 1.6s infinite;transition:filter .2s ease;cursor:pointer}
svg circle.alert:hover{fill:#fecaca;filter:drop-shadow(0 0 7px #ffffffaa)}
svg circle.last{fill:var(--grn);filter:drop-shadow(0 0 4px #22c55e);transition:filter .2s ease;cursor:pointer}
svg circle.last:hover{fill:#f8fafc;filter:drop-shadow(0 0 8px #ffffffbb)}
svg .lvl{stroke-width:2;opacity:1;transition:stroke .2s ease}
svg .lvl:hover{stroke:#f8fafc;opacity:1}
svg .lvl.nsop{stroke:#4ade80;filter:drop-shadow(0 0 4px #22c55e99)}
svg .lvl.nres{stroke:#f87171;filter:drop-shadow(0 0 4px #ef444499)}
svg text.lvlTxt{fill:#fff;font-size:12px;font-weight:700;paint-order:stroke;stroke:#000;stroke-width:3px}
svg .canal{fill:rgba(255,255,255,.045)}
svg .lvlpx{stroke:#fff;stroke-width:1.4;stroke-dasharray:3 3;opacity:.9;filter:drop-shadow(0 0 4px #ffffff99)}
.kv{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:#cbd5e1;background:#0c0c0e;
transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease;cursor:default}
.chip b{color:#fff}
.chip:hover{border-color:#e2e8f0;color:#fff;box-shadow:0 0 10px #ffffff22;transform:translateY(-1px)}
.chead:hover .ctit{color:#fff}
.chead:hover .chev{color:#fff;transform:scale(1.25)}
table.ops tr:hover td{background:#ffffff0d}
.tscroll{max-height:264px;overflow-y:auto;border-radius:8px}
.tscroll thead th{position:sticky;top:0;background:#0c0c0e;z-index:1}
footer{color:#64748b;font-size:12px;margin:16px 2px;line-height:1.5}
@media(max-width:1024px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){body{padding:14px 10px 24px}.grid{grid-template-columns:minmax(0,1fr)}.card{padding:14px 13px;margin-bottom:10px}table.ops th,table.ops td{padding:7px 8px;font-size:12px}.tscroll{max-height:320px}header{gap:8px}.nav{margin:0 -2px 6px;padding:8px 2px}}
@media(max-width:480px){.big{font-size:26px;letter-spacing:-.4px}.clock{font-size:22px}.gwrap{flex-direction:column;align-items:flex-start}}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:#000}
::-webkit-scrollbar-thumb{background:#26262b;border-radius:99px;border:2px solid #000}
::-webkit-scrollbar-thumb:hover{background:#3a3a41}
button:focus-visible,a:focus-visible{outline:2px solid #38bdf8;outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
.stats{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.stat{flex:1 1 100px;background:#0c0c0e;border:1px solid var(--line);border-radius:10px;padding:6px 9px;
transition:border-color .2s ease,box-shadow .2s ease}
.stat:hover{border-color:#ffffff38;box-shadow:0 0 10px #ffffff14}
.tfgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:6px}
.tf{background:#0c0c0e;border:1px solid var(--line);border-radius:10px;padding:8px;
transition:border-color .2s ease,box-shadow .2s ease}
.tf:hover{border-color:#ffffff38;box-shadow:0 0 10px #ffffff14}
.tf .thead{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.tf .tfn{font-weight:800;font-size:13px}
.tf .tend{font-size:10px;font-weight:700;border-radius:999px;padding:2px 8px;text-transform:uppercase}
.tend.alcista{background:#052e16;color:#4ade80}
.tend.bajista{background:#450a0a;color:#fca5a5}
.tend.lateral{background:#1e293b;color:#cbd5e1}
svg.spark{width:100%;height:56px;display:block}
svg.spark .sline{fill:none;stroke-width:2;stroke-linejoin:round}
.rsibar{height:5px;border-radius:99px;background:#17171a;overflow:hidden;margin-top:6px}
.rsibar i{display:block;height:100%;border-radius:99px}
.tf .tmeta{font-size:11px;color:var(--mut);margin-top:4px;font-variant-numeric:tabular-nums}
ul.pq{list-style:none;margin:8px 0 0;padding:0}
ul.pq li{font-size:12.5px;color:#cbd5e1;background:#0c0c0e;border:1px solid var(--line);
border-radius:10px;padding:7px 10px;margin-bottom:6px}
ul.pq li:hover{border-color:#ffffff38}
.sec{grid-column:1/-1;font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;
color:#64748b;margin:10px 2px 14px;padding-top:10px;border-top:1px solid #ffffff10}
.nav{display:flex;gap:6px;overflow-x:auto;padding:8px 2px;margin-bottom:4px;scrollbar-width:none;
position:sticky;top:0;z-index:5;background:rgba(0,0,0,.82);backdrop-filter:blur(8px)}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:none;font-size:12px;color:#cbd5e1;background:#0c0c0e;border:1px solid var(--line);
border-radius:999px;padding:5px 13px;text-decoration:none;transition:border-color .2s ease,color .2s ease}
.nav a:hover{border-color:#38bdf8;color:#fff}
html{scroll-behavior:smooth}
.card{scroll-margin-top:10px}
.duel{display:flex;align-items:stretch;gap:8px;margin-top:8px}
.fighter{flex:1;background:#0c0c0e;border:1px solid var(--line);border-radius:12px;padding:10px;
text-align:center;transition:all .3s ease}
.fighter .fmono{font-size:22px;display:inline-block}
.fighter .fname{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin-top:2px}
.fighter .fpow{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:2px}
.fighter.winner{border-color:#ffd76a;box-shadow:0 0 22px #ffd76a55,0 0 44px #ffd76a22;
animation:winGlow 1.8s ease-in-out infinite}
.fighter.winner .fmono{animation:rebote 1s ease-in-out infinite}
.fighter.loser{opacity:.55;filter:grayscale(.9);transform:rotate(-3deg) scale(.96)}
@keyframes winGlow{0%,100%{box-shadow:0 0 14px #ffd76a44}50%{box-shadow:0 0 30px #ffd76a88,0 0 60px #ffd76a33}}
@keyframes rebote{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-8px) rotate(4deg)}}
.vs{align-self:center;font-size:20px;font-weight:800;color:#ffd76a;text-shadow:0 0 12px #ffd76a88;
animation:blink 2.4s infinite;white-space:nowrap}
.winbanner{margin-top:8px;text-align:center;font-weight:800;font-size:14px;border-radius:10px;padding:8px;
background:linear-gradient(90deg,#3b2f04,#5b4a08,#3b2f04);background-size:200% 100%;
border:1px solid #ffd76a88;color:#ffe9a8;animation:brillo 3s linear infinite}
@keyframes brillo{from{background-position:0% 0}to{background-position:200% 0}}
.fighter.dormido .fmono{filter:grayscale(.7);animation:respirar 3.2s ease-in-out infinite}
@keyframes respirar{0%,100%{transform:scale(1);opacity:.85}50%{transform:scale(1.07);opacity:1}}
.zzz{position:relative;height:22px;font-size:13px;color:#94a3b8}
.zzz span{position:absolute;left:50%;bottom:0;opacity:0;animation:subir 3s ease-in infinite}
.zzz span:nth-child(2){animation-delay:1s;font-size:16px}
.zzz span:nth-child(3){animation-delay:2s;font-size:19px}
@keyframes subir{0%{transform:translateX(-50%);opacity:0}30%{opacity:.9}100%{transform:translate(-8px,-22px);opacity:0}}

.stat small{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut)}
.stat b{font-size:15px;font-variant-numeric:tabular-nums}
table.ops{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px;line-height:1.45}
table.ops th{text-align:left;color:#a9b8cc;font-weight:700;font-size:11px;letter-spacing:.5px;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
table.ops td{padding:8px 10px;border-bottom:1px solid rgba(148,163,184,.1);font-variant-numeric:tabular-nums;vertical-align:top}
table.ops tr:last-child td{border-bottom:none}
.win{color:#4ade80;font-weight:700}.loss{color:#fca5a5;font-weight:700}
.tagLONG{color:#4ade80;font-weight:700}.tagSHORT{color:#fca5a5;font-weight:700}
.mini{font-size:12px;color:var(--mut)}
.chead{all:unset;display:flex;align-items:center;justify-content:space-between;width:100%;cursor:pointer;
box-sizing:border-box;padding:6px 0 12px;min-height:36px;border-radius:8px}
.ctit{font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:#93c5fd}
.chev{color:#93c5fd;font-size:14px;transition:transform .35s ease;display:inline-block}
.card.closed .chev{transform:rotate(-90deg)}
.cbody{display:grid;grid-template-rows:1fr;opacity:1;transition:grid-template-rows .45s ease,opacity .3s ease}
.card.closed .cbody{grid-template-rows:0fr;opacity:0}
.cinner{overflow:hidden;min-height:0}
.tbtn{font-size:12px;color:#cbd5e1;background:#0f172a;border:1px solid var(--line);border-radius:999px;
padding:4px 12px;cursor:pointer}
.tbtn:hover{border-color:#38bdf8;color:#fff}
.gwrap{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.gauge{width:150px;flex:none}
.gauge .track{stroke:#17171a}
.gauge .fill{stroke-linecap:round;transition:stroke-dashoffset 1.2s ease}
.gnum{font-size:26px;font-weight:800;fill:#fff}
.glab{font-size:10px;fill:var(--mut)}
.clock{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}
.nyon{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px}
.nyon.on{background:#052e16;color:#4ade80;border:1px solid #22c55e55}
.nyon.off{background:#1e293b;color:#cbd5e1;border:1px solid var(--line)}
/* ===== TEMA MONOCROMO ARQUITECTONICO (idle) ===== */
:root{--acc:#f0f0f0;--grn:#e8e8e8;--amb:#aab0bb;--red:#8a8a8a}
body{background:#000;background-image:linear-gradient(rgba(240,240,240,.028) 1px,transparent 1px),linear-gradient(90deg,rgba(240,240,240,.028) 1px,transparent 1px);background-size:28px 28px}
body::before{background:radial-gradient(circle,#1a1d24 0%,transparent 70%)!important}
body::after{background:radial-gradient(circle,#0e0f13 0%,transparent 70%)!important}
body[data-bias="ALZA"]::before,body[data-bias="BAJA"]::before{ background:radial-gradient(circle,#1a1d24 0%,transparent 70%)!important}
body[data-bias="ALZA"]::after,body[data-bias="BAJA"]::after{background:radial-gradient(circle,#0e0f13 0%,transparent 70%)!important}
.logo{background:linear-gradient(135deg,#e8e8e8,#555)!important;box-shadow:0 0 14px #ffffff44!important;color:#000!important}
.flash{border-color:#ffffff88!important;animation:flashB 1.8s ease-in-out infinite}
@keyframes flashB{0%,100%{box-shadow:0 10px 30px #0006,0 0 8px #ffffff33}50%{box-shadow:0 10px 30px #0006,0 0 28px #ffffff88}}
#pvivo.sub{color:#fff}#pvivo.baj{color:#8a8a8a}
.win,.tagLONG{color:#fff!important}.loss,.tagSHORT{color:#9a9a9a!important}
.atag{color:#e8e8e8!important;border-color:#ffffff44!important;background:#1a1a1a!important}
.tend.alcista{background:#1a1a1a!important;color:#fff!important}
.tend.bajista{background:#1a1a1a!important;color:#9a9a9a!important}
.fmono.b,.fmono.t,.fmono.o{background:linear-gradient(135deg,#e8e8e8,#444)!important;box-shadow:0 0 18px #ffffff33!important;color:#000!important}
.fighter.winner{border-color:#fff!important;box-shadow:0 0 22px #ffffff44!important}
.vs{color:#fff!important;text-shadow:0 0 12px #ffffff66!important}
.winbanner{background:linear-gradient(90deg,#1a1a1a,#333,#1a1a1a)!important;background-size:200% 100%;border-color:#ffffff55!important;color:#fff!important}
ul.pq li{border-left-color:#f0f0f0!important}
svg .lvl.nsop{stroke:#e8e8e8!important;filter:drop-shadow(0 0 4px #ffffff66)!important}
svg .lvl.nres{stroke:#8a8a8a!important;filter:drop-shadow(0 0 4px #ffffff44)!important}
.ctit,.chev{color:#e8e8e8!important}
.nav a:hover,.tbtn:hover{border-color:#f0f0f0!important}
button:focus-visible,a:focus-visible{outline-color:#f0f0f0!important}
/* ===== CUADRILLA IDLE ===== */
.crew{display:flex;gap:8px;align-items:flex-end;margin-left:6px}
.bot{width:34px;text-align:center}
.bot .cuerpo{width:26px;height:26px;margin:0 auto;border-radius:50%;background:#0b0d12;border:2px solid #f0f0f0;position:relative;animation:salto 2.6s ease-in-out infinite;box-shadow:0 0 10px #ffffff22}
.bot:nth-child(2) .cuerpo{animation-delay:.3s}.bot:nth-child(3) .cuerpo{animation-delay:.6s}
.bot:nth-child(4) .cuerpo{animation-delay:.9s}.bot:nth-child(5) .cuerpo{animation-delay:1.2s}.bot:nth-child(6) .cuerpo{animation-delay:1.5s}
@keyframes salto{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
.bot .cuerpo::before,.bot .cuerpo::after{content:"";position:absolute;top:7px;width:4px;height:5px;border-radius:50%;background:#fff;animation:parp 4s infinite}
.bot .cuerpo::before{left:6px}.bot .cuerpo::after{right:6px}
@keyframes parp{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
.bot small{display:block;font-size:8px;color:#9a9a9a;letter-spacing:.5px;margin-top:2px}
.crew[data-mood="alerta"] .cuerpo{border-color:#fff;animation:salto .7s ease-in-out infinite;box-shadow:0 0 16px #ffffff66}
.crew[data-mood="bien"] .cuerpo{box-shadow:0 0 14px #ffffff44}
.crew[data-mood="bajo"] .cuerpo{border-color:#555;animation:none;opacity:.75}
.idlebar{height:3px;border-radius:99px;background:#17171a;overflow:hidden;margin-top:4px}
.idlebar i{display:block;height:100%;background:#f0f0f0;width:0%}
.big{font-variant-numeric:tabular-nums;letter-spacing:-.5px}
/* ===== BOTS LIBRES ===== */
.freebot{position:absolute;left:0;top:0;z-index:6;width:30px;pointer-events:none;transition:none;will-change:transform}
.freebot .cb{width:24px;height:24px;margin:0 auto;border-radius:50%;background:#0b0d12;border:2px solid #f0f0f0;position:relative;box-shadow:0 0 10px #ffffff33}
.freebot .cb::before,.freebot .cb::after{content:"";position:absolute;top:7px;width:4px;height:5px;border-radius:50%;background:#fff}
.freebot .cb::before{left:5px}.freebot .cb::after{right:5px}
.freebot .lb{display:block;font-size:8px;color:#e8e8e8;text-align:center;letter-spacing:.5px;text-shadow:0 0 6px #000,0 0 3px #000}
.freebot .bb{position:absolute;bottom:30px;left:50%;transform:translateX(-50%);background:rgba(240,240,240,.95);color:#000;font-size:9px;padding:2px 6px;border-radius:4px;white-space:nowrap;display:none;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.freebot.work .bb{display:block}
.freebot.up .cb{border-color:#fff;box-shadow:0 0 18px #ffffff88}
.card.extract{outline:2px solid #ffffffaa!important;outline-offset:2px}
.portal{position:fixed;right:10px;z-index:5;width:44px;height:44px;border:2px dashed #f0f0f0;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;background:rgba(240,240,240,.06);box-shadow:0 0 16px #ffffff33;animation:giro 6s linear infinite;pointer-events:none}
@keyframes giro{from{transform:rotate(0)}to{transform:rotate(360deg)}}
h1,.ctit,.sec{letter-spacing:1.5px}
"""


def _prox_pasada(ahora_dt):
    """Próxima pasada del bot (espejo de cron-job): NY 13–20 c/5, resto c/15."""
    try:
        h, m = ahora_dt.hour, ahora_dt.minute
        if 13 <= h <= 20:
            nm = ((m // 5) + 1) * 5
            base = ahora_dt.replace(second=0, microsecond=0)
            return base + datetime.timedelta(minutes=nm - m) if nm < 60 else base.replace(hour=h + 1, minute=0)
        nm = ((m // 15) + 1) * 15
        base = ahora_dt.replace(second=0, microsecond=0)
        if nm < 60:
            return base + datetime.timedelta(minutes=nm - m)
        return (base + datetime.timedelta(days=1)).replace(hour=0, minute=0)
    except Exception:
        return None


def _sec(titulo, sid=None):
    return f"<div class='sec'{(' id=' + sid) if sid else ''}>{titulo}</div>"


def _card(cid, titulo, cuerpo):
    return (f"<div class='card' id='c-{cid}'>"
            f"<button class='chead' data-c='{cid}' aria-expanded='true'>"
            f"<span class='ctit'>{titulo}</span><span class='chev'>▾</span></button>"
            f"<div class='cbody'><div class='cinner'>{cuerpo}</div></div></div>")


def _sala_html(snap, est):
    """Sala viva: canvas grande con datos horneados (sin fetch). Siempre renderiza."""
    try:
        snap = snap if isinstance(snap, dict) else {}
        est = est if isinstance(est, dict) else {}
        niv = snap.get("niv") or {}
        sop = (niv.get("sop") or [{}])[0] or {}
        res = (niv.get("res") or [{}])[0] or {}
        return ("<canvas id='salaCanvas' width='1100' height='560'></canvas>"
                "<p class='mini'>Oficina en vivo: techo "
                f"{_esc(res.get('precio') or 's/d')} · piso "
                f"{_esc(sop.get('precio') or 's/d')} · sin datos = modo demo.</p>")
    except Exception:
        return "<canvas id='salaCanvas' width='1100' height='560'></canvas>"


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
        erc = ""
        try:
            if d.get("er") is not None:
                erc = f" · ER {float(d['er']):.2f}"
        except Exception:
            pass
        chips.append(f"<span class='chip'><b>{lbl}</b> {_esc(t)} · RSI {_esc(r)}{_esc(erc)}</span>")
    fg = snap.get("fg") or {}
    senti = snap.get("senti") or {}
    chips.append(f"<span class='chip'>Miedo <b>{_esc(fg.get('valor', '?'))}</b> {_esc(fg.get('etiqueta', ''))}</span>")
    fund = senti.get("funding", None)
    chips.append(f"<span class='chip'>funding <b>{_esc(fund if fund is not None else 's/d')}</b></span>")
    pres = snap.get("pres") or {}
    if pres.get("txt"):
        chips.append(f"<span class='chip'>News {_esc(pres.get('txt'))}</span>")
    niv = snap.get("niv") or {}
    try:
        sop = (niv.get("sop") or [{}])[0].get("precio", "?")
        res = (niv.get("res") or [{}])[0].get("precio", "?")
        chips.append(f"<span class='chip'>SOP <b>{_esc(sop)}</b> · RES <b>{_esc(res)}</b></span>")
    except Exception:
        pass
    evs = snap.get("evs") or []
    if evs:
        e0 = evs[0]
        chips.append(f"<span class='chip'>Evt {_esc(e0.get('titulo', '?'))}</span>")
    return (f"<p>Régimen <b style='color:#e2e8f0'>{_esc(reg)}</b> · grado <b style='color:#e2e8f0'>{_esc(grade)}</b></p>"
            f"<div class='kv'>{''.join(chips)}</div>")


def _hace(tiso, ahora):
    try:
        t0 = datetime.datetime.fromisoformat(tiso)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        h = (ahora - t0).total_seconds() / 3600
        if h < 1:
            return f"hace {int(h * 60)}min"
        return f"hace {h:.1f}h"
    except Exception:
        return ""


def frescura(tiso, ahora_dt, max_min=15):
    try:
        s = str(tiso).strip() if isinstance(tiso, str) else tiso
        try:
            if isinstance(s, str) and s.endswith("Z"):
                s = s[:-1] + "+00:00"
            t0 = datetime.datetime.fromisoformat(s)
        except Exception:
            return ("s/d", "")
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        try:
            ahora = ahora_dt
            if ahora.tzinfo is None:
                ahora = ahora.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return ("s/d", "")
        try:
            mm = float(max_min)
        except Exception:
            mm = 15
        diff_min = (ahora - t0).total_seconds() / 60
        if diff_min < 0:
            diff_min = 0
        texto = _hace(tiso if isinstance(tiso, str) else str(tiso), ahora_dt) or f"hace {int(diff_min)}min"
        if diff_min <= mm:
            return ("vivo", texto)
        if diff_min <= 4 * mm:
            return ("tibio", texto)
        return ("viejo", texto)
    except Exception:
        return ("s/d", "")


def _sh(x):
    try:
        import math
        x = [float(v) for v in (x or [])]
        if len(x) < 5:
            return None
        m = sum(x) / len(x)
        var = sum((v - m) ** 2 for v in x) / len(x)
        return round(m / math.sqrt(var), 2) if var > 0 else None
    except Exception:
        return None


def _ev_txt(l):
    try:
        l = list(l or [])
        if len(l) < 5:
            return "s/d"
        p = sum(l) / len(l)
        return f"{2 * p - (1 - p):+.2f}R"
    except Exception:
        return "s/d"


def _calib_txt(log):
    try:
        log = [e for e in (log or []) if isinstance(e, dict)]
        if len(log) < 5:
            return ""
        br = sum(((float(e.get("conf", 50)) / 100) - float(e.get("r", 0))) ** 2 for e in log) / len(log)
        cubs = {}
        for e in log:
            c = float(e.get("conf", 50))
            k = "40s" if c < 50 else ("50s" if c < 60 else "60+")
            a, b = cubs.get(k, [0, 0])
            cubs[k] = [a + 1, b + float(e.get("r", 0))]
        det = ", ".join(f"{k}:{round(100 * w / n)}%({n})" for k, (n, w) in sorted(cubs.items()))
        return f"<p>Conciencia: {det} · Brier {round(br, 3)}</p>"
    except Exception:
        return ""


def _ops_html(est, ahora):
    abiertas = [o for o in (est.get("paper_abiertas") or []) if isinstance(o, dict)]
    cerradas = [c for c in (est.get("paper_cerradas") or []) if isinstance(c, dict)]
    pend = [p for p in (est.get("pendientes") or []) if isinstance(p, dict)]
    journal = [j for j in (est.get("journal") or []) if isinstance(j, dict)]
    banco = est.get("banco")
    n = len(cerradas)
    w = sum(1 for c in cerradas if _num(c.get("pnl")) > 0)
    tot_r = sum(_num(c.get("r")) for c in cerradas)
    tot_pnl = sum(_num(c.get("pnl")) for c in cerradas)
    wr = f"{round(w / n * 100)}% ({w}/{n})" if n else "s/d"
    shp = _sh([c.get("r", 0) for c in cerradas])
    shp_txt = f" · Sharpe {shp:+}" if shp is not None else ""
    racha = 0
    for c in reversed(cerradas):
        if _num(c.get("pnl")) < 0:
            racha += 1
        else:
            break
    frenos = []
    try:
        b = float(banco) if banco is not None else 100.0
        pico = float(est.get("banco_pico", b))
        dd = (pico - b) / pico * 100 if pico > 0 else 0
        if dd >= 10:
            frenos.append("bloqueo pico −10%")
    except Exception:
        dd = 0
    pd = est.get("paper_dia") or {}
    try:
        base = float(banco) if banco is not None else 100.0
        if isinstance(pd, dict) and float(pd.get("pnl", 0)) <= -0.03 * base:
            frenos.append("bloqueo día −3%")
    except Exception:
        pass
    if racha >= 3:
        frenos.append("aviso racha: riesgo 0,5%")
    freno_txt = " · ".join(frenos) if frenos else "frenos OK"
    btxt = f"{miles(banco)} USDT ({tot_pnl:+.0f})" if banco is not None else "100 USDT (sin empezar)"
    uc = est.get("ultima_conf")
    uc_txt = ""
    if isinstance(uc, (int, float)) and not abiertas and n == 0:
        uc_txt = f" · última conf {uc:g}% (requiere 35%+ con sesgo)"
    stats = (
        f"<div class='stats'>"
        f"<div class='stat'><small>Banco</small><b>{btxt}</b></div>"
        f"<div class='stat'><small>Ganadas</small><b>{wr}</b></div>"
        f"<div class='stat'><small>Total</small><b>{tot_r:+.1f}R{shp_txt}</b></div>"
        f"<div class='stat'><small>Racha pérdida</small><b>{racha}</b></div>"
        f"</div><p class='mini'>{freno_txt} · papel opera señales 35%+ (invisible, sin avisos){uc_txt}</p>")
    if abiertas:
        filas = "".join(
            f"<tr><td class='tag{_esc(o.get('dir', ''))}'>{_esc(o.get('dir', '?'))}</td>"
            f"<td>{miles(o.get('entrada'))}</td><td>{miles(o.get('stop'))}</td>"
            f"<td>{miles(o.get('tp'))}</td><td>{miles(o.get('riesgo'))}</td></tr>"
            for o in abiertas[-6:])
        ab = (f"<p class='mini'>Abiertas ({len(abiertas)})</p>"
              f"<table class='ops'><tr><th>Dir</th><th>Ent</th><th>SL</th><th>TP</th><th>Riesgo</th></tr>{filas}</table>")
    else:
        ab = "<p class='mini'>Sin abiertas ahora mismo.</p>"
    if cerradas:
        filas = ""
        for c in reversed(cerradas[-8:]):
            pnl = _num(c.get("pnl"))
            cls = "win" if pnl > 0 else "loss"
            res = c.get("res", "?")
            ft = ""
            try:
                ft = str(c.get("t", ""))[5:16].replace("T", " ")
            except Exception:
                pass
            filas += (f"<tr><td class='tag{_esc(c.get('dir', ''))}'>{_esc(c.get('dir', '?'))}</td>"
                      f"<td>{_esc(res)}</td><td class='{cls}'>{pnl:+.0f}</td>"
                      f"<td class='{cls}'>{_num(c.get('r')):+.2f}R</td><td>{_esc(ft)}</td></tr>")
        ce = (f"<p class='mini'>Últimas cerradas ({n})</p>"
              f"<table class='ops'><tr><th>Dir</th><th>Fin</th><th>PnL</th><th>R</th><th>Fecha</th></tr>{filas}</table>")
    else:
        ce = ("<p class='mini'>Sin cerradas aún — el papel sólo abre con ALZA/BAJA de 35%+ "
              "y el mercado viene lateral. Cuando opere, aquí verás cada cierre.</p>")
    if pend:
        lp = "".join(
            f"<span class='chip'><b>{_esc(p.get('bias', '?'))}</b> {_esc(p.get('conf', '?'))}% @ {miles(p.get('precio'))} "
            f"{_esc(_hace(p.get('t', ''), ahora))}</span>" for p in pend[-6:])
        pe = f"<p class='mini'>En seguimiento ({len(pend)} — se evalúan a 8h)</p><div class='kv'>{lp}</div>"
    else:
        pe = "<p class='mini'>En seguimiento: 0 — no hay señales esperando evaluación.</p>"
    if journal:
        lj = "".join(
            f"<span class='chip'><b>{_esc(j.get('dir', '?'))}</b> {_esc(j.get('res', '?'))} "
            f"{_num(j.get('r')):+.2f}R</span>" for j in journal[-5:])
        jo = f"<p class='mini'>Mi diario ({len(journal)})</p><div class='kv'>{lj}</div>"
    else:
        jo = "<p class='mini'>Mi diario: vacío — registra con /opere en Telegram.</p>"
    sims = [o for o in (est.get("sim_abiertas", []) or []) if isinstance(o, dict)]
    simc = [o for o in (est.get("sim_cerradas", []) or []) if isinstance(o, dict)]
    if sims or simc:
        ls = "".join(
            f"<span class='chip'><b>{_esc(o.get('dir', '?'))}</b> {miles(o.get('entrada'))} "
            f"SL {miles(o.get('stop'))}</span>" for o in sims[-4:])
        w = sum(1 for x in simc if _num(x.get("r")) > 0)
        jo += (f"<p class='mini'><span class='simtag'>SIM</span>Simuladas: {len(sims)} abiertas, {len(simc)} cerradas ({w} ganadas)</p>"
               f"<div class='kv'>{ls}</div>" if ls else
               f"<p class='mini'><span class='simtag'>SIM</span>Simuladas: {len(simc)} cerradas ({w} ganadas)</p>")
    return (f"{stats}{ab}{ce}{pe}{jo}")


def _sombra_html(est):
    """Tarjeta Sombra: eval_sombra acumuladas + pendientes en cola. Puro."""
    try:
        evs = [e for e in ((est or {}).get("eval_sombra") or []) if isinstance(e, dict)]
        pen = [p for p in ((est or {}).get("pend_sombra") or []) if isinstance(p, dict)]
        if not evs and not pen:
            return "<p class='mini'>sin evaluaciones aún</p>"
        n = len(evs)
        ok = sum(1 for e in evs if e.get("r") == 1)
        wr = f"{round(ok / n * 100)}% ({ok}/{n})" if n else "s/d"
        return (f"<div class='stats'><div class='stat'><small>Evaluadas</small><b>{n}</b></div>"
                f"<div class='stat'><small>Acierto</small><b>{_esc(wr)}</b></div>"
                f"<div class='stat'><small>En cola</small><b>{len(pen)}</b></div></div>"
                f"<p class='mini'>Mide toda señal con sesgo, sin piso de confianza.</p>")
    except Exception:
        return "<p class='mini'>sin evaluaciones aún</p>"


def _kpis_papel_html(est):
    """KPIs puros de dinero papel desde est['paper_cerradas'] (pnl y r por item)."""
    try:
        bruto = (est or {}).get("paper_cerradas") if isinstance(est, dict) else None
        cerradas = [c for c in (bruto or []) if isinstance(c, dict)]
        if not cerradas:
            return "<p class='mini'>sin operaciones aún</p>"
        n = len(cerradas)
        pnls = [_num(c.get("pnl")) for c in cerradas]
        rs = [_num(c.get("r")) for c in cerradas]
        ganadas = sum(1 for v in pnls if v > 0)
        wr = (ganadas / n * 100) if n else 0.0
        bruto_win = sum(v for v in pnls if v > 0)
        bruto_loss = sum(-v for v in pnls if v < 0)
        if bruto_loss > 0:
            pf_txt = f"{bruto_win / bruto_loss:.2f}"
        else:
            pf_txt = "s/d"
        exp_r = sum(rs) / n if n else 0.0
        i_mejor = max(range(n), key=lambda i: pnls[i])
        i_peor = min(range(n), key=lambda i: pnls[i])
        mejor_txt = f"{pnls[i_mejor]:+.0f} ({rs[i_mejor]:+.2f}R)"
        peor_txt = f"{pnls[i_peor]:+.0f} ({rs[i_peor]:+.2f}R)"
        ultimo = pnls[-1]
        if ultimo > 0:
            signo = 1
        elif ultimo < 0:
            signo = -1
        else:
            signo = 0
        racha = 0
        if signo == 1:
            for v in reversed(pnls):
                if v > 0:
                    racha += 1
                else:
                    break
            racha_txt = f"{racha} ganadas"
        elif signo == -1:
            for v in reversed(pnls):
                if v < 0:
                    racha += 1
                else:
                    break
            racha_txt = f"{racha} perdidas"
        else:
            racha_txt = "neutra"
        return (
            f"<div class='stats'>"
            f"<div class='stat'><small>Cerradas</small><b>{_esc(n)}</b></div>"
            f"<div class='stat'><small>Ganadas</small><b>{_esc(f'{ganadas}/{n} ({wr:.0f}%)')}</b></div>"
            f"<div class='stat'><small>Profit factor</small><b>{_esc(pf_txt)}</b></div>"
            f"<div class='stat'><small>Expectancy</small><b>{_esc(f'{exp_r:+.2f}R')}</b></div>"
            f"<div class='stat'><small>Mejor</small><b>{_esc(mejor_txt)}</b></div>"
            f"<div class='stat'><small>Peor</small><b>{_esc(peor_txt)}</b></div>"
            f"<div class='stat'><small>Racha actual</small><b>{_esc(racha_txt)}</b></div>"
            f"</div>")
    except Exception:
        return "<p class='mini'>sin operaciones aún</p>"


def _seguimiento_html(est, ahora_dt):
    """En seguimiento: pendientes con cuenta atrás a 8h. Puro, jamás rompe."""
    try:
        pend = [p for p in ((est or {}).get("pendientes") or []) if isinstance(p, dict)]
        if not pend:
            return "<p class='mini'>sin pendientes — no hay señales esperando evaluación.</p>"
        try:
            ahora = ahora_dt
            if ahora is None:
                ahora = datetime.datetime.now(datetime.timezone.utc)
            if ahora.tzinfo is None:
                ahora = ahora.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return "<p class='mini'>sin pendientes — no hay señales esperando evaluación.</p>"
        filas = []
        for p in pend[-6:]:
            try:
                bias = _esc(p.get("bias", "?"))
                conf = _esc(p.get("conf", "?"))
                px = miles(p.get("precio"))
                s = str(p.get("t", "") or "")
                s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
                t0 = datetime.datetime.fromisoformat(s2)
                if t0.tzinfo is None:
                    t0 = t0.replace(tzinfo=datetime.timezone.utc)
                venc = t0 + datetime.timedelta(hours=8)
                rest = (venc - ahora).total_seconds()
                trans = (ahora - t0).total_seconds()
                pct = max(0, min(100, trans / (8 * 3600) * 100))
                if rest <= 0:
                    txt = "vencida, evaluando"
                else:
                    try:
                        txt = _hace(ahora.isoformat(), venc).replace("hace", "vence en")
                    except Exception:
                        txt = ""
                    if not txt:
                        dh = rest / 3600
                        txt = f"vence en {dh:.1f}h" if dh >= 1 else f"vence en {int(rest // 60)}min"
                filas.append(
                    f"<div class='tmeta'><b style='color:#e2e8f0'>{bias}</b> {conf}% @ {px} · {_esc(txt)}</div>"
                    f"<div class='rsibar'><i style='width:{pct:.0f}%;background:#38bdf8'></i></div>")
            except Exception:
                continue
        if not filas:
            return "<p class='mini'>sin pendientes — no hay señales esperando evaluación.</p>"
        return (f"<p class='mini'>En seguimiento ({len(pend)} — se evalúan a 8h)</p>"
                f"{''.join(filas)}")
    except Exception:
        return "<p class='mini'>sin pendientes — no hay señales esperando evaluación.</p>"


def _calibracion_html(est):
    """Calibración: Brier + n + cubetas desde snapshot o est. Puro, jamás rompe."""
    try:
        log = None
        try:
            if isinstance(est, dict):
                log = est.get("eval_log")
                if not log:
                    snap = est.get("snapshot")
                    if isinstance(snap, dict):
                        log = snap.get("eval_log")
        except Exception:
            log = None
        log = [e for e in (log or []) if isinstance(e, dict)]
        if len(log) < 5:
            return "<p class='mini'>sin datos aún (mínimo 5 evaluadas).</p>"
        tab = None
        try:
            fn = globals().get("tabla_calibracion")
            if callable(fn):
                tab = fn(log)
        except Exception:
            tab = None
        if not isinstance(tab, dict):
            try:
                br = sum(((float(e.get("conf", 50)) / 100) - float(e.get("r", 0))) ** 2 for e in log) / len(log)
                cubs = {}
                for e in log:
                    c = float(e.get("conf", 50))
                    k = "40s" if c < 50 else ("50s" if c < 60 else "60+")
                    a, b = cubs.get(k, [0, 0])
                    cubs[k] = [a + 1, b + float(e.get("r", 0))]
                tab = {"n": len(log), "brier": round(br, 3),
                       "cubetas": {k: (nn, round(100 * w / nn)) for k, (nn, w) in sorted(cubs.items())}}
            except Exception:
                return "<p class='mini'>sin datos aún (mínimo 5 evaluadas).</p>"
        try:
            n = int(tab.get("n", len(log)))
            br = float(tab.get("brier", 0))
        except Exception:
            return "<p class='mini'>sin datos aún (mínimo 5 evaluadas).</p>"
        cubs = tab.get("cubetas") if isinstance(tab.get("cubetas"), dict) else {}
        chips = []
        try:
            for k in sorted(cubs.keys()):
                vv = cubs[k]
                if isinstance(vv, (list, tuple)) and len(vv) == 2:
                    chips.append(f"<span class='chip'><b>{_esc(k)}</b> {_esc(vv[1])}% ({_esc(vv[0])})</span>")
                else:
                    chips.append(f"<span class='chip'>{_esc(k)}: {_esc(vv)}</span>")
        except Exception:
            chips = []
        det = f"<div class='kv'>{''.join(chips)}</div>" if chips else ""
        return (f"<div class='stats'><div class='stat'><small>Brier</small><b>{_esc(round(br, 3))}</b></div>"
                f"<div class='stat'><small>Evaluadas</small><b>{_esc(n)}</b></div></div>{det}"
                f"<p class='mini'>Brier 0 perfecto · 0.25 inútil. Cubeta: acierto (n).</p>")
    except Exception:
        return "<p class='mini'>sin datos aún (mínimo 5 evaluadas).</p>"


CD_JS = ("<script>(function(){try{var el=document.getElementById('cd');"
          "if(!el||!el.dataset||!el.dataset.next)return;"
          "var t=new Date(el.dataset.next).getTime();if(!isFinite(t))return;"
          "function tk(){try{var d=t-Date.now();if(d<0){el.textContent='pronto';return;}"
          "var h=Math.floor(d/36e5),m=Math.floor(d%36e5/6e4),s=Math.floor(d%6e4/1e3);"
          "el.textContent=h+'h '+m+'m '+s+'s';}catch(e){}}"
          "try{tk();}catch(e){}setInterval(function(){try{tk();}catch(e){}},1000);}catch(e){}})();</script>")

UI_JS = ("<script>(function(){"
          "var KEY='vig_cards_v1';"
          "function load(){try{return JSON.parse(localStorage.getItem(KEY))||{};}catch(e){return{};}}"
          "function save(s){try{localStorage.setItem(KEY,JSON.stringify(s));}catch(e){}}"
          "document.querySelectorAll('.card').forEach(function(c){"
          "var id=c.id.replace('c-','');if(load()[id]==='0'){c.classList.add('closed');"
          "var b=c.querySelector('.chead');if(b)b.setAttribute('aria-expanded','false');}});"
          "document.querySelectorAll('.chead').forEach(function(b){"
          "b.addEventListener('click',function(){var c=b.closest('.card');c.classList.toggle('closed');"
          "var sh=c.classList.contains('closed');b.setAttribute('aria-expanded',String(!sh));"
          "var s=load();s[b.dataset.c]=sh?'0':'1';save(s);});});"
          "var tgl=document.getElementById('plegar');"
          "if(tgl){try{var _s0=load();var _cs=document.querySelectorAll('.card');var _ao=Array.prototype.some.call(_cs,function(c){return !c.classList.contains('closed');});tgl.textContent=_ao?'Desplegar todo':'Plegar todo';}catch(e){}tgl.addEventListener('click',function(){try{"
          "var cards=document.querySelectorAll('.card');"
          "var anyOpen=Array.prototype.some.call(cards,function(c){return !c.classList.contains('closed');});"
          "var s={};cards.forEach(function(c){var id=c.id.replace('c-','');"
          "if(anyOpen){c.classList.add('closed');s[id]='0';}else{c.classList.remove('closed');s[id]='1';}"
          "var b=c.querySelector('.chead');if(b)b.setAttribute('aria-expanded',String(!anyOpen));});"
          "save(s);tgl.textContent=anyOpen?'Desplegar todo':'Plegar todo';}catch(e){}});}"
          "var AC=null;"
          "function tono(f,t0,dd){try{var o=AC.createOscillator(),g=AC.createGain();o.type='sine';"
          "o.frequency.value=f;o.connect(g);g.connect(AC.destination);var t=AC.currentTime+t0;"
          "g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(0.16,t+0.04);"
          "g.gain.exponentialRampToValueAtTime(0.0001,t+dd);o.start(t);o.stop(t+dd+0.05);}catch(e){}}"
          "function motif(){var b=document.body.dataset.bias||'LATERAL';"
          "var seq=b==='ALZA'?[523,659,784]:(b==='BAJA'?[392,330,262]:[440,440]);"
          "try{if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();}catch(e){return;}"
          "if(AC.state==='suspended'){AC.resume();}"
          "seq.forEach(function(f,i){tono(f,i*0.14,0.4);});}"
          "var MEL=null,AC2=null,AN=null,AD=null,beat=0,rafM=0;"
          "var quietM=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
          "function melodia(){if(MEL)return MEL;"
          "try{var a=new Audio('melodia.mp4');a.loop=true;a.preload='auto';a.volume=0;MEL=a;"
          "MEL.addEventListener('playing',function(){window.__musica=true;fst('playing');});"
          "MEL.addEventListener('pause',function(){window.__musica=false;fst('pause');});"
          "MEL.addEventListener('error',function(){window.__musica=false;motif();});"
          "return MEL;}"
          "catch(e){return null;}}"
          "function fst(e){var b=document.getElementById('sonido');if(!b)return;"
          "b.textContent=e==='playing'?'Sonando':(on?'Sonido on':'Sonido off');}"
          "function audioGraph(){try{if(!AC2)AC2=new (window.AudioContext||window.webkitAudioContext)();"
          "if(!AN){var src=AC2.createMediaElementSource(MEL);AN=AC2.createAnalyser();AN.fftSize=256;"
          "AN.smoothingTimeConstant=0.75;AD=new Uint8Array(AN.frequencyBinCount);"
          "src.connect(AN);AN.connect(AC2.destination);}"
          "if(AC2.state==='suspended'){AC2.resume();}}catch(e){}}"
          "var volTok=0;"
          "function subirVol(tk){try{if(tk!==volTok||!MEL)return;"
          "if(MEL.volume<0.35){MEL.volume=Math.min(0.35,MEL.volume+0.05);"
          "setTimeout(function(){subirVol(tk);},150);}}catch(e){}}"
          "function bajarVol(tk,fin){try{if(tk!==volTok||!MEL){if(fin)fin();return;}"
          "if(MEL.volume>0.02){MEL.volume=Math.max(0,MEL.volume-0.05);"
          "setTimeout(function(){bajarVol(tk,fin);},70);return;}}catch(e){}"
          "if(fin)fin();}"
          "var relojes=0,modoReloj=false;"
          "function latir(){var t=0;try{t=performance.now();}catch(e){}"
          "var L=document.getElementById('latido');"
          "var cv=document.getElementById('fondo');"
          "var fl=window.__flash||0;"
          "if(AN&&AD&&L){try{AN.getByteFrequencyData(AD);var s=0;for(var i=0;i<8;i++)s+=AD[i];"
          "s=s/8/255;"
          "if(s<0.004){relojes++;if(relojes>90)modoReloj=true;}else{relojes=0;modoReloj=false;}"
          "beat=Math.max(s,beat*0.9);"
          "var slow=window.__slow||0;slow+=(s-slow)*0.06;window.__slow=slow;"
          "window.__cal=(window.__cal||0)+1;"
          "if(!modoReloj){var ultimo=window.__bum||-99999;"
          "if(window.__cal>90&&s>slow*1.3&&s>0.08&&(t-ultimo)>220){fl=1;window.__bum=t;}"
          "else{fl=Math.max(0,fl-0.09);}window.__flash=fl;}"
          "}catch(e){}}"
          "if(MEL&&!MEL.paused&&(modoReloj||!AN)&&L){var ph=((t/1000)*142/60)%1;"
          "beat=Math.max(0,1-ph*2.5);"
          "if(ph<0.12){fl=1;}else{fl=Math.max(0,fl-0.12);}window.__flash=fl;}"
          "if(L){var br=0.5+0.5*Math.sin(t/1400);"
          "var b=document.body.dataset.bias||'';"
          "var c=b==='ALZA'?'34,197,94':(b==='BAJA'?'239,68,68':'226,232,240');"
          "L.style.background='radial-gradient(circle at 50% 42%,rgba('+c+','+(0.05+beat*0.25+fl*0.40+br*0.015).toFixed(3)+'),transparent 62%)';"
          "if(cv)cv.style.filter='brightness('+(1+beat*0.8+fl*1.4+br*0.03).toFixed(2)+')';"
          "var D=document.getElementById('destello');"
          "if(D){D.style.background='radial-gradient(circle at 50% 45%,rgba('+c+','+(0.05+beat*0.28+fl*0.50).toFixed(3)+'),transparent 70%)';"
          "D.style.opacity='1';"
          "D.style.boxShadow='inset 0 0 '+(40+fl*150+beat*60).toFixed(0)+'px rgba('+c+','+(0.10+fl*0.45).toFixed(3)+')';}"
          "var H=document.getElementById('c-hero');"
          "if(H){H.style.boxShadow=fl>0.04?('0 0 26px rgba('+c+',0.65),0 10px 30px #0006'):'';}"
          "window.__fr=(window.__fr||0)+1;"
          "if(window.__fr%30===0){var M=document.getElementById('motor');"
          "if(M){var st='ambiente';"
          "if(MEL&&!MEL.paused){st=modoReloj?'reloj 142':('audio '+beat.toFixed(2));}"
          "M.textContent='motor: '+st;}}}"
          "if(!quietM){try{if(rafM)cancelAnimationFrame(rafM);}catch(e){}rafM=requestAnimationFrame(latir);}}"
          "function suena(parar){if(parar){try{if(rafM)cancelAnimationFrame(rafM);}catch(e){}"
          "volTok++;var tk=volTok;"
          "bajarVol(tk,function(){beat=0;window.__flash=0;"
          "var L=document.getElementById('latido');if(L)L.style.background='transparent';"
          "var cv=document.getElementById('fondo');if(cv)cv.style.filter='';"
          "try{if(MEL)MEL.pause();}catch(e){}});return;}"
          "volTok++;var tk2=volTok;"
          "var m=melodia();if(!m){motif();return;}"
          "audioGraph();"
          "try{m.currentTime=0;m.volume=0;window.__slow=0;window.__cal=0;window.__bum=0;var p=m.play();if(p&&p.catch)p.catch(function(){});}catch(e){}"
          "subirVol(tk2);if(!quietM){try{if(rafM)cancelAnimationFrame(rafM);}catch(e){}rafM=requestAnimationFrame(latir);}else{latir();}}"
          "var on=false;try{on=localStorage.getItem('vig_sound')==='1';}catch(e){}"
          "var snd=document.getElementById('sonido');"
          "function paint(){if(snd)snd.textContent=on?'Sonido on':'Sonido off';}"
          "paint();if(on){try{suena(false);}catch(e){}}"
          "try{var _so=false;try{_so=localStorage.getItem('vig_sound')!=='1';}catch(e){_so=true;}if(rafM){try{cancelAnimationFrame(rafM);}catch(e){}rafM=0;}if(!quietM&&!_so){try{rafM=requestAnimationFrame(latir);}catch(e){}}else{try{latir();}catch(e){}}}catch(e){}"
          "if(snd){snd.addEventListener('click',function(){on=!on;"
          "try{localStorage.setItem('vig_sound',on?'1':'0');}catch(e){}paint();suena(!on);});}"
          "})();</script>")


def _gauge_reloj_html(est, hist, ahora_dt):
    try:
        snap = est.get("snapshot") or {}
        fg = snap.get("fg") or {}
        v = _num(fg.get("valor"), None) if fg.get("valor") is not None else None
    except Exception:
        v, fg = None, {}
    if not isinstance(v, (int, float)):
        # respaldo: ultimo fg del historial
        v = None
        for h in reversed(hist or []):
            try:
                fv = float((h or {}).get("fg"))
                v = fv
                break
            except Exception:
                continue
    if not isinstance(v, (int, float)):
        return ""
    try:
        if isinstance(v, bool) or v != v or v in (float("inf"), float("-inf")):
            return ""
    except Exception:
        return ""
    v = max(0, min(100, float(v)))
    et = _esc((fg or {}).get("etiqueta", ""))
    col = "#ef4444" if v < 25 else ("#f59e0b" if v < 45 else ("#facc15" if v < 55 else ("#4ade80" if v < 75 else "#22c55e")))
    L = 188.5
    off = L * (1 - v / 100)
    gauge = (
        f"<svg class='gauge' viewBox='0 0 150 95'>"
        f"<path d='M15 80 A60 60 0 0 1 135 80' fill='none' class='track' stroke-width='12'/>"
        f"<path d='M15 80 A60 60 0 0 1 135 80' fill='none' stroke='{col}' stroke-width='12' "
        f"stroke-dasharray='{L:.1f}' stroke-dashoffset='{L:.1f}' class='fill'>"
        f"<animate attributeName='stroke-dashoffset' from='{L:.1f}' to='{off:.1f}' dur='1.2s' fill='freeze'/>"
        f"<title>{v:g} — {et}</title></path>"
        f"<text x='75' y='68' text-anchor='middle' class='gnum'>{v:g}</text>"
        f"<text x='75' y='84' text-anchor='middle' class='glab'>{et}</text></svg>")
    fgh = []
    try:
        for h in (hist or [])[-30:]:
            fv = (h or {}).get("fg")
            if isinstance(fv, (int, float)) and not isinstance(fv, bool) and fv == fv and fv not in (float("inf"), float("-inf")):
                fgh.append(fv)
    except Exception:
        fgh = []
    spark = svg_linea(fgh, color="#f59e0b") if len(fgh) >= 2 else ""
    evs = [(2, "noche"), (7, "madrugada"), (8, "mañana"), (13, "pre-NY"), (20, "cierre NY")]
    hnow = ahora_dt.hour + ahora_dt.minute / 60
    ny_on = 13 <= ahora_dt.hour < 20
    nxt = None
    for hh, lbl in evs:
        if hnow < hh:
            nxt = (hh, lbl)
            break
    if nxt is None:
        nxt = (evs[0][0] + 24, evs[0][1])
    nh, nlbl = nxt
    base = ahora_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    tnext = base + datetime.timedelta(hours=nh)
    dh = (tnext - ahora_dt).total_seconds() / 3600
    bog = ahora_dt - datetime.timedelta(hours=5)
    estado_ny = ("<span class='nyon on'><span class='dot'></span>NY ACTIVA</span>" if ny_on
                 else "<span class='nyon off'>NY cerrada</span>")
    return (
        f"<div class='gwrap'>{gauge}"
        f"<div><div class='clock'>{bog.strftime('%H:%M')} <small style='font-size:12px;color:#94a3b8'>Bogotá</small></div>"
        f"<div class='sub'>UTC {ahora_dt.strftime('%H:%M')} · {estado_ny}</div>"
        f"<p class='mini'>Siguiente: <b style='color:#e2e8f0'>{nlbl}</b> en "
        f"<b id='cd' data-next='{tnext.isoformat()}'>~{int(dh)}h {int((dh % 1) * 60)}min</b></p></div></div>"
        f"{spark}")


def _tfs_html(snap):
    tf = (snap or {}).get("tf") or {}
    if not isinstance(tf, dict) or not tf:
        return ""
    bloques = []
    for k, lbl, iv in (("h1", "1H", "1h"), ("h4", "4H", "4h"), ("d1", "1D", "1d"), ("w1", "1S", "1w")):
        d = tf.get(k) or {}
        if not isinstance(d, dict):
            continue
        tend = str(d.get("tend", "?")).lower()
        cls = "alcista" if "alci" in tend else ("bajista" if "baji" in tend else "lateral")
        rsi = d.get("rsi", "?")
        try:
            rv = max(0, min(100, float(rsi)))
            rcol = "#4ade80" if rv >= 55 else ("#f59e0b" if rv >= 45 else "#64748b")
            rbar = f"<div class='rsibar'><i style='width:{rv:.0f}%;background:{rcol}'></i></div>"
        except Exception:
            rbar = ""
        try:
            macd = float(d.get("macd", 0))
            mar = "▲" if macd > 0 else ("▼" if macd < 0 else "●")
        except Exception:
            mar = "●"
        bloques.append(
            f"<div class='tf'><div class='thead'><span class='tfn'>{lbl}</span>"
            f"<span class='tend {cls}'>{_esc(tend)}</span></div>"
            f"<svg class='spark' data-tf='{iv}' viewBox='0 0 200 56' preserveAspectRatio='none'>"
            f"<text x='6' y='32' class='tag'>cargando…</text></svg>"
            f"{rbar}<div class='tmeta'>RSI {_esc(rsi)} · MACD {mar}</div></div>")
    if not bloques:
        return ""
    return (f"<div class='tfgrid'>{''.join(bloques)}</div>"
            f"<p class='mini'>Curvas en vivo (Binance) · RSI/MACD del último parte.</p>")


TF_JS = ("<script>(function(){try{"          "if(!window.fetch)return;var boxes=document.querySelectorAll('svg.spark[data-tf]');"
          "if(!boxes.length)return;"
          "function col(t){var b=document.body.dataset.bias||'';return b==='ALZA'?'#4ade80':(b==='BAJA'?'#fca5a5':'#f1f5f9');}"
          "boxes.forEach(function(svg){"
          "var iv=svg.dataset.tf;"
          "fetch('https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval='+iv+'&limit=30')"
          ".then(function(r){if(!r.ok)throw 0;return r.json();})"
          ".then(function(kl){"
          "var cs=kl.map(function(k){return parseFloat(k[4]);}).filter(function(x){return x>0;});"
          "if(cs.length<2)throw 0;"
          "var lo=Math.min.apply(null,cs),hi=Math.max.apply(null,cs),rg=(hi-lo)||1;"
          "var pts=cs.map(function(v,i){"
          "return (6+i*(188/(cs.length-1))).toFixed(1)+','+(50-((v-lo)/rg)*44).toFixed(1);}).join(' ');"
          "var c=col();"
          "svg.innerHTML='<polyline class=\"sline\" points=\"'+pts+'\" stroke=\"'+c+'\"/>';"
          "var last=cs[cs.length-1];"
          "var lx=194,ly=50-((last-lo)/rg)*44;"
          "svg.innerHTML+='<circle cx=\"'+lx.toFixed(1)+'\" cy=\"'+ly.toFixed(1)+'\" r=\"3\" fill=\"'+c+'\"/>';"
          "}).catch(function(){try{svg.style.display='none';}catch(e){}});"
          "});}catch(e){}})();</script>")

SALA_JS = ("<script>(function(){try{"
           "var cv=document.getElementById('salaCanvas');if(!cv||!cv.getContext)return;"
           "var x=cv.getContext('2d');var ds=document.body.dataset;"
           "function num(k,d){var v=parseFloat(ds[k]);return (v>0&&isFinite(v))?v:d;}"
           "var bias=ds.bias||'?';var conf=ds.conf||'?';"
           "var RES=num('res',82500),SOP=num('sop',80500),BAN=num('banco',74.33);"
           "var MOT=(ds.motivo||'').slice(0,60);var DEMO=!ds.res;"
           "var MEM={};try{MEM=JSON.parse(ds.mem||'{}')}catch(e){MEM={};}"
           "function ficha(n){try{var m=MEM[String(Math.round(n))];if(m&&(m.hold+m.rompe)>0)return 'aguanta '+m.hold+'/'+(m.hold+m.rompe);}catch(e){}return 'zona nueva';}"
           "var W=cv.width,H=cv.height;function ISO(u){var S2=60;return {x:W/2+(u.x-u.y)*0.86*S2,y:H*0.44+(u.x+u.y)*0.5*S2-u.z*S2};}"
           "var DK=[{x:0,y:0,r:'TEN'},{x:2.2,y:0,r:'TEC'},{x:4.4,y:0,r:'PIS'},{x:0,y:2.4,r:'MSJ'},{x:2.2,y:2.4,r:'SOM'},{x:4.4,y:2.4,r:'PAP'}];"
           "function val(r){if(r==='TEN')return String(bias)+' '+(conf||'?');if(r==='TEC')return Math.round(RES);if(r==='PIS')return Math.round(SOP);if(r==='PAP')return BAN.toFixed(2);if(r==='MSJ')return MOT?('“'+MOT.slice(0,18)+'”'):'···';return '···';}"
           "var BT=[];for(var i=0;i<6;i++)BT.push({r:DK[i].r,d:i,u:{x:DK[i].x+0.5,y:DK[i].y+1.4},t:{x:Math.random()*6.8,y:Math.random()*4},sp:.02+Math.random()*.015,esp:i*0.4,lleva:false,fr:'',dic:0});"
           "var ND=[];for(var n=0;n<30;n++)ND.push({x:.04+Math.random()*.92,y:.06+Math.random()*.86,vx:(Math.random()-.5)*.0006,vy:(Math.random()-.5)*.0004});"
           "var PU=[{a:0,b:1,t:0},{a:3,b:5,t:.4},{a:6,b:9,t:.7},{a:10,b:14,t:.2}];var POL=[];for(var p=0;p<24;p++)POL.push({x:Math.random(),y:Math.random()});"
           "var lT=0;"
           "function fr(){"
           "var t=performance.now();var s=t/1000;var dt=Math.min(.05,(t-(lT||t))/1000)||.016;lT=t;var K=dt*60;"
           "x.fillStyle='#020304';x.fillRect(0,0,W,H);"
           "for(var q=0;q<POL.length;q++){var g=POL[q];g.y-=0.0004*K;if(g.y<0){g.y=1;g.x=Math.random();}x.fillStyle='rgba(240,240,240,.25)';x.fillRect(g.x*W,g.y*H,1.5,1.5);}"
           "x.fillStyle='#f0f0f0';x.font='11px monospace';"
           "x.fillText('TECHO '+Math.round(RES)+' '+ficha(RES),10,16);"
           "x.fillText('PISO '+Math.round(SOP)+' '+ficha(SOP),10,30);"
           "x.fillStyle='#aab0bb';x.fillText(String(bias)+' '+(conf||'?')+(DEMO?' · DEMO':' · NUBE'),10,44);"
           "/* constelación a toda la tarjeta */"
           "var NC=[];for(var m=0;m<ND.length;m++){var nn=ND[m];nn.x+=nn.vx*K;nn.y+=nn.vy*K;if(nn.x<.03||nn.x>.97)nn.vx*=-1;if(nn.y<.04||nn.y>.94)nn.vy*=-1;NC.push({x:nn.x*W,y:nn.y*H});}"
           "for(var a=0;a<NC.length;a++)for(var b=0;b<NC.length;b++){if(b<=a)continue;var dx=NC[a].x-NC[b].x,dy=NC[a].y-NC[b].y,d=Math.sqrt(dx*dx+dy*dy);if(d<150){x.strokeStyle='rgba(240,240,240,'+(0.35*(1-d/150))+')';x.beginPath();x.moveTo(NC[a].x,NC[a].y);x.lineTo(NC[b].x,NC[b].y);x.stroke();}}"
           "for(var k=0;k<NC.length;k++){x.fillStyle='#f0f0f0';x.beginPath();x.arc(NC[k].x,NC[k].y,2.4,0,7);x.fill();}"
           "var BOOM=false;try{BOOM=(Date.now()-(window.__upload||0)<4000);}catch(e){BOOM=false;}"
           "for(var u=0;u<PU.length;u++){var pp=PU[u];pp.t+=0.008*K*(BOOM?4:1);if(pp.t>1){pp.t=0;}var A=NC[pp.a%NC.length],B=NC[pp.b%NC.length];if(A&&B){var qx=A.x+(B.x-A.x)*pp.t,qy=A.y+(B.y-A.y)*pp.t;x.fillStyle='#fff';x.beginPath();x.arc(qx,qy,3,0,7);x.fill();}}"
           "var ANCH=[['TECHO '+Math.round(RES)+' · '+ficha(RES),.08,.12],['SESGO '+String(bias)+' '+(conf||'?'),.08,.5],['PISO '+Math.round(SOP)+' · '+ficha(SOP),.08,.88]];"
           "for(var an2=0;an2<ANCH.length;an2++){var ax=ANCH[an2][1]*W,ay2=ANCH[an2][2]*H;"
           "x.strokeStyle='#fff';x.beginPath();x.arc(ax,ay2,10+Math.sin(s*3+an2)*2,0,7);x.stroke();"
           "x.fillStyle='#fff';x.beginPath();x.arc(ax,ay2,4,0,7);x.fill();"
           "x.fillStyle='#f0f0f0';x.font='11px monospace';x.fillText(ANCH[an2][0],ax+18,ay2+4);}"
           "requestAnimationFrame(fr);}"
           "try{requestAnimationFrame(fr);}catch(e){}}catch(e){}"
           "})();</script>")

IDLE_JS = ("<script>(function(){try{"
           "var ds=document.body.dataset;var crew=document.getElementById('crew');"
           "var conf=parseFloat(ds.conf)||0;"
           "var mood='normal';"
           "if(ds.grade==='A')mood='alerta';"
           "else if(conf>=55)mood='bien';"
           "else if(ds.bias==='LATERAL'&&conf<25)mood='bajo';"
           "if(crew)crew.dataset.mood=mood;"
           "var jobs={TEN:'mide sesgo '+ds.bias,TEC:'vigila techo '+ds.res,PIS:'cuida piso '+ds.sop,MSJ:'lleva '+(ds.motivo||'el parte'),SOM:'junta evals',PAP:'cuida '+ds.banco};"
           "if(crew){var bs=crew.querySelectorAll('.bot');var ks=['TEN','TEC','PIS','MSJ','SOM','PAP'];"
           "for(var i=0;i<bs.length&&i<ks.length;i++){bs[i].title=ks[i]+': '+jobs[ks[i]];}}"
           "}catch(e){}})();</script>")

FREE_JS = r"""<script>
// FREE_JS rewrite legible (bots libres).
// Origen: dashboard.py FREE_JS (~1254-1325). Solo lectura, sin editar dashboard.py.
// Features conservadas: 10 bots con oficio, 7 estados, portales ETH/SOL/BNB
// con precio Binance, charla al cruzarse, anarquía ~50s, entrega a #c-sala
// con window.__upload, forma distinta por rol.
// Reglas: funciones pequeñas, sin minificar, DOM con guardas,
// requestAnimationFrame con agenda-previa (inmortal), dt normalizado.
(function () {
  'use strict';

  try {
    // 0. Respeto a movimiento reducido: no animar nada.
    if (
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }

    // ---- Configuración -------------------------------------------------
    var UP_ID = 'c-sala'; // tarjeta de entrega
    var ANARCHY_EVERY = 50; // segundos entre anarquías
    var ANARCHY_LASTS = 8; // segundos que dura el x2.2
    var ANARCHY_SPEED = 2.2; // multiplicador durante anarquía
    var CHAT_DIST2 = 3600; // 60px al cuadrado: distancia de charla
    var CHAT_COOLDOWN = 20; // segundos de silencio tras charlar
    var SPEED_GO = 230; // px/s hacia tarjeta
    var SPEED_PORTAL = 260; // px/s hacia portal
    var SPEED_STROLL = 200; // px/s de paseo
    var SPEED_UP = 260; // px/s hacia sala

    // Oficio de cada bot + tarjetas que visita.
    var JOBS = [
      { r: 'TEN', cards: ['c-conf', 'c-hero'] },
      { r: 'TEC', cards: ['c-porque', 'c-tfs'] },
      { r: 'PIS', cards: ['c-tfs', 'c-porque'] },
      { r: 'MSJ', cards: ['c-alertas', 'c-seg'] },
      { r: 'SOM', cards: ['c-sombra', 'c-prec'] },
      { r: 'PAP', cards: ['c-banco', 'c-kpis'] },
      { r: 'ETH', cards: ['c-macro', 'c-ctx'] },
      { r: 'SOL', cards: ['c-dom', 'c-liqmap'] },
      { r: 'BNB', cards: ['c-macro', 'c-calib'] },
      { r: 'ECO', cards: ['c-alertas', 'c-banco'] }
    ];

    // Forma visual distinta por rol (border-radius del cuerpo).
    var SHAPES = {
      TEN: '50%',
      TEC: '30%',
      PIS: '50%',
      MSJ: '8px',
      SOM: '50%',
      PAP: '4px',
      ETH: '50% 50% 4px 4px',
      SOL: '4px 4px 50% 50%',
      BNB: '50%',
      ECO: '30%'
    };

    // Portales a la derecha, uno por moneda escrutada.
    var PORTS = [
      { sym: 'ETHUSDT', tag: 'ETH' },
      { sym: 'SOLUSDT', tag: 'SOL' },
      { sym: 'BNBUSDT', tag: 'BNB' }
    ];

    var SCOUTS = { ETH: true, SOL: true, BNB: true }; // roles que usan portales
    var CREW_ORDER = ['TEN', 'TEC', 'PIS', 'MSJ', 'SOM', 'PAP']; // orden en #crew

    // ---- Utilidades DOM con guardas ------------------------------------
    function byId(id) {
      try {
        return document.getElementById(id) || null;
      } catch (e) {
        return null;
      }
    }

    function query(sel, root) {
      try {
        var base = root || document;
        if (!base || !base.querySelector) {
          return null;
        }
        return base.querySelector(sel) || null;
      } catch (e) {
        return null;
      }
    }

    function queryAll(sel, root) {
      try {
        var base = root || document;
        if (!base || !base.querySelectorAll) {
          return [];
        }
        return base.querySelectorAll(sel) || [];
      } catch (e) {
        return [];
      }
    }

    function viewW() {
      try {
        return window.innerWidth || 800;
      } catch (e) {
        return 800;
      }
    }

    function viewH() {
      try {
        return window.innerHeight || 600;
      } catch (e) {
        return 600;
      }
    }

    function scrollX() {
      try {
        return window.scrollX || window.pageXOffset || 0;
      } catch (e) {
        return 0;
      }
    }

    function scrollY() {
      try {
        return window.scrollY || window.pageYOffset || 0;
      } catch (e) {
        return 0;
      }
    }

    // Centro de una tarjeta en coords de página. Null si no visible.
    // Con caché de 500ms: getBoundingClientRect por frame = lag.
    var RCC = { t: 0, m: {} };
    try {
      window.addEventListener('scroll', function () { RCC = { t: 0, m: {} }; }, { passive: true });
    } catch (e) {}
    function cardCenter(id) {
      try {
        var now = Date.now();
        if (now - RCC.t > 500) { RCC = { t: now, m: {} }; }
        if (RCC.m[id]) { return RCC.m[id]; }
        var el = byId(id);
        if (!el || !el.getBoundingClientRect) {
          return null;
        }
        var r = el.getBoundingClientRect();
        if (!r || r.width < 40 || r.height < 30) {
          return null;
        }
        var o = {
          x: r.left + r.width / 2 + scrollX(),
          y: r.top + 80 + scrollY()
        };
        RCC.m[id] = o;
        return o;
      } catch (e) {
        return null;
      }
    }

    // Primeras palabras de una tarjeta, para llevar en la mano.
    function cardText(id) {
      try {
        var el = byId(id);
        if (!el) {
          return '';
        }
        var inner = query('.cinner', el) || el;
        var t = '';
        try {
          t = inner.innerText || '';
        } catch (e) {
          t = '';
        }
        return t.replace(/\s+/g, ' ').trim().slice(0, 64);
      } catch (e) {
        return '';
      }
    }

    // ---- Creación de actores -------------------------------------------
    function makeBot(job) {
      var d = null;
      try {
        d = document.createElement('div');
      } catch (e) {
        return null;
      }
      if (!d) {
        return null;
      }
      try {
        d.className = 'freebot';
        d.innerHTML =
          '<div class="cb"></div>' +
          '<span class="lb">' + job.r + '</span>' +
          '<span class="bb"></span>';
      } catch (e) {
        return null;
      }
      try {
        document.body.appendChild(d);
      } catch (e) {
        return null;
      }
      // Forma distinta por rol, con guarda.
      try {
        var body = query('.cb', d);
        if (body && SHAPES[job.r]) {
          body.style.borderRadius = SHAPES[job.r];
        }
      } catch (e) {
        // decorativo: se ignora
      }
      return {
        r: job.r,
        cards: job.cards,
        el: d,
        bub: query('.bb', d),
        x: Math.random() * viewW(),
        y: scrollY() + viewH() * 0.4 + Math.random() * 200,
        tx: 0,
        ty: 0,
        est: 'ir', // ir|extraer|portal|viaje|paseo|subir|volver
        t: 0, // temporizador del estado actual
        tarea: 0, // índice de tarjeta visitada
        desvio: 0, // 1 si ya paseó (evita paseos encadenados)
        carry: '', // dato en la mano
        chat: 0, // cooldown de conversación
        port: null // portal elegido
      };
    }

    function makePortals() {
      var i;
      for (i = 0; i < PORTS.length; i++) {
        try {
          var pd = document.createElement('div');
          pd.className = 'portal';
          pd.textContent = PORTS[i].tag;
          pd.style.top = 140 + i * 220 + 'px';
          document.body.appendChild(pd);
          PORTS[i].el = pd;
        } catch (e) {
          PORTS[i].el = null;
        }
      }
    }

    // ---- Diálogo (bocadillo) --------------------------------------------
    function habla(b, txt, cls) {
      if (!b || !b.el) {
        return;
      }
      try {
        if (b.bub) {
          b.bub.textContent = txt;
        }
        b.el.classList.add('work');
        if (cls) {
          b.el.classList.add(cls);
        }
      } catch (e) {
        // decorativo
      }
    }

    function calla(b) {
      if (!b || !b.el) {
        return;
      }
      try {
        b.el.classList.remove('work');
        b.el.classList.remove('up');
      } catch (e) {
        // decorativo
      }
    }

    // ---- Precio real de Binance para el portal --------------------------
    function precioPortal(sym, cb) {
      try {
        fetch(
          'https://data-api.binance.vision/api/v3/ticker/price?symbol=' + sym
        )
          .then(function (r) {
            return r.json();
          })
          .then(function (j) {
            var p = parseFloat(j && j.price);
            cb(p > 0 ? p : null);
          })
          .catch(function () {
            cb(null);
          });
      } catch (e) {
        cb(null);
      }
    }

    function formatPrice(p) {
      try {
        return p.toLocaleString('es-CO', { maximumFractionDigits: 2 });
      } catch (e) {
        return String(p);
      }
    }

    // ---- Movimiento ------------------------------------------------------
    // Avanza hacia (tx,ty) hasta speed*dt. Devuelve true si llegó.
    function stepToward(b, tx, ty, speed, dt) {
      var dx = tx - b.x;
      var dy = ty - b.y;
      var dd = Math.sqrt(dx * dx + dy * dy);
      if (dd < 1e-6) {
        return true;
      }
      var step = Math.min(speed * dt, dd);
      b.x += (dx / dd) * step;
      b.y += (dy / dd) * step;
      return step >= dd - 1e-9;
    }

    function flashCard(id) {
      var card = byId(id);
      if (!card) {
        return;
      }
      try {
        card.classList.add('extract');
        setTimeout(function () {
          try {
            card.classList.remove('extract');
          } catch (e) {
            // el nodo pudo desaparecer
          }
        }, 1200);
      } catch (e) {
        // decorativo
      }
    }

    // ---- Estados (uno por función pequeña) -------------------------------
    function tickIr(b, dt, mul) {
      var id = b.cards[b.tarea % b.cards.length];
      var p = cardCenter(id);
      if (!p) {
        // Tarjeta ausente: probar la siguiente, luego rendirse a 'subir'.
        b.tarea++;
        if (b.tarea > b.cards.length + 1) {
          b.tarea = 0;
          b.est = 'subir';
        }
        return;
      }
      var dx = p.x - b.x;
      var dy = p.y - b.y;
      var dd = Math.sqrt(dx * dx + dy * dy);
      if (dd < 24) {
        b.est = 'extraer';
        b.t = 1.4;
        b.carry = cardText(id);
        flashCard(id);
        habla(b, b.r + ': ' + cardText(id));
        return;
      }
      stepToward(b, p.x, p.y, SPEED_GO * mul, dt);
    }

    function tickExtraer(b, dt) {
      b.t -= dt;
      if (b.t > 0) {
        return;
      }
      calla(b);
      b.tarea++;
      if (SCOUTS[b.r] && Math.random() < 0.4) {
        // Explorador: a veces cruza un portal antes de subir.
        b.est = 'portal';
        b.port = PORTS[Math.floor(Math.random() * PORTS.length)];
      } else if (b.desvio <= 0 && Math.random() < 0.25) {
        // Paseo ocasional, solo si no se desvió recién.
        b.desvio = 1;
        b.est = 'paseo';
        b.tx = Math.random() * viewW();
        b.ty = scrollY() + Math.random() * viewH();
      } else {
        b.desvio = 0;
        // Cada 3 tareas sube directo; si no, sigue rondando.
        b.est = b.tarea % 3 === 2 ? 'subir' : 'ir';
      }
    }

    function tickPortal(b, dt, mul) {
      if (!b.port) {
        b.est = 'subir';
        return;
      }
      var idx = PORTS.indexOf(b.port);
      var px = viewW() - 32 + scrollX();
      var py = 140 + (idx < 0 ? 0 : idx) * 220 + scrollY();
      var dx = px - b.x;
      var dy = py - b.y;
      var dd = Math.sqrt(dx * dx + dy * dy);
      if (dd < 30) {
        // Entra al portal: se oculta 3s y trae el precio real.
        b.est = 'viaje';
        b.t = 3;
        try {
          b.el.style.display = 'none';
        } catch (e) {
          // decorativo
        }
        habla(b, b.r + ': ¡entro al portal ' + b.port.tag + '!');
        (function (bb, pp) {
          precioPortal(pp.sym, function (p) {
            try {
              bb.el.style.display = '';
            } catch (e) {
              // decorativo
            }
            bb.carry = pp.tag + ' ' + (p ? formatPrice(p) : 's/d');
            bb.est = 'subir';
          });
        })(b, b.port);
        return;
      }
      stepToward(b, px, py, SPEED_PORTAL * mul, dt);
    }

    function tickViaje(b, dt) {
      // Salvavidas: si el fetch tardó, reaparece con lo que tenga.
      b.t -= dt;
      if (b.t <= 0 && b.est === 'viaje') {
        try {
          b.el.style.display = '';
        } catch (e) {
          // decorativo
        }
        b.carry = b.carry || 'nada';
        b.est = 'subir';
      }
    }

    function tickPaseo(b, dt, mul) {
      var dx = b.tx - b.x;
      var dy = b.ty - b.y;
      var dd = Math.sqrt(dx * dx + dy * dy);
      if (dd < 24) {
        b.est = 'ir';
        return;
      }
      stepToward(b, b.tx, b.ty, SPEED_STROLL * mul, dt);
    }

    // Dónde entregar: #c-sala, o cabecera, o centro arriba.
    function uploadPoint() {
      var u = cardCenter(UP_ID);
      if (u) {
        return u;
      }
      try {
        var h = query('header');
        var sy = scrollY();
        if (h && h.getBoundingClientRect) {
          var hr = h.getBoundingClientRect();
          return {
            x: hr.left + hr.width / 2 + scrollX(),
            y: hr.bottom + 40 + sy
          };
        }
      } catch (e) {
        // sigue al fallback
      }
      return { x: viewW() / 2, y: 120 + scrollY() };
    }

    function markUpload() {
      try {
        window.__upload = Date.now();
      } catch (e) {
        // no crítico
      }
    }

    function paintSala(b) {
      try {
        var sm = query('#c-sala .cinner p.mini');
        if (sm) {
          if (!sm.dataset.orig) {
            sm.dataset.orig = sm.textContent;
          }
          sm.textContent = '✸ ' + b.r + ' aportó: ' + (b.carry || 'dato');
        }
      } catch (e) {
        // decorativo
      }
    }

    function paintCrew(b) {
      try {
        var btns = queryAll('#crew .bot');
        var ki = CREW_ORDER.indexOf(b.r);
        if (ki >= 0 && btns && btns[ki]) {
          btns[ki].title = b.r + ': ' + (b.carry || ' dato entregado');
          var cuerpo = query('.cuerpo', btns[ki]);
          if (cuerpo) {
            cuerpo.style.boxShadow = '0 0 18px #ffffff88';
          }
        }
      } catch (e) {
        // decorativo
      }
    }

    function tickSubir(b, dt, mul) {
      var u = uploadPoint();
      var dx = u.x - b.x;
      var dy = u.y - b.y;
      var dd = Math.sqrt(dx * dx + dy * dy);
      if (dd < 40) {
        markUpload();
        paintSala(b);
        paintCrew(b);
        habla(b, b.r + ': ¡entregado a la cuadrilla!', 'up');
        b.est = 'volver';
        b.t = 1.6;
        return;
      }
      stepToward(b, u.x, u.y, SPEED_UP * mul, dt);
    }

    function tickVolver(b, dt) {
      b.t -= dt;
      if (b.t <= 0) {
        calla(b);
        b.est = 'ir';
      }
    }

    function placeBot(b) {
      if (!b || !b.el) {
        return;
      }
      try {
        b.el.style.transform = 'translate(' + (b.x - 15) + 'px,' + b.y + 'px)';
      } catch (e) {
        // decorativo
      }
    }

    // ---- Eventos globales --------------------------------------------------
    function tickAnarchy(bots, dt, state) {
      state.clock += dt;
      if (state.clock > ANARCHY_EVERY) {
        var i;
        state.clock = 0;
        state.power = ANARCHY_LASTS;
        for (i = 0; i < bots.length; i++) {
          habla(bots[i], '¡ANARQUÍA!');
        }
      }
      if (state.power > 0) {
        state.power -= dt;
      }
    }

    function speedMul(state) {
      return state.power > 0 ? ANARCHY_SPEED : 1;
    }

    // Dos bots que se cruzan conversan; ECO copia lo que oye.
    function tickChats(bots, dt) {
      var i;
      var j;
      for (i = 0; i < bots.length; i++) {
        for (j = i + 1; j < bots.length; j++) {
          var a = bots[i];
          var b = bots[j];
          if (a.chat > 0) {
            a.chat -= dt;
          }
          if (b.chat > 0) {
            b.chat -= dt;
          }
          var gx = a.x - b.x;
          var gy = a.y - b.y;
          if (gx * gx + gy * gy < CHAT_DIST2 && a.chat <= 0 && b.chat <= 0) {
            a.chat = CHAT_COOLDOWN;
            b.chat = CHAT_COOLDOWN;
            var info = b.carry || cardText(b.cards[0]) || 'nada nuevo';
            habla(a, a.r + ': ¿qué sabes?');
            habla(b, b.r + ': ' + String(info).slice(0, 48));
            if (a.r === 'ECO') {
              a.carry = info;
            }
          }
        }
      }
    }

    // ---- Arranque -----------------------------------------------------------
    var bots = [];
    var k;
    for (k = 0; k < JOBS.length; k++) {
      var made = makeBot(JOBS[k]);
      if (made) {
        bots.push(made);
      }
    }
    if (bots.length === 0) {
      return;
    }
    makePortals();

    var state = { clock: 0, power: 0 };
    var lastT = 0;

    // Bucle inmortal: agenda-previa primero, cuerpo con guarda, dt normalizado.
    function fr(t) {
      // Agenda-previa: el próximo frame queda pedido aunque esto falle.
      try {
        requestAnimationFrame(fr);
      } catch (e) {
        // sin rAF no hay animación; se sale sin romper la página
        return;
      }
      try {
        var now = typeof t === 'number' ? t : 0;
        // dt en segundos, recortado a 50ms; k = factor a 60fps.
        var dt = Math.min(0.05, (now - (lastT || now)) / 1000) || 0.016;
        lastT = now;

        tickAnarchy(bots, dt, state);
        var mul = speedMul(state);

        var i;
        for (i = 0; i < bots.length; i++) {
          var b = bots[i];
          if (!b || !b.el) {
            continue;
          }
          if (b.est === 'ir') {
            tickIr(b, dt, mul);
          } else if (b.est === 'extraer') {
            tickExtraer(b, dt);
          } else if (b.est === 'portal') {
            tickPortal(b, dt, mul);
          } else if (b.est === 'viaje') {
            tickViaje(b, dt);
          } else if (b.est === 'paseo') {
            tickPaseo(b, dt, mul);
          } else if (b.est === 'subir') {
            tickSubir(b, dt, mul);
          } else if (b.est === 'volver') {
            tickVolver(b, dt);
          } else {
            // Estado desconocido: vuelve a rondar en vez de atascarse.
            b.est = 'ir';
          }
          placeBot(b);
        }

        tickChats(bots, dt);
      } catch (e) {
        // Un frame malo no mata el bucle: el siguiente ya está agendado.
      }
    }

    try {
      requestAnimationFrame(fr);
    } catch (e) {
      // sin rAF no se anima, pero la página sigue viva
    }
  } catch (e) {
    // Fallo de arranque: nunca romper la página.
  }
})();

</script>"""

VIVO_JS = ("<script>(function(){try{"
          "var el=document.getElementById('pvivo');if(!el)return;"
          "var ant=0,cur=0,tmr=0;"
          "function fmt(x){try{return Number(x).toLocaleString('de-DE',{maximumFractionDigits:0});}catch(e){return x;}}"
          "function tic(){fetch('https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT')"
          ".then(function(r){if(!r.ok)throw 0;return r.json();})"
          ".then(function(j){var p=parseFloat(j.price);if(!(p>0))throw 0;"
          "if(tmr)clearInterval(tmr);"
          "if(cur>0&&cur!==p){var d=p-cur,k=0;tmr=setInterval(function(){k++;cur=cur+d/8;"
          "el.textContent=fmt(Math.round(cur));"
          "if(k>=8){cur=p;el.textContent=fmt(p);clearInterval(tmr);tmr=0;}},60);}"
          "else{cur=p;el.textContent=fmt(p);}"
          "if(ant>0){el.className=p>ant?'sub':(p<ant?'baj':'');}"
          "ant=p;}).catch(function(){});}"
          "try{tic();}catch(e){}setInterval(function(){try{if(!document.hidden)tic();}catch(e){}},10000);"
          "var ed=document.getElementById('edad');"
          "if(ed&&ed.dataset&&ed.dataset.t){var t0=new Date(ed.dataset.t).getTime();"
          "function ve(){var s=Math.max(0,Math.floor((Date.now()-t0)/1000));"
          "var m=Math.floor(s/60);ed.textContent=m>0?(m+' min '+('0'+(s%60)).slice(-2)+' s'):(s+' s');}"
          "try{ve();}catch(e){}setInterval(function(){try{ve();}catch(e){}},1000);}}catch(e){}"
          "})();</script>")

FONDO_JS = ("<script>(function(){"
          "var cv=document.getElementById('fondo');if(!cv||!cv.getContext)return;"
          "var ctx=cv.getContext('2d');"
          "var quiet=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
          "var raw=(document.body.dataset.px||'').split(',');"
          "var px=raw.map(function(x){return parseFloat(x);}).filter(function(x){return x>0;});"
          "var bias=document.body.dataset.bias||'?';"
          "var conf=document.body.dataset.conf||'?';"
          "var run=document.body.dataset.run||'?';var _al='?',_gr='?';try{_al=document.body.dataset.alertas||'?';_gr=document.body.dataset.grade||'?';}catch(e){}"
          "function size(){var d=Math.min(window.devicePixelRatio||1,1.5);"
          "cv.width=Math.floor(innerWidth*d);cv.height=Math.floor(innerHeight*d);"
          "cv.style.width=innerWidth+'px';cv.style.height=innerHeight+'px';"
          "ctx.setTransform(d,0,0,d,0,0);}"
          "size();window.addEventListener('resize',size);"
          "var W=function(){return innerWidth;},H=function(){return innerHeight;};"
          "function grid(){ctx.strokeStyle='rgba(148,163,184,0.05)';ctx.lineWidth=1;ctx.beginPath();"
          "for(var x=0;x<W();x+=56){ctx.moveTo(x+.5,0);ctx.lineTo(x+.5,H());}"
          "for(var y=0;y<H();y+=56){ctx.moveTo(0,y+.5);ctx.lineTo(W(),y+.5);}"
          "ctx.stroke();}"
          "function linea(){if(px.length<2)return;"
          "var bb=document.body.dataset.bias||'';"
          "ctx.strokeStyle=bb==='ALZA'?'rgba(74,222,128,0.12)':(bb==='BAJA'?'rgba(248,113,113,0.12)':'rgba(226,232,240,0.12)');"
          "var lo=Math.min.apply(null,px),hi=Math.max.apply(null,px),rg=(hi-lo)||1;"
          "ctx.lineWidth=1.2;ctx.beginPath();"
          "px.forEach(function(v,i){"
          "var x=20+i*((W()-40)/(px.length-1)),y=H()*0.32+(1-(v-lo)/rg)*H()*0.30;"
          "if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});"
          "ctx.stroke();return {lo:lo,rg:rg};}"
          "function punto(m,t){if(px.length<2||!m)return;"
          "var i=Math.floor(t/40)%px.length;"
          "var v=px[i];var x=20+i*((W()-40)/(px.length-1));"
          "var y=H()*0.32+(1-(v-m.lo)/m.rg)*H()*0.30;"
          "var p=(t%1200)/1200;"
          "ctx.fillStyle='rgba(125,211,252,'+(0.10+0.10*Math.sin(p*6.28))+')';"
          "ctx.beginPath();ctx.arc(x,y,2.5+p*5,0,6.29);ctx.fill();"
          "ctx.fillStyle='rgba(224,242,254,0.20)';"
          "ctx.beginPath();ctx.arc(x,y,2,0,6.29);ctx.fill();}"
          "var msgs=[bias+' '+conf+'% · G'+_gr,'run '+run+' · '+_al+' al','BTCUSDT'];"
          "function textos(t){ctx.font='12px ui-monospace,monospace';"
          "msgs.forEach(function(m,i){"
          "var sp=H()+80;"
          "var y=(sp-((t*0.02+i*sp/3)%sp))%sp-40;"
          "var x=W()*0.08+i*W()*0.28;"
          "ctx.fillStyle='rgba(226,232,240,0.055)';"
          "ctx.fillText(m,x,y);});}"
          "function frame(t){if(document.hidden){requestAnimationFrame(frame);return;}"
          "ctx.clearRect(0,0,W(),H());grid();var m=linea();punto(m,t);textos(t);"
          "try{var _so2=true;try{_so2=localStorage.getItem('vig_sound')!=='1';}catch(e){}if(quiet||_so2){}else if(!document.hidden){setTimeout(function(){try{requestAnimationFrame(frame);}catch(e){}},500);}}catch(e){}}"
          "frame(0);})();</script>")


def presion_dia(hist, hoy):
    """Medidor honesto del día: alertas bajistas vs alcistas (por texto).
    No predice: resume hacia dónde empujaron los avisos."""
    try:
        bj = al = 0
        for h in hist or []:
            if not isinstance(h, dict) or h.get("tipo") != "alerta":
                continue
            if str(h.get("t", ""))[:10] != hoy:
                continue
            m = str(h.get("motivo", ""))
            if "BAJISTA" in m or "PISO" in m or "bajo mínimos" in m or "Ritmo acelerado -" in m:
                bj += 1
            elif "ALCISTA" in m or "TECHO" in m or "sobre máximos" in m or "Ritmo acelerado +" in m:
                al += 1
        return {"bajistas": bj, "alcistas": al}
    except Exception:
        return {"bajistas": 0, "alcistas": 0}


def _alertas_html(est, hist, ahora_dt=None):
    COOL_H = {"fuerte": 4, "brusco": 2, "liq": 4, "ritmo": 2, "toque": 4, "diadc": 24, "ruptura": 12}
    sil = []
    try:
        cools = (est or {}).get("cools") or {}
        if isinstance(cools, dict) and ahora_dt is not None:
            for k, t0 in cools.items():
                try:
                    cat, resto = str(k).split(":", 1)
                    hh = COOL_H.get(cat)
                    if hh is None:
                        continue
                    t0d = datetime.datetime.fromisoformat(t0)
                    if t0d.tzinfo is None:
                        t0d = t0d.replace(tzinfo=datetime.timezone.utc)
                    fin = t0d + datetime.timedelta(hours=hh)
                    if fin > ahora_dt:
                        txt = resto
                        if cat == "ruptura" and txt.startswith("ruptura"):
                            txt = txt[len("ruptura"):].strip()
                        sil.append(f"{cat} {txt} → hasta {fin.strftime('%H:%M')}")
                except Exception:
                    continue
    except Exception:
        pass
    als = [h for h in (hist or []) if isinstance(h, dict) and h.get("tipo") == "alerta"]
    sils = ""
    if sil:
        vis = "; ".join(sil[:3])
        mas = f" (+{len(sil) - 3} más)" if len(sil) > 3 else ""
        sils = f"<p class='mini' title='{_esc('; '.join(sil))}'>Silenciados: {_esc(vis)}{mas}</p>"
    try:
        hoy = (ahora_dt.strftime("%Y-%m-%d") if ahora_dt is not None
               else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"))
        pr = presion_dia(hist, hoy)
        pres_txt = (f"<p class='mini'>Presión del día: {pr['bajistas']} bajistas / {pr['alcistas']} alcistas</p>"
                    if (pr["bajistas"] + pr["alcistas"]) > 0 else "")
    except Exception:
        pres_txt = ""
    if not als:
        return (f"<p class='mini'>Sin alertas en ventana — el bot sólo avisa con cambio real, "
                f"no cada pasada.</p>{sils}")
    filas = ""
    for h in reversed(als[-8:]):
        try:
            ft = str(h.get("t", ""))[5:16].replace("T", " ")
        except Exception:
            ft = "?"
        b = str(h.get("bias", "?")).upper()
        cls = "alza" if b == "ALZA" else ("baja" if b == "BAJA" else "lateral")
        mot = str(h.get("motivo", ""))
        corto = (mot[:110] + "…") if len(mot) > 110 else mot
        filas += (f"<tr><td>{ft}</td><td><span class='badge {cls}'>{b}</span></td>"
                  f"<td>{miles(h.get('precio'))}</td><td>{h.get('conf', '?')}%</td>"
                  f"<td title='{_esc(mot)}'>{_esc(corto)}</td></tr>")
    return (f"<div class='tscroll'><table class='ops'><thead><tr><th>Hora</th><th>Sesgo</th><th>Precio</th><th>Conf</th><th>Motivo</th></tr></thead>"
            f"{filas}</table></div><p class='mini'>Últimas {min(len(als), 8)} de {len(als)} en ventana.</p>{sils}{pres_txt}"
            f"<p class='mini' title='TECHO = estás debajo, puede devolver abajo · PISO = estás encima, puede devolver arriba · se anula SOLO con cierre 1H más allá.'>TECHO / PISO: se anulan con cierre 1H más allá.</p>")


def _porque_html(snap):
    if not isinstance(snap, dict) or not snap:
        return ""
    pts = []
    tf = snap.get("tf") or {}
    if isinstance(tf, dict) and tf:
        al = sum(1 for k in ("h1", "h4", "d1", "w1")
                 if isinstance(tf.get(k), dict) and "alci" in str((tf[k] or {}).get("tend", "")).lower())
        bj = sum(1 for k in ("h1", "h4", "d1", "w1")
                 if isinstance(tf.get(k), dict) and "baji" in str((tf[k] or {}).get("tend", "")).lower())
        det = " · ".join(f"{ {'h1': '1H', 'h4': '4H', 'd1': '1D', 'w1': '1S'}[k]} {((tf.get(k) or {}).get('tend', '?'))}"
                            for k in ("h1", "h4", "d1", "w1") if isinstance(tf.get(k), dict))
        pts.append(f"Tendencia: {al} TF alcistas / {bj} bajistas ({det})")
    fg = snap.get("fg") or {}
    senti = snap.get("senti") or {}
    if isinstance(fg, dict) and fg.get("valor") is not None:
        pts.append(f"Sentimiento: miedo {fg.get('valor')} ({fg.get('etiqueta', '')}) · "
                   f"funding {senti.get('funding', 's/d')} · taker {senti.get('taker', 's/d')}")
    pres = snap.get("pres") or {}
    if isinstance(pres, dict) and pres.get("txt"):
        pts.append(f"Noticias: {pres.get('txt')}")
    niv = snap.get("niv") or {}
    try:
        px = float(snap.get("precio") or 0)
        sop = (niv.get("sop") or [{}])[0].get("precio")
        res = (niv.get("res") or [{}])[0].get("precio")
        if px and sop and res:
            pts.append(f"Posición: a {abs(px - float(sop)) / px * 100:.2f}% del soporte "
                       f"y {abs(float(res) - px) / px * 100:.2f}% de la resistencia")
    except Exception:
        pass
    if snap.get("regimen"):
        pts.append(f"Régimen: {snap.get('regimen')} · grado {snap.get('grade', '?')}")
    if not pts:
        return ""
    return "<ul class='pq'>" + "".join(f"<li>{_esc(p)}</li>" for p in pts) + "</ul>"


def _fam(titulo):
    try:
        tl = str(titulo or "").upper()
        for fam, pats in (("CPI", ("CPI", "IPC")), ("PPI", ("PPI",)),
                          ("FOMC", ("FOMC", "POWELL", "TASA", "RATE DECISION")),
                          ("NFP", ("NFP", "NON-FARM", "NOMINAS", "PAYROLL", "EMPLEO")),
                          ("PIB", ("PIB", "GDP")), ("VENTAS", ("VENTAS", "RETAIL"))):
            if any(p in tl for p in pats):
                return fam
        return "OTRO"
    except Exception:
        return "OTRO"


def _dom_html(snap):
    dom = (snap or {}).get("dom") if isinstance(snap, dict) else None
    if not isinstance(dom, dict) or dom.get("btc") is None:
        return ""
    try:
        b = max(0, min(100, float(dom["btc"])))
        e = max(0, min(100, float(dom.get("eth") or 0)))
        col = "#f7931a" if b >= 55 else ("#a78bfa" if b < 48 else "#e2e8f0")
        ver = ("temporada BTC" if b >= 55 else ("zona mixta" if b >= 48 else "aires de altseason"))
        return (f"<div class='big' style='font-size:24px'>{b:.1f}% <small style='font-size:12px;color:#94a3b8'>BTC</small></div>"
                f"<div class='rsibar'><i style='width:{b:.0f}%;background:{col}'></i></div>"
                f"<p class='mini'>{ver} · ETH {e:.1f}% · resto {100 - b - e:.1f}%</p>")
    except Exception:
        return ""


def _liqmap_html(snap):
    lm = (snap or {}).get("liqmap") if isinstance(snap, dict) else None
    if not isinstance(lm, dict):
        return ""

    def lado(lst, color):
        out = []
        for x in (lst or [])[:5]:
            try:
                sc = max(0, min(100, float(x.get("score", 50))))
                out.append(
                    f"<div class='tmeta'>{miles(x.get('precio'))} ({float(x.get('dist', 0)):+.2f}%)</div>"
                    f"<div class='rsibar'><i style='width:{sc:.0f}%;background:{color}'></i></div>")
            except Exception:
                continue
        return "".join(out) or "<p class='mini'>—</p>"

    im = lm.get("iman") or {}
    banner = ""
    try:
        if im.get("lado"):
            banner = (f"<p class='mini'>Imán de stops: <b style='color:#e2e8f0'>{_esc(str(im['lado']).upper())}</b> "
                      f"({_esc(im.get('pct', '?'))}%)</p>")
    except Exception:
        pass
    return (f"{banner}<p class='mini'>Arriba</p>{lado(lm.get('arriba'), '#f87171')}"
            f"<p class='mini'>Abajo</p>{lado(lm.get('abajo'), '#4ade80')}"
            f"<p class='mini'>Estimado: stops tras máximos/mínimos y redondos.</p>")


def _macro_html(snap, ahora_dt):
    if not isinstance(snap, dict):
        return ""
    evs = snap.get("evs") or []
    if not isinstance(evs, list) or not evs:
        return ""
    fut = []
    for e in evs:
        if not isinstance(e, dict):
            continue
        try:
            _cs = e.get("cuando", "")
            if isinstance(_cs, str) and _cs.endswith("Z"):
                _cs = _cs[:-1] + "+00:00"
            cu = datetime.datetime.fromisoformat(_cs)
            if cu.tzinfo is None:
                cu = cu.replace(tzinfo=datetime.timezone.utc)
            if cu >= ahora_dt:
                fut.append((cu, e))
        except Exception:
            continue
    if not fut:
        return ""
    fut.sort(key=lambda x: x[0])
    grupos = []
    for cu, e in fut:
        if grupos and grupos[-1][0] == cu:
            grupos[-1][1].append(e)
        else:
            grupos.append((cu, [e]))
    filas = ""
    for cu, es in grupos[:5]:
        dh = (cu - ahora_dt).total_seconds() / 3600
        cuad = f"en {int(dh)}h {int((dh % 1) * 60)}min" if dh >= 1 else f"en {int(dh * 60)}min"
        imp = "High" if any(str(x.get("impact", "")) == "High" for x in es) else str(es[0].get("impact", "?"))
        cls = "baja" if imp == "High" else "lateral"
        tit = es[0].get("titulo", "?")
        if len(es) > 1:
            tit += f" +{len(es) - 1}"
        full = " · ".join(str(x.get("titulo", "?")) for x in es)
        stu = ""
        try:
            st = (snap.get("evstudy", {}) or {}).get(_fam(es[0].get("titulo", ""))) if snap else None
            if isinstance(st, dict) and st.get("n", 0) >= 3:
                stu = f" suele ±{st['avg']}% (n={st['n']})"
        except Exception:
            pass
        filas += (f"<tr><td>{cu.strftime('%d %H:%M')}</td><td title=\"{_esc(full)}\">{_esc(tit)}{_esc(stu)}</td>"
                  f"<td><span class='badge {cls}'>{_esc(imp)}</span></td><td>{_esc(cuad)}</td></tr>")
    return (f"<table class='ops'><tr><th>Día/hora</th><th>Evento</th><th>Impacto</th><th>Falta</th></tr>"
            f"{filas}</table><p class='mini'>±30 min de eventos High: sin señales (blackout).</p>")


def _duelo_html(snap):
    """Osos (ventas) vs Toros (compras): dos fuerzas INDEPENDIENTES.
    Osos = % ventas en prints de ballenas 5+ BTC. Toros = taker buy/sell
    mapeado 0-100 (50 = parejo). Gana por 15+ con fuerza 40+."""
    if not isinstance(snap, dict):
        return ""
    bal = snap.get("bal") if isinstance(snap.get("bal"), dict) else None
    taker = (snap.get("senti") or {}).get("taker") if isinstance(snap.get("senti"), dict) else None
    po = None
    try:
        if bal and not isinstance(bal.get("buys"), bool) and not isinstance(bal.get("sells"), bool):
            _b = float(bal.get("buys", 0))
            _s = float(bal.get("sells", 0))
            if _b == _b and _s == _s and _b not in (float("inf"), float("-inf")) and _s not in (float("inf"), float("-inf")) and (_b + _s) > 0:
                po = _s / (_b + _s) * 100
    except Exception:
        po = None
    pt = None
    try:
        if taker is not None and not isinstance(taker, bool):
            _t = float(taker)
            if _t == _t and _t not in (float("inf"), float("-inf")):
                pt = max(0, min(100, (_t - 0.7) / 0.6 * 100))
    except Exception:
        pt = None
    if po is None and pt is None:
        dor = ("<div class='fighter dormido'><span class='fmono {c}'>{l}</span>"
               "<div class='zzz'><span>·</span><span>·</span><span>·</span></div>"
               "<div class='fname'>{n} en espera</div></div>")
        return (
            f"<div class='duel'>{dor.format(c='o', l='O', n='Osos')}"
            f"<div class='vs'>VS</div>{dor.format(c='t', l='T', n='Toros')}</div>"
            f"<div class='winbanner'>Nadie en la arena todavía</div>"
            f"<p class='mini'>La cinta de ballenas y el taker aparecen en la próxima pasada.</p>")
    plz = ("<div class='fighter dormido'><span class='fmono {c}'>{l}</span>"
           "<div class='zzz'><span>·</span><span>·</span><span>·</span></div>"
           "<div class='fname'>{n} en espera</div><div class='fpow'>s/d</div></div>")
    if po is None or pt is None:
        dw = ""
        try:
            nb = int(bal.get("nb", 0)) if bal else 0
            ns = int(bal.get("ns", 0)) if bal else 0
        except Exception:
            nb, ns = 0, 0
        if (nb + ns) > 0:
            dw = (f"<div class='tmeta'><span class='loss'>−{bal.get('sells', 0)} BTC en {bal.get('ns', 0)}</span> · "
                  f"<span class='win'>+{bal.get('buys', 0)} BTC en {bal.get('nb', 0)}</span></div>")
        fo = (f"<div class='fighter'><span class='fmono o'>O</span><div class='fname'>Osos</div>"
              f"<div class='fpow'>{po:.0f}</div>"
              f"<div class='rsibar'><i style='width:{po:.0f}%;background:#ef4444'></i></div>{dw}</div>"
              if po is not None else plz.format(c='o', l='O', n='Osos · cinta sin ballenas' if isinstance(bal, dict) else 'Osos'))
        tk = (snap.get("senti") or {}).get("taker") if isinstance(snap.get("senti"), dict) else None
        dt = f"<div class='tmeta'>taker buy/sell {tk if tk is not None else 's/d'}</div>"
        ft = (f"<div class='fighter'><span class='fmono t'>T</span><div class='fname'>Toros</div>"
              f"<div class='fpow'>{pt:.0f}</div>"
              f"<div class='rsibar'><i style='width:{pt:.0f}%;background:#4ade80'></i></div>{dt}</div>"
              if pt is not None else plz.format(c='t', l='T', n='Toros'))
        return (f"<div class='duel'>{fo}<div class='vs'>VS</div>{ft}</div>"
                f"<div class='winbanner'>Esperando al rival</div>"
                f"<p class='mini'>Osos = ventas/(ventas+compras) en prints de 5+ BTC · "
                f"Toros = taker buy/sell (50 = parejo).</p>")
    po_d = po if po is not None else 50
    pt_d = pt if pt is not None else 50
    diff = pt_d - po_d
    twin = diff > 0
    toros_compra = pt_d > 50
    osos_venta = po_d > 50
    if abs(diff) >= 15 and max(po_d, pt_d) >= 40 and ((twin and toros_compra) or (not twin and osos_venta)):
        if twin:
            banner = "VICTORIA DE LOS TOROS — la compra agresiva manda"
        else:
            banner = "VICTORIA DE LOS OSOS — la venta agresiva manda"
        cw, cl = ("loser", "winner") if twin else ("winner", "loser")
    else:
        banner, cw, cl = "Pelea pareja — nadie domina", "", ""
    det_w = ""
    try:
        nb2 = int(bal.get("nb", 0)) if bal else 0
        ns2 = int(bal.get("ns", 0)) if bal else 0
    except Exception:
        nb2, ns2 = 0, 0
    if (nb2 + ns2) > 0:
        det_w = (f"<div class='tmeta'><span class='loss'>−{_esc(bal.get('sells', 0))} BTC en {_esc(bal.get('ns', 0))}</span> · "
                 f"<span class='win'>+{_esc(bal.get('buys', 0))} BTC en {_esc(bal.get('nb', 0))}</span> · max {_esc(bal.get('big', 0))}</div>")
    elif bal:
        det_w = "<div class='tmeta'>sin prints ≥5 BTC en la cinta</div>"
    else:
        det_w = "<div class='tmeta'>cinta de ballenas s/d aún</div>"
    det_t = f"<div class='tmeta'>taker buy/sell {_esc(taker if taker is not None else 's/d')}</div>"
    return (
        f"<div class='duel'>"
        f"<div class='fighter {cw}'><span class='fmono o'>O</span><div class='fname'>Osos</div>"
        f"<div class='fpow'>{po_d:.0f}</div>"
        f"<div class='rsibar'><i style='width:{po_d:.0f}%;background:#ef4444'></i></div>{det_w}</div>"
        f"<div class='vs'>VS</div>"
        f"<div class='fighter {cl}'><span class='fmono t'>T</span><div class='fname'>Toros</div>"
        f"<div class='fpow'>{pt_d:.0f}</div>"
        f"<div class='rsibar'><i style='width:{pt_d:.0f}%;background:#4ade80'></i></div>{det_t}</div>"
        f"</div><div class='winbanner'>{banner}</div>"
        f"<p class='mini'>Osos = ventas en prints de 5+ BTC · "
        f"Toros = taker buy/sell (50 = parejo). Gana por 15+ con fuerza 40+.</p>")


def _saludo(ahora_dt):
    try:
        hb = (ahora_dt - datetime.timedelta(hours=5)).hour
    except Exception:
        return ""
    if 5 <= hb < 12:
        return "Buenos días"
    if 12 <= hb < 19:
        return "Buenas tardes"
    if 19 <= hb or hb < 0:
        return "Buenas noches"
    return "De madrugada"


def _banner_html(est, hist, ahora_dt):
    ult = est.get("ultima_alerta") if isinstance(est.get("ultima_alerta"), dict) else None
    if not ult:
        for h in reversed(hist or []):
            if isinstance(h, dict) and h.get("tipo") == "alerta":
                ult = {"t": h.get("t", ""), "motivo": h.get("motivo", "alerta"),
                       "precio": h.get("precio", 0), "bias": h.get("bias", "?"),
                       "conf": h.get("conf", "?")}
                break
    if not ult:
        return ""
    try:
        t0 = datetime.datetime.fromisoformat(ult.get("t", ""))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        mins = (ahora_dt - t0).total_seconds() / 60
    except Exception:
        return ""
    if not (0 <= mins < 45):
        return ""
    hace = f"hace {int(mins)} min" if mins >= 1 else "hace menos de 1 min"
    b = str(ult.get("bias", "?")).upper()
    cls = "alza" if b == "ALZA" else ("baja" if b == "BAJA" else "lateral")
    return (f"<div class='card flash' id='c-ultima'><div class='cbody'><div class='cinner'>"
            f"<span class='atag'>ALERTA</span><b>Última alerta</b> · {hace} · "
            f"<span class='badge {cls}'>{b} {ult.get('conf', '?')}%</span> "
            f"{miles(ult.get('precio'))} — {_esc(ult.get('motivo', '')[:140])}"
            f"</div></div></div>")


def build_dashboard(est, hist):
    if not isinstance(est, dict):
        est = {}
    if not isinstance(hist, list):
        hist = []
    ahora_dt = datetime.datetime.now(datetime.timezone.utc)
    hay_dato = False
    try:
        dt_data = datetime.datetime.fromisoformat(est.get("ultimo_run", ""))
        if dt_data.tzinfo is None:
            dt_data = dt_data.replace(tzinfo=datetime.timezone.utc)
        hay_dato = True
    except Exception:
        dt_data = ahora_dt
    ahora = dt_data.strftime("%d/%m %H:%M UTC") if hay_dato else "sin datos aún"
    ahora_iso = dt_data.isoformat() if hay_dato else ""
    ult = [h for h in hist[-30:] if isinstance(h, dict)]
    px = [_num(h.get("precio")) for h in ult]
    cf = [h.get("conf", 0) for h in ult]
    marcas = [i for i, h in enumerate(ult) if h.get("tipo") == "alerta"]
    alza = [v for v in (est.get("alza") or []) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))]
    baja = [v for v in (est.get("baja") or []) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))]
    try:
        pa = f"{round(sum(alza) / len(alza) * 100)}% ({int(sum(alza))}/{len(alza)})" if len(alza) >= 5 else "s/d"
    except Exception:
        pa = "s/d"
    try:
        pb = f"{round(sum(baja) / len(baja) * 100)}% ({int(sum(baja))}/{len(baja)})" if len(baja) >= 5 else "s/d"
    except Exception:
        pb = "s/d"
    banco = est.get("banco")
    eq = [100.0]
    for c in est.get("paper_cerradas", []) or []:
        try:
            eq.append(eq[-1] + _num((c or {}).get("pnl", 0), 0))
        except Exception:
            continue
    eq_txt = f"{miles(banco)} USDT" if banco is not None else "100 USDT (sin empezar)"
    bias = _txt(est.get("ultimo_bias"))
    _conf = est.get("ultima_conf")
    conf = _conf if isinstance(_conf, (int, float)) else "?"
    conf_w = max(0, min(100, float(_conf))) if isinstance(_conf, (int, float)) and not isinstance(_conf, bool) and _conf == _conf and _conf not in (float("inf"), float("-inf")) else 0
    precio = _num((ult[-1].get("precio", 0) if ult else 0), 0)
    emp = " · empate total de marcos" if isinstance(_conf, (int, float)) and _conf == 0 and bias == "LATERAL" else ""
    if len(px) >= 2 and px[0]:
        d = px[-1] - px[0]
        dpct = d / px[0] * 100
        delta_txt = f"{'+' if d >= 0 else ''}{miles(d)} ({'+' if dpct >= 0 else ''}{dpct:.2f}%) en ventana"
        rango_txt = f"rango {miles(min(px))} – {miles(max(px))}"
    else:
        delta_txt, rango_txt = "sin ventana aún", ""
    n_alertas = len(marcas)
    ctx = _contexto_html(est.get("snapshot"))
    ops = _ops_html(est, ahora_dt)
    reloj = _gauge_reloj_html(est, ult, ahora_dt)
    nvs, dist_txt = [], ""
    try:
        niv = (est.get("snapshot") or {}).get("niv") or {}
        sops = [s for s in (niv.get("sop") or []) if isinstance(s, dict)][:2]
        ress = [r for r in (niv.get("res") or []) if isinstance(r, dict)][:2]
        for s in sops:
            _n = int(s.get("n") or len(s.get("origenes") or []) or 1)
            _f = f" · {_n} fuentes" if _n >= 2 else ""
            nvs.append({"precio": s.get("precio"), "etiqueta": f"SOP · {s.get('origen', 'soporte')}{_f}", "kind": "sop"})
        for r in ress:
            _n = int(r.get("n") or len(r.get("origenes") or []) or 1)
            _f = f" · {_n} fuentes" if _n >= 2 else ""
            nvs.append({"precio": r.get("precio"), "etiqueta": f"RES · {r.get('origen', 'resistencia')}{_f}", "kind": "res"})
        if precio and sops and ress:
            ds = (precio - float(sops[0].get("precio", precio))) / precio * 100
            dr = (float(ress[0].get("precio", precio)) - precio) / precio * 100
            dist_txt = f" · SOP a −{abs(ds):.2f}% · RES a +{abs(dr):.2f}%"
    except Exception:
        nvs, dist_txt = [], ""
    hero = (f"<div class='big'>{miles(precio)}<span class='badge {_bias_class(bias)}'>{_esc(bias)} {_esc(conf)}%</span></div>"
            f"<div class='pill'><i style='--w:{conf_w}%'></i></div>"
            f"<div class='sub'>{_esc(delta_txt)} · {_esc(rango_txt)} · <span class='cdot'></span>{n_alertas} alertas en ventana{_esc(dist_txt)}{_esc(emp)}</div></div>")
    curva = (f"{svg_linea(px, marcas=marcas, niveles=nvs)}"
             f"<p><span style='color:#4ade80'>─ soporte</span> · "
             f"<span style='color:#fca5a5'>─ resistencia</span> (origen al pasar el mouse).</p>")
    confb = (f"{svg_barras(cf, [str(i) for i in range(len(cf))])}"
             f"<p>Verde ≥55 (fuerte) · ámbar ≥40 · gris debajo. Líneas: 45 registra / 55 fuerte.</p>")
    banco_b = f"<div class='big' style='font-size:22px'>{eq_txt}</div>{svg_linea(eq, color='#22c55e')}"
    prec_b = (f"<p>ALZA {pa} · BAJA {pb}</p>"
              f"<p>EV ALZA {_ev_txt(alza)} · BAJA {_ev_txt(baja)} (plan 2R, rentable sobre 33%)</p>"
              f"{_calib_txt(est.get('eval_log'))}"
              f"<p>Se evalúa a 8h: objetivo 2R antes que stop 1R.</p>")
    try:
        _tiso = est.get("latido") or est.get("ultimo_run")
    except Exception:
        _tiso = None
    try:
        _fest, _ftxt = frescura(_tiso, ahora_dt) if _tiso else ("s/d", "")
    except Exception:
        _fest, _ftxt = ("s/d", "")
    _fuente = f"fuente: {_fest} ({_ftxt})" if _ftxt else "fuente: s/d"
    act_b = (f"<p>{len(hist)} pasadas guardadas · run {_esc(est.get('runs', '?'))}</p>"
             f"<p>Sesión NY 13–20 UTC · avisos sólo con cambio real.</p>"
             f"<p>{_esc(_fuente)}</p>")
    ban = _banner_html(est, ult, ahora_dt)
    tarjetas = []
    if ban:
        tarjetas.append(ban)
    tarjetas.append(_sec("Precio", "s-precio"))
    tarjetas.append(_card("hero", "Precio y sesgo", hero))
    tarjetas.append(_card("curva", f"Precio · últimas {len(px)}", curva))
    tarjetas.append(_card("sala", "Sala viva", _sala_html(est.get("snapshot"), est)))
    tarjetas.append(_sec("Señales", "s-senales"))
    tarjetas.append(_card("alertas", "Alertas", _alertas_html(est, ult, ahora_dt)))
    tarjetas.append(_card("conf", "Confianza (escala 0–100)", confb))
    pq = _porque_html(est.get("snapshot"))
    if pq:
        tarjetas.append(_card("porque", "Por qué este sesgo", pq))
    tarjetas.append(_sec("Mercado", "s-mercado"))
    tfs = _tfs_html(est.get("snapshot"))
    if tfs:
        tarjetas.append(_card("tfs", "Temporalidades", tfs))
    if reloj:
        tarjetas.append(_card("reloj", "Miedo y sesión", reloj))
    if ctx:
        tarjetas.append(_card("ctx", "Contexto", ctx))
    dh = _dom_html(est.get("snapshot"))
    if dh:
        tarjetas.append(_card("dom", "Dominancia", dh))
    lq = _liqmap_html(est.get("snapshot"))
    if lq:
        tarjetas.append(_card("liqmap", "Mapa de liquidez", lq))
    du = _duelo_html(est.get("snapshot"))
    if du:
        tarjetas.append(_card("duelo", "Osos vs Toros", du))
    mc = _macro_html(est.get("snapshot"), ahora_dt)
    if mc:
        tarjetas.append(_card("macro", "Macro · eventos", mc))
    tarjetas.append(_sec("Dinero papel", "s-dinero"))
    tarjetas.append(_card("ops", "Operaciones papel", ops))
    try:
        _seg = _seguimiento_html(est, ahora_dt)
    except Exception:
        _seg = "<p class='mini'>sin pendientes — no hay señales esperando evaluación.</p>"
    tarjetas.append(_card("seg", "En seguimiento", _seg))
    tarjetas.append(_card("banco", "Banco papel", banco_b))
    try:
        _kpis = _kpis_papel_html(est)
    except Exception:
        _kpis = "<p class='mini'>sin operaciones aún</p>"
    tarjetas.append(_card("kpis", "Dinero papel: KPIs", _kpis))
    tarjetas.append(_card("prec", "Precisión", prec_b))
    try:
        _cal = _calibracion_html(est)
    except Exception:
        _cal = "<p class='mini'>sin datos aún (mínimo 5 evaluadas).</p>"
    tarjetas.append(_card("calib", "Calibración", _cal))
    try:
        _som = _sombra_html(est)
    except Exception:
        _som = "<p class='mini'>sin evaluaciones aún</p>"
    tarjetas.append(_card("sombra", "Sombra (aprende de todo)", _som))
    tarjetas.append(_sec("Sistema", "s-sistema"))
    tarjetas.append(_card("frescura", "Frescura", f"<p>{_esc(_fuente)}</p><p class='mini'>vivo hasta 15 min · tibio hasta 60 min · viejo despues · s/d sin latido</p>"))
    tarjetas.append(_card("act", "Actividad", act_b))
    grid = "".join(tarjetas)
    try:
        fpx = ",".join(str(int(v)) for v in px[-30:] if isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf")) and v) or ""
    except Exception:
        fpx = ""
    snap_g = est.get("snapshot") or {}
    try:
        _nvg = snap_g.get("niv") or {}
        _sres = ((_nvg.get("res") or [{}])[0] or {}).get("precio", "")
        _ssop = ((_nvg.get("sop") or [{}])[0] or {}).get("precio", "")
        _mem = est.get("mem_zonas") or {}
        _mem_mini = {str(k): {"hold": int((v or {}).get("hold", 0) or 0), "rompe": int((v or {}).get("rompe", 0) or 0)}
                     for k, v in list(_mem.items())[:60]} if isinstance(_mem, dict) else {}
        _ual = est.get("ultima_alerta") or {}
        _mem_js = json.dumps(_mem_mini)
        _sala_ds = (f' data-res="{_esc(_sres)}" data-sop="{_esc(_ssop)}"'
                    f' data-banco="{_esc(est.get("banco", ""))}"'
                    f' data-motivo="{_esc(str(_ual.get("motivo", ""))[:80])}"'
                    f" data-mem='{_mem_js}'")
    except Exception:
        _sala_ds = ""
    grade = snap_g.get("grade", "?") if isinstance(snap_g, dict) else "?"
    max_cls = " alerta-max" if grade == "A" else ""
    hoy = ahora_dt.strftime("%Y-%m-%d")
    runs_hoy = sum(1 for h in hist if isinstance(h, dict) and str(h.get("t", ""))[:10] == hoy)
    al_hoy = sum(1 for h in hist if isinstance(h, dict) and h.get("tipo") == "alerta" and str(h.get("t", ""))[:10] == hoy)
    prox = _prox_pasada(ahora_dt)
    try:
        seg = min(120, max(20, int((prox - ahora_dt).total_seconds()) + 45)) if prox else 120
        prox_txt = prox.strftime("%H:%M") if prox else "?"
    except Exception:
        seg, prox_txt = 120, "?"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="120">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vigilante BTC</title>
<style>{CSS}</style></head><body data-bias="{_esc(bias)}" data-conf="{_esc(conf)}" data-alertas="{n_alertas}" data-run="{_esc(est.get("runs", "?"))}" data-px="{fpx}" data-grade="{_esc(grade)}"{_sala_ds}><canvas id="fondo"></canvas><div id="latido"></div><div id="destello"></div><div class="wrap{max_cls}">
<header id="hdr"><h1><span class="logo">V</span>Vigilante BTC</h1>
<div class="crew" id="crew" data-mood="normal" title="Cuadrilla: cada bot hace su oficio">
<div class="bot"><div class="cuerpo"></div><small>TEN</small></div>
<div class="bot"><div class="cuerpo"></div><small>TEC</small></div>
<div class="bot"><div class="cuerpo"></div><small>PIS</small></div>
<div class="bot"><div class="cuerpo"></div><small>MSJ</small></div>
<div class="bot"><div class="cuerpo"></div><small>SOM</small></div>
<div class="bot"><div class="cuerpo"></div><small>PAP</small></div>
</div>
<span class="saludo" id="hdr-saludo">{_esc(_saludo(ahora_dt))}</span>
<span class="live" id="hdr-act"><span class="dot"></span>actualizado {_esc(ahora)} · recarga en <b id="recarga">{seg // 60}:{seg % 60:02d}</b></span>
<span class="live" id="hdr-prox"><span class="dot"></span>próxima pasada ~{_esc(prox_txt)}</span>
<span class="live" id="hdr-edad"><span class="dot"></span>datos de hace {f'<b id="edad" data-t="{_esc(ahora_iso)}">…</b>' if hay_dato else '<b id="edad">sin datos aún</b>'}</span>
<span class="live" id="hdr-vivo"><span class="dot" style="background:var(--amb)"></span>BTC <b id="pvivo">…</b> <small style="color:#64748b">en vivo</small></span>
<a class="tbtn" href="motor.html" target="_blank" rel="noopener">Motor 4h</a>
<button class="tbtn" id="plegar">Plegar todo</button>
<button class="tbtn" id="sonido">Sonido off</button><span id="motor"></span></header>
<div class="nav"><a href="#s-precio">Precio</a><a href="#s-senales">Señales</a><a href="#s-mercado">Mercado</a><a href="#s-dinero">Dinero</a><a href="#s-sistema">Sistema</a></div>
<div class="grid">
{grid}
</div><footer>Análisis probabilístico. No es asesoramiento financiero. v36. · hoy {runs_hoy} pasadas · {al_hoy} alertas</footer>
</div>
<script>var RL={seg};setInterval(function(){{var el=document.getElementById('recarga');
if(window.__musica){{if(el)el.textContent='♪';RL=120;}}
else{{var m=Math.floor(RL/60),s=RL%60;
if(el)el.textContent=m+':'+(s<10?'0':'')+s;RL--;if(RL<0)location.reload();}}}},1000);</script>
{CD_JS}
{UI_JS}
{TF_JS}
{VIVO_JS}
{IDLE_JS}
{FREE_JS}
{SALA_JS}
{FONDO_JS}
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
