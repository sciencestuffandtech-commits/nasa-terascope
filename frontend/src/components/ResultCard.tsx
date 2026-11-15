import { LineChart, Line, XAxis, YAxis, ReferenceLine, Tooltip, ResponsiveContainer } from "recharts";
import { SEASONS } from "../lib/api";
import type { SeriesResult, VarMeta, Sel, Season } from "../lib/api";

export const LABEL: Record<Season, string> = { All: "Whole year", DJF: "Dec to Feb", MAM: "Mar to May", JJA: "Jun to Aug", SON: "Sep to Nov" };
export const f = (v: number) => (Number.isFinite(v) ? (v >= 0 ? "+" : "") + v.toFixed(Math.abs(v) < 0.1 ? 3 : 2) : "n/a");
const tone: Record<string, string> = {
  "Robustly detectable trend": "#1a7f4b", "Probable trend": "#1c6fb5", "Uncertain trend": "#a86a00",
  "No statistically detectable trend": "#4a5561", "Insufficient data": "#4a5561",
};

export default function ResultCard({ r, meta, sel, short, onSeason, onExport }: {
  r: SeriesResult; meta: VarMeta; sel: Sel; short: boolean; onSeason: (s: Season) => void; onExport: () => void;
}) {
  const u = `${meta.units}/decade`, exploratory = !!r.custom || short;
  const nums = r.values.filter((v): v is number => v != null);
  const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
  const mx = Math.max(1e-9, ...Object.values(r.by_season ?? {}).map(v => Math.abs(v ?? 0)));
  return (
    <div className="card">
      {exploratory ? <p className="badge" style={{ background: "#3a4552" }}>Custom selection</p>
        : <p className="badge" style={{ background: tone[r.class] }}>{r.class}</p>}
      <p className="big">{f(r.slope_per_decade)} <small>{u}</small></p>
      {exploratory ? null : (<>
        <p>95% CI {f(r.ci_analytical[0])} to {f(r.ci_analytical[1])}{r.ci_bootstrap && <> · bootstrap {f(r.ci_bootstrap[0])} to {f(r.ci_bootstrap[1])}</>}</p>
        <p>p = {r.p.toPrecision(2)}{r.q != null && <> · q (FDR) = {r.q.toPrecision(2)}</>}</p>
        <p className="explain">{r.explanation}</p>
      </>)}

      <h3>Trend by season</h3>
      <table className="seasons"><tbody>
        {SEASONS.map(k => { const v = r.by_season?.[k] ?? NaN; return (
          <tr key={k} className={sel.season === k ? "on" : ""} onClick={() => onSeason(k)}>
            <td>{LABEL[k]}</td><td className="num">{f(v)}</td>
            <td className="barcell"><span className={v < 0 ? "neg" : "pos"} style={{ width: `${Number.isFinite(v) ? (Math.abs(v) / mx) * 100 : 0}%` }} /></td>
          </tr>); })}
      </tbody></table>
      <p className="note">{u} over {sel.start} to {sel.end}. Click a row to chart that season.</p>

      <h3>Summary of selection</h3>
      <p className="stats">Mean {mean.toFixed(2)} · min {Math.min(...nums).toFixed(2)} · max {Math.max(...nums).toFixed(2)} {meta.units} · {nums.length} months · {r.valid_pct.toFixed(0)}% valid</p>

      {!r.custom && (
        <details>
          <summary>Evidence and sensitivity checks</summary>
          <ul>
            <li>Direction agrees in {(r.f_sign * 100).toFixed(0)}% of rolling 15-year windows.</li>
            <li>Annual-mean autocorrelation check: {r.c4 ? "agrees" : "does not agree"}.</li>
            <li>Unresolved data discontinuity: {r.c5 ? "yes, capped at Uncertain" : "none documented"}.</li>
          </ul>
          <ResponsiveContainer width="100%" height={130}>
            <LineChart data={r.windows}>
              <XAxis dataKey="start" tick={{ fill: "#7f93a5", fontSize: 11 }} /><YAxis width={40} tick={{ fill: "#7f93a5", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#0b1119", border: "1px solid #1c2835" }} />
              <ReferenceLine y={0} stroke="#7f93a5" /><Line dataKey="slope" stroke="#5fc3ff" dot isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="note">Slope per decade by window start year.</p>
        </details>
      )}
      <button className="export" onClick={onExport}>Export report as PDF</button>

    </div>
  );
}