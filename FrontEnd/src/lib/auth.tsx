import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, sesion } from "./api";
import type { Rol } from "./tipos";

interface Usuario { nombre: string; rol: Rol }
interface Auth {
  usuario: Usuario | null;
  /** Mensaje para mostrar en el inicio de sesión (por ejemplo, «tu sesión terminó»). */
  aviso: string | null;
  entrar: (correo: string, contrasena: string) => Promise<void>;
  salir: () => void;
  /** Verdadero si la persona salió a propósito: la siguiente que entre no vuelve a la pantalla de la anterior. */
  salidaManual: boolean;
}

const Contexto = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [salidaManual, setSalidaManual] = useState(false);
  const cache = useQueryClient();

  const limpiar = useCallback(() => {
    sesion.quitar();
    setUsuario(null);
    cache.clear(); // nada de lo que vio esta persona queda para la siguiente
  }, [cache]);
  const salir = useCallback(() => { setSalidaManual(true); limpiar(); }, [limpiar]);

  useEffect(() => {
    sesion.alVencer(() => { setAviso("Tu sesión terminó. Vuelve a iniciar sesión."); setSalidaManual(false); limpiar(); });
    return () => sesion.alVencer(null);
  }, [limpiar]);

  const entrar = useCallback(async (correo: string, contrasena: string) => {
    const r = await api.post<{ token: string; rol: Rol; nombre: string }>("/auth/login", { correo, contrasena }, { sinSesion: true });
    sesion.poner(r.token);
    setAviso(null);
    setSalidaManual(false);
    setUsuario({ nombre: r.nombre, rol: r.rol });
  }, []);

  const valor = useMemo(() => ({ usuario, aviso, entrar, salir, salidaManual }), [usuario, aviso, entrar, salir, salidaManual]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Contexto);
  if (!c) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return c;
}
