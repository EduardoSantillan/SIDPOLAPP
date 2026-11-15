"""Registra la configuración congelada (config/experimento_v1.json) con su SHA-256.

Uso:  python -m common.registrar_config            → la registra SIN aprobar (la API se niega a ejecutarla)
      python -m common.registrar_config --aprobar  → la deja aprobada con la fecha de hoy
La aprobación es una decisión del equipo y del asesor; la plataforma no edita el contenido (ADR-05).
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

from common.db import sesion

RUTA = Path(__file__).resolve().parents[1] / "config" / "experimento_v1.json"
RUTA_FICHA = Path(__file__).resolve().parents[1] / "config" / "ficha_v1.json"


def sha256_config(contenido: dict) -> str:
    return hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main(aprobar: bool, ruta: Path = RUTA, ruta_ficha: Path | None = RUTA_FICHA) -> str:
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    h = sha256_config(contenido)
    with sesion() as db:
        db.execute(
            text("INSERT INTO configuracion_experimento(nombre, version, contenido, sha256, aprobada_en) "
                 "VALUES (:n, :v, CAST(:c AS jsonb), :h, :a) ON CONFLICT (sha256) DO NOTHING"),
            {"n": contenido["nombre"], "v": contenido["version"], "c": json.dumps(contenido), "h": h, "a": date.today() if aprobar else None})
        if aprobar:  # la aprobación sí se puede dar después; el contenido nunca cambia
            db.execute(text("UPDATE configuracion_experimento SET aprobada_en = :a WHERE sha256 = :h AND aprobada_en IS NULL"),
                       {"a": date.today(), "h": h})
        if ruta_ficha:  # la ficha informativa (RF-23) queda ligada a esta configuración; versionada, no se edita
            ficha = json.loads(ruta_ficha.read_text(encoding="utf-8"))
            db.execute(
                text("INSERT INTO ficha_informativa(config_id, secciones, version) "
                     "SELECT config_id, CAST(:s AS jsonb), :v FROM configuracion_experimento WHERE sha256 = :h "
                     "AND NOT EXISTS (SELECT 1 FROM ficha_informativa f JOIN configuracion_experimento c USING (config_id) WHERE c.sha256 = :h AND f.version = :v)"),
                {"s": json.dumps(ficha["secciones"], ensure_ascii=False), "v": ficha["version"], "h": h})
        db.commit()
    return h


if __name__ == "__main__":
    print(main("--aprobar" in sys.argv))
