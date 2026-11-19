import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alerta, Cargando, ErrorCaja, Etiqueta, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { delitoTitulo, fechaHora, mesTexto } from "../lib/formato";
import type { Delito, Ejecucion, Version } from "../lib/tipos";

const ESTADO = { en_curso: ["warn", "En curso"], completada: ["ok", "Completada"], fallida: ["err", "Fallida"] } as const;
const Estado = ({ e }: { e: Ejecucion["estado"] }) => <Etiqueta tipo={ESTADO[e][0]}>{ESTADO[e][1]}</Etiqueta>;

function haceCuanto(iso: string): string {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return min < 1 ? "hace menos de un minuto" : `hace ${min} minuto${min > 1 ? "s" : ""}`;
}

/** Analista: elegir los datos y el tipo de denuncia, iniciar el cálculo y seguirlo hasta que termine. */
export function Ejecuciones() {
  const cache = useQueryClient();
  const [versionId, setVersionId] = useState("");
  const [delito, setDelito] = useState<Delito>("ROBO");
  const [elegida, setElegida] = useState<string | null>(null);
  const [confirmando, setConfirmando] = useState(false);

  const versiones = useQuery({ queryKey: ["versiones"], queryFn: () => api.get<{ items: Version[] }>("/versiones") });
  const lista = useQuery({
    queryKey: ["ejecuciones"], queryFn: () => api.get<{ items: Ejecucion[] }>("/ejecuciones"),
    refetchInterval: (q) => (q.state.data?.items.some((e) => e.estado === "en_curso") ? 4000 : false),
  });
  const items = lista.data?.items ?? [];
  const actual = items.find((e) => e.ejecucion_id === elegida) ?? items[0];
  const detalle = useQuery({
    queryKey: ["ejecucion", actual?.ejecucion_id], enabled: !!actual,
    queryFn: () => api.get<Ejecucion>(`/ejecuciones/${actual!.ejecucion_id}`),
    refetchInterval: (q) => (q.state.data?.estado === "en_curso" ? 4000 : false),
  });

  const iniciar = useMutation({
    mutationFn: () => api.post<{ ejecucion_id: string }>("/ejecuciones", { version_id: versionId || versiones.data?.items[0]?.id, target: delito }),
    onSuccess: (r) => { setElegida(r.ejecucion_id); cache.invalidateQueries({ queryKey: ["ejecuciones"] }); },
  });
  const hayVersiones = (versiones.data?.items.length ?? 0) > 0;
  const datosElegidos = versiones.data?.items.find((v) => v.id === (versionId || versiones.data?.items[0]?.id));

  return (
    <>
      <Titulo texto="Ejecuciones" />
      <h1>Ejecuciones</h1>
      <p className="lead">Genera los resultados que ven las demás personas. Puede tardar unos minutos y puedes seguir usando la plataforma mientras tanto.</p>
      <div className="card">
        <h2>Iniciar una ejecución nueva</h2>
        {versiones.isPending ? <Cargando /> : versiones.error ? <ErrorCaja error={versiones.error} /> : !hayVersiones ? (
          <Alerta tipo="warn">No hay datos completos para usar todavía. Pídele al administrador que registre una versión de datos y la revise.</Alerta>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); setConfirmando(true); }}>
            <div className="row">
              <label className="f" style={{ margin: 0, flex: 2, minWidth: 220 }}><span>Datos a usar</span>
                <select value={versionId} onChange={(e) => setVersionId(e.target.value)} style={{ width: "100%" }}>
                  {versiones.data!.items.map((v) => <option key={v.id} value={v.id}>{v.nombre_archivo} · corte {mesTexto(`${v.periodo_corte}-01`)} · {v.version}</option>)}
                </select>
              </label>
              <label className="f" style={{ margin: 0 }}><span>Tipo de denuncia</span>
                <select value={delito} onChange={(e) => setDelito(e.target.value as Delito)}><option value="ROBO">Robo</option><option value="HURTO">Hurto</option></select>
              </label>
              <button className="primary" type="submit" disabled={iniciar.isPending} style={{ alignSelf: "flex-end" }}>{iniciar.isPending ? "Iniciando…" : "Iniciar ejecución"}</button>
            </div>
            {confirmando && (
              <Alerta tipo="warn">
                Se calcularán los resultados de <b>{delitoTitulo(delito)}</b>{datosElegidos && <> con <b>{datosElegidos.nombre_archivo}</b> (corte {mesTexto(`${datosElegidos.periodo_corte}-01`)})</>}.
                Cuando termine, las demás personas verán estos resultados.
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="primary" type="button" onClick={() => { setConfirmando(false); iniciar.mutate(); }}>Confirmar e iniciar</button>
                  <button type="button" onClick={() => setConfirmando(false)}>Cancelar</button>
                </div>
              </Alerta>
            )}
            <p className="note" style={{ marginTop: 10 }}>Solo aparecen los datos que ya pasaron todas las revisiones. Si falta alguno, el administrador lo resuelve en «Versiones de datos».</p>
          </form>
        )}
        {iniciar.error && <ErrorCaja error={iniciar.error} />}
        {iniciar.isSuccess && <Alerta tipo="ok">Ejecución iniciada. Puedes cambiar de pantalla: seguirá en el historial.</Alerta>}
      </div>

      <div className="cols dos">
        <div className="card tabla-scroll">
          <h2>Historial</h2>
          {lista.isPending ? <Cargando /> : lista.error ? <ErrorCaja error={lista.error} reintentar={() => lista.refetch()} /> : !items.length ? (
            <p className="muted">Todavía no se inició ninguna ejecución.</p>
          ) : (
            <table>
              <thead><tr><th>Tipo</th><th>Datos</th><th>Estado</th><th>Inicio</th></tr></thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.ejecucion_id} className={`click ${e.ejecucion_id === actual?.ejecucion_id ? "sel" : ""}`}>
                    <td><button className="enlace" onClick={() => setElegida(e.ejecucion_id)} aria-pressed={e.ejecucion_id === actual?.ejecucion_id}>{delitoTitulo(e.target)}</button></td>
                    <td>{e.version.nombre} · corte {mesTexto(`${e.version.corte}-01`)}</td><td><Estado e={e.estado} /></td><td>{fechaHora(e.inicio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {actual && (
          <div className="card sidepanel" aria-live="polite">
            <h2>{delitoTitulo(actual.target)} · corte {mesTexto(`${actual.version.corte}-01`)}</h2>
            <Estado e={detalle.data?.estado ?? actual.estado} />
            {(detalle.data?.estado ?? actual.estado) === "en_curso" && (
              <p className="note" style={{ marginTop: 12 }}><span className="spin" aria-hidden="true" />Calculando. Empezó {haceCuanto(actual.inicio)}. Esta pantalla se actualiza sola.</p>
            )}
            {detalle.data?.estado === "fallida" && <Alerta tipo="err"><b>No terminó.</b> {detalle.data.motivo} No se guardó ningún resultado a medias. Vuelve a iniciarla desde arriba.</Alerta>}
            {detalle.data?.estado === "completada" && (
              <>
                <Alerta tipo="ok"><b>Terminó.</b> Los resultados ya están disponibles para todas las personas.</Alerta>
                <Link className="btn" to={`/comparar?delito=${actual.target}`}>Ver la comparación de modelos</Link>
              </>
            )}
            {detalle.data?.configuracion && (
              <dl className="datos">
                <dt>Configuración</dt><dd>{detalle.data.configuracion.nombre} · {detalle.data.configuracion.version}</dd>
                <dt>Huella de la configuración</dt><dd className="mono">{detalle.data.configuracion.sha256}</dd>
              </dl>
            )}
          </div>
        )}
      </div>
    </>
  );
}
