import { useEffect, useMemo, useRef, useState } from "react";
import { denuncias, mayuscula, mesCorto, mesTexto, num } from "../lib/formato";
import type { Serie } from "../lib/tipos";

const W = 860, H = 340, L = 46, R = 50, T = 14, B = 34;
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
type Punto = { fecha: string; registradas: number | null; regimen: string; estimaciones: Record<string, number> };

export function Grafico({ serie, distrito }: { serie: Serie; distrito: string }) {
  const ms = serie.meses_siguientes;
  // Los meses que aún no tienen denuncias registradas van al final como puntos sin cifra registrada, solo con la estimación.
  const p: Punto[] = useMemo(() => {
    const reales: Punto[] = serie.puntos;
    const futuros: Punto[] = (ms?.meses ?? []).map((m) => ({ fecha: m.fecha, registradas: null, regimen: "desde_nov_2024", estimaciones: Object.fromEntries(m.estimaciones.map((e) => [e.estrategia, e.valor])) }));
    return [...reales, ...futuros];
  }, [serie.puntos, ms]);
  const ultimoReal = serie.puntos.length - 1;
  // Se recuerda el MES elegido, no su posición: si el periodo cambia y ese mes ya no está, se vuelve al último mes con denuncias registradas.
  const [elegido, setElegido] = useState<string | null>(null);
  const enSerie = elegido ? p.findIndex((x) => x.fecha === elegido) : -1;
  const i = enSerie >= 0 ? enSerie : ultimoReal;
  const caja = useRef<HTMLDivElement>(null);
  // En el teléfono el gráfico se desliza de lado: se empieza viendo lo más reciente.
  useEffect(() => { if (caja.current) caja.current.scrollLeft = caja.current.scrollWidth; }, [serie.puntos.length]);
  const fijar = (k: number | null) => setElegido(k == null ? null : p[Math.max(0, Math.min(p.length - 1, k))]?.fecha ?? null);

  const g = useMemo(() => {
    const n = Math.max(1, p.length - 1);
    const valores = p.flatMap((x) => [x.registradas, x.estimaciones.local, x.estimaciones.global].filter((v): v is number => v != null));
    const paso = pasoBonito(Math.max(5, ...valores) * 1.05);
    const max = paso * 4;
    const X = (k: number) => L + (k / n) * (W - L - R);
    const Y = (v: number) => T + (H - T - B) - (v / max) * (H - T - B);
    const trazo = (f: (k: number) => number | null | undefined) => {
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
    fijar(Math.round(((px - L) / (W - L - R)) * (p.length - 1)));
  };
  const tecla = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); fijar(i - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); fijar(i + 1); }
    if (e.key === "Home") { e.preventDefault(); fijar(0); }
    if (e.key === "End") { e.preventDefault(); fijar(p.length - 1); }
  };

  const act = p[i];
  const marcas = p.map((x, k) => ({ x, k })).filter(({ x, k }) => k === 0 || x.fecha.slice(5, 7) === "01");
  return (
    <>
      <div className="chartwrap">
        <div className="chartscroll" ref={caja}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" tabIndex={0}
             aria-label={`Denuncias registradas por mes en ${distrito} y lo que estimaba cada modelo. Usa las flechas para recorrer los meses.`}
             onPointerMove={(e) => mover(e.clientX, e.currentTarget)} onPointerDown={(e) => mover(e.clientX, e.currentTarget)} onPointerLeave={() => fijar(null)} onKeyDown={tecla}>
          {g.quiebre >= 0 && (
            <>
              <rect x={g.X(g.quiebre)} y={T} width={g.X(p.length - 1) - g.X(g.quiebre)} height={H - T - B} fill="var(--regime)" />
              <text x={g.X(g.quiebre) + 6} y={T + 14}>Desde nov 2024</text>
            </>
          )}
          {ms && ms.meses.length > 0 && (
            <rect className="banda-est" x={g.X(ultimoReal)} y={T} width={g.X(p.length - 1) - g.X(ultimoReal) + 36} height={H - T - B} />
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
          {act.registradas != null && <circle cx={g.X(i)} cy={g.Y(act.registradas)} r="5" fill="var(--ink)" />}
          {(["global", "local"] as const).map((e) => act.estimaciones[e] != null && (
            <circle key={`sel-${e}`} cx={g.X(i)} cy={g.Y(act.estimaciones[e])} r="4" fill={e === "local" ? "var(--in)" : "var(--wa)"} stroke="var(--surface)" strokeWidth="1.5" />
          ))}
          {(() => {  // el mes que se está mirando, bien grande y pegado a la línea, para no tener que bajar la vista
            const texto = mayuscula(mesTexto(act.fecha)), ancho = texto.length * 8.6 + 22, cabe = g.X(i) + 8 + ancho <= W - 4;
            const x = cabe ? g.X(i) + 8 : g.X(i) - 8 - ancho;
            return (
              <g pointerEvents="none" aria-hidden="true">
                <rect x={x} y={T + 2} width={ancho} height={28} rx="6" fill="var(--surface)" stroke="var(--ink3)" />
                <text x={x + ancho / 2} y={T + 21} textAnchor="middle" style={{ fontSize: 15, fontWeight: 700, fill: "var(--ink)" }}>{texto}</text>
              </g>
            );
          })()}
          {ms && ms.meses.length > 0 && (
            <>
              {(() => {  // el rótulo va arriba, salvo que los círculos queden ahí: entonces va abajo
                const ys = p.slice(ultimoReal + 1).flatMap((pt) => (["local", "global"] as const).map((e) => pt.estimaciones[e]).filter((v) => v != null).map((v) => g.Y(v)));
                const arriba = Math.min(...ys) > T + 34;
                return <text x={g.X(p.length - 1) + 34} y={arriba ? T + 14 : H - B - 8} textAnchor="end">Estimación</text>;
              })()}
              {p.slice(ultimoReal + 1).flatMap((pt, j) => (["global", "local"] as const).map((e) => pt.estimaciones[e] != null && (
                <circle key={`${j}-${e}`} cx={g.X(ultimoReal + 1 + j)} cy={g.Y(pt.estimaciones[e])} r="4.5" fill="none" stroke={e === "local" ? "var(--in)" : "var(--wa)"} strokeWidth="2.2" />
              )))}
              {(() => {  // los números del último mes estimado, uno arriba y otro abajo para que no se encimen
                const ult = p[p.length - 1], k = p.length - 1;
                const par = (["local", "global"] as const).filter((e) => ult.estimaciones[e] != null).sort((a, b) => ult.estimaciones[b] - ult.estimaciones[a]);
                return par.map((e, j) => (
                  <text key={e} x={g.X(k) + 9} y={g.Y(ult.estimaciones[e]) + (j === 0 ? -6 : 14)} fontWeight="700" fill={e === "local" ? "var(--in)" : "var(--wa)"}>{num(ult.estimaciones[e])}</text>
                ));
              })()}
            </>
          )}
        </svg>
        </div>
        <p className="note solo-movil">Desliza el gráfico hacia los lados para ver otros meses.</p>
        <div className="readout" aria-live="polite">
          {act.registradas != null ? (
            <>
              <b>{mesTexto(act.fecha)}</b>: se registraron <b>{denuncias(act.registradas)}</b>
              {act.estimaciones.local != null && (
                <>; el modelo por distrito estimaba <b>{denuncias(act.estimaciones.local)}</b> y el modelo con todo Lima, <b>{denuncias(act.estimaciones.global ?? 0)}</b>.</>
              )}
            </>
          ) : (
            <>
              <b>{mesTexto(act.fecha)}</b>: todavía no hay denuncias registradas. Estimación con datos hasta {mesTexto(ms?.datos_hasta ?? act.fecha)}:
              {" "}el modelo por distrito, <b>{denuncias(act.estimaciones.local ?? 0)}</b>; el modelo con todo Lima, <b>{denuncias(act.estimaciones.global ?? 0)}</b>.
            </>
          )}
        </div>
      </div>
      <div className="legend">
        <span><i style={{ borderColor: "var(--ink)" }} />Denuncias registradas</span>
        <span><i style={{ borderColor: "var(--in)", borderTopStyle: "dashed" }} />{ETQ.local} (lo que estimaba)</span>
        <span><i style={{ borderColor: "var(--wa)", borderTopStyle: "dotted" }} />{ETQ.global} (lo que estimaba)</span>
        {ms && ms.meses.length > 0 && <span><span className="circ" aria-hidden="true" />Estimación de los meses sin denuncias registradas</span>}
      </div>
      <details>
        <summary>Ver los números mes a mes</summary>
        <div className="tabla-scroll" style={{ maxHeight: 280 }}>
          <table>
            <thead><tr><th>Mes</th><th className="n">Registradas</th><th className="n">{ETQ.local}</th><th className="n">{ETQ.global}</th></tr></thead>
            <tbody>
              {[...p].reverse().map((x) => (
                <tr key={x.fecha}>
                  <td>{mesTexto(x.fecha)}{x.registradas == null && " (estimación)"}</td><td className="n">{x.registradas != null ? num(x.registradas) : "aún sin dato"}</td>
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
