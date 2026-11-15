"""Exportación a CSV y PDF (RF-24) con el aviso de alcance y la metadata de trazabilidad (RF-25, RNF-07, RNF-08).
Las dos salidas se arman con lo ya guardado: no recalculan nada."""
import csv
import io
from datetime import datetime, timezone

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from api_plataforma.servicios import resultados as R
from common.aviso import AVISO

DELITO = {"ROBO": "robo", "HURTO": "hurto"}
PERIODO_TEXTO = {"todo": "Todos los meses evaluados", "antes_nov_2024": "Antes de nov 2024", "desde_nov_2024": "Desde nov 2024"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def mes_texto(f) -> str:
    return f"{MESES[f.month - 1]} {f.year}"


def metadata(ej, target: str, nombre_distrito: str | None, periodo: str) -> list[tuple[str, str]]:
    """Pares (etiqueta, valor) que acompañan toda exportación; el primero es siempre el aviso."""
    return [
        ("Aviso", AVISO),
        ("Delito", DELITO[target]),
        ("Distrito", nombre_distrito or "Todos los distritos"),
        ("Periodo", PERIODO_TEXTO[periodo]),
        ("Estrategias", "; ".join(R.ETIQUETAS.values())),
        ("Versión de datos", f"{ej['nombre_archivo']} (corte {ej['periodo_corte']:%Y-%m})"),
        ("SHA-256 de los datos", ej["sha_datos"]),
        ("Ejecución", str(ej["ejecucion_id"])),
        ("Configuración", f"{ej['cfg_nombre']} {ej['cfg_version']}"),
        ("SHA-256 de la configuración", ej["cfg_sha"]),
        ("Exportado", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]


def csv_bytes(meta: list[tuple[str, str]], filas: list[dict]) -> bytes:
    """Líneas de metadata (empiezan con «#») y luego la tabla: una fila por distrito, mes y estrategia."""
    b = io.StringIO()
    w = csv.writer(b, lineterminator="\r\n")
    for k, v in meta:
        w.writerow([f"# {k}: {v}"])
    w.writerow(["distrito", "ubigeo", "mes", "periodo", "denuncias_registradas", "estrategia", "estimado", "diferencia_estimado_menos_registrado"])
    for f in filas:
        w.writerow([f["distrito"], f["ubigeo"], f"{f['fecha']:%Y-%m}", R.REGIMEN_API[f["regimen"]], f["observado"],
                    R.ETIQUETAS[f["estrategia"]], f"{f['estimado']:.2f}", f"{f['estimado'] - f['observado']:.2f}"])
    return b.getvalue().encode("utf-8-sig")  # con marca BOM para que Excel respete las tildes


def _grafico(filas: list[dict]) -> Drawing:
    d = Drawing(16.5 * cm, 6.5 * cm)
    meses = sorted({f["fecha"] for f in filas})
    idx = {m: i for i, m in enumerate(meses)}
    series = {"registradas": {}, "local": {}, "global": {}}
    for f in filas:
        series["registradas"][f["fecha"]] = f["observado"]
        if f["estrategia"] in ("local", "global"):
            series[f["estrategia"]][f["fecha"]] = f["estimado"]
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 1.4 * cm, 1.0 * cm, 14.6 * cm, 4.6 * cm
    lp.data = [[(idx[m], v) for m, v in sorted(s.items())] for s in series.values()]
    for linea, col in zip(lp.lines, (colors.HexColor("#1a1a1a"), colors.HexColor("#1d6fb8"), colors.HexColor("#c2570c"))):
        linea.strokeColor, linea.strokeWidth = col, 1.4
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, max(len(meses) - 1, 1)
    lp.xValueAxis.valueSteps = list(range(0, len(meses), max(len(meses) // 6, 1)))
    lp.xValueAxis.labelTextFormat = lambda i: mes_texto(meses[int(i)]) if 0 <= int(i) < len(meses) else ""
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 7
    d.add(lp)
    d.add(String(1.4 * cm, 6.0 * cm, "Registradas (negro) · Modelo por distrito (azul) · Modelo con todo Lima (naranja)", fontSize=7.5))
    return d


def _estilo_tabla() -> TableStyle:
    return TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c1cc")),
                       ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])


def _pie(canvas, doc):
    """El aviso de alcance va también al pie de cada página."""
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(2 * cm, 1.1 * cm, "Denuncias registradas en SIDPOL; no es la criminalidad real ni una recomendación operativa.")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _coma(x, d: int = 1) -> str:
    return "—" if x is None else f"{x:.{d}f}".replace(".", ",")


def pdf_bytes(meta, target: str, nombre_distrito: str | None, periodo: str, filas: list[dict], errores: list) -> bytes:
    """`errores`: con un distrito, la lista de `error_promedio` (etiqueta, denuncias_por_mes, mase); para todos, filas ya armadas."""
    est = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=est["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    chico = ParagraphStyle("c", parent=normal, fontSize=7.5, leading=9.5)
    aviso = ParagraphStyle("a", parent=normal, backColor=colors.HexColor("#fff4d6"), borderPadding=6, fontSize=9)

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;")

    b = io.BytesIO()
    doc = SimpleDocTemplate(b, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Denuncias registradas de {DELITO[target]}", author="SIDPOL")
    ultimo = max(f["fecha"] for f in filas)
    el = [Paragraph(f"Denuncias registradas de {DELITO[target]}: {esc(nombre_distrito or 'todos los distritos')}", est["Title"]),
          Paragraph(esc(PERIODO_TEXTO[periodo]), normal), Spacer(1, 6), Paragraph(esc(AVISO), aviso), Spacer(1, 12)]
    if nombre_distrito:
        u = [f for f in filas if f["fecha"] == ultimo]
        e = {f["estrategia"]: f["estimado"] for f in u}
        el.append(Paragraph(f"En {esc(nombre_distrito)} se registraron <b>{u[0]['observado']}</b> denuncias de {DELITO[target]} en {mes_texto(ultimo)}; "
                            f"el modelo por distrito estimaba {round(e['local'])} y el modelo con todo Lima, {round(e['global'])}.", normal))
        el += [Spacer(1, 8), _grafico(filas), Spacer(1, 8), Paragraph("Cuánto se equivocó cada forma de estimar en los meses evaluados", est["Heading3"])]
        tabla = [["Forma de estimar", "Error promedio (denuncias por mes)", "MASE"]] + [
            [x["etiqueta"], _coma(x["denuncias_por_mes"]), "No calculable" if x["mase"] is None else _coma(x["mase"], 2)] for x in errores]
        el += [Table(tabla, colWidths=[8 * cm, 5.5 * cm, 3.5 * cm], style=_estilo_tabla()), Spacer(1, 4), Paragraph(esc(R.MASE_EXPLICACION), chico)]
    else:
        el.append(Paragraph(f"Último mes evaluado: {mes_texto(ultimo)}. Error promedio en denuncias por mes (menos es mejor).", normal))
        tabla = [["Distrito", f"Registradas {mes_texto(ultimo)}", "Por distrito", "Con todo Lima", "Mes anterior", "Mismo mes año pasado"]] + errores
        el += [Spacer(1, 6), Table(tabla, repeatRows=1, style=_estilo_tabla(), colWidths=[4.6 * cm, 2.6 * cm, 2.3 * cm, 2.5 * cm, 2.4 * cm, 2.6 * cm])]
    el += [Spacer(1, 14), Paragraph("Datos de esta exportación", est["Heading4"])]
    el += [Paragraph(f"<b>{esc(k)}:</b> {esc(v)}", chico) for k, v in meta[1:]]
    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return b.getvalue()
