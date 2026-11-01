# Vigilante — máquina de análisis cuantitativo (NO opera)

**REARME 2026-11-01.** Este repo dejó de ser un bot que opera y ahora es un
**instrumento de análisis**: baja datos públicos, los mide con disciplina
(cero look-ahead, percentiles causales, resultados negativos publicados) y
publica un **informe de inteligencia**. No ejecuta órdenes, no propone entradas
y no toca un exchange.

```
collector/ + analysis/archivo_micro.py   →  datos (klines, microestructura)
analysis/percentiles.py                  →  precisión (percentil causal)
analysis/informe.py                      →  lo que se lee (informe diario)
analysis/expr_*.py                       →  investigación auditable (H1..H6)
.github/workflows/                       →  todo automático, diario
```

**Lo que ya está medido y publicado** (no es opinión, es
`analysis/EXPERIMENTOS.md`): en este marco —velas de 5 min, hold 4-72 h, coste
~0,2 % por viaje— **ninguna de las seis familias de señal probadas supera el
peaje**. El resultado negativo está publicado igual que el positivo. Por eso el
valor está en el análisis, no en la ejecución.

```bash
python analysis/informe.py              # el informe, ya
python analysis/percentiles.py --todo   # percentiles causales
python test_vigilante.py                # 73 pruebas del analizador
python -m unittest discover -s analysis -p 'test_*.py'
```

Monitor público: https://luiferx.github.io/vigilante-btc/

---

<div align="center">

# OH WHY

<img src="docs/ohwhy.gif" alt="OH WHY" width="480">

</div>
