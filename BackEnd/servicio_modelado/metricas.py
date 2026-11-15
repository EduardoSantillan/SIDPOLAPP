"""Evaluador de métricas (AC-05): errores, MASE con escala fija por serie, y resumen por periodo.

MASE = promedio de |y − ŷ| / Q_j. Q_j es el error absoluto medio de repetir el mismo mes del año anterior
dentro de la ventana de referencia (2018-01…2022-12); es FIJO por serie: no se recalcula por origen ni por periodo.
"""
import numpy as np
import pandas as pd

PERIODOS = ("general", "pre_break", "post_break")
MOTIVO_ESCALA_CERO = "El distrito casi no registra denuncias en el periodo de referencia: la escala del MASE es cero."


def constantes_q(panel: pd.DataFrame, inicio: str, fin: str, estacionalidad: int = 12) -> pd.Series:
    """Q_j por UBIGEO. `panel`: columnas ubigeo, fecha, y (un solo target)."""
    wide = panel.pivot(index="fecha", columns="ubigeo", values="y").sort_index()
    dif = (wide - wide.shift(estacionalidad)).abs()
    ventana = dif.loc[pd.Timestamp(inicio) + pd.DateOffset(months=estacionalidad): pd.Timestamp(fin)]
    return ventana.mean()


def resumir(pronosticos: pd.DataFrame, q: pd.Series, corte: pd.Timestamp) -> pd.DataFrame:
    """`pronosticos`: ubigeo, estrategia, variante, fecha_objetivo, y_true, y_pred.
    Devuelve filas de metrica_desempeno: ubigeo, estrategia, variante, periodo, metrica, valor, motivo_nulo."""
    d = pronosticos.copy()
    d["abs"] = (d["y_true"] - d["y_pred"]).abs()
    d["sq"] = (d["y_true"] - d["y_pred"]) ** 2
    d["q"] = d["ubigeo"].map(q)
    d["scaled"] = np.where(d["q"] > 0, d["abs"] / d["q"].where(d["q"] > 0), np.nan)
    d["regimen"] = np.where(d["fecha_objetivo"] < corte, "pre_break", "post_break")
    filas = []
    for periodo in PERIODOS:
        sub = d if periodo == "general" else d[d["regimen"] == periodo]
        if sub.empty:
            continue
        g = sub.groupby(["ubigeo", "estrategia", "variante"], as_index=False).agg(
            MASE=("scaled", "mean"), MAE=("abs", "mean"), MSE=("sq", "mean"), q=("q", "first"))
        g["RMSE"] = np.sqrt(g.pop("MSE"))
        for r in g.itertuples(index=False):
            for metrica in ("MASE", "MAE", "RMSE"):
                valor = getattr(r, metrica)
                nulo = metrica == "MASE" and not (r.q > 0)
                filas.append((r.ubigeo, r.estrategia, r.variante, periodo, metrica,
                              None if nulo else float(valor), MOTIVO_ESCALA_CERO if nulo else None))
    return pd.DataFrame(filas, columns=["ubigeo", "estrategia", "variante", "periodo", "metrica", "valor", "motivo_nulo"])
