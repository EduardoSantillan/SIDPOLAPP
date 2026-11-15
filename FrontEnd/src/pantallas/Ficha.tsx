import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Aviso, Cargando, ErrorCaja, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Ficha as FichaTipo } from "../lib/tipos";

/** «Cómo se calculó»: la ficha en lenguaje llano, con secciones que se recorren de una en una. */
export function Ficha() {
  const { usuario } = useAuth();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ["ficha"], queryFn: () => api.get<FichaTipo>("/ficha"), staleTime: 5 * 60_000 });
  const secciones = q.data?.secciones ?? [];
  const k = Math.max(0, secciones.findIndex((s) => s.id === params.get("seccion")));
  const ir = (i: number) => setParams({ seccion: secciones[i].id });
  const s = secciones[k];

  return (
    <>
      <Titulo texto="Cómo se calculó" />
      <h1>Cómo se calculó</h1>
      <p className="lead">Explicado sin términos técnicos.</p>
      {q.isPending ? <Cargando /> : q.error ? <ErrorCaja error={q.error} reintentar={() => q.refetch()} /> : s && (
        <>
          <div className="ficha">
            <nav aria-label="Secciones de la ficha">
              {secciones.map((x, i) => (
                <Link key={x.id} to={`?seccion=${x.id}`} aria-current={i === k ? "page" : undefined}>{x.titulo}</Link>
              ))}
            </nav>
            <div className="card">
              <h2>{s.titulo}</h2>
              <p>{s.texto}</p>
              {k === secciones.length - 1 && (
                <p className="note">
                  Configuración usada: {q.data.configuracion.nombre}, versión {q.data.configuracion.version}.
                  {usuario?.rol === "analista" && <><br />Huella (SHA-256): <span className="mono">{q.data.configuracion.sha256}</span></>}
                </p>
              )}
              <div className="row" style={{ justifyContent: "space-between" }}>
                {k > 0 ? <button onClick={() => ir(k - 1)}>Anterior</button> : <span />}
                {k < secciones.length - 1 ? <button onClick={() => ir(k + 1)}>Siguiente</button> : <span />}
              </div>
            </div>
          </div>
          <Aviso texto={q.data.aviso} />
        </>
      )}
    </>
  );
}
