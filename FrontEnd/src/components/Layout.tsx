import { NavLink, Navigate, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "../lib/auth";
import type { Rol } from "../lib/tipos";

export const NOMBRE_ROL: Record<Rol, string> = { usuario: "Usuario", analista: "Analista de datos", administrador: "Administrador del sistema" };

const CON_DELITO = new Set(["/", "/distritos", "/comparar"]);

const MENU: Record<Rol, [string, string][]> = {
  usuario: [["/", "Inicio"], ["/distritos", "Todos los distritos"], ["/ficha", "Cómo se calculó"]],
  analista: [["/", "Inicio"], ["/distritos", "Todos los distritos"], ["/comparar", "Comparar modelos"], ["/ejecuciones", "Ejecuciones"], ["/ficha", "Cómo se calculó"]],
  administrador: [["/versiones", "Versiones de datos"], ["/usuarios", "Usuarios"], ["/", "Inicio"], ["/distritos", "Todos los distritos"], ["/ficha", "Cómo se calculó"]],
};

/** Pantalla con cabecera. Sin sesión, lleva al inicio de sesión y vuelve después a donde la persona iba. */
export function Layout() {
  const { usuario, salir, salidaManual } = useAuth();
  const lugar = useLocation();
  const [params] = useSearchParams();
  const delito = params.get("delito"); // se conserva al pasar de una pantalla a otra: quien miraba hurto sigue viendo hurto
  if (!usuario) return <Navigate to="/login" replace state={salidaManual ? undefined : { desde: lugar.pathname + lugar.search }} />;
  return (
    <>
      <a className="skip" href="#contenido">Saltar al contenido</a>
      <header className="top">
        <div className="brand">Denuncias por distrito</div>
        <nav aria-label="Secciones">
          {MENU[usuario.rol].map(([ruta, texto]) => (
            <NavLink key={ruta} to={delito && CON_DELITO.has(ruta) ? `${ruta}?delito=${delito}` : ruta} end={ruta === "/"}>{texto}</NavLink>
          ))}
        </nav>
        <div className="who"><span>{NOMBRE_ROL[usuario.rol]}</span><button onClick={salir}>Salir</button></div>
      </header>
      <main id="contenido" tabIndex={-1}><Outlet /></main>
    </>
  );
}

/** Deja pasar solo a los roles indicados; a los demás les explica sin asustar. */
export function SoloRoles({ roles }: { roles: Rol[] }) {
  const { usuario } = useAuth();
  if (usuario && !roles.includes(usuario.rol)) {
    return (
      <div className="card">
        <h1>Esta sección no está disponible para tu cuenta</h1>
        <p className="lead">Si la necesitas, pídele acceso al administrador del sistema.</p>
        <NavLink className="btn" to={usuario.rol === "administrador" ? "/versiones" : "/"}>Ir al inicio</NavLink>
      </div>
    );
  }
  return <Outlet />;
}
