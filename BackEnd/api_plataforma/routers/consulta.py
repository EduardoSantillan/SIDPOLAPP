"""Consulta de resultados (RF-19 a RF-23). Solo lectura, para los tres roles. Devuelve lo ya calculado: no recalcula nada."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api_plataforma.schemas import DistritoOut, FichaOut, ResumenDistritoOut, SerieOut, TablaOut
from api_plataforma.servicios import resultados as R
from api_plataforma.servicios.resultados import Periodo, Target
from common.aviso import AVISO
from common.db import get_db
from common.errores import ErrorNegocio
from common.seguridad import requiere_rol

router = APIRouter(tags=["consulta"], dependencies=[Depends(requiere_rol("usuario", "analista", "administrador"))])

ORDENES = ("distrito", "registradas", *R.ESTRATEGIAS)


def _error_promedio(met: dict) -> list[dict]:
    """Error en denuncias (MAE) y MASE de cada forma de estimar, siempre en el mismo orden."""
    filas = []
    for est in R.ESTRATEGIAS:
        m = met.get((est, R.PRINCIPAL[est]), {})
        mase, motivo = m.get("MASE", (None, None))
        mae = m.get("MAE", (None, None))[0]
        filas.append({"estrategia": est, "etiqueta": R.ETIQUETAS[est], "denuncias_por_mes": R.redondear(mae, 1),
                      "mase": R.redondear(mase, 2), "motivo": motivo})
    return filas


@router.get("/distritos", response_model=list[DistritoOut])
def listar_distritos(db: Session = Depends(get_db)):
    return [{"ubigeo": d["ubigeo"], "nombre": d["nombre"]} for d in R.distritos(db)]


# La ruta fija /distritos/resumen va antes que /distritos/{ubigeo}/…
@router.get("/distritos/resumen", response_model=TablaOut)
def tabla(target: Target, periodo: Periodo = "todo", ubigeos: str | None = None, orden: str = "distrito", dir: Literal["asc", "desc"] = "asc",
          ejecucion_id: str | None = None, db: Session = Depends(get_db)):
    if orden not in ORDENES:
        raise ErrorNegocio(422, "ORDEN_NO_VALIDO", "No se puede ordenar por esa columna.")
    lista = R.lista_ubigeos(db, ubigeos)
    ej = R.ejecucion_para(db, target, ejecucion_id)
    ultimo = R.meses_evaluados(db, ej, periodo)[-1]
    met = R.metricas(db, ej, periodo, lista)
    obs = {u: y for u, y in db.execute(
        text("SELECT ubigeo, y FROM observacion_mensual WHERE version_id = :v AND target = :t AND fecha = :f"),
        {"v": ej["version_id"], "t": target, "f": ultimo}).all()}
    filas = [{"ubigeo": d["ubigeo"], "distrito": d["nombre"], "registradas_ultimo_mes": obs.get(d["ubigeo"]),
              "error_promedio": _error_promedio(met.get(d["ubigeo"], {}))}
             for d in R.distritos(db) if lista is None or d["ubigeo"] in lista]
    if orden != "distrito":  # solo a pedido de la persona; por defecto es alfabético
        def valor(f):
            if orden == "registradas":
                return f["registradas_ultimo_mes"]
            return next(e["denuncias_por_mes"] for e in f["error_promedio"] if e["estrategia"] == orden)
        con, sin = [f for f in filas if valor(f) is not None], [f for f in filas if valor(f) is None]
        filas = sorted(con, key=valor, reverse=dir == "desc") + sin
    elif dir == "desc":
        filas.reverse()
    return {"target": target, "periodo": periodo, "ultimo_mes": ultimo.isoformat(), "mase_explicacion": R.MASE_EXPLICACION,
            "filas": filas, "ejecucion_id": str(ej["ejecucion_id"]), "aviso": AVISO}


@router.get("/distritos/{ubigeo}/resumen", response_model=ResumenDistritoOut)
def resumen(ubigeo: str, target: Target, periodo: Periodo = "todo", ejecucion_id: str | None = None, db: Session = Depends(get_db)):
    nombre = R.distrito(db, ubigeo)
    ej = R.ejecucion_para(db, target, ejecucion_id)
    meses = R.meses_evaluados(db, ej, periodo, ubigeo)
    ultimo = meses[-1]
    estimado = {est: v for est, v in db.execute(
        text("SELECT estrategia, estimado FROM resultado_pronostico WHERE ejecucion_id = :e AND ubigeo = :u AND fecha_objetivo = :f AND variante IN ('E1','base')"),
        {"e": ej["ejecucion_id"], "u": ubigeo, "f": ultimo}).all()}
    registradas = db.execute(text("SELECT y FROM observacion_mensual WHERE version_id = :v AND target = :t AND ubigeo = :u AND fecha = :f"),
                             {"v": ej["version_id"], "t": target, "u": ubigeo, "f": ultimo}).scalar()
    estimaciones = [{"estrategia": e, "etiqueta": R.ETIQUETAS[e], "valor": round(estimado[e]), "diferencia": round(estimado[e]) - registradas}
                    for e in R.ESTRATEGIAS if e in estimado]
    rango = db.execute(
        text("SELECT min(y), max(y) FROM (SELECT y FROM observacion_mensual WHERE version_id = :v AND target = :t AND ubigeo = :u AND fecha <= :f "
             "ORDER BY fecha DESC LIMIT 12) x"), {"v": ej["version_id"], "t": target, "u": ubigeo, "f": ultimo}).one()
    met = R.metricas(db, ej, periodo, [ubigeo]).get(ubigeo, {})
    return {"ubigeo": ubigeo, "distrito": nombre, "target": target, "periodo": periodo,
            "ultimo_mes": ultimo.isoformat(), "registradas_ultimo_mes": registradas, "estimaciones_ultimo_mes": estimaciones,
            "error_promedio": _error_promedio(met), "mase_explicacion": R.MASE_EXPLICACION, "meses_evaluados": len(meses),
            "rango_habitual": {"min": rango[0], "max": rango[1], "meses": 12}, "ejecucion_id": str(ej["ejecucion_id"]), "aviso": AVISO}


@router.get("/distritos/{ubigeo}/serie", response_model=SerieOut)
def serie(ubigeo: str, target: Target, periodo: Periodo = "todo", ejecucion_id: str | None = None, db: Session = Depends(get_db)):
    R.distrito(db, ubigeo)
    ej = R.ejecucion_para(db, target, ejecucion_id)
    sql = "SELECT fecha, y, regimen FROM observacion_mensual WHERE version_id = :v AND target = :t AND ubigeo = :u"
    p = {"v": ej["version_id"], "t": target, "u": ubigeo}
    if periodo in R.REGIMEN_BD:
        sql += " AND regimen = :r"
        p["r"] = R.REGIMEN_BD[periodo]
    est: dict = {}
    for f, e, v in db.execute(
            text("SELECT fecha_objetivo, estrategia, estimado FROM resultado_pronostico WHERE ejecucion_id = :e AND ubigeo = :u AND variante IN ('E1','base')"),
            {"e": ej["ejecucion_id"], "u": ubigeo}).all():
        est.setdefault(f, {})[e] = round(v)
    puntos = [{"fecha": f.isoformat(), "registradas": y, "regimen": R.REGIMEN_API[r], "estimaciones": est.get(f, {})}
              for f, y, r in db.execute(text(sql + " ORDER BY fecha"), p).all()]
    return {"ubigeo": ubigeo, "target": target, "periodo": periodo,
            "cambio_registro": {"fecha": ej["corte"], "texto": "Desde nov 2024 cambió la forma de registrar"},
            "puntos": puntos, "estrategias": [{"estrategia": e, "etiqueta": R.ETIQUETAS[e]} for e in R.ESTRATEGIAS],
            "ejecucion_id": str(ej["ejecucion_id"]), "aviso": AVISO}


@router.get("/ficha", response_model=FichaOut)
def ficha(db: Session = Depends(get_db)):
    """Ficha informativa (RF-23) de la configuración de la última ejecución completada; si no hay, de la última aprobada."""
    f = db.execute(text(
        "SELECT f.secciones, f.version, c.nombre, c.version AS cfg_version, c.sha256 FROM ficha_informativa f JOIN configuracion_experimento c USING (config_id) "
        "WHERE c.aprobada_en IS NOT NULL ORDER BY (SELECT max(e.fin) FROM ejecucion e WHERE e.config_id = c.config_id AND e.estado = 'completada') DESC NULLS LAST, "
        "c.aprobada_en DESC, c.version DESC, f.version DESC LIMIT 1")).mappings().first()
    if not f:
        raise ErrorNegocio(404, "SIN_FICHA", "Todavía no hay una ficha informativa.")
    return {"secciones": f["secciones"], "version_ficha": f["version"],
            "configuracion": {"nombre": f["nombre"], "version": f["cfg_version"], "sha256": f["sha256"]}, "aviso": AVISO}
