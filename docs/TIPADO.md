# TIPADO.md — inventario mypy y endurecimiento (T4)

Registro del antes/despues del endurecimiento de tipado sobre los arboles
`vigilante/`, `collector/` y `tools/`. Sin dependencias nuevas: mypy es
herramienta de desarrollo (no entra al runtime), igual que en CI.

## Como reproducirlo

```bash
python -m mypy vigilante/ collector/ tools/                    # PUERTA: config de pyproject.toml
python -m mypy --check-untyped-defs vigilante/ collector/ tools/  # MODO ESTRICTO: también revisa cuerpos de funciones sin anotar
```

Entorno medido: Python 3.13.7, mypy 2.4.0. La puerta declara
`python_version = 3.11`, `check_untyped_defs = false`,
`no_implicit_optional = true`.

## Resumen

| modo                        | errores ANTES | errores DESPUES |
| --------------------------- | ------------: | --------------: |
| puerta (config `pyproject`) |            11 |             **0** |
| estricto (`--check-untyped-defs`) |       64 |             **0** |

En los dos modos: `Success: no issues found in 18 source files`.

## Inventario ANTES (modo estricto, por modulo)

| archivo                    | errores | codigos                                           |
| -------------------------- | ------: | ------------------------------------------------- |
| `vigilante/precision.py`   |      20 | `union-attr` 16, `arg-type` 4                       |
| `collector/collector.py`   |      11 | `index` 9, `var-annotated` 1, `attr-defined` 1      |
| `vigilante/red.py`         |       9 | `assignment` 8, `misc` 1                            |
| `vigilante/mercado.py`     |       6 | `var-annotated` 3, `arg-type` 1, `assignment` 1, `operator` 1 |
| `vigilante/toques.py`      |       5 | `operator` 3, `var-annotated` 1, `call-overload` 1  |
| `vigilante/indicadores.py` |       3 | `var-annotated` 3                                   |
| `vigilante/medicion.py`    |       3 | `var-annotated` 3                                   |
| `vigilante/analisis.py`    |       3 | `var-annotated` 2, `arg-type` 1                     |
| `vigilante/eventos.py`     |       2 | `var-annotated` 2                                   |
| `vigilante/estado.py`      |       1 | `call-overload` 1                                   |
| `vigilante/render.py`      |       1 | `var-annotated` 1                                   |
| **total (11 archivos)**    |  **64** |                                                   |

`tools/secret_scan.py` ya estaba limpio (0 antes, 0 despues).

La **puerta** solo ve 11 errores, todos en `collector/collector.py`
(`check_untyped_defs = false` oculta el resto): 9 `index` + 1 `attr-defined`
por `health` inferido como `dict[str, object]`, y 1 `var-annotated` por
`rows` en `fetch_klines_kraken`.

## Que se arreglo

### 1. Puerta: `collector/collector.py` (11 → 0)

- `health: dict[str, Any]` (en `main`): el payload de salud mezcla
  `bool`/`str`/contadores y sub-dicts por trabajo; sin la anotacion mypy lo
  cerraba como `dict[str, object]` y rechazaba cada asignacion indexada
  (`health["jobs"][fname] = ...`, 9 `index` + 1 `attr-defined`).
- `rows: list = ...` (Kraken): `next(gen, [])` daba `Any | list[Any]`.
- Anotaciones de firma que faltaban: `http_get_json(...) -> Any`,
  `with_fallback(..., primary: Callable[[], list[dict]], fallback: ...) -> list[dict]`.

### 2. Diccionarios inferidos como `dict[str, None]` (9 → 0)

Ocurre al inicializar un dict con todos los valores `None` y rellenarlos
despues: mypy cierra `dict[str, None]` y rechaza el float.

- `vigilante/red.py`: `MERCADO: dict[str, str | None]`, `out: dict[str, float | None]`
  en `sentiment()` (8 `assignment`).
- `vigilante/mercado.py`: `out: dict[str, float | None]` en `coinbase_analisis`.

### 3. Listas/dicts sin anotar que mypy no puede inferir (15 → 0)

`var-annotated` puro: el elemento se deduce demasiado tarde.

- `vigilante/toques.py`: `out: list[dict]` (pivotes_micro).
- `vigilante/indicadores.py`: `hs`/`ls: list[tuple[int, float]]`, `clusters: list[list]`.
- `vigilante/medicion.py`: `buckets: dict[str, list]` (x2), `cubs: dict[str, list[float]]`.
- `vigilante/analisis.py`: `sups`/`ress: list[dict]`.
- `vigilante/eventos.py`: `oi: dict[float, dict[str, float]]`, `acc: dict[str, tuple[int, int]]`.
- `vigilante/render.py`: `_out: list[str]`.
- `vigilante/mercado.py`: `zonas: list[dict]`, `trs: list[float | None]`.

### 4. Modelo y JSON de disco (modelo dict heterogeneo y `Optional` sin tratar)

- `vigilante/toques.py`: `MODELO_TOQUES: dict[str, Any]` — el literal mezcla
  str, float, listas de float y dicts; mypy lo cerraba como `dict[str, object]`
  y de ahi salian el `zip(...)` de `score_toque` (`call-overload`) y las
  comparaciones `z > 30` / `math.exp(-z)` (`operator`, 3).
- `vigilante/estado.py`: `est: dict[str, Any]` + firma honesta
  `cargar_estado() -> tuple[dict[str, Any], list[dict[str, Any]]]`
  (antes devolvia una tupla sin declarar y `int(est.get("offset"))`
  era `call-overload` sobre `object`).
- `vigilante/precision.py`: dos helpers privados que reemplazan el patron
  repetido y fragil `d.get(k) if isinstance(d.get(k), dict) else {}`:

  ```python
  def _sub(d, clave) -> dict[str, Any]   # sub-diccionario tolerante
  def _num(v) -> float | None            # float tolerante
  ```

  Con ellos se van 16 `union-attr` + 4 `arg-type`. Es el mismo
  comportamiento: el ternario ya garantizaba dict o `{}`, y `_num` es
  exactamente el `try: float(...) except: None` que estaba inline.

### 5. `vigilante/analisis.py` — Optional tratado de verdad

`evalua_zona`: `float((vig.get(lado) or {}).get("nivel"))` →
`float(prev["nivel"]) if isinstance(prev, dict) else None`. Mismo resultado
(antes un valor ausente daba `TypeError`/`KeyError`, ambos capturados por el
  `except` de la zona y con desenlace `ant = None`), pero ahora el `None` es
  explicito en lugar de un accidente.

### 6. `vigilante/mercado.py` — suma sobre lista con `None`

`_atr_serie`: con `trs: list[float | None]` mypy exigio explicitar el filtro:
`sum(x for x in trs[i-n:i] if x is not None)`. El `all(x is not None ...)` de
la linea anterior ya garantizaba que no hay `None` en la ventana: el valor
calculado no cambia.

## BUG REAL encontrado (arreglado): `mensaje_pila` con `er = None`

`vigilante/mercado.py`, bloque de "Reaccion probable" (~linea 635 antes del
arreglo):

```python
er = h1.get("er")   # eficiencia() puede devolver None si el 1H no tiene 30+ velas
"er": 0 if (er if er is not None else 0.2) < 0.15 else (1 if er < 0.4 else 2)
#                                                       ^^^^^ er sin el fallback
```

La primera comparacion aplicaba el fallback y la segunda no: con `er is None`
reventaba con `TypeError: '<' not supported between instances of
'NoneType' and 'float'`, el `except Exception: pass` de arriba se lo comia y
el mensaje perdia el bloque completo de "Reaccion probable" (y el vector de
`prob_reaccion`).

Lo detecto mypy como
`Unsupported operand types for < ("float" and "None")` justo en esa linea.
Repro (fuera del repo, sin tocar test_vigilante.py):

```python
msg, _ = mensaje_pila([{"precio": 82992, "razones": ["S1 semanal"]}], 83100,
                      [{"precio": 82992}], [{"precio": 84199}],
                      {"tend": "lateral", "er": None, "rsi": 55, "z": 0.5},
                      {"adx": 25}, 14)
# antes: "Reaccion probable" ausente (195 caracteres)
# ahora: identico al caso er=0.1 (232 caracteres)
```

Arreglo: una sola variable con el fallback, usada en las dos comparaciones
(`er_v = er if er is not None else 0.2`). Es el unico cambio del T4 que
**altera comportamiento**, y solo en el caso que antes estaba roto.

## Categorias que quedan (y por que)

Con el alcance pedido ("no buscar el 100%") **no queda ni un error de mypy**,
pero si deuda que conviene no esconder:

1. **La puerta sigue sin revisar los cuerpos sin anotar.** Los 11 errores de
   la puerta eran solo la punta: el resto de `vigilante/` solo se ve si se
   enciende `--check-untyped-defs`. Como ya quedo limpio en los dos modos,
   encenderlo en `pyproject.toml` (`check_untyped_defs = true`) es el paso
   siguiente natural y no rompe nada hoy. No lo hice para no cambiar la puerta
   en una tarea de endurecimiento.
2. **Casi ninguna firma publica esta anotada.** `vigilante/` arrastra el
   estilo del monolito del que se extrajo (`def klines(interval, limit):`).
   Anotar todo el paquete es otra tarea (mecanica pero larga); aqui solo se
   anotaron las firmas cuyo retorno mypy ya estaba comprobando y las que
   hacian falta para callar un error real.
3. **`Any` a proposito en 8 sitios** (`http_get_json`, `MODELO_TOQUES`,
   `health`, `est`, `_sub`, `_num`, ...): son valores que vienen de JSON o de
   disco y cuya forma no esta garantizada. Ahi el tipado deja de morder por
   diseño; el que viene de la red se valida con `isinstance`/`try`.
4. **Lo que mypy no ve de esta tarea**: `vigilante_cloud.py` y `analysis/`
   (arboles de otros). `vigilante_cloud.py` re-exporta nombres de
   `vigilante/`, asi que estos arreglos tambien le llegan, pero no se midio.

## Ruff (por que mide otras cosas)

- Puerta del repo (`select = ["F"]`, `ignore = ["F841"]`) sobre los tres
  arboles: **All checks passed**.
- Con el select estricto de la tarea (`--select F,E,W,I,B,UP --ignore E501`)
  los tres arboles siguen dando 64 avisos: **todos previos a este T4** y
  concentrados en codigo heredado del monolito (`UP017` por
  `datetime.timezone.utc`, `E402`/`I001` en bloques de import heredados,
  `E741` variable `l`, `B905`/`B904`/`B023`, `UP031`). Ni los imports que se
  anadieron (`typing.Any`, `collections.abc.Callable`) ni ninguna linea
  nueva introducen avisos: el diff de `I001` solo propone ordenar miembros de
  import que ya venian desordenados, y las 11 ocurrencias de `UP017` de
  `collector/collector.py` son los 11 `timezone.utc` que ya existian.
- Los 3 `F` que daba el repo completo al empezar estaban en
  `analysis/paper_report.py` (arbol ajeno). Se resolvieron en paralelo durante
  esta tarea, asi que el repo entero queda hoy en `All checks passed`.

## Verificacion

```
python test_vigilante.py                              -> OK 699 pruebas | FALLOS 0
python collector/test_collector.py                    -> Ran 12 tests ... OK
python -m ruff check --no-cache .                     -> All checks passed!
python -m mypy vigilante/ collector/ tools/           -> Success: no issues found in 18 source files (exit 0)
python -m mypy --check-untyped-defs vigilante/ collector/ tools/
                                                      -> Success: no issues found in 18 source files (exit 0)
python -m compileall -q vigilante collector tools     -> sin salida, exit 0
cd analysis && python test_hold_model.py              -> OK (5)
cd analysis && python test_decision_engine.py         -> OK (18)
cd analysis && python test_pipeline.py                -> OK (7)
```

Nota sobre la salida de `python -m mypy vigilante/ collector/ tools/`: ademas
del `Success` final aparecen *notes* `annotation-unchecked` ("by default the
bodies of untyped functions are not checked"). Son informativas, **no son
errores**: el exit code es 0. Avisan de que una variable anotada dentro de una
funcion sin anotar no se comprueba con la configuracion actual; por eso el
inventario estricto de arriba se mide con `--check-untyped-defs`, que tambien
queda en 0.
