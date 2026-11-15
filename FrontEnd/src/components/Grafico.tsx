import { useMemo, useState } from "react";
import { mesCorto, mesTexto, num } from "../lib/formato";
import type { Serie } from "../lib/tipos";

const W = 860, H = 300, L = 46, R = 16, T = 14, B = 34;
/** Un paso «redondo» (1, 2, 5, 10, 20, 50…) para que el eje diga 0, 100, 200, 300, 400 y no 0, 99, 199. */
function pasoBonito(max: number): number {
  const crudo = max / 4, pot = 10 ** Math.floor(Math.log10(crudo)), f = crudo / pot;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pot;
}
const ETQ = { local: "Modelo por distrito", global: "Modelo con todo Lima" } as const;

/**
 * Lo registrado contra lo que estimaban los dos modelos. Las líneas se distinguen por trazo y por color.
 * Pasar el ratón o usar las flechas del teclado muestra el mes en una frase; debajo hay una tabla con los mismos números.
 */
export function Grafico({ serie, distrito }: { serie: Serie; distrito: string }) {
  const p = serie.puntos;
  const [fijo, setFijo] = useState<number | null>(null);
  const i = fijo ?? p.length - 1;

  const g = useMemo(() => {
    const n = Math.max(1, p.length - 1);
    const valores = p.flatMap((x) => [x.registradas, x.estimaciones.local, x.estimaciones.global].filter((v): v is number => v != null));
    const paso = pasoBonito(Math.max(5, ...valores) * 1.05);
    const max = paso * 4;
    const X = (k: number) => L + (k / n) * (W - L - R);
    const Y = (v: number) => T + (H - T - B) - (v / max) * (H - T - B);
    const trazo = (f: (k: number) => number | undefined) => {
      let d = "", baja = true;
      p.forEach((_, k) => {
        const v = f(k);
        if (v == null) { baja = true; return; }
        d += `${baja ? "M" : "L"}${X(k).toFixed(1)} ${Y(v).toFixed(1)} `;
        baja = false;
      });
      return d;
    };
    const quiebre = p.findIndex((x) => x.regimen === "desde_nov_2024");
    return { max, X, Y, trazo, quiebre };
  }, [p]);

  if (!p.length) return <p className="muted">No hay meses para mostrar en este periodo.</p>;

  const mover = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * W;
    setFijo(Math.max(0, Math.min(p.length - 1, Math.round(((px - L) / (W - L - R)) * (p.length - 1)))));
  };
  const tecla = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setFijo(Math.max(0, i - 1)); }
    if (e.key === "ArrowRight") { e.preventDefault(); setFijo(Math.min(p.length - 1, i + 1)); }
    if (e.key === "Home") { e.preventDefault(); setFijo(0); }
    if (e.key === "End") { e.preventDefault(); setFijo(p.length - 1); }
  };

  const act = p[i];
  const marcas = p.map((x, k) => ({ x, k })).filter(({ x, k }) => k === 0 || x.fecha.slice(5, 7) === "01");
  return (
    <>
      <div className="chartwrap">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" tabIndex={0}
             aria-label={`Denuncias registradas por mes en ${distrito} y lo que estimaba cada modelo. Usa las flechas para recorrer los meses.`}
             onMouseMove={(e) => mover(e.clientX, e.currentTarget)} onMouseLeave={() => setFijo(null)} onKeyDown={tecla}>
          {g.quiebre >= 0 && (
            <>
              <rect x={g.X(g.quiebre)} y={T} width={g.X(p.length - 1) - g.X(g.quiebre)} height={H - T - B} fill="var(--regime)" />
              <text x={g.X(g.quiebre) + 6} y={T + 14}>Desde nov 2024</text>
            </>
          )}
          {[0, 1, 2, 3, 4].map((k) => {
            const v = (g.max * k) / 4;
            return <g key={k}><line x1={L} x2={W - R} y1={g.Y(v)} y2={g.Y(v)} stroke="var(--line)" /><text x={L - 8} y={g.Y(v) + 4} textAnchor="end">{num(Math.round(v))}</text></g>;
          })}
          {marcas.map(({ x, k }) => <text key={k} x={g.X(k)} y={H - 10} textAnchor="middle">{x.fecha.slice(5, 7) === "01" ? x.fecha.slice(0, 4) : mesCorto(x.fecha)}</text>)}
          <path d={g.trazo((k) => p[k].estimaciones.global)} fill="none" stroke="var(--wa)" strokeWidth="2.2" strokeDasharray="2 3" />
          <path d={g.trazo((k) => p[k].estimaciones.local)} fill="none" stroke="var(--in)" strokeWidth="2.2" strokeDasharray="6 4" />
          <path d={g.trazo((k) => p[k].registradas)} fill="none" stroke="var(--ink)" strokeWidth="2.6" />
          <line x1={g.X(i)} x2={g.X(i)} y1={T} y2={H - B} stroke="var(--ink3)" strokeDasharray="3 3" />
          <circle cx={g.X(i)} cy={g.Y(act.registradas)} r="4" fill="var(--ink)" />
        </svg>
        <div className="readout" aria-live="polite">
          <b>{mesTexto(act.fecha)}</b>: se registraron <b>{num(act.registradas)}</b> denuncias
          {act.estimaciones.local != null && (
            <> · {ETQ.local}: <b>{num(act.estimaciones.local)}</b> · {ETQ.global}: <b>{num(act.estimaciones.global ?? 0)}</b></>
          )}
        </div>
      </div>
      <div className="legend">
        <span><i style={{ borderColor: "var(--ink)" }} />Denuncias registradas</span>
        <span><i style={{ borderColor: "var(--in)", borderTopStyle: "dashed" }} />{ETQ.local} (lo que estimaba)</span>
        <span><i style={{ borderColor: "var(--wa)", borderTopStyle: "dotted" }} />{ETQ.global} (lo que estimaba)</span>
      </div>
      <details>
        <summary>Ver los números mes a mes</summary>
        <div className="tabla-scroll" style={{ maxHeight: 280 }}>
          <table>
            <thead><tr><th>Mes</th><th className="n">Registradas</th><th className="n">{ETQ.local}</th><th className="n">{ETQ.global}</th></tr></thead>
            <tbody>
              {[...p].reverse().map((x) => (
                <tr key={x.fecha}>
                  <td>{mesTexto(x.fecha)}</td><td className="n">{num(x.registradas)}</td>
                  <td className="n">{x.estimaciones.local != null ? num(x.estimaciones.local) : "—"}</td>
                  <td className="n">{x.estimaciones.global != null ? num(x.estimaciones.global) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
