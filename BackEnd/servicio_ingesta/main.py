"""AC-04 servicio-ingesta (interno, 8001). Solo la API lo llama, con la cabecera x-clave-servicio."""
import hmac

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common import errores, logging as obs
from common.config import cargar
from common.db import get_db
from common.errores import ErrorNegocio
from servicio_ingesta.verificador import VersionNoExiste, verificar_version

cfg = cargar()
app = FastAPI(title="SIDPOL — servicio de ingesta (interno)", docs_url=None, redoc_url=None, openapi_url=None)
errores.instalar(app)
obs.install(app, "servicio_ingesta")


def _clave(x_clave_servicio: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_clave_servicio, cfg.clave_servicio):
        raise ErrorNegocio(403, "SIN_CLAVE_DE_SERVICIO", "Servicio interno: acceso denegado.")


class VerificarIn(BaseModel):
    version_id: str


@app.post("/interno/verificar", dependencies=[Depends(_clave)])
def verificar(datos: VerificarIn, db: Session = Depends(get_db)):
    try:
        return verificar_version(db, datos.version_id)
    except VersionNoExiste:
        raise ErrorNegocio(404, "VERSION_NO_EXISTE", "No existe esa versión de datos.")
