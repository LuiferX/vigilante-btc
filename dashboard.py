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


def svg_linea(vals, w=560, h=160, color="#38bdf8", marcas=None, niveles=None):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if len(vals) < 2:
        return "<p>sin datos aún</p>"
    _uid[0] += 1
    gid = f"g{_uid[0]}"
    lo, hi = min(vals), max(vals)
    nvs = []
    for nv in (niveles or []):
        try:
            p = float((nv or {}).get("precio"))
            nvs.append((p, str((nv or {}).get("etiqueta", "")), str((nv or {}).get("kind", ""))))
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
    dots.append(
        f'<circle class="last" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4.5">'
        f"<title>cierre · {vals[-1]:,.0f}</title></circle>")
    lvls = []
    for p, txt, kind in nvs:
        y = h - 14 - (p - lo) / rg * (h - 34)
        cls = "nres" if kind == "res" else "nsop"
        lvls.append(
            f"<line x1='10' y1='{y:.1f}' x2='{w - 62}' y2='{y:.1f}' class='lvl {cls}'>"
            f"<title>{txt} · {p:,.0f}</title></line>"
            f"<text x='{w - 60}' y='{y - 3:.1f}' class='tag lvl-{cls}'>{p:,.0f}</text>")
    return (
        f'<svg class="resp draw" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f"<defs><linearGradient id=\"{gid}\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
        f"<stop offset=\"0\" stop-color=\"{color}\" stop-opacity=\".35\"/>"
        f"<stop offset=\"1\" stop-color=\"{color}\" stop-opacity=\"0\"/></linearGradient></defs>"
        f"<path d=\"{area}\" fill=\"url(#{gid})\"/>"
        f"<polyline class=\"linea\" points=\"{pts}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2.5\" stroke-linejoin=\"round\"/>"
        + "".join(lvls) + "".join(dots) +
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
svg .lvl{stroke-width:1.2;stroke-dasharray:6 4;opacity:.85}
svg .lvl.nsop{stroke:#22c55e}svg .lvl.nres{stroke:#ef4444}
svg .tag.lvl-nsop{fill:#4ade80}svg .tag.lvl-nres{fill:#fca5a5}
.kv{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:#cbd5e1;background:#0f172a}
.chip b{color:#fff}
footer{color:#64748b;font-size:12px;margin:14px 2px}
@media(max-width:480px){.big{font-size:24px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
.stats{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.stat{flex:1 1 100px;background:#0f172a;border:1px solid var(--line);border-radius:10px;padding:6px 9px}
.stat small{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut)}
.stat b{font-size:15px;font-variant-numeric:tabular-nums}
table.ops{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
table.ops th{text-align:left;color:var(--mut);font-weight:600;padding:4px 6px;border-bottom:1px solid var(--line)}
table.ops td{padding:4px 6px;border-bottom:1px solid #1e293b;font-variant-numeric:tabular-nums}
.win{color:#4ade80;font-weight:700}.loss{color:#fca5a5;font-weight:700}
.tagLONG{color:#4ade80;font-weight:700}.tagSHORT{color:#fca5a5;font-weight:700}
.mini{font-size:12px;color:var(--mut)}
.chead{all:unset;display:flex;align-items:center;justify-content:space-between;width:100%;cursor:pointer;
box-sizing:border-box;padding:2px 0 10px}
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
.gauge .track{stroke:#1e293b}
.gauge .fill{stroke-linecap:round;transition:stroke-dashoffset 1.2s ease}
.gnum{font-size:26px;font-weight:800;fill:#fff}
.glab{font-size:10px;fill:var(--mut)}
.clock{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}
.nyon{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px}
.nyon.on{background:#052e16;color:#4ade80;border:1px solid #22c55e55}
.nyon.off{background:#1e293b;color:#cbd5e1;border:1px solid var(--line)}
"""


def _card(cid, titulo, cuerpo):
    return (f"<div class='card' id='c-{cid}'>"
            f"<button class='chead' data-c='{cid}' aria-expanded='true'>"
            f"<span class='ctit'>{titulo}</span><span class='chev'>▾</span></button>"
            f"<div class='cbody'><div class='cinner'>{cuerpo}</div></div></div>")


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
    return (f"<p>Régimen <b style='color:#e2e8f0'>{reg}</b> · grado <b style='color:#e2e8f0'>{grade}</b></p>"
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
    racha = 0
    for c in reversed(cerradas):
        if _num(c.get("pnl")) < 0:
            racha += 1
        else:
            break
    frenos = []
    try:
        b = float(banco) if banco is not None else 10000.0
        pico = float(est.get("banco_pico", b))
        dd = (pico - b) / pico * 100 if pico > 0 else 0
        if dd >= 10:
            frenos.append("⛔ pico −10%")
    except Exception:
        dd = 0
    pd = est.get("paper_dia") or {}
    try:
        base = float(banco) if banco is not None else 10000.0
        if isinstance(pd, dict) and float(pd.get("pnl", 0)) <= -0.03 * base:
            frenos.append("⛔ día −3%")
    except Exception:
        pass
    if racha >= 3:
        frenos.append("⚠️ racha: riesgo 0,5%")
    freno_txt = " · ".join(frenos) if frenos else "frenos OK ✅"
    btxt = f"{miles(banco)} USDT ({tot_pnl:+.0f})" if banco is not None else "10.000 USDT (sin empezar)"
    stats = (
        f"<div class='stats'>"
        f"<div class='stat'><small>Banco</small><b>{btxt}</b></div>"
        f"<div class='stat'><small>Ganadas</small><b>{wr}</b></div>"
        f"<div class='stat'><small>Total</small><b>{tot_r:+.1f}R</b></div>"
        f"<div class='stat'><small>Racha pérdida</small><b>{racha}</b></div>"
        f"</div><p class='mini'>{freno_txt} · papel opera señales 35%+ (invisible, sin avisos)</p>")
    if abiertas:
        filas = "".join(
            f"<tr><td class='tag{o.get('dir', '')}'>{o.get('dir', '?')}</td>"
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
            filas += (f"<tr><td class='tag{c.get('dir', '')}'>{c.get('dir', '?')}</td>"
                      f"<td>{res}</td><td class='{cls}'>{pnl:+.0f}</td>"
                      f"<td class='{cls}'>{_num(c.get('r')):+.2f}R</td><td>{ft}</td></tr>")
        ce = (f"<p class='mini'>Últimas cerradas ({n})</p>"
              f"<table class='ops'><tr><th>Dir</th><th>Fin</th><th>PnL</th><th>R</th><th>Fecha</th></tr>{filas}</table>")
    else:
        ce = ("<p class='mini'>Sin cerradas aún — el papel sólo abre con ALZA/BAJA de 35%+ "
              "y el mercado viene lateral. Cuando opere, aquí verás cada cierre.</p>")
    if pend:
        lp = "".join(
            f"<span class='chip'><b>{p.get('bias', '?')}</b> {p.get('conf', '?')}% @ {miles(p.get('precio'))} "
            f"{_hace(p.get('t', ''), ahora)}</span>" for p in pend[-6:])
        pe = f"<p class='mini'>En seguimiento ({len(pend)} — se evalúan a 8h)</p><div class='kv'>{lp}</div>"
    else:
        pe = "<p class='mini'>En seguimiento: 0 — no hay señales esperando evaluación.</p>"
    if journal:
        lj = "".join(
            f"<span class='chip'><b>{j.get('dir', '?')}</b> {j.get('res', '?')} "
            f"{_num(j.get('r')):+.2f}R</span>" for j in journal[-5:])
        jo = f"<p class='mini'>Mi diario ({len(journal)})</p><div class='kv'>{lj}</div>"
    else:
        jo = "<p class='mini'>Mi diario: vacío — registra con /opere en Telegram.</p>"
    return (f"{stats}{ab}{ce}{pe}{jo}")


CD_JS = ("<script>(function(){var el=document.getElementById('cd');"
          "if(!el||!el.dataset||!el.dataset.next)return;"
          "var t=new Date(el.dataset.next).getTime();"
          "function tk(){var d=t-Date.now();if(d<0){el.textContent='¡ahora!';return;}"
          "var h=Math.floor(d/36e5),m=Math.floor(d%36e5/6e4),s=Math.floor(d%6e4/1e3);"
          "el.textContent=h+'h '+m+'m '+s+'s';}"
          "tk();setInterval(tk,1000);})();</script>")

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
          "if(tgl){tgl.addEventListener('click',function(){"
          "var cards=document.querySelectorAll('.card');"
          "var anyOpen=Array.prototype.some.call(cards,function(c){return !c.classList.contains('closed');});"
          "var s={};cards.forEach(function(c){var id=c.id.replace('c-','');"
          "if(anyOpen){c.classList.add('closed');s[id]='0';}else{c.classList.remove('closed');s[id]='1';}"
          "var b=c.querySelector('.chead');if(b)b.setAttribute('aria-expanded',String(!anyOpen));});"
          "save(s);tgl.textContent=anyOpen?'Desplegar todo':'Plegar todo';});}"
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
          "var on=false;try{on=localStorage.getItem('vig_sound')==='1';}catch(e){}"
          "var snd=document.getElementById('sonido');"
          "function paint(){if(snd)snd.textContent=on?'\\u{1F50A} Sonido':'\\u{1F507} Sonido';}"
          "paint();if(on){try{motif();}catch(e){}}"
          "if(snd){snd.addEventListener('click',function(){on=!on;"
          "try{localStorage.setItem('vig_sound',on?'1':'0');}catch(e){}paint();if(on)motif();});}"
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
    v = max(0, min(100, v))
    et = (fg or {}).get("etiqueta", "")
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
            if isinstance(fv, (int, float)):
                fgh.append(fv)
    except Exception:
        fgh = []
    spark = svg_linea(fgh, color="#f59e0b") if len(fgh) >= 2 else ""
    evs = [(2, "🌙 noche"), (7, "🌅 madrugada"), (8, "☀️ mañana"), (13, "🗽 pre-NY"), (20, "🏁 cierre NY")]
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


def build_dashboard(est, hist):
    if not isinstance(est, dict):
        est = {}
    if not isinstance(hist, list):
        hist = []
    ahora_dt = datetime.datetime.now(datetime.timezone.utc)
    ahora = ahora_dt.strftime("%d/%m %H:%M UTC")
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
    ops = _ops_html(est, ahora_dt)
    reloj = _gauge_reloj_html(est, ult, ahora_dt)
    nvs, dist_txt = [], ""
    try:
        niv = (est.get("snapshot") or {}).get("niv") or {}
        sops = [s for s in (niv.get("sop") or []) if isinstance(s, dict)][:2]
        ress = [r for r in (niv.get("res") or []) if isinstance(r, dict)][:2]
        for s in sops:
            nvs.append({"precio": s.get("precio"), "etiqueta": f"🛡 {s.get('origen', 'soporte')}", "kind": "sop"})
        for r in ress:
            nvs.append({"precio": r.get("precio"), "etiqueta": f"🧲 {r.get('origen', 'resistencia')}", "kind": "res"})
        if precio and sops and ress:
            ds = (precio - float(sops[0].get("precio", precio))) / precio * 100
            dr = (float(ress[0].get("precio", precio)) - precio) / precio * 100
            dist_txt = f" · 🛡 a −{abs(ds):.2f}% · 🧲 a +{abs(dr):.2f}%"
    except Exception:
        nvs, dist_txt = [], ""
    hero = (f"<div class='big'>{miles(precio)}<span class='badge {_bias_class(bias)}'>{bias} {conf}%</span></div>"
            f"<div class='pill'><i style='--w:{conf_w}%'></i></div>"
            f"<div class='sub'>{delta_txt} · {rango_txt} · 🔴 {n_alertas} alertas en ventana{dist_txt}</div>")
    curva = (f"{svg_linea(px, marcas=marcas, niveles=nvs)}"
             f"<p><span style='color:#4ade80'>─ soporte</span> · "
             f"<span style='color:#fca5a5'>─ resistencia</span> (origen al pasar el mouse).</p>")
    confb = (f"{svg_barras(cf, [str(i) for i in range(len(cf))])}"
             f"<p>Verde ≥55 (fuerte) · ámbar ≥40 · gris debajo. Líneas: 45 registra / 55 fuerte.</p>")
    banco_b = f"<div class='big' style='font-size:22px'>{eq_txt}</div>{svg_linea(eq, color='#22c55e')}"
    prec_b = (f"<p>ALZA {pa} · BAJA {pb}</p>"
              f"<p>Se evalúa a 8h: objetivo 2R antes que stop 1R.</p>")
    act_b = (f"<p>{len(hist)} pasadas guardadas · run {est.get('runs', '?')}</p>"
             f"<p>Sesión NY 13–20 UTC · avisos sólo con cambio real.</p>")
    tarjetas = [_card("hero", "Precio y sesgo", hero),
                _card("curva", f"Precio (últimas {len(px)}) + alertas 🔴", curva),
                _card("conf", "Confianza (escala 0–100)", confb)]
    if reloj:
        tarjetas.append(_card("reloj", "Miedo y sesión 🕰️", reloj))
    if ctx:
        tarjetas.append(_card("ctx", "Contexto", ctx))
    tarjetas.append(_card("ops", "Operaciones papel 🤖", ops))
    tarjetas.append(_card("banco", "Banco papel", banco_b))
    tarjetas.append(_card("prec", "Precisión", prec_b))
    tarjetas.append(_card("act", "Actividad", act_b))
    grid = "".join(tarjetas)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="300">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vigilante BTC</title>
<style>{CSS}</style></head><body data-bias="{bias}" data-conf="{conf}" data-alertas="{n_alertas}"><div class="wrap">
<header><h1>🤖 Vigilante BTC</h1>
<span class="live"><span class="dot"></span>actualizado {ahora} · se refresca solo</span>
<button class="tbtn" id="plegar">Plegar todo</button>
<button class="tbtn" id="sonido">🔇 Sonido</button></header>
<div class="grid">
{grid}
</div><footer>Análisis probabilístico. No es asesoramiento financiero. v7.</footer>
</div>
<script>setTimeout(function(){{location.reload()}},300000);</script>
{CD_JS}
{UI_JS}
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
