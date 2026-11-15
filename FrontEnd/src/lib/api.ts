/** Cliente de la API: rutas relativas bajo /api, token solo en memoria, mensajes en español y cierre de sesión si vence. */

export class ApiError extends Error {
  constructor(public status: number, public codigo: string, mensaje: string, public detalle?: unknown) {
    super(mensaje);
  }
}

// Si la API no trae un mensaje propio, se dice algo útil según el tipo de problema.
const MENSAJES: Record<number, string> = {
  0: "No hay conexión con el servidor. Revisa tu internet e inténtalo otra vez.",
  400: "No se pudo completar la acción. Revisa los datos e inténtalo otra vez.",
  401: "Tu sesión terminó. Vuelve a iniciar sesión.",
  403: "Tu cuenta no tiene permiso para hacer esto.",
  404: "No se encontró lo que buscas.",
  409: "Esta acción choca con algo que ya existe.",
  413: "El archivo es demasiado grande.",
  422: "Revisa los datos ingresados.",
  429: "Demasiados intentos seguidos. Espera un momento e inténtalo de nuevo.",
  500: "Algo falló de nuestro lado. Vuelve a intentarlo en un momento.",
  502: "El servicio no está disponible ahora. Vuelve a intentarlo en un momento.",
  503: "El servicio no está disponible ahora. Vuelve a intentarlo en un momento.",
  504: "El servicio tardó demasiado en responder. Vuelve a intentarlo.",
};

let token: string | null = null; // solo en memoria: al recargar la página hay que volver a entrar
let alVencerSesion: (() => void) | null = null;

export const sesion = {
  poner: (t: string) => { token = t; },
  quitar: () => { token = null; },
  alVencer: (f: (() => void) | null) => { alVencerSesion = f; },
};

type Params = Record<string, string | number | boolean | undefined | null>;
interface Opciones { metodo?: string; cuerpo?: unknown; form?: FormData; params?: Params; sinSesion?: boolean; esperaMs?: number }

function construirUrl(ruta: string, params?: Params): string {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, String(v)); });
  const s = q.toString();
  return `/api${ruta}${s ? `?${s}` : ""}`;
}

async function pedir(ruta: string, o: Opciones = {}): Promise<Response> {
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), o.esperaMs ?? 30_000);
  const cab: Record<string, string> = {};
  if (token && !o.sinSesion) cab.Authorization = `Bearer ${token}`;
  if (o.cuerpo !== undefined) cab["Content-Type"] = "application/json";
  let r: Response;
  try {
    r = await fetch(construirUrl(ruta, o.params), {
      method: o.metodo ?? "GET", headers: cab, signal: control.signal,
      body: o.form ?? (o.cuerpo !== undefined ? JSON.stringify(o.cuerpo) : undefined),
    });
  } catch (e) {
    const agotado = e instanceof DOMException && e.name === "AbortError";
    throw new ApiError(agotado ? 504 : 0, "SIN_CONEXION", MENSAJES[agotado ? 504 : 0]);
  } finally {
    clearTimeout(reloj);
  }
  if (r.ok) return r;
  let cuerpo: { codigo?: string; mensaje?: string; detalle?: unknown } = {};
  try { cuerpo = await r.json(); } catch { /* la respuesta no era JSON */ }
  if (r.status === 401 && token && !o.sinSesion) alVencerSesion?.();
  throw new ApiError(r.status, cuerpo.codigo ?? "ERROR", cuerpo.mensaje ?? MENSAJES[r.status] ?? MENSAJES[500], cuerpo.detalle);
}

export const api = {
  get: async <T>(ruta: string, params?: Params): Promise<T> => (await pedir(ruta, { params })).json(),
  post: async <T>(ruta: string, cuerpo?: unknown, o: Opciones = {}): Promise<T> => (await pedir(ruta, { ...o, metodo: "POST", cuerpo })).json(),
  patch: async <T>(ruta: string, cuerpo: unknown): Promise<T> => (await pedir(ruta, { metodo: "PATCH", cuerpo })).json(),
  put: async <T>(ruta: string, cuerpo: unknown): Promise<T> => (await pedir(ruta, { metodo: "PUT", cuerpo })).json(),
  subir: async <T>(ruta: string, form: FormData): Promise<T> => (await pedir(ruta, { metodo: "POST", form, esperaMs: 120_000 })).json(),
  /** Descarga un archivo (CSV o PDF): el token va en la cabecera, por eso no sirve un enlace simple. */
  descargar: async (ruta: string, params: Params): Promise<void> => {
    const r = await pedir(ruta, { params, esperaMs: 60_000 });
    const nombre = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "descarga";
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
