"""Paso 1: alembic upgrade head crea las 13 tablas + ajustes e impone inmutabilidad. Requiere TEST_DATABASE_URL."""
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="define TEST_DATABASE_URL para probar contra PostgreSQL")

TRECE = {
    "perfil_usuario", "distrito", "version_datos", "validacion_version", "registro_pendiente",
    "equivalencia_distrito", "observacion_mensual", "configuracion_experimento", "ejecucion",
    "resultado_pronostico", "metrica_desempeno", "ficha_informativa", "evento_auditoria",
}


def test_crea_las_13_tablas_y_los_ajustes(engine):
    with engine.connect() as c:
        tablas = {r[0] for r in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
    assert TRECE <= tablas
    assert "token_activacion" in tablas
    assert not any("riesgo" in t or "prioridad" in t for t in tablas)


def _ids(c):
    u = c.execute(text("INSERT INTO perfil_usuario(nombre,correo,rol,estado) VALUES ('A',:c,'administrador','activo') RETURNING user_id"), {"c": uuid.uuid4().hex + "@x.pe"}).scalar()
    v = c.execute(text(
        "INSERT INTO version_datos(nombre_archivo,periodo_corte,version,sha256,ruta_archivo,estado,registrada_por) "
        "VALUES (:n,'2026-07-01','v1',:h,'/datos/f.csv','registrada',:u) RETURNING version_id"),
        {"n": uuid.uuid4().hex + ".csv", "h": uuid.uuid4().hex + uuid.uuid4().hex, "u": u}).scalar()
    return u, v


def test_version_solo_cambia_de_estado_y_no_se_borra(engine):
    with engine.begin() as c:
        _, v = _ids(c)
        c.execute(text("UPDATE version_datos SET estado='integra' WHERE version_id=:v"), {"v": v})  # permitido
    for sql in ("UPDATE version_datos SET version='otra' WHERE version_id=:v", "DELETE FROM version_datos WHERE version_id=:v"):
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text(sql), {"v": v})


def test_observaciones_inmutables_y_checks(engine):
    with engine.begin() as c:
        _, v = _ids(c)
        c.execute(text("INSERT INTO distrito VALUES ('150101','Lima') ON CONFLICT DO NOTHING"))
        c.execute(text("INSERT INTO observacion_mensual VALUES (:v,'150101','ROBO','2026-07-01',5,'post_break','observed')"), {"v": v})
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("UPDATE observacion_mensual SET y=9 WHERE version_id=:v"), {"v": v})
    with pytest.raises(DBAPIError), engine.begin() as c:  # target inválido
        c.execute(text("INSERT INTO observacion_mensual VALUES (:v,'150101','ESTAFA','2026-06-01',1,'post_break','observed')"), {"v": v})


def test_una_sola_ejecucion_en_curso_por_target(engine):
    with engine.begin() as c:
        u, v = _ids(c)
        cfg = c.execute(text("INSERT INTO configuracion_experimento(nombre,version,contenido,sha256) VALUES ('c','v0.8.5','{}',:h) RETURNING config_id"),
                        {"h": uuid.uuid4().hex + uuid.uuid4().hex}).scalar()
        q = "INSERT INTO ejecucion(version_id,config_id,target,iniciada_por) VALUES (:v,:c,'ROBO',:u)"
        c.execute(text(q), {"v": v, "c": cfg, "u": u})
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text(q), {"v": v, "c": cfg, "u": u})
