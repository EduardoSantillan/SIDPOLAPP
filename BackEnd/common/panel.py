"""Verificación del CSV de SIDPOL y construcción del panel distrito × mes × target.

Port del Notebook 01 (Auditoría SIDPOL) sin fechas fijas: el periodo sale del archivo y se compara con el
`periodo_corte` que registra el administrador. La regla de ceros y el corte de régimen son las del Protocolo.
"""
import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

BREAK_DATE = date(2024, 11, 1)
INICIO_ESPERADO = date(2018, 1, 1)  # la escala del MASE usa 2018-2022: la serie debe partir ahí
TARGETS = ["ROBO", "HURTO"]
DEPARTAMENTO_LIMA = "LIMA METROPOLITANA"
EXPECTED_UBIGEOS = [f"1501{i:02d}" for i in range(1, 44)]
EXPECTED_COLUMNS = ["ANIO", "MES", "DPTO_HECHO_NEW", "PROV_HECHO", "DIST_HECHO", "UBIGEO_HECHO", "P_MODALIDADES", "cantidad"]


class SnapshotInvalido(ValueError):
    """El archivo no se puede leer como CSV de SIDPOL."""


@dataclass
class Control:
    control: str
    aprobado: bool
    detalle: str


@dataclass
class Resultado:
    estado: str  # integra | con_pendientes | invalida
    controles: list[Control] = field(default_factory=list)
    pendientes: dict[str, int] = field(default_factory=dict)  # codigo_original -> filas
    panel: pd.DataFrame | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_ubigeo(series: pd.Series) -> pd.Series:
    return (
        series.astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True).str.zfill(6)
    )


def _decodificar(contenido: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SnapshotInvalido("No se pudo leer el texto del archivo (usa UTF-8 o Latin-1).")


def leer_csv(contenido: bytes) -> pd.DataFrame:
    """Lee el CSV (separador «,» o «;», UTF-8 o Latin-1). Cualquier problema de lectura → SnapshotInvalido."""
    if not contenido.strip():
        raise SnapshotInvalido("El archivo está vacío.")
    texto = _decodificar(contenido)
    primera = texto.split("\n", 1)[0]
    sep = ";" if primera.count(";") > primera.count(",") else ","
    try:
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, quoting=csv.QUOTE_MINIMAL, skipinitialspace=True)
    except Exception as e:  # pandas lanza varios tipos de error de parseo
        raise SnapshotInvalido(f"El archivo no tiene formato CSV válido ({type(e).__name__}).") from e
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    faltan = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if faltan:
        raise SnapshotInvalido(f"Faltan columnas: {', '.join(faltan)}.")
    for c in ("ANIO", "MES", "cantidad"):
        num = pd.to_numeric(df[c], errors="coerce")
        if num.isna().any():
            raise SnapshotInvalido(f"La columna {c} tiene valores que no son números.")
        df[c] = num
    if (df["MES"] % 1 != 0).any() or ((df["MES"] < 1) | (df["MES"] > 12)).any():
        raise SnapshotInvalido("La columna MES debe tener números del 1 al 12.")
    df["UBIGEO"] = clean_ubigeo(df["UBIGEO_HECHO"])
    df["MODALIDAD"] = df["P_MODALIDADES"].astype("string").str.strip().str.upper()
    df["DEPTO"] = df["DPTO_HECHO_NEW"].astype("string").str.strip().str.upper()
    df["fecha"] = pd.to_datetime(dict(year=df["ANIO"].astype(int), month=df["MES"].astype(int), day=1))
    return df


def _meses(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="MS")


def verificar(df: pd.DataFrame, periodo_corte: date, equivalencias: dict[str, str] | None = None,
              inicio_esperado: date = INICIO_ESPERADO) -> Resultado:
    """Controles de RF-05 y estado de la versión. `equivalencias`: código original → UBIGEO resuelto."""
    equivalencias = equivalencias or {}
    c: list[Control] = [Control("estructura", True, "El archivo tiene todas las columnas y números válidos.")]

    def anotar(nombre: str, ok: bool, bien: str, mal: str) -> bool:
        c.append(Control(nombre, ok, bien if ok else mal))
        return ok

    ok = True
    cant = df["cantidad"]
    ok &= anotar("conteos_positivos", bool((cant > 0).all() and (cant % 1 == 0).all()),
                 "Todos los conteos son enteros positivos.", "Hay conteos en cero, negativos o con decimales.")

    meses = _meses(df)
    presentes = df["fecha"].drop_duplicates()
    faltan = meses.difference(pd.DatetimeIndex(presentes))
    ok &= anotar("continuidad_mensual", len(faltan) == 0, f"La serie es mensual y continua ({len(meses)} meses).",
                 "Faltan meses: " + ", ".join(m.strftime("%Y-%m") for m in faltan[:6]) + ("…" if len(faltan) > 6 else "") + ".")
    ok &= anotar("periodo_corte", df["fecha"].max().date() == periodo_corte,
                 f"El último mes del archivo coincide con el periodo de corte ({periodo_corte:%Y-%m}).",
                 f"El último mes del archivo es {df['fecha'].max():%Y-%m} y el periodo de corte indicado es {periodo_corte:%Y-%m}.")
    ok &= anotar("inicio_serie", df["fecha"].min().date() == inicio_esperado,
                 f"La serie empieza en {inicio_esperado:%Y-%m}.",
                 f"La serie empieza en {df['fecha'].min():%Y-%m} y debe empezar en {inicio_esperado:%Y-%m}.")

    lima = df[df["DEPTO"] == DEPARTAMENTO_LIMA].copy()
    # La unicidad se mide sobre los códigos tal como vienen en el archivo; las equivalencias después se suman.
    repetidas = int(lima.duplicated(["fecha", "UBIGEO", "MODALIDAD"]).sum())
    lima["UBIGEO"] = [u if u in EXPECTED_UBIGEOS else equivalencias.get(u) for u in lima["UBIGEO"]]
    sin_reconocer = lima[lima["UBIGEO"].isna()]
    pendientes = df.loc[sin_reconocer.index, "UBIGEO"].value_counts().to_dict() if len(sin_reconocer) else {}
    lima = lima[lima["UBIGEO"].notna()]
    anotar("ubigeo_reconocido", not pendientes, "Todos los códigos de distrito de Lima se reconocieron.",
           f"{len(pendientes)} código(s) de distrito no reconocidos; el administrador debe indicar a qué distrito corresponden.")

    ok &= anotar("claves_unicas", repetidas == 0, "No hay filas repetidas por mes, distrito y delito.",
                 f"Hay {repetidas} fila(s) repetidas por mes, distrito y delito.")

    faltan_d = sorted(set(EXPECTED_UBIGEOS) - set(lima["UBIGEO"]))
    if faltan_d and pendientes:
        c.append(Control("distritos_completos", True, f"Faltan {len(faltan_d)} distrito(s), que pueden venir de los códigos pendientes."))
    else:
        ok &= anotar("distritos_completos", not faltan_d, "Están los 43 distritos de Lima Metropolitana.",
                     "Faltan distritos: " + ", ".join(faltan_d[:6]) + ("…" if len(faltan_d) > 6 else "") + ".")
    falta_t = [t for t in TARGETS if t not in set(lima["MODALIDAD"])]
    ok &= anotar("delitos_presentes", not falta_t, "Hay registros de Robo y de Hurto.", f"No hay registros de: {', '.join(falta_t)}.")

    if not ok:
        return Resultado("invalida", c, pendientes)
    if pendientes:
        return Resultado("con_pendientes", c, pendientes)
    panel = _construir(lima, df, meses)
    ceros = int(panel["value_origin"].str.startswith("reconstructed").sum())
    c.append(Control("ceros_reconstruidos", True,
                     f"{ceros} mes(es) sin registros se tomaron como cero (queda anotado como valor reconstruido)."))
    return Resultado("integra", c, {}, panel)


def _construir(lima: pd.DataFrame, df: pd.DataFrame, meses: pd.DatetimeIndex) -> pd.DataFrame:
    original = lima[lima["UBIGEO_HECHO"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(6).isin(EXPECTED_UBIGEOS)]
    nombres = pd.concat([original, lima]).drop_duplicates("UBIGEO")[["UBIGEO", "DIST_HECHO"]].sort_values("UBIGEO")
    mensual = lima.groupby(["fecha", "UBIGEO", "MODALIDAD"], as_index=False)["cantidad"].sum()
    hay_fila = set(zip(lima["UBIGEO"], lima["fecha"]))

    grid = pd.MultiIndex.from_product([EXPECTED_UBIGEOS, meses, TARGETS], names=["UBIGEO", "fecha", "target"]).to_frame(index=False)
    valores = mensual[mensual["MODALIDAD"].isin(TARGETS)].rename(columns={"MODALIDAD": "target", "cantidad": "y_raw"})
    panel = grid.merge(valores[["UBIGEO", "fecha", "target", "y_raw"]], on=["UBIGEO", "fecha", "target"], how="left").merge(nombres, on="UBIGEO", how="left")

    sin_filas = np.array([(u, f) not in hay_fila for u, f in zip(panel["UBIGEO"], panel["fecha"])])
    panel["value_origin"] = np.where(panel["y_raw"].notna(), "observed",
                                     np.where(sin_filas, "reconstructed_zero_no_rows", "reconstructed_zero_target_absent"))
    panel["y"] = panel["y_raw"].fillna(0).astype(int)
    panel["regime"] = np.where(panel["fecha"] < pd.Timestamp(BREAK_DATE), "pre_break", "post_break")
    return (panel[["fecha", "UBIGEO", "DIST_HECHO", "target", "y", "regime", "value_origin"]]
            .sort_values(["target", "UBIGEO", "fecha"]).reset_index(drop=True))
