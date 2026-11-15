"""Límite de intentos de login por correo y por IP (en memoria: una sola VM, un solo proceso)."""
import time
from collections import defaultdict

MAX_FALLOS = 5
VENTANA_S = 15 * 60
_fallos: dict[str, list[float]] = defaultdict(list)


def _vigentes(clave: str) -> list[float]:
    ahora = time.monotonic()
    _fallos[clave] = [t for t in _fallos[clave] if ahora - t < VENTANA_S]
    return _fallos[clave]


def bloqueado(*claves: str) -> bool:
    return any(len(_vigentes(c)) >= MAX_FALLOS for c in claves)


def registrar_fallo(*claves: str) -> None:
    for c in claves:
        _vigentes(c).append(time.monotonic())


def limpiar(*claves: str) -> None:
    for c in claves:
        _fallos.pop(c, None)


def reiniciar_todo() -> None:  # solo para pruebas
    _fallos.clear()
