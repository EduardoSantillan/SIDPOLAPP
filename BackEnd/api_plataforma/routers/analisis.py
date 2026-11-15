"""Análisis del Analista (RF-16, RF-17, RF-18): comparación Local vs Global y referencias, y trazabilidad de un resultado.
Muestra métricas y diferencias; no declara cuál es mejor."""
import statistics
from datetime import date

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api_plataforma.schemas import ComparacionOut, TrazabilidadOut
from api_plataforma.servicios import resultados as R
from api_plataforma.servicios.resultados import Estrategia, Periodo, Target
from common.aviso import AVISO
from common.db import get_db
from common.errores import ErrorNegocio
from common.seguridad import requiere_rol

router = APIRouter(tags=["analisis"], dependencies=[Depends(requiere_rol("analista"))])

# (estrategia, variante) en orden fijo; la sensibilidad E1b va al final y se rotula aparte.
CLAVES = [(e, R.PRINCIPAL[e]) for e in R.ESTRATEGIAS] + [("global", "E1b")]


def _etiqueta(est: str, var: str) -> str:
    return R.ETIQUETA_E1B if var == "E1b" else R.ETIQUETAS[est]


def _val(m: dict, metrica: str):
    return R.redondear(m.get(metrica, (None, None))[0], 3)


def _dif(met: dict, variante_global: str):
    g, l = met.get(("global", variante_global), {}).get("MASE", (None, None))[0], met.get(("local", "E1"), {}).get("MASE", (None, None))[0]
    return None if g is None or l is None else g - l


@router.get("/comparacion", response_model=ComparacionOut)
def comparacion(target: Target, periodo: Periodo = "todo", ubigeos: str | None = None, ejecucion_id: str | None = None, db: Session = Depends(get_db)):
    lista = R.lista_ubigeos(db, ubigeos)
    ej = R.ejecucion_para(db, target, ejecucion_id)
    R.meses_evaluados(db, ej, periodo)  # 404 si el periodo no tiene meses evaluados
    met = R.metricas(db, ej, periodo, lista, con_e1b=True)
    filas = []
    for d in R.distritos(db):
        if lista is not None and d["ubigeo"] not in lista:
            continue
        m = met.get(d["ubigeo"], {})
        e1, e1b = _dif(m, "E1"), _dif(m, "E1b")
        filas.append({
            "ubigeo": d["ubigeo"], "distrito": d["nombre"],
            "estrategias": [{"estrategia": e, "variante": v, "etiqueta": _etiqueta(e, v), "mase": _val(m.get((e, v), {}), "MASE"),
                             "motivo": m.get((e, v), {}).get("MASE", (None, None))[1], "mae": _val(m.get((e, v), {}), "MAE"),
                             "rmse": _val(m.get((e, v), {}), "RMSE")} for e, v in CLAVES],
            "diferencia_mase_global_menos_local": R.redondear(e1, 3),
            "diferencia_mase_global_e1b_menos_local": R.redondear(e1b, 3)})
    resumen = []
    for e, v in CLAVES:  # mediana y rango intercuartílico, no promedio
        x = [m[(e, v)]["MASE"][0] for m in met.values() if (e, v) in m and m[(e, v)].get("MASE", (None,))[0] is not None]
        q = np.percentile(x, [25, 75]).tolist() if x else [None, None]
        resumen.append({"estrategia": e, "variante": v, "etiqueta": _etiqueta(e, v), "distritos": len(x),
                        "mediana_mase": R.redondear(statistics.median(x), 3) if x else None, "iqr_mase": [R.redondear(i, 3) for i in q]})
    dif = {}
    for clave, v in (("E1", "E1"), ("E1b", "E1b")):
        x = [d for d in (_dif(m, v) for m in met.values()) if d is not None]
        dif[clave] = {"distritos": len(x), "mediana": R.redondear(statistics.median(x), 3) if x else None}
    return {"target": target, "periodo": periodo, "filas": filas,
            "resumen": {"mase": resumen, "mediana_diferencia_global_menos_local": dif, "explicacion_diferencia": R.SIGNO_DIFERENCIA},
            "mase_explicacion": R.MASE_EXPLICACION,
            "origen": {"ejecucion_id": str(ej["ejecucion_id"]), "version_datos": {"nombre": ej["nombre_archivo"], "corte": ej["periodo_corte"].strftime("%Y-%m"), "sha256": ej["sha_datos"]},
                       "configuracion": {"nombre": ej["cfg_nombre"], "version": ej["cfg_version"], "sha256": ej["cfg_sha"]}},
            "aviso": AVISO}


@router.get("/trazabilidad", response_model=TrazabilidadOut)
def trazabilidad(target: Target, ubigeo: str, estrategia: Estrategia, fecha_objetivo: date, variante: str | None = None,
                 ejecucion_id: str | None = None, db: Session = Depends(get_db)):
    R.distrito(db, ubigeo)
    ej = R.ejecucion_para(db, target, ejecucion_id)
    var = variante or R.PRINCIPAL[estrategia]
    f = db.execute(
        text("SELECT fecha_origen, fecha_objetivo, estimado, observado FROM resultado_pronostico "
             "WHERE ejecucion_id = :e AND ubigeo = :u AND estrategia = :s AND variante = :v AND fecha_objetivo = :f"),
        {"e": ej["ejecucion_id"], "u": ubigeo, "s": estrategia, "v": var, "f": fecha_objetivo}).mappings().first()
    if not f:
        raise ErrorNegocio(404, "RESULTADO_NO_EXISTE", "No hay un resultado con esos datos en esa ejecución.")
    return {"ejecucion_id": str(ej["ejecucion_id"]), "target": target, "ubigeo": ubigeo, "estrategia": estrategia, "variante": var,
            "fecha_origen": f["fecha_origen"].isoformat(), "fecha_objetivo": f["fecha_objetivo"].isoformat(),
            "observado": f["observado"], "estimado": f["estimado"],
            "version_datos": {"nombre": ej["nombre_archivo"], "corte": ej["periodo_corte"].strftime("%Y-%m"), "sha256": ej["sha_datos"]},
            "configuracion": {"nombre": ej["cfg_nombre"], "version": ej["cfg_version"], "sha256": ej["cfg_sha"]}, "aviso": AVISO}
