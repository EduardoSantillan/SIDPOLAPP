import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NOMBRE_ROL } from "../components/Layout";
import { Alerta, Cargando, ErrorCaja, Etiqueta, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Rol, Usuario } from "../lib/tipos";

const ROLES: Rol[] = ["usuario", "analista", "administrador"];
interface Enlace { enlace_activacion: string; vence: string; nombre: string }

/** Administrador: crear cuentas, cambiar el rol y desactivar. El enlace de activación se entrega a mano (no hay correo). */
export function Usuarios() {
  const cache = useQueryClient();
  const yo = useAuth();
  const [form, setForm] = useState({ nombre: "", correo: "", rol: "usuario" as Rol });
  const [enlace, setEnlace] = useState<Enlace | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [pendiente, setPendiente] = useState<{ id: string; datos: { rol?: Rol; activo?: boolean }; texto: string } | null>(null);
  const lista = useQuery({ queryKey: ["usuarios"], queryFn: () => api.get<{ items: Usuario[] }>("/usuarios", { limite: 200 }) });
  const refrescar = () => cache.invalidateQueries({ queryKey: ["usuarios"] });

  const crear = useMutation({
    mutationFn: () => api.post<{ enlace_activacion: string; vence: string }>("/usuarios", { ...form, nombre: form.nombre.trim(), correo: form.correo.trim() }),
    onSuccess: (r) => { setEnlace({ ...r, nombre: form.nombre.trim() }); setCopiado(false); setForm({ nombre: "", correo: "", rol: "usuario" }); refrescar(); },
  });
  const cambiar = useMutation({ mutationFn: (a: { id: string; datos: { rol?: Rol; activo?: boolean } }) => api.patch(`/usuarios/${a.id}`, a.datos), onSuccess: refrescar });
  const reenviar = useMutation({
    mutationFn: (u: Usuario) => api.post<{ enlace_activacion: string; vence: string }>(`/usuarios/${u.id}/reenviar-activacion`).then((r) => ({ ...r, nombre: u.nombre })),
    onSuccess: (r) => { setEnlace(r); setCopiado(false); },
  });
  const esYo = (u: Usuario) => u.rol === "administrador" && u.nombre === yo.usuario?.nombre; // no puede quitarse su propio acceso
  const copiar = async () => { await navigator.clipboard?.writeText(enlace!.enlace_activacion); setCopiado(true); };

  return (
    <>
      <Titulo texto="Usuarios" />
      <h1>Usuarios</h1>
      <p className="lead">Crea cuentas y define qué puede hacer cada persona.</p>

      <form className="card" onSubmit={(e) => { e.preventDefault(); crear.mutate(); }}>
        <h2>Crear una cuenta</h2>
        <div className="grid2">
          <label className="f"><span>Nombre</span><input type="text" required minLength={2} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></label>
          <label className="f"><span>Correo</span><input type="email" required value={form.correo} onChange={(e) => setForm({ ...form, correo: e.target.value })} /></label>
        </div>
        <label className="f" style={{ maxWidth: 300 }}><span>Rol</span>
          <select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value as Rol })}>
            <option value="usuario">Usuario (consulta)</option><option value="analista">Analista de datos</option><option value="administrador">Administrador del sistema</option>
          </select>
        </label>
        <button className="primary" type="submit" disabled={crear.isPending}>{crear.isPending ? "Creando…" : "Crear cuenta"}</button>
        {crear.error && <ErrorCaja error={crear.error} />}
      </form>

      {enlace && (
        <Alerta tipo="ok">
          <b>Entrégale este enlace a {enlace.nombre}.</b> Sirve una sola vez y vence en 72 horas. Con él elegirá su contraseña.
          <div className="row" style={{ marginTop: 8 }}>
            <input type="text" readOnly value={enlace.enlace_activacion} aria-label="Enlace de activación" onFocus={(e) => e.currentTarget.select()} style={{ flex: 1, minWidth: 240 }} />
            <button onClick={copiar}>{copiado ? "Copiado" : "Copiar enlace"}</button>
          </div>
        </Alerta>
      )}

      <div className="card tabla-scroll">
        <h2>Cuentas</h2>
        {pendiente && (
          <Alerta tipo="warn">
            {pendiente.texto}
            <div className="row" style={{ marginTop: 8 }}>
              <button className="primary" onClick={() => { cambiar.mutate({ id: pendiente.id, datos: pendiente.datos }); setPendiente(null); }}>Confirmar</button>
              <button onClick={() => setPendiente(null)}>Cancelar</button>
            </div>
          </Alerta>
        )}
        {lista.isPending ? <Cargando /> : lista.error ? <ErrorCaja error={lista.error} reintentar={() => lista.refetch()} /> : (
          <table>
            <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th><span className="sr">Acciones</span></th></tr></thead>
            <tbody>
              {lista.data.items.map((u) => (
                <tr key={u.id}>
                  <td>{u.nombre}</td><td>{u.correo}</td>
                  <td>
                    <select aria-label={`Rol de ${u.nombre}`} value={u.rol} disabled={u.estado === "inactivo" || cambiar.isPending || esYo(u)} title={esYo(u) ? "No puedes cambiar tu propio rol" : undefined}
                            onChange={(e) => setPendiente({ id: u.id, datos: { rol: e.target.value as Rol }, texto: `¿Cambiar a ${u.nombre} a «${NOMBRE_ROL[e.target.value as Rol]}»? Cambia lo que puede hacer en la plataforma.` })}>
                      {ROLES.map((r) => <option key={r} value={r}>{NOMBRE_ROL[r]}</option>)}
                    </select>
                  </td>
                  <td>{u.estado === "activo" ? <Etiqueta tipo="ok">Activo</Etiqueta> : u.estado === "inactivo" ? <Etiqueta tipo="err">Desactivado</Etiqueta> : <Etiqueta tipo="warn">Falta activar</Etiqueta>}</td>
                  <td>
                    {u.estado === "activo" && <button onClick={() => setPendiente({ id: u.id, datos: { activo: false }, texto: `¿Desactivar la cuenta de ${u.nombre}? No podrá entrar. Podrás reactivarla cuando quieras.` })} disabled={esYo(u)} title={esYo(u) ? "No puedes desactivar tu propia cuenta" : undefined}>Desactivar</button>}
                    {u.estado === "inactivo" && <button onClick={() => cambiar.mutate({ id: u.id, datos: { activo: true } })}>Reactivar</button>}
                    {u.estado === "pendiente_activacion" && <button onClick={() => reenviar.mutate(u)}>Nuevo enlace</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cambiar.error && <ErrorCaja error={cambiar.error} />}
        {reenviar.error && <ErrorCaja error={reenviar.error} />}
      </div>
    </>
  );
}
