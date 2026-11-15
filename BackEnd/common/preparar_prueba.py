"""Deja listo un entorno SOLO PARA PROBAR la plataforma con personas (prueba de los 2 minutos).

Qué hace: crea tres cuentas de prueba (usuario, analista, administrador), registra el archivo real de SIDPOL de prueba
(el mismo de las pruebas automáticas), aprueba la configuración del experimento EN ESTE ENTORNO y corre los cálculos reales
de robo y hurto con la plataforma (XGBoost de verdad, unos 30 segundos por delito).

Seguridad: se niega a correr si ENTORNO no es «desarrollo». No debe usarse en el servidor real: la aprobación de la
configuración es una decisión del equipo y del asesor, y estas cuentas llevan una contraseña conocida.
Uso:  docker compose -p sidpol_prueba ... exec api python -m common.preparar_prueba   (lo hace scripts/preparar_prueba.sh)
"""
import logging
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from common.config import cargar
from common.db import sesion
from common.registrar_config import main as registrar_config
from common.seguridad import hash_password

CLAVE = "clave-de-prueba-123"
CUENTAS = [("Ana Torres", "usuario@prueba.pe", "usuario"), ("Marco Barzola", "analista@prueba.pe", "analista"),
           ("Eduardo Santillán", "admin@prueba.pe", "administrador")]
CSV = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sidpol_lima.csv"


def main() -> int:
    for ruidoso in ("httpx", "sidpol"):  # que se lea solo lo importante
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    if cargar().entorno != "desarrollo":
        print("Esto solo corre en un entorno de desarrollo (ENTORNO=desarrollo). No se hizo nada.", file=sys.stderr)
        return 2
    from api_plataforma.main import app

    api = TestClient(app)
    with sesion() as db:
        for nombre, correo, rol in CUENTAS:
            db.execute(text("INSERT INTO perfil_usuario(nombre, correo, rol, estado, password_hash) VALUES (:n,:c,:r,'activo',:h) ON CONFLICT DO NOTHING"),
                       {"n": nombre, "c": correo, "r": rol, "h": hash_password(CLAVE)})
        db.commit()

    def entrar(correo: str) -> dict:
        r = api.post("/auth/login", json={"correo": correo, "contrasena": CLAVE})
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["token"]}

    admin, analista = entrar("admin@prueba.pe"), entrar("analista@prueba.pe")
    r = api.post("/versiones", headers=admin, data={"periodo_corte": "2026-07", "version": "v1"},
                 files={"archivo": ("denuncias_lima_jul2026.csv", CSV.read_bytes(), "text/csv")})
    if r.status_code == 201:
        print(f"Versión de datos registrada: {r.json()['estado']}")
    elif r.status_code == 409:
        print("La versión de datos ya estaba registrada.")
    else:
        print("No se pudo registrar el archivo:", r.text, file=sys.stderr)
        return 1
    registrar_config(aprobar=True)
    print("Configuración aprobada en este entorno de prueba.")

    versiones = api.get("/versiones", headers=analista).json()["items"]
    version_id = next(v["id"] for v in versiones if v["estado"] == "integra")
    for delito in ("ROBO", "HURTO"):
        hay = api.get("/ejecuciones", headers=analista).json()["items"]
        if any(e["target"] == delito and e["estado"] == "completada" for e in hay):
            print(f"{delito}: ya había resultados.")
            continue
        r = api.post("/ejecuciones", headers=analista, json={"version_id": version_id, "target": delito})
        if r.status_code != 202:
            print(f"{delito}: no se pudo iniciar: {r.text}", file=sys.stderr)
            return 1
        eid = r.json()["ejecucion_id"]
        print(f"{delito}: calculando…", flush=True)
        for _ in range(180):
            time.sleep(2)
            estado = api.get(f"/ejecuciones/{eid}", headers=analista).json()
            if estado["estado"] != "en_curso":
                break
        if estado["estado"] != "completada":
            print(f"{delito}: terminó como {estado['estado']}: {estado.get('motivo')}", file=sys.stderr)
            return 1
        print(f"{delito}: listo.")
    print("\nCuentas de prueba (contraseña de todas: %s):" % CLAVE)
    for nombre, correo, rol in CUENTAS:
        print(f"  {rol:14s} {correo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
