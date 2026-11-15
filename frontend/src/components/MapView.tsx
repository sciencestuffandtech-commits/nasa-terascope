import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { LOC_COLORS } from "../lib/api";
import type { MapData, Cell } from "../lib/api";

const mix = (a: number[], b: number[], t: number) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
const MID = [38, 48, 60]; // near-zero cells blend into the dark map on purpose
const PAL: Record<string, { neg: number[]; pos: number[] }> = {
  default: { neg: [56, 128, 201], pos: [240, 125, 30] },
  precip: { neg: [191, 129, 45], pos: [53, 151, 143] },
};
const pal = (v: string) => PAL[v] ?? PAL.default;
const rgb = (c: number[]) => `rgb(${c.join(",")})`;
const color = (s: number, m: number, v: string) => {
  const t = Math.max(-1, Math.min(1, s / m)), P = pal(v);
  return `rgb(${(t < 0 ? mix(MID, P.neg, -t) : mix(MID, P.pos, t)).join(",")})`;
};
const nearest = (a: number[], v: number) => a.reduce((b, x) => (Math.abs(x - v) < Math.abs(b - v) ? x : b));

function build(d: MapData) {
  const step = Math.abs(d.lat[1] - d.lat[0]), h = step / 2;
  const abs: number[] = [];
  d.slope_per_decade.forEach(r => r.forEach(v => { if (v != null) abs.push(Math.abs(v)); }));
  abs.sort((a, b) => a - b);
  const m = Math.max(1e-9, abs.length ? abs[Math.min(abs.length - 1, Math.floor(abs.length * 0.98))] : 1e-9);
  const cells: any[] = [], dots: any[] = [];
  d.lat.forEach((la, i) => d.lon.forEach((lo, j) => {
    const st = d.status[i][j], s = d.slope_per_decade[i][j], q = d.q_value[i][j];
    const c = st === 1 ? "#5b6672" : st === 2 ? "#9aa5b1" : s == null ? "rgba(0,0,0,0)" : color(s, m, d.var);
    cells.push({ type: "Feature", properties: { c }, geometry: { type: "Polygon",
      coordinates: [[[lo - h, la - h], [lo + h, la - h], [lo + h, la + h], [lo - h, la + h], [lo - h, la - h]]] } });
    if (st === 0 && q != null && q <= 0.10) // stippling: BH-FDR q <= 0.10 on valid cells only
      dots.push({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [lo, la] } });
  }));
  return { cells: { type: "FeatureCollection", features: cells }, dots: { type: "FeatureCollection", features: dots }, m };
}

export default function MapView({ data, cells, active, onSelect, onReady, units }: {
  data: MapData | null; units?: string; cells: Cell[]; active: number;
  onSelect: (c: { lat: number; lon: number }) => void;
  onReady: (snapshot: () => Promise<string | null>) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const mp = useRef<maplibregl.Map | null>(null);
  const mks = useRef<maplibregl.Marker[]>([]);
  const dref = useRef<MapData | null>(null); dref.current = data;
  const sel = useRef(onSelect); sel.current = onSelect;
  const scale = useRef(1);

  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!, center: [20, 20], zoom: 1.6, attributionControl: { compact: true },
      style: { version: 8, sources: { b: { type: "raster", tileSize: 256,
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], attribution: "© OpenStreetMap contributors" } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#06090f" } },
          { id: "b", type: "raster", source: "b",
            paint: { "raster-brightness-min": 0.7, "raster-brightness-max": 0.04, "raster-saturation": -0.7 } }] },
    });
    m.on("click", (e: maplibregl.MapMouseEvent) => {
      const d = dref.current; if (!d) return;
      sel.current({ lat: nearest(d.lat, e.lngLat.lat), lon: nearest(d.lon, e.lngLat.lng) });
    });
    onReady(() => new Promise(res => {
      m.once("render", () => { try { res(m.getCanvas().toDataURL("image/png")); } catch { res(null); } });
      m.triggerRepaint();
    }));
    mp.current = m;
    return () => m.remove();
  }, []);

  useEffect(() => {
    const m = mp.current; if (!m || !data) return;
    const b = build(data); scale.current = b.m;
    const apply = () => {
      (["cells", "dots"] as const).forEach(id => {
        const s = m.getSource(id) as maplibregl.GeoJSONSource | undefined;
        if (s) s.setData(b[id] as any); else m.addSource(id, { type: "geojson", data: b[id] as any });
      });
      if (!m.getLayer("cells")) m.addLayer({ id: "cells", type: "fill", source: "cells", paint: { "fill-color": ["get", "c"], "fill-opacity": 0.85 } });
      if (!m.getLayer("dots")) m.addLayer({ id: "dots", type: "circle", source: "dots", paint: { "circle-radius": 1.5, "circle-color": "#e8f3fb" } });
    };
    try { apply(); } catch { m.once("load", apply); }
  }, [data]);

  useEffect(() => {
    const m = mp.current; if (!m) return;
    mks.current.forEach(k => k.remove()); mks.current = [];
    cells.forEach((c, i) => mks.current.push(new maplibregl.Marker({ color: LOC_COLORS[i % LOC_COLORS.length] }).setLngLat([c.lon, c.lat]).addTo(m)));
    const a = cells[active];
    if (a) m.easeTo({ center: [a.lon, a.lat], duration: 700 });
  }, [cells, active]);

  const bv = !!data?.var?.startsWith("bvar");
  return (
    <>
      <div ref={el} className="map" />
      <div className="legend">
        <div className="ramp" style={{ background: `linear-gradient(90deg,${rgb(pal(data?.var ?? "").neg)},#26303c,${rgb(pal(data?.var ?? "").pos)})` }} />
        {bv ? (<>
          <div className="ramp-labels"><span>negative</span><span>± {scale.current.toPrecision(2)} SD per SD (98th pct)</span><span>positive</span></div>
          <p>BVAR: cumulative lag coefficient, {data?.var?.startsWith("bvar:tp") ? `temperature → later ${data.var.endsWith(":soil") ? "soil moisture" : "precipitation"}` : `${data?.var?.endsWith(":soil") ? "soil moisture" : "precipitation"} → later temperature`}.</p>
          <p><i className="dot" /> 90% credible interval excludes zero (no multiple-testing control; about 10% expected by chance)</p>
        </>) : (<>
          <div className="ramp-labels"><span>decrease</span><span>± {scale.current.toPrecision(2)} {units ?? ""} per decade (98th pct)</span><span>increase</span></div>
          <p><i className="dot" /> significant after false-discovery-rate control (q ≤ 0.10)</p>
          <p><i style={{ background: "#5b6672" }} /> insufficient data <i style={{ background: "#9aa5b1" }} /> insufficient variability</p>
        </>)}
      </div>
    </>
  );
}