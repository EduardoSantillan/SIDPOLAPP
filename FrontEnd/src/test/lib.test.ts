import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, sesion } from "../lib/api";
import { comparado, denuncias, mesTexto, num, restarMeses } from "../lib/formato";

afterEach(() => { vi.unstubAllGlobals(); sesion.quitar(); sesion.alVencer(null); });

describe("formato", () => {
  it("usa coma decimal y escribe los meses con palabras", () => {
    expect(num(30.25, 1)).toBe("30,3");
    expect(num(0.6412, 2)).toBe("0,64");
    expect(num(12345)).toBe("12.345");
    expect(mesTexto("2026-07-01")).toBe("julio 2026");
    expect(mesTexto("2024-09-01")).toBe("setiembre 2024");
  });
  it("compara lo estimado con lo registrado en una frase", () => {
    expect(comparado(-12)).toBe("12 denuncias menos que lo registrado");
    expect(comparado(1)).toBe("1 denuncia más que lo registrado");
    expect(comparado(0)).toBe("coincide al redondear");
  });
  it("pone la unidad a cada número, en singular cuando es uno", () => {
    expect(denuncias(1)).toBe("1 denuncia");
    expect(denuncias(0)).toBe("0 denuncias");
    expect(denuncias(12345)).toBe("12.345 denuncias");
  });
  it("resta meses sin salirse del calendario", () => {
    expect(restarMeses("2026-07-01", 42)).toBe("2023-01-01");
    expect(restarMeses("2026-02-01", 2)).toBe("2025-12-01");
    expect(restarMeses("2026-07-01", 0)).toBe("2026-07-01");
  });
});

describe("cliente de la API", () => {
  const responder = (status: number, cuerpo: unknown) =>
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(cuerpo), { status, headers: { "content-type": "application/json" } })));

  it("muestra el mensaje en español que trae la API", async () => {
    responder(409, { codigo: "EJECUCION_EN_CURSO", mensaje: "Ya hay una ejecución en curso para este delito. Espera a que termine." });
    await expect(api.post("/ejecuciones", {})).rejects.toMatchObject({ status: 409, codigo: "EJECUCION_EN_CURSO", message: "Ya hay una ejecución en curso para este delito. Espera a que termine." });
  });
  it("si la API no trae mensaje, dice algo útil según el tipo de problema", async () => {
    responder(500, "boom");
    await expect(api.get("/x")).rejects.toMatchObject({ message: "Algo falló de nuestro lado. Vuelve a intentarlo en un momento." });
  });
  it("sin conexión lo dice con claridad", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed"); }));
    const e: unknown = await api.get("/x").catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).message).toMatch(/No hay conexión/);
  });
  it("cierra la sesión cuando el servidor responde 401 con una sesión abierta, pero no en el inicio de sesión", async () => {
    const vencer = vi.fn();
    sesion.alVencer(vencer);
    sesion.poner("token-de-prueba");
    responder(401, { codigo: "TOKEN_INVALIDO", mensaje: "Tu sesión terminó." });
    await api.get("/distritos").catch(() => {});
    expect(vencer).toHaveBeenCalledTimes(1);
    vencer.mockClear();
    await api.post("/auth/login", {}, { sinSesion: true }).catch(() => {});
    expect(vencer).not.toHaveBeenCalled();
  });
  it("manda el token solo cuando hay sesión y nunca en el inicio de sesión", async () => {
    const f = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    sesion.poner("abc");
    await api.get("/ficha");
    await api.post("/auth/login", {}, { sinSesion: true });
    const cab = (i: number) => (f.mock.calls[i] as unknown as [string, RequestInit])[1].headers as Record<string, string>;
    expect(cab(0).Authorization).toBe("Bearer abc");
    expect(cab(1).Authorization).toBeUndefined();
  });
});
