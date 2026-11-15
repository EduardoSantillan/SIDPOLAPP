import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Aviso, Cargando, Falla, SelectorDelito, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { mesTexto, num } from "../lib/formato";
import type { Delito, Tabla } from "../lib/tipos";

type Columna = "distrito" | "registradas" | "local" | "global";

/** Tabla de los 43 distritos: alfabética siempre que nadie pida otra cosa, y con las marcas para comparar unos pocos. */
export function Distritos() {
  const [params, setParams] = useSearchParams();
  const delito: Delito = params.get("delito") === "HURTO" ? "HURTO" : "ROBO";
  const [orden, setOrden] = useState<{ col: Columna; dir: 1 | -1 }>({ col: "distrito", dir: 1 });
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [soloMarcados, setSoloMarcados] = useState(false);
  const q = useQuery({ queryKey: ["tabla", delito], queryFn: () => api.get<Tabla>("/distritos/resumen", { target: delito }) });

  const filas = useMemo(() => {
    const t = (q.data?.filas ?? []).map((f) => ({
      ubigeo: f.ubigeo, distrito: f.distrito, registradas: f.registradas_ultimo_mes ?? null,
      local: f.error_promedio.find((e) => e.estrategia === "local")?.denuncias_por_mes ?? null,
      global: f.error_promedio.find((e) => e.estrategia === "global")?.denuncias_por_mes ?? null,
    }));
    const { col, dir } = orden;
    t.sort((a, b) => {
      if (col === "distrito") return a.distrito.localeCompare(b.distrito, "es") * dir;
      const x = a[col], y = b[col];
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">Orden alfabético por defecto. Toca el título de una columna para ordenar por ella. Un guion (—) significa que no hay dato para medirlo.</p>
          </div>
          <Aviso texto={q.data.aviso} />
        </>
      )}
    </>
  );
}
