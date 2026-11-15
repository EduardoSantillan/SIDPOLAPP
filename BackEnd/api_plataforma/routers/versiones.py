import os
import re
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api_plataforma.schemas import PendientesOut, ResueltaOut, VersionDetalleOut, VersionesOut
from api_plataforma.servicios import auditoria, ingesta
from common.config import cargar
from common.db import get_db
from common.errores import ErrorNegocio
from common.panel import sha256_bytes
from common.seguridad import requiere_rol

router = APIRouter(tags=["versiones"])
_PERIODO = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _nombre_seguro(nombre: str | None) -> str:
    n = os.path.basename((nombre or "").replace("\\", "/")).strip()
    return n[:200]


async def _leer_limitado(archivo: UploadFile, tope_mb: int) -> bytes:
    tope = tope_mb * 1024 * 1024
    partes, total = [], 0
    while chunk := await archivo.read(1024 * 1024):
        total += len(chunk)
        if total > tope:
            raise ErrorNegocio(413, "ARCHIVO_MUY_GRANDE", f"El archivo pesa más de {tope_mb} MB.")
        partes.append(chunk)
    return b"".join(partes)


def _fila(db: Session, version_id: str):
    try:
        f = db.execute(
            text("SELECT v.*, u.nombre AS registrada_por_nombre FROM version_datos v JOIN perfil_usuario u ON u.user_id = v.registrada_por "
                 "WHERE v.version_id = CAST(:v AS uuid)"), {"v": version_id}).mappings().first()
    except Exception:
        db.rollback()
        f = None
    if not f:
        raise ErrorNegocio(404, "VERSION_NO_EXISTE", "No existe esa versión de datos.")
    return f


def _controles(db: Session, version_id) -> list[dict]:
    """Controles de la última verificación (todos comparten la hora de su transacción)."""
    filas = db.execute(
        text("SELECT control, aprobado, detalle FROM validacion_version WHERE version_id = :v AND verificada_en = "
             "(SELECT max(verificada_en) FROM validacion_version WHERE version_id = :v) ORDER BY validacion_id"),
        {"v": version_id}).mappings().all()
    return [dict(f) for f in filas]


def _resumen(f) -> dict:
    return {"id": str(f["version_id"]), "nombre_archivo": f["nombre_archivo"], "periodo_corte": f["periodo_corte"].strftime("%Y-%m"),
            "version": f["version"], "estado": f["estado"], "registrada_en": f["registrada_en"].isoformat()}


def _detalle(db: Session, f) -> dict:
    pend = db.execute(text("SELECT count(*) FILTER (WHERE estado = 'abierto'), count(*) FROM registro_pendiente WHERE version_id = :v"),
                      {"v": f["version_id"]}).one()
    return {**_resumen(f), "sha256": f["sha256"], "registrada_por": f["registrada_por_nombre"],
            "controles": _controles(db, f["version_id"]), "pendientes_abiertos": pend[0], "pendientes_total": pend[1]}


@router.post("/versiones", status_code=201, response_model=VersionDetalleOut)
async def registrar(archivo: UploadFile = File(...), periodo_corte: str = Form(...), version: str = Form(...),
                    admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    m = _PERIODO.match(periodo_corte.strip())
    if not m:
        raise ErrorNegocio(422, "PERIODO_INVALIDO", "El periodo de corte debe tener el formato AAAA-MM, por ejemplo 2026-07.")
    corte = date(int(m[1]), int(m[2]), 1)
    nombre = _nombre_seguro(archivo.filename)
    version = version.strip()
    if not nombre.lower().endswith(".csv"):
        raise ErrorNegocio(422, "ARCHIVO_NO_CSV", "Sube un archivo con extensión .csv.")
    if not version or len(version) > 60:
        raise ErrorNegocio(422, "VERSION_INVALIDA", "Indica un nombre de versión de hasta 60 caracteres.")
    contenido = await _leer_limitado(archivo, cargar().max_csv_mb)
    if not contenido.strip():
        raise ErrorNegocio(422, "ARCHIVO_VACIO", "El archivo está vacío.")
    h = sha256_bytes(contenido)

    igual = db.execute(
        text("SELECT version, nombre_archivo, periodo_corte FROM version_datos WHERE sha256 = :h OR (nombre_archivo = :n AND periodo_corte = :c) LIMIT 1"),
        {"h": h, "n": nombre, "c": corte}).mappings().first()
    if igual:
        raise ErrorNegocio(409, "VERSION_DUPLICADA",
                           f"Ya existe la versión «{igual['version']}» ({igual['nombre_archivo']}, corte {igual['periodo_corte']:%Y-%m}) con el mismo archivo o el mismo nombre y periodo. Registra un archivo corregido como versión nueva.")

    carpeta = Path(cargar().ruta_csv)
    carpeta.mkdir(parents=True, exist_ok=True)
    vid = uuid.uuid4()
    ruta = carpeta / f"{vid}.csv"
    ruta.write_bytes(contenido)
    try:
        db.execute(
            text("INSERT INTO version_datos(version_id, nombre_archivo, periodo_corte, version, sha256, ruta_archivo, estado, registrada_por) "
                 "VALUES (:i,:n,:c,:v,:h,:r,'registrada',:u)"),
            {"i": vid, "n": nombre, "c": corte, "v": version, "h": h, "r": str(ruta), "u": admin["user_id"]})
        auditoria.registrar(db, admin["user_id"], "registrar_version", "version_datos", vid, {"sha256": h, "archivo": nombre})
        db.commit()
    except IntegrityError:  # dos subidas simultáneas del mismo archivo
        db.rollback()
        ruta.unlink(missing_ok=True)
        raise ErrorNegocio(409, "VERSION_DUPLICADA", "Esa versión ya fue registrada (quizá por otra subida al mismo tiempo).")

    ingesta.verificar(str(vid))
    return _detalle(db, _fila(db, str(vid)))


@router.get("/versiones", response_model=VersionesOut)
def listar(u: dict = Depends(requiere_rol("administrador", "analista")), db: Session = Depends(get_db)):
    solo_integras = "WHERE estado = 'integra'" if u["rol"] == "analista" else ""
    filas = db.execute(text(f"SELECT * FROM version_datos {solo_integras} ORDER BY periodo_corte DESC, registrada_en DESC")).mappings().all()
    return {"items": [_resumen(f) for f in filas]}


@router.get("/versiones/{version_id}", response_model=VersionDetalleOut)
def detalle(version_id: str, _: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    return _detalle(db, _fila(db, version_id))


@router.post("/versiones/{version_id}/verificar", response_model=VersionDetalleOut)
def verificar(version_id: str, admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    f = _fila(db, version_id)
    ingesta.verificar(str(f["version_id"]))
    auditoria.registrar(db, admin["user_id"], "verificar_version", "version_datos", f["version_id"])
    db.commit()
    return _detalle(db, _fila(db, version_id))


@router.get("/versiones/{version_id}/pendientes", response_model=PendientesOut)
def pendientes(version_id: str, _: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    f = _fila(db, version_id)
    filas = db.execute(
        text("SELECT p.pendiente_id, p.codigo_original, p.n_filas, p.estado, e.ubigeo, e.resuelta_en FROM registro_pendiente p "
             "LEFT JOIN equivalencia_distrito e USING (pendiente_id) WHERE p.version_id = :v ORDER BY p.codigo_original"),
        {"v": f["version_id"]}).mappings().all()
    return {"items": [{"id": str(p["pendiente_id"]), "codigo": p["codigo_original"], "filas": p["n_filas"], "estado": p["estado"],
                       "ubigeo": p["ubigeo"], "resuelta_en": p["resuelta_en"].isoformat() if p["resuelta_en"] else None} for p in filas]}


class EquivalenciaIn(BaseModel):
    ubigeo: str


@router.put("/pendientes/{pendiente_id}/equivalencia", response_model=ResueltaOut)
def resolver(pendiente_id: str, datos: EquivalenciaIn, admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    try:
        p = db.execute(
            text("SELECT p.pendiente_id, p.version_id, p.estado, v.estado AS estado_version FROM registro_pendiente p "
                 "JOIN version_datos v USING (version_id) WHERE p.pendiente_id = CAST(:p AS uuid)"), {"p": pendiente_id}).mappings().first()
    except Exception:
        db.rollback()
        p = None
    if not p:
        raise ErrorNegocio(404, "PENDIENTE_NO_EXISTE", "No existe ese código pendiente.")
    if p["estado_version"] != "con_pendientes" or p["estado"] != "abierto":
        raise ErrorNegocio(409, "YA_RESUELTA", "Este código ya está resuelto o su versión ya no admite cambios.")
    ubigeo = datos.ubigeo.strip()
    if not db.execute(text("SELECT 1 FROM distrito WHERE ubigeo = :u"), {"u": ubigeo}).first():
        raise ErrorNegocio(422, "UBIGEO_DESCONOCIDO", "Ese UBIGEO no corresponde a ninguno de los 43 distritos de Lima Metropolitana.")
    db.execute(text("INSERT INTO equivalencia_distrito(pendiente_id, ubigeo, resuelta_por) VALUES (:p,:u,:a)"),
               {"p": p["pendiente_id"], "u": ubigeo, "a": admin["user_id"]})
    db.execute(text("UPDATE registro_pendiente SET estado = 'resuelto' WHERE pendiente_id = :p"), {"p": p["pendiente_id"]})
    auditoria.registrar(db, admin["user_id"], "resolver_equivalencia", "registro_pendiente", p["pendiente_id"], {"ubigeo": ubigeo})
    db.commit()
    abiertos = db.execute(text("SELECT count(*) FROM registro_pendiente WHERE version_id = :v AND estado = 'abierto'"), {"v": p["version_id"]}).scalar()
    return {"resuelta": True, "pendientes_abiertos": abiertos,
            "siguiente_paso": "Verifica la versión para continuar." if abiertos == 0 else None}
