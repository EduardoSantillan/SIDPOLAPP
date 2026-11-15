"""Generador de CSV sintético con la forma del CSV de SIDPOL (para no depender de archivos externos)."""
import io

import pandas as pd

UBIGEOS = [f"1501{i:02d}" for i in range(1, 44)]


def csv_sintetico(inicio="2018-01", fin="2019-12", *, omitir_mes=None, sin_columna=None, extra_ubigeo=None,
                  quitar_distrito=None, con_cero=False, duplicar=False, sep=",", codificacion="utf-8", renombrar_distrito=None, variante=0) -> bytes:
    meses = pd.date_range(inicio, fin, freq="MS")
    filas = []
    for m in meses:
        if omitir_mes and m.strftime("%Y-%m") == omitir_mes:
            continue
        for i, u in enumerate(UBIGEOS):
            if u == quitar_distrito:
                continue
            nombre = f"DISTRITO {u}" if u != "150105" else "BREÑA"
            for mod, base in (("Robo", 20), ("Hurto", 30), ("Otros", 50)):
                if mod == "Robo" and (m.month + i) % 17 == 0:
                    continue  # mes sin robos en ese distrito → ceros reconstruidos
                filas.append((m.year, m.month, "LIMA METROPOLITANA", "LIMA", nombre, u, mod, base + (m.month * i) % 7 + 1))
        if extra_ubigeo:
            filas.append((m.year, m.month, "LIMA METROPOLITANA", "LIMA", "DISTRITO NUEVO", extra_ubigeo, "Robo", 3))
        filas.append((m.year, m.month, "CUSCO", "CUSCO", "CUSCO", "80101", "Robo", 9 + variante))  # otra región: se ignora
    df = pd.DataFrame(filas, columns=["ANIO", "MES", "DPTO_HECHO_NEW", "PROV_HECHO", "DIST_HECHO", "UBIGEO_HECHO", "P_MODALIDADES", "cantidad"])
    if con_cero:
        df.loc[5, "cantidad"] = 0
    if duplicar:
        df = pd.concat([df, df.iloc[[0]]])
    if renombrar_distrito:
        df["DIST_HECHO"] = df["DIST_HECHO"].str.replace("DISTRITO 150101", renombrar_distrito)
    if sin_columna:
        df = df.drop(columns=[sin_columna])
    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=sep)
    return buf.getvalue().encode(codificacion)
