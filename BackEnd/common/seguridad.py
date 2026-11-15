"""JWT (PyJWT) + bcrypt. Cada petición verifica en BD que la cuenta siga activa y con el mismo rol."""
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import cargar
from .db import get_db
from .errores import ErrorNegocio

ROLES = ("usuario", "analista", "administrador")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
_HASH_FALSO = bcrypt.hashpw(b"relleno", bcrypt.gensalt()).decode()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()


def verificar_password(p: str, h: str | None) -> bool:
    """Compara siempre contra un hash (falso si no hay) para que el tiempo no delate si el correo existe."""
    ok = bcrypt.checkpw(p.encode()[:72], (h or _HASH_FALSO).encode())
    return ok and h is not None


def crear_token(user_id: str, rol: str) -> str:
    cfg = cargar()
    exp = datetime.now(timezone.utc) + timedelta(minutes=cfg.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "rol": rol, "exp": exp}, cfg.jwt_secret, algorithm="HS256")


def token_activacion() -> tuple[str, str]:
    """(token para el enlace, hash para guardar). Un solo uso, vence en 72 h."""
    t = secrets.token_urlsafe(32)
    return t, sha256(t.encode()).hexdigest()


def usuario_actual(token: str | None = Depends(_oauth2), db: Session = Depends(get_db)) -> dict:
    if not token:
        raise ErrorNegocio(401, "sin_sesion", "Tu sesión terminó. Vuelve a iniciar sesión.")
    try:
        datos = jwt.decode(token, cargar().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ErrorNegocio(401, "sesion_invalida", "Tu sesión terminó. Vuelve a iniciar sesión.")
    fila = db.execute(
        text("SELECT user_id, nombre, rol, estado FROM perfil_usuario WHERE user_id = :u"), {"u": datos["sub"]}
    ).mappings().first()
    if not fila or fila["estado"] != "activo" or fila["rol"] != datos["rol"]:
        raise ErrorNegocio(401, "cuenta_no_vigente", "Tu cuenta ya no está activa o cambió de rol. Vuelve a iniciar sesión.")
    return dict(fila)


def requiere_rol(*roles: str):
    def dep(u: dict = Depends(usuario_actual)) -> dict:
        if u["rol"] not in roles:
            raise ErrorNegocio(403, "sin_permiso", "Tu rol no tiene permiso para esta acción.")
        return u

    return dep
