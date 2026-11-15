"""Motores de estrategias (AC-05).

- Referencias naïve: no se entrenan.
- Local: un XGBoost por distrito, reentrenado en cada origen con ventana expansiva.
- Global: un XGBoost con los 43 distritos, reentrenado en cada origen con ventana expansiva.

Cada motor recibe el panel de UN target (ubigeo, fecha, y), la lista de meses a pronosticar y un contexto con los
hiperparámetros congelados, y devuelve ubigeo, fecha_objetivo, y_pred. Las predicciones de un mes salen solo de datos
de meses anteriores (sin fuga). El resultado lleva en `attrs["ajustes"]` cuántos modelos se entrenaron (control de conteo
del Protocolo). Las variables y el recorte a cero siguen `sidpol.py` del asesor (build_features, to_counts_from_z).
`regimen` y `value_origin` nunca entran como variables.
"""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from servicio_modelado.errores import ErrorEjecucion

VARIABLES_NIVEL = ["lag_1", "lag_2", "lag_3", "lag_6", "lag_12", "rolling_mean_3", "rolling_mean_6", "mes_sin", "mes_cos", "ubigeo"]


@dataclass
class Contexto:
    """Lo que un motor necesita además del panel: viene de la configuración congelada, no se edita."""
    target: str
    seleccion: dict = field(default_factory=dict)   # configuracion["congelada"]["selected"][target]: H_L, H_G
    parametros: dict = field(default_factory=dict)  # configuracion["congelada"]["level_params"]
    variables: list = field(default_factory=lambda: list(VARIABLES_NIVEL))


Motor = Callable[[pd.DataFrame, list, Contexto], pd.DataFrame]


# ---------- referencias (sin entrenamiento) ----------
def _rezago(panel: pd.DataFrame, meses: list, k: int) -> pd.DataFrame:
    y = panel.set_index(["ubigeo", "fecha"])["y"].astype(float)
    filas = []
    for ubigeo in sorted(panel["ubigeo"].unique()):
        for m in meses:
            origen = m - pd.DateOffset(months=k)
            if (ubigeo, origen) not in y.index:
                raise ValueError(f"Falta el dato de {origen:%Y-%m} para {ubigeo}")
            filas.append((ubigeo, m, y[(ubigeo, origen)]))
    out = pd.DataFrame(filas, columns=["ubigeo", "fecha_objetivo", "y_pred"])
    out.attrs["ajustes"] = 0
    return out


def naive1(panel, meses, ctx=None):
    """Repetir el mes anterior."""
    return _rezago(panel, meses, 1)


def naive_estacional(panel, meses, ctx=None):
    """Repetir el mismo mes del año pasado."""
    return _rezago(panel, meses, 12)


# ---------- variables ----------
def construir_variables(panel: pd.DataFrame, distritos: list) -> pd.DataFrame:
    """Rezagos y medias móviles de z = log1p(y), siempre con meses ANTERIORES de la misma serie (port de build_features)."""
    d = panel.sort_values(["ubigeo", "fecha"]).copy()
    d["z"] = np.log1p(d["y"].astype(float))
    g = d.groupby("ubigeo", observed=True)["z"]
    for k in (1, 2, 3, 6, 12):
        d[f"lag_{k}"] = g.shift(k)
    for v in (3, 6):
        d[f"rolling_mean_{v}"] = g.transform(lambda s, v=v: s.shift(1).rolling(v).mean())
    mes = d["fecha"].dt.month
    d["mes_sin"], d["mes_cos"] = np.sin(2 * np.pi * mes / 12), np.cos(2 * np.pi * mes / 12)
    d["ubigeo"] = d["ubigeo"].astype(pd.CategoricalDtype(categories=distritos, ordered=False))  # las mismas 43 categorías en ambos enfoques
    return d.dropna(subset=["lag_12"]).reset_index(drop=True)  # sin imputar


def _a_denuncias(z_hat) -> np.ndarray:
    """Vuelve a la escala original: expm1 recortado a cero, sin redondear."""
    return np.maximum(np.expm1(np.asarray(z_hat, dtype=float)), 0.0)


def _modelo(ctx: Contexto, h: dict):
    from xgboost import XGBRegressor  # se importa aquí: el servicio de ingesta y la API no lo necesitan
    # n_jobs es de rendimiento, no del modelo: con modelos tan pequeños, -1 en un contenedor con muchos núcleos es ~24 veces más lento.
    return XGBRegressor(**{**ctx.parametros, "n_jobs": 1}, max_depth=int(h["max_depth"]), n_estimators=int(h["n_estimators"]))


def _predecir(ctx: Contexto, h: dict, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    modelo = _modelo(ctx, h).fit(train[ctx.variables], train["z"].astype(float))
    return _a_denuncias(modelo.predict(test[ctx.variables]))


def _preparar(panel: pd.DataFrame, meses: list, ctx: Contexto, clave_h: str):
    if clave_h not in ctx.seleccion or not ctx.parametros:
        raise ErrorEjecucion(f"La configuración no trae los hiperparámetros «{clave_h}» de {ctx.target}.")
    distritos = sorted(panel["ubigeo"].unique())
    d = construir_variables(panel, distritos)
    return distritos, d, ctx.seleccion[clave_h]


def _origen(d: pd.DataFrame, mes: pd.Timestamp, distritos: list):
    train, test = d[d["fecha"] < mes], d[d["fecha"] == mes].sort_values("ubigeo")
    if train.empty or train["fecha"].max() != mes - pd.DateOffset(months=1):
        raise ErrorEjecucion(f"No hay historia hasta {mes - pd.DateOffset(months=1):%Y-%m} para pronosticar {mes:%Y-%m}.")
    if len(test) != len(distritos):
        raise ErrorEjecucion(f"En {mes:%Y-%m} el pronóstico necesita los {len(distritos)} distritos y hay {len(test)}.")
    return train, test


def _global(clave_h: str) -> Motor:
    def motor(panel, meses, ctx):
        distritos, d, h = _preparar(panel, meses, ctx, clave_h)
        filas = []
        for mes in meses:
            train, test = _origen(d, mes, distritos)  # corte temporal: solo meses anteriores
            pred = _predecir(ctx, h, train, test)
            filas.append(pd.DataFrame({"ubigeo": test["ubigeo"].astype(str).to_numpy(), "fecha_objetivo": mes, "y_pred": pred}))
        out = pd.concat(filas, ignore_index=True)
        out.attrs["ajustes"] = len(meses)  # un modelo por origen
        return out
    return motor


def _local(clave_h: str) -> Motor:
    def motor(panel, meses, ctx):
        distritos, d, h = _preparar(panel, meses, ctx, clave_h)
        filas, ajustes = [], 0
        for mes in meses:
            train, test = _origen(d, mes, distritos)
            for u in distritos:
                tr, te = train[train["ubigeo"] == u], test[test["ubigeo"] == u]
                if tr.empty or len(te) != 1:
                    raise ErrorEjecucion(f"No hay datos suficientes de {u} para pronosticar {mes:%Y-%m}.")
                filas.append((u, mes, float(_predecir(ctx, h, tr, te)[0])))
                ajustes += 1  # un modelo por distrito y por origen
        out = pd.DataFrame(filas, columns=["ubigeo", "fecha_objetivo", "y_pred"])
        out.attrs["ajustes"] = ajustes
        return out
    return motor


# fuente (columna `fuente` de la configuración congelada) → motor
MOTORES: dict[str, Motor] = {
    "local_HL": _local("H_L"),
    "global_HL": _global("H_L"),   # E1: mismos hiperparámetros que el Local
    "global_HG": _global("H_G"),   # E1b: sensibilidad con los hiperparámetros propios del Global
    "naive1": naive1,
    "naive_seasonal": naive_estacional,
}
