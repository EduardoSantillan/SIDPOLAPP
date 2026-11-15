"""Paso 2: login, activación, usuarios, auditoría y matriz rol × operación (RF-01, RF-02, RF-08…11, RNF-03, RNF-10)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from common import limite
from common.seguridad import hash_password

CLAVE = "clave-segura-123"


@pytest.fixture()
def api(engine):
    from api_plataforma.main import app

    limite.reiniciar_todo()
    return TestClient(app, raise_server_exceptions=False)


def _cuenta(engine, rol="usuario", estado="activo", clave=CLAVE):
    correo = f"{uuid.uuid4().hex[:10]}@x.pe"
    with engine.begin() as c:
        uid = c.execute(
            text("INSERT INTO perfil_usuario(nombre,correo,rol,estado,password_hash) VALUES ('Persona Prueba',:c,:r,:e,:h) RETURNING user_id"),
            {"c": correo, "r": rol, "e": estado, "h": hash_password(clave) if clave else None},
        ).scalar()
    return str(uid), correo


def _login(api, correo, clave=CLAVE):
    return api.post("/auth/login", json={"correo": correo, "contrasena": clave})


def _cabecera(api, correo):
    return {"Authorization": f"Bearer {_login(api, correo).json()['token']}"}


@pytest.fixture()
def admin(api, engine):
    uid, correo = _cuenta(engine, "administrador")
    return uid, _cabecera(api, correo)


# ---------- login ----------
def test_login_correcto(api, engine):
    _, correo = _cuenta(engine, "analista")
    r = _login(api, correo)
    assert r.status_code == 200 and r.json()["rol"] == "analista" and r.json()["token"]


def test_correo_inexistente_y_clave_mala_dan_el_mismo_mensaje(api, engine):
    _, correo = _cuenta(engine)
    a = _login(api, correo, "otra-clave-xxxxx")
    b = _login(api, "nadie@x.pe")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() and a.json()["codigo"] == "CREDENCIALES_INCORRECTAS"


def test_cuenta_inactiva_rechazada(api, engine):
    _, correo = _cuenta(engine, estado="inactivo")
    r = _login(api, correo)
    assert r.status_code == 403 and r.json()["codigo"] == "CUENTA_INACTIVA"


def test_cuenta_pendiente_no_puede_entrar(api, engine):
    _, correo = _cuenta(engine, estado="pendiente_activacion", clave=None)
    assert _login(api, correo).status_code == 401


def test_limite_de_intentos(api, engine):
    _, correo = _cuenta(engine)
    for _ in range(5):
        assert _login(api, correo, "mala-clave-xxxx").status_code == 401
    r = _login(api, correo)  # incluso con la clave buena, queda bloqueado
    assert r.status_code == 429 and r.json()["codigo"] == "DEMASIADOS_INTENTOS"


def test_token_deja_de_valer_si_la_cuenta_se_desactiva_o_cambia_de_rol(api, engine):
    uid, correo = _cuenta(engine, "analista")
    h = _cabecera(api, correo)
    assert api.get("/auth/yo", headers=h).status_code == 200
    with engine.begin() as c:
        c.execute(text("UPDATE perfil_usuario SET rol='usuario' WHERE user_id=:u"), {"u": uid})
    assert api.get("/auth/yo", headers=h).status_code == 401
    h = _cabecera(api, correo)
    with engine.begin() as c:
        c.execute(text("UPDATE perfil_usuario SET estado='inactivo' WHERE user_id=:u"), {"u": uid})
    assert api.get("/auth/yo", headers=h).status_code == 401


def test_token_falso_o_ausente(api):
    assert api.get("/auth/yo").status_code == 401
    assert api.get("/auth/yo", headers={"Authorization": "Bearer basura"}).status_code == 401


# ---------- alta por enlace de activación ----------
def _token_de(enlace):
    return enlace.split("token=")[1]


def test_flujo_de_alta_y_activacion(api, admin, engine):
    _, h = admin
    correo = f"{uuid.uuid4().hex[:8]}@x.pe"
    r = api.post("/usuarios", headers=h, json={"nombre": "Ana Nueva", "correo": correo, "rol": "usuario"})
    assert r.status_code == 201 and r.json()["estado"] == "pendiente_activacion"
    token = _token_de(r.json()["enlace_activacion"])
    with engine.connect() as c:  # el token se guarda solo como hash
        assert c.execute(text("SELECT count(*) FROM token_activacion WHERE token_hash = :t"), {"t": token}).scalar() == 0
    assert _login(api, correo, "cualquiera-123456").status_code == 401
    assert api.post("/auth/activar", json={"token": token, "contrasena": "corta"}).status_code == 422
    assert api.post("/auth/activar", json={"token": token, "contrasena": "mi-clave-nueva-1"}).status_code == 200
    assert _login(api, correo, "mi-clave-nueva-1").status_code == 200
    r2 = api.post("/auth/activar", json={"token": token, "contrasena": "otra-clave-nueva-1"})
    assert r2.status_code == 400 and r2.json()["codigo"] == "TOKEN_INVALIDO_O_VENCIDO"


def test_token_vencido(api, admin, engine):
    _, h = admin
    r = api.post("/usuarios", headers=h, json={"nombre": "Vence Pronto", "correo": f"{uuid.uuid4().hex[:8]}@x.pe", "rol": "usuario"})
    with engine.begin() as c:
        c.execute(text("UPDATE token_activacion SET vence_en = now() - interval '1 minute' WHERE usado_en IS NULL AND user_id = CAST(:u AS uuid)"), {"u": r.json()["id"]})
    r2 = api.post("/auth/activar", json={"token": _token_de(r.json()["enlace_activacion"]), "contrasena": "mi-clave-nueva-1"})
    assert r2.status_code == 400


def test_reenviar_invalida_el_enlace_anterior(api, admin):
    _, h = admin
    r = api.post("/usuarios", headers=h, json={"nombre": "Re Enviar", "correo": f"{uuid.uuid4().hex[:8]}@x.pe", "rol": "analista"})
    viejo = _token_de(r.json()["enlace_activacion"])
    nuevo = _token_de(api.post(f"/usuarios/{r.json()['id']}/reenviar-activacion", headers=h).json()["enlace_activacion"])
    assert api.post("/auth/activar", json={"token": viejo, "contrasena": "mi-clave-nueva-1"}).status_code == 400
    assert api.post("/auth/activar", json={"token": nuevo, "contrasena": "mi-clave-nueva-1"}).status_code == 200


def test_correo_repetido(api, admin):
    _, h = admin
    d = {"nombre": "Repetido Uno", "correo": f"{uuid.uuid4().hex[:8]}@x.pe", "rol": "usuario"}
    assert api.post("/usuarios", headers=h, json=d).status_code == 201
    r = api.post("/usuarios", headers=h, json={**d, "correo": d["correo"].upper()})
    assert r.status_code == 409 and r.json()["codigo"] == "CORREO_REPETIDO"


# ---------- gestión ----------
def test_cambiar_rol_desactivar_y_listar(api, admin, engine):
    _, h = admin
    uid, correo = _cuenta(engine, "usuario")
    assert api.patch(f"/usuarios/{uid}", headers=h, json={"rol": "analista"}).json()["rol"] == "analista"
    assert api.patch(f"/usuarios/{uid}", headers=h, json={"activo": False}).json()["estado"] == "inactivo"
    assert _login(api, correo).status_code == 403
    assert api.patch(f"/usuarios/{uid}", headers=h, json={"activo": True}).json()["estado"] == "activo"
    assert any(u["id"] == uid for u in api.get("/usuarios", headers=h).json()["items"])
    assert api.get(f"/usuarios/{uuid.uuid4()}", headers=h).status_code == 404
    assert api.get("/usuarios/no-es-uuid", headers=h).status_code == 404


def test_el_administrador_no_se_quita_el_acceso(api, admin):
    uid, h = admin
    assert api.patch(f"/usuarios/{uid}", headers=h, json={"activo": False}).status_code == 409
    assert api.patch(f"/usuarios/{uid}", headers=h, json={"rol": "usuario"}).status_code == 409


def test_auditoria_de_operaciones(api, admin, engine):
    uid, h = admin
    r = api.post("/usuarios", headers=h, json={"nombre": "Audit Ada", "correo": f"{uuid.uuid4().hex[:8]}@x.pe", "rol": "usuario"})
    api.patch(f"/usuarios/{r.json()['id']}", headers=h, json={"rol": "analista"})
    with engine.connect() as c:
        acciones = {a for (a,) in c.execute(text("SELECT accion FROM evento_auditoria WHERE objeto_id = :o AND actor_id = CAST(:a AS uuid)"), {"o": r.json()["id"], "a": uid})}
    assert {"crear_usuario", "cambiar_rol"} <= acciones


# ---------- matriz rol × operación (RNF-03) ----------
ROLES = ["usuario", "analista", "administrador"]
OPERACIONES = [  # (método, ruta, cuerpo, roles permitidos)
    ("GET", "/auth/yo", None, set(ROLES)),
    ("GET", "/usuarios", None, {"administrador"}),
    ("POST", "/usuarios", {"nombre": "Matriz Test", "correo": "@", "rol": "usuario"}, {"administrador"}),
    ("GET", "/usuarios/{id}", None, {"administrador"}),
    ("PATCH", "/usuarios/{id}", {"rol": "usuario"}, {"administrador"}),
    ("POST", "/usuarios/{id}/reenviar-activacion", None, {"administrador"}),
]


@pytest.mark.parametrize("rol", ROLES + ["sin_sesion"])
@pytest.mark.parametrize("metodo,ruta,cuerpo,permitidos", OPERACIONES)
def test_matriz_rol_operacion(api, engine, rol, metodo, ruta, cuerpo, permitidos):
    objetivo, _ = _cuenta(engine, "usuario", "pendiente_activacion", None)
    ruta = ruta.replace("{id}", objetivo)
    if cuerpo and "correo" in cuerpo:
        cuerpo = {**cuerpo, "correo": f"{uuid.uuid4().hex[:8]}@x.pe"}
    headers = {} if rol == "sin_sesion" else _cabecera(api, _cuenta(engine, rol)[1])
    r = api.request(metodo, ruta, headers=headers, json=cuerpo)
    if rol == "sin_sesion":
        assert r.status_code == 401
    elif rol in permitidos:
        assert r.status_code < 300, r.text
    else:
        assert r.status_code == 403 and r.json()["codigo"] == "sin_permiso"
