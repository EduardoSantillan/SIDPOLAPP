import { useQuery } from "@tanstack/react-query";
import { Aviso, Cargando, ErrorCaja, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Ficha as FichaTipo } from "../lib/tipos";

/** «Cómo se calculó»: la ficha en lenguaje llano, en una sola página. El detalle técnico y la configuración son del Analista y del Administrador. */
export function Ficha() {
  const { usuario } = useAuth();
  const q = useQuery({ queryKey: ["ficha"], queryFn: () => api.get<FichaTipo>("/ficha"), staleTime: 5 * 60_000 });
  const tecnico = usuario?.rol !== "usuario";
  const secciones = (q.data?.secciones ?? []).filter((s) => tecnico || s.id !== "detalle_tecnico");

  return (
    <>
      <Titulo texto="Cómo se calculó" />
      <h1>Cómo se calculó</h1>
      <p className="lead">Qué muestra la plataforma, qué no muestra y cómo leer los números.</p>
      {q.isPending ? <Cargando /> : q.error ? <ErrorCaja error={q.error} reintentar={() => q.refetch()} /> : (
        <>
          <div className="card ficha-una">
            {secciones.map((s) => (
              <section key={s.id} aria-labelledby={`ficha-${s.id}`}>
                <h2 id={`ficha-${s.id}`}>{s.titulo}</h2>
                <p>{s.texto}</p>
              </section>
            ))}
            {tecnico && (
              <p className="note">
                Configuración usada: {q.data.configuracion.nombre}, versión {q.data.configuracion.version}.
                {usuario?.rol === "analista" && <><br />Huella (SHA-256): <span className="mono">{q.data.configuracion.sha256}</span></>}
              </p>
            )}
          </div>
          <Aviso texto={q.data.aviso} />
        </>
      )}
    </>
  );
}
