"""AC-05: corre el experimento aprobado sobre una versión íntegra y persiste resultados versionados.

Todo o nada: los resultados se guardan en UNA transacción junto con el estado «completada». Si algo falla en
cualquier etapa, no queda ningún resultado parcial y la ejecución queda «fallida» con un motivo en texto llano.
"""
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from common.db import sesion
from servicio_modelado import metricas
from servicio_modelado.errores import ErrorEjecucion
from servicio_modelado.motores import FUTURO, MOTORES, VARIABLES_NIVEL, Contexto

log = logging.getLogger("sidpol")
MOTIVO_REINICIO = "El servicio se reinició durante la ejecución. Vuelve a iniciarla."


def recuperar_en_curso() -> int:
    """Al arrancar: una ejecución que quedó «en curso» no volverá a terminar sola."""
    with sesion() as db:
        n = db.execute(text("UPDATE ejecucion SET estado='fallida', motivo_fallo=:m, fin=now() WHERE estado='en_curso'"),
                       {"m": MOTIVO_REINICIO}).rowcount
        db.commit()
    return n


def _cargar(db: Session, ejecucion_id: str):
    e = db.execute(
        text("SELECT e.ejecucion_id, e.version_id, e.target, e.estado, v.estado AS estado_version, c.contenido, c.aprobada_en "
             "FROM ejecucion e JOIN version_datos v USING (version_id) JOIN configuracion_experimento c USING (config_id) "
             "WHERE e.ejecucion_id = CAST(:e AS uuid)"), {"e": ejecucion_id}).mappings().first()
    if not e:
        raise ErrorEjecucion("No existe la ejecución.")
    if e["estado_version"] != "integra":
        raise ErrorEjecucion("La versión de datos no está íntegra: no se puede ejecutar.")
    if e["aprobada_en"] is None:
        raise ErrorEjecucion("La configuración del experimento no está aprobada.")
    return e


def _panel(db: Session, version_id, target: str) -> pd.DataFrame:
    filas = db.execute(
        text("SELECT ubigeo, fecha, y FROM observacion_mensual WHERE version_id = :v AND target = :t ORDER BY ubigeo, fecha"),
        {"v": version_id, "t": target}).all()
    df = pd.DataFrame(filas, columns=["ubigeo", "fecha", "y"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def calcular(panel: pd.DataFrame, cfg: dict, target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (pronósticos, métricas) de todas las estrategias de la configuración. Sin acceso a la base."""
    ev = cfg["evaluacion"]
    meses = list(pd.date_range(ev["primer_mes_pronosticado"], ev["ultimo_mes_pronosticado"], freq="MS"))
    ultimo = panel["fecha"].max()
    if panel.empty or ultimo < meses[-1]:
        raise ErrorEjecucion(f"La versión llega hasta {ultimo:%Y-%m} y la configuración evalúa hasta {meses[-1]:%Y-%m}.")
    distritos = panel["ubigeo"].nunique()
    esperados = len(meses) * distritos
    # Meses sin dato registrado (el modelo sigue siendo de un mes por delante): se estiman al final, con los datos hasta el último mes
    # con dato. El primero usa solo datos reales; cada siguiente toma la estimación del anterior como si fuera el dato (encadenado).
    # No entran a ninguna métrica: todavía no hay con qué compararlos.
    adelante = int(ev.get("meses_adelante", 0))
    futuros = [ultimo + pd.DateOffset(months=k) for k in range(1, adelante + 1)]
    if futuros and ultimo != meses[-1]:
        raise ErrorEjecucion(f"Para estimar meses sin dato, la versión debe terminar en el último mes evaluado ({meses[-1]:%Y-%m}) y llega hasta {ultimo:%Y-%m}.")
    cong = cfg.get("congelada", {})
    ctx = Contexto(target=target, seleccion=cong.get("selected", {}).get(target, {}), parametros=cong.get("level_params", {}),
                   variables=["ubigeo" if v == "UBIGEO" else v for v in cong.get("level_features", VARIABLES_NIVEL)])

    y = panel.set_index(["ubigeo", "fecha"])["y"].astype(float)
    partes = []
    for est in cfg["estrategias"]:
        motor = MOTORES.get(est["fuente"])
        if motor is None:
            raise ErrorEjecucion(f"La configuración pide la estrategia «{est['fuente']}», que la plataforma no sabe ejecutar.")
        # Un mes pronosticado solo ve el panel hasta el mes anterior (sin fuga de información).
        p = motor(panel, meses, ctx)
        ajustes = p.attrs.get("ajustes")
        p["estrategia"], p["variante"] = est["estrategia"], est["variante"]
        p["y_true"] = y.reindex(pd.MultiIndex.from_arrays([p["ubigeo"], p["fecha_objetivo"]])).to_numpy()
        # Controles de conteo (Protocolo §6): mismos meses y distritos, valores finitos y no negativos,
        # y los modelos entrenados que corresponden (Local: uno por distrito y origen; Global: uno por origen; naïve: ninguno).
        if len(p) != esperados or p.duplicated(["ubigeo", "fecha_objetivo"]).any():
            raise ErrorEjecucion(f"Los pronósticos de «{est['fuente']}» no tienen exactamente {esperados} filas (distrito × mes).")
        if not (p["y_pred"].notna().all() and np.isfinite(p["y_pred"]).all() and (p["y_pred"] >= 0).all() and p["y_true"].notna().all()):
            raise ErrorEjecucion(f"Hay pronósticos no válidos en «{est['fuente']}».")
        entrenados = {"local": esperados, "global": len(meses)}.get(est["estrategia"], 0) if est.get("entrena") else 0
        if ajustes != entrenados:
            raise ErrorEjecucion(f"«{est['fuente']}» entrenó {ajustes} modelos y debían ser {entrenados}.")
        p["fecha_origen"] = p["fecha_objetivo"] - pd.DateOffset(months=cfg["horizonte_meses"])
        partes.append(p)
        if futuros:
            f = FUTURO[est["fuente"]](panel, futuros, ctx)
            aj_f = f.attrs.get("ajustes")
            f["estrategia"], f["variante"], f["y_true"] = est["estrategia"], est["variante"], np.nan
            f["fecha_origen"] = ultimo  # los datos que vio: hasta el último mes con dato, también para el segundo mes en adelante
            if len(f) != len(futuros) * distritos or f.duplicated(["ubigeo", "fecha_objetivo"]).any():
                raise ErrorEjecucion(f"Las estimaciones de «{est['fuente']}» para los meses sin dato no tienen exactamente {len(futuros) * distritos} filas.")
            if not (f["y_pred"].notna().all() and np.isfinite(f["y_pred"]).all() and (f["y_pred"] >= 0).all()):
                raise ErrorEjecucion(f"Hay estimaciones no válidas en «{est['fuente']}» para los meses sin dato.")
            entrenados_f = {"local": distritos, "global": 1}.get(est["estrategia"], 0) if est.get("entrena") else 0  # un solo entrenamiento, con los datos hasta el último mes
            if aj_f != entrenados_f:
                raise ErrorEjecucion(f"«{est['fuente']}» entrenó {aj_f} modelos para los meses sin dato y debían ser {entrenados_f}.")
            partes.append(f)
    if not partes:
        raise ErrorEjecucion("La configuración no tiene estrategias que la plataforma sepa ejecutar.")
    pron = pd.concat(partes, ignore_index=True)

    esc = cfg["escala_mase"]
    q = metricas.constantes_q(panel, esc["ventana_inicio"], esc["ventana_fin"], esc["estacionalidad_meses"])
    met = metricas.resumir(pron[pron["fecha_objetivo"] <= meses[-1]], q, pd.Timestamp(cfg["regimen_corte"]))  # el mes sin dato no entra a las métricas
    return pron, met


def ejecutar(ejecucion_id: str) -> None:
    with sesion() as db:
        try:
            e = _cargar(db, ejecucion_id)
            if e["estado"] != "en_curso":
                return
            panel = _panel(db, e["version_id"], e["target"])
            pron, met = calcular(panel, e["contenido"], e["target"])
            _persistir(db, e, pron, met)
            log.info("ejecucion %s completada: %d pronósticos, %d métricas", ejecucion_id, len(pron), len(met))
        except ErrorEjecucion as err:
            db.rollback()
            _fallar(db, ejecucion_id, str(err))
        except Exception as err:  # error interno: el detalle va al log, la persona ve un mensaje general
            db.rollback()
            log.exception("ejecucion %s fallida", ejecucion_id)
            _fallar(db, ejecucion_id, f"Falló el cálculo por un error interno ({type(err).__name__}). Vuelve a iniciarla.")


def _persistir(db: Session, e, pron: pd.DataFrame, met: pd.DataFrame) -> None:
    eid = e["ejecucion_id"]
    db.execute(
        text("INSERT INTO resultado_pronostico(ejecucion_id, ubigeo, estrategia, variante, fecha_origen, fecha_objetivo, estimado, observado) "
             "VALUES (:e,:u,:s,:v,:fo,:ft,:p,:o)"),
        [{"e": eid, "u": r.ubigeo, "s": r.estrategia, "v": r.variante, "fo": r.fecha_origen.date(), "ft": r.fecha_objetivo.date(),
          "p": float(r.y_pred), "o": None if pd.isna(r.y_true) else int(r.y_true)} for r in pron.itertuples(index=False)])
    db.execute(
        text("INSERT INTO metrica_desempeno(ejecucion_id, ubigeo, estrategia, variante, periodo, metrica, valor, motivo_nulo) "
             "VALUES (:e,:u,:s,:v,:p,:m,:x,:n)"),
        [{"e": eid, "u": r.ubigeo, "s": r.estrategia, "v": r.variante, "p": r.periodo, "m": r.metrica, "x": None if pd.isna(r.valor) else float(r.valor), "n": r.motivo_nulo}
         for r in met.itertuples(index=False)])
    db.execute(text("UPDATE ejecucion SET estado='completada', fin=now() WHERE ejecucion_id = :e AND estado='en_curso'"), {"e": eid})
    db.commit()


def _fallar(db: Session, ejecucion_id: str, motivo: str) -> None:
    db.execute(text("UPDATE ejecucion SET estado='fallida', motivo_fallo=:m, fin=now() WHERE ejecucion_id = CAST(:e AS uuid) AND estado='en_curso'"),
               {"m": motivo, "e": ejecucion_id})
    db.commit()
