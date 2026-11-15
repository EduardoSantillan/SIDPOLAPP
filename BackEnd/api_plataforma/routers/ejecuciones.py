from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api_plataforma.schemas import EjecucionesOut, EjecucionIniciadaOut, EjecucionOut
from api_plataforma.servicios import auditoria, modelado
from common.db import get_db
from common.errores import ErrorNegocio
from common.seguridad import requiere_rol

router = APIRouter(prefix="/ejecuciones", tags=["ejecuciones"])

BASE = ("SELECT e.ejecucion_id, e.target, e.estado, e.motivo_fallo, e.inicio, e.fin, v.nombre_archivo, v.periodo_corte, v.version, "
        "c.nombre AS config_nombre, c.version AS config_version, c.sha256 AS config_sha256 "
        "FROM ejecucion e JOIN version_datos v USING (version_id) JOIN configuracion_experimento c USING (config_id)")


class EjecucionIn(BaseModel):
    version_id: str
    target: Literal["ROBO", "HURTO"]


def _salida(f, detalle: bool = False) -> dict:
    s = {"ejecucion_id": str(f["ejecucion_id"]), "target": f["target"], "estado": f["estado"],
         "version": {"nombre": f["nombre_archivo"], "version": f["version"], "corte": f["periodo_corte"].strftime("%Y-%m")},
         "inicio": f["inicio"].isoformat(), "fin": f["fin"].isoformat() if f["fin"] else None}
    if detalle:
        s["motivo"] = f["motivo_fallo"] if f["estado"] == "fallida" else None
        s["configuracion"] = {"nombre": f["config_nombre"], "version": f["config_version"], "sha256": f["config_sha256"]}
    return s


@router.post("", status_code=202, response_model=EjecucionIniciadaOut)
def iniciar(datos: EjecucionIn, u: dict = Depends(requiere_rol("analista")), db: Session = Depends(get_db)):
    try:
        v = db.execute(text("SELECT version_id, estado FROM version_datos WHERE version_id = CAST(:v AS uuid)"), {"v": datos.version_id}).mappings().first()
    except Exception:
        db.rollback()
        v = None
    if not v:
        raise ErrorNegocio(404, "VERSION_NO_EXISTE", "No existe esa versión de datos.")
    if v["estado"] != "integra":
        motivos = {"con_pendientes": "tiene códigos de distrito sin resolver", "invalida": "no pasó la verificación", "registrada": "todavía no se verificó"}
        raise ErrorNegocio(409, "VERSION_NO_INTEGRA",
                           f"No se puede ejecutar: la versión {motivos.get(v['estado'], 'no está íntegra')}. Pide al administrador que la revise.",
                           {"motivo": v["estado"]})
    cfg = db.execute(text("SELECT config_id FROM configuracion_experimento WHERE aprobada_en IS NOT NULL ORDER BY aprobada_en DESC, version DESC LIMIT 1")).first()
    if not cfg:
        raise ErrorNegocio(409, "CONFIGURACION_NO_APROBADA", "No hay una configuración de experimento aprobada. La plataforma solo ejecuta configuraciones aprobadas.")
    try:
        eid = db.execute(
            text("INSERT INTO ejecucion(version_id, config_id, target, iniciada_por) VALUES (:v,:c,:t,:u) RETURNING ejecucion_id"),
            {"v": v["version_id"], "c": cfg[0], "t": datos.target, "u": u["user_id"]}).scalar()
    except IntegrityError:  # índice único parcial: una en curso por target
        db.rollback()
        raise ErrorNegocio(409, "EJECUCION_EN_CURSO", "Ya hay una ejecución en curso para este delito. Espera a que termine.")
    auditoria.registrar(db, u["user_id"], "iniciar_ejecucion", "ejecucion", eid, {"version_id": datos.version_id, "target": datos.target})
    db.commit()
    if not modelado.ejecutar(str(eid)):
        db.execute(text("UPDATE ejecucion SET estado='fallida', motivo_fallo=:m, fin=now() WHERE ejecucion_id=:e"),
                   {"m": "No se pudo contactar al servicio de modelado. Vuelve a iniciarla en un momento.", "e": eid})
        db.commit()
        raise ErrorNegocio(502, "SERVICIO_NO_DISPONIBLE", "No se pudo iniciar el cálculo ahora. Vuelve a intentarlo en un momento.")
    return {"ejecucion_id": str(eid), "estado": "en_curso"}


@router.get("", response_model=EjecucionesOut)
def historial(limite: int = 50, desde: int = 0, _: dict = Depends(requiere_rol("analista")), db: Session = Depends(get_db)):
    filas = db.execute(text(BASE + " ORDER BY e.inicio DESC LIMIT :l OFFSET :d"), {"l": min(max(limite, 1), 200), "d": max(desde, 0)}).mappings().all()
    return {"items": [_salida(f) for f in filas]}


@router.get("/{ejecucion_id}", response_model=EjecucionOut)
def estado(ejecucion_id: str, _: dict = Depends(requiere_rol("analista")), db: Session = Depends(get_db)):
    try:
        f = db.execute(text(BASE + " WHERE e.ejecucion_id = CAST(:e AS uuid)"), {"e": ejecucion_id}).mappings().first()
    except Exception:
        db.rollback()
        f = None
    if not f:
        raise ErrorNegocio(404, "EJECUCION_NO_EXISTE", "No existe esa ejecución.")
    return _salida(f, detalle=True)
