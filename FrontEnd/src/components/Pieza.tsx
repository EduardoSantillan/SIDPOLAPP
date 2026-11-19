import { useEffect, type ReactNode } from "react";
import { ApiError } from "../lib/api";
import { AVISO_BASE, delitoTexto, delitoTitulo } from "../lib/formato";
import type { Delito } from "../lib/tipos";

/** Banda con el aviso de alcance. El texto lo entrega la API, para que sea el mismo en todas partes (RF-25). */
export function Aviso({ texto }: { texto: string }) {
  return <div className="banner" role="note">{texto}</div>;
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return <p role="status" className="muted"><span className="spin" aria-hidden="true" />{texto}</p>;
}

/** Error de la API con su mensaje en español. No muestra códigos ni detalles técnicos. */
export function ErrorCaja({ error, reintentar }: { error: unknown; reintentar?: () => void }) {
  const mensaje = error instanceof ApiError ? error.message : "Algo salió mal. Vuelve a intentarlo.";
  return (
    <div className="alert err" role="alert">
      {mensaje}{" "}
      {reintentar && <button onClick={reintentar} style={{ marginLeft: 8 }}>Intentar de nuevo</button>}
    </div>
  );
}

/** Cuando todavía no hay resultados se dice tal cual: nada de datos inventados. */
export function SinResultados({ delito }: { delito: Delito }) {
  return (
    <>
      <div className="card vacio">
        <h2>Todavía no hay resultados de {delitoTexto(delito)}</h2>
        <p>Aparecerán aquí cuando el equipo de análisis termine de calcularlos.</p>
      </div>
      <Aviso texto={AVISO_BASE} />
    </>
  );
}

/** Muestra el error; si es «sin resultados», lo explica con calma en vez de como una falla. */
export function Falla({ error, delito, reintentar }: { error: unknown; delito: Delito; reintentar?: () => void }) {
  if (error instanceof ApiError && error.codigo === "SIN_RESULTADOS") return <SinResultados delito={delito} />;
  return <><ErrorCaja error={error} reintentar={reintentar} /><Aviso texto={AVISO_BASE} /></>;
}

export function SelectorDelito({ valor, alCambiar }: { valor: Delito; alCambiar: (d: Delito) => void }) {
  return (
    <div className="seg" role="group" aria-label="Tipo de denuncia">
      {(["ROBO", "HURTO"] as Delito[]).map((d) => (
        <button key={d} aria-pressed={valor === d} onClick={() => alCambiar(d)}>{delitoTitulo(d)}</button>
      ))}
    </div>
  );
}

/** Pone el título de la pestaña del navegador para cada pantalla. */
export function Titulo({ texto }: { texto: string }) {
  useEffect(() => { document.title = `${texto} · Denuncias por distrito`; }, [texto]);
  return null;
}

export function Etiqueta({ tipo, children }: { tipo?: "ok" | "warn" | "err"; children: ReactNode }) {
  return <span className={`tag ${tipo ?? ""}`}>{children}</span>;
}

export function Alerta({ tipo, children }: { tipo: "ok" | "err" | "warn"; children: ReactNode }) {
  return <div className={`alert ${tipo}`} role={tipo === "err" ? "alert" : "status"}>{children}</div>;
}
