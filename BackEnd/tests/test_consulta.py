"""Paso 6: consulta de resultados (RF-19…23), comparación y trazabilidad del Analista (RF-16…18), RNF-01, RNF-03, RNF-07, RNF-08.
Los resultados salen de una ejecución completada y guardada con el panel real; Local y Global son valores sintéticos
conocidos (el entrenamiento se prueba en test_modelado), así que cada número devuelto se puede recalcular aquí."""
import hashlib
import time
import uuid

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from api_plataforma.servicios.resultados import ETIQUETAS, clave_orden
from common.aviso import AVISO
from common.db import sesion
from common.registrar_config import main as registrar_config
from servicio_modelado import ejecutor, metricas
from tests.comun import CFG, CFG_NAIVE, FIX

SMM = "150138"  # Santa María del Mar: lo usamos para probar la escala cero
SURCO = "150140"
PROHIBIDAS = ("riesgo", "prioridad", "ranking", "mejor", "peor", "ganador", "posicion")


def _con_modelos(pron: pd.DataFrame) -> pd.DataFrame:
    """Agrega Local, Global y Global-E1b con valores conocidos a partir de las referencias."""
    n1 = pron[pron["estrategia"] == "naive1"].copy()
    ne = pron[pron["estrategia"] == "naive_estacional"].copy()
    loc = n1.assign(estrategia="local", variante="E1", y_pred=n1["y_pred"] * 1.1 + 1.0)
    glo = ne.assign(estrategia="global", variante="E1", y_pred=ne["y_pred"] * 0.95 + 0.5)
    e1b = glo.assign(variante="E1b", y_pred=glo["y_pred"] * 1.02)
    return pd.concat([pron, loc, glo, e1b], ignore_index=True)


@pytest.fixture(scope="module")
def datos(engine, entorno, panel_real):
    sha_cfg = registrar_config(aprobar=True)  # configuración v0.8.5 completa, con su ficha
    csv = (FIX / "sidpol_lima.csv").read_bytes()
    out = {"sha_cfg": sha_cfg, "sha_datos": hashlib.sha256(csv).hexdigest(), "pron": {}, "met": {}, "eid": {}}
    entorno["entrar"]("analista")
    with engine.begin() as c:
        cfg_id = c.execute(text("SELECT config_id FROM configuracion_experimento WHERE sha256 = :h"), {"h": sha_cfg}).scalar()
        uid = c.execute(text("SELECT user_id FROM perfil_usuario WHERE rol='analista' LIMIT 1")).scalar()
    for t in ("ROBO", "HURTO"):
        pron, _ = ejecutor.calcular(panel_real[t], CFG_NAIVE, t)
        pron = _con_modelos(pron)
        q = metricas.constantes_q(panel_real[t], "2018-01", "2022-12", 12)
        met = metricas.resumir(pron, q, pd.Timestamp(CFG["regimen_corte"]))
        if t == "ROBO":  # un distrito sin escala: MASE no calculable, con motivo
            m = (met["ubigeo"] == SMM) & (met["metrica"] == "MASE")
            met.loc[m, "valor"], met.loc[m, "motivo_nulo"] = None, metricas.MOTIVO_ESCALA_CERO
        with engine.begin() as c:
            eid = c.execute(text("INSERT INTO ejecucion(version_id, config_id, target, iniciada_por) VALUES (CAST(:v AS uuid), :c, :t, :u) RETURNING ejecucion_id"),
                            {"v": entorno["version"], "c": cfg_id, "t": t, "u": uid}).scalar()
        with sesion() as db:
            ejecutor._persistir(db, {"ejecucion_id": eid}, pron.assign(fecha_origen=pron["fecha_objetivo"] - pd.DateOffset(months=1)), met)
        out["pron"][t], out["met"][t], out["eid"][t] = pron, met, str(eid)
    return out


@pytest.fixture()
def api(lib, datos):
    return lib["api"]


@pytest.fixture()
def h(lib):
    return {r: lib["entrar"](r) for r in ("usuario", "analista", "administrador")}


def _ids(o, acumulado=None):
    """Todas las claves de un JSON, para comprobar que no hay campos prohibidos."""
    acumulado = set() if acumulado is None else acumulado
    if isinstance(o, dict):
        for k, v in o.items():
            acumulado.add(k.lower())
            _ids(v, acumulado)
    elif isinstance(o, list):
        for v in o:
            _ids(v, acumulado)
    return acumulado


def _esperado_ultimo(datos, t, u, estrategia, variante="E1"):
    p = datos["pron"][t]
    f = p[(p["ubigeo"] == u) & (p["estrategia"] == estrategia) & (p["variante"] == variante)]
    return f.sort_values("fecha_objetivo").iloc[-1]


# ---------- resumen del distrito (RF-19, RF-21) ----------
def test_resumen_devuelve_los_numeros_de_la_frase_y_se_recalculan(api, h, datos):
    r = api.get(f"/distritos/{SURCO}/resumen", params={"target": "ROBO"}, headers=h["usuario"])
    assert r.status_code == 200
    d = r.json()
    assert d["distrito"] == "Santiago de Surco" and d["ultimo_mes"] == "2026-07-01" and d["meses_evaluados"] == 43
    assert d["ejecucion_id"] == datos["eid"]["ROBO"] and d["aviso"] == AVISO
    loc = _esperado_ultimo(datos, "ROBO", SURCO, "local")
    assert d["registradas_ultimo_mes"] == int(loc["y_true"])
    e = {x["estrategia"]: x for x in d["estimaciones_ultimo_mes"]}
    assert list(e) == ["local", "global", "naive1", "naive_estacional"] and e["local"]["etiqueta"] == "Modelo por distrito"
    assert e["local"]["valor"] == round(loc["y_pred"]) and e["local"]["diferencia"] == round(loc["y_pred"]) - int(loc["y_true"])
    p = datos["pron"]["ROBO"]
    for ep in d["error_promedio"]:
        fila = p[(p["ubigeo"] == SURCO) & (p["estrategia"] == ep["estrategia"]) & (p["variante"].isin(["E1", "base"]))]
        assert ep["etiqueta"] == ETIQUETAS[ep["estrategia"]]
        assert ep["denuncias_por_mes"] == pytest.approx((fila["y_true"] - fila["y_pred"]).abs().mean(), abs=0.05) and ep["mase"] is not None
    assert d["rango_habitual"]["min"] <= d["registradas_ultimo_mes"] <= d["rango_habitual"]["max"]
    assert "MASE" in d["mase_explicacion"]


@pytest.mark.parametrize("periodo,ultimo,meses", [("antes_nov_2024", "2024-10-01", 22), ("desde_nov_2024", "2026-07-01", 21), ("todo", "2026-07-01", 43)])
def test_periodos_filtran_sin_recalcular(api, h, datos, engine, periodo, ultimo, meses):
    d = api.get(f"/distritos/{SURCO}/resumen", params={"target": "ROBO", "periodo": periodo}, headers=h["usuario"]).json()
    assert d["ultimo_mes"] == ultimo and d["meses_evaluados"] == meses
    with engine.connect() as c:  # el número mostrado es el guardado, no uno nuevo
        guardado = c.execute(text("SELECT valor FROM metrica_desempeno WHERE ejecucion_id = CAST(:e AS uuid) AND ubigeo = :u AND estrategia = 'local' AND variante = 'E1' "
                                  "AND metrica = 'MAE' AND periodo = :p"), {"e": datos["eid"]["ROBO"], "u": SURCO, "p": {"todo": "general", "antes_nov_2024": "pre_break", "desde_nov_2024": "post_break"}[periodo]}).scalar()
    assert next(x for x in d["error_promedio"] if x["estrategia"] == "local")["denuncias_por_mes"] == round(guardado, 1)


def test_mase_no_calculable_se_guarda_como_nulo_no_como_nan(engine, datos):
    with engine.connect() as c:
        nan = c.execute(text("SELECT count(*) FROM metrica_desempeno WHERE valor = 'NaN'::float8")).scalar()
        nulos = c.execute(text("SELECT count(*) FROM metrica_desempeno WHERE valor IS NULL AND ejecucion_id = CAST(:e AS uuid)"), {"e": datos["eid"]["ROBO"]}).scalar()
    assert nan == 0 and nulos == 15  # 5 estrategias × 3 periodos del distrito sin escala


def test_distrito_sin_escala_viene_con_motivo_y_sigue_mostrando_el_error_en_denuncias(api, h):
    d = api.get(f"/distritos/{SMM}/resumen", params={"target": "ROBO"}, headers=h["usuario"]).json()
    for x in d["error_promedio"]:
        assert x["mase"] is None and "escala" in x["motivo"] and x["denuncias_por_mes"] is not None


# ---------- serie (RF-20, RF-21) ----------
def test_serie_marca_el_cambio_de_nov_2024_y_trae_estimaciones_desde_el_primer_origen(api, h, datos):
    d = api.get(f"/distritos/{SURCO}/serie", params={"target": "HURTO"}, headers=h["analista"]).json()
    assert d["cambio_registro"]["fecha"] == "2024-11-01" and "nov 2024" in d["cambio_registro"]["texto"]
    assert len(d["puntos"]) == 103 and d["puntos"][0]["fecha"] == "2018-01-01"
    con = [p for p in d["puntos"] if p["estimaciones"]]
    assert len(con) == 43 and con[0]["fecha"] == "2023-01-01" and set(con[0]["estimaciones"]) == {"local", "global", "naive1", "naive_estacional"}
    assert {p["regimen"] for p in d["puntos"]} == {"antes_nov_2024", "desde_nov_2024"}
    antes = api.get(f"/distritos/{SURCO}/serie", params={"target": "HURTO", "periodo": "antes_nov_2024"}, headers=h["analista"]).json()["puntos"]
    despues = api.get(f"/distritos/{SURCO}/serie", params={"target": "HURTO", "periodo": "desde_nov_2024"}, headers=h["analista"]).json()["puntos"]
    assert len(antes) == 82 and len(despues) == 21 and antes[-1]["fecha"] == "2024-10-01" and despues[0]["fecha"] == "2024-11-01"


# ---------- tabla de distritos (RF-22) ----------
def test_distritos_y_tabla_son_alfabeticos_por_defecto(api, h):
    ds = api.get("/distritos", headers=h["usuario"]).json()
    nombres = [d["nombre"] for d in ds]
    assert len(ds) == 43 and nombres == sorted(nombres, key=clave_orden)
    t = api.get("/distritos/resumen", params={"target": "ROBO"}, headers=h["usuario"]).json()
    assert [f["distrito"] for f in t["filas"]] == nombres and t["ultimo_mes"] == "2026-07-01" and t["aviso"] == AVISO
    assert all(len(f["error_promedio"]) == 4 for f in t["filas"])


def test_la_tabla_se_ordena_solo_si_la_persona_lo_pide_y_se_filtra_por_distritos(api, h):
    t = api.get("/distritos/resumen", params={"target": "ROBO", "orden": "local", "dir": "desc"}, headers=h["usuario"]).json()["filas"]
    v = [next(e["denuncias_por_mes"] for e in f["error_promedio"] if e["estrategia"] == "local") for f in t]
    assert v == sorted(v, reverse=True)
    f = api.get("/distritos/resumen", params={"target": "ROBO", "ubigeos": f"{SURCO},{SMM}"}, headers=h["usuario"]).json()["filas"]
    assert {x["ubigeo"] for x in f} == {SURCO, SMM}
    assert api.get("/distritos/resumen", params={"target": "ROBO", "orden": "riesgo"}, headers=h["usuario"]).status_code == 422
    assert api.get("/distritos/resumen", params={"target": "ROBO", "ubigeos": "abc"}, headers=h["usuario"]).status_code == 422


# ---------- sin resultados: se dice, no se inventa ----------
def test_sin_resultados_lo_dice_tal_cual(api, h, engine):
    r = api.get(f"/distritos/{SURCO}/resumen", params={"target": "ROBO", "ejecucion_id": str(uuid.uuid4())}, headers=h["usuario"])
    assert r.status_code == 404 and r.json()["codigo"] == "SIN_RESULTADOS" and r.json()["mensaje"] == "Todavía no hay resultados de robo."
    assert api.get(f"/distritos/{SURCO}/serie", params={"target": "HURTO", "ejecucion_id": "x"}, headers=h["usuario"]).status_code == 404
    with engine.begin() as c:  # sin ninguna ejecución completada de HURTO
        ids = [r[0] for r in c.execute(text("SELECT ejecucion_id FROM ejecucion WHERE estado='completada' AND target='HURTO'"))]
        c.execute(text("UPDATE ejecucion SET estado='fallida', motivo_fallo='prueba' WHERE estado='completada' AND target='HURTO'"))
    try:
        r = api.get("/distritos/resumen", params={"target": "HURTO"}, headers=h["usuario"])
        assert r.status_code == 404 and r.json()["mensaje"] == "Todavía no hay resultados de hurto."
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE ejecucion SET estado='completada', motivo_fallo=NULL WHERE ejecucion_id = ANY(:i)"), {"i": ids})
    assert api.get(f"/distritos/150199/resumen", params={"target": "ROBO"}, headers=h["usuario"]).json()["codigo"] == "DISTRITO_NO_EXISTE"


# ---------- comparación y trazabilidad del Analista ----------
def test_comparacion_muestra_metricas_y_diferencia_sin_declarar_ganador(api, h, datos):
    d = api.get("/comparacion", params={"target": "ROBO"}, headers=h["analista"]).json()
    assert len(d["filas"]) == 43 and d["aviso"] == AVISO
    m = datos["met"]["ROBO"]
    m = m[(m["periodo"] == "general") & (m["metrica"] == "MASE")]
    loc = m[(m["estrategia"] == "local")].set_index("ubigeo")["valor"]
    glo = m[(m["estrategia"] == "global") & (m["variante"] == "E1")].set_index("ubigeo")["valor"]
    fila = next(f for f in d["filas"] if f["ubigeo"] == SURCO)
    assert [(e["estrategia"], e["variante"]) for e in fila["estrategias"]] == [("local", "E1"), ("global", "E1"), ("naive1", "base"), ("naive_estacional", "base"), ("global", "E1b")]
    assert fila["diferencia_mase_global_menos_local"] == pytest.approx(glo[SURCO] - loc[SURCO], abs=1e-3)
    res = {(x["estrategia"], x["variante"]): x for x in d["resumen"]["mase"]}
    assert res[("local", "E1")]["mediana_mase"] == pytest.approx(loc.dropna().median(), abs=1e-3)
    assert res[("local", "E1")]["iqr_mase"] == pytest.approx(np.percentile(loc.dropna(), [25, 75]), abs=1e-3)
    assert res[("local", "E1")]["distritos"] == 42  # Santa María del Mar no tiene escala
    dif = (glo - loc).dropna()
    assert d["resumen"]["mediana_diferencia_global_menos_local"]["E1"]["mediana"] == pytest.approx(dif.median(), abs=1e-3)
    assert "Negativa" in d["resumen"]["explicacion_diferencia"]
    sin = next(f for f in d["filas"] if f["ubigeo"] == SMM)
    assert sin["estrategias"][0]["mase"] is None and sin["estrategias"][0]["motivo"] and sin["estrategias"][0]["mae"] is not None
    sub = api.get("/comparacion", params={"target": "ROBO", "ubigeos": SURCO}, headers=h["analista"]).json()
    assert len(sub["filas"]) == 1 and d["origen"]["configuracion"]["sha256"] == datos["sha_cfg"]


def test_trazabilidad_une_el_resultado_con_su_version_configuracion_y_ejecucion(api, h, datos):
    p = {"target": "ROBO", "ubigeo": SURCO, "estrategia": "local", "fecha_objetivo": "2026-07-01"}
    d = api.get("/trazabilidad", params=p, headers=h["analista"]).json()
    esperado = _esperado_ultimo(datos, "ROBO", SURCO, "local")
    assert d["estimado"] == pytest.approx(esperado["y_pred"]) and d["observado"] == int(esperado["y_true"])
    assert d["fecha_origen"] == "2026-06-01" and d["variante"] == "E1" and d["ejecucion_id"] == datos["eid"]["ROBO"]
    assert d["version_datos"]["sha256"] == datos["sha_datos"] and d["configuracion"]["sha256"] == datos["sha_cfg"] and d["version_datos"]["corte"] == "2026-07"
    assert api.get("/trazabilidad", params={**p, "variante": "E1b"}, headers=h["analista"]).status_code == 404
    assert api.get("/trazabilidad", params={**p, "estrategia": "global", "variante": "E1b"}, headers=h["analista"]).status_code == 200
    assert api.get("/trazabilidad", params={**p, "fecha_objetivo": "2022-01-01"}, headers=h["analista"]).json()["codigo"] == "RESULTADO_NO_EXISTE"


def test_ficha_informativa_en_lenguaje_llano_con_la_configuracion_al_final(api, h, datos):
    d = api.get("/ficha", headers=h["usuario"]).json()
    ids = [s["id"] for s in d["secciones"]]
    assert ids[0] == "que_muestra" and ids[-1] == "detalle_tecnico" and "cambio_de_registro" in ids
    assert len(d["configuracion"]["sha256"]) == 64 and d["aviso"] == AVISO
    assert all(s["titulo"] and s["texto"] for s in d["secciones"])


# ---------- reglas transversales ----------
def test_ninguna_respuesta_trae_riesgo_prioridad_ranking_ni_mejor(api, h):
    llamadas = [("/distritos", {}), (f"/distritos/{SURCO}/resumen", {"target": "ROBO"}), (f"/distritos/{SURCO}/serie", {"target": "ROBO"}),
                ("/distritos/resumen", {"target": "HURTO"}), ("/ficha", {}), ("/comparacion", {"target": "ROBO"}),
                ("/trazabilidad", {"target": "ROBO", "ubigeo": SURCO, "estrategia": "global", "fecha_objetivo": "2026-07-01"})]
    for ruta, q in llamadas:
        r = api.get(ruta, params=q, headers=h["analista"])
        assert r.status_code == 200, ruta
        claves = _ids(r.json())
        assert not [k for k in claves if any(p in k for p in PROHIBIDAS)], (ruta, claves)
        if "aviso" in r.json() or ruta != "/distritos":
            assert r.json().get("aviso") == AVISO or ruta == "/distritos"


@pytest.mark.parametrize("rol,esperado", [("usuario", 200), ("analista", 200), ("administrador", 200), ("sin_sesion", 401)])
@pytest.mark.parametrize("ruta,q", [("/distritos", {}), (f"/distritos/{SURCO}/resumen", {"target": "ROBO"}), (f"/distritos/{SURCO}/serie", {"target": "ROBO"}),
                                    ("/distritos/resumen", {"target": "ROBO"}), ("/ficha", {})])
def test_consulta_para_los_tres_roles_y_nunca_sin_sesion(api, h, rol, esperado, ruta, q):
    assert api.get(ruta, params=q, headers={} if rol == "sin_sesion" else h[rol]).status_code == esperado


@pytest.mark.parametrize("rol,esperado", [("usuario", 403), ("administrador", 403), ("sin_sesion", 401), ("analista", 200)])
@pytest.mark.parametrize("ruta,q", [("/comparacion", {"target": "ROBO"}),
                                    ("/trazabilidad", {"target": "ROBO", "ubigeo": SURCO, "estrategia": "local", "fecha_objetivo": "2026-07-01"})])
def test_comparacion_y_trazabilidad_solo_para_el_analista(api, h, rol, esperado, ruta, q):
    assert api.get(ruta, params=q, headers={} if rol == "sin_sesion" else h[rol]).status_code == esperado


def test_rnf01_las_vistas_de_consulta_responden_en_menos_de_3_segundos_p95(api, h):
    llamadas = [(f"/distritos/{SURCO}/resumen", {"target": "ROBO"}), (f"/distritos/{SURCO}/serie", {"target": "ROBO"}),
                ("/distritos/resumen", {"target": "ROBO"}), ("/comparacion", {"target": "HURTO"}), ("/ficha", {})]
    tiempos = []
    for _ in range(12):
        for ruta, q in llamadas:
            t0 = time.perf_counter()
            assert api.get(ruta, params=q, headers=h["analista"]).status_code == 200
            tiempos.append(time.perf_counter() - t0)
    assert np.percentile(tiempos, 95) <= 3.0


# ---------- exportación (RF-24, RF-25, RNF-08) ----------
def _csv(api, headers, **q):
    import io
    r = api.get("/exportaciones", params={"formato": "csv", "target": "ROBO", **q}, headers=headers)
    assert r.status_code == 200, r.text
    texto = r.content.decode("utf-8-sig")
    return r, texto, pd.read_csv(io.StringIO(texto), comment="#", dtype={"ubigeo": str})


def _pdf(api, headers, **q):
    import io
    import re

    from pypdf import PdfReader
    r = api.get("/exportaciones", params={"formato": "pdf", "target": "ROBO", **q}, headers=headers)
    assert r.status_code == 200, r.text
    paginas = [re.sub(r"\s+", " ", p.extract_text()) for p in PdfReader(io.BytesIO(r.content)).pages]
    return r, paginas


def test_csv_de_un_distrito_trae_aviso_metadata_y_los_numeros_guardados(api, h, datos):
    r, texto, df = _csv(api, h["usuario"], ubigeo=SURCO)
    assert r.headers["content-type"].startswith("text/csv") and r.content[:3] == b"\xef\xbb\xbf"
    assert r.headers["content-disposition"] == 'attachment; filename="sidpol_robo_santiago_de_surco_todo.csv"'
    cabecera = texto.split("distrito,ubigeo")[0]
    for esperado in (f"# Aviso: {AVISO}", "# Delito: robo", "# Distrito: Santiago de Surco", f"# SHA-256 de los datos: {datos['sha_datos']}",
                     f"# Ejecución: {datos['eid']['ROBO']}", f"# SHA-256 de la configuración: {datos['sha_cfg']}", "# Versión de datos: extracto_lima.csv (corte 2026-07)", "Modelo por distrito"):
        assert esperado in cabecera, esperado
    assert len(df) == 43 * 4 and set(df["estrategia"]) == set(ETIQUETAS.values()) and (df["ubigeo"] == SURCO).all()
    p = datos["pron"]["ROBO"]
    esperado = p[(p["ubigeo"] == SURCO) & (p["estrategia"] == "local") & (p["fecha_objetivo"] == "2026-07-01")].iloc[0]
    f = df[(df["mes"] == "2026-07") & (df["estrategia"] == ETIQUETAS["local"])].iloc[0]
    assert f["estimado"] == pytest.approx(esperado["y_pred"], abs=0.005) and f["denuncias_registradas"] == int(esperado["y_true"])
    assert f["diferencia_estimado_menos_registrado"] == pytest.approx(esperado["y_pred"] - esperado["y_true"], abs=0.01)


def test_csv_de_todos_los_distritos_y_por_periodo(api, h):
    _, _, todos = _csv(api, h["analista"])
    assert len(todos) == 43 * 43 * 4 and todos["ubigeo"].nunique() == 43
    _, _, despues = _csv(api, h["analista"], ubigeo=SURCO, periodo="desde_nov_2024")
    assert len(despues) == 21 * 4 and set(despues["periodo"]) == {"desde_nov_2024"} and despues["mes"].min() == "2024-11"


def test_pdf_de_un_distrito_trae_aviso_frase_tabla_y_metadata(api, h, datos):
    r, paginas = _pdf(api, h["usuario"], ubigeo=SURCO)
    assert r.content[:4] == b"%PDF" and r.headers["content-disposition"].endswith('.pdf"')
    texto = " ".join(paginas)
    assert AVISO in texto
    for esperado in ("Santiago de Surco", "jul 2026", "MASE", "Error promedio", datos["sha_datos"], datos["sha_cfg"], datos["eid"]["ROBO"], "Modelo por distrito"):
        assert esperado in texto, esperado
    assert "riesgo" not in texto.lower() and "prioridad" not in texto.lower()


def test_pdf_de_todos_los_distritos_lleva_el_aviso_en_cada_pagina(api, h, datos):
    t0 = time.perf_counter()
    _, paginas = _pdf(api, h["administrador"])
    assert time.perf_counter() - t0 <= 3.0
    assert len(paginas) >= 2 and AVISO in paginas[0]
    assert all("Denuncias registradas en SIDPOL; no es la criminalidad real" in p for p in paginas)  # RNF-08: pie en cada página
    assert "Santa María del Mar" in " ".join(paginas) and "No calculable" not in " ".join(paginas)


@pytest.mark.parametrize("rol,esperado", [("usuario", 200), ("analista", 200), ("administrador", 200), ("sin_sesion", 401)])
@pytest.mark.parametrize("formato", ["csv", "pdf"])
def test_exportar_para_los_tres_roles_y_nunca_sin_sesion(api, h, rol, esperado, formato):
    r = api.get("/exportaciones", params={"formato": formato, "target": "HURTO", "ubigeo": SURCO}, headers={} if rol == "sin_sesion" else h[rol])
    assert r.status_code == esperado


def test_exportar_deja_registro_y_rechaza_pedidos_invalidos(api, h, engine, datos):
    with engine.connect() as c:
        antes = c.execute(text("SELECT count(*) FROM evento_auditoria WHERE accion = 'exportar'")).scalar()
    assert api.get("/exportaciones", params={"formato": "csv", "target": "ROBO", "ubigeo": SURCO}, headers=h["usuario"]).status_code == 200
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM evento_auditoria WHERE accion = 'exportar'")).scalar() == antes + 1
    assert api.get("/exportaciones", params={"formato": "xlsx", "target": "ROBO"}, headers=h["usuario"]).status_code == 422
    assert api.get("/exportaciones", params={"formato": "csv", "target": "ROBO", "ubigeo": "150199"}, headers=h["usuario"]).json()["codigo"] == "DISTRITO_NO_EXISTE"
    r = api.get("/exportaciones", params={"formato": "csv", "target": "ROBO", "ejecucion_id": str(uuid.uuid4())}, headers=h["usuario"])
    assert r.status_code == 404 and r.json()["codigo"] == "SIN_RESULTADOS"  # sin resultados no se exporta nada inventado
