import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Aviso, Cargando, ErrorCaja, Falla, SelectorDelito, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { PERIODOS, delitoTexto, mesTexto, num } from "../lib/formato";
import type { Comparacion, Delito, Periodo, Resumen, Trazabilidad } from "../lib/tipos";

const dif = (v: number | null | undefined) => (v == null ? "—" : num(v, 2));

/** Analista: Local contra Global y contra las referencias, con la diferencia numérica. No dice cuál es mejor. */
export function Comparar() {
  const [params, setParams] = useSearchParams();
  const delito: Delito = params.get("delito") === "HURTO" ? "HURTO" : "ROBO";
  const periodo = (PERIODOS.some(([v]) => v === params.get("periodo")) ? params.get("periodo") : "todo") as Periodo;
  const [conPropio, setConPropio] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["comparacion", delito, periodo], queryFn: () => api.get<Comparacion>("/comparacion", { target: delito, periodo }) });
  const cambiar = (c: Record<string, string>) => { setParams({ delito, periodo, ...c }); setAbierto(null); };
  const d = q.data;
  const col = (f: Comparacion["filas"][number], est: string, variante?: string) =>
    f.estrategias.find((e) => e.estrategia === est && (variante ? e.variante === variante : e.variante !== "E1b"));

  return (
    <>
      <Titulo texto="Comparar modelos" />
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Comparar modelos</h1>
          <p className="lead" style={{ marginBottom: 6 }}>Qué tan cerca estuvo cada modelo de lo registrado (ejecución más reciente de {delitoTexto(delito)}). La plataforma muestra la diferencia; la conclusión es de quien analiza.</p>
        </div>
        <div className="row">
          <select aria-label="Periodo" value={periodo} onChange={(e) => cambiar({ periodo: e.target.value })}>{PERIODOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
          <SelectorDelito valor={delito} alCambiar={(x) => cambiar({ delito: x })} />
        </div>
      </div>

      {q.isPending ? <Cargando /> : q.error ? <Falla error={q.error} delito={delito} reintentar={() => q.refetch()} /> : d && (
        <>
          <div className="card">
            <h2>Resumen entre distritos</h2>
            <div className="tabla-scroll">
              <table>
                <thead><tr><th>Modelo</th><th className="n">Distritos medidos</th><th className="n">Mediana de MASE</th><th className="n">Rango central (25 %–75 %)</th></tr></thead>
                <tbody>
                  {d.resumen.mase.filter((r) => conPropio || r.variante !== "E1b").map((r) => (
                    <tr key={`${r.estrategia}${r.variante}`}>
                      <td>{r.etiqueta}</td><td className="n">{r.distritos}</td><td className="n">{r.mediana_mase != null ? num(r.mediana_mase, 2) : "—"}</td>
                      <td className="n">{r.iqr_mase[0] != null ? `${num(r.iqr_mase[0], 2)} – ${num(r.iqr_mase[1] ?? 0, 2)}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ margin: "12px 0 4px" }}>
              Mediana de la diferencia entre distritos: <b>{dif(d.resumen.mediana_diferencia_global_menos_local.E1?.mediana)}</b>
              {conPropio && <> · con el ajuste propio: <b>{dif(d.resumen.mediana_diferencia_global_menos_local.E1b?.mediana)}</b></>}
            </p>
            <p className="note">{d.resumen.explicacion_diferencia}</p>
            <p className="note">{d.mase_explicacion} Se resume con la mediana porque unos pocos distritos muy chicos distorsionan el promedio.</p>
            <label className="row" style={{ gap: 8, marginTop: 8 }}>
              <input type="checkbox" checked={conPropio} onChange={(e) => setConPropio(e.target.checked)} />
              <span className="note">Mostrar también el modelo con todo Lima con sus propios ajustes (prueba de sensibilidad)</span>
            </label>
          </div>

          <div className={`cols ${abierto ? "dos" : "sola"}`}>
            <div className="card">
              <h2>Por distrito</h2>
              <div className="tabla-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Distrito</th><th className="n">Modelo por distrito</th><th className="n">Modelo con todo Lima</th>
                      <th className="n">Repetir el mes anterior</th><th className="n">Repetir el mismo mes del año pasado</th>
                      <th className="n">Diferencia (con todo Lima − por distrito)</th>
                      {conPropio && <><th className="n">Con todo Lima, ajuste propio</th><th className="n">Diferencia con ajuste propio</th></>}
                    </tr>
                  </thead>
                  <tbody>
                    {d.filas.map((f) => (
                      <tr key={f.ubigeo} className={abierto === f.ubigeo ? "sel" : ""}>
                        <td><button className="enlace" onClick={() => setAbierto(f.ubigeo)} aria-label={`Ver de dónde sale un valor de ${f.distrito}`}>{f.distrito}</button></td>
                        {["local", "global", "naive1", "naive_estacional"].map((e) => <td key={e} className="n">{dif(col(f, e)?.mase)}</td>)}
                        <td className="n">{dif(f.diferencia_mase_global_menos_local)}</td>
                        {conPropio && <><td className="n">{dif(col(f, "global", "E1b")?.mase)}</td><td className="n">{dif(f.diferencia_mase_global_e1b_menos_local)}</td></>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="note">Valores en MASE (menos es mejor). La diferencia es MASE del modelo con todo Lima menos MASE del modelo por distrito: si es negativa, el modelo con todo Lima se equivocó menos. Un guion (—) significa que el distrito casi no registra denuncias y la medida no se puede calcular. Toca el nombre de un distrito para ver de dónde sale un valor.</p>
            </div>
            {abierto && <Origen ubigeo={abierto} delito={delito} nombre={d.filas.find((f) => f.ubigeo === abierto)?.distrito ?? ""} alCerrar={() => setAbierto(null)} />}
          </div>
          <Aviso texto={d.aviso} />
        </>
      )}
    </>
  );
}

const MODELOS: [string, string, string][] = [
  ["local", "E1", "Modelo por distrito"], ["global", "E1", "Modelo con todo Lima"], ["naive1", "base", "Repetir el mes anterior"],
  ["naive_estacional", "base", "Repetir el mismo mes del año pasado"], ["global", "E1b", "Modelo con todo Lima, ajuste propio"],
];

/** Panel lateral: de dónde sale un valor (RF-18). Cada dato con la versión de datos y la configuración que lo produjeron. */
function Origen({ ubigeo, delito, nombre, alCerrar }: { ubigeo: string; delito: Delito; nombre: string; alCerrar: () => void }) {
  const [modelo, setModelo] = useState("local|E1");
  const [mes, setMes] = useState<string | null>(null);
  const resumen = useQuery({ queryKey: ["resumen", ubigeo, delito], queryFn: () => api.get<Resumen>(`/distritos/${ubigeo}/resumen`, { target: delito }) });
  const ultimo = resumen.data?.ultimo_mes.slice(0, 7);
  const elegido = mes ?? ultimo;
  const [estrategia, variante] = modelo.split("|");
  const t = useQuery({
    queryKey: ["traza", ubigeo, delito, elegido, modelo], enabled: !!elegido,
    queryFn: () => api.get<Trazabilidad>("/trazabilidad", { target: delito, ubigeo, estrategia, variante, fecha_objetivo: `${elegido}-01` }),
  });

  return (
    <div className="card sidepanel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>De dónde sale un valor</h2>
        <button onClick={alCerrar} aria-label="Cerrar">Cerrar</button>
      </div>
      <p className="note">{nombre} · {delitoTexto(delito)}</p>
      <label className="f"><span>Modelo</span>
        <select value={modelo} onChange={(e) => setModelo(e.target.value)}>{MODELOS.map(([e, v, n]) => <option key={`${e}|${v}`} value={`${e}|${v}`}>{n}</option>)}</select>
      </label>
      {ultimo && (
        <label className="f"><span>Mes estimado</span>
          <input type="month" min="2023-01" max={ultimo} value={elegido} onChange={(e) => e.target.value && setMes(e.target.value)} />
        </label>
      )}
      {resumen.isPending || (t.isPending && !!elegido) ? <Cargando /> : resumen.error ? <ErrorCaja error={resumen.error} /> : t.error ? <ErrorCaja error={t.error} /> : t.data && (
        <dl className="datos" aria-live="polite">
          <dt>Mes estimado</dt><dd>{mesTexto(t.data.fecha_objetivo)} (se estimó con lo registrado hasta {mesTexto(t.data.fecha_origen)})</dd>
          <dt>Estimado</dt><dd>{num(t.data.estimado, 1)} denuncias</dd>
          <dt>Registrado</dt><dd>{t.data.observado != null ? `${num(t.data.observado)} denuncias` : "Ese mes todavía no tiene datos"}</dd>
          <dt>Datos usados</dt><dd>{t.data.version_datos.nombre} · corte {t.data.version_datos.corte}</dd>
          <dt>Huella de los datos (SHA-256)</dt><dd className="mono">{t.data.version_datos.sha256}</dd>
          <dt>Configuración</dt><dd>{t.data.configuracion.nombre} · {t.data.configuracion.version}</dd>
          <dt>Huella de la configuración (SHA-256)</dt><dd className="mono">{t.data.configuracion.sha256}</dd>
          <dt>Ejecución</dt><dd className="mono">{t.data.ejecucion_id}</dd>
        </dl>
      )}
    </div>
  );
}
