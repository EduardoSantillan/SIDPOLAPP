import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Alerta, Cargando, ErrorCaja, Etiqueta, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { fechaHora, mesTexto } from "../lib/formato";
import type { Pendiente, Version, VersionDetalle } from "../lib/tipos";
import { usarDistritos } from "./Inicio";

const ESTADO: Record<Version["estado"], ["ok" | "warn" | "err" | undefined, string]> = {
  integra: ["ok", "Íntegra"], con_pendientes: ["warn", "Con distritos por resolver"], invalida: ["err", "No válida"], registrada: [undefined, "Registrada"],
};
const TITULO_CONTROL: Record<string, string> = {
  estructura: "Columnas esperadas", conteos_positivos: "Conteos válidos", continuidad_mensual: "Meses continuos", periodo_corte: "Mes de corte",
  inicio_serie: "Inicio de la serie", ubigeo_reconocido: "Códigos de distrito reconocidos", claves_unicas: "Sin filas repetidas",
  distritos_completos: "Los 43 distritos", delitos_presentes: "Robo y hurto presentes", ceros_reconstruidos: "Meses sin registros", integridad_sha256: "Archivo sin alteraciones",
};
const ORDEN_CONTROLES = Object.keys(TITULO_CONTROL);

/** Administrador: registrar el archivo, ver qué revisiones pasó y resolver los códigos de distrito que el sistema no reconoce. */
export function Versiones() {
  const cache = useQueryClient();
  const archivo = useRef<HTMLInputElement>(null);
  const [corte, setCorte] = useState("");
  const [nombre, setNombre] = useState("");
  const [elegida, setElegida] = useState<string | null>(null);

  const lista = useQuery({ queryKey: ["versiones"], queryFn: () => api.get<{ items: Version[] }>("/versiones") });
  const items = lista.data?.items ?? [];
  const actual = items.find((v) => v.id === elegida) ?? items[0];
  const detalle = useQuery({ queryKey: ["version", actual?.id], enabled: !!actual, queryFn: () => api.get<VersionDetalle>(`/versiones/${actual!.id}`) });
  const refrescar = () => { cache.invalidateQueries({ queryKey: ["versiones"] }); cache.invalidateQueries({ queryKey: ["version"] }); cache.invalidateQueries({ queryKey: ["pendientes"] }); };

  const registrar = useMutation({
    mutationFn: () => {
      const f = archivo.current?.files?.[0];
      if (!f) throw new Error("falta");
      const form = new FormData();
      form.set("archivo", f); form.set("periodo_corte", corte); form.set("version", nombre.trim());
      return api.subir<VersionDetalle>("/versiones", form);
    },
    onSuccess: (v) => { setElegida(v.id); refrescar(); if (archivo.current) archivo.current.value = ""; },
  });

  return (
    <>
      <Titulo texto="Versiones de datos" />
      <h1>Versiones de datos</h1>
      <p className="lead">Registra el archivo que publica el Ministerio del Interior y revisa que esté completo. Las versiones guardadas no se pueden borrar ni cambiar: si hay un error, se registra una nueva.</p>

      <form className="card" onSubmit={(e) => { e.preventDefault(); registrar.mutate(); }}>
        <h2>Registrar una versión nueva</h2>
        <div className="grid2">
          <label className="f"><span>Archivo CSV (hasta 40 MB)</span><input ref={archivo} type="file" accept=".csv" required /></label>
          <label className="f"><span>Mes de corte (último mes que trae el archivo)</span><input type="month" required value={corte} onChange={(e) => setCorte(e.target.value)} /></label>
        </div>
        <label className="f" style={{ maxWidth: 260 }}><span>Nombre de la versión</span><input type="text" required maxLength={60} value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="por ejemplo, v1" /></label>
        <button className="primary" type="submit" disabled={registrar.isPending}>{registrar.isPending ? "Registrando y revisando…" : "Registrar y revisar"}</button>
        {registrar.error && <ErrorCaja error={registrar.error} />}
        {registrar.data && (registrar.data.estado === "integra"
          ? <Alerta tipo="ok"><b>Versión registrada.</b> Pasó todas las revisiones y ya se puede usar para calcular.</Alerta>
          : registrar.data.estado === "con_pendientes"
            ? <Alerta tipo="warn"><b>Versión registrada, pero falta un paso.</b> Hay códigos de distrito que el sistema no reconoce; resuélvelos abajo.</Alerta>
            : <Alerta tipo="err"><b>Versión registrada, pero no pasó las revisiones.</b> Mira abajo qué falló; corrige el archivo y regístralo como una versión nueva.</Alerta>)}
      </form>

      <div className="cols dos">
        <div className="card tabla-scroll">
          <h2>Versiones registradas</h2>
          {lista.isPending ? <Cargando /> : lista.error ? <ErrorCaja error={lista.error} reintentar={() => lista.refetch()} /> : !items.length ? <p className="muted">Todavía no hay versiones registradas.</p> : (
            <table>
              <thead><tr><th>Archivo</th><th>Corte</th><th>Estado</th></tr></thead>
              <tbody>
                {items.map((v) => (
                  <tr key={v.id} className={v.id === actual?.id ? "sel" : ""}>
                    <td><button className="enlace" onClick={() => setElegida(v.id)} aria-pressed={v.id === actual?.id}>{v.nombre_archivo}</button></td>
                    <td>{mesTexto(`${v.periodo_corte}-01`)}</td><td><Etiqueta tipo={ESTADO[v.estado][0]}>{ESTADO[v.estado][1]}</Etiqueta></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {actual && <Revision v={detalle.data} cargando={detalle.isPending} error={detalle.error} alCambiar={refrescar} />}
      </div>
    </>
  );
}

function Revision({ v, cargando, error, alCambiar }: { v?: VersionDetalle; cargando: boolean; error: unknown; alCambiar: () => void }) {
  const verificar = useMutation({ mutationFn: () => api.post<VersionDetalle>(`/versiones/${v!.id}/verificar`), onSuccess: alCambiar });
  if (cargando) return <div className="card sidepanel"><Cargando /></div>;
  if (error || !v) return <div className="card sidepanel"><ErrorCaja error={error} /></div>;
  return (
    <div className="card sidepanel">
      <h2>Revisión de {v.nombre_archivo}</h2>
      <ul className="controles">
        {[...v.controles].sort((a, b) => ORDEN_CONTROLES.indexOf(a.control) - ORDEN_CONTROLES.indexOf(b.control)).map((c) => (
          <li key={c.control} className={c.aprobado ? "ok" : "mal"}>
            <span className="ic" aria-hidden="true">{c.aprobado ? "✔" : "✖"}</span>
            <span><b>{TITULO_CONTROL[c.control] ?? c.control}</b>{c.aprobado ? "" : " — no pasó"}<br /><span className="note">{typeof c.detalle === "string" ? c.detalle : ""}</span></span>
          </li>
        ))}
      </ul>
      <p className="note">Huella del archivo (SHA-256): <span className="mono">{v.sha256}</span><br />Registrada el {fechaHora(v.registrada_en)} por {v.registrada_por}</p>
      {v.estado === "integra" && <Alerta tipo="ok"><b>Versión íntegra.</b> Ya se puede usar para calcular.</Alerta>}
      {v.estado === "invalida" && <Alerta tipo="err"><b>Esta versión no se puede usar.</b> Corrige el archivo y regístralo otra vez como una versión nueva; esta se queda guardada como registro.</Alerta>}
      {v.estado === "con_pendientes" && (
        <>
          <Alerta tipo="warn"><b>Hay códigos de distrito que el sistema no reconoce.</b> Dile a qué distrito corresponde cada uno.</Alerta>
          <Pendientes versionId={v.id} alCambiar={alCambiar} />
          {v.pendientes_abiertos === 0 && (
            <>
              <button className="primary" onClick={() => verificar.mutate()} disabled={verificar.isPending}>{verificar.isPending ? "Revisando…" : "Volver a revisar la versión"}</button>
              {verificar.error && <ErrorCaja error={verificar.error} />}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Pendientes({ versionId, alCambiar }: { versionId: string; alCambiar: () => void }) {
  const distritos = usarDistritos();
  const q = useQuery({ queryKey: ["pendientes", versionId], queryFn: () => api.get<{ items: Pendiente[] }>(`/versiones/${versionId}/pendientes`) });
  if (q.isPending) return <Cargando />;
  if (q.error) return <ErrorCaja error={q.error} />;
  return (
    <div>
      {q.data.items.map((p) => <FilaPendiente key={p.id} p={p} distritos={distritos.data ?? []} alCambiar={alCambiar} />)}
    </div>
  );
}

function FilaPendiente({ p, distritos, alCambiar }: { p: Pendiente; distritos: { ubigeo: string; nombre: string }[]; alCambiar: () => void }) {
  const [ubigeo, setUbigeo] = useState("");
  const guardar = useMutation({ mutationFn: () => api.put(`/pendientes/${p.id}/equivalencia`, { ubigeo }), onSuccess: alCambiar });
  if (p.estado === "resuelto") {
    const d = distritos.find((x) => x.ubigeo === p.ubigeo);
    return <p className="row" style={{ marginBottom: 8 }}>✔ Código <b>{p.codigo}</b> → {d?.nombre ?? p.ubigeo}</p>;
  }
  return (
    <div className="row" style={{ marginBottom: 8 }}>
      <span>Código <b>{p.codigo}</b> ({p.filas} filas)</span>
      <select aria-label={`Distrito del código ${p.codigo}`} value={ubigeo} onChange={(e) => setUbigeo(e.target.value)}>
        <option value="">Elegir distrito…</option>
        {distritos.map((d) => <option key={d.ubigeo} value={d.ubigeo}>{d.nombre}</option>)}
      </select>
      <button disabled={!ubigeo || guardar.isPending} onClick={() => guardar.mutate()}>Guardar</button>
      {guardar.error && <ErrorCaja error={guardar.error} />}
    </div>
  );
}
