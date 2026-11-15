import argparse, json, sys, tempfile, time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from joblib import Parallel, delayed

from . import bvar_cell

PROC = Path("data/processed")
NY, NM = 25, 12


def load_cfg(path="config.yaml"):
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    b = cfg["bvar"]
    b.setdefault("scale_by_month", True)
    b.setdefault("calibration", {"n_cells": 300, "n_shifts": 3, "pass_window": [0.06, 0.14]})
    b.setdefault("min_shift_years", 2)
    return cfg


def seasonal_residuals(x, slope_per_year):
    X = np.asarray(x, float).reshape(NY, NM)
    t = np.arange(NY, dtype=float)[:, None]
    a = np.nanmedian(X - slope_per_year * t, axis=0)
    return X - a - slope_per_year * t


def residual_series(x, slope_dec, scale_by_month):
    R = seasonal_residuals(x, slope_dec / 10.0)
    if not np.isfinite(R).all():
        return None
    if scale_by_month:
        sd = R.std(axis=0, ddof=1)
        if (sd <= 0).any():
            return None
        R = R / sd
    r = R.ravel()
    return r if r.std() > 0 else None


def load_inputs(proc=PROC, second="precip"):
    ld = lambda f: (lambda z: {k: z[k] for k in z.files})(np.load(proc / f))
    tc, pc, ts, ps = ld("t2m_cube.npz"), ld(f"{second}_cube.npz"), ld("t2m_cells.npz"), ld(f"{second}_cells.npz")
    if tc["data"].shape[1:] != pc["data"].shape[1:]:  # soil has no cells south of -60: subset t2m to its grid
        li = np.abs(tc["lat"][:, None] - pc["lat"][None]).argmin(0); oi = np.abs(tc["lon"][:, None] - pc["lon"][None]).argmin(0)
        assert np.allclose(tc["lat"][li], pc["lat"], atol=0.5) and np.allclose(tc["lon"][oi], pc["lon"], atol=0.5), "grids do not nest"
        tc = dict(tc, data=tc["data"][:, li][:, :, oi], lat=pc["lat"], lon=pc["lon"])
        ts = {k: v[li][:, oi] for k, v in ts.items()}
    assert tc["data"].shape == pc["data"].shape, "cubes differ in shape: grid matching needed"
    assert np.allclose(tc["lat"], pc["lat"]) and np.allclose(tc["lon"], pc["lon"]), "grids differ"
    assert tc["data"].shape[0] == NY * NM, "expected 300 months"
    assert np.array_equal(tc["months"][:12], np.arange(1, 13)), "series must start in January"
    return tc, pc, ts, ps


def build_residuals(tc, pc, ts, ps, scale_by_month):
    Td, Pd = tc["data"], pc["data"]
    both = (ts["status"] == 0) & (ps["status"] == 0)
    idx = np.argwhere(both)
    rows, RT, RP = [], [], []
    for i, j in idx:
        rt = residual_series(Td[:, i, j], ts["slope_dec"][i, j], scale_by_month)
        rp = residual_series(Pd[:, i, j], ps["slope_dec"][i, j], scale_by_month)
        if rt is None or rp is None:
            continue
        rows.append((i, j)); RT.append(rt); RP.append(rp)
    info = dict(n_status0_t=int((ts["status"] == 0).sum()), n_status0_p=int((ps["status"] == 0).sum()),
                n_status0_both=int(both.sum()), n_eligible=len(rows))
    return np.array(rows, int), np.array(RT), np.array(RP), info


def check_residuals(Td, slope_dec, cells, n=100, seed=0):
    try:
        from backend.pipeline.stats import seasonal_sen_per_year
    except Exception as e:
        return dict(skipped=f"stats import failed: {e}")
    rng = np.random.default_rng(seed)
    sel = rng.choice(len(cells), min(n, len(cells)), replace=False)
    worst = 0.0
    for k in sel:
        i, j = cells[k]
        R = seasonal_residuals(Td[:, i, j], slope_dec[i, j] / 10.0)
        worst = max(worst, abs(seasonal_sen_per_year(R)))
    return dict(n_checked=len(sel), max_abs_residual_sen_slope=float(worst))


FIELDS = ["pt_med", "pt_lo", "pt_hi", "pt_pneg", "tp_med", "tp_lo", "tp_hi", "tp_pneg", "gain"]


def _chunk(RT, RP, b, seeds, forecast):
    out = np.full((len(RT), len(FIELDS)), np.nan)
    for k in range(len(RT)):
        try:
            r = bvar_cell.analyse_cell(np.column_stack([RT[k], RP[k]]), p=b["lags"], lam=b["lambda_tightness"],
                                       decay=b["lag_decay"], n_draws=b["n_draws"], seed=int(seeds[k]),
                                       do_forecast=forecast)
        except np.linalg.LinAlgError:
            continue
        out[k] = [r["P_to_T"]["median"], r["P_to_T"]["lo"], r["P_to_T"]["hi"], r["P_to_T"]["p_neg"],
                  r["T_to_P"]["median"], r["T_to_P"]["lo"], r["T_to_P"]["hi"], r["T_to_P"]["p_neg"],
                  r.get("forecast_gain_T", np.nan)]
    return out


def run_cells(RT, RP, b, seed, forecast=True, n_jobs=-1, chunk=100):
    seeds = seed + np.arange(len(RT))
    parts = Parallel(n_jobs=n_jobs)(
        delayed(_chunk)(RT[k:k + chunk], RP[k:k + chunk], b, seeds[k:k + chunk], forecast)
        for k in range(0, len(RT), chunk))
    return np.vstack(parts) if parts else np.empty((0, len(FIELDS)))


def excl(res):
    lo, hi = res[:, 1], res[:, 2]
    return (lo > 0) | (hi < 0)


def summarise(res, level):
    ok = np.isfinite(res[:, 0])
    r = res[ok]
    if len(r) == 0:
        return dict(n=0)
    pt_lo, pt_hi, tp_lo, tp_hi = r[:, 1], r[:, 2], r[:, 5], r[:, 6]
    s = dict(
        n=int(len(r)),
        frac_PtoT_excl0=float(((pt_lo > 0) | (pt_hi < 0)).mean()),
        frac_PtoT_negative=float((pt_hi < 0).mean()),
        frac_PtoT_positive=float((pt_lo > 0).mean()),
        frac_TtoP_excl0=float(((tp_lo > 0) | (tp_hi < 0)).mean()),
        frac_TtoP_negative=float((tp_hi < 0).mean()),
        frac_TtoP_positive=float((tp_lo > 0).mean()),
        null_expectation_two_sided=round(1 - level, 4),
        null_expectation_each_side=round((1 - level) / 2, 4),
        median_PtoT=float(np.median(r[:, 0])),
    )
    g = r[:, 8]
    if np.isfinite(g).any():
        s.update(median_forecast_gain_T=float(np.nanmedian(g)), frac_forecast_gain_positive=float(np.nanmean(g > 0)))
    return s


def shifted(RP, rng, min_years, same_shift=None):
    n = len(RP)
    ks = np.full(n, same_shift) if same_shift is not None else rng.integers(min_years, NY - min_years + 1, n)
    return np.array([np.roll(RP[i], 12 * int(ks[i])) for i in range(n)])


def calibrate(RT, RP, b, seed, n_jobs):
    c = b["calibration"]
    rng = np.random.default_rng(seed)
    n = min(c["n_cells"], len(RT))
    sel = rng.choice(len(RT), n, replace=False)
    reps = []
    for s in range(c["n_shifts"]):
        res = run_cells(RT[sel], shifted(RP[sel], rng, b["min_shift_years"]), b, seed + 7919 * (s + 1),
                        forecast=False, n_jobs=n_jobs)
        r = res[np.isfinite(res[:, 0])]
        reps.append((float(((r[:, 1] > 0) | (r[:, 2] < 0)).mean()), float(((r[:, 5] > 0) | (r[:, 6] < 0)).mean())))
    pt, tp = np.mean([x[0] for x in reps]), np.mean([x[1] for x in reps])
    lo, hi = c["pass_window"]
    return dict(n_cells=int(n), n_shifts=c["n_shifts"], rate_PtoT_excl0=float(pt), rate_TtoP_excl0=float(tp),
                per_replicate=[dict(PtoT=a, TtoP=d) for a, d in reps], expected=round(1 - b["credible_level"], 3),
                pass_window=[lo, hi], passed=bool(lo <= pt <= hi and lo <= tp <= hi))


def field_null(RT, RP, b, seed, n_reps, n_jobs):
    rng = np.random.default_rng(seed)
    ks = rng.permutation(np.arange(b["min_shift_years"], NY - b["min_shift_years"] + 1))[:n_reps]
    out = []
    for k in ks:
        res = run_cells(RT, shifted(RP, rng, b["min_shift_years"], same_shift=int(k)), b, seed + int(k),
                        forecast=False, n_jobs=n_jobs)
        r = res[np.isfinite(res[:, 0])]
        out.append(dict(shift_years=int(k), frac_PtoT_excl0=float(((r[:, 1] > 0) | (r[:, 2] < 0)).mean()),
                        frac_PtoT_negative=float((r[:, 2] < 0).mean())))
    return out


def land_mask(lat, lon):
    try:
        from global_land_mask import globe
    except ImportError:
        return None
    LON, LAT = np.meshgrid(((np.asarray(lon) + 180) % 360) - 180, lat)
    return globe.is_land(LAT, LON)

def main(proc=PROC, cfg_path="config.yaml", calibrate_only=False, n_field=0, forecast=True, n_jobs=-1, second="precip"):
    t0 = time.time()
    cfg = load_cfg(cfg_path); b = cfg["bvar"]
    tag = "" if second == "precip" else f"_{second}"
    hyp = b.get("hypothesis_" + second, b["hypothesis"])
    tc, pc, ts, ps = load_inputs(proc, second)
    cells, RT, RP, info = build_residuals(tc, pc, ts, ps, b["scale_by_month"])
    print(f"eligible cells: {info}")
    if len(cells) == 0:
        sys.exit("no eligible cells")
    chk = check_residuals(tc["data"], ts["slope_dec"], cells); print("residual check:", chk)
    cal = calibrate(RT, RP, b, b["seed"], n_jobs)
    print("null calibration on shifted REAL residuals:", json.dumps(cal))
    if calibrate_only:
        return dict(calibration=cal)

    res = run_cells(RT, RP, b, b["seed"], forecast=forecast, n_jobs=n_jobs)
    lm = land_mask(tc["lat"], tc["lon"])
    is_land = np.array([lm[i, j] for i, j in cells]) if lm is not None else None
    summ = dict(all_cells=summarise(res, b["credible_level"]))
    if is_land is not None:
        summ["land_cells"] = summarise(res[is_land], b["credible_level"])
        summ["ocean_cells"] = summarise(res[~is_land], b["credible_level"])
    else:
        summ["note"] = "No land mask (pip install global-land-mask). H-TP is stated for land cells: report land-only when available."
    fn = field_null(RT, RP, b, b["seed"] + 1, n_field, n_jobs) if n_field else []
    if fn:
        obs = summ["land_cells"]["frac_PtoT_excl0"] if is_land is not None else summ["all_cells"]["frac_PtoT_excl0"]
        summ["field_null"] = dict(replicates=fn, observed_frac_PtoT_excl0=obs,
                                  n_null_reps_at_or_above_observed=int(sum(f["frac_PtoT_excl0"] >= obs for f in fn)),
                                  note="Null built on all eligible cells; compare with the matching observed set.")

    nlat, nlon = tc["data"].shape[1:]
    grids = {k: np.full((nlat, nlon), np.nan) for k in FIELDS}
    for n, k in enumerate(FIELDS):
        grids[k][cells[:, 0], cells[:, 1]] = res[:, n]
    ex = np.full((nlat, nlon), np.nan); ex[cells[:, 0], cells[:, 1]] = excl(res).astype(float)
    np.savez_compressed(proc / f"bvar{tag}_cells.npz", lat=tc["lat"], lon=tc["lon"], pt_excl0=ex,
                        land=(lm if lm is not None else np.array([])), **grids)
    mp = dict(var="bvar", lat=tc["lat"].tolist(), lon=tc["lon"].tolist(),
              pt_median=[[None if not np.isfinite(v) else round(float(v), 3) for v in r] for r in grids["pt_med"]],
              pt_excl0=[[None if not np.isfinite(v) else int(v) for v in r] for r in ex],
              label="EXPLORATORY lagged association; not causal; not in Section 5 or the FDR family")
    (proc / f"map_bvar{tag}.json").write_text(json.dumps(mp), encoding="utf-8")
    out = dict(hypothesis=hyp, config={k: b[k] for k in b if k != "hypothesis"}, input_info=info,
               residual_check=chk, calibration=cal, summary=summ, seconds=round(time.time() - t0, 1),
               versions=dict(numpy=np.__version__))
    (proc / f"bvar{tag}_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1)); print(f"done in {out['seconds']} s")
    return out


def selftest():
    from backend.pipeline.stats import seasonal_sen_per_year
    rng = np.random.default_rng(3)
    nlat, nlon = 10, 20
    T = np.zeros((300, nlat, nlon)); P = np.zeros_like(T)
    coupled = np.zeros((nlat, nlon), bool); coupled[:, :10] = True
    season = np.tile(np.cos(2 * np.pi * np.arange(12) / 12), NY)
    msd = np.tile(np.linspace(0.5, 2.0, 12), NY)
    t = np.arange(300) / 12
    for i in range(nlat):
        for j in range(nlon):
            y = bvar_cell.simulate(300, -0.30 if coupled[i, j] else 0.0, phi=0.3, rng=rng)
            T[:, i, j] = 10 * season + 0.02 * t + y[:, 0] * msd
            P[:, i, j] = 3 + 2 * season + 0.01 * t + y[:, 1] * msd
    P[:, 0, :] = 0.0
    tmp = Path(tempfile.mkdtemp()); sl = lambda D: np.array([[seasonal_sen_per_year(D[:, i, j].reshape(NY, NM)) * 10
                                                              if D[:, i, j].std() > 0 else np.nan
                                                              for j in range(nlon)] for i in range(nlat)])
    lat, lon = np.linspace(-88, 88, nlat), np.linspace(-178, 178, nlon)
    meta = dict(lat=lat, lon=lon, years=np.repeat(np.arange(2001, 2026), 12), months=np.tile(np.arange(1, 13), NY))
    for name, D in (("t2m", T), ("precip", P)):
        np.savez(tmp / f"{name}_cube.npz", data=D, **meta)
        s = sl(D); np.savez(tmp / f"{name}_cells.npz", status=np.where(np.isfinite(s), 0, 2).astype(np.int8), slope_dec=s)
    cfg = dict(bvar=dict(lags=3, lambda_tightness=0.2, lag_decay=1.0, n_draws=200, credible_level=0.90, seed=11,
                         scale_by_month=True, calibration=dict(n_cells=100, n_shifts=2, pass_window=[0.04, 0.16]),
                         min_shift_years=2, hypothesis="selftest"))
    (tmp / "config.yaml").write_text(yaml.safe_dump(cfg)); (tmp / "x").mkdir(exist_ok=True)
    out = main(proc=tmp, cfg_path=str(tmp / "config.yaml"), n_field=3, n_jobs=1)
    z = np.load(tmp / "bvar_cells.npz")
    ex = z["pt_excl0"]
    print("coupled-half detection:", np.nanmean(ex[:, :10]), " uncoupled-half:", np.nanmean(ex[:, 10:]))
    assert out["residual_check"]["max_abs_residual_sen_slope"] < 1e-9
    assert not np.isfinite(z["pt_med"][0]).any(), "constant-precip row should be excluded"
    assert np.nanmean(ex[:, :10]) > 0.7 and np.nanmean(ex[:, 10:]) < 0.25
    print("SELFTEST OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--calibrate-only", action="store_true")
    ap.add_argument("--field-null", type=int, default=0)
    ap.add_argument("--no-forecast", action="store_true")
    ap.add_argument("--jobs", type=int, default=-1)
    ap.add_argument("--second", default="precip", choices=["precip", "soil"])
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        main(calibrate_only=a.calibrate_only, n_field=a.field_null, forecast=not a.no_forecast, n_jobs=a.jobs, second=a.second)
