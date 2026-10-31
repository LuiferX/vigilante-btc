#!/usr/bin/env python3
"""
comandos.py - CHAT EN 2 VIAS (Fase 14): lee comandos de Telegram y los
responde con la ultima foto del mercado.
"""

import json
import os
import urllib.request


def leer_comandos(offset):
    """Lee mensajes nuevos dirigidos al bot (chat en 2 vías con retardo)."""
    try:
        offset = int(offset or 0)
    except Exception:
        offset = 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return [], offset
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=10"
        req = urllib.request.Request(url, headers={"User-Agent": "vigilante-cloud/3.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        msgs = []
        new_off = offset
        res = data.get("result", []) if isinstance(data, dict) else []
        if res:
            try:
                new_off = max(new_off, int(res[-1].get("update_id", 0)) + 1)
            except Exception:
                pass
        for u in res:
            try:
                new_off = max(new_off, int(u.get("update_id", 0)) + 1)
            except Exception:
                pass
            m = u.get("message") or u.get("edited_message") or {}
            txt = (m.get("text") or "").strip()
            cid = (m.get("chat") or {}).get("id")
            if txt.startswith("/"):
                tk = txt.split()[0].split("@")[0].lower()
                msgs.append(
                    {
                        "chat": cid,
                        "texto": tk,
                        "full": txt[:500],
                        "nombre": str(((m.get("from") or {}).get("first_name") or ""))[:30].replace(
                            "\n", " "
                        ),
                    }
                )
        return msgs, new_off
    except Exception:
        return [], offset


from vigilante.estado import MAX_OPS
from vigilante.eventos import linea_estudio
from vigilante.indicadores import fmt_miles
from vigilante.medicion import calibrar, prec_str, precision_plan, tabla_calibracion
from vigilante.paper import PAPER_BANCO, PAPER_LEV, racha_perdidas
from vigilante.precision import cargar_motor_nuevo


def responder_comando(cmd, ctx):
    """Solo responde al dueño (seguridad: verifica el chat). Devuelve (texto, dirty)."""
    chat_ok = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_ok or str((cmd or {}).get("chat")) != str(chat_ok):
        return None, False
    c = str((cmd or {}).get("texto") or "").split("@")[0].strip().lower() or "/ayuda"
    try:
        t = ctx["t"]
        dirb = ctx["dirb"]
        niv = ctx["niv"]
        fg = ctx["fg"]
        est = ctx["est"]
        ahora = ctx["ahora"]
        _rs = niv.get("resistencias") or []
        _ss = niv.get("soportes") or []
        if not _rs or not _ss:
            return ("Niveles en cálculo, prueba /precio en la próxima pasada.", False)
        res = _rs[0]
        sup = _ss[0]
    except Exception:
        return ("No entiendo el estado ahora mismo, prueba en la próxima pasada.", False)
    if c == "/precio":
        return (
            f"BTC ahora: {fmt_miles(t['last'])} ({t['chg']:+.2f}% 24h). "
            f"Rango del día: {fmt_miles(t['lo'])} - {fmt_miles(t['hi'])}.",
            False,
        )
    if c == "/direccion":

        def _tf(x):
            return f"{x.get('tf', '?')} {x.get('tend', '?')} RSI {x.get('rsi', '?')} MACD {'+' if x.get('macd', 0) > 0 else '-'}"

        return (
            f"Dirección: {dirb['bias']} (confianza {dirb['confianza']}%). "
            + " | ".join(_tf(ctx[k]) for k in ("h1", "h4", "d1", "w1"))
            + ".",
            False,
        )
    if c == "/niveles":
        return (
            "Soportes: "
            + " | ".join(fmt_miles(x["precio"]) for x in niv["soportes"])
            + "\nResistencias: "
            + " | ".join(fmt_miles(x["precio"]) for x in niv["resistencias"]),
            False,
        )
    if c == "/miedo":
        ff = f"{ctx['senti']['funding']:+.4f}%" if ctx["senti"]["funding"] is not None else "n/d"
        tk = ctx["senti"]["taker"] if ctx["senti"]["taker"] is not None else "n/d"
        return (
            f"{fg['etiqueta']}: {fg['valor']}/100 (RSI 1D {ctx['d1']['rsi']}, funding {ff}, taker {tk}).",
            False,
        )
    if c == "/noticias":
        ns = (ctx.get("notis") or [])[:3]
        if not ns:
            return ("Sin noticias relevantes ahora mismo.", False)
        base = "Top noticias:\n" + "\n".join(f"• [{n['score']}] {n['titulo']}" for n in ns)
        pr = ctx.get("pres")
        if pr:
            base += f"\nPresión: {pr['txt']}."
        return (base, False)
    if c == "/eventos":
        evs = ctx["evs"][:3]
        if not evs:
            return ("Sin eventos fuertes esta semana.", False)
        return (
            "Próximos eventos:\n"
            + "\n".join(
                f"• {e['titulo']} ({e['cuando'].strftime('%a %d %H:%M')} UTC)"
                + (
                    f"\n  📊 {linea_estudio(est, e['titulo'])}"
                    if linea_estudio(est, e["titulo"])
                    else ""
                )
                for e in evs
            ),
            False,
        )
    if c == "/precision":
        _pp = precision_plan(est)
        if _pp:
            _pa, _pb = _pp
            base = (
                f"Precisión (dirección del plan): ALZA {prec_str(_pa)} · " f"BAJA {prec_str(_pb)}."
            )
        else:
            base = (
                f"Precisión (histórico por sesgo): ALZA {prec_str(est.get('alza', []))} · "
                f"BAJA {prec_str(est.get('baja', []))}. Aún sin muestras de plan."
            )
        aut = ctx.get("aut")
        if aut:
            base += (
                f"\nAuto: mejor {aut['mejor'][0]} ({aut['mejor'][1]}%) · "
                f"peor {aut['peor'][0]} ({aut['peor'][1]}%) · n={aut['n']}."
            )
        cal = calibrar(est)
        if cal:
            base += "\nCalib: " + ", ".join(f"{s}x{f}" for s, f in sorted(cal.items())) + "."
        tc = tabla_calibracion(est.get("eval_log", []))
        if tc:
            cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
            base += f"\nConciencia: cuando digo 40s/50s/60+ acierto {cub} · Brier {tc['brier']} (0 perfecto) · n={tc['n']}."
        return (base, False)
    if c == "/sombra":
        try:
            slog = [e for e in (est.get("eval_sombra", []) or []) if isinstance(e, dict)]
            n = len(slog)
            if not n:
                return (
                    "Sombra: sin evaluaciones aún (mide toda señal con sesgo, sin operar).",
                    False,
                )
            ok = sum(1 for e in slog if float(e.get("r", 0) or 0) > 0)
            pct = round(ok / n * 100) if n else 0
            base = f"Sombra: n={n} · acierto {pct}% ({ok}/{n})."
            try:
                tc = tabla_calibracion(slog)
            except Exception:
                tc = None
            if tc and tc.get("cubetas"):
                cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
                base += f"\nPor confianza: {cub}."
            return (base, False)
        except Exception:
            return ("Sombra: sin datos válidos aún.", False)
    if c == "/evals":
        try:
            elog_all = [e for e in (est.get("eval_log", []) or []) if isinstance(e, dict)]
            elog_plan = [e for e in elog_all if e.get("metodo") == "plan"]
            elog = elog_plan or elog_all
            n = len(elog)
            if not n:
                return ("Evals: sin evaluaciones aún.", False)
            etiqueta = "plan" if elog_plan else "histórico por sesgo"
            ok = sum(1 for e in elog if float(e.get("r", 0) or 0) > 0)
            pct = round(ok / n * 100) if n else 0
            base = f"Evals ({etiqueta}): n={n} · acierto {pct}% ({ok}/{n})."
            try:
                tc = tabla_calibracion(elog)
            except Exception:
                tc = None
            if tc and tc.get("cubetas"):
                cub = ", ".join(f"{k}:{v[1]}%({v[0]})" for k, v in sorted(tc["cubetas"].items()))
                base += f"\nPor confianza: {cub} · Brier {tc['brier']} (0 perfecto)."
            try:
                glog = [e for e in (est.get("eval_gate", []) or []) if isinstance(e, dict)]
                if glog:
                    gok = sum(1 for e in glog if float(e.get("r", 0) or 0) > 0)
                    gpct = round(gok / len(glog) * 100) if glog else 0
                    base += (
                        f"\nGate (silenciadas, contrafactual): {gok}/{len(glog)} = {gpct}%."
                        " No se enviaron; solo auditan el filtro."
                    )
            except Exception:
                pass
            base += "\nDesde este fix: direccion real del plan. Antes se media el sesgo."
            return (base, False)
        except Exception:
            return ("Evals: sin datos válidos aún.", False)
    if c == "/manos":
        sm = ctx.get("smart")
        if not sm:
            return ("Sin datos de flujos ahora.", False)
        try:
            return (
                (
                    f"Instituciones {sm.get('inst', '?')}/100 · Minoristas {sm.get('ret', '?')}/100.\n"
                    + str(sm.get("veredicto", "sin veredicto"))
                ),
                False,
            )
        except Exception:
            return ("Sin datos de flujos ahora.", False)
    if c == "/calidad":
        g = ctx.get("grade", "?")
        rg = ctx.get("regimen", "?")
        bl = " (blackout: sin señales nuevas)" if ctx.get("bloqueo") else ""
        return (f"Calidad: {g} · régimen {rg}{bl}. Opera solo las A.", False)
    if c in ("/motor", "/motor4h"):
        m = ctx.get("motor") or cargar_motor_nuevo()
        if not m:
            return (
                "Motor 4h: sin lectura fresca. El pipeline corre cada 15 min; revisa /motor.html.",
                False,
            )
        base = f"Motor 4h: {m.get('action', '?')} · sesgo {m.get('bias') or '?'} · {m.get('age_min')} min."
        if m.get("trigger"):
            base += f"\nTrigger: {m['trigger']}"
        if m.get("invalidation"):
            base += f"\nInvalida: {m['invalidation']}"
        base += "\nEs contexto, no una orden: el motor no ejecuta."
        return (base, False)
    if c == "/detalle":
        return ("Te mando el parte completo ahora.", False)
    if c == "/alerta":
        parts = cmd.get("full", "").split()
        if len(parts) != 2:
            return ("Uso: /alerta 85000 (te aviso al tocarlo).", False)
        try:
            px = float(parts[1])
        except Exception:
            return ("Precio inválido.", False)
        if px <= 0:
            return ("Precio debe ser > 0.", False)
        if not (1000 <= px <= 1000000):
            return ("Precio fuera de rango sensato (1.000–1.000.000).", False)
        d = "sube" if px >= t["last"] else "baja"
        al = est.get("mis_alertas") or []
        if len(al) >= 20:
            return ("Tienes 20 alertas (máximo). Borra con /borrar.", False)
        al.append({"precio": px, "dir": d})
        est["mis_alertas"] = al
        verbo = "suba a" if d == "sube" else "baje a"
        return (f"Alerta creada: te aviso cuando BTC {verbo} {fmt_miles(px)}.", True)
    if c == "/alertas":
        al = est.get("mis_alertas") or []
        limpias = [a for a in al if isinstance(a, dict) and a.get("precio") and a.get("dir")]
        if not limpias:
            if al:
                return ("Tus alertas están corruptas. Usa /borrar y crea de nuevo.", False)
            return ("Sin alertas de precio. Crea con /alerta 85000.", False)
        try:
            txt = "\n".join(f"• {fmt_miles(float(a['precio']))} ({a['dir']})" for a in limpias)
        except Exception:
            return ("Tus alertas están corruptas. Usa /borrar y crea de nuevo.", False)
        return (("Tus alertas:\n" + txt), False)
    if c == "/borrar":
        est["mis_alertas"] = []
        return ("Alertas de precio borradas.", True)
    if c == "/opere":
        parts = cmd.get("full", "").split()
        if len(parts) != 5:
            return (
                "Uso: /opere LONG|SHORT entrada stop tp (ej: /opere LONG 83000 82500 84000).",
                False,
            )
        d = parts[1].upper()
        if d not in ("LONG", "SHORT"):
            return ("Dirección: LONG o SHORT.", False)
        try:
            e, s, tp = float(parts[2]), float(parts[3]), float(parts[4])
        except Exception:
            return ("Números inválidos.", False)
        if not (e > 0 and s > 0 and tp > 0 and e != s):
            return ("Revisa precios (stop distinto de entrada).", False)
        if d == "LONG" and not (s < e):
            return ("En LONG el stop va bajo la entrada.", False)
        if d == "SHORT" and not (s > e):
            return ("En SHORT el stop va sobre la entrada.", False)
        ops = est.get("ops") or []
        if len(ops) >= MAX_OPS:
            return ("Tienes 20 operaciones abiertas (máximo). Cierra con /cerrar.", False)
        ops.append({"dir": d, "entrada": e, "stop": s, "tp": tp, "t": ahora.isoformat()})
        est["ops"] = ops
        return (
            (
                f"Registrada: {d} {fmt_miles(e)} (SL {fmt_miles(s)} / TP {fmt_miles(tp)}). "
                "Te aviso al cerrar."
            ),
            True,
        )
    if c == "/voy":
        ops = est.get("ops") or []
        if not ops:
            return ("Sin operaciones abiertas.", False)
        lines = []
        for o in ops or []:
            try:
                e, s = float(o["entrada"]), float(o["stop"])
                riesgo = abs(e - s) or 1
                rr = (
                    (t["last"] - e) / riesgo if o.get("dir") == "LONG" else (e - t["last"]) / riesgo
                )
                lines.append(
                    f"{o.get('dir', '?')} {fmt_miles(e)}: {rr:+.1f}R ahora (SL {fmt_miles(s)} / TP {fmt_miles(float(o.get('tp', s)))})"
                )
            except Exception:
                continue
        return ("\n".join(lines) or "Sin operaciones válidas.", False)
    if c == "/diario":
        j = est.get("journal", [])
        if not j:
            return ("Diario vacío: registra con /opere LONG entrada stop tp.", False)
        w = sum(1 for x in j if x.get("r", 0) > 0)
        tr = round(sum(x.get("r", 0) for x in j), 1)
        return (
            f"Diario: {len(j)} ops · ganadas {w} ({round(w / len(j) * 100)}%) · total {tr:+.1f}R.",
            False,
        )
    if c == "/papel":
        try:
            banco = float(est.get("banco", PAPER_BANCO))
        except Exception:
            banco = float(PAPER_BANCO)
        j = est.get("paper_cerradas", [])
        ops = est.get("paper_abiertas", [])
        if not j and not ops:
            return (
                f"Papel XLX: banco {PAPER_BANCO:.0f} USDT, lev {PAPER_LEV}x, sin operaciones aún. Abro solo con señales ALZA/BAJA de 35%+.",
                False,
            )
        w = sum(1 for x in j if x.get("pnl", 0) > 0)
        wr = f"{round(w / len(j) * 100)}% ({w}/{len(j)})" if j else "s/d"
        tr = round(sum(x.get("r", 0) for x in j), 1) if j else 0
        txt = f"Papel XLX: banco {fmt_miles(banco)} USDT ({banco - PAPER_BANCO:+.0f}) · lev {PAPER_LEV}x · cerradas {len(j)} · ganadas {wr} · total {tr:+.1f}R."
        if racha_perdidas(est) >= 3:
            txt += " Penalizado: arriesga 0.5% (3+ pérdidas seguidas)."
        if ops:
            txt += "\nAbiertas:\n" + "\n".join(
                f"• {o['dir']} {fmt_miles(o['entrada'])} (SL {fmt_miles(o['stop'])} / TP {fmt_miles(o['tp'])} / LIQ {fmt_miles(o.get('liq', 0))})"
                for o in ops
            )
        return (txt, False)
    if c == "/cerrar":
        ops = est.get("ops", [])
        if not ops:
            return ("No hay operaciones abiertas.", False)
        j = est.get("journal", [])
        outs = []
        for o in ops:
            e, s = o["entrada"], o["stop"]
            riesgo = abs(e - s) or 1
            rr = (t["last"] - e) / riesgo if o["dir"] == "LONG" else (e - t["last"]) / riesgo
            j.append({"dir": o["dir"], "res": "MANUAL", "r": round(rr, 2), "t": ahora.isoformat()})
            outs.append(f"{o['dir']} cerrada en {fmt_miles(t['last'])} ({rr:+.1f}R)")
        est["ops"] = []
        est["journal"] = j[-50:]
        return ("\n".join(outs), True)
    if c == "/simula":
        parts = cmd.get("full", "").split()
        sims = est.get("sim_abiertas", [])
        if len(parts) == 1:
            cerr = est.get("sim_cerradas", [])
            w = sum(1 for x in cerr if x.get("r", 0) > 0)
            base = f"Simulador: {len(sims)} abiertas · {len(cerr)} cerradas ({w} ganadas)."
            if sims:
                base += "\n" + "\n".join(
                    f"• {o['dir']} {fmt_miles(o['entrada'])} (SL {fmt_miles(o['stop'])} / TP {fmt_miles(o['tp'])})"
                    for o in sims[-5:]
                )
            base += "\nUso: /simula LONG|SHORT entrada [stop tp] (sin dinero, solo aprendizaje)."
            return (base, False)
        if len(parts) not in (3, 5) or parts[1].upper() not in ("LONG", "SHORT"):
            return ("Uso: /simula LONG 83000 o /simula SHORT 83000 82500 84000.", False)
        if len(sims) >= 5:
            return ("Tienes 5 simuladas abiertas (máximo). Espera cierres.", False)
        d = parts[1].upper()
        try:
            e = float(parts[2])
            if len(parts) == 5:
                s, tp = float(parts[3]), float(parts[4])
            elif d == "LONG":
                s = niv["soportes"][0]["precio"]
                tp = e + 2 * (e - s)
            else:
                s = niv["resistencias"][0]["precio"]
                tp = e - 2 * (s - e)
        except Exception:
            return ("Números inválidos.", False)
        if not (e > 0 and s > 0 and tp > 0 and e != s):
            return ("Revisa los precios (stop distinto de entrada).", False)
        if d == "LONG" and not (s < e):
            return ("En LONG el stop va bajo la entrada.", False)
        if d == "SHORT" and not (s > e):
            return ("En SHORT el stop va sobre la entrada.", False)
        riesgo = abs(e - s) or 1
        rr = abs(tp - e) / riesgo
        sims.append({"dir": d, "entrada": e, "stop": s, "tp": tp, "t": ahora.isoformat()})
        est["sim_abiertas"] = sims
        return (
            (
                f"🔬 Simulada: {d} {fmt_miles(e)} (SL {fmt_miles(s)} / TP {fmt_miles(tp)}, {rr:.1f}R). "
                "Sin dinero, solo aprendizaje. Te aviso al cerrar."
            ),
            True,
        )
    _nom = str((cmd or {}).get("nombre") or "").strip().replace("\n", " ")[:30]
    hola = f" Hola {_nom}." if _nom else " Hola."
    return (
        (
            hola + " Te respondo en cada pasada (máx ~30 min).\n"
            "Comandos: /precio /direccion /niveles /miedo /noticias /eventos /motor /precision /sombra /evals /manos "
            "/alerta /alertas /borrar /opere /voy /diario /cerrar /calidad /detalle /papel /simula"
        ),
        False,
    )
