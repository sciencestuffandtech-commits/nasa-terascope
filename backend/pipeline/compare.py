from __future__ import annotations
import numpy as np
from scipy.stats import spearmanr
from .stats import seasonal_sen_per_year
from .bootstrap import _pooled_median_batch


def _fit(X):
    n = X.shape[0]; t = np.arange(n, dtype=float)
    b = seasonal_sen_per_year(X)
    a = np.nanmedian(X - b * t[:, None], axis=0)
    return a, b, X - a[None, :] - b * t[:, None]


def paired_delta(XA, XB, L, B, seed, ci=0.95, chunk=100):
    rng = np.random.default_rng(seed)
    n = XA.shape[0]; t = np.arange(n, dtype=float)
    aA, bA, RA = _fit(XA); aB, bB, RB = _fit(XB)
    I, J = np.triu_indices(n, 1); dt = (J - I).astype(float)
    k = int(np.ceil(n / L)); out = np.empty(B)
    base = lambda a, b: a[None, None, :] + b * t[None, :, None]
    for s in range(0, B, chunk):
        e = min(B, s + chunk)
        starts = rng.integers(0, n - L + 1, size=(e - s, k))
        idx = (starts[:, :, None] + np.arange(L)[None, None, :]).reshape(e - s, -1)[:, :n]
        out[s:e] = (_pooled_median_batch(base(aA, bA) + RA[idx], I, J, dt, idx)
                    - _pooled_median_batch(base(aB, bB) + RB[idx], I, J, dt, idx))
    lo, hi = np.percentile(out, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    return float(bA - bB), float(lo), float(hi)


def _annual_anom(X):
    return (X - np.nanmean(X, axis=0)[None, :]).mean(axis=1)


def _detrend(y):
    n = len(y); t = np.arange(n, dtype=float); i, j = np.triu_indices(n, 1)
    b = np.median((y[j] - y[i]) / (j - i))
    return y - b * t - np.median(y - b * t)


def _rho(x, y):
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan")
    return float(spearmanr(x, y)[0])


def association(XA, XB, L=3, B=1000, seed=0, ci=0.95, min_years=15):
    a, b = _annual_anom(XA), _annual_anom(XB)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < min_years:
        return None
    a, b = a[ok], b[ok]; n = len(a)
    rng = np.random.default_rng(seed)
    k = int(np.ceil(n / L))
    starts = rng.integers(0, n - L + 1, size=(B, k))
    idx = (starts[:, :, None] + np.arange(L)[None, None, :]).reshape(B, -1)[:, :n]
    out = {"n_years": int(n), "block_length": int(L), "B": int(B)}
    for name, (x, y) in {"raw": (a, b), "detrended": (_detrend(a), _detrend(b))}.items():
        r0 = _rho(x, y)
        bs = np.array([_rho(x[i], y[i]) for i in idx]); bs = bs[np.isfinite(bs)]
        if not np.isfinite(r0) or len(bs) < B // 2:
            return None
        lo, hi = np.percentile(bs, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
        out[name] = {"rho": r0, "ci": [float(lo), float(hi)]}
    return out


def _state(cls):
    return {"Robustly detectable trend": "yes", "Probable trend": "yes", "Uncertain trend": "uncertain",
            "No statistically detectable trend": "no"}.get(cls, "na")


def _lc(s): return s[:1].lower() + s[1:]
def _uc(s): return s[:1].upper() + s[1:]
def _dir(v): return "increasing" if v > 0 else "decreasing"
def _s(v): return f"{v:+.3g}"


def implication(ida, idb, A, B, assoc, reason=None):
    sa, sb = _state(A["cls"]), _state(B["cls"])
    na, nb = _lc(A["name"]), _lc(B["name"])
    parts = []
    if "na" in (sa, sb):
        bad = [x["name"] for x, s in ((A, sa), (B, sb)) if s == "na"]
        parts.append(f"{_uc(_lc(' and '.join(bad)))} cannot be assessed at this cell (insufficient data or variability).")
    elif sa == "yes" and sb == "yes":
        same = (A["slope"] > 0) == (B["slope"] > 0)
        parts.append(f"Both variables show a detectable trend, {'in the same direction' if same else 'in opposite directions'}: "
                     f"{na} is {_dir(A['slope'])} ({_s(A['slope'])} {A['units']}/decade) and {nb} is {_dir(B['slope'])} ({_s(B['slope'])} {B['units']}/decade).")
        if {ida, idb} == {"t2m", "precip"}:
            t, p = (A, B) if ida == "t2m" else (B, A)
            if t["slope"] > 0:
                parts.append("That is consistent with a " + ("warmer and wetter" if p["slope"] > 0 else "warmer and drier") +
                             " tendency.")
    elif "yes" in (sa, sb):
        y, o, so = (A, B, sb) if sa == "yes" else (B, A, sa)
        parts.append(f"Only {_lc(y['name'])} shows a detectable trend ({_dir(y['slope'])}, {_s(y['slope'])} {y['units']}/decade). "
                     f"{_uc(_lc(o['name']))} has {'an uncertain trend' if so == 'uncertain' else 'no statistically detectable trend'} here.")
    else:
        parts.append("Neither variable shows a robustly or probably detectable trend at this cell.")
    if assoc:
        d, r = assoc["detrended"], assoc["raw"]
        if d["ci"][0] > 0 or d["ci"][1] < 0:
            parts.append(f"Year to year, after removing each variable's own trend, the two co-vary (Spearman rho {d['rho']:+.2f}, 95% CI {d['ci'][0]:+.2f} to {d['ci'][1]:+.2f}): "
                         f"years with higher {na} tend to have {'higher' if d['rho'] > 0 else 'lower'} {nb}.")
        else:
            parts.append(f"Year to year, after removing each variable's own trend, co-variation is not distinguishable from zero "
                         f"(rho {d['rho']:+.2f}, 95% CI {d['ci'][0]:+.2f} to {d['ci'][1]:+.2f}).")
        if (r["ci"][0] > 0 or r["ci"][1] < 0) and not (d["ci"][0] > 0 or d["ci"][1] < 0):
            parts.append(f"The raw correlation (rho {r['rho']:+.2f}) is clearer only because it also reflects shared trends, which can produce an association by themselves.")
    elif reason:
        parts.append(reason)
