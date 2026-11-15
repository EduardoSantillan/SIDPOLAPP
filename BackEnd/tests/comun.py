"""Constantes compartidas por las pruebas."""
import json
from pathlib import Path

from common.registrar_config import RUTA

FIX = Path(__file__).parent / "fixtures"
CFG = json.loads(RUTA.read_text(encoding="utf-8"))
# Solo las referencias: las pruebas rápidas no entrenan XGBoost (el entrenamiento se prueba aparte).
CFG_NAIVE = {**CFG, "estrategias": [e for e in CFG["estrategias"] if not e["entrena"]]}
