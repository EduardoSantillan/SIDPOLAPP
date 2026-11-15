"""RNF-05: el panel reproduce la salida del Notebook 01 y los totales oficiales de control (diferencia 0).
Fixture dentro del repo: extracto de Lima del CSV de SIDPOL (tests/fixtures)."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from common import panel as P
from tests.sintetico import csv_sintetico

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def resultado():
    df = P.leer_csv((FIX / "sidpol_lima.csv").read_bytes())
    return P.verificar(df, date(2026, 7, 1))


def test_la_version_real_queda_integra(resultado):
    assert resultado.estado == "integra", [c for c in resultado.controles if not c.aprobado]
    assert resultado.pendientes == {}


def test_forma_del_panel(resultado):
    p = resultado.panel
    assert len(p) == 43 * 103 * 2
    assert p["y"].notna().all() and (p["y"] >= 0).all()
    assert p.groupby(["target", "UBIGEO"]).size().eq(103).all()


def test_coincide_con_salida_del_notebook(resultado):
    ref = pd.read_csv(FIX / "panel_referencia.csv", dtype={"UBIGEO": str}, parse_dates=["fecha"])
    cols = ["fecha", "UBIGEO", "target", "y", "regime", "value_origin"]
    a = resultado.panel[cols].sort_values(cols[:3]).reset_index(drop=True)
    b = ref[cols].sort_values(cols[:3]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    assert (resultado.panel["value_origin"] != "observed").sum() == 340  # ceros reconstruidos (Notebook 01)


@pytest.mark.parametrize("target,desde,hasta,total", [
    ("ROBO", "2025-01-01", "2025-07-01", 16359), ("ROBO", "2026-01-01", "2026-07-01", 14569),
    ("HURTO", "2025-01-01", "2025-07-01", 45422), ("HURTO", "2026-01-01", "2026-07-01", 43903),
])
def test_totales_de_control_oficiales(resultado, target, desde, hasta, total):
    p = resultado.panel
    m = (p["target"] == target) & (p["fecha"] >= desde) & (p["fecha"] <= hasta)
    assert int(p.loc[m, "y"].sum()) == total


def test_regimen_por_fecha(resultado):
    p = resultado.panel
    assert (p.loc[p["fecha"] < "2024-11-01", "regime"] == "pre_break").all()
    assert (p.loc[p["fecha"] >= "2024-11-01", "regime"] == "post_break").all()


def test_sintetico_valido_es_integro_y_acepta_separador_y_codificacion():
    for kw in ({}, {"sep": ";"}, {"codificacion": "latin-1"}):
        r = P.verificar(P.leer_csv(csv_sintetico(**kw)), date(2019, 12, 1))
        assert r.estado == "integra", kw
        assert len(r.panel) == 43 * 24 * 2


@pytest.mark.parametrize("kw,control", [
    ({"sin_columna": "cantidad"}, "estructura"),
    ({"omitir_mes": "2018-06"}, "continuidad_mensual"),
    ({"con_cero": True}, "conteos_positivos"),
    ({"duplicar": True}, "claves_unicas"),
    ({"quitar_distrito": "150110"}, "distritos_completos"),
    ({"inicio": "2018-03"}, "inicio_serie"),
    ({"fin": "2019-11"}, "periodo_corte"),
])
def test_versiones_defectuosas_son_invalidas(kw, control):
    try:
        r = P.verificar(P.leer_csv(csv_sintetico(**kw)), date(2019, 12, 1))
    except P.SnapshotInvalido:
        assert control == "estructura"
        return
    assert r.estado == "invalida" and r.panel is None
    assert control in {c.control for c in r.controles if not c.aprobado}


def test_ubigeo_desconocido_deja_pendiente_y_la_equivalencia_lo_resuelve():
    df = P.leer_csv(csv_sintetico(extra_ubigeo="150199"))
    r = P.verificar(df, date(2019, 12, 1))
    assert r.estado == "con_pendientes" and r.pendientes == {"150199": 24} and r.panel is None
    r2 = P.verificar(df, date(2019, 12, 1), {"150199": "150110"})
    assert r2.estado == "integra"
    base = P.verificar(P.leer_csv(csv_sintetico()), date(2019, 12, 1)).panel
    suma = lambda p: int(p.loc[(p["UBIGEO"] == "150110") & (p["target"] == "ROBO"), "y"].sum())
    assert suma(r2.panel) == suma(base) + 3 * 24  # las filas del código resuelto se suman al distrito


@pytest.mark.parametrize("contenido", [b"", b"   \n", b"\x00\x01\x02 no es csv", "a,b\n1".encode()])
def test_basura_no_se_lee_pero_nunca_revienta(contenido):
    with pytest.raises(P.SnapshotInvalido):
        P.leer_csv(contenido)
