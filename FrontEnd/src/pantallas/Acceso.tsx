import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { ErrorCaja, Alerta, Titulo } from "../components/Pieza";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Login() {
  const { usuario, entrar, aviso } = useAuth();
  const { state } = useLocation() as { state: { desde?: string } | null };
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const m = useMutation({ mutationFn: () => entrar(correo.trim(), clave) });

  if (usuario) return <Navigate to={state?.desde ?? (usuario.rol === "administrador" ? "/versiones" : "/")} replace />;
  const enviar = (e: FormEvent) => { e.preventDefault(); m.mutate(); }; // al entrar, el <Navigate> de arriba lleva a cada rol a su pantalla

  return (
    <main>
      <Titulo texto="Iniciar sesión" />
      <form className="login card" onSubmit={enviar}>
        <div className="brand" style={{ marginBottom: 6 }}>Denuncias por distrito</div>
        <h1 style={{ fontSize: 24 }}>Iniciar sesión</h1>
        <p className="note">Solo entran personas con una cuenta creada por el administrador. Si olvidaste tu clave, pídele ayuda a él.</p>
        {aviso && <Alerta tipo="warn">{aviso}</Alerta>}
        <label className="f"><span>Correo</span>
          <input type="email" autoComplete="username" required value={correo} onChange={(e) => setCorreo(e.target.value)} placeholder="nombre@dominio.pe" />
        </label>
        <label className="f"><span>Contraseña</span>
          <input type="password" autoComplete="current-password" required value={clave} onChange={(e) => setClave(e.target.value)} />
        </label>
        <button className="primary" type="submit" style={{ width: "100%" }} disabled={m.isPending}>{m.isPending ? "Entrando…" : "Entrar"}</button>
        {m.error && <ErrorCaja error={m.error} />}
      </form>
    </main>
  );
}

/** Pantalla a la que llega la persona con el enlace que le dio el administrador. */
export function Activar() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [clave, setClave] = useState("");
  const [repetida, setRepetida] = useState("");
  const m = useMutation({ mutationFn: () => api.post("/auth/activar", { token, contrasena: clave }, { sinSesion: true }) });
  const corta = clave.length > 0 && clave.length < 10;
  const distinta = repetida.length > 0 && repetida !== clave;

  return (
    <main>
      <Titulo texto="Activar tu cuenta" />
      <div className="login card">
        <div className="brand" style={{ marginBottom: 6 }}>Denuncias por distrito</div>
        <h1 style={{ fontSize: 24 }}>Elige tu contraseña</h1>
        {m.isSuccess ? (
          <>
            <Alerta tipo="ok"><b>Tu cuenta quedó lista.</b> Ya puedes entrar con tu correo y la contraseña que elegiste.</Alerta>
            <Link className="btn primary" to="/login">Ir a iniciar sesión</Link>
          </>
        ) : !token ? (
          <Alerta tipo="err">Este enlace está incompleto. Pídele uno nuevo al administrador.</Alerta>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); if (!corta && !distinta) m.mutate(); }}>
            <p className="note">Usa al menos 10 caracteres. Puede ser una frase fácil de recordar.</p>
            <label className="f"><span>Contraseña nueva</span>
              <input type="password" autoComplete="new-password" required value={clave} onChange={(e) => setClave(e.target.value)} aria-invalid={corta} />
            </label>
            {corta && <p className="note" role="status" style={{ color: "var(--er)" }}>Faltan {10 - clave.length} caracteres.</p>}
            <label className="f"><span>Escríbela otra vez</span>
              <input type="password" autoComplete="new-password" required value={repetida} onChange={(e) => setRepetida(e.target.value)} aria-invalid={distinta} />
            </label>
            {distinta && <p className="note" role="status" style={{ color: "var(--er)" }}>Las dos contraseñas no coinciden.</p>}
            <button className="primary" type="submit" style={{ width: "100%" }} disabled={m.isPending || clave.length < 10 || clave !== repetida}>
              {m.isPending ? "Guardando…" : "Guardar y activar mi cuenta"}
            </button>
            {m.error && <ErrorCaja error={m.error} />}
          </form>
        )}
      </div>
    </main>
  );
}
