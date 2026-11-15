"""Cliente REST hacia servicio-modelado (interno). Las pruebas lo reemplazan por una llamada directa."""
import httpx

from common.config import cargar


def ejecutar(ejecucion_id: str) -> bool:
    """Pide el procesamiento (responde 202). False si el servicio no está disponible."""
    cfg = cargar()
    try:
        r = httpx.post(f"{cfg.url_modelado}/interno/ejecutar", json={"ejecucion_id": ejecucion_id},
                       headers={"x-clave-servicio": cfg.clave_servicio}, timeout=15)
    except httpx.HTTPError:
        return False
    return r.status_code == 202
