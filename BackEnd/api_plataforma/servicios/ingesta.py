"""Cliente REST hacia servicio-ingesta (interno). Las pruebas lo reemplazan por una llamada directa."""
import httpx

from common.config import cargar
from common.errores import ErrorNegocio


def verificar(version_id: str) -> dict:
    cfg = cargar()
    try:
        r = httpx.post(f"{cfg.url_ingesta}/interno/verificar", json={"version_id": version_id},
                       headers={"x-clave-servicio": cfg.clave_servicio}, timeout=300)
    except httpx.HTTPError:
        raise ErrorNegocio(502, "SERVICIO_NO_DISPONIBLE",
                           "La versión quedó registrada pero no se pudo verificar ahora. Inténtalo de nuevo en un momento.")
    if r.status_code != 200:
        raise ErrorNegocio(502, "SERVICIO_NO_DISPONIBLE", "La verificación no pudo completarse. Inténtalo de nuevo.")
    return r.json()
