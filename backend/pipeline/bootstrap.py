import numpy as np
from .stats import seasonal_sen_per_year


def _pooled_median_batch(Xs, I, J, dt, idx):
    D = (Xs[:, J, :] - Xs[:, I, :]) / dt[None, :, None]
    dup = idx[:, I] == idx[:, J]
    D = np.where(dup[:, :, None], np.nan, D).reshape(len(Xs), -1)
    return np.nanmedian(D, axis=1)


def bootstrap_slopes(X, L, B, rng, chunk=100):
    n = X.shape[0]
    t = np.arange(n, dtype=float)
    b = seasonal_sen_per_year(X)
    a = np.nanmedian(X - b * t[:, None], axis=0)
    R = X - a[None, :] - b * t[:, None]
    I, J = np.triu_indices(n, 1)
    dt = (J - I).astype(float)
    k = int(np.ceil(n / L))
    out = np.empty(B)
    for s in range(0, B, chunk):
        e = min(B, s + chunk)
        starts = rng.integers(0, n - L + 1, size=(e - s, k))
        idx = (starts[:, :, None] + np.arange(L)[None, None, :]).reshape(e - s, -1)[:, :n]
        Xs = a[None, None, :] + b * t[None, :, None] + R[idx]
        out[s:e] = _pooled_median_batch(Xs, I, J, dt, idx)
    return out


def bootstrap_ci(X, L, B, rng, ci=0.95):
    sl = bootstrap_slopes(X, L, B, rng)
    lo, hi = np.percentile(sl, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    return float(lo), float(hi)
