"""AC-03 api-plataforma: único servicio público. Paso 1: arranque seguro + /health."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_plataforma.routers import analisis, auth, consulta, ejecuciones, exportaciones, usuarios, versiones
from common import errores, logging as obs
from common.config import cargar

cfg = cargar()  # falla aquí si JWT_SECRET o CLAVE_SERVICIO faltan o son débiles

_dev = cfg.entorno == "desarrollo"  # en producción no se publica la documentación interactiva
app = FastAPI(title="SIDPOL — API de la plataforma", version="1.0.0",
              docs_url="/docs" if _dev else None, redoc_url=None, openapi_url="/openapi.json" if _dev else None)
errores.instalar(app)
obs.install(app, "api_plataforma")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cfg.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(versiones.router)
app.include_router(ejecuciones.router)
app.include_router(consulta.router)
app.include_router(analisis.router)
app.include_router(exportaciones.router)
