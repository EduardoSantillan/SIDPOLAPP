from datetime import datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api_plataforma.schemas import EstadoOut, LoginOut, YoOut
from api_plataforma.servicios import auditoria
from common import limite
from common.db import get_db
from common.errores import ErrorNegocio
from common.seguridad import crear_token, hash_password, usuario_actual, verificar_password

router = APIRouter(prefix="/auth", tags=["auth"])
MIN_CLAVE = 10


class LoginIn(BaseModel):
    correo: EmailStr
    contrasena: str


class ActivarIn(BaseModel):
    token: str
    contrasena: str = Field(min_length=MIN_CLAVE, max_length=72)


@router.post("/login", response_model=LoginOut)
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    correo = datos.correo.lower()
    claves = (f"correo:{correo}", f"ip:{request.client.host if request.client else '?'}")
    if limite.bloqueado(*claves):
        raise ErrorNegocio(429, "DEMASIADOS_INTENTOS", "Demasiados intentos. Espera unos minutos e inténtalo de nuevo.")
    u = db.execute(
        text("SELECT user_id, nombre, rol, estado, password_hash FROM perfil_usuario WHERE correo = :c"), {"c": correo}
    ).mappings().first()
    if not verificar_password(datos.contrasena, u["password_hash"] if u else None):
        limite.registrar_fallo(*claves)
        raise ErrorNegocio(401, "CREDENCIALES_INCORRECTAS", "Correo o contraseña incorrectos.")
    if u["estado"] != "activo":
        raise ErrorNegocio(403, "CUENTA_INACTIVA", "Tu cuenta está desactivada. Pide al administrador que la reactive.")
    limite.limpiar(*claves)
    return {"token": crear_token(str(u["user_id"]), u["rol"]), "rol": u["rol"], "nombre": u["nombre"]}


@router.get("/yo", response_model=YoOut)
def yo(u: dict = Depends(usuario_actual), db: Session = Depends(get_db)):
    correo = db.execute(text("SELECT correo FROM perfil_usuario WHERE user_id = :u"), {"u": u["user_id"]}).scalar()
    return {"nombre": u["nombre"], "correo": correo, "rol": u["rol"]}


@router.post("/activar", response_model=EstadoOut)
def activar(datos: ActivarIn, db: Session = Depends(get_db)):
    h = sha256(datos.token.encode()).hexdigest()
    t = db.execute(
        text("SELECT user_id, vence_en, usado_en FROM token_activacion WHERE token_hash = :h FOR UPDATE"), {"h": h}
    ).mappings().first()
    if not t or t["usado_en"] or t["vence_en"] < datetime.now(timezone.utc):
        raise ErrorNegocio(400, "TOKEN_INVALIDO_O_VENCIDO", "El enlace no es válido o ya venció. Pide uno nuevo al administrador.")
    db.execute(text("UPDATE token_activacion SET usado_en = now() WHERE token_hash = :h"), {"h": h})
    db.execute(
        text("UPDATE perfil_usuario SET password_hash = :p, estado = 'activo' WHERE user_id = :u AND estado = 'pendiente_activacion'"),
        {"p": hash_password(datos.contrasena), "u": t["user_id"]},
    )
    auditoria.registrar(db, t["user_id"], "activar_cuenta", "perfil_usuario", t["user_id"])
    db.commit()
    return {"estado": "activo"}
