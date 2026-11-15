import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { sesion } from "../lib/api";
import { AuthProvider } from "../lib/auth";

type Respuesta = { status?: number; cuerpo: unknown };
export type Rutas = Record<string, Respuesta | ((url: URL, init?: RequestInit) => Respuesta)>;

/** Reemplaza fetch por respuestas fijas según la ruta (sin el prefijo /api). Lo que no esté definido da 404, como la API. */
export function simularApi(rutas: Rutas) {
  const llamadas: { url: URL; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (entrada: string, init?: RequestInit) => {
    const url = new URL(entrada, "http://prueba");
    llamadas.push({ url, init });
    const clave = url.pathname.replace(/^\/api/, "");
    const r = rutas[clave] ?? rutas[`${init?.method ?? "GET"} ${clave}`];
    const res = typeof r === "function" ? r(url, init) : r ?? { status: 404, cuerpo: { codigo: "NO_EXISTE", mensaje: "No se encontró lo que buscas." } };
    const status = res.status ?? 200;
    return new Response(JSON.stringify(res.cuerpo), { status, headers: { "content-type": "application/json" } });
  }));
  return llamadas;
}

export function pintar(ruta: string) {
  sesion.quitar();
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={cache}>
      <MemoryRouter initialEntries={[ruta]}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

export const LOGIN = (rol: "usuario" | "analista" | "administrador"): Respuesta => ({ cuerpo: { token: "t", rol, nombre: "Persona de prueba" } });
