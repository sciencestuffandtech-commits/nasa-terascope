from __future__ import annotations
import argparse, json, time
from pathlib import Path
import numpy as np
from joblib import Parallel, delayed
from .load import ROOT, Product, load_config, load_product
from .quality import eligibility, summarise
from .stats import seasonal_sen_per_year, sen_ci_per_year

OUT = ROOT / "data" / "processed"


def _cell(X):
    import pymannkendall as mk
    r = mk.correlated_seasonal_test(X.ravel(), period=12)
    lo, hi = sen_ci_per_year(X, r.var_s)
    return float(r.p), seasonal_sen_per_year(X), lo, hi


def _chunk(Xs):
    return [_cell(X) for X in Xs]


def compute(p: Product, cfg: dict, n_jobs: int = -1) -> dict:
    from statsmodels.stats.multitest import multipletests
    t0 = time.time(); T, Y, Xn = p.data.shape; ny = p.n_years
    status = eligibility(p.data, p.years, cfg).astype(np.int8)
    incomplete = (status == 0) & ~np.isfinite(p.data).all(axis=0)
    status[incomplete] = 1
    cells = np.argwhere(status == 0)
    Xs = [p.data[:, i, j].reshape(ny, 12).astype(float) for i, j in cells]
    out = Parallel(n_jobs=n_jobs)(delayed(_chunk)(Xs[k:k + 200]) for k in range(0, len(Xs), 200))
    res = np.array([r for c in out for r in c], float).reshape(-1, 4)
    P, S, LO, HI = (res[:, k] for k in range(4)) if len(res) else (np.array([]),) * 4
    good = np.isfinite(P) & np.isfinite(S)
    status[tuple(cells[~good].T)] = 2 if (~good).any() else 0
    nan = lambda: np.full((Y, Xn), np.nan)
    slope, q, pv, lo, hi = nan(), nan(), nan(), nan(), nan()
    gi = cells[good]; qcfg, alpha = cfg["fdr"], cfg["alpha"]
    n_sig_fdr = n_sig_by = n_sig_raw = 0
    if good.any():
        qv = multipletests(P[good], method=qcfg["method"])[1]
        n_sig_fdr = int((qv <= qcfg["q"]).sum()); n_sig_raw = int((P[good] < alpha).sum())
        n_sig_by = int((multipletests(P[good], method="fdr_by")[1] <= qcfg["q"]).sum())
        slope[tuple(gi.T)] = S[good] * cfg["rate_unit_years"]; q[tuple(gi.T)] = qv; pv[tuple(gi.T)] = P[good]
        lo[tuple(gi.T)] = LO[good] * cfg["rate_unit_years"]; hi[tuple(gi.T)] = HI[good] * cfg["rate_unit_years"]
    meta = dict(p.meta); meta["limitations"] = list(meta["limitations"])
    n_inc = int(incomplete.sum())
    meta.update(summary=summarise(status), n_incomplete_excluded=n_inc, n_tested=int(good.sum()),
                n_significant_raw=n_sig_raw, n_significant_fdr=n_sig_fdr, n_significant_by=n_sig_by,
                fdr_q=qcfg["q"], seconds=round(time.time() - t0, 1),
                variance_estimator=f"pymannkendall {cfg['library']['version']} correlated_seasonal_test")
    return dict(status=status, slope=slope, q=q, p=pv, lo=lo, hi=hi, meta=meta)


def _json(a):
    return [[None if not np.isfinite(v) else round(float(v), 4) for v in row] for row in a]


def write(pid: str, p: Product, r: dict, out: Path = OUT):
    out.mkdir(parents=True, exist_ok=True)
    (out / f"map_{pid}.json").write_text(json.dumps({"var": pid, "lat": p.lat.tolist(), "lon": p.lon.tolist(),
        "slope_per_decade": _json(r["slope"]), "q_value": _json(r["q"]), "status": r["status"].tolist()}), encoding="utf-8")
    np.savez_compressed(out / f"{pid}_cube.npz", data=p.data, lat=p.lat, lon=p.lon, years=p.years, months=p.months)
    np.savez_compressed(out / f"{pid}_cells.npz", status=r["status"], slope_dec=r["slope"], q=r["q"], p=r["p"], lo_dec=r["lo"], hi_dec=r["hi"])
    mp = out / "meta.json"
    allm = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {"variables": []}
    allm["variables"] = [v for v in allm["variables"] if v["id"] != pid] + [r["meta"]]
    mp.write_text(json.dumps(allm, indent=1, default=str), encoding="utf-8")


def run(pid: str, cfg: dict | None = None, allow_unlocked: bool = False, n_jobs: int = -1):
    cfg = cfg or load_config()
    p = load_product(pid, cfg, require_locked=not allow_unlocked)
    if p.meta["tier"] != 1:
        raise RuntimeError(f"[{pid}] is Tier {p.meta['tier']}: no full trend analysis (Addendum A Sec 5.4)")
    r = compute(p, cfg, n_jobs); write(pid, p, r)
    m = r["meta"]
    print(f"[{pid}] {m['summary']}\n  tested={m['n_tested']} significant: raw={m['n_significant_raw']} "
          f"FDR(q={m['fdr_q']})={m['n_significant_fdr']} BY={m['n_significant_by']}  incomplete excluded={m['n_incomplete_excluded']}  ({m['seconds']}s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("product"); ap.add_argument("--allow-unlocked", action="store_true")
    ap.add_argument("--jobs", type=int, default=-1); a = ap.parse_args()
    run(a.product, allow_unlocked=a.allow_unlocked, n_jobs=a.jobs)
