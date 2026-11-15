import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

log = logging.getLogger("sidpol")
_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def install(app: FastAPI, servicio: str) -> None:
    """Middleware de observabilidad: request_id, ruta, duración y status; más /health."""

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        if not _ID_VALIDO.match(rid):  # lo que llega de fuera no se copia a los logs si trae caracteres raros
            rid = uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
            resp.headers["x-request-id"] = rid
            return resp
        finally:
            log.info(json.dumps({
                "servicio": servicio, "request_id": rid, "ruta": request.url.path,
                "metodo": request.method, "status": status,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
            }))

    @app.get("/health", tags=["sistema"])
    def health():
        return {"servicio": servicio, "estado": "ok"}
