"""Paso 1: la app no arranca con secretos débiles (RNF-04) y expone /health."""
import pytest
from pydantic import ValidationError

from common.config import Settings

BASE = {"database_url": "postgresql+psycopg://x:x@h/x", "jwt_secret": "j" * 40, "clave_servicio": "c" * 40}


def test_acepta_secretos_fuertes():
    assert Settings(**BASE).jwt_expire_minutes == 60


@pytest.mark.parametrize("campo", ["jwt_secret", "clave_servicio"])
@pytest.mark.parametrize("valor", ["", "cambiar-en-produccion", "corto", "x" * 31])
def test_rechaza_secretos_debiles(campo, valor):
    with pytest.raises(ValidationError):
        Settings(**{**BASE, campo: valor})


def test_falta_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="x", clave_servicio="c" * 40)


def test_health_y_errores_en_espanol():
    from fastapi.testclient import TestClient

    from api_plataforma.main import app

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["estado"] == "ok"
    assert r.headers["x-request-id"]
    r = c.get("/no-existe")
    assert r.status_code == 404 and set(r.json()) == {"codigo", "mensaje", "detalle"}
