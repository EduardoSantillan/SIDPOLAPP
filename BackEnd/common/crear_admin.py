"""Crea la primera cuenta de administrador y muestra su enlace de activación.

Uso:  python -m common.crear_admin "Nombre Apellido" correo@dominio.pe
"""
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from common.config import cargar
from common.db import sesion
from common.seguridad import token_activacion


def main(nombre: str, correo: str) -> None:
    with sesion() as db:
        uid = db.execute(
            text("INSERT INTO perfil_usuario(nombre, correo, rol, estado) VALUES (:n, :c, 'administrador', 'pendiente_activacion') RETURNING user_id"),
            {"n": nombre, "c": correo.lower()},
        ).scalar()
        token, h = token_activacion()
        db.execute(text("INSERT INTO token_activacion(token_hash, user_id, vence_en) VALUES (:h, :u, :v)"),
                   {"h": h, "u": uid, "v": datetime.now(timezone.utc) + timedelta(hours=72)})
        db.execute(text("INSERT INTO evento_auditoria(actor_id, accion, objeto_tipo, objeto_id) VALUES (:u, 'crear_administrador_inicial', 'perfil_usuario', :o)"),
                   {"u": uid, "o": str(uid)})
        db.commit()
    print(f"{cargar().front_url.rstrip('/')}/activar?token={token}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
