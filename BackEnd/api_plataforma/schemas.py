"""Modelos de respuesta de la API pública. El front genera sus tipos desde /openapi.json (openapi-typescript).
Ningún modelo tiene campos de riesgo, prioridad, ranking ni «mejor»: lo que no está aquí no sale por la API."""
from typing import Any, Literal

from pydantic import BaseModel

Rol = Literal["usuario", "analista", "administrador"]
EstadoCuenta = Literal["pendiente_activacion", "activo", "inactivo"]
EstadoVersion = Literal["registrada", "integra", "con_pendientes", "invalida"]
EstadoEjecucion = Literal["en_curso", "completada", "fallida"]
Target = Literal["ROBO", "HURTO"]
Periodo = Literal["todo", "antes_nov_2024", "desde_nov_2024"]
Estrategia = Literal["local", "global", "naive1", "naive_estacional"]


class ErrorOut(BaseModel):
    codigo: str
    mensaje: str
    detalle: Any = None


# ---------- auth y usuarios ----------
class LoginOut(BaseModel):
    token: str
    rol: Rol
    nombre: str


class YoOut(BaseModel):
    nombre: str
    correo: str
    rol: Rol


class EstadoOut(BaseModel):
    estado: str


class UsuarioOut(BaseModel):
    id: str
    nombre: str
    correo: str
    rol: Rol
    estado: EstadoCuenta


class UsuariosOut(BaseModel):
    items: list[UsuarioOut]


class EnlaceOut(BaseModel):
    enlace_activacion: str
    vence: str


class UsuarioCreadoOut(EnlaceOut):
    id: str
    estado: EstadoCuenta


# ---------- versiones ----------
class ControlOut(BaseModel):
    control: str
    aprobado: bool
    detalle: Any = None


class VersionResumenOut(BaseModel):
    id: str
    nombre_archivo: str
    periodo_corte: str
    version: str
    estado: EstadoVersion
    registrada_en: str


class VersionDetalleOut(VersionResumenOut):
    sha256: str
    registrada_por: str
    controles: list[ControlOut]
    pendientes_abiertos: int
    pendientes_total: int


class VersionesOut(BaseModel):
    items: list[VersionResumenOut]


class PendienteOut(BaseModel):
    id: str
    codigo: str
    filas: int
    estado: Literal["abierto", "resuelto"]
    ubigeo: str | None = None
    resuelta_en: str | None = None


class PendientesOut(BaseModel):
    items: list[PendienteOut]


class ResueltaOut(BaseModel):
    resuelta: bool
    pendientes_abiertos: int
    siguiente_paso: str | None = None


# ---------- ejecuciones ----------
class VersionCortaOut(BaseModel):
    nombre: str
    version: str
    corte: str


class ConfiguracionOut(BaseModel):
    nombre: str
    version: str
    sha256: str


class EjecucionOut(BaseModel):
    ejecucion_id: str
    target: Target
    estado: EstadoEjecucion
    version: VersionCortaOut
    inicio: str
    fin: str | None = None
    motivo: str | None = None  # solo en el detalle, si falló
    configuracion: ConfiguracionOut | None = None  # solo en el detalle


class EjecucionesOut(BaseModel):
    items: list[EjecucionOut]


class EjecucionIniciadaOut(BaseModel):
    ejecucion_id: str
    estado: EstadoEjecucion


# ---------- consulta ----------
class DistritoOut(BaseModel):
    ubigeo: str
    nombre: str


class EstimacionOut(BaseModel):
    estrategia: Estrategia
    etiqueta: str
    valor: int
    diferencia: int


class ErrorEstrategiaOut(BaseModel):
    estrategia: Estrategia
    etiqueta: str
    denuncias_por_mes: float | None = None
    mase: float | None = None
    motivo: str | None = None


class RangoOut(BaseModel):
    min: int | None = None
    max: int | None = None
    meses: int


class ResumenDistritoOut(BaseModel):
    ubigeo: str
    distrito: str
    target: Target
    periodo: Periodo
    ultimo_mes: str
    registradas_ultimo_mes: int
    estimaciones_ultimo_mes: list[EstimacionOut]
    error_promedio: list[ErrorEstrategiaOut]
    mase_explicacion: str
    meses_evaluados: int
    rango_habitual: RangoOut
    ejecucion_id: str
    aviso: str


class CambioRegistroOut(BaseModel):
    fecha: str
    texto: str


class PuntoSerieOut(BaseModel):
    fecha: str
    registradas: int
    regimen: Literal["antes_nov_2024", "desde_nov_2024"]
    estimaciones: dict[str, int]


class EtiquetaEstrategiaOut(BaseModel):
    estrategia: Estrategia
    etiqueta: str


class SerieOut(BaseModel):
    ubigeo: str
    target: Target
    periodo: Periodo
    cambio_registro: CambioRegistroOut
    puntos: list[PuntoSerieOut]
    estrategias: list[EtiquetaEstrategiaOut]
    ejecucion_id: str
    aviso: str


class FilaTablaOut(BaseModel):
    ubigeo: str
    distrito: str
    registradas_ultimo_mes: int | None = None
    error_promedio: list[ErrorEstrategiaOut]


class TablaOut(BaseModel):
    target: Target
    periodo: Periodo
    ultimo_mes: str
    mase_explicacion: str
    filas: list[FilaTablaOut]
    ejecucion_id: str
    aviso: str


class FichaSeccionOut(BaseModel):
    id: str
    titulo: str
    texto: str


class FichaOut(BaseModel):
    secciones: list[FichaSeccionOut]
    version_ficha: str
    configuracion: ConfiguracionOut
    aviso: str


# ---------- análisis (Analista) ----------
class MetricasEstrategiaOut(BaseModel):
    estrategia: Estrategia
    variante: str
    etiqueta: str
    mase: float | None = None
    motivo: str | None = None
    mae: float | None = None
    rmse: float | None = None


class FilaComparacionOut(BaseModel):
    ubigeo: str
    distrito: str
    estrategias: list[MetricasEstrategiaOut]
    diferencia_mase_global_menos_local: float | None = None
    diferencia_mase_global_e1b_menos_local: float | None = None


class ResumenMaseOut(BaseModel):
    estrategia: Estrategia
    variante: str
    etiqueta: str
    distritos: int
    mediana_mase: float | None = None
    iqr_mase: list[float | None]


class MedianaDiferenciaOut(BaseModel):
    distritos: int
    mediana: float | None = None


class ResumenComparacionOut(BaseModel):
    mase: list[ResumenMaseOut]
    mediana_diferencia_global_menos_local: dict[str, MedianaDiferenciaOut]
    explicacion_diferencia: str


class VersionDatosOut(BaseModel):
    nombre: str
    corte: str
    sha256: str


class OrigenOut(BaseModel):
    ejecucion_id: str
    version_datos: VersionDatosOut
    configuracion: ConfiguracionOut


class ComparacionOut(BaseModel):
    target: Target
    periodo: Periodo
    filas: list[FilaComparacionOut]
    resumen: ResumenComparacionOut
    mase_explicacion: str
    origen: OrigenOut
    aviso: str


class TrazabilidadOut(BaseModel):
    ejecucion_id: str
    target: Target
    ubigeo: str
    estrategia: Estrategia
    variante: str
    fecha_origen: str
    fecha_objetivo: str
    observado: int | None = None
    estimado: float
    version_datos: VersionDatosOut
    configuracion: ConfiguracionOut
    aviso: str
