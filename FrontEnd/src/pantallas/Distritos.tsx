import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Aviso, Cargando, Falla, SelectorDelito, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { mesTexto, num } from "../lib/formato";
import type { Delito, Tabla } from "../lib/tipos";

type Columna = string;  // "distrito", "registradas", "local", "global" o «AAAA-MM-DD|estrategia» (estimaciones de los meses sin dato)
type Fila = { ubigeo: string; distrito: string; registradas: number | null; local: number | null; global: number | null; sig: Record<string, number> };
const valorDe = (f: Fila, col: Columna): number | null => (col === "registradas" || col === "local" || col === "global" ? f[col] : f.sig[col] ?? null);

/** Tabla de los 43 distritos: alfabética siempre que nadie pida otra cosa, y con las marcas para comparar unos pocos. */
export function Distritos() {
  const [params, setParams] = useSearchParams();
  const delito: Delito = params.get("delito") === "HURTO" ? "HURTO" : "ROBO";
  const [orden, setOrden] = useState<{ col: Columna; dir: 1 | -1 }>({ col: "distrito", dir: 1 });
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [soloMarcados, setSoloMarcados] = useState(false);
  const q = useQuery({ queryKey: ["tabla", delito], queryFn: () => api.get<Tabla>("/distritos/resumen", { target: delito }) });

  const filas = useMemo(() => {
    const t: Fila[] = (q.data?.filas ?? []).map((f) => ({
      ubigeo: f.ubigeo, distrito: f.distrito, registradas: f.registradas_ultimo_mes ?? null,
      local: f.error_promedio.find((e) => e.estrategia === "local")?.denuncias_por_mes ?? null,
      global: f.error_promedio.find((e) => e.estrategia === "global")?.denuncias_por_mes ?? null,
      sig: Object.fromEntries((f.estimaciones_siguientes ?? []).map((e) => [`${e.fecha}|${e.estrategia}`, e.valor])),
    }));
    const { col, dir } = orden;
    t.sort((a, b) => {
      if (col === "distrito") return a.distrito.localeCompare(b.distrito, "es") * dir;
      const x = valorDe(a, col), y = valorDe(b, col);
      if (x == null && y == null) return 0;
      if (x == null) return 1; // lo que no se puede medir va siempre al final
      if (y == null) return -1;
      return (x - y) * dir;
    });
    return soloMarcados ? t.filter((f) => marcados.has(f.ubigeo)) : t;
  }, [q.data, orden, soloMarcados, marcados]);

  const marcar = (u: string, si: boolean) => {
    const n = new Set(marcados);
    if (si) n.add(u); else n.delete(u);
    setMarcados(n);
    if (n.size < 2) setSoloMarcados(false);
  };
  const th = (col: Columna, texto: string, numerica = false) => (
    <th className={numerica ? "n" : ""} aria-sort={orden.col === col ? (orden.dir > 0 ? "ascending" : "descending") : "none"}>
      <button onClick={() => setOrden({ col, dir: orden.col === col ? (-orden.dir as 1 | -1) : 1 })}>
        {texto}{orden.col === col ? (orden.dir > 0 ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  const mes = q.data ? mesTexto(q.data.ultimo_mes) : "";
  const sig = q.data?.meses_siguientes ?? [];  // meses que todavía no tienen denuncias registradas

  return (
    <>
      <Titulo texto="Todos los distritos" />
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Todos los distritos</h1>
          <p className="lead" style={{ marginBottom: 6 }}>Denuncias registradas en {mes || "el último mes"} y cuánto se equivocaron en promedio los modelos.</p>
        </div>
        <SelectorDelito valor={delito} alCambiar={(d) => { setParams({ delito: d }); setMarcados(new Set()); setSoloMarcados(false); }} />
      </div>
      {q.isPending ? <Cargando /> : q.error ? <Falla error={q.error} delito={delito} reintentar={() => q.refetch()} /> : (
        <>
          <div className="card">
            <div className="row" style={{ marginBottom: 10, justifyContent: "space-between" }}>
              <span className="note" role="status">
                {marcados.size ? `${marcados.size} marcado${marcados.size > 1 ? "s" : ""}` : "Marca dos o más distritos para compararlos"}
              </span>
              <span className="row">
                <button className="primary" disabled={marcados.size < 2} onClick={() => setSoloMarcados(!soloMarcados)}>
                  {soloMarcados ? "Volver a ver todos" : "Comparar los marcados"}
                </button>
                {marcados.size > 0 && <button onClick={() => { setMarcados(new Set()); setSoloMarcados(false); }}>Quitar marcas</button>}
              </span>
            </div>
            <div className="tabla-scroll">
              <table>
                <thead>
                  <tr>
                    <th><span className="sr">Marcar</span></th>
                    {th("distrito", "Distrito")}
                    {th("registradas", `Registradas en ${mes}`, true)}
                    {th("local", "Modelo por distrito: error promedio (denuncias/mes)", true)}
                    {th("global", "Modelo con todo Lima: error promedio (denuncias/mes)", true)}
                    {sig.flatMap((m) => [th(`${m}|local`, `Estimado para ${mesTexto(m)}: modelo por distrito`, true), th(`${m}|global`, `Estimado para ${mesTexto(m)}: modelo con todo Lima`, true)])}
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.ubigeo} className={marcados.has(f.ubigeo) ? "sel" : ""}>
                      <td><input type="checkbox" checked={marcados.has(f.ubigeo)} onChange={(e) => marcar(f.ubigeo, e.target.checked)} aria-label={`Marcar ${f.distrito}`} /></td>
                      <td><Link to={`/distrito/${f.ubigeo}?delito=${delito}`}>{f.distrito}</Link></td>
                      <td className="n">{f.registradas != null ? num(f.registradas) : "—"}</td>
                      <td className="n">{f.local != null ? num(f.local, 1) : "—"}</td>
                      <td className="n">{f.global != null ? num(f.global, 1) : "—"}</td>
                      {sig.flatMap((m) => [`${m}|local`, `${m}|global`].map((k) => <td key={k} className="n">{f.sig[k] != null ? num(f.sig[k]) : "—"}</td>))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sig.length > 0 && q.data.datos_hasta && (
              <p className="note">
                Las últimas columnas son estimaciones de denuncias registradas para {sig.map((m) => mesTexto(m)).join(" y ")}, hechas con datos hasta {mesTexto(q.data.datos_hasta)}.
                Todavía no hay denuncias registradas de esos meses, así que no se pueden comparar y no entran en el error promedio.
                {sig.length > 1 && <> {mesTexto(sig[1])} se apoya además en la estimación del mes anterior, por eso puede equivocarse más.</>}
              </p>
            )}
            <p className="note">Orden alfabético por defecto. Toca el título de una columna para ordenar por ella. Un guion (—) significa que no hay dato para medirlo.</p>
          </div>
          <Aviso texto={q.data.aviso} />
        </>
      )}
    </>
  );
}
