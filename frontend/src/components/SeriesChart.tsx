import { cloneElement, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import type { SeriesResult } from "../lib/api";

export default function SeriesChart({ r, units, width, light }: { r: SeriesResult; units: string; width?: number; light?: boolean }) {
  const [mode, setMode] = useState<"values" | "anomalies">("values");
  const [showTrend, setShowTrend] = useState(true);
  const y = r[mode];
  const vs = y.filter((v): v is number => v != null);
  const mean = vs.reduce((a, b) => a + b, 0) / vs.length;
  const yr = (d: string) => +d.slice(0, 4) + (+d.slice(5, 7) - 0.5) / 12;
  const tm = r.dates.reduce((a, d) => a + yr(d), 0) / r.dates.length;
  const data = r.dates.map((d, i) => ({ d, y: y[i], trend: Number.isFinite(r.slope_per_decade) ? mean + (r.slope_per_decade / 10) * (yr(d) - tm) : null }));
  const ink = light ? "#444" : "#7f93a5";
  const chart = (
    <LineChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
      <CartesianGrid stroke={light ? "#ddd" : "#1c2835"} />
      <XAxis dataKey="d" minTickGap={48} tick={{ fill: ink, fontSize: 11 }} stroke={ink} />
      <YAxis domain={["auto", "auto"]} width={44} tick={{ fill: ink, fontSize: 11 }} stroke={ink}
        label={{ value: units, angle: -90, position: "insideLeft", fill: ink, fontSize: 11 }} />
      {!width && <Tooltip contentStyle={{ background: "#0b1119", border: "1px solid #1c2835" }} formatter={(v: any) => (typeof v === "number" ? v.toFixed(2) : v)} />}
      <Line dataKey="y" name={mode === "values" ? "Observed" : "Anomaly"} dot={false} stroke={light ? "#0b6fa8" : "#5fc3ff"} strokeWidth={1.4} isAnimationActive={false} />
      {showTrend && <Line dataKey="trend" name="Trend (display)" dot={false} stroke={light ? "#c2410c" : "#f07d1e"} strokeDasharray="6 4" strokeWidth={2} isAnimationActive={false} />}
    </LineChart>
  );
  return (
    <div>
      {!width && (
        <div className="toggle">
          <button className={mode === "values" ? "on" : ""} onClick={() => setMode("values")}>Observed</button>
          <button className={mode === "anomalies" ? "on" : ""} onClick={() => setMode("anomalies")}>Anomalies</button>
          <label><input type="checkbox" checked={showTrend} onChange={e => setShowTrend(e.target.checked)} /> Trend line</label>
        </div>
      )}
      {width ? cloneElement(chart, { width, height: 220 }) : <ResponsiveContainer width="100%" height={230}>{chart}</ResponsiveContainer>}
    </div>
  );
}
