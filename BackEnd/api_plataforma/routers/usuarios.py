from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api_plataforma.schemas import EnlaceOut, UsuarioCreadoOut, UsuarioOut, UsuariosOut
from api_plataforma.servicios import auditoria
from common.config import cargar
from common.db import get_db
from common.errores import ErrorNegocio
from common.seguridad import requiere_rol, token_activacion

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
Rol = Literal["usuario", "analista", "administrador"]
VIGENCIA_H = 72


class UsuarioIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    correo: EmailStr
    rol: Rol


class UsuarioPatch(BaseModel):
    rol: Rol | None = None
    activo: bool | None = None


def _enlace(db: Session, user_id) -> dict:
    token, h = token_activacion()
    vence = datetime.now(timezone.utc) + timedelta(hours=VIGENCIA_H)
    # Un solo enlace vigente por cuenta: se invalidan los anteriores.
    db.execute(text("UPDATE token_activacion SET usado_en = now() WHERE user_id = :u AND usado_en IS NULL"), {"u": user_id})
    db.execute(text("INSERT INTO token_activacion(token_hash, user_id, vence_en) VALUES (:h, :u, :v)"), {"h": h, "u": user_id, "v": vence})
    return {"enlace_activacion": f"{cargar().front_url.rstrip('/')}/activar?token={token}", "vence": vence.isoformat()}


def _fila(db: Session, user_id):
    try:
        f = db.execute(text("SELECT user_id, nombre, correo, rol, estado FROM perfil_usuario WHERE user_id = CAST(:u AS uuid)"), {"u": user_id}).mappings().first()
    except Exception:
        db.rollback()
        f = None
    if not f:
        raise ErrorNegocio(404, "USUARIO_NO_ENCONTRADO", "No encontramos esa cuenta.")
    return f


def _salida(f) -> dict:
    return {"id": str(f["user_id"]), "nombre": f["nombre"], "correo": f["correo"], "rol": f["rol"], "estado": f["estado"]}


@router.post("", status_code=201, response_model=UsuarioCreadoOut)
def crear(datos: UsuarioIn, admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    try:
        uid = db.execute(
            text("INSERT INTO perfil_usuario(nombre, correo, rol, estado) VALUES (:n, :c, :r, 'pendiente_activacion') RETURNING user_id"),
            {"n": datos.nombre.strip(), "c": datos.correo.lower(), "r": datos.rol},
        ).scalar()
    except IntegrityError:
        db.rollback()
        raise ErrorNegocio(409, "CORREO_REPETIDO", "Ya existe una cuenta con ese correo.")
    enlace = _enlace(db, uid)
    auditoria.registrar(db, admin["user_id"], "crear_usuario", "perfil_usuario", uid, {"rol": datos.rol})
    db.commit()
    return {"id": str(uid), "estado": "pendiente_activacion", **enlace}


@router.get("", response_model=UsuariosOut)
def listar(limite: int = 50, desde: int = 0, _: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    filas = db.execute(
        text("SELECT user_id, nombre, correo, rol, estado FROM perfil_usuario ORDER BY nombre LIMIT :l OFFSET :d"),
        {"l": min(max(limite, 1), 200), "d": max(desde, 0)},
    ).mappings().all()
    return {"items": [_salida(f) for f in filas]}


@router.get("/{user_id}", response_model=UsuarioOut)
def detalle(user_id: str, _: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    return _salida(_fila(db, user_id))


@router.patch("/{user_id}", response_model=UsuarioOut)
def modificar(user_id: str, datos: UsuarioPatch, admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    f = _fila(db, user_id)
    propio = str(f["user_id"]) == str(admin["user_id"])
    if propio and ((datos.activo is False) or (datos.rol and datos.rol != "administrador")):
        raise ErrorNegocio(409, "CUENTA_PROPIA", "No puedes quitarte el acceso ni cambiar tu propio rol.")
    if datos.rol and datos.rol != f["rol"]:
        db.execute(text("UPDATE perfil_usuario SET rol = :r WHERE user_id = :u"), {"r": datos.rol, "u": f["user_id"]})
        auditoria.registrar(db, admin["user_id"], "cambiar_rol", "perfil_usuario", f["user_id"], {"de": f["rol"], "a": datos.rol})
    if datos.activo is not None and f["estado"] != "pendiente_activacion":
        nuevo = "activo" if datos.activo else "inactivo"
        if nuevo != f["estado"]:
            db.execute(text("UPDATE perfil_usuario SET estado = :e WHERE user_id = :u"), {"e": nuevo, "u": f["user_id"]})
            auditoria.registrar(db, admin["user_id"], "activar_usuario" if datos.activo else "desactivar_usuario", "perfil_usuario", f["user_id"])
    db.commit()
    return _salida(_fila(db, user_id))


@router.post("/{user_id}/reenviar-activacion", response_model=EnlaceOut)
def reenviar(user_id: str, admin: dict = Depends(requiere_rol("administrador")), db: Session = Depends(get_db)):
    f = _fila(db, user_id)
    if f["estado"] != "pendiente_activacion":
        raise ErrorNegocio(409, "YA_ACTIVADA", "Esta cuenta ya fue activada.")
    enlace = _enlace(db, f["user_id"])
    auditoria.registrar(db, admin["user_id"], "reenviar_activacion", "perfil_usuario", f["user_id"])
    db.commit()
    return enlace
