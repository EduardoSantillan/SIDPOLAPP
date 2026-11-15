"""AC-04: verifica una versión de datos (AC-04.1) y, si queda íntegra, construye su panel (AC-04.2)."""
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from common import panel as P


class VersionNoExiste(Exception):
    pass


def _equivalencias(db: Session, version_id) -> dict[str, str]:
    filas = db.execute(
        text("SELECT p.codigo_original, e.ubigeo FROM registro_pendiente p JOIN equivalencia_distrito e USING (pendiente_id) "
             "WHERE p.version_id = :v"), {"v": version_id},
    ).all()
    return {c: u.strip() for c, u in filas}


def verificar_version(db: Session, version_id: str) -> dict:
    """Recalcula el hash, repite los controles y guarda el resultado. Devuelve estado y controles."""
    v = db.execute(
        text("SELECT version_id, ruta_archivo, periodo_corte, sha256, estado FROM version_datos WHERE version_id = CAST(:v AS uuid)"),
        {"v": version_id},
    ).mappings().first()
    if not v:
        raise VersionNoExiste(version_id)

    controles: list[P.Control] = []
    pendientes: dict[str, int] = {}
    panel = None
    estado = "invalida"
    try:
        contenido = Path(v["ruta_archivo"]).read_bytes()
    except OSError:
        controles.append(P.Control("integridad_sha256", False, "No se encontró el archivo guardado de esta versión."))
        contenido = None
    if contenido is not None:
        coincide = P.sha256_bytes(contenido) == v["sha256"]
        controles.append(P.Control(
            "integridad_sha256", coincide,
            "El archivo guardado coincide con el SHA-256 registrado." if coincide else
            "El archivo guardado ya no coincide con el SHA-256 registrado: fue alterado."))
        if coincide:
            try:
                df = P.leer_csv(contenido)
                r = P.verificar(df, v["periodo_corte"], _equivalencias(db, v["version_id"]))
                estado, pendientes, panel = r.estado, r.pendientes, r.panel
                controles += r.controles
            except P.SnapshotInvalido as e:
                controles.append(P.Control("estructura", False, str(e)))

    # Una versión que ya fue íntegra y dejó observaciones no se reescribe (inmutabilidad): solo se confirma o se invalida.
    _guardar(db, v, estado, controles, pendientes, panel)
    db.commit()
    return {"version_id": str(v["version_id"]), "estado": estado,
            "controles": [{"control": c.control, "aprobado": c.aprobado, "detalle": c.detalle} for c in controles],
            "pendientes_abiertos": len(pendientes) if estado == "con_pendientes" else 0}


def _guardar(db: Session, v, estado: str, controles, pendientes: dict[str, int], panel) -> None:
    vid = v["version_id"]
    for c in controles:  # un lote por verificación: comparten la hora de la transacción
        db.execute(text("INSERT INTO validacion_version(version_id, control, aprobado, detalle) VALUES (:v,:c,:a,:d)"),
                   {"v": vid, "c": c.control, "a": c.aprobado, "d": c.detalle})
    for codigo, n in pendientes.items():
        db.execute(
            text("INSERT INTO registro_pendiente(version_id, codigo_original, n_filas) VALUES (:v,:c,:n) "
                 "ON CONFLICT (version_id, codigo_original) DO UPDATE SET n_filas = EXCLUDED.n_filas"),
            {"v": vid, "c": codigo, "n": int(n)})
    db.execute(text("UPDATE version_datos SET estado = :e WHERE version_id = :v"), {"e": estado, "v": vid})
    if panel is not None:
        ya = db.execute(text("SELECT 1 FROM observacion_mensual WHERE version_id = :v LIMIT 1"), {"v": vid}).first()
        if not ya:
            filas = [{"v": vid, "u": r.UBIGEO, "t": r.target, "f": r.fecha.date(), "y": int(r.y), "r": r.regime, "o": r.value_origin}
                     for r in panel.itertuples(index=False)]
            db.execute(text("INSERT INTO observacion_mensual(version_id, ubigeo, target, fecha, y, regimen, value_origin) "
                            "VALUES (:v,:u,:t,:f,:y,:r,:o)"), filas)
