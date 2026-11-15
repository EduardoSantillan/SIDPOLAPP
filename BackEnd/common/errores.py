"""Errores uniformes {codigo, mensaje, detalle} en español."""
from fastapi import FastAPI, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

MENSAJES = {
    401: "Tu sesión terminó. Vuelve a iniciar sesión.",
    403: "Tu rol no tiene permiso para esta acción.",
    404: "No encontramos lo que buscas.",
    405: "Esta operación no existe. Las versiones de datos no se modifican: registra una nueva con el archivo corregido.",
    413: "El archivo es demasiado grande.",
    409: "Eso ya existe o está en uso.",
    422: "Revisa los datos enviados.",
}


class ErrorNegocio(HTTPException):
    def __init__(self, status: int, codigo: str, mensaje: str, detalle=None):
        super().__init__(status_code=status, detail={"codigo": codigo, "mensaje": mensaje, "detalle": detalle})


def _cuerpo(status: int, detail) -> dict:
    if isinstance(detail, dict) and "codigo" in detail:
        return detail
    return {"codigo": f"http_{status}", "mensaje": MENSAJES.get(status, detail if isinstance(detail, str) else "Ocurrió un error."), "detalle": None}


def instalar(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_cuerpo(exc.status_code, exc.detail), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        return JSONResponse(
            {"codigo": "validacion", "mensaje": MENSAJES[422], "detalle": [e["loc"][-1] for e in exc.errors()]},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception):
        return JSONResponse({"codigo": "interno", "mensaje": "Algo salió mal de nuestro lado.", "detalle": None}, status_code=500)
