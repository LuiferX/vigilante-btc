#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comandos.py - OYENTE: responde comandos cada 5 min (despertador de comandos).

Lee getUpdates + la foto del mercado (snapshot que guarda el vigilante)
+ 1 ticker fresco, y responde sin duplicar codigo (reusa responder_comando).
/detalle deja bandera: el proximo parte va completo.
Corre en GitHub Actions (oyente.yml) disparado por cron-job cada 5 min.
"""
import datetime
import os

import vigilante_cloud as vc


def main():
    ahora = datetime.datetime.now(datetime.timezone.utc)
    est, hist = vc.cargar_estado()
    if not est.get("snapshot"):
        print("Sin snapshot aun (espera el proximo parte).")
        return
    snap = est["snapshot"]
    try:
        cmds, new_off = vc.leer_comandos(est.get("offset", 0))
    except Exception:
        cmds, new_off = [], est.get("offset", 0)
    sucio = False
    if new_off != est.get("offset", 0):
        est["offset"] = new_off
        sucio = True
    try:
        t = vc.ticker24()
        fresco_txt = ""
    except Exception:
        t = {"last": snap["precio"], "chg": snap.get("chg", 0),
             "hi": snap.get("hi", 0), "lo": snap.get("lo", 0)}
        fresco_txt = " (precio del último parte)"
    evs = []
    for e in snap.get("evs", []):
        try:
            d = dict(e)
            d["cuando"] = datetime.datetime.fromisoformat(e["cuando"])
            evs.append(d)
        except Exception:
            continue
    try:
        bloq, _ = vc.blackout(evs, ahora)
    except Exception:
        bloq = False
    try:
        ctx = {"t": t,
               "dirb": {"bias": snap["bias"], "confianza": snap["conf"]},
               "niv": {"resistencias": snap["niv"]["res"], "soportes": snap["niv"]["sop"]},
               "fg": {"valor": snap["fg"]["valor"], "etiqueta": snap["fg"]["etiqueta"]},
               "est": est,
               "h1": snap["tf"]["h1"], "h4": snap["tf"]["h4"],
               "d1": snap["tf"]["d1"], "w1": snap["tf"]["w1"],
               "senti": {"funding": snap["senti"]["funding"], "taker": snap["senti"]["taker"]},
               "notis": snap.get("notis", []), "evs": evs, "ahora": ahora,
               "cb": None, "smart": snap.get("smart"),
               "aut": vc.auto_stats(est.get("eval_log", [])),
               "grade": snap.get("grade", "?"), "regimen": snap.get("regimen", "?"),
               "bloqueo": bloq, "pres": snap.get("pres")}
    except Exception as e:
        print(f"Snapshot incompatible, espero al proximo parte ({e}).")
        return
    chat_ok = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    fresco = est.get("runs", 0) == 0
    n_resp = 0
    if not fresco:
        print(f"Comandos pendientes: {len(cmds)}")
        for cm in cmds:
            if cm["texto"] == "/detalle" and str(cm["chat"]) == str(chat_ok) and chat_ok:
                est["pide_detalle"] = True
                sucio = True
                vc.send_telegram("💬 /detalle\nAnotado: te mando el detalle en la próxima pasada (máx 15 min).")
                print("  /detalle anotado")
                n_resp += 1
                continue
            r, d = vc.responder_comando(cm, ctx)
            if r:
                vc.send_telegram("💬 " + cm["texto"] + "\n" + r + fresco_txt)
                print(f"  respondido {cm['texto']}")
                n_resp += 1
            else:
                print(f"  ignorado {cm['texto']}")
            sucio = sucio or d
    if sucio:
        vc.guardar_estado(est, hist)
    print(f"Oyente OK: {n_resp} respuestas")


if __name__ == "__main__":
    main()
