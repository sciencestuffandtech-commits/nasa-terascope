import numpy as np


def to_year_month(x, period: int = 12):
    x = np.asarray(x, float)
    assert len(x) % period == 0, "series must be whole years"
    return x.reshape(-1, period)


def pooled_pairwise_slopes(X):
    out = []
    for m in range(X.shape[1]):
        col = X[:, m]; idx = np.flatnonzero(np.isfinite(col))
        if len(idx) < 2:
            continue
        i, j = np.triu_indices(len(idx), 1)
        out.append((col[idx[j]] - col[idx[i]]) / (idx[j] - idx[i]))
    return np.concatenate(out) if out else np.array([])


def kendall_s(X):
    s = 0
    for m in range(X.shape[1]):
        col = X[:, m]; v = col[np.isfinite(col)]
        i, j = np.triu_indices(len(v), 1)
        s += int(np.sign(v[j] - v[i]).sum())
    return s


def seasonal_sen_per_year(X):
    sl = pooled_pairwise_slopes(X)
    return float(np.median(sl)) if sl.size else float("nan")

def sen_ci_per_year(X, var_s: float, z: float = 1.959963984540054):
    sl = np.sort(pooled_pairwise_slopes(X)); N = len(sl)
    if N < 2 or not np.isfinite(var_s) or var_s <= 0:
        return float("nan"), float("nan")
    C = z * np.sqrt(var_s)
    m1, m2 = (N - C) / 2.0, (N + C) / 2.0
    pos = np.clip(np.array([m1 - 1.0, m2]), 0, N - 1)
    lo, hi = np.interp(pos, np.arange(N), sl)
    return float(lo), float(hi)
