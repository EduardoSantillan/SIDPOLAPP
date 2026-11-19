"""Lectura de resultados ya calculados (paso 6). Nunca dispara un cálculo: solo consulta lo que dejó una ejecución completada."""
import re
import unicodedata
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from common.errores import ErrorNegocio

Target = Literal["ROBO", "HURTO"]
Periodo = Literal["todo", "antes_nov_2024", "desde_nov_2024"]
Estrategia = Literal["local", "global", "naive1", "naive_estacional"]

ETIQUETAS = {"local": "Modelo por distrito", "global": "Modelo con todo Lima",
             "naive1": "Repetir el mes anterior", "naive_estacional": "Repetir el mismo mes del año pasado"}
ETIQUETA_E1B = "Modelo con todo Lima (ajuste propio)"
ESTRATEGIAS = tuple(ETIQUETAS)                    # orden fijo de presentación; nunca por desempeño
PRINCIPAL = {"local": "E1", "global": "E1", "naive1": "base", "naive_estacional": "base"}
PERIODO_BD = {"todo": "general", "antes_nov_2024": "pre_break", "desde_nov_2024": "post_break"}
REGIMEN_BD = {"antes_nov_2024": "pre_break", "desde_nov_2024": "post_break"}
REGIMEN_API = {"pre_break": "antes_nov_2024", "post_break": "desde_nov_2024"}
MASE_EXPLICACION = ("MASE compara el error con el de repetir el mismo mes del año anterior (escala fija 2018–2022): "
                    "0,64 = 64 % de ese error. Menos es mejor.")
SIGNO_DIFERENCIA = "Diferencia = MASE del modelo con todo Lima − MASE del modelo por distrito. Negativa: el modelo con todo Lima tuvo menos error."
_UBIGEO = re.compile(r"^1501\d{2}$")


_ACENTOS = {"ancon": "Ancón", "jesus": "Jesús", "lurin": "Lurín", "rimac": "Rímac", "martin": "Martín", "maria": "María"}
_MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y"}


def nombre_legible(n: str) -> str:
    """«SANTA MARIA DEL MAR» → «Santa María del Mar». La base guarda el nombre como lo trae el SIDPOL."""
    n = n.replace(" - ", "-")
    palabras = []
    for i, w in enumerate(n.lower().split(" ")):
        w = _ACENTOS.get(w, w if (w in _MINUSCULAS and i) else "-".join(x.capitalize() for x in w.split("-")))
        palabras.append(w)
    return " ".join(palabras)


def clave_orden(nombre: str) -> str:
    return unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode().lower()


def ejecucion_para(db: Session, target: str, ejecucion_id: str | None = None):
    """Última ejecución completada del delito (o la indicada). Sin resultados → 404 con un mensaje que lo dice tal cual."""
    sql = ("SELECT e.ejecucion_id, e.target, e.version_id, e.config_id, e.fin, v.nombre_archivo, v.periodo_corte, v.sha256 AS sha_datos, "
           "c.nombre AS cfg_nombre, c.version AS cfg_version, c.sha256 AS cfg_sha, c.contenido->>'regimen_corte' AS corte "
           "FROM ejecucion e JOIN version_datos v USING (version_id) JOIN configuracion_experimento c USING (config_id) "
           "WHERE e.estado = 'completada' AND e.target = :t")
    if ejecucion_id:
        sql += " AND e.ejecucion_id = CAST(:e AS uuid)"
    try:
        f = db.execute(text(sql + " ORDER BY e.fin DESC LIMIT 1"), {"t": target, "e": ejecucion_id}).mappings().first()
    except Exception:  # identificador mal escrito
        db.rollback()
        f = None
    if not f:
        raise ErrorNegocio(404, "SIN_RESULTADOS", f"Todavía no hay resultados de {'robo' if target == 'ROBO' else 'hurto'}.")
    return f


def distrito(db: Session, ubigeo: str) -> str:
    n = db.execute(text("SELECT nombre FROM distrito WHERE ubigeo = :u"), {"u": ubigeo}).scalar() if _UBIGEO.match(ubigeo) else None
    if n is None:
        raise ErrorNegocio(404, "DISTRITO_NO_EXISTE", "No existe ese distrito.")
    return nombre_legible(n)


def lista_ubigeos(db: Session, valor: str | None) -> list[str] | None:
    if not valor:
        return None
    u = [x.strip() for x in valor.split(",") if x.strip()]
    if not u or len(u) > 43 or any(not _UBIGEO.match(x) for x in u):
        raise ErrorNegocio(422, "UBIGEOS_NO_VALIDOS", "Los distritos indicados no son válidos.")
    return sorted(set(u))


def distritos(db: Session) -> list[dict]:
    filas = db.execute(text("SELECT ubigeo, nombre FROM distrito")).all()
    return [{"ubigeo": u, "nombre": n} for u, n in sorted(((u, nombre_legible(n)) for u, n in filas), key=lambda f: clave_orden(f[1]))]


def meses_evaluados(db: Session, ej, periodo: str, ubigeo: str | None = None) -> list:
    """Meses con resultado del periodo pedido (el periodo se lee del régimen de la serie observada, sin recalcular)."""
    sql = ("SELECT DISTINCT r.fecha_objetivo FROM resultado_pronostico r JOIN observacion_mensual o "
           "ON o.version_id = :v AND o.ubigeo = r.ubigeo AND o.target = :t AND o.fecha = r.fecha_objetivo "
           "WHERE r.ejecucion_id = :e AND r.variante IN ('E1','base')")
    p = {"v": ej["version_id"], "t": ej["target"], "e": ej["ejecucion_id"]}
    if periodo in REGIMEN_BD:
        sql += " AND o.regimen = :reg"
        p["reg"] = REGIMEN_BD[periodo]
    if ubigeo:
        sql += " AND r.ubigeo = :u"
        p["u"] = ubigeo
    m = [f[0] for f in db.execute(text(sql + " ORDER BY 1"), p).all()]
    if not m:
        raise ErrorNegocio(404, "SIN_RESULTADOS", "No hay meses evaluados en ese periodo.")
    return m


def metricas(db: Session, ej, periodo: str, ubigeos: list[str] | None = None, con_e1b: bool = False) -> dict:
    """{ubigeo: {(estrategia, variante): {'MASE': (valor, motivo), 'MAE': ..., 'RMSE': ...}}}."""
    sql = ("SELECT ubigeo, estrategia, variante, metrica, valor, motivo_nulo FROM metrica_desempeno "
           "WHERE ejecucion_id = :e AND periodo = :p AND variante IN ('E1','base'" + (",'E1b'" if con_e1b else "") + ")")
    p = {"e": ej["ejecucion_id"], "p": PERIODO_BD[periodo]}
    if ubigeos:
        sql += " AND ubigeo = ANY(:u)"
        p["u"] = ubigeos
    out: dict = {}
    for u, est, var, met, valor, motivo in db.execute(text(sql), p).all():
        out.setdefault(u, {}).setdefault((est, var), {})[met] = (valor, motivo)
    return out


def meses_sin_dato(db: Session, ej, ubigeo: str | None = None) -> dict | None:
    """Estimaciones de los meses siguientes al último con dato registrado, que la ejecución hizo sin poder compararlas todavía.
    {'datos_hasta': date, 'meses': [date, ...], 'estimaciones': {date: {ubigeo: {estrategia: estimado}}}} o None si la ejecución no los trae.
    Nunca entran a las métricas ni a los meses evaluados."""
    sql = ("SELECT r.ubigeo, r.fecha_origen, r.fecha_objetivo, r.estrategia, r.estimado FROM resultado_pronostico r "
           "WHERE r.ejecucion_id = :e AND r.variante IN ('E1','base') AND r.observado IS NULL "
           "AND NOT EXISTS (SELECT 1 FROM observacion_mensual o WHERE o.version_id = :v AND o.target = :t AND o.ubigeo = r.ubigeo AND o.fecha = r.fecha_objetivo)")
    p = {"e": ej["ejecucion_id"], "v": ej["version_id"], "t": ej["target"]}
    if ubigeo:
        sql += " AND r.ubigeo = :u"
        p["u"] = ubigeo
    filas = db.execute(text(sql), p).all()
    if not filas:
        return None
    est: dict = {}
    for u, _, f, e, v in filas:
        est.setdefault(f, {}).setdefault(u, {})[e] = float(v)
    return {"datos_hasta": max(f[1] for f in filas), "meses": sorted(est), "estimaciones": est}


def filas_sin_dato(db: Session, ej, periodo: str, ubigeo: str | None = None) -> list[dict]:
    """Las estimaciones de los meses sin dato registrado, con la forma de `filas_mensuales` (observado vacío), para las exportaciones.
    Esos meses son posteriores a nov 2024: no se incluyen al pedir solo «antes de nov 2024»."""
    p = None if periodo == "antes_nov_2024" else meses_sin_dato(db, ej, ubigeo)
    if not p:
        return []
    nombres = {d["ubigeo"]: d["nombre"] for d in distritos(db)}
    filas = [{"ubigeo": u, "distrito": nombres[u], "fecha": f, "estrategia": e, "estimado": est[e], "observado": None, "regimen": "post_break"}
             for f, por_distrito in p["estimaciones"].items() for u, est in por_distrito.items() for e in ESTRATEGIAS if e in est]
    orden_d = {u: i for i, u in enumerate(nombres)}
    filas.sort(key=lambda f: (orden_d[f["ubigeo"]], f["fecha"], ESTRATEGIAS.index(f["estrategia"])))
    return filas


def redondear(v, d: int):
    return None if v is None or v != v else round(float(v), d)  # v != v: NaN


def filas_mensuales(db: Session, ej, periodo: str, ubigeo: str | None = None) -> list[dict]:
    """Estimado y registrado de cada mes evaluado, por distrito y estrategia (variantes principales), en orden fijo."""
    sql = ("SELECT r.ubigeo, r.fecha_objetivo AS fecha, r.estrategia, r.estimado, r.observado, o.regimen "
           "FROM resultado_pronostico r JOIN observacion_mensual o ON o.version_id = :v AND o.ubigeo = r.ubigeo AND o.target = :t AND o.fecha = r.fecha_objetivo "
           "WHERE r.ejecucion_id = :e AND r.variante IN ('E1','base')")
    p = {"v": ej["version_id"], "t": ej["target"], "e": ej["ejecucion_id"]}
    if periodo in REGIMEN_BD:
        sql += " AND o.regimen = :reg"
        p["reg"] = REGIMEN_BD[periodo]
    if ubigeo:
        sql += " AND r.ubigeo = :u"
        p["u"] = ubigeo
    nombres = {d["ubigeo"]: d["nombre"] for d in distritos(db)}
    orden_d = {u: i for i, u in enumerate(nombres)}  # distritos() ya viene alfabético
    filas = [dict(f, distrito=nombres[f["ubigeo"]]) for f in db.execute(text(sql), p).mappings().all()]
    filas.sort(key=lambda f: (orden_d[f["ubigeo"]], f["fecha"], ESTRATEGIAS.index(f["estrategia"])))
    return filas
