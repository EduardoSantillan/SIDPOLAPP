import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Valores de prueba válidos (≥ 32 caracteres); la BD real es opcional (TEST_DATABASE_URL).
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("CLAVE_SERVICIO", "s" * 40)
import tempfile  # noqa: E402

os.environ["RUTA_CSV"] = tempfile.mkdtemp(prefix="sidpol_csv_")
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://x:x@localhost:5432/x"))


import subprocess  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
URL_BD = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine():
    """Esquema limpio migrado con alembic (una vez por sesión de pruebas)."""
    if not URL_BD:
        pytest.skip("define TEST_DATABASE_URL para probar contra PostgreSQL")
    e = create_engine(URL_BD)
    with e.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RAIZ, env={**os.environ, "DATABASE_URL": URL_BD}, check=True)
    return e


# ---------- fixtures compartidas: versión íntegra real, API con ingesta y modelado en proceso ----------
import json  # noqa: E402
import uuid  # noqa: E402
from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from common import limite  # noqa: E402
from common import panel as P  # noqa: E402
from common.registrar_config import main as registrar_config  # noqa: E402
from common.seguridad import hash_password  # noqa: E402
from servicio_modelado import ejecutor  # noqa: E402
from tests.comun import CFG_NAIVE, FIX  # noqa: E402


@pytest.fixture(scope="session")
def panel_real():
    r = P.verificar(P.leer_csv((FIX / "sidpol_lima.csv").read_bytes()), date(2026, 7, 1))
    p = r.panel.rename(columns={"UBIGEO": "ubigeo", "target": "tg"})
    return {t: p[p["tg"] == t][["ubigeo", "fecha", "y"]].reset_index(drop=True) for t in ("ROBO", "HURTO")}


@pytest.fixture(scope="session")
def entorno(engine):
    """API con ingesta y modelado en proceso, una versión íntegra real y la configuración aprobada."""
    from api_plataforma.main import app
    from api_plataforma.servicios import ingesta, modelado
    from common.db import sesion
    from servicio_ingesta.verificador import verificar_version

    mp = pytest.MonkeyPatch()

    def ing(version_id):
        with sesion() as db:
            return verificar_version(db, version_id)

    mp.setattr(ingesta, "verificar", ing)
    mp.setattr(modelado, "ejecutar", lambda eid: (ejecutor.ejecutar(eid), True)[1])
    api = TestClient(app, raise_server_exceptions=False)

    def entrar(rol):
        correo = f"{uuid.uuid4().hex[:10]}@x.pe"
        with engine.begin() as c:
            c.execute(text("INSERT INTO perfil_usuario(nombre,correo,rol,estado,password_hash) VALUES ('P',:c,:r,'activo',:h)"),
                      {"c": correo, "r": rol, "h": hash_password("clave-segura-123")})
        return {"Authorization": "Bearer " + api.post("/auth/login", json={"correo": correo, "contrasena": "clave-segura-123"}).json()["token"]}

    admin = entrar("administrador")
    r = api.post("/versiones", headers=admin, data={"periodo_corte": "2026-07", "version": "extracto-lima"},
                 files={"archivo": ("extracto_lima.csv", (FIX / "sidpol_lima.csv").read_bytes(), "text/csv")})
    assert r.json()["estado"] == "integra"
    # Configuración rápida (solo referencias) para las pruebas de la API; gana a la v0.8.5 por versión.
    ruta_rapida = Path(tempfile.mkdtemp(prefix="sidpol_cfg_")) / "referencias.json"
    ruta_rapida.write_text(json.dumps({**CFG_NAIVE, "version": "v0.8.5-referencias"}), encoding="utf-8")
    sha = registrar_config(aprobar=True, ruta=ruta_rapida)
    yield {"api": api, "entrar": entrar, "admin": admin, "version": r.json()["id"], "sha": sha, "mp": mp}
    mp.undo()


@pytest.fixture()
def lib(engine, entorno):
    """Cada prueba parte sin ejecuciones en curso y sin límites de login acumulados."""
    limite.reiniciar_todo()
    with engine.begin() as c:
        c.execute(text("UPDATE ejecucion SET estado='fallida', motivo_fallo='limpieza de prueba', fin=now() WHERE estado='en_curso'"))
    return entorno
