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


# ---------- meses sin dato registrado: estimación hacia adelante ----------
# El modelo sigue siendo el de un mes por delante, entrenado UNA vez con los datos hasta el último mes con dato. El primer mes sin dato
# usa solo datos reales; cada mes siguiente toma la estimación del anterior como si fuera el dato (encadenado), sin redondear.
def _con_mes(panel: pd.DataFrame, mes: pd.Timestamp, valores: dict | None) -> pd.DataFrame:
    """Agrega `mes` para todos los distritos: vacío (el mes a estimar) o con las estimaciones puestas como dato."""
    ubigeos = sorted(panel["ubigeo"].unique())
    y = [np.nan if valores is None else float(valores[u]) for u in ubigeos]
    return pd.concat([panel, pd.DataFrame({"ubigeo": ubigeos, "fecha": mes, "y": y})], ignore_index=True)


def _futuro(panel: pd.DataFrame, meses: list, estimar) -> pd.DataFrame:
    """`estimar(panel_con_mes_vacío, mes)` devuelve {ubigeo: estimación}; se encadena mes a mes."""
    trabajo, filas = panel, []
    for m in meses:
        est = estimar(_con_mes(trabajo, m, None), m)
        filas += [(u, m, v) for u, v in est.items()]
        trabajo = _con_mes(trabajo, m, est)
    return pd.DataFrame(filas, columns=["ubigeo", "fecha_objetivo", "y_pred"])


def _rezago_futuro(k: int) -> Motor:
    def motor(panel, meses, ctx=None):
        def estimar(p, m):
            y = p.set_index(["ubigeo", "fecha"])["y"].astype(float)
            origen = m - pd.DateOffset(months=k)
            faltan = [u for u in sorted(p["ubigeo"].unique()) if (u, origen) not in y.index]
            if faltan:
                raise ErrorEjecucion(f"Falta el dato de {origen:%Y-%m} para estimar {m:%Y-%m}.")
            return {u: y[(u, origen)] for u in sorted(p["ubigeo"].unique())}
        out = _futuro(panel, meses, estimar)
        out.attrs["ajustes"] = 0
        return out
    return motor


def _global_futuro(clave_h: str) -> Motor:
    def motor(panel, meses, ctx):
        distritos, d, h = _preparar(panel, meses, ctx, clave_h)
        modelo = _modelo(ctx, h).fit(d[ctx.variables], d["z"].astype(float))  # entrenado con todo lo que hay, hasta el último mes con dato

        def estimar(p, m):
            test = construir_variables(p, distritos)
            test = test[test["fecha"] == m].sort_values("ubigeo")
            if len(test) != len(distritos):
                raise ErrorEjecucion(f"En {m:%Y-%m} la estimación necesita los {len(distritos)} distritos y hay {len(test)}.")
            return dict(zip(test["ubigeo"].astype(str), _a_denuncias(modelo.predict(test[ctx.variables]))))
        out = _futuro(panel, meses, estimar)
        out.attrs["ajustes"] = 1
        return out
    return motor


def _local_futuro(clave_h: str) -> Motor:
    def motor(panel, meses, ctx):
        distritos, d, h = _preparar(panel, meses, ctx, clave_h)
        modelos = {}
        for u in distritos:
            tr = d[d["ubigeo"] == u]
            if tr.empty:
                raise ErrorEjecucion(f"No hay datos suficientes de {u} para estimar los meses sin dato.")
            modelos[u] = _modelo(ctx, h).fit(tr[ctx.variables], tr["z"].astype(float))  # un modelo por distrito, con sus datos hasta el último mes

        def estimar(p, m):
            test = construir_variables(p, distritos)
            test = test[test["fecha"] == m].sort_values("ubigeo")
            out = {}
            for u in distritos:
                te = test[test["ubigeo"] == u]
                if len(te) != 1:
                    raise ErrorEjecucion(f"No hay datos suficientes de {u} para estimar {m:%Y-%m}.")
                out[u] = float(_a_denuncias(modelos[u].predict(te[ctx.variables]))[0])
            return out
        out = _futuro(panel, meses, estimar)
        out.attrs["ajustes"] = len(distritos)
        return out
    return motor


# fuente → estimación de meses sin dato (mismas fuentes que MOTORES)
FUTURO: dict[str, Motor] = {
    "local_HL": _local_futuro("H_L"),
    "global_HL": _global_futuro("H_L"),
    "global_HG": _global_futuro("H_G"),
    "naive1": _rezago_futuro(1),
    "naive_seasonal": _rezago_futuro(12),
}

# fuente (columna `fuente` de la configuración congelada) → motor
MOTORES: dict[str, Motor] = {
    "local_HL": _local("H_L"),
    "global_HL": _global("H_L"),   # E1: mismos hiperparámetros que el Local
    "global_HG": _global("H_G"),   # E1b: sensibilidad con los hiperparámetros propios del Global
    "naive1": naive1,
    "naive_seasonal": naive_estacional,
}
