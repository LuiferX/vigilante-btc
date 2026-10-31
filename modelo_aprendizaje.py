#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modelo_aprendizaje.py - MODELO VISUAL del aprendizaje del Vigilante BTC.

Simula el cerebro del bot con SUS REGLAS REALES (ver vigilante_cloud.py):
 - registra senales ALZA/BAJA con confianza >= umbral (sin duplicados en 4 h)
 - evalua 8 h despues con umbral relativo al ATR (acierto = moverse a favor)
 - muestra % solo con minimo 5 evaluadas
 - auto-stats por sesion (min 10) y auto-calibracion de umbrales por sesion
 - plan 2R: acierto +2R, fallo -1R

La "habilidad verdadera" por sesion es inventada (semilla fija) SOLO para
visualizar el mecanismo: lo interesante es COMO el bot la descubre solo.
Genera: aprendizaje_metricas.png + aprendizaje_ciclo.png
"""
import math
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

random.seed(7)

SKILL = {"NY": 0.62, "Londres": 0.52, "Asia": 0.38, "noche": 0.48}
SESIONES = ["NY", "Londres", "Asia", "noche"]


def sesion(hora):
    if 0 <= hora < 8:
        return "Asia"
    if 8 <= hora < 13:
        return "Londres"
    if 13 <= hora < 21:
        return "NY"
    return "noche"


DIAS = 60
PASOS = DIAS * 48  # pasadas cada 30 min

thr = {s: 55 for s in SESIONES}
thr_hist = {s: [(0, 55)] for s in SESIONES}
ult_reg = {}
pend = []
eval_events = []
ses_eval = {s: [] for s in SESIONES}
eq, rodante = [], []
aciertos = 0
r_acum = 0.0
n_eval = 0
mostrar_desde = None
precio = 83000.0

for step in range(PASOS):
    hora = (step * 0.5) % 24
    ses = sesion(hora)
    precio *= 1 + random.gauss(0.0, 0.004)
    atr = precio * 0.004
    umbral = max(0.002, (atr / precio) * 0.5)
    # --- generar senal (como el analisis del bot) ---
    bias = random.choices(["ALZA", "BAJA", "LATERAL"], weights=[30, 30, 40])[0]
    conf = random.randint(20, 80)
    if bias != "LATERAL" and conf >= thr[ses]:
        if not (bias in ult_reg and step - ult_reg[bias] < 8):
            ult_reg[bias] = step
            pend.append({"eval": step + 16, "ses": ses, "bias": bias,
                         "precio": precio, "umbral": umbral})
    # --- evaluar vencidas (8 h despues) ---
    for p in [x for x in pend if x["eval"] <= step]:
        ok = random.random() < SKILL[p["ses"]]
        mag = p["umbral"] * (1 + random.random())
        mov = mag if (p["bias"] == "ALZA") == ok else -mag
        hit = 1 if ((mov >= p["umbral"]) if p["bias"] == "ALZA" else (mov <= -p["umbral"])) else 0
        r = 2 if hit else -1
        aciertos += hit
        r_acum += r
        n_eval += 1
        ses_eval[p["ses"]].append(hit)
        eval_events.append({"step": step, "ses": p["ses"], "hit": hit})
        pend.remove(p)
        if n_eval == 5:
            mostrar_desde = step
        if n_eval % 20 == 0:
            for s in SESIONES:
                if len(ses_eval[s]) >= 5:
                    hr = sum(ses_eval[s]) / len(ses_eval[s])
                    if hr > 0.55 and thr[s] > 45:
                        thr[s] -= 5
                    elif hr < 0.45 and thr[s] < 70:
                        thr[s] += 5
            for s in SESIONES:
                thr_hist[s].append((n_eval, thr[s]))
    eq.append(r_acum)
    if len(eval_events) >= 20:
        rodante.append(sum(e["hit"] for e in eval_events[-20:]) / 20 * 100)
    else:
        rodante.append(None)

# ---------------- Figura 1: metricas ----------------
fig, ax = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("Modelo visual del aprendizaje del Vigilante BTC (simulacion 60 dias)", fontsize=14)
dias_x = [s / 48 for s in range(PASOS)]

ax[0, 0].plot(dias_x, eq, color="tab:blue")
ax[0, 0].axhline(0, color="gray", linewidth=0.8)
ax[0, 0].set_title("R acumulado (plan 2R: acierto +2, fallo -1)")
ax[0, 0].set_xlabel("dias")
ax[0, 0].set_ylabel("R")

rx = [d for d, v in zip(dias_x, rodante) if v is not None]
ry = [v for v in rodante if v is not None]
ax[0, 1].plot(rx, ry, color="tab:orange", label="precision movil (20)")
if n_eval:
    ax[0, 1].axhline(aciertos / n_eval * 100, color="tab:green", linestyle="--", label="global")
ax[0, 1].axhline(50, color="gray", linewidth=0.8)
if mostrar_desde is not None:
    ax[0, 1].axvline(mostrar_desde / 48, color="red", linestyle=":", label="minimo 5: aqui nace el %")
ax[0, 1].set_title("Precision: del silencio al veredicto")
ax[0, 1].set_xlabel("dias")
ax[0, 1].set_ylabel("% acierto")
ax[0, 1].legend(fontsize=8)

pcts = []
ns = []
for s in SESIONES:
    v = ses_eval[s]
    pcts.append(round(sum(v) / len(v) * 100) if v else 0)
    ns.append(len(v))
colores = ["tab:green" if p >= 50 else "tab:red" for p in pcts]
barras = ax[1, 0].bar(SESIONES, pcts, color=colores)
ax[1, 0].axhline(50, color="gray", linewidth=0.8)
ax[1, 0].set_title("Precision por sesion (lo que el bot descubre solo)")
ax[1, 0].set_ylabel("% acierto")
for b, p, n in zip(barras, pcts, ns):
    ax[1, 0].text(b.get_x() + b.get_width() / 2, b.get_height() + 1, f"{p}% (n={n})",
                   ha="center", fontsize=9)

for s in SESIONES:
    xs = [c for c, _ in thr_hist[s]]
    ys = [t for _, t in thr_hist[s]]
    ax[1, 1].plot(xs, ys, marker="o", label=s)
ax[1, 1].set_title("Auto-calibracion: umbrales por sesion en el tiempo")
ax[1, 1].set_xlabel("senales evaluadas")
ax[1, 1].set_ylabel("umbral de confianza")
ax[1, 1].legend(fontsize=8)

fig.tight_layout()
fig.savefig("aprendizaje_metricas.png", dpi=110)
print("OK: aprendizaje_metricas.png")

# ---------------- Figura 2: el ciclo ----------------
fig2, a2 = plt.subplots(figsize=(8, 10))
a2.set_xlim(0, 10)
a2.set_ylim(0, 12)
a2.axis("off")
a2.set_title("El ciclo de aprendizaje del bot", fontsize=14)
pasos_ciclo = [
    (5, 10.5, "1. SENAL\nregistra ALZA/BAJA\nconf >= umbral (sin duplicados 4 h)"),
    (5, 8.5, "2. ESPERA 8 H\nel mercado habla,\nel bot calla"),
    (5, 6.5, "3. EVALUA\nse movio >= 0.5 ATR\na favor? (1/0)"),
    (5, 4.5, "4. ESTADISTICA\n% solo con minimo 5\npor sesion con minimo 10"),
    (5, 2.5, "5. AUTO-CALIBRA\nsesion buena -> exige menos\nsesion mala -> exige mas"),
    (5, 0.7, "6. UMBRAL NUEVO\nvuelve al paso 1\nmas sabio"),
]
cajas = []
for x, y, txt in pasos_ciclo:
    caj = FancyBboxPatch((x - 2.6, y - 0.65), 5.2, 1.3, boxstyle="round,pad=0.1",
                         facecolor="#E8F4FD", edgecolor="#1F77B4")
    a2.add_patch(caj)
    a2.text(x, y, txt, ha="center", va="center", fontsize=9)
    cajas.append((x, y))
for i in range(len(cajas) - 1):
    a2.add_patch(FancyArrowPatch((cajas[i][0], cajas[i][1] - 0.65),
                                 (cajas[i + 1][0], cajas[i + 1][1] + 0.65),
                                 arrowstyle="-|>", color="#1F77B4", linewidth=2))
a2.annotate("", xy=(7.6, 10.5), xytext=(7.6, 0.7),
            arrowprops=dict(arrowstyle="-|>", color="tab:green", linewidth=2,
                            connectionstyle="angle3,angleA=0,angleB=90"))
a2.text(8.4, 5.6, "el ciclo\nnunca\npara", ha="center", va="center", fontsize=10, color="tab:green")
fig2.tight_layout()
fig2.savefig("aprendizaje_ciclo.png", dpi=110)
print("OK: aprendizaje_ciclo.png")

# ---------------- Resumen ----------------
print(f"Senales evaluadas: {n_eval} | global: {round(aciertos / n_eval * 100, 1)}% | R total: {r_acum:+.0f}")
for s in SESIONES:
    v = ses_eval[s]
    print(f"  {s}: {round(sum(v) / len(v) * 100, 1)}% (n={len(v)}) -> umbral final {thr[s]}")
