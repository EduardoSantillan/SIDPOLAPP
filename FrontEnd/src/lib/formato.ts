import type { Delito, Periodo } from "./tipos";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"];

/** Número con coma decimal y punto para los miles: 12.345,6 (igual que el resto de los textos). */
export const num = (n: number, d = 0) => n.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d });

/** "2026-07-01" → "julio 2026". Se lee del texto, sin pasar por zonas horarias. */
export function mesTexto(iso: string): string {
  const [a, m] = iso.split("-").map(Number);
  return `${MESES[m - 1]} ${a}`;
}
/** Para empezar una frase: «agosto 2026» → «Agosto 2026». */
export const mayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export const mesCorto = (iso: string) => MESES[Number(iso.split("-")[1]) - 1].slice(0, 3);

export const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString("es-PE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export const delitoTexto = (d: Delito) => (d === "ROBO" ? "robo" : "hurto");
export const delitoTitulo = (d: Delito) => (d === "ROBO" ? "Robo" : "Hurto");

export const PERIODOS: [Periodo, string][] = [["todo", "Todo el periodo"], ["antes_nov_2024", "Antes de nov 2024"], ["desde_nov_2024", "Desde nov 2024"]];

/** "2026-07-01" menos 42 meses → "2023-01-01". Se calcula con el texto, sin zonas horarias. */
export function restarMeses(iso: string, n: number): string {
  const [a, m] = iso.split("-").map(Number);
  const total = a * 12 + (m - 1) - n;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}-01`;
}

/** Aviso de alcance para las pantallas que aún no tienen la respuesta de la API (inicio, errores, sin resultados). Es la primera frase del aviso de la API. */
export const AVISO_BASE = "Cifras de denuncias registradas en SIDPOL: no equivalen a la criminalidad real ni son una recomendación operativa.";

/** «1 denuncia», «12 denuncias»: un número siempre con su unidad. */
export const denuncias = (n: number) => `${num(n)} ${n === 1 ? "denuncia" : "denuncias"}`;

/** "13 denuncias menos que lo registrado", "coincide al redondear", etc. Los valores ya vienen redondeados: no se dice «igual» para no sugerir un acierto exacto. */
export function comparado(diferencia: number): string {
  if (diferencia === 0) return "coincide al redondear";
  return `${denuncias(Math.abs(diferencia))} ${diferencia < 0 ? "menos" : "más"} que lo registrado`;
}
