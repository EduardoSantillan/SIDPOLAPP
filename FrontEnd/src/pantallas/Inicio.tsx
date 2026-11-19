import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Aviso, Cargando, ErrorCaja, SelectorDelito, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { AVISO_BASE, sinTildes } from "../lib/formato";
import type { Delito, Distrito } from "../lib/tipos";

export function usarDistritos() {
  return useQuery({ queryKey: ["distritos"], queryFn: () => api.get<Distrito[]>("/distritos"), staleTime: Infinity });
}

/** Una sola pregunta: ¿de qué distrito quieres saber? */
export function Inicio() {
  const [params, setParams] = useSearchParams();
  const delito: Delito = params.get("delito") === "HURTO" ? "HURTO" : "ROBO";
  const [texto, setTexto] = useState("");
  const ir = useNavigate();
  const { data, isPending, error, refetch } = usarDistritos();

  const coincidencias = texto.trim() ? (data ?? []).filter((d) => sinTildes(d.nombre).includes(sinTildes(texto.trim()))).slice(0, 8) : [];
  const abrir = (d: Distrito) => ir(`/distrito/${d.ubigeo}?delito=${delito}`);

  return (
    <section className="hero">
      <Titulo texto="Inicio" />
      <h1>¿De qué distrito quieres saber?</h1>
      <p className="lead">Mira cuántas denuncias se registraron y qué tanto se parecen a lo que estimaban los modelos.</p>
      <p className="note" style={{ marginBottom: 10 }}>Primero, ¿qué tipo de denuncia?</p>
      <SelectorDelito valor={delito} alCambiar={(d) => setParams({ delito: d })} />
      {error ? <ErrorCaja error={error} reintentar={() => refetch()} /> : isPending ? <Cargando /> : (
        <div className="pick">
          <input type="text" aria-label="Distrito" autoFocus autoComplete="off" placeholder="Escribe el nombre del distrito, por ejemplo Surco"
                 value={texto} onChange={(e) => setTexto(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && coincidencias[0]) abrir(coincidencias[0]); }} />
          {coincidencias.length > 0 && (
            <div className="sug" role="listbox" aria-label="Distritos que coinciden">
              {coincidencias.map((d) => <button key={d.ubigeo} role="option" aria-selected={false} onClick={() => abrir(d)}>{d.nombre}</button>)}
            </div>
          )}
          {texto.trim() && coincidencias.length === 0 && <p className="note" role="status">No encontramos ese distrito. Revisa cómo está escrito.</p>}
        </div>
      )}
      <p style={{ marginTop: 22 }}><Link to={`/distritos?delito=${delito}`}>Prefiero ver todos los distritos juntos</Link></p>
      <div style={{ maxWidth: 560, margin: "28px auto 0", textAlign: "left" }}><Aviso texto={AVISO_BASE} /></div>
    </section>
  );
}
