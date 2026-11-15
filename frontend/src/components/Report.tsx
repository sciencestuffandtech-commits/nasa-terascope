import { LineChart, Line, XAxis, YAxis, ReferenceLine, CartesianGrid } from "recharts";
import SeriesChart from "./SeriesChart";
import { LABEL, f } from "./ResultCard";
import { USE_FIXTURES } from "../lib/api";
import type { SeriesResult, VarMeta, Sel } from "../lib/api";

export default function Report({ r, meta, cell, sel, short, shot }: {
  r: SeriesResult; meta: VarMeta; cell: { lat: number; lon: number }; sel: Sel; short: boolean; shot: string | null;
}) {
  const ex = !!r.custom || short;
  return (
    <section className="report">
      <h1>Earth System Trend Detective</h1>
      <p className="rmeta">Report generated {new Date().toLocaleString()}</p>
      {USE_FIXTURES && <p className="rwarn">FIXTURE DATA: synthetic, not NASA observations.</p>}
      <h2>{meta.name}</h2>
      <table className="rt"><tbody>
        <tr><td>Location (grid cell centre)</td><td>{cell.lat}°, {cell.lon}° ({meta.grid} grid)</td></tr>
        <tr><td>Period and season</td><td>{sel.start} to {sel.end}, {LABEL[sel.season]}</td></tr>
        <tr><td>Estimated trend</td><td>{f(r.slope_per_decade)} {meta.units}/decade</td></tr>
        {!ex && <tr><td>95% confidence interval</td><td>{f(r.ci_analytical[0])} to {f(r.ci_analytical[1])}</td></tr>}
        {!ex && <tr><td>p and q (FDR)</td><td>{r.p.toPrecision(2)} and {r.q != null ? r.q.toPrecision(2) : "n/a"}</td></tr>}
        <tr><td>Valid observations</td><td>{r.valid_pct.toFixed(0)}%</td></tr>
      </tbody></table>
      {!ex && <p>{r.explanation}</p>}
      <SeriesChart r={r} units={meta.units} width={680} light />
      <h3>Trend by season (per decade, {sel.start} to {sel.end})</h3>
      <table className="rt"><tbody>
        {Object.entries(r.by_season ?? {}).map(([k, v]) => <tr key={k}><td>{LABEL[k as keyof typeof LABEL]}</td><td>{f(v ?? NaN)} {meta.units}</td></tr>)}
      </tbody></table>
      {!r.custom && (<>
        <h3>Rolling 15-year windows</h3>
        <LineChart width={680} height={150} data={r.windows}>
          <CartesianGrid stroke="#ddd" /><XAxis dataKey="start" /><YAxis width={40} /><ReferenceLine y={0} stroke="#888" />
          <Line dataKey="slope" stroke="#0b6fa8" dot isAnimationActive={false} />
        </LineChart>
        <p>Direction agrees in {(r.f_sign * 100).toFixed(0)}% of windows. Annual-mean check: {r.c4 ? "agrees" : "does not agree"}. Unresolved discontinuity: {r.c5 ? "yes" : "none documented"}.</p>
      </>)}
      {shot && (<><h3>Map at export time</h3><img src={shot} alt="Trend map" className="rmap" /></>)}
      <h3>Data and limitations</h3>
      <p>{meta.dataset} {meta.version}, {meta.grid}, {meta.period[0]} to {meta.period[1]}. DOI: {meta.doi}.</p>
      <p>{meta.limitations.join(" ")} {meta.discontinuities.join(" ")}</p>
    </section>
  );
}
