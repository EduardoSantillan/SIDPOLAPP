from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import cargar


@lru_cache
def _fabrica():
    engine = create_engine(cargar().database_url, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


def get_db():
    """Dependencia FastAPI: una sesión por petición."""
    with _fabrica()() as s:
        yield s


def sesion() -> Session:
    return _fabrica()()
