"""Paso 4: ejecuciones con referencias naïve y métricas (RF-12…15, RNF-06, RNF-07, RNF-09).
Los valores se comparan contra los resultados reales del paquete del asesor (fixtures del repo)."""
import importlib.util
import json
import tempfile
import uuid
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from common import limite
from common import panel as P
from common.registrar_config import RUTA, main as registrar_config
from common.seguridad import hash_password
from servicio_modelado import ejecutor, motores
from tests.sintetico import csv_sintetico

from tests.comun import CFG, CFG_NAIVE, FIX  # noqa: E402


# ---------- cálculo puro contra los resultados del asesor (fixtures en conftest) ----------
@pytest.mark.parametrize("target", ["ROBO", "HURTO"])
def test_referencias_y_metricas_coinciden_con_el_asesor(panel_real, target):
    pron, met = ejecutor.calcular(panel_real[target], CFG_NAIVE, target)
    ref = pd.read_csv(FIX / "referencia_naive.csv", dtype={"UBIGEO": str}, parse_dates=["forecast_month"])
    ref = ref[ref["target"] == target].replace({"strategy": {"naive_seasonal": "naive_estacional"}})
    m = pron.merge(ref, left_on=["ubigeo", "fecha_objetivo", "estrategia"], right_on=["UBIGEO", "forecast_month", "strategy"], validate="1:1")
    assert len(pron) == len(ref) == 2 * 43 * 43
    assert np.array_equal(m["y_pred_x"], m["y_pred_y"]) and np.array_equal(m["y_true_x"], m["y_true_y"])

    mref = pd.read_csv(FIX / "metricas_naive.csv", dtype={"UBIGEO": str})
    mref = mref[mref["target"] == target].replace({"strategy": {"naive_seasonal": "naive_estacional"}})
    g = met[met["periodo"] == "general"].pivot_table(index=["ubigeo", "estrategia"], columns="metrica", values="valor").reset_index()
    j = g.merge(mref, left_on=["ubigeo", "estrategia"], right_on=["UBIGEO", "strategy"], validate="1:1")
    assert len(j) == 86
    for col in ("MASE", "MAE", "RMSE"):
        np.testing.assert_allclose(j[f"{col}_x"], j[f"{col}_y"], rtol=1e-9)


def test_constantes_de_escala_iguales_a_las_del_notebook(panel_real):
    ref = pd.read_csv(FIX / "mase_constantes.csv", dtype={"UBIGEO": str})
    for t in ("ROBO", "HURTO"):
        q = ejecutor.metricas.constantes_q(panel_real[t], "2018-01", "2022-12", 12)
        r = ref[ref["target"] == t].set_index("UBIGEO")["Q_j"]
        np.testing.assert_allclose(q.reindex(r.index), r, rtol=1e-12)


def test_periodos_y_mase_nulo_con_motivo(panel_real):
    p = panel_real["ROBO"].copy()
    u0 = p["ubigeo"].iloc[0]
    p.loc[(p["ubigeo"] == u0) & (p["fecha"] <= "2022-12-01"), "y"] = 5  # serie constante → escala 0
    _, met = ejecutor.calcular(p, CFG_NAIVE, "ROBO")
    assert set(met["periodo"]) == {"general", "pre_break", "post_break"}
    nulos = met[(met["ubigeo"] == u0) & (met["metrica"] == "MASE")]
    assert nulos["valor"].isna().all() and nulos["motivo_nulo"].notna().all()
    assert met[(met["ubigeo"] == u0) & (met["metrica"] == "MAE")]["valor"].notna().all()


def test_version_que_no_llega_al_ultimo_mes_falla_con_motivo_claro(panel_real):
    p = panel_real["ROBO"]
    corto = p[p["fecha"] < "2026-07-01"]
    with pytest.raises(ejecutor.ErrorEjecucion, match="llega hasta 2026-06"):
        ejecutor.calcular(corto, CFG_NAIVE, "ROBO")


# ---------- ejecuciones por la API (fixtures `entorno` y `lib` en conftest) ----------
def _conteo(engine, tabla, eid):
    with engine.connect() as c:
        return c.execute(text(f"SELECT count(*) FROM {tabla} WHERE ejecucion_id = CAST(:e AS uuid)"), {"e": eid}).scalar()


@pytest.mark.parametrize("target", ["ROBO", "HURTO"])
def test_ejecucion_completa_persiste_resultados_trazables(lib, engine, target):
    api, h = lib["api"], lib["entrar"]("analista")
    r = api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": target})
    assert r.status_code == 202 and r.json()["estado"] == "en_curso"
    eid = r.json()["ejecucion_id"]
    d = api.get(f"/ejecuciones/{eid}", headers=h).json()
    assert d["estado"] == "completada" and d["motivo"] is None and d["fin"]
    assert d["configuracion"]["sha256"] == lib["sha"] and d["version"]["corte"] == "2026-07"  # RNF-07
    assert _conteo(engine, "resultado_pronostico", eid) == 2 * 43 * 43
    assert _conteo(engine, "metrica_desempeno", eid) == 2 * 43 * 3 * 3
    with engine.connect() as c:
        mal = c.execute(text("SELECT count(*) FROM resultado_pronostico WHERE ejecucion_id = CAST(:e AS uuid) AND (observado IS NULL OR fecha_origen >= fecha_objetivo)"), {"e": eid}).scalar()
        aud = c.execute(text("SELECT count(*) FROM evento_auditoria WHERE accion='iniciar_ejecucion' AND objeto_id=:e"), {"e": eid}).scalar()
    assert mal == 0 and aud == 1
    assert eid in {x["ejecucion_id"] for x in api.get("/ejecuciones", headers=h).json()["items"]}


@pytest.mark.parametrize("kw,motivo", [({"omitir_mes": "2018-06"}, "invalida"), ({"extra_ubigeo": "150199"}, "con_pendientes")])
def test_rnf06_no_se_ejecuta_sobre_versiones_no_integras(lib, engine, kw, motivo):
    api, admin, h = lib["api"], lib["admin"], lib["entrar"]("analista")
    csv = csv_sintetico(variante=uuid.uuid4().int % 10**9, **kw)
    v = api.post("/versiones", headers=admin, data={"periodo_corte": "2019-12", "version": "x"}, files={"archivo": (f"{uuid.uuid4().hex[:6]}.csv", csv, "text/csv")}).json()
    assert v["estado"] == motivo
    r = api.post("/ejecuciones", headers=h, json={"version_id": v["id"], "target": "ROBO"})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_NO_INTEGRA" and r.json()["detalle"]["motivo"] == motivo
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ejecucion WHERE version_id = CAST(:v AS uuid)"), {"v": v["id"]}).scalar() == 0


def test_version_inexistente_y_configuracion_no_aprobada(lib, engine):
    api, h = lib["api"], lib["entrar"]("analista")
    assert api.post("/ejecuciones", headers=h, json={"version_id": str(uuid.uuid4()), "target": "ROBO"}).status_code == 404
    assert api.post("/ejecuciones", headers=h, json={"version_id": "x", "target": "ROBO"}).status_code == 404
    assert api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": "ESTAFA"}).status_code == 422
    with engine.begin() as c:
        c.execute(text("UPDATE configuracion_experimento SET aprobada_en = NULL"))
    try:
        r = api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": "ROBO"})
        assert r.status_code == 409 and r.json()["codigo"] == "CONFIGURACION_NO_APROBADA"
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE configuracion_experimento SET aprobada_en = CURRENT_DATE"))


def test_una_en_curso_por_delito_y_robo_no_bloquea_hurto(lib, engine, monkeypatch):
    from api_plataforma.servicios import modelado

    monkeypatch.setattr(modelado, "ejecutar", lambda eid: True)  # el modelado «tarda»: la ejecución queda en curso
    api, h = lib["api"], lib["entrar"]("analista")
    body = {"version_id": lib["version"], "target": "ROBO"}
    assert api.post("/ejecuciones", headers=h, json=body).status_code == 202
    r = api.post("/ejecuciones", headers=h, json=body)
    assert r.status_code == 409 and r.json()["codigo"] == "EJECUCION_EN_CURSO"
    assert api.post("/ejecuciones", headers=h, json={**body, "target": "HURTO"}).status_code == 202


def test_modelado_caido_deja_la_ejecucion_fallida(lib, engine, monkeypatch):
    from api_plataforma.servicios import modelado

    monkeypatch.setattr(modelado, "ejecutar", lambda eid: False)
    api, h = lib["api"], lib["entrar"]("analista")
    r = api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": "ROBO"})
    assert r.status_code == 502
    ultima = api.get("/ejecuciones?limite=1", headers=h).json()["items"][0]
    assert ultima["estado"] == "fallida"
    assert "servicio de modelado" in api.get(f"/ejecuciones/{ultima['ejecucion_id']}", headers=h).json()["motivo"]


def test_falla_a_mitad_de_la_persistencia_no_deja_resultados_parciales(lib, engine, monkeypatch):
    def metricas_rotas(pron, q, corte):  # un periodo inválido rompe el CHECK DESPUÉS de insertar los pronósticos
        m = ejecutor.metricas.resumir.__wrapped__(pron, q, corte)
        m.loc[m.index[-1], "periodo"] = "xx"
        return m

    real = ejecutor.metricas.resumir
    metricas_rotas.__wrapped__ = real
    api, h = lib["api"], lib["entrar"]("analista")
    monkeypatch.setattr(ejecutor.metricas, "resumir", metricas_rotas)
    eid = api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": "ROBO"}).json()["ejecucion_id"]
    d = api.get(f"/ejecuciones/{eid}", headers=h).json()
    assert d["estado"] == "fallida" and "error interno" in d["motivo"]
    assert _conteo(engine, "resultado_pronostico", eid) == 0 and _conteo(engine, "metrica_desempeno", eid) == 0


def test_reinicio_marca_fallida_la_que_quedo_en_curso(lib, engine, monkeypatch):
    from api_plataforma.servicios import modelado

    monkeypatch.setattr(modelado, "ejecutar", lambda eid: True)
    api, h = lib["api"], lib["entrar"]("analista")
    eid = api.post("/ejecuciones", headers=h, json={"version_id": lib["version"], "target": "HURTO"}).json()["ejecucion_id"]
    assert ejecutor.recuperar_en_curso() >= 1
    d = api.get(f"/ejecuciones/{eid}", headers=h).json()
    assert d["estado"] == "fallida" and "reinició" in d["motivo"]


# ---------- roles ----------
@pytest.mark.parametrize("rol", ["usuario", "administrador", "sin_sesion"])
@pytest.mark.parametrize("metodo,ruta", [("POST", "/ejecuciones"), ("GET", "/ejecuciones"), ("GET", f"/ejecuciones/{uuid.uuid4()}")])
def test_solo_el_analista_usa_ejecuciones(lib, rol, metodo, ruta):
    h = {} if rol == "sin_sesion" else lib["entrar"](rol)
    r = lib["api"].request(metodo, ruta, headers=h, json={"version_id": lib["version"], "target": "ROBO"} if metodo == "POST" else None)
    assert r.status_code == (401 if rol == "sin_sesion" else 403)


def test_servicio_interno_de_modelado_exige_clave(engine):
    from servicio_modelado.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/interno/ejecutar", json={"ejecucion_id": str(uuid.uuid4())}).status_code == 403
    assert c.post("/interno/ejecutar", json={"ejecucion_id": str(uuid.uuid4())}, headers={"x-clave-servicio": "s" * 40}).status_code == 202


# ---------- Local y Global (XGBoost): reentrenan en cada origen ----------
# XGBoost 3.4.1 exige Python >= 3.12 (el modelado corre en 3.13); en un entorno sin él estas pruebas se omiten.
con_xgboost = pytest.mark.skipif(importlib.util.find_spec("xgboost") is None, reason="XGBoost no está instalado en este entorno")


@pytest.fixture(scope="module")
def completo(panel_real):
    """Corre la configuración congelada completa (5 estrategias) sobre el panel real: unos 80 s por delito."""
    return {t: ejecutor.calcular(panel_real[t], CFG, t) for t in ("ROBO", "HURTO")}


FUENTES = {("local", "E1"): "local_HL", ("global", "E1"): "global_HL", ("global", "E1b"): "global_HG"}


@con_xgboost
@pytest.mark.lento
@pytest.mark.parametrize("target", ["ROBO", "HURTO"])
def test_local_y_global_coinciden_con_los_resultados_del_asesor(completo, target):
    pron, met = completo[target]
    pron = pron.assign(fuente=[FUENTES.get(k) for k in zip(pron["estrategia"], pron["variante"])]).dropna(subset=["fuente"])
    ref = pd.read_csv(FIX / "referencia_modelos.csv", dtype={"UBIGEO": str}, parse_dates=["forecast_month"])
    ref = ref[ref["target"] == target]
    m = pron.merge(ref, left_on=["ubigeo", "fecha_objetivo", "fuente"], right_on=["UBIGEO", "forecast_month", "strategy"], validate="1:1")
    assert len(pron) == len(ref) == 3 * 43 * 43  # 1.849 por estrategia y delito (3.698 entre los dos delitos)
    assert np.array_equal(m["y_true_x"], m["y_true_y"])
    np.testing.assert_allclose(m["y_pred_x"], m["y_pred_y"], atol=1e-3)  # otro entorno numérico: tolerancia, no igualdad bit a bit

    mref = pd.read_csv(FIX / "metricas_modelos.csv", dtype={"UBIGEO": str})
    mref = mref[mref["target"] == target]
    g = met[(met["periodo"] == "general") & (met["metrica"] == "MASE")]
    g = g.assign(fuente=[FUENTES.get(k) for k in zip(g["estrategia"], g["variante"])]).dropna(subset=["fuente"])
    j = g.merge(mref, left_on=["ubigeo", "fuente"], right_on=["UBIGEO", "strategy"], validate="1:1")
    assert len(j) == 3 * 43
    np.testing.assert_allclose(j["valor"], j["MASE"], atol=1e-6)


@con_xgboost
@pytest.mark.lento
def test_ejecucion_con_las_cinco_estrategias_se_persiste_completa(lib, engine, completo, monkeypatch):
    """La ejecución con la configuración congelada completa guarda las 5 estrategias en una sola transacción."""
    sha = registrar_config(aprobar=True)
    lib["entrar"]("analista")
    with engine.begin() as c:
        cfg_id = c.execute(text("SELECT config_id FROM configuracion_experimento WHERE sha256 = :h"), {"h": sha}).scalar()
        uid = c.execute(text("SELECT user_id FROM perfil_usuario WHERE rol='analista' LIMIT 1")).scalar()
        eid = c.execute(text("INSERT INTO ejecucion(version_id, config_id, target, iniciada_por) VALUES (CAST(:v AS uuid), :c, 'ROBO', :u) RETURNING ejecucion_id"),
                        {"v": lib["version"], "c": cfg_id, "u": uid}).scalar()
    monkeypatch.setattr(ejecutor, "calcular", lambda panel, cfg, target: completo[target])  # el cálculo ya se comprobó arriba
    ejecutor.ejecutar(str(eid))
    assert _conteo(engine, "resultado_pronostico", eid) == 5 * 43 * 43
    assert _conteo(engine, "metrica_desempeno", eid) == 5 * 43 * 3 * 3
    with engine.connect() as c:
        est = {tuple(f) for f in c.execute(text("SELECT DISTINCT estrategia, variante FROM resultado_pronostico WHERE ejecucion_id = :e"), {"e": eid})}
        estado = c.execute(text("SELECT estado FROM ejecucion WHERE ejecucion_id = :e"), {"e": eid}).scalar()
    assert est == {("local", "E1"), ("global", "E1"), ("global", "E1b"), ("naive1", "base"), ("naive_estacional", "base")}
    assert estado == "completada"


# ---------- motores con tres meses (rápidas) ----------
@pytest.fixture(scope="module")
def ctx_robo():
    s = CFG["congelada"]
    return motores.Contexto(target="ROBO", seleccion=s["selected"]["ROBO"], parametros=s["level_params"],
                            variables=["ubigeo" if v == "UBIGEO" else v for v in s["level_features"]])


MESES = list(pd.date_range("2026-05-01", "2026-07-01", freq="MS"))


@con_xgboost
def test_conteo_de_modelos_local_uno_por_distrito_y_origen_global_uno_por_origen(panel_real, ctx_robo):
    p = panel_real["ROBO"]
    local = motores.MOTORES["local_HL"](p, MESES, ctx_robo)
    glob = motores.MOTORES["global_HL"](p, MESES, ctx_robo)
    assert local.attrs["ajustes"] == 3 * 43 and glob.attrs["ajustes"] == 3
    assert len(local) == len(glob) == 3 * 43
    assert motores.MOTORES["naive1"](p, MESES, ctx_robo).attrs["ajustes"] == 0
    for out in (local, glob):
        assert out["y_pred"].notna().all() and (out["y_pred"] >= 0).all()
        assert not out.duplicated(["ubigeo", "fecha_objetivo"]).any()


@con_xgboost
@pytest.mark.parametrize("fuente", ["local_HL", "global_HL", "global_HG"])
def test_sin_fuga_de_informacion_el_pronostico_no_depende_de_meses_posteriores(panel_real, ctx_robo, fuente):
    p = panel_real["ROBO"]
    alterado = p.copy()
    alterado.loc[alterado["fecha"] >= "2026-06-01", "y"] += 500  # cambia el mes pronosticado y los siguientes
    a = motores.MOTORES[fuente](p, [pd.Timestamp("2026-06-01")], ctx_robo)
    b = motores.MOTORES[fuente](alterado, [pd.Timestamp("2026-06-01")], ctx_robo)
    np.testing.assert_array_equal(a["y_pred"], b["y_pred"])


def test_las_variables_no_incluyen_regimen_ni_origen_del_valor():
    assert not {"regime", "regimen", "value_origin"} & set(motores.VARIABLES_NIVEL)
    p = pd.DataFrame({"ubigeo": ["150101"] * 14, "fecha": pd.date_range("2024-01-01", periods=14, freq="MS"), "y": range(14)})
    d = motores.construir_variables(p, ["150101"])
    assert len(d) == 2 and not d["lag_12"].isna().any()  # sin lag_12 se descarta: no se imputa
    assert not {"regime", "value_origin"} & set(d.columns)


def test_falta_un_distrito_en_el_mes_a_pronosticar_falla_con_motivo(panel_real, ctx_robo):
    p = panel_real["ROBO"]
    sin = p[~((p["ubigeo"] == p["ubigeo"].iloc[0]) & (p["fecha"] == "2026-07-01"))]
    with pytest.raises(ejecutor.ErrorEjecucion, match="necesita los 43 distritos"):
        motores.MOTORES["global_HL"](sin, [pd.Timestamp("2026-07-01")], ctx_robo)


def test_si_el_conteo_de_modelos_no_cuadra_la_ejecucion_se_detiene(panel_real, monkeypatch):
    def mal(panel, meses, ctx):
        out = motores.naive1(panel, meses, ctx)
        out.attrs["ajustes"] = 7
        return out

    cfg = {**CFG, "estrategias": [e for e in CFG["estrategias"] if e["fuente"] == "local_HL"]}
    monkeypatch.setitem(motores.MOTORES, "local_HL", mal)
    with pytest.raises(ejecutor.ErrorEjecucion, match="entrenó 7 modelos y debían ser 1849"):
        ejecutor.calcular(panel_real["ROBO"], cfg, "ROBO")


def test_estrategia_desconocida_en_la_configuracion_no_se_omite_en_silencio(panel_real):
    extra = {"entrena": True, "estrategia": "otra", "fuente": "otra_HL", "variante": "E9"}
    cfg = {**CFG_NAIVE, "estrategias": CFG_NAIVE["estrategias"] + [extra]}
    with pytest.raises(ejecutor.ErrorEjecucion, match="no sabe ejecutar"):
        ejecutor.calcular(panel_real["ROBO"], cfg, "ROBO")


# ---------- meses sin dato registrado: estimación hacia adelante (agosto y setiembre de 2026) ----------
def _con_estimacion(cfg: dict, meses: int = 2, ultimo: str | None = None) -> dict:
    ev = {**cfg["evaluacion"], "meses_adelante": meses}
    if ultimo:
        ev["ultimo_mes_pronosticado"] = ultimo
    return {**cfg, "evaluacion": ev}


AGO, SEP = pd.Timestamp("2026-08-01"), pd.Timestamp("2026-09-01")


def test_los_meses_sin_dato_se_estiman_pero_no_cambian_nada_de_lo_evaluado(panel_real):
    base_p, base_m = ejecutor.calcular(panel_real["ROBO"], CFG_NAIVE, "ROBO")
    pron, met = ejecutor.calcular(panel_real["ROBO"], _con_estimacion(CFG_NAIVE), "ROBO")
    nuevo = pron[pron["fecha_objetivo"] >= AGO]
    assert len(pron) == len(base_p) + 2 * 2 * 43 and len(nuevo) == 2 * 2 * 43   # 2 meses x 2 referencias x 43 distritos
    assert nuevo["y_true"].isna().all() and nuevo["y_pred"].notna().all()
    assert (nuevo["fecha_origen"] == pd.Timestamp("2026-07-01")).all()          # los dos, con datos hasta julio
    pd.testing.assert_frame_equal(pron[pron["fecha_objetivo"] <= "2026-07-01"].reset_index(drop=True), base_p.reset_index(drop=True))
    pd.testing.assert_frame_equal(met, base_m)                                  # las métricas no ven los meses sin dato


def test_las_referencias_en_los_meses_sin_dato_repiten_lo_que_dicen_sus_nombres(panel_real):
    p = panel_real["ROBO"]
    pron, _ = ejecutor.calcular(p, _con_estimacion(CFG_NAIVE), "ROBO")

    def mes(estrategia, m):
        return pron[(pron["estrategia"] == estrategia) & (pron["fecha_objetivo"] == m)].set_index("ubigeo")["y_pred"].sort_index().to_numpy()

    def real(m):
        return p[p["fecha"] == m].set_index("ubigeo")["y"].sort_index().to_numpy()
    jul = real(pd.Timestamp("2026-07-01"))
    np.testing.assert_array_equal(mes("naive1", AGO), jul)       # repetir el mes anterior: agosto = julio
    np.testing.assert_array_equal(mes("naive1", SEP), jul)       # y setiembre repite la estimación de agosto, que es julio
    np.testing.assert_array_equal(mes("naive_estacional", AGO), real(pd.Timestamp("2025-08-01")))
    np.testing.assert_array_equal(mes("naive_estacional", SEP), real(pd.Timestamp("2025-09-01")))


def test_para_estimar_meses_sin_dato_la_version_debe_terminar_en_el_ultimo_mes_evaluado(panel_real):
    with pytest.raises(ejecutor.ErrorEjecucion, match="debe terminar en el último mes evaluado"):
        ejecutor.calcular(panel_real["ROBO"], _con_estimacion(CFG_NAIVE, 1, ultimo="2026-06"), "ROBO")


@con_xgboost
@pytest.mark.parametrize("fuente,ajustes", [("local_HL", 43), ("global_HL", 1)])
def test_el_primer_mes_sin_dato_coincide_con_estimarlo_de_a_un_mes_y_el_segundo_se_encadena(panel_real, ctx_robo, fuente, ajustes):
    p = panel_real["ROBO"]
    vacio = pd.DataFrame({"ubigeo": sorted(p["ubigeo"].unique()), "fecha": AGO, "y": np.nan})
    a_un_mes = motores.MOTORES[fuente](pd.concat([p, vacio], ignore_index=True), [AGO], ctx_robo)  # el método de siempre, con agosto vacío
    fut = motores.FUTURO[fuente](p, [AGO, SEP], ctx_robo)
    assert fut.attrs["ajustes"] == ajustes                                      # se entrena una sola vez, con datos hasta julio
    ago, sep = fut[fut["fecha_objetivo"] == AGO], fut[fut["fecha_objetivo"] == SEP]
    np.testing.assert_array_equal(ago.sort_values("ubigeo")["y_pred"], a_un_mes.sort_values("ubigeo")["y_pred"])
    assert len(sep) == 43 and sep["y_pred"].notna().all() and (sep["y_pred"] >= 0).all()
    assert not np.array_equal(ago.sort_values("ubigeo")["y_pred"], sep.sort_values("ubigeo")["y_pred"])


@con_xgboost
def test_setiembre_depende_de_la_estimacion_de_agosto_y_no_ve_nada_posterior_a_julio(panel_real, ctx_robo):
    p = panel_real["ROBO"]
    sep = motores.FUTURO["global_HL"](p, [AGO, SEP], ctx_robo)
    alterado = p.copy()
    alterado.loc[alterado["fecha"] == "2026-07-01", "y"] += 300   # cambiar julio mueve agosto y, encadenado, también setiembre
    sep2 = motores.FUTURO["global_HL"](alterado, [AGO, SEP], ctx_robo)
    assert not np.array_equal(sep["y_pred"], sep2["y_pred"])


def test_la_configuracion_con_estimacion_solo_agrega_los_meses_sin_dato():
    import json
    nueva = json.loads((RUTA.parent / "experimento_v2.json").read_text(encoding="utf-8"))
    assert {k for k in nueva if nueva[k] != CFG.get(k)} == {"evaluacion", "version"}
    assert nueva["evaluacion"] == {**CFG["evaluacion"], "meses_adelante": 2}
