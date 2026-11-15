from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | str = ROOT / "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_ym(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


@dataclass
class Product:
    id: str
    data: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    years: np.ndarray
    months: np.ndarray
    meta: dict = field(default_factory=dict)

    @property
    def n_years(self) -> int:
        return len(np.unique(self.years))


def open_raw(path: Path | str, variable: str, date_regex: str | None = None):
    import xarray as xr
    ds = xr.open_dataset(path)
    if variable not in ds.variables:
        raise KeyError(f"variable '{variable}' not in {path}. Available: {list(ds.data_vars)}")
    da = ds[variable]
    tname = next((n for n in ("time", "Time", "t") if n in da.dims), None)
    latn = next((n for n in ("lat", "latitude", "Latitude") if n in da.dims), None)
    lonn = next((n for n in ("lon", "longitude", "Longitude") if n in da.dims), None)
    if not (latn and lonn):
        raise ValueError(f"expected lat/lon dims, got {da.dims}")
    if tname:
        da = da.transpose(tname, latn, lonn)
        years = da[tname].dt.year.values.astype(int)
        months = da[tname].dt.month.values.astype(int)
        vals = da.values.astype("float32")
    else:
        if not date_regex:
            raise ValueError(f"{path} has no time dimension; set date_regex in config.yaml to read the month from the filename")
        m = re.search(date_regex, Path(path).name)
        if not m:
            raise ValueError(f"date_regex {date_regex!r} did not match filename {Path(path).name}")
        g = m.groups()
        y, mo = (int(g[0][:4]), int(g[0][4:6])) if len(g) == 1 else (int(g[0]), int(g[1]))
        da = da.transpose(latn, lonn)
        vals = da.values.astype("float32")[None]
        years, months = np.array([y]), np.array([mo])
    attrs = {"global": dict(ds.attrs), "variable": dict(da.attrs), "dims": list(da.dims)}
    lat, lon = da[latn].values.astype(float), da[lonn].values.astype(float)
    ds.close()
    return vals, lat, lon, years, months, attrs


def list_files(p: dict) -> list[Path]:
    if p.get("files"):
        return sorted(ROOT.glob(p["files"]))
    return [ROOT / p["file"]]


def standardise(vals, lat, lon, valid_range=None):
    vals = np.array(vals, dtype="float32", copy=True)
    if valid_range is not None:
        lo, hi = valid_range
        vals[(vals < lo) | (vals > hi)] = np.nan
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    lon = np.where(lon > 180, lon - 360, lon)
    li, oi = np.argsort(lat), np.argsort(lon)
    return vals[:, li][:, :, oi], lat[li], lon[oi]


def crop_period(vals, years, months, start: str, end: str):
    (y0, m0), (y1, m1) = parse_ym(start), parse_ym(end)
    idx = lambda y, m: y * 12 + m - 1
    n = idx(y1, m1) - idx(y0, m0) + 1
    out = np.full((n,) + vals.shape[1:], np.nan, dtype="float32")
    pos = idx(years, months) - idx(y0, m0)
    keep = (pos >= 0) & (pos < n)
    out[pos[keep]] = vals[keep]
    t = idx(y0, m0) + np.arange(n)
    return out, t // 12, t % 12 + 1


def months_with_data(vals, years, months):
    return np.isfinite(vals).reshape(len(vals), -1).any(axis=1)


def last_complete_year(vals, years, months) -> int | None:
    ok = months_with_data(vals, years, months)
    done = [int(y) for y in np.unique(years) if ok[years == y].sum() == 12 and (months[years == y] == np.arange(1, 13)).all()]
    return max(done) if done else None


def common_period(products_raw: dict[str, tuple], start: str, end: str, min_years: int):
    y0, y1 = parse_ym(start)[0], parse_ym(end)[0]
    firsts, lasts = [], []
    for vals, years, months in products_raw.values():
        ok = months_with_data(vals, years, months)
        cy = [int(y) for y in np.unique(years) if ok[years == y].sum() == 12]
        if not cy:
            return None
        firsts.append(min(cy)); lasts.append(max(cy))
    lo, hi = max(firsts), min(lasts)
    if lo <= y0 and hi >= y1:
        return start, end
    hi2 = min(hi, y1); lo2 = max(lo, hi2 - (y1 - y0))
    return (f"{lo2}-01", f"{hi2}-12") if hi2 - lo2 + 1 >= min_years else None


def choose_block_factor(nlat: int, nlon: int, cap: int) -> int:
    for f in range(1, min(nlat, nlon) + 1):
        if nlat % f == 0 and nlon % f == 0 and (nlat // f) * (nlon // f) <= cap:
            return f
    raise ValueError(f"no integer block factor brings {nlat}x{nlon} under {cap} cells")


def block_average(vals, lat, lon, f: int, min_valid_fraction: float):
    if f == 1:
        return vals, lat, lon
    T, Y, X = vals.shape
    w = np.cos(np.deg2rad(lat))[None, :, None] * np.ones((1, 1, X))
    fin = np.isfinite(vals)
    num = np.where(fin, vals, 0.0) * w
    den = fin * w
    blk = lambda a: a.reshape(T, Y // f, f, X // f, f).sum(axis=(2, 4))
    wtot = (w[0].reshape(Y // f, f, X // f, f)).sum(axis=(1, 3))[None]
    n, d = blk(num), blk(den)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(d / wtot >= min_valid_fraction, n / d, np.nan).astype("float32")
    return out, lat.reshape(-1, f).mean(1), lon.reshape(-1, f).mean(1)


def apply_units(vals, p: dict):
    sc, off = p.get("scale", 1), p.get("offset", 0)
    return vals if (sc == 1 and off == 0) else (vals * sc + off).astype("float32")


def prepare_slice(vals, lat, lon, p: dict, cfg: dict, factor: int | None = None):
    vals = apply_units(vals, p)
    vals, lat, lon = standardise(vals, lat, lon, p.get("valid_range"))
    f = factor or choose_block_factor(len(lat), len(lon), cfg["grid_cap_cells"])
    vals, lat, lon = block_average(vals, lat, lon, f, cfg["block_average_min_valid_fraction"])
    return vals, lat, lon, f


def concat_time(parts):
    lat0, lon0 = parts[0][1], parts[0][2]
    for k, (_, la, lo, _, _) in enumerate(parts):
        if la.shape != lat0.shape or lo.shape != lon0.shape or not (np.allclose(la, lat0) and np.allclose(lo, lon0)):
            raise ValueError(f"slice {k} is on a different grid from slice 0; cannot stack")
    vals = np.concatenate([q[0] for q in parts]); years = np.concatenate([q[3] for q in parts]); months = np.concatenate([q[4] for q in parts])
    key = years * 12 + months - 1
    u, c = np.unique(key, return_counts=True)
    if (c > 1).any():
        d = [f"{k // 12}-{k % 12 + 1:02d}" for k in u[c > 1]]
        raise ValueError(f"duplicate months in input files: {d[:6]}")
    o = np.argsort(key)
    return vals[o], lat0, lon0, years[o], months[o]


def load_product(pid: str, cfg: dict | None = None, require_locked: bool = True) -> Product:
    cfg = cfg or load_config()
    p = cfg["products"][pid]
    if not p.get("enabled", True):
        raise RuntimeError(f"[{pid}] is disabled in config.yaml (enabled: false). Enable it only after the core two products work.")
    if not p.get("variable"):
        raise RuntimeError(f"[{pid}] variable is not set in config.yaml (VERIFY against the file; lock_products lists the real names).")
    if require_locked:
        missing = [k for k in ("version", "doi", "url", "discontinuity_registry") if not p.get(k)]
        if missing:
            raise RuntimeError(f"[{pid}] config.yaml still has VERIFY fields unset: {missing}. "
                               "Fill them from the product documentation (Addendum A Sec 0 and 2), "
                               "or call load_product(..., require_locked=False) while exploring.")
    files = [f for f in list_files(p) if f.exists()]
    if not files:
        raise FileNotFoundError(f"[{pid}] no files found for {p.get('files') or p.get('file')}. See data/README.md.")
    start, end = cfg["period"]["start"], cfg["period"]["end"]
    (y0, m0), (y1, m1) = parse_ym(start), parse_ym(end)
    k0, k1 = y0 * 12 + m0 - 1, y1 * 12 + m1 - 1
    parts, f, native, span = [], None, None, [10**9, -10**9]
    for path in files:
        v, la, lo, y, m, _ = open_raw(path, p["variable"], p.get("date_regex"))
        key = y * 12 + m - 1
        span = [min(span[0], int(y.min())), max(span[1], int(y.max()))]
        keep = (key >= k0) & (key <= k1)
        if not keep.any():
            continue
        v, y, m = v[keep], y[keep], m[keep]
        native = native or (len(la), len(lo))
        v, la, lo, f = prepare_slice(v, la, lo, p, cfg, f)
        parts.append((v, la, lo, y, m))
    if not parts:
        raise RuntimeError(f"[{pid}] none of the {len(files)} file(s) overlap {start}..{end} (files span {span[0]}..{span[1]}).")
    vals, lat, lon, years, months = concat_time(parts)
    vals, years, months = crop_period(vals, years, months, start, end)
    have = months_with_data(vals, years, months)
    if not have.all():
        gaps = [f"{yy}-{mm:02d}" for yy, mm, h in zip(years, months, have) if not h]
        raise RuntimeError(f"[{pid}] no data at all for {len(gaps)} month(s) in {start}..{end}: {gaps[:6]}... "
                           f"(files span {span[0]}..{span[1]}). Per Addendum Sec 2, use common_period() and update config.yaml; "
                           "the period is never shrunk silently.")
    step = abs(float(lat[1] - lat[0]))
    n_years = len(np.unique(years))
    meta = {
        "id": pid, "name": p["name"], "units": p["units"], "dataset": p["dataset"], "version": p.get("version"),
        "doi": p.get("doi"), "url": p.get("url"), "grid": f"{step:g}°", "native_shape": list(native),
        "block_factor": f, "period": [start, end], "tier": 1 if n_years >= cfg["min_record_years_tier1"] else 3,
        "limitations": list(p.get("limitations", [])), "discontinuities": [p["discontinuity_registry"]] if p.get("discontinuity_registry") else [],
        "source_files": len(files),
    }
    if f > 1:
        meta["limitations"].append(f"Block-averaged once from {native[0]}x{native[1]} to {len(lat)}x{len(lon)} (area-weighted) to respect the grid cap.")
    return Product(pid, vals, lat, lon, years, months, meta)
