from __future__ import annotations
import json
from functools import lru_cache
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .pipeline.load import ROOT, load_config
from .pipeline.stats import seasonal_sen_per_year
from .pipeline.classify import classify, explain
from .pipeline.compare import paired_delta, association, implication

PROC = ROOT / "data" / "processed"
cfg = load_config()
MONTHS = {"All": list(range(1, 13)), "DJF": [12, 1, 2], "MAM": [3, 4, 5], "JJA": [6, 7, 8], "SON": [9, 10, 11]}
app = FastAPI(title="Earth System Trend Detective")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET"], allow_headers=["*"])
U = cfg["rate_unit_years"]
from .bvar_routes import router as bvar_router
app.include_router(bvar_router)


def _c(v):
    return None if v is None or not np.isfinite(v) else float(v)


@lru_cache(maxsize=8)
def _load(var: str):
    try:
        return dict(np.load(PROC / f"{var}_cube.npz")), dict(np.load(PROC / f"{var}_cells.npz"))
    except FileNotFoundError:
        raise HTTPException(404, f"no processed data for '{var}'. Run: python -m backend.pipeline.precompute {var}")


def _meta(var: str) -> dict:
    mp = PROC / "meta.json"
    if not mp.exists():
        raise HTTPException(404, "meta.json missing. Run precompute first.")
    m = next((v for v in json.loads(mp.read_text(encoding="utf-8"))["variables"] if v["id"] == var), None)
    if not m:
        raise HTTPException(404, f"unknown variable '{var}'")
    return m


def _sen(Xm):
    s = seasonal_sen_per_year(Xm)
    return s * U if np.isfinite(s) else None


def _season_matrix(Xs, season):
    keep = np.zeros(12, bool); keep[[m - 1 for m in MONTHS[season]]] = True
    Xm = Xs.copy(); Xm[:, ~keep] = np.nan
    return Xm


@app.get("/meta")
def meta():
    mp = PROC / "meta.json"
    if not mp.exists():
        raise HTTPException(404, "meta.json missing. Run precompute first.")
    return json.loads(mp.read_text(encoding="utf-8"))


@app.get("/map")
def map_(var: str):
    f = PROC / f"map_{var}.json"
    if not f.exists():
        raise HTTPException(404, f"no map for '{var}'. Run precompute first.")
    return FileResponse(f, media_type="application/json")


@app.get("/series")
def series(var: str, lat: float, lon: float, start: int | None = None, end: int | None = None, season: str = "All"):
    import pymannkendall as mk
    if season not in MONTHS:
        raise HTTPException(400, f"season must be one of {list(MONTHS)}")
    d, cl = _load(var); meta = _meta(var)
    i, j = int(np.abs(d["lat"] - lat).argmin()), int(np.abs(d["lon"] - lon).argmin())
    X = d["data"][:, i, j].astype(float).reshape(-1, 12); ny = len(X); y0 = int(d["years"][0]); y1 = y0 + ny - 1
    start, end = start or y0, end or y1
    if not (y0 <= start <= end <= y1):
        raise HTTPException(400, f"years must satisfy {y0} <= start <= end <= {y1}")
    custom = (start, end, season) != (y0, y1, "All")
    Xs = X[start - y0:end - y0 + 1]; clim = np.nanmean(X, axis=0)
    cols = [m - 1 for m in MONTHS[season]]
    dates, vals, anoms = [], [], []
    for r in range(len(Xs)):
        for c in range(12):
            if c in cols:
                dates.append(f"{start + r}-{c + 1:02d}"); vals.append(_c(Xs[r, c])); anoms.append(_c(Xs[r, c] - clim[c]))
    valid_pct = 100.0 * float(np.isfinite(Xs[:, cols]).mean())
    status = int(cl["status"][i, j])
    prov = {"dataset": f"{meta['dataset']} {meta.get('version')}", "doi": str(meta.get("doi")),
            "variance": meta.get("variance_estimator", ""), "multiple testing": f"BH-FDR q={cfg['fdr']['q']} (Wilks 2016)",
            "period": f"{y0} to {y1}"}
    base = dict(dates=dates, values=vals, anomalies=anoms, valid_pct=valid_pct, windows=[], f_sign=0.0, c4=False, c5=False,
                provenance=prov, custom=custom, p=None, q=None, ci_analytical=[None, None], by_season=None, slope_per_decade=None)
    if status != 0:
        why = "insufficient variability (mostly identical values)" if status == 2 else "incomplete record (missing months)"
        return {**base, "class": "Insufficient data", "explanation": f"This cell is not analysed: {why}."}
    by = {k: _sen(_season_matrix(Xs, k)) for k in MONTHS}
    Xm = _season_matrix(Xs, season); slope = _sen(Xm)
    W, step = cfg["stability"]["window_years"], cfg["stability"]["step_years"]
    wins = [{"start": start + s, "slope": _c(_sen(Xm[s:s + W]))} for s in range(0, len(Xs) - W + 1, step)]
    sg = np.sign(slope or 0)
    f_sign = float(np.mean([np.sign(w["slope"] or 0) == sg and sg != 0 for w in wins])) if wins else 0.0
    out = {**base, "slope_per_decade": _c(slope), "by_season": by, "windows": wins, "f_sign": f_sign}
    if custom:
        return {**out, "class": "Uncertain trend", "explanation": "Exploratory selection: not the pre-specified test."}
    p, q, lo, hi = (float(cl[k][i, j]) for k in ("p", "q", "lo_dec", "hi_dec"))
    ann = Xs.mean(axis=1)
    a = mk.hamed_rao_modification_test(ann) if np.isfinite(ann).all() else None
    c4 = bool(a is not None and np.isfinite(a.p) and np.sign(a.slope) == sg and a.p <= cfg["alpha"])
    if a is None or not np.isfinite(a.p):
        prov["C4 note"] = "annual-mean Hamed-Rao check undefined for this cell (negative variance); counted as not agreeing"
    reg = (meta.get("discontinuities") or [""])[0].strip().lower()
    c5 = bool(reg) and not reg.startswith("none documented")
    c1, c2 = q <= cfg["fdr"]["q"], (lo > 0 or hi < 0)
    cls = classify(True, c1, c2, f_sign, c4, c5, cfg)
    return {**out, "p": p, "q": q, "ci_analytical": [lo, hi], "c4": c4, "c5": c5, "class": cls,
            "explanation": explain(cls, slope or 0.0, meta["units"])}


def _snap(d, lat, lon):
    return int(np.abs(d["lat"] - lat).argmin()), int(np.abs(d["lon"] - lon).argmin())


def _cellX(d, i, j):
    return d["data"][:, i, j].astype(float).reshape(-1, 12)


@app.get("/compare")
def compare(var: str, lat: list[float] = Query(...), lon: list[float] = Query(...)):
    if len(lat) != len(lon) or not 2 <= len(lat) <= 6:
        raise HTTPException(400, "give 2 to 6 matching lat/lon pairs")
    d, cl = _load(var)
    bc = cfg["bootstrap"]; Ls = [bc["block_length_primary"], *bc["block_length_sensitivity"]]
    ij = [_snap(d, a, b) for a, b in zip(lat, lon)]
    i0, j0 = ij[0]; pairs = []
    for i, j in ij[1:]:
        base = {"lat": float(d["lat"][i]), "lon": float(d["lon"][j]), "delta": None, "ci": None, "ci_by_L": None, "differs": None}
        if (i, j) == (i0, j0):
            pairs.append({**base, "reason": "same grid cell as location 1"}); continue
        if int(cl["status"][i0, j0]) != 0 or int(cl["status"][i, j]) != 0:
            pairs.append({**base, "reason": "one of the two cells is not analysed (insufficient data or variability)"}); continue
        Xo, Xr = _cellX(d, i, j), _cellX(d, i0, j0)
        by = {}
        for L in Ls:
            dl, lo, hi = paired_delta(Xo, Xr, L, bc["B"], bc["seed"], bc["ci"])
            by[str(L)] = [lo * U, hi * U]; delta = dl * U
        lo, hi = by[str(Ls[0])]
        pairs.append({**base, "delta": _c(delta), "ci": [lo, hi], "ci_by_L": by, "differs": bool(lo > 0 or hi < 0)})
    return {"var": var, "block_length": Ls[0], "B": bc["B"], "pairs": pairs}


@app.get("/joint")
def joint(var_a: str, var_b: str, lat: float, lon: float):
    if var_a == var_b:
        raise HTTPException(400, "pick two different variables")
    da, ca = _load(var_a); db, cb = _load(var_b)
    ma, mb = _meta(var_a), _meta(var_b)
    if da["years"].shape != db["years"].shape or not np.array_equal(da["years"], db["years"]):
        raise HTTPException(400, "the two variables do not cover the same years; no joint analysis")
    ia, ja = _snap(da, lat, lon); ib, jb = _snap(db, lat, lon)
    la, lo_a, lb, lo_b = float(da["lat"][ia]), float(da["lon"][ja]), float(db["lat"][ib]), float(db["lon"][jb])
    A = {**series(var_a, la, lo_a), "id": var_a, "name": ma["name"], "units": ma["units"]}
    Bs = {**series(var_b, lb, lo_b), "id": var_b, "name": mb["name"], "units": mb["units"]}
    note = None if (abs(la - lb) < 1e-6 and abs(lo_a - lo_b) < 1e-6) else f"Grid cell centres differ slightly: {la}, {lo_a} vs {lb}, {lo_b}."
    assoc, reason = None, None
    if int(ca["status"][ia, ja]) != 0 or int(cb["status"][ib, jb]) != 0:
        reason = "Association not computed: at least one cell is not analysed (insufficient data or variability)."
    else:
        bc = cfg["bootstrap"]
        assoc = association(_cellX(da, ia, ja), _cellX(db, ib, jb), bc["block_length_primary"], bc["B"], bc["seed"], bc["ci"])
        if assoc is None:
            reason = "Association not computed: too few paired years or a constant series."
    txt = implication(var_a, var_b,
                      {"name": ma["name"], "units": ma["units"], "slope": A["slope_per_decade"], "cls": A["class"]},
                      {"name": mb["name"], "units": mb["units"], "slope": Bs["slope_per_decade"], "cls": Bs["class"]}, assoc, reason)
    return {"lat": la, "lon": lo_a, "a": A, "b": Bs, "association": assoc, "association_reason": reason, "implication": txt, "note": note}
