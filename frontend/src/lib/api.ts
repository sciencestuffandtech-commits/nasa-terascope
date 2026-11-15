export type Status = 0 | 1 | 2;
export type Season = "All" | "DJF" | "MAM" | "JJA" | "SON";
export type EvidenceClass =
  | "Robustly detectable trend" | "Probable trend" | "Uncertain trend"
  | "No statistically detectable trend" | "Insufficient data";
export interface VarMeta {
  id: string; name: string; units: string; dataset: string; version: string; doi: string; grid: string;
  period: [string, string]; tier: 1 | 2 | 3; limitations: string[]; discontinuities: string[];
}
export interface MapData {
  var: string; lat: number[]; lon: number[];
  slope_per_decade: (number | null)[][]; q_value: (number | null)[][]; status: Status[][];
}
export interface Sel { start: number; end: number; season: Season }
export interface SeriesResult {
  dates: string[]; values: (number | null)[]; anomalies: (number | null)[];
  valid_pct: number; slope_per_decade: number;
  ci_analytical: [number, number]; ci_bootstrap?: [number, number];
  p: number; q: number | null;
  windows: { start: number; slope: number }[];
  f_sign: number; c4: boolean; c5: boolean;
  class: EvidenceClass; explanation: string; provenance: Record<string, string>;
  by_season?: Record<string, number | null>; // slope per decade for All/DJF/MAM/JJA/SON over the selected years
  custom?: boolean;                          // true when the selection differs from the default period/season
}

export interface Cell { lat: number; lon: number }
export const LOC_COLORS = ["#5fc3ff", "#f07d1e", "#7bd88f", "#e879f9"];   // max 4 locations
export const MAX_LOCS = LOC_COLORS.length;

export interface PairDelta {
  lat: number; lon: number; delta: number | null; ci: [number, number] | null;
  ci_by_L: Record<string, [number, number]> | null; differs: boolean | null; reason?: string;
}
export interface CompareResult { var: string; block_length: number; B: number; pairs: PairDelta[] }
export interface AssocPart { rho: number; ci: [number, number] }
export interface Association { n_years: number; block_length: number; B: number; raw: AssocPart; detrended: AssocPart }
export type JointSeries = SeriesResult & { id: string; name: string; units: string };
export interface Joint {
  lat: number; lon: number; a: JointSeries; b: JointSeries;
  association: Association | null; association_reason: string | null; implication: string; note: string | null;
}

export type BvarDirKey = "pt" | "tp";
export type BvarSrc = "precip" | "soil";
export interface BvarMap {
  var: string; lat: number[]; lon: number[];
  pt_median: (number | null)[][]; pt_excl0: (number | null)[][]; tp_median: (number | null)[][]; tp_excl0: (number | null)[][];
}
export interface BvarDirStat { median: number; lo: number; hi: number; excludes_zero: boolean }
export interface BvarCell { lat: number; lon: number; eligible: boolean; reason?: string; pt?: BvarDirStat; tp?: BvarDirStat; forecast_gain?: number | null }
export interface BvarSet {
  n: number; frac_PtoT_excl0: number; frac_PtoT_negative: number; frac_PtoT_positive: number;
  frac_TtoP_excl0: number; frac_TtoP_negative: number; frac_TtoP_positive: number;
}
export interface BvarSummary {
  hypothesis?: string; note?: string;
  calibration?: { rate_PtoT_excl0: number; rate_TtoP_excl0: number; expected: number; pass_window: [number, number]; passed: boolean } | null;
  sets: Record<string, BvarSet | null | undefined>;
  null: { n_reps: number; PtoT_excl0: [number, number] | null; PtoT_negative: [number, number] | null } | null;
}

export const USE_FIXTURES = false;
export const SEASONS: Season[] = ["All", "DJF", "MAM", "JJA", "SON"];
export const DEFAULT_SEL: Sel = { start: 2001, end: 2025, season: "All" };
const API = "http://localhost:8000";
const j = <T,>(u: string) =>
  fetch(u).then(r => { if (!r.ok) throw new Error(`${r.status} ${u}`); return r.json() as Promise<T>; });

export const getMeta = () => j<{ variables: VarMeta[] }>(USE_FIXTURES ? "/fixtures/meta.json" : `${API}/meta`);
export const getMap = (v: string) => j<MapData>(USE_FIXTURES ? `/fixtures/map_${v}.json` : `${API}/map?var=${v}`);
export const getSeries = async (v: string, lat: number, lon: number, s: Sel) =>
  USE_FIXTURES
    ? applySel(await j<SeriesResult>(`/fixtures/series_${v}.json`), s)
    : j<SeriesResult>(`${API}/series?var=${v}&lat=${lat}&lon=${lon}&start=${s.start}&end=${s.end}&season=${s.season}`);

const noFixtures = () => Promise.reject(new Error("not available in fixture mode"));
export const getCompare = (v: string, cells: Cell[]) =>
  USE_FIXTURES ? noFixtures() : j<CompareResult>(`${API}/compare?var=${v}&${cells.map(c => `lat=${c.lat}&lon=${c.lon}`).join("&")}`);
export const getJoint = (a: string, b: string, lat: number, lon: number) =>
  USE_FIXTURES ? noFixtures() : j<Joint>(`${API}/joint?var_a=${a}&var_b=${b}&lat=${lat}&lon=${lon}`);
export const getBvarMap = (src: BvarSrc = "precip") => (USE_FIXTURES ? noFixtures() : j<BvarMap>(`${API}/bvar/map?src=${src}`));
export const getBvarCell = (lat: number, lon: number, src: BvarSrc = "precip") => (USE_FIXTURES ? noFixtures() : j<BvarCell>(`${API}/bvar/cell?lat=${lat}&lon=${lon}&src=${src}`));
export const getBvarSummary = (src: BvarSrc = "precip") => (USE_FIXTURES ? noFixtures() : j<BvarSummary>(`${API}/bvar/summary?src=${src}`));

const MONTHS: Record<Season, number[]> = {
  All: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], DJF: [12, 1, 2], MAM: [3, 4, 5], JJA: [6, 7, 8], SON: [9, 10, 11],
};
function sen(dates: string[], vals: (number | null)[]): number | null {
  const by: Record<number, { t: number; v: number }[]> = {};
  dates.forEach((d, i) => { const v = vals[i]; if (v == null) return; (by[+d.slice(5, 7)] ||= []).push({ t: +d.slice(0, 4), v }); });
  const sl: number[] = [];
  Object.values(by).forEach(a => { for (let i = 0; i < a.length; i++) for (let k = i + 1; k < a.length; k++)
    if (a[k].t !== a[i].t) sl.push((a[k].v - a[i].v) / (a[k].t - a[i].t)); });
  if (!sl.length) return null;
  sl.sort((x, y) => x - y); const h = sl.length >> 1;
  return 10 * (sl.length % 2 ? sl[h] : (sl[h - 1] + sl[h]) / 2);
}
function applySel(b: SeriesResult, s: Sel): SeriesResult {
  const yi = b.dates.map((_, i) => i).filter(i => +b.dates[i].slice(0, 4) >= s.start && +b.dates[i].slice(0, 4) <= s.end);
  const by: Record<string, number | null> = {};
  SEASONS.forEach(k => { const ix = yi.filter(i => MONTHS[k].includes(+b.dates[i].slice(5, 7)));
    by[k] = sen(ix.map(i => b.dates[i]), ix.map(i => b.values[i])); });
  const custom = s.start !== DEFAULT_SEL.start || s.end !== DEFAULT_SEL.end || s.season !== "All";
  if (!custom) by.All = b.slope_per_decade;
  const ix = yi.filter(i => MONTHS[s.season].includes(+b.dates[i].slice(5, 7)));
  return { ...b, dates: ix.map(i => b.dates[i]), values: ix.map(i => b.values[i]), anomalies: ix.map(i => b.anomalies[i]),
    slope_per_decade: custom ? (by[s.season] ?? NaN) : b.slope_per_decade, by_season: by, custom };
}