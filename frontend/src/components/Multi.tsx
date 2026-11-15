import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import { getCompare, LOC_COLORS } from "../lib/api";
import type { Cell, SeriesResult, VarMeta, CompareResult, Joint } from "../lib/api";
import { f } from "./ResultCard";

const ink = "#7f93a5";
const tip = { background: "#0b1119", border: "1px solid #1c2835" };
const fmt = (v: unknown) => (typeof v === "number" ? v.toFixed(3) : String(v));
const SHORT: Record<string, string> = {
  "Robustly detectable trend": "Robust", "Probable trend": "Probable", "Uncertain trend": "Uncertain",
  "No statistically detectable trend": "None detectable", "Insufficient data": "Insufficient data",
};

export function ComparePanel({ varId, meta, cells, results, exploratory, custom }: {
  varId: string; meta: VarMeta; cells: Cell[]; results: SeriesResult[]; exploratory: boolean; custom: boolean;
}) {
  const [cmp, setCmp] = useState<CompareResult | null>(null);
  const [err, setErr] = useState("");
  const key = cells.map(c => `${c.lat},${c.lon}`).join("|");
  useEffect(() => {
    setCmp(null); setErr("");
    if (cells.length < 2) return;
    let dead = false;
    getCompare(varId, cells).then(r => { if (!dead) setCmp(r); }).catch(e => { if (!dead) setErr(String(e)); });
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, varId]);

  const data = useMemo(() => {
    const m = new Map<string, any>();
    results.forEach((r, k) => r.dates.forEach((d, i) => { const row = m.get(d) ?? { d }; row[`s${k}`] = r.anomalies[i]; m.set(d, row); }));
    return [...m.values()].sort((a, b) => String(a.d).localeCompare(String(b.d)));
  }, [results]);

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Compare locations: {meta.name}</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid stroke="#1c2835" />
          <XAxis dataKey="d" minTickGap={48} tick={{ fill: ink, fontSize: 11 }} stroke={ink} />
          <YAxis domain={["auto", "auto"]} width={44} tick={{ fill: ink, fontSize: 11 }} stroke={ink}
            label={{ value: meta.units, angle: -90, position: "insideLeft", fill: ink, fontSize: 11 }} />
          <Tooltip contentStyle={tip} formatter={fmt} />
          {results.map((_, k) => <Line key={k} dataKey={`s${k}`} name={`Location ${k + 1}`} dot={false} stroke={LOC_COLORS[k]} strokeWidth={1.3} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
      <p className="note">Anomalies from each location's own calendar-month mean, for plotting only.</p>

      <table className="cmp">
        <thead><tr><th>Location</th><th>Trend / decade</th><th>95% CI</th><th>Evidence</th></tr></thead>
        <tbody>
          {results.map((r, k) => (
            <tr key={k}>
              <td><i className="sw" style={{ background: LOC_COLORS[k] }} />{cells[k].lat}°, {cells[k].lon}°</td>
              <td>{f(r.slope_per_decade)}</td>
              <td>{exploratory || !r.ci_analytical ? "n/a" : `${f(r.ci_analytical[0])} to ${f(r.ci_analytical[1])}`}</td>
              <td>{exploratory ? "Exploratory" : SHORT[r.class] ?? r.class}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">Units: {meta.units}/decade.{exploratory && " Custom period or season: no evidence class."}</p>

      <h3>Is the trend different from location 1?</h3>
      {err && <p className="error">{err}</p>}
      {!cmp && !err && <p className="hint">Computing paired bootstrap…</p>}
      {cmp && (
        <table className="cmp">
          <thead><tr><th>Location</th><th>Δ trend / decade</th><th>95% interval</th><th>Verdict</th></tr></thead>
          <tbody>
            {cmp.pairs.map((p, k) => (
              <tr key={k}>
                <td><i className="sw" style={{ background: LOC_COLORS[k + 1] }} />{k + 2}</td>
                {p.delta == null || !p.ci ? <td colSpan={3} className="verdict-no">{p.reason ?? "not available"}</td> : (<>
                  <td>{f(p.delta)}</td>
                  <td>{f(p.ci[0])} to {f(p.ci[1])}</td>
                  <td className={p.differs ? "verdict-yes" : "verdict-no"}>{p.differs ? "Differs" : "No detectable difference"}</td>
                </>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">
        Δ = trend at the location minus trend at location 1, in {meta.units}/decade. Paired year-block bootstrap (B = {cmp?.B ?? 1000}, block length {cmp?.block_length ?? 3} years,).
        {custom && " Always computed on the full period and whole year, whatever the time frame selected above."}
      </p>
      {cmp?.pairs.some(p => p.ci_by_L) && (
        <details><summary>Block-length sensitivity</summary>
          <ul>{cmp.pairs.map((p, k) => p.ci_by_L && (
            <li key={k}>Location {k + 2}: {Object.entries(p.ci_by_L).map(([L, c]) => `L=${L}: ${f(c[0])} to ${f(c[1])}`).join(" · ")}</li>))}
          </ul>
        </details>
      )}
    </div>
  );
}

function annual(r: SeriesResult) {
  const by: Record<string, number[]> = {};
  r.dates.forEach((d, i) => { const v = r.anomalies[i]; if (v != null) (by[d.slice(0, 4)] ||= []).push(v); });
  return by;
}

export function JointPanel({ joint, busy, err }: { joint: Joint | null; busy: boolean; err: string }) {
  const data = useMemo(() => {
    if (!joint) return [];
    const a = annual(joint.a), b = annual(joint.b), mean = (x?: number[]) => (x && x.length === 12 ? x.reduce((s, v) => s + v, 0) / 12 : null);
    return Object.keys(a).sort().map(y => ({ y, a: mean(a[y]), b: mean(b[y]) }));
  }, [joint]);
  if (err) return <p className="error">{err}</p>;
  if (busy || !joint) return <p className="hint">Analysing both variables…</p>;
  const { a, b, association: s } = joint;
  const row = (label: string, p: { rho: number; ci: [number, number] }) => (
    <tr><td>{label}</td><td>{f(p.rho)}</td><td>{f(p.ci[0])} to {f(p.ci[1])}</td></tr>
  );
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Two variables at {joint.lat}°, {joint.lon}°</h3>
      <table className="cmp">
        <thead><tr><th>Variable</th><th>Trend / decade</th><th>Evidence</th></tr></thead>
        <tbody>
          {[a, b].map((v, k) => (
            <tr key={v.id}>
              <td><i className="sw" style={{ background: LOC_COLORS[k] }} />{v.name}</td>
              <td>{f(v.slope_per_decade)} {v.units}</td>
              <td>{SHORT[v.class] ?? v.class}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ left: 0, right: 0, top: 10 }}>
          <CartesianGrid stroke="#1c2835" />
          <XAxis dataKey="y" minTickGap={24} tick={{ fill: ink, fontSize: 11 }} stroke={ink} />
          <YAxis yAxisId="a" domain={["auto", "auto"]} width={44} tick={{ fill: LOC_COLORS[0], fontSize: 11 }} stroke={LOC_COLORS[0]} />
          <YAxis yAxisId="b" orientation="right" domain={["auto", "auto"]} width={44} tick={{ fill: LOC_COLORS[1], fontSize: 11 }} stroke={LOC_COLORS[1]} />
          <Tooltip contentStyle={tip} formatter={fmt} />
          <Line yAxisId="a" dataKey="a" name={`${a.name} (${a.units})`} dot={false} stroke={LOC_COLORS[0]} strokeWidth={1.6} isAnimationActive={false} />
          <Line yAxisId="b" dataKey="b" name={`${b.name} (${b.units})`} dot={false} stroke={LOC_COLORS[1]} strokeWidth={1.6} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="note">Annual mean anomalies, each variable on its own axis (left: {a.units}, right: {b.units}).</p>

      <h3>Year-to-year association</h3>
      {s ? (
        <table className="cmp">
          <thead><tr><th>Computed on</th><th>Spearman ρ</th><th>95% interval</th></tr></thead>
          <tbody>
            {row("Annual anomalies (includes shared trends)", s.raw)}
            {row("Trend removed from each (year-to-year only)", s.detrended)}
          </tbody>
        </table>
      ) : <p className="note">{joint.association_reason}</p>}
      {s && <p className="note">{s.n_years} paired years, lag 0. Paired year-block bootstrap (B = {s.B}, block length {s.block_length}).</p>}

      <h3>What this suggests</h3>
      <p className="explain implication">{joint.implication}</p>
      {joint.note && <p className="note">{joint.note}</p>}
    </div>
  );
}