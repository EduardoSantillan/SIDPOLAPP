"""Configuración desde variables de entorno. Falla al arrancar si los secretos no son seguros (RNF-04)."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETOS_DE_EJEMPLO = {"", "cambiar-en-produccion", "cambia-esto", "changeme", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    front_url: str = "http://localhost:5173"
    clave_servicio: str  # cabecera x-clave-servicio entre la API y los servicios internos
    ruta_csv: str = "/datos/csv"
    max_csv_mb: int = 40  # el CSV nacional de SIDPOL pesa ~27 MB; el plan decía 10 MB
    url_ingesta: str = "http://ingesta:8001"
    url_modelado: str = "http://modelado:8002"
    entorno: str = "produccion"  # «desarrollo» publica /docs y /openapi.json (el front genera sus tipos desde ahí)

    @field_validator("jwt_secret", "clave_servicio")
    @classmethod
    def _secreto_fuerte(cls, v: str) -> str:
        if v.strip().lower() in SECRETOS_DE_EJEMPLO or v.strip().lower().startswith("reemplazar") or len(v) < 32:
            raise ValueError("debe tener al menos 32 caracteres y no ser un valor de ejemplo")
        return v


def cargar() -> Settings:
    return Settings()  # lanza ValidationError si falta o es débil: la app no arranca
