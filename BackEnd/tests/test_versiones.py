"""Paso 3: registro de versiones, SHA-256, verificación, pendientes y equivalencias (RF-03…07, RNF-06)."""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from common import limite
from common.seguridad import hash_password
from tests.sintetico import csv_sintetico


def _csv(**kw):
    """CSV sintético distinto en cada llamada (el SHA-256 es único en toda la base); solo cambia una fila ajena a Lima."""
    return csv_sintetico(variante=uuid.uuid4().int % 10**9, **kw)


@pytest.fixture()
def api(engine, monkeypatch):
    """API con ingesta llamada en proceso (en producción es REST con x-clave-servicio)."""
    from api_plataforma.main import app
    from api_plataforma.servicios import ingesta
    from common.db import sesion
    from servicio_ingesta.verificador import verificar_version

    def directo(version_id):
        with sesion() as db:
            return verificar_version(db, version_id)

    monkeypatch.setattr(ingesta, "verificar", directo)
    limite.reiniciar_todo()
    return TestClient(app, raise_server_exceptions=False)


def _cabecera(api, engine, rol):
    correo = f"{uuid.uuid4().hex[:10]}@x.pe"
    with engine.begin() as c:
        c.execute(text("INSERT INTO perfil_usuario(nombre,correo,rol,estado,password_hash) VALUES ('P',:c,:r,'activo',:h)"),
                  {"c": correo, "r": rol, "h": hash_password("clave-segura-123")})
    t = api.post("/auth/login", json={"correo": correo, "contrasena": "clave-segura-123"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture()
def admin(api, engine):
    return _cabecera(api, engine, "administrador")


def _subir(api, h, contenido, nombre=None, corte="2019-12", version="v-prueba"):
    nombre = nombre or f"{uuid.uuid4().hex[:8]}.csv"
    return api.post("/versiones", headers=h, files={"archivo": (nombre, contenido, "text/csv")}, data={"periodo_corte": corte, "version": version})


def _fallidos(r):
    return {c["control"] for c in r.json()["controles"] if not c["aprobado"]}


def test_registro_valido_queda_integro_con_sha256_y_observaciones(api, admin, engine):
    r = _subir(api, admin, _csv())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "integra" and len(d["sha256"]) == 64 and d["pendientes_abiertos"] == 0
    assert all(c["aprobado"] for c in d["controles"])
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM observacion_mensual WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar()
        aud = c.execute(text("SELECT count(*) FROM evento_auditoria WHERE accion='registrar_version' AND objeto_id=:v"), {"v": d["id"]}).scalar()
    assert n == 43 * 24 * 2 and aud == 1


def test_duplicado_por_nombre_y_periodo_o_por_hash(api, admin):
    csv = _csv()
    assert _subir(api, admin, csv, "a.csv").status_code == 201
    r = _subir(api, admin, _csv(renombrar_distrito="OTRO NOMBRE"), "a.csv")  # mismo nombre y corte
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DUPLICADA"
    r = _subir(api, admin, csv, "b.csv")  # mismo contenido, otro nombre
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DUPLICADA"


@pytest.mark.parametrize("kw,fallido,estado", [
    ({"omitir_mes": "2018-06"}, "continuidad_mensual", "invalida"),
    ({"con_cero": True}, "conteos_positivos", "invalida"),
    ({"quitar_distrito": "150110"}, "distritos_completos", "invalida"),
    ({"sin_columna": "cantidad"}, "estructura", "invalida"),
])
def test_rnf06_versiones_defectuosas_quedan_invalidas(api, admin, kw, fallido, estado):
    r = _subir(api, admin, _csv(**kw))
    assert r.status_code == 201 and r.json()["estado"] == estado and fallido in _fallidos(r)


def test_hash_alterado_invalida_la_version(api, admin, engine):
    d = _subir(api, admin, _csv()).json()
    assert d["estado"] == "integra"
    with engine.connect() as c:
        ruta = c.execute(text("SELECT ruta_archivo FROM version_datos WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar()
    Path(ruta).write_bytes(Path(ruta).read_bytes() + b"\n2019,12,LIMA METROPOLITANA,LIMA,X,150101,Robo,1\n")
    r = api.post(f"/versiones/{d['id']}/verificar", headers=admin)
    assert r.json()["estado"] == "invalida" and "integridad_sha256" in _fallidos(r)


def test_archivo_ilegible_no_da_500(api, admin):
    r = _subir(api, admin, b"\x00\x01\x02 esto no es un csv")
    assert r.status_code == 201 and r.json()["estado"] == "invalida" and "estructura" in _fallidos(r)
    assert _subir(api, admin, b"  ").status_code == 422
    assert _subir(api, admin, _csv(), "datos.xlsx").status_code == 422
    assert _subir(api, admin, _csv(), corte="2019/12").status_code == 422
    assert _subir(api, admin, _csv(), corte="2019-13").status_code == 422


def test_tamano_maximo(api, admin, monkeypatch):
    monkeypatch.setenv("MAX_CSV_MB", "1")
    r = _subir(api, admin, b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413 and r.json()["codigo"] == "ARCHIVO_MUY_GRANDE"


def test_pendientes_equivalencia_y_reverificacion(api, admin, engine):
    d = _subir(api, admin, _csv(extra_ubigeo="150199")).json()
    assert d["estado"] == "con_pendientes" and d["pendientes_abiertos"] == 1
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM observacion_mensual WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar() == 0
    p = api.get(f"/versiones/{d['id']}/pendientes", headers=admin).json()["items"]
    assert p[0]["codigo"] == "150199" and p[0]["estado"] == "abierto"
    assert api.put(f"/pendientes/{p[0]['id']}/equivalencia", headers=admin, json={"ubigeo": "999999"}).status_code == 422
    r = api.put(f"/pendientes/{p[0]['id']}/equivalencia", headers=admin, json={"ubigeo": "150110"})
    assert r.status_code == 200 and r.json()["pendientes_abiertos"] == 0
    assert api.put(f"/pendientes/{p[0]['id']}/equivalencia", headers=admin, json={"ubigeo": "150110"}).status_code == 409
    assert api.get(f"/versiones/{d['id']}", headers=admin).json()["estado"] == "con_pendientes"  # hasta verificar
    r = api.post(f"/versiones/{d['id']}/verificar", headers=admin)
    assert r.json()["estado"] == "integra"
    with engine.connect() as c:
        quien = c.execute(text("SELECT resuelta_por, resuelta_en FROM equivalencia_distrito WHERE pendiente_id = CAST(:p AS uuid)"), {"p": p[0]["id"]}).one()
        n = c.execute(text("SELECT count(*) FROM observacion_mensual WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar()
    assert quien[0] and quien[1] and n == 43 * 24 * 2
    # una verificación repetida de una versión íntegra no duplica ni reescribe observaciones
    api.post(f"/versiones/{d['id']}/verificar", headers=admin)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM observacion_mensual WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar() == n


def test_las_versiones_no_se_editan_ni_se_borran(api, admin, engine):
    d = _subir(api, admin, _csv()).json()
    assert api.put(f"/versiones/{d['id']}", headers=admin, json={}).status_code == 405
    assert api.delete(f"/versiones/{d['id']}", headers=admin).status_code == 405
    assert api.patch(f"/versiones/{d['id']}", headers=admin, json={}).status_code == 405
    with pytest.raises(DBAPIError), engine.begin() as c:  # tampoco por SQL directo
        c.execute(text("DELETE FROM version_datos WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]})


def test_detalle_y_listado_por_rol(api, admin, engine):
    ok = _subir(api, admin, _csv()).json()
    mala = _subir(api, admin, _csv(omitir_mes="2018-06")).json()
    ids_admin = {v["id"] for v in api.get("/versiones", headers=admin).json()["items"]}
    assert {ok["id"], mala["id"]} <= ids_admin
    analista = _cabecera(api, engine, "analista")
    ids_analista = {v["id"] for v in api.get("/versiones", headers=analista).json()["items"]}
    assert ok["id"] in ids_analista and mala["id"] not in ids_analista
    assert api.get(f"/versiones/{ok['id']}", headers=analista).status_code == 403
    assert api.get(f"/versiones/{uuid.uuid4()}", headers=admin).status_code == 404
    assert api.get("/versiones/no-es-uuid", headers=admin).status_code == 404


# ---------- matriz rol × operación de este módulo (RNF-03) ----------
@pytest.mark.parametrize("rol", ["usuario", "analista", "administrador", "sin_sesion"])
@pytest.mark.parametrize("metodo,ruta,permitidos", [
    ("GET", "/versiones", {"administrador", "analista"}),
    ("GET", "/versiones/{v}", {"administrador"}),
    ("POST", "/versiones/{v}/verificar", {"administrador"}),
    ("GET", "/versiones/{v}/pendientes", {"administrador"}),
    ("PUT", "/pendientes/{p}/equivalencia", {"administrador"}),
])
def test_matriz_versiones(api, admin, engine, rol, metodo, ruta, permitidos):
    v = _subir(api, admin, _csv(extra_ubigeo="150199")).json()["id"]
    p = api.get(f"/versiones/{v}/pendientes", headers=admin).json()["items"][0]["id"]
    ruta = ruta.replace("{v}", v).replace("{p}", p)
    h = {} if rol == "sin_sesion" else _cabecera(api, engine, rol)
    r = api.request(metodo, ruta, headers=h, json={"ubigeo": "150110"} if metodo == "PUT" else None)
    if rol == "sin_sesion":
        assert r.status_code == 401
    elif rol in permitidos:
        assert r.status_code < 300, r.text
    else:
        assert r.status_code == 403


@pytest.mark.parametrize("rol", ["usuario", "analista", "sin_sesion"])
def test_solo_el_administrador_registra(api, engine, rol):
    h = {} if rol == "sin_sesion" else _cabecera(api, engine, rol)
    r = _subir(api, h, _csv())
    assert r.status_code == (401 if rol == "sin_sesion" else 403)


def test_servicio_interno_exige_clave(engine):
    from servicio_ingesta.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/interno/verificar", json={"version_id": str(uuid.uuid4())}).status_code == 403
    r = c.post("/interno/verificar", json={"version_id": str(uuid.uuid4())}, headers={"x-clave-servicio": "s" * 40})
    assert r.status_code in (404, 500)  # con clave correcta pasa la puerta (uuid inexistente → 404)


REAL = Path(__file__).resolve().parents[2] / "referencia/notebooks_finales/SIDPOL_Notebooks/00. Datasets/DATASET_Denuncias_Policiales_Ene 2018 a Julio 2026.csv"


@pytest.mark.skipif(not REAL.exists(), reason="CSV nacional de referencia no disponible")
def test_csv_nacional_real_queda_integro(api, admin, engine):
    r = _subir(api, admin, REAL.read_bytes(), "DATASET_real.csv", corte="2026-07", version="snapshot-jul-2026")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "integra", [c for c in d["controles"] if not c["aprobado"]]
    assert d["sha256"] == "baf9b11a2496d2c675326e7265ad0d9b5464b261dd2b731ae667aab2bf43a217"  # snapshot de referencia del asesor
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM observacion_mensual WHERE version_id = CAST(:v AS uuid)"), {"v": d["id"]}).scalar() == 43 * 103 * 2
