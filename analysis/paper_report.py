"""paper_report.py - resumen HONESTO del paper trading invisible (solo lectura).

Lee las operaciones de papel cerradas del estado del Vigilante (archivo local o
rama `estado` de GitHub, publica, sin token) y calcula el rendimiento medido:

- numero de operaciones, ganadas/perdidas y win rate,
- R-multiple total, medio, mejor y peor,
- Sharpe por operacion (media / desviacion, NO anualizado),
- max drawdown del banco y de la curva de PnL acumulado,
- PnL por semana (ISO) y por mes,
- desglose por lado (LONG/SHORT) y por tipo de cierre (TP/SL/LIQ/BE/REBORN).

Reglas del modulo (honestidad ante todo):

- NUNCA inventa un dato: lo que no existe se marca ``n/d`` (no dato) y se dice
  por que en ``notas``.
- NUNCA rompe: una entrada corrupta se descarta y se declara, no aborta.
- No ejecuta ordenes, no usa claves y no escribe el estado: es solo lectura.

Uso:

    python analysis/paper_report.py --estado estado.json --out-json analysis/data/paper_summary.json
    python analysis/paper_report.py            # sin archivo local: baja la rama estado
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

ND = "n/d"  # etiqueta de "no dato": se respeta, no se rellena con ceros
BOT = "paper_report"
VERSION = 1
URL_ESTADO = "https://raw.githubusercontent.com/LuiferX/vigilante-btc/estado/estado.json"

KEYS_CERRADAS = ("paper_cerradas", "cerradas", "paper_closed", "trades_cerrados")
KEYS_JOURNAL = ("journal", "diario", "paper_journal")
KEYS_CONTENEDOR = ("paper", "papel")
KEYS_PNL = ("pnl", "PnL", "profit", "ganancia")
KEYS_R = ("r", "R", "r_mult", "r_multiple")
KEYS_DIR = ("dir", "lado", "side", "direccion")
KEYS_RES = ("res", "resultado", "cierre", "donde")
KEYS_T = ("t", "ts", "fecha", "time", "cerrado")
KEYS_RIESGO = ("riesgo", "risk", "risk0")

MIN_SHARPE = 5          # paper.sharpe tampoco opina con menos de 5 datos
MAX_GUARDADAS = 100     # vigilante/paper.py guarda solo las ultimas 100 cerradas
UMBRAL_MUESTRA = 30     # por debajo de esto: muestra chica, no es edge

DISCLAIMER = (
    "Paper trading invisible: banco virtual, sin ordenes reales y sin dinero. "
    "Las cifras salen solo de las operaciones cerradas guardadas en el estado. "
    "Lo que no existe se marca 'n/d'. Con pocas operaciones esto es muestra, no edge."
)


# ------------------------------------------------------------------ utilidades
def _clave_primera(dato: dict, claves: tuple[str, ...]) -> Any:
    for k in claves:
        if k in dato and dato[k] is not None:
            return dato[k]
    return None


def _num(valor: Any) -> float | None:
    """Float tolerante (acepta '1,5'). None si no es numero: nunca adivina."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        txt = valor.strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None
    return None


def _fecha(valor: Any) -> datetime | None:
    """datetime consciente de zona horaria (UTC por defecto) o None."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        seg = float(valor)
        if seg > 1e12:  # milisegundos
            seg /= 1000.0
        if 1e8 < seg < 1e11:
            try:
                return datetime.fromtimestamp(seg, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return None
        return None
    if isinstance(valor, str):
        txt = valor.strip().replace("Z", "+00:00")
        if not txt:
            return None
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _redondear(valor: Any, dec: int = 2) -> Any:
    """Redondea si hay numero; si no hay dato devuelve la etiqueta n/d."""
    if valor is None:
        return ND
    return round(float(valor), dec)


def sharpe_por_op(valores: list[float]) -> float | None:
    """Sharpe por operacion (Rf=0): media / desviacion. None con <5 datos."""
    limpios = [v for v in valores if isinstance(v, (int, float))]
    if len(limpios) < MIN_SHARPE:
        return None
    media = sum(limpios) / len(limpios)
    var = sum((v - media) ** 2 for v in limpios) / len(limpios)
    if var <= 0:
        return None
    return round(media / math.sqrt(var), 2)


def drawdown_curva(valores: list[float]) -> tuple[float, int, int] | None:
    """Max caida pico->valle de una curva. (caida, idx_pico, idx_valle) o None."""
    if not valores:
        return None
    pico = valores[0]
    idx_pico = 0
    peor = 0.0
    par = (0, 0)
    for i, v in enumerate(valores):
        if v > pico:
            pico, idx_pico = v, i
        caida = pico - v
        if caida > peor:
            peor, par = caida, (idx_pico, i)
    return (round(peor, 2), par[0], par[1])


def clave_semana(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def clave_mes(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# ------------------------------------------------------------------ lectura
def leer_estado(
    ruta: str | None = None,
    url: str | None = None,
    timeout: float = 20.0,
) -> tuple[dict | None, str, str | None]:
    """Lee el estado: primero el archivo local, si no, la rama estado de GitHub.

    Devuelve ``(estado, fuente, error)``. ``estado`` es None solo si no se pudo
    leer de ningun lado; el motivo queda en ``error`` y NUNCA lanza. La ``fuente``
    dice de donde salio (local:<ruta> o github:<url> [sin archivo local <ruta>]).
    """
    if ruta and os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return None, f"local:{ruta}", f"estado local ilegible ({type(exc).__name__})"
        if not isinstance(data, dict):
            return None, f"local:{ruta}", "el estado local no es un objeto JSON"
        return data, f"local:{ruta}", None

    destino = url or URL_ESTADO
    sin_local = f" (sin archivo local: {ruta})" if ruta else ""
    try:
        pedido = urllib.request.Request(
            destino, headers={"User-Agent": f"{BOT}/{VERSION}"}
        )
        with urllib.request.urlopen(pedido, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return (
            None,
            f"github:{destino}{sin_local}",
            f"descarga fallida ({type(exc).__name__})",
        )
    if not isinstance(data, dict):
        return None, f"github:{destino}{sin_local}", "el estado descargado no es un objeto JSON"
    return data, f"github:{destino}{sin_local}", None


def _lista_de(estado: dict, claves: tuple[str, ...]) -> tuple[str | None, list]:
    """Busca la lista de operaciones en el estado (tambien anidada en paper/papel)."""
    for k in claves:
        valor = estado.get(k)
        if isinstance(valor, list) and valor:
            return k, valor
    for cont in KEYS_CONTENEDOR:
        sub = estado.get(cont)
        if isinstance(sub, dict):
            for k in claves:
                valor = sub.get(k)
                if isinstance(valor, list) and valor:
                    return f"{cont}.{k}", valor
    return None, []


def _normaliza(dato: dict, idx: int, meta: dict) -> dict:
    pnl = _num(_clave_primera(dato, KEYS_PNL))
    r = _num(_clave_primera(dato, KEYS_R))
    r_derivada = False
    if r is None and pnl is not None:
        riesgo = _num(_clave_primera(dato, KEYS_RIESGO))
        if riesgo:
            r = pnl / riesgo
            r_derivada = True
            meta["r_derivadas"] += 1
    if pnl is None:
        meta["sin_pnl"] += 1
    if r is None:
        meta["sin_r"] += 1
    dt = _fecha(_clave_primera(dato, KEYS_T))
    if dt is None:
        meta["sin_fecha"] += 1
    return {
        "i": idx,
        "dir": str(_clave_primera(dato, KEYS_DIR) or "?"),
        "res": str(_clave_primera(dato, KEYS_RES) or "?"),
        "pnl": pnl,
        "r": r,
        "r_derivada": r_derivada,
        "dt": dt,
    }


def extraer_ops(estado: dict) -> tuple[list[dict], dict]:
    """Normaliza las operaciones cerradas del estado. (ops, meta).

    Preferencia: ``paper_cerradas``. Si no existe, ``journal`` (guarda r pero no
    pnl: se declara, no se inventa el PnL). Las entradas que no son objetos o no
    tienen ningun dato util se descartan y se cuentan en ``meta['descartadas']``.
    """
    meta = {
        "clave": None,
        "origen": "estado",
        "con_pnl": True,
        "n_brutas": 0,
        "descartadas": 0,
        "duplicados": 0,
        "sin_fecha": 0,
        "sin_pnl": 0,
        "sin_r": 0,
        "r_derivadas": 0,
    }
    clave, brutas = _lista_de(estado, KEYS_CERRADAS)
    if not brutas:
        clave, brutas = _lista_de(estado, KEYS_JOURNAL)
        meta["origen"] = "journal"
        meta["con_pnl"] = False
    meta["clave"] = clave
    meta["n_brutas"] = len(brutas)

    ops: list[dict] = []
    vistas: dict[tuple, int] = {}
    for i, dato in enumerate(brutas):
        if not isinstance(dato, dict):
            meta["descartadas"] += 1  # basura: se declara, no rompe
            continue
        op = _normaliza(dato, i, meta)
        if op["pnl"] is None and op["r"] is None:
            meta["descartadas"] += 1
            continue
        ops.append(op)
        huella = (
            op["dir"],
            op["res"],
            op["pnl"],
            op["r"],
            op["dt"].isoformat() if op["dt"] else None,
        )
        if huella in vistas:
            meta["duplicados"] += 1
        vistas[huella] = vistas.get(huella, 0) + 1

    # orden temporal (las sin fecha se quedan al final, en su orden original)
    ops.sort(key=lambda o: (0, o["dt"].timestamp(), o["i"]) if o["dt"] else (1, 0.0, o["i"]))
    return ops, meta


# ------------------------------------------------------------------ metricas
def _racha(pnls: list[float]) -> tuple[int, str]:
    if not pnls:
        return 0, ND
    signo = 1 if pnls[-1] > 0 else (-1 if pnls[-1] < 0 else 0)
    if signo == 0:
        return 0, "neutra"
    n = 0
    for v in reversed(pnls):
        if (v > 0) if signo == 1 else (v < 0):
            n += 1
        else:
            break
    if signo == 1:
        return n, f"{n} ganada" if n == 1 else f"{n} ganadas"
    return n, f"{n} perdida" if n == 1 else f"{n} perdidas"


def metricas(ops: list[dict]) -> dict:
    """Estadisticas de un grupo de operaciones. Lo que no haya es n/d."""
    n = len(ops)
    pnls = [o["pnl"] for o in ops if o["pnl"] is not None]
    rs = [o["r"] for o in ops if o["r"] is not None]
    ganadas = sum(1 for v in pnls if v > 0)
    perdidas = sum(1 for v in pnls if v < 0)
    neutras = sum(1 for v in pnls if v == 0)

    bruto_win = sum(v for v in pnls if v > 0)
    bruto_loss = sum(-v for v in pnls if v < 0)
    if bruto_loss > 0:
        pf: Any = round(bruto_win / bruto_loss, 2)
    else:
        pf = ND

    curva: list[float] = []
    acum = 0.0
    for v in pnls:
        acum += v
        curva.append(round(acum, 2))
    dd = drawdown_curva(curva)

    n_racha, txt_racha = _racha(pnls)
    return {
        "n": n,
        "ganadas": ganadas if pnls else ND,
        "perdidas": perdidas if pnls else ND,
        "neutras": neutras if pnls else ND,
        "win_rate": round(100.0 * ganadas / n, 1) if (pnls and n) else ND,
        "pnl_total": _redondear(sum(pnls)) if pnls else ND,
        "pnl_medio": _redondear(sum(pnls) / len(pnls)) if pnls else ND,
        "pnl_mejor": _redondear(max(pnls)) if pnls else ND,
        "pnl_peor": _redondear(min(pnls)) if pnls else ND,
        "r_total": _redondear(sum(rs)) if rs else ND,
        "r_medio": _redondear(sum(rs) / len(rs), 3) if rs else ND,
        "r_mejor": _redondear(max(rs)) if rs else ND,
        "r_peor": _redondear(min(rs)) if rs else ND,
        "sharpe": _redondear(sharpe_por_op(rs)),
        "sharpe_n": len(rs),
        "profit_factor": pf,
        "racha": n_racha,
        "racha_txt": txt_racha,
        "max_dd_curva_usdt": dd[0] if dd else ND,
        "curva_pnl": curva if pnls else [],
    }


def _por_grupo(ops: list[dict], clave_fn) -> dict:
    grupos: dict[str, list[dict]] = {}
    for op in ops:
        if op["dt"] is None:
            continue
        grupos.setdefault(clave_fn(op["dt"]), []).append(op)
    return {k: metricas(v) for k, v in sorted(grupos.items())}


def _por_campo(ops: list[dict], campo: str) -> dict:
    grupos: dict[str, list[dict]] = {}
    for op in ops:
        grupos.setdefault(op[campo], []).append(op)
    return {k: metricas(v) for k, v in sorted(grupos.items())}


# ------------------------------------------------------------------ informe
def construir_reporte(estado: dict | None, fuente: str, error: str | None = None) -> dict:
    """Arma el informe completo. Con estado=None devuelve un informe vacio honesto."""
    notas: list[str] = []
    ops: list[dict] = []
    meta: dict = {
        "clave": None,
        "origen": "estado",
        "con_pnl": True,
        "n_brutas": 0,
        "descartadas": 0,
        "duplicados": 0,
        "sin_fecha": 0,
        "sin_pnl": 0,
        "sin_r": 0,
        "r_derivadas": 0,
    }
    banco = None
    banco_pico = None
    abiertas = 0
    dia = None

    if error:
        notas.append(f"No se pudo leer el estado: {error}.")
    if estado is not None:
        if fuente.startswith("github:"):
            notas.append("Fuente: rama estado de GitHub (publica, solo lectura, sin token).")
        ops, meta = extraer_ops(estado)
        banco = _num(estado.get("banco") or estado.get("bank") or estado.get("paper_banco"))
        banco_pico = _num(estado.get("banco_pico") or estado.get("banco_max"))
        crudas = estado.get("paper_abiertas")
        abiertas = len([x for x in crudas if isinstance(x, dict)]) if isinstance(crudas, list) else 0
        papel_dia = estado.get("paper_dia")
        if isinstance(papel_dia, dict):
            dia = {
                "fecha": str(papel_dia.get("fecha") or ND),
                "pnl": _redondear(_num(papel_dia.get("pnl"))),
            }

    if ops:
        if meta["descartadas"]:
            notas.append(
                f"{meta['descartadas']} entradas sin datos utiles o corruptas: "
                "se descartan y se declaran, no rompen el informe."
            )
        if meta["duplicados"]:
            notas.append(
                f"duplicados exactos detectados: {meta['duplicados']} "
                "(mismo dir/res/pnl/r/fecha). Se cuentan todas: no se deduplican "
                "en silencio porque no se puede saber si es doble registro."
            )
        if meta["sin_fecha"]:
            notas.append(
                f"{meta['sin_fecha']} operaciones sin fecha: quedan fuera del PnL "
                "por semana y por mes."
            )
        if meta["r_derivadas"]:
            notas.append(f"{meta['r_derivadas']} operaciones sin R: se calculo pnl/riesgo.")
        if meta["sin_pnl"]:
            notas.append("Hay operaciones sin PnL: win rate y profit factor no las cubren.")
        if len(ops) >= MAX_GUARDADAS:
            notas.append(
                f"El estado guarda solo las ultimas {MAX_GUARDADAS} cerradas: "
                "puede haber historia previa que este informe no ve."
            )
        if any(o["res"].upper() == "REBORN" for o in ops):
            notas.append(
                "Hay cierres REBORN (el banco se reinicio a 100 USDT): la suma de "
                "PnL no es la equity real de la cuenta."
            )
        if meta["origen"] == "journal" or not meta["con_pnl"]:
            notas.append(
                "Fuente journal: no guarda PnL (guarda R), asi que PnL total, "
                "win rate y profit factor son n/d."
            )
        if len(ops) < UMBRAL_MUESTRA:
            notas.append(
                f"Muestra chica ({len(ops)} operaciones): esto es descripcion, no "
                "una evaluacion de edge."
            )
    else:
        notas.append("Sin operaciones cerradas: no hay nada que medir todavia.")

    # metricas globales
    glob = metricas(ops)
    glob["banco"] = _redondear(banco)
    glob["banco_inicio_estimado"] = ND
    glob["max_dd_banco_pct"] = ND

    curva = glob.get("curva_pnl") or []
    if banco_pico and banco is not None and banco_pico > 0:
        glob["max_dd_banco_pct"] = round(100.0 * (banco_pico - banco) / banco_pico, 2)
    elif banco is not None and curva:
        notas.append(
            "banco_pico no esta en el estado (el reset REBORN lo borra): el drawdown "
            "del banco es n/d; se informa el de la curva de PnL."
        )
    if banco is not None and curva and not any(
        o["res"].upper() == "REBORN" for o in ops
    ):
        base = banco - curva[-1]
        glob["banco_inicio_estimado"] = round(base, 2)
        equity = [base + c for c in curva]
        dd_eq = drawdown_curva(equity)
        glob["max_dd_curva_pct"] = dd_eq[0] / equity[dd_eq[1]] * 100.0 if dd_eq else ND
        glob["max_dd_curva_pct"] = (
            round(glob["max_dd_curva_pct"], 2)
            if isinstance(glob["max_dd_curva_pct"], float)
            else ND
        )
        notas.append(
            "El drawdown en % de la curva es una estimacion: supone banco = inicio + "
            "PnL de papel y que no hubo reset REBORN."
        )
    else:
        glob["max_dd_curva_pct"] = ND

    informe = {
        "bot": BOT,
        "version": VERSION,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "fuente": {
            "tipo": "local" if fuente.startswith("local:") else "github",
            "detalle": fuente,
            "clave_cerradas": meta["clave"],
            "origen_datos": meta["origen"],
            "error": error,
        },
        "sin_datos": not ops,
        "resumen": glob,
        "por_semana": _por_grupo(ops, clave_semana),
        "por_mes": _por_grupo(ops, clave_mes),
        "por_lado": _por_campo(ops, "dir"),
        "por_res": _por_campo(ops, "res"),
        "abiertas": abiertas,
        "dia": dia,
        "meta": meta,
        "notas": notas,
        "disclaimer": DISCLAIMER,
        "nd": ND,
    }
    informe["texto"] = resumen_texto(informe)
    return informe


# ------------------------------------------------------------------ texto
def _txt_num(valor: Any, dec: int = 2, signo: bool = False) -> str:
    if valor is None or valor == ND:
        return ND
    if isinstance(valor, str):
        return valor
    fmt = f"{{:+.{dec}f}}" if signo else f"{{:.{dec}f}}"
    return fmt.format(float(valor))


def _txt_grupo(nombre: str, grupos: dict, dec: int = 2) -> list[str]:
    if not grupos:
        return [f"{nombre}: {ND}"]
    filas = []
    for k, g in grupos.items():
        n = g.get("n", 0)
        filas.append(
            f"  {k}: n={n} | R {_txt_num(g.get('r_total'), 1, True)} | "
            f"PnL {_txt_num(g.get('pnl_total'), 2, True)}"
        )
    return [f"{nombre}:"] + filas


def resumen_texto(informe: dict) -> str:
    """Version legible del informe (para consola y para el dashboard)."""
    r = informe["resumen"]
    f = informe["fuente"]
    linea = [
        "PAPEL XLX - resumen honesto (solo lectura, sin ordenes)",
        f"fuente: {f['detalle']} | clave: {f['clave_cerradas'] or ND} | "
        f"generado {informe['generado']}",
    ]
    if informe["sin_datos"]:
        linea.append("sin operaciones cerradas: no hay rendimiento que medir.")
    else:
        linea.append(
            f"operaciones: {r['n']} | ganadas {r['ganadas']} | perdidas {r['perdidas']} | "
            f"neutras {r['neutras']} | win rate {_txt_num(r['win_rate'], 1)}%"
        )
        linea.append(
            f"R: total {_txt_num(r['r_total'], 2, True)} | medio {_txt_num(r['r_medio'], 3, True)}"
            f" | mejor {_txt_num(r['r_mejor'], 2, True)} | peor {_txt_num(r['r_peor'], 2, True)}"
        )
        linea.append(
            f"PnL de cerradas: total {_txt_num(r['pnl_total'], 2, True)} | "
            f"medio {_txt_num(r['pnl_medio'], 2, True)} | profit factor {r['profit_factor']}"
        )
        linea.append(
            f"Sharpe por operacion (no anualizado): {_txt_num(r['sharpe'], 2, True)} "
            f"(n={r['sharpe_n']})"
        )
        dd_banco = r["max_dd_banco_pct"]
        dd_banco_txt = ND if dd_banco == ND else f"{_txt_num(dd_banco, 2)}%"
        dd_curva_pct = r["max_dd_curva_pct"]
        dd_curva_txt = ND if dd_curva_pct == ND else f"{_txt_num(dd_curva_pct, 2)}%"
        linea.append(
            f"Max drawdown: banco {dd_banco_txt} | "
            f"curva de PnL {_txt_num(r['max_dd_curva_usdt'], 2)} USDT "
            f"({dd_curva_txt})"
        )
        linea.append(
            f"Banco: {_txt_num(r['banco'])} USDT | abiertas ahora: {informe['abiertas']}"
        )
        linea.extend(_txt_grupo("por semana", informe["por_semana"]))
        linea.extend(_txt_grupo("por mes", informe["por_mes"]))
        linea.extend(_txt_grupo("por lado", informe["por_lado"]))
        linea.extend(_txt_grupo("por cierre", informe["por_res"]))
    if informe["notas"]:
        linea.append("notas:")
        linea.extend(f"  - {n}" for n in informe["notas"])
    linea.append(f"n/d = no dato (no se inventa). {informe['disclaimer']}")
    return "\n".join(linea)


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Resumen honesto del paper trading invisible (solo lectura, sin ordenes)"
    )
    ap.add_argument(
        "--estado",
        default=None,
        help="ruta al estado.json local; si no existe, se baja de la rama estado",
    )
    ap.add_argument("--url", default=URL_ESTADO, help="URL raw del estado (publica, sin token)")
    ap.add_argument("--timeout", type=float, default=20.0, help="segundos de espera de red")
    ap.add_argument("--out-json", default=None, help="ruta del JSON de salida")
    args = ap.parse_args(argv)

    estado, fuente, error = leer_estado(args.estado, args.url, timeout=args.timeout)
    informe = construir_reporte(estado, fuente, error)
    print(informe["texto"])

    if args.out_json:
        try:
            carpeta = os.path.dirname(os.path.abspath(args.out_json))
            os.makedirs(carpeta, exist_ok=True)
            with open(args.out_json, "w", encoding="utf-8") as fh:
                json.dump(informe, fh, ensure_ascii=False, indent=2)
        except (OSError, ValueError) as exc:
            print(f"[paper_report] no se pudo escribir {args.out_json}: {exc}", file=sys.stderr)
            return 1
        print(f"[paper_report] JSON escrito en {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
