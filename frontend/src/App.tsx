import { useEffect, useMemo, useRef, useState } from "react";
import { getMeta, getMap, getSeries, getJoint, getBvarMap, getBvarCell, getBvarSummary, USE_FIXTURES, DEFAULT_SEL, SEASONS, LOC_COLORS, MAX_LOCS } from "./lib/api";
import type { VarMeta, MapData, SeriesResult, Sel, Cell, Joint, BvarMap, BvarCell, BvarSummary, BvarDirKey, BvarSrc } from "./lib/api";
import MapView from "./components/MapView";
import SeriesChart from "./components/SeriesChart";
import ResultCard, { LABEL } from "./components/ResultCard";
import Report from "./components/Report";
import BvarPanel from "./components/BvarPanel";
import { ComparePanel, JointPanel } from "./components/Multi.tsx";
import "./styles.css";

const nearest = (a: number[], v: number) => a.reduce((b, x) => (Math.abs(x - v) < Math.abs(b - v) ? x : b));

export default function App() {
  const [metas, setMetas] = useState<VarMeta[]>([]);
  const [varId, setVarId] = useState("");
  const [map, setMap] = useState<MapData | null>(null);
  const [cells, setCells] = useState<Cell[]>([]);
  const [active, setActive] = useState(0);
  const [adding, setAdding] = useState(false);
  const [got, setGot] = useState<{ key: string; r: SeriesResult[] } | null>(null);
  const [varB, setVarB] = useState("");
  const [joint, setJoint] = useState<Joint | null>(null);
  const [jBusy, setJBusy] = useState(false);
  const [jErr, setJErr] = useState("");
  const [sel, setSel] = useState<Sel>(DEFAULT_SEL);
  const [latIn, setLatIn] = useState(""); const [lonIn, setLonIn] = useState(""); const [cErr, setCErr] = useState("");
  const [shot, setShot] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [bvarOn, setBvarOn] = useState(false);
  const [bvarDir, setBvarDir] = useState<BvarDirKey>("pt");
  const [bvarSrc, setBvarSrc] = useState<BvarSrc>("precip");
  const [bvarMap, setBvarMap] = useState<BvarMap | null>(null);
  const [bvarSum, setBvarSum] = useState<BvarSummary | null>(null);
  const [bvarCell, setBvarCell] = useState<BvarCell | null>(null);
  const [bvarErr, setBvarErr] = useState("");
  const snap = useRef<() => Promise<string | null>>(async () => null);
  const meta = metas.find(m => m.id === varId);
  const cell = cells[active] ?? null;
  const key = JSON.stringify([varId, cells, sel]);
  const results = got && got.key === key ? got.r : null;      // ignore results that belong to an older selection
  const res = results?.[active] ?? null;
  const y0 = meta ? +meta.period[0].slice(0, 4) : 2001, y1 = meta ? +meta.period[1].slice(0, 4) : 2025;
  const years = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i);
  const short = sel.end - sel.start + 1 < 20;
  const fail = (e: unknown) => setErr(String(e));
  const bvarView = useMemo<MapData | null>(() => {
    if (!bvarOn || !bvarMap) return null;
    const med = bvarDir === "pt" ? bvarMap.pt_median : bvarMap.tp_median, ex = bvarDir === "pt" ? bvarMap.pt_excl0 : bvarMap.tp_excl0;
    return { var: `bvar:${bvarDir}:${bvarSrc}`, lat: bvarMap.lat, lon: bvarMap.lon, slope_per_decade: med,
      q_value: ex.map(r => r.map(v => (v == null ? null : v ? 0 : 1))), status: med.map(r => r.map(() => 0 as const)) };
  }, [bvarOn, bvarMap, bvarDir, bvarSrc]);

  useEffect(() => { getMeta().then(m => { setMetas(m.variables); setVarId(m.variables[0].id); }).catch(fail); }, []);
  useEffect(() => {
    if (!varId) return;
    setMap(null); setSel({ start: y0, end: y1, season: "All" });
    getMap(varId).then(m => {
      setMap(m);                                               // keep the chosen locations, snapped to this variable's grid
      setCells(cs => cs.map(c => ({ lat: nearest(m.lat, c.lat), lon: nearest(m.lon, c.lon) })));
    }).catch(fail);
  }, [varId]);
  useEffect(() => {
    if (!bvarOn) return;
    setBvarErr(""); setBvarMap(null); setBvarSum(null);
    getBvarMap(bvarSrc).then(setBvarMap).catch(e => setBvarErr(String(e)));
    getBvarSummary(bvarSrc).then(setBvarSum).catch(e => setBvarErr(String(e)));
  }, [bvarOn, bvarSrc]);
  useEffect(() => {
    if (!bvarOn || !cell) { setBvarCell(null); return; }
    let dead = false; setBvarCell(null);
    getBvarCell(cell.lat, cell.lon, bvarSrc).then(r => { if (!dead) setBvarCell(r); }).catch(e => { if (!dead) setBvarErr(String(e)); });
    return () => { dead = true; };
  }, [bvarOn, cell?.lat, cell?.lon, bvarSrc]);
  useEffect(() => { if (cell) { setLatIn(String(cell.lat)); setLonIn(String(cell.lon)); } }, [cell]);
  useEffect(() => {
    if (!cells.length || !varId) return;
    let dead = false;
    Promise.all(cells.map(c => getSeries(varId, c.lat, c.lon, sel)))
      .then(r => { if (!dead) setGot({ key, r }); }).catch(e => { if (!dead) fail(e); });
    return () => { dead = true; };
  }, [key]);
  useEffect(() => {
    setJoint(null); setJErr("");
    if (!varB || !cell || varB === varId) return;
    let dead = false; setJBusy(true);
    getJoint(varId, varB, cell.lat, cell.lon).then(r => { if (!dead) setJoint(r); })
      .catch(e => { if (!dead) setJErr(String(e)); }).finally(() => { if (!dead) setJBusy(false); });
    return () => { dead = true; };
  }, [varId, varB, cell?.lat, cell?.lon]);

  const pick = (c: Cell) => {
    if (adding || cells.length === 0) {
      const at = cells.findIndex(x => x.lat === c.lat && x.lon === c.lon);
      if (at >= 0) setActive(at); else { setCells([...cells, c]); setActive(cells.length); }
      setAdding(false);
    } else setCells(cells.map((x, i) => (i === active ? c : x)));
  };
  const removeCell = (i: number) => {
    setCells(cells.filter((_, k) => k !== i)); setActive(a => Math.max(0, a > i || a === cells.length - 1 ? a - 1 : a)); setAdding(false);
  };
  const go = () => {
    const la = parseFloat(latIn), lo = parseFloat(lonIn);
    if (!map || !isFinite(la) || !isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) {
      setCErr("Enter a latitude from -90 to 90 and a longitude from -180 to 180."); return;
    }
    setCErr(""); pick({ lat: nearest(map.lat, la), lon: nearest(map.lon, lo) });
  };
  const exportPdf = async () => { setShot(await snap.current()); setTimeout(() => window.print(), 300); };

  return (
    <div className="app">
      <div className="stage">
        <MapView data={bvarView ?? map} units={meta?.units} cells={cells} active={active} onSelect={pick} onReady={f => { snap.current = f; }} />
        {USE_FIXTURES && <div className="pill">Fixture data: synthetic, not NASA observations</div>}
      </div>
      <aside className="side">
        <h1>Terrascope</h1>
        {err && <p className="error">Could not load data: {err}</p>}
        <label className="field">Variable
          <select value={varId} onChange={e => { setVarId(e.target.value); if (e.target.value === varB) setVarB(""); }}>{metas.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select>
        </label>
        {metas.length > 1 && (
          <label className="field" style={{ marginTop: 8 }}>Compare with a second variable
            <select value={varB} onChange={e => setVarB(e.target.value)}>
              <option value="">None</option>
              {metas.filter(m => m.id !== varId).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </label>
        )}

        <label className="field" style={{ marginTop: 8, flexDirection: "row", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={bvarOn} onChange={e => setBvarOn(e.target.checked)} style={{ width: "auto" }} />
          Show BVAR layer (lagged association with temperature)
        </label>
        {bvarOn && (<>
          <label className="field" style={{ marginTop: 8 }}>Second variable
            <select value={bvarSrc} onChange={e => setBvarSrc(e.target.value as BvarSrc)}>
              <option value="precip">Precipitation</option>
              <option value="soil">Soil moisture (0-10 cm)</option>
            </select>
          </label>
          <label className="field" style={{ marginTop: 8 }}>Direction shown on the map
            <select value={bvarDir} onChange={e => setBvarDir(e.target.value as BvarDirKey)}>
              <option value="pt">{bvarSrc === "soil" ? "Soil moisture" : "Precipitation"} → later temperature</option>
              <option value="tp">Temperature → later {bvarSrc === "soil" ? "soil moisture" : "precipitation"}</option>
            </select>
          </label>
          <BvarPanel dir={bvarDir} src={bvarSrc} cell={bvarCell} sum={bvarSum} err={bvarErr} hasCell={!!cell} />
        </>)}

        <h3>Locations</h3>
        <div className="locs">
          {cells.map((c, i) => (
            <span key={`${c.lat},${c.lon}`} className={"loc" + (i === active ? " on" : "")}>
              <button onClick={() => setActive(i)}><i style={{ background: LOC_COLORS[i] }} />{c.lat}°, {c.lon}°</button>
              <button className="x" aria-label={`Remove location ${i + 1}`} onClick={() => removeCell(i)}>×</button>
            </span>
          ))}
          <button className={adding ? "on" : ""} disabled={cells.length >= MAX_LOCS && !adding} onClick={() => setAdding(a => !a)}>+ Location</button>
        </div>
        {adding && <p className="note">Click the map, or type coordinates and press Go, to add location {cells.length + 1} (max {MAX_LOCS}).</p>}
        <div className="row">
          <input aria-label="Latitude" placeholder="Latitude" value={latIn} onChange={e => setLatIn(e.target.value)} onKeyDown={e => e.key === "Enter" && go()} />
          <input aria-label="Longitude" placeholder="Longitude" value={lonIn} onChange={e => setLonIn(e.target.value)} onKeyDown={e => e.key === "Enter" && go()} />
          <button onClick={go}>Go</button>
        </div>
        {cErr ? <p className="error">{cErr}</p> : <p className="note">{cell ? `Active: ${meta?.grid} grid cell centred at ${cell.lat}°, ${cell.lon}°. Clicking the map moves it.` : "Type coordinates or click the map. Input snaps to the nearest grid cell."}</p>}

        <h3>Time frame</h3>
        <div className="row">
          <label className="field">From<select value={sel.start} onChange={e => setSel(s => ({ ...s, start: +e.target.value, end: Math.max(+e.target.value, s.end) }))}>{years.map(y => <option key={y}>{y}</option>)}</select></label>
          <label className="field">To<select value={sel.end} onChange={e => setSel(s => ({ ...s, end: +e.target.value, start: Math.min(+e.target.value, s.start) }))}>{years.map(y => <option key={y}>{y}</option>)}</select></label>
        </div>
        <div className="chips">{SEASONS.map(k => <button key={k} className={sel.season === k ? "on" : ""} onClick={() => setSel(s => ({ ...s, season: k }))}>{LABEL[k]}</button>)}</div>
        {(sel.start !== y0 || sel.end !== y1 || sel.season !== "All") && <p className="note"><a href="#" onClick={e => { e.preventDefault(); setSel({ start: y0, end: y1, season: "All" }); }}>Reset to full period</a></p>}

        {!cell && <p className="hint">Pick a location to see its time series, trend and evidence.</p>}
        {cell && !res && <p className="hint">Loading…</p>}
        {results && meta && cells.length > 1 && (
          <ComparePanel varId={varId} meta={meta} cells={cells} results={results} exploratory={short || !!res?.custom} custom={!!res?.custom} />
        )}
        {res && meta && cell && (<>
          <h3><i className="sw" style={{ background: LOC_COLORS[active] }} />{meta.name} at {cell.lat}°, {cell.lon}°</h3>
          <SeriesChart r={res} units={meta.units} />
          <ResultCard r={res} meta={meta} sel={sel} short={short} onSeason={k => setSel(s => ({ ...s, season: k }))} onExport={exportPdf} />
        </>)}
        {varB && cell && <JointPanel joint={joint} busy={jBusy} err={jErr} />}
        {meta && (
          <details className="data">
            <summary>Data and limitations</summary>
            <p>{meta.dataset} {meta.version} ({meta.grid}), {meta.period[0]} to {meta.period[1]}. DOI: {meta.doi}</p>
            <p>{meta.limitations.join(" ")} {meta.discontinuities.join(" ")}</p>
          </details>
        )}
      </aside>
      {res && meta && cell && <Report r={res} meta={meta} cell={cell} sel={sel} short={short} shot={shot} />}
    </div>
  );
}