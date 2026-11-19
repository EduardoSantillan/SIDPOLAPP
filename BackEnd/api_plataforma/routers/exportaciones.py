"""Exportación CSV/PDF (RF-24) con metadata y aviso (RF-25). Los tres roles; deja registro de quién exporta."""
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api_plataforma.routers.consulta import _error_promedio
from api_plataforma.servicios import auditoria, exportacion as X, resultados as R
from api_plataforma.servicios.resultados import Periodo, Target
from common.db import get_db
from common.seguridad import requiere_rol

router = APIRouter(tags=["exportaciones"])


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in R.clave_orden(s)).strip("_")


@router.get("/exportaciones")
def exportar(target: Target, formato: Literal["csv", "pdf"], ubigeo: str | None = None, periodo: Periodo = "todo", ejecucion_id: str | None = None,
             u: dict = Depends(requiere_rol("usuario", "analista", "administrador")), db: Session = Depends(get_db)):
    nombre = R.distrito(db, ubigeo) if ubigeo else None
    ej = R.ejecucion_para(db, target, ejecucion_id)
    R.meses_evaluados(db, ej, periodo, ubigeo)  # 404 si no hay nada que exportar
    filas = R.filas_mensuales(db, ej, periodo, ubigeo)
    sin_dato = R.filas_sin_dato(db, ej, periodo, ubigeo)  # estimación del mes que aún no tiene denuncias registradas (puede no haber)
    meta = X.metadata(ej, target, nombre, periodo)
    if formato == "csv":
        cuerpo, tipo = X.csv_bytes(meta, filas, sin_dato), "text/csv; charset=utf-8"
    else:
        met = R.metricas(db, ej, periodo, [ubigeo] if ubigeo else None)
        if ubigeo:
            errores = _error_promedio(met.get(ubigeo, {}))
        else:
            ultimo = max(f["fecha"] for f in filas)
            reg = {f["ubigeo"]: f["observado"] for f in filas if f["fecha"] == ultimo}
            errores = []
            for d in R.distritos(db):
                ep = {e["estrategia"]: e["denuncias_por_mes"] for e in _error_promedio(met.get(d["ubigeo"], {}))}
                errores.append([d["nombre"], reg.get(d["ubigeo"], "—")] + [X._coma(ep[e]) for e in R.ESTRATEGIAS])
        cuerpo, tipo = X.pdf_bytes(meta, target, nombre, periodo, filas, errores, sin_dato), "application/pdf"
    auditoria.registrar(db, u["user_id"], "exportar", "ejecucion", ej["ejecucion_id"], {"formato": formato, "target": target, "ubigeo": ubigeo, "periodo": periodo})
    db.commit()
    archivo = f"sidpol_{X.DELITO[target]}_{_slug(nombre) if nombre else 'todos_los_distritos'}_{periodo}.{formato}"
    return Response(cuerpo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{archivo}"', "Cache-Control": "no-store"})
