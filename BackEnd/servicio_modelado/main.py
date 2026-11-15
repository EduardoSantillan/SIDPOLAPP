"""AC-05 servicio-modelado (interno, 8002). Responde 202 y trabaja en segundo plano; sin colas ni reintentos."""
import hmac
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header
from pydantic import BaseModel

from common import errores, logging as obs
from common.config import cargar
from common.errores import ErrorNegocio
from servicio_modelado.ejecutor import ejecutar, recuperar_en_curso

cfg = cargar()


@asynccontextmanager
async def _vida(_: FastAPI):
    obs.log.info("modelado: %d ejecución(es) en curso marcadas como fallidas al reiniciar", recuperar_en_curso())
    yield


app = FastAPI(title="SIDPOL — servicio de modelado (interno)", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_vida)
errores.instalar(app)
obs.install(app, "servicio_modelado")


def _clave(x_clave_servicio: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_clave_servicio, cfg.clave_servicio):
        raise ErrorNegocio(403, "SIN_CLAVE_DE_SERVICIO", "Servicio interno: acceso denegado.")


class EjecutarIn(BaseModel):
    ejecucion_id: str


@app.post("/interno/ejecutar", status_code=202, dependencies=[Depends(_clave)])
def iniciar(datos: EjecutarIn, fondo: BackgroundTasks):
    fondo.add_task(ejecutar, datos.ejecucion_id)
    return {"ejecucion_id": datos.ejecucion_id, "estado": "en_curso"}
