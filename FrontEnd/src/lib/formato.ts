import type { Delito, Periodo } from "./tipos";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"];

/** Número con coma decimal y punto para los miles: 12.345,6 (igual que el resto de los textos). */
export const num = (n: number, d = 0) => n.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d });

/** "2026-07-01" → "julio 2026". Se lee del texto, sin pasar por zonas horarias. */
export function mesTexto(iso: string): string {
  const [a, m] = iso.split("-").map(Number);
  return `${MESES[m - 1]} ${a}`;
}
export const mesCorto = (iso: string) => MESES[Number(iso.split("-")[1]) - 1].slice(0, 3);

export const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString("es-PE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export const delitoTexto = (d: Delito) => (d === "ROBO" ? "robo" : "hurto");
export const delitoTitulo = (d: Delito) => (d === "ROBO" ? "Robo" : "Hurto");

export const PERIODOS: [Periodo, string][] = [["todo", "Todo el periodo"], ["antes_nov_2024", "Antes de nov 2024"], ["desde_nov_2024", "Desde nov 2024"]];

/** "13 menos que lo registrado", "igual a lo registrado", etc. */
export function comparado(diferencia: number): string {
  if (diferencia === 0) return "igual a lo registrado";
  return `${num(Math.abs(diferencia))} ${diferencia < 0 ? "menos" : "más"} que lo registrado`;
}
