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
  // la serie respeta el periodo pedido, como la API: «antes» y «desde» nov 2024 recortan el tramo mostrado
  "/distritos/150140/serie": (url) => {
    const periodo = url.searchParams.get("periodo") ?? "todo";
    return { cuerpo: {
      ubigeo: "150140", target: "ROBO", periodo, cambio_registro: { fecha: "2024-11-01", texto: "Desde nov 2024 cambió la forma de registrar" },
      puntos: periodo === "todo" ? puntos : puntos.filter((p) => p.regimen === periodo), estrategias: [], ejecucion_id: "e1", aviso: AVISO } };
  },
};

// Los meses siguientes al último con dato (agosto y setiembre 2026): se estiman, pero todavía no hay denuncias registradas con qué compararlos.
const est = (l: number, g: number, n1: number, ne: number) => [
  { estrategia: "local", etiqueta: "Modelo por distrito", valor: l },
  { estrategia: "global", etiqueta: "Modelo con todo Lima", valor: g },
  { estrategia: "naive1", etiqueta: "Repetir el mes anterior", valor: n1 },
  { estrategia: "naive_estacional", etiqueta: "Repetir el mismo mes del año pasado", valor: ne },
];
const SIGUIENTES = { datos_hasta: "2026-07-01", meses: [{ fecha: "2026-08-01", estimaciones: est(151, 149, 152, 140) }, { fecha: "2026-09-01", estimaciones: est(147, 145, 152, 138) }] };
type CuerpoRuta = { cuerpo: Record<string, unknown> };
const CON_SIGUIENTES: Rutas = {
  ...DATOS,
  "/distritos/150140/resumen": { cuerpo: { ...(DATOS["/distritos/150140/resumen"] as CuerpoRuta).cuerpo, meses_siguientes: SIGUIENTES } },
  "/distritos/150140/serie": (url) => {
    const base = (DATOS["/distritos/150140/serie"] as (u: URL) => CuerpoRuta)(url).cuerpo;
    return { cuerpo: { ...base, meses_siguientes: url.searchParams.get("periodo") === "antes_nov_2024" ? null : SIGUIENTES } };
  },
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
    expect(screen.getByText(/se equivocó en promedio por/)).toHaveTextContent("13,0 denuncias al mes"); // un decimal, igual que la tabla
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

  it("muestra el error con un decimal en la frase y en la tabla, y no dice «igual» cuando solo coincide al redondear", async () => {
    const base = (DATOS["/distritos/150140/resumen"] as { cuerpo: Record<string, unknown> }).cuerpo;
    simularApi({ ...DATOS, "/distritos/150140/resumen": { cuerpo: { ...base, registradas_ultimo_mes: 0,
      estimaciones_ultimo_mes: [
        { estrategia: "local", etiqueta: "Modelo por distrito", valor: 0, diferencia: 0 },
        { estrategia: "global", etiqueta: "Modelo con todo Lima", valor: 0, diferencia: 0 },
      ],
      error_promedio: [
        { estrategia: "local", etiqueta: "Modelo por distrito", denuncias_por_mes: 0.4, mase: 0.9 },
        { estrategia: "global", etiqueta: "Modelo con todo Lima", denuncias_por_mes: 0.5, mase: 0.95 },
        { estrategia: "naive1", etiqueta: "Repetir el mes anterior", denuncias_por_mes: 0.6, mase: 1 },
        { estrategia: "naive_estacional", etiqueta: "Repetir el mismo mes del año pasado", denuncias_por_mes: 0.7, mase: 1.1 },
      ] } } });
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    const frase = await screen.findByText(/se equivocó en promedio por/);
    expect(frase).toHaveTextContent("0,4 denuncias al mes");
    expect(frase).toHaveTextContent("0,5");
    expect(screen.getByRole("cell", { name: "0,4" })).toBeInTheDocument(); // la tabla dice lo mismo que la frase
    expect(screen.getByRole("cell", { name: "0,5" })).toBeInTheDocument();
    expect(screen.getAllByText("coincide al redondear")).toHaveLength(2);
    expect(screen.queryByText(/igual a lo registrado/)).not.toBeInTheDocument();
  });

  it("aclara a qué se aplica el periodo y que la evaluación empezó en enero de 2023, no en nov 2024", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO&periodo=desde_nov_2024");
    await entrar();
    const nota = await screen.findByText(/El periodo seleccionado se aplica al histórico y a las descargas/);
    expect(nota).toHaveTextContent("El resumen de arriba usa siempre los 43 meses evaluados, de enero 2023 a julio 2026");
    expect(await screen.findByText(/existen desde enero 2023, cuando empezó la evaluación; este periodo solo muestra un tramo de ella/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/aparecen solo desde noviembre 2024/);
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

describe("meses sin denuncias registradas todavía", () => {
  it("lo dice con todas sus letras: estimaciones con datos hasta el último mes, setiembre apoyado en agosto, sin compararlas ni mezclarlas con el error", async () => {
    simularApi(CON_SIGUIENTES);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    const titulo = await screen.findByText(/Para agosto 2026 y setiembre 2026, los modelos estiman/);
    const tarjeta = titulo.closest(".card") as HTMLElement;
    expect(titulo).toHaveTextContent("denuncias de robo");
    expect(tarjeta).toHaveTextContent("Modelo por distrito151Agosto 2026147Setiembre 2026");
    expect(tarjeta).toHaveTextContent("Modelo con todo Lima149Agosto 2026145Setiembre 2026");
    expect(tarjeta).toHaveTextContent("Con datos hasta julio 2026");
    expect(tarjeta).toHaveTextContent("Todavía no hay denuncias registradas de esos meses");
    expect(tarjeta).toHaveTextContent("Setiembre 2026 se apoya en la estimación de agosto 2026 y puede equivocarse más");
    expect(tarjeta).not.toHaveTextContent("menos que lo registrado"); // no hay dato con qué comparar
    expect(screen.getByText(/En Santiago de Surco se registraron/)).toHaveTextContent("152 denuncias de robo en julio 2026"); // la respuesta de siempre sigue primero
    const texto = document.body.textContent ?? "";
    for (const prohibida of ["SHA", "naïve", "naive", "pre_break", "post_break", "horizonte", "riesgo", "prioridad", "ranking", "Local", "Global", "peligro"]) {
      expect(texto).not.toContain(prohibida);
    }
  });

  it("en «Todos los distritos» las estimaciones van en columnas aparte, con su aclaración", async () => {
    const f = (ubigeo: string, distrito: string, reg: number, v: number[]) => ({
      ubigeo, distrito, registradas_ultimo_mes: reg,
      estimaciones_siguientes: [
        { fecha: "2026-08-01", estrategia: "local", etiqueta: "Modelo por distrito", valor: v[0] }, { fecha: "2026-08-01", estrategia: "global", etiqueta: "Modelo con todo Lima", valor: v[1] },
        { fecha: "2026-09-01", estrategia: "local", etiqueta: "Modelo por distrito", valor: v[2] }, { fecha: "2026-09-01", estrategia: "global", etiqueta: "Modelo con todo Lima", valor: v[3] }],
      error_promedio: [{ estrategia: "local", etiqueta: "Modelo por distrito", denuncias_por_mes: 13, mase: 0.6 },
                       { estrategia: "global", etiqueta: "Modelo con todo Lima", denuncias_por_mes: 12, mase: 0.5 }] });
    const tabla = (con: boolean) => ({ cuerpo: { target: "ROBO", periodo: "todo", ultimo_mes: ultimo.fecha, mase_explicacion: "x", ejecucion_id: "e1", aviso: AVISO,
      meses_siguientes: con ? ["2026-08-01", "2026-09-01"] : [], datos_hasta: con ? "2026-07-01" : null,
      filas: [f("150131", "San Isidro", 40, [42, 39, 41, 38]), f("150140", "Santiago de Surco", 152, [151, 149, 147, 145])] } });
    simularApi({ ...DATOS, "/distritos/resumen": tabla(true) });
    pintar("/distritos?delito=ROBO");
    await entrar();
    // una columna por mes, con nombre corto, y un selector para elegir qué forma de estimar se ve
    expect(await screen.findByRole("columnheader", { name: /agosto 2026 \(estimado\)/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /setiembre 2026 \(estimado\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /Estimado para/ })).not.toBeInTheDocument(); // sin encabezados largos
    expect(screen.getByRole("cell", { name: "151" })).toBeInTheDocument();      // modelo por distrito, agosto
    expect(screen.getByRole("cell", { name: "147" })).toBeInTheDocument();      // modelo por distrito, setiembre
    await userEvent.selectOptions(screen.getByLabelText("Estimación según"), "global");
    expect(screen.getByRole("cell", { name: "149" })).toBeInTheDocument();      // modelo con todo Lima, agosto
    expect(screen.getByRole("cell", { name: "145" })).toBeInTheDocument();      // modelo con todo Lima, setiembre
    expect(screen.queryByRole("cell", { name: "151" })).not.toBeInTheDocument();
    const nota = screen.getByText(/son estimaciones con datos hasta julio 2026/);
    expect(nota).toHaveTextContent("Agosto 2026 y setiembre 2026 son estimaciones con datos hasta julio 2026: todavía no hay denuncias registradas de esos meses.");
    expect(nota).toHaveTextContent("Setiembre 2026 se apoya en la estimación de agosto 2026, así que puede equivocarse más.");
  });

  it("sin estimaciones para esos meses no aparece la tarjeta (por ejemplo, si la ejecución no las trae)", async () => {
    simularApi(DATOS);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    await screen.findByText(/En Santiago de Surco se registraron/);
    expect(screen.queryByText(/los modelos estiman/)).not.toBeInTheDocument();
  });

  it("en el gráfico los últimos puntos son las estimaciones: se leen en una frase y la tabla los marca sin inventar el registrado", async () => {
    simularApi(CON_SIGUIENTES);
    pintar("/distrito/150140?delito=ROBO");
    await entrar();
    const grafico = await screen.findByRole("img", { name: /Usa las flechas/ });
    const lectura = () => document.querySelector(".readout") as HTMLElement;
    expect(lectura()).toHaveTextContent("julio 2026"); // al abrir se ve el último mes con denuncias registradas
    fireEvent.keyDown(grafico, { key: "ArrowRight" });
    expect(lectura()).toHaveTextContent("agosto 2026: todavía no hay denuncias registradas");
    expect(lectura()).toHaveTextContent("Modelo por distrito: 151");
    fireEvent.keyDown(grafico, { key: "End" });
    expect(lectura()).toHaveTextContent("setiembre 2026: todavía no hay denuncias registradas");
    expect(lectura()).toHaveTextContent("Modelo por distrito: 147");
    expect(lectura()).toHaveTextContent("Modelo con todo Lima: 145");
    for (const mes of ["agosto 2026 (estimación)", "setiembre 2026 (estimación)"]) {
      expect((screen.getByRole("cell", { name: mes }).closest("tr") as HTMLElement)).toHaveTextContent("aún sin dato");
    }
    expect(screen.getByText(/Los círculos del final son la estimación de agosto 2026 y setiembre 2026/)).toBeInTheDocument();
  });

  it("al mirar solo «antes de nov 2024» no aparecen las estimaciones, porque esos meses son posteriores", async () => {
    simularApi(CON_SIGUIENTES);
    pintar("/distrito/150140?delito=ROBO&periodo=antes_nov_2024");
    await entrar();
    await screen.findByRole("img", { name: /Usa las flechas/ });
    expect(screen.queryByText(/Los círculos del final/)).not.toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: /agosto 2026 \(estimación\)/ })).not.toBeInTheDocument(); // el gráfico no los trae; el resumen de arriba sí (usa todos los meses)
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

  it("al cambiar de periodo, el mes elegido sigue si existe en la nueva serie y, si no, pasa al último mes disponible", async () => {
    simularApi(DATOS);
    // Se empieza por el periodo corto para que quede guardado en memoria: al volver a él, la serie cambia al instante
    // con el gráfico ya montado, que es justo el caso en que una posición vieja quedaba fuera de la serie.
    pintar("/distrito/150140?delito=ROBO&periodo=antes_nov_2024");
    await entrar();
    const grafico = () => screen.findByRole("img", { name: /Usa las flechas/ });
    const lectura = () => screen.getByText(/se registraron/, { selector: ".readout" });
    const periodo = (v: string) => userEvent.selectOptions(screen.getByLabelText("Periodo"), v);
    await grafico();

    await periodo("todo");
    await waitFor(() => expect(lectura()).toHaveTextContent("julio 2026"));
    fireEvent.keyDown(await grafico(), { key: "Home" });
    for (let k = 0; k < 3; k++) fireEvent.keyDown(await grafico(), { key: "ArrowRight" });
    expect(lectura()).toHaveTextContent("setiembre 2024");

    await periodo("antes_nov_2024"); // setiembre 2024 sigue existiendo en la serie corta: se conserva
    await waitFor(() => expect(lectura()).toHaveTextContent("setiembre 2024"));

    await periodo("todo");
    fireEvent.keyDown(await grafico(), { key: "End" });
    expect(lectura()).toHaveTextContent("julio 2026");

    await periodo("antes_nov_2024"); // julio 2026 ya no está: pasa al último mes disponible, sin romper la pantalla
    await waitFor(() => expect(lectura()).toHaveTextContent("octubre 2024"));
    expect(lectura()).toHaveTextContent(`${puntos[4].registradas}`);
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
