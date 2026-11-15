import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LOGIN, pintar, simularApi, type Rutas } from "./ayudas";

const AVISO = "Cifras de denuncias registradas en SIDPOL: no equivalen a la criminalidad real ni son una recomendación operativa.";

// 26 meses seguidos: de junio 2024 a julio 2026
const puntos = Array.from({ length: 26 }, (_, i) => {
  const a = 2024 + Math.floor((5 + i) / 12), mes = ((5 + i) % 12) + 1;
  return { fecha: `${a}-${String(mes).padStart(2, "0")}-01`, registradas: 100 + i, regimen: a * 12 + mes >= 2024 * 12 + 11 ? "desde_nov_2024" : "antes_nov_2024",
           estimaciones: i >= 10 ? { local: 90 + i, global: 95 + i, naive1: 99 + i, naive_estacional: 80 + i } : {} };
});
const ultimo = puntos[puntos.length - 1];

const DATOS: Rutas = {
  "POST /auth/login": LOGIN("usuario"),
  "/distritos": { cuerpo: [{ ubigeo: "150140", nombre: "Santiago de Surco" }, { ubigeo: "150131", nombre: "San Isidro" }] },
  "/distritos/150140/resumen": { cuerpo: {
    ubigeo: "150140", distrito: "Santiago de Surco", target: "ROBO", periodo: "todo", ultimo_mes: ultimo.fecha, registradas_ultimo_mes: 152,
    estimaciones_ultimo_mes: [
      { estrategia: "local", etiqueta: "Modelo por distrito", valor: 140, diferencia: -12 },
      { estrategia: "global", etiqueta: "Modelo con todo Lima", valor: 138, diferencia: -14 },
    ],
    error_promedio: [
      { estrategia: "local", etiqueta: "Modelo por distrito", denuncias_por_mes: 13, mase: 0.64 },
      { estrategia: "global", etiqueta: "Modelo con todo Lima", denuncias_por_mes: 12.1, mase: 0.61 },
      { estrategia: "naive1", etiqueta: "Repetir el mes anterior", denuncias_por_mes: 20.5, mase: 1 },
      { estrategia: "naive_estacional", etiqueta: "Repetir el mismo mes del año pasado", denuncias_por_mes: 23, mase: 1.12 },
    ],
    mase_explicacion: "MASE compara el error con el de repetir el mismo mes del año anterior (escala fija 2018–2022): 0,64 = 64 % de ese error. Menos es mejor.",
    meses_evaluados: 43, rango_habitual: { min: 100, max: 200, meses: 12 }, ejecucion_id: "e1", aviso: AVISO } },
  "/distritos/150140/serie": { cuerpo: {
    ubigeo: "150140", target: "ROBO", periodo: "todo", cambio_registro: { fecha: "2024-11-01", texto: "Desde nov 2024 cambió la forma de registrar" },
    puntos, estrategias: [], ejecucion_id: "e1", aviso: AVISO } },
};

afterEach(() => vi.unstubAllGlobals());

async function entrar(rol: "usuario" | "analista" | "administrador" = "usuario") {
  await userEvent.type(await screen.findByLabelText("Correo"), "alguien@prueba.pe");
  await userEvent.type(screen.getByLabelText("Contraseña"), "clave-segura-123");
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
  return rol;
}

describe("acceso", () => {
  it("sin sesión lleva al inicio de sesión y, tras entrar, vuelve a donde la persona iba", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    await entrar();
    expect(await screen.findByText(/En Santiago de Surco se registraron/)).toBeInTheDocument();
  });

  it("con credenciales malas muestra el mensaje de la API y no entra", async () => {
    simularApi({ ...DATOS, "POST /auth/login": { status: 401, cuerpo: { codigo: "CREDENCIALES_INCORRECTAS", mensaje: "Correo o contraseña incorrectos." } } });
    pintar("/");
    await entrar();
    expect(await screen.findByRole("alert")).toHaveTextContent("Correo o contraseña incorrectos.");
    expect(screen.queryByText("¿De qué distrito quieres saber?")).not.toBeInTheDocument();
  });

  it("un Usuario que escribe la dirección de una pantalla del Analista ve una explicación amable", async () => {
    simularApi(DATOS);
    pintar("/ejecuciones");
    await entrar();
    expect(await screen.findByText("Esta sección no está disponible para tu cuenta")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ejecuciones" })).not.toBeInTheDocument();
  });

  it("cada rol ve solo su menú", async () => {
    simularApi({ ...DATOS, "POST /auth/login": LOGIN("analista") });
    pintar("/");
    await entrar("analista");
    const menu = await screen.findByRole("navigation", { name: "Secciones" });
    expect(menu).toHaveTextContent("Comparar modelos");
    expect(menu).toHaveTextContent("Ejecuciones");
    expect(menu).not.toHaveTextContent("Usuarios");
  });
});

describe("Inicio y Mi distrito", () => {
  it("encuentra el distrito escribiendo una parte del nombre, sin importar tildes ni mayúsculas, y lo abre", async () => {
    simularApi(DATOS);
    pintar("/");
    await entrar();
    await userEvent.type(await screen.findByLabelText("Distrito"), "SURCO");
    await userEvent.click(await screen.findByRole("option", { name: "Santiago de Surco" }));
    expect(await screen.findByText(/En Santiago de Surco se registraron/)).toBeInTheDocument();
  });

  it("da la respuesta primero, en una frase con su unidad, y después el detalle", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    const frase = await screen.findByText(/En Santiago de Surco se registraron/);
    expect(frase).toHaveTextContent("152 denuncias de robo en julio 2026");
    expect(screen.getByText("Modelo por distrito", { selector: ".t" })).toBeInTheDocument();
    expect(screen.getByText("12 menos que lo registrado")).toBeInTheDocument();
    expect(screen.getByText(/se equivocó en promedio por/)).toHaveTextContent("13 denuncias al mes");
    expect(screen.getByText(/0,64 = 64 % de ese error/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(AVISO); // el aviso de alcance siempre visible
  });

  it("la pantalla del Usuario no tiene jerga técnica ni etiquetas de riesgo", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    await screen.findByText(/En Santiago de Surco se registraron/);
    const texto = document.body.textContent ?? "";
    for (const prohibida of ["SHA", "naïve", "naive", "pre_break", "post_break", "origen", "horizonte", "riesgo", "prioridad", "ranking", "Local", "Global"]) {
      expect(texto).not.toContain(prohibida);
    }
  });

  it("si todavía no hay resultados lo dice con calma, sin inventar números", async () => {
    simularApi({ ...DATOS, "/distritos/150140/resumen": { status: 404, cuerpo: { codigo: "SIN_RESULTADOS", mensaje: "Todavía no hay resultados de robo." } },
                 "/distritos/150140/serie": { status: 404, cuerpo: { codigo: "SIN_RESULTADOS", mensaje: "Todavía no hay resultados de robo." } } });
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    expect(await screen.findByText("Todavía no hay resultados de robo")).toBeInTheDocument();
    expect(screen.queryByText(/denuncias de robo en/)).not.toBeInTheDocument();
  });

  it("cambiar el periodo pide la serie de ese periodo y deja el enlace compartible", async () => {
    const llamadas = simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    await screen.findByText(/En Santiago de Surco se registraron/);
    await userEvent.selectOptions(screen.getByLabelText("Periodo"), "desde_nov_2024");
    await waitFor(() => expect(llamadas.some((l) => l.url.pathname.endsWith("/serie") && l.url.searchParams.get("periodo") === "desde_nov_2024")).toBe(true));
  });
});

describe("gráfico accesible", () => {
  it("el mes se lee en una frase, se recorre con las flechas y hay una tabla con los mismos números", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    const grafico = await screen.findByRole("img", { name: /Usa las flechas/ });
    expect(screen.getByText(/se registraron/, { selector: ".readout" })).toHaveTextContent(`${ultimo.registradas}`);
    fireEvent.keyDown(grafico, { key: "Home" });
    expect(screen.getByText(/se registraron/, { selector: ".readout" })).toHaveTextContent("junio 2024");
    expect(screen.getByText("Ver los números mes a mes")).toBeInTheDocument();
  });
});

describe("Analista", () => {
  it("si ya hay una ejecución en curso muestra el mensaje de la API en vez de fallar en silencio", async () => {
    simularApi({
      ...DATOS, "POST /auth/login": LOGIN("analista"),
      "/versiones": { cuerpo: { items: [{ id: "v1", nombre_archivo: "datos.csv", periodo_corte: "2026-07", version: "v1", estado: "integra", registrada_en: "2026-11-01T10:00:00Z" }] } },
      "/ejecuciones": (_u, init) => init?.method === "POST"
        ? { status: 409, cuerpo: { codigo: "EJECUCION_EN_CURSO", mensaje: "Ya hay una ejecución en curso para este delito. Espera a que termine." } }
        : { cuerpo: { items: [] } },
    });
    pintar("/ejecuciones");
    await entrar("analista");
    await userEvent.click(await screen.findByRole("button", { name: "Iniciar ejecución" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ya hay una ejecución en curso para este delito. Espera a que termine.");
  });
});
