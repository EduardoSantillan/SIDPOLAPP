"""RNF-10: cada operación de administración o ejecución deja usuario, fecha, acción y objeto."""
import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def registrar(db: Session, actor_id, accion: str, objeto_tipo: str, objeto_id=None, detalle: dict | None = None) -> None:
    db.execute(
        text("INSERT INTO evento_auditoria(actor_id, accion, objeto_tipo, objeto_id, detalle) "
             "VALUES (:a, :ac, :t, :o, CAST(:d AS jsonb))"),
        {"a": actor_id, "ac": accion, "t": objeto_tipo, "o": None if objeto_id is None else str(objeto_id),
         "d": json.dumps(detalle) if detalle else None},
    )
