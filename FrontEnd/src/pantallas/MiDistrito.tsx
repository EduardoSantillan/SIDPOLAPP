import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Grafico } from "../components/Grafico";
import { Alerta, Aviso, Cargando, ErrorCaja, Falla, SelectorDelito, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { PERIODOS, comparado, delitoTexto, mesTexto, num, restarMeses } from "../lib/formato";
import type { Delito, Periodo, Resumen, Serie } from "../lib/tipos";

const ESTILO_ESTIMACION: Record<string, string> = { local: "est", global: "est b" };

/** Pregunta: ¿cuántas denuncias hay y qué tanto se parecía lo estimado? La respuesta va primero, en una frase. */
export function MiDistrito() {
  const { ubigeo = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const delito: Delito = params.get("delito") === "HURTO" ? "HURTO" : "ROBO";
  const periodo = (PERIODOS.some(([v]) => v === params.get("periodo")) ? params.get("periodo") : "todo") as Periodo;
  const cambiar = (c: Record<string, string>) => setParams({ delito, periodo, ...c });

  const resumen = useQuery({ queryKey: ["resumen", ubigeo, delito], queryFn: () => api.get<Resumen>(`/distritos/${ubigeo}/resumen`, { target: delito }) });
  const serie = useQuery({ queryKey: ["serie", ubigeo, delito, periodo], queryFn: () => api.get<Serie>(`/distritos/${ubigeo}/serie`, { target: delito, periodo }) });
  const r = resumen.data;
  // La evaluación empezó con el primer mes que tiene resultado; el filtro de periodo solo cambia el tramo que se muestra.
  const inicio = r ? restarMeses(r.ultimo_mes, r.meses_evaluados - 1) : "";

  return (
    <>
      <Titulo texto={r?.distrito ?? "Distrito"} />
      <p className="note"><Link to={`/?delito=${delito}`}>← Elegir otro distrito</Link></p>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>{r?.distrito ?? "…"}</h1>
        <SelectorDelito valor={delito} alCambiar={(d) => cambiar({ delito: d })} />
      </div>

      {resumen.isPending ? <Cargando /> : resumen.error ? <Falla error={resumen.error} delito={delito} reintentar={() => resumen.refetch()} /> : r && (
        <>
          <Respuesta r={r} delito={delito} />
          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
              <h2 style={{ margin: 0 }}>Mes a mes</h2>
              <label className="row" style={{ gap: 8 }}>
                <span className="note">Periodo</span>
                <select aria-label="Periodo" value={periodo} onChange={(e) => cambiar({ periodo: e.target.value })}>
                  {PERIODOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </label>
            </div>
            <p className="note" style={{ margin: "0 0 10px" }}>
              El periodo seleccionado se aplica al histórico y a las descargas. El resumen de arriba usa siempre los {r.meses_evaluados} meses
              evaluados, de {mesTexto(inicio)} a {mesTexto(r.ultimo_mes)}.
            </p>
            {serie.isPending ? <Cargando /> : serie.error ? <ErrorCaja error={serie.error} reintentar={() => serie.refetch()} /> : (
              <>
                <Grafico serie={serie.data} distrito={r.distrito} />
                <p className="note" style={{ marginTop: 12 }}>
                  La zona sombreada marca desde noviembre de 2024, cuando cambió la forma de registrar las denuncias.
                  {" "}Las líneas punteadas (lo que estimaban los modelos) existen desde {mesTexto(inicio)}, cuando empezó la evaluación
                  {periodo === "todo" ? "." : "; este periodo solo muestra un tramo de ella."}
                </p>
              </>
            )}
          </div>
          <Aviso texto={r.aviso} />
          <Acciones ubigeo={ubigeo} delito={delito} periodo={periodo} />
        </>
      )}
    </>
  );
}

function Respuesta({ r, delito }: { r: Resumen; delito: Delito }) {
  const err = Object.fromEntries(r.error_promedio.map((e) => [e.estrategia, e]));
  const local = err.local, global = err.global;
  const sinMase = local?.mase == null && global?.mase == null;
  return (
    <div className="card">
      <p className="answer">En {r.distrito} se registraron <b>{num(r.registradas_ultimo_mes)} denuncias de {delitoTexto(delito)}</b> en {mesTexto(r.ultimo_mes)}.</p>
      <p className="note" style={{ margin: "-6px 0 12px" }}>Para ese mes, los modelos habían estimado:</p>
      <div className="grid2">
        {r.estimaciones_ultimo_mes.filter((e) => e.estrategia === "local" || e.estrategia === "global").map((e) => (
          <div key={e.estrategia} className={ESTILO_ESTIMACION[e.estrategia]}>
            <div className="t">{e.etiqueta}</div><div className="n">{num(e.valor)}</div><div className="t">{comparado(e.diferencia)}</div>
          </div>
        ))}
      </div>
      {local?.denuncias_por_mes != null && global?.denuncias_por_mes != null && (
        <p style={{ margin: "16px 0 0" }}>
          <b>¿Qué tan cerca suelen estar?</b> En los últimos {r.meses_evaluados} meses, el modelo por distrito se equivocó en promedio por <b>{num(local.denuncias_por_mes, 1)} denuncias al mes</b> y
          el modelo con todo Lima por <b>{num(global.denuncias_por_mes, 1)}</b>.
          {r.rango_habitual.min != null && <> En este distrito, durante el último año, se registraron entre {num(r.rango_habitual.min)} y {num(r.rango_habitual.max ?? 0)} denuncias al mes.</>}
        </p>
      )}
      {sinMase && <Alerta tipo="warn">Este distrito registra muy pocas denuncias al mes, así que el MASE no se puede calcular. El error en denuncias sí es válido.</Alerta>}
      <table style={{ marginTop: 12 }}>
        <thead><tr><th>Forma de estimar</th><th className="n">Error promedio (denuncias al mes)</th><th className="n">MASE (menos es mejor)</th></tr></thead>
        <tbody>
          {r.error_promedio.map((e) => (
            <tr key={e.estrategia} style={e.estrategia.startsWith("naive") ? { color: "var(--ink2)" } : undefined}>
              <td>{e.etiqueta}{e.estrategia.startsWith("naive") && <span className="note"> · regla simple para comparar</span>}</td>
              <td className="n">{e.denuncias_por_mes != null ? num(e.denuncias_por_mes, 1) : "—"}</td>
              <td className="n">{e.mase != null ? num(e.mase, 2) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note" style={{ margin: "8px 0 0" }}>{r.mase_explicacion}</p>
    </div>
  );
}

function Acciones({ ubigeo, delito, periodo }: { ubigeo: string; delito: Delito; periodo: Periodo }) {
  const [estado, setEstado] = useState<"csv" | "pdf" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const bajar = async (formato: "csv" | "pdf") => {
    setEstado(formato); setError(null);
    try { await api.descargar("/exportaciones", { formato, target: delito, ubigeo, periodo }); } catch (e) { setError(e); } finally { setEstado(null); }
  };
  return (
    <>
      <div className="row">
        <button onClick={() => bajar("pdf")} disabled={estado !== null}>{estado === "pdf" ? "Preparando…" : "Descargar PDF"}</button>
        <button onClick={() => bajar("csv")} disabled={estado !== null}>{estado === "csv" ? "Preparando…" : "Descargar CSV (Excel)"}</button>
        <Link className="btn" to="/ficha">Cómo se calculó</Link>
      </div>
      {error != null && <ErrorCaja error={error} />}
    </>
  );
}
