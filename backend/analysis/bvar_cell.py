import numpy as np
from scipy.stats import invwishart


def standardize(Y):
    mu, sd = Y.mean(0), Y.std(0, ddof=1)
    return (Y - mu) / sd, mu, sd


def build_xy(Y, p):
    T, n = Y.shape
    X = np.hstack([Y[p - l - 1: T - l - 1] for l in range(p)] + [np.ones((T - p, 1))])
    return Y[p:], X


def dummy_obs(n, p, lam, decay, eps=1e-4):
    k = n * p + 1
    J = np.diag(np.arange(1, p + 1, dtype=float) ** decay)
    Xd1 = np.hstack([np.kron(J, np.eye(n)) / lam, np.zeros((n * p, 1))])
    Yd1 = np.zeros((n * p, n))
    Xd2 = np.zeros((n, k)); Yd2 = np.eye(n)
    Xd3 = np.zeros((1, k)); Xd3[0, -1] = eps; Yd3 = np.zeros((1, n))
    return np.vstack([Yd1, Yd2, Yd3]), np.vstack([Xd1, Xd2, Xd3])


def posterior(Y, p=3, lam=0.2, decay=1.0):
    Ys, Xs = build_xy(Y, p)
    Yd, Xd = dummy_obs(Y.shape[1], p, lam, decay)
    Ya, Xa = np.vstack([Yd, Ys]), np.vstack([Xd, Xs])
    XtX_inv = np.linalg.inv(Xa.T @ Xa)
    B = XtX_inv @ Xa.T @ Ya
    R = Ya - Xa @ B
    S = R.T @ R
    nu = Xa.shape[0] - Xa.shape[1]
    return B, S, nu, XtX_inv


def draw_posterior(B, S, nu, XtX_inv, n_draws, rng):
    n = B.shape[1]
    Sig = invwishart(df=nu, scale=S).rvs(size=n_draws, random_state=rng).reshape(n_draws, n, n)
    A = np.linalg.cholesky(XtX_inv)
    out = np.empty((n_draws,) + B.shape)
    for d in range(n_draws):
        Z = rng.standard_normal(B.shape)
        out[d] = B + A @ Z @ np.linalg.cholesky(Sig[d]).T
    return out


def lag_sum(Bdraws, p, n, src, tgt):
    return sum(Bdraws[:, l * n + src, tgt] for l in range(p))


def summarize(x, level=0.90):
    lo, hi = np.quantile(x, [(1 - level) / 2, 1 - (1 - level) / 2])
    return dict(median=float(np.median(x)), lo=float(lo), hi=float(hi),
                p_neg=float((x < 0).mean()), excludes_zero=bool(lo > 0 or hi < 0))


def rolling_forecast_gain(Y, p=3, lam=0.2, decay=1.0, n_test=60):
    T = Y.shape[0]
    e_bv, e_un = [], []
    for t in range(T - n_test, T):
        Ytr = Y[:t]
        Ytr_s, mu, sd = standardize(Ytr)
        B, *_ = posterior(Ytr_s, p, lam, decay)
        x = np.concatenate([Ytr_s[-l - 1] for l in range(p)] + [[1.0]])
        f_bv = (x @ B)[0]
        B1, *_ = posterior(Ytr_s[:, :1], p, lam, decay)
        x1 = np.concatenate([Ytr_s[-l - 1, :1] for l in range(p)] + [[1.0]])
        f_un = (x1 @ B1)[0]
        y_true = (Y[t, 0] - mu[0]) / sd[0]
        e_bv.append(y_true - f_bv); e_un.append(y_true - f_un)
    r_bv, r_un = np.sqrt(np.mean(np.square(e_bv))), np.sqrt(np.mean(np.square(e_un)))
    return float(1 - r_bv / r_un)


def analyse_cell(Y, p=3, lam=0.2, decay=1.0, n_draws=300, seed=0, do_forecast=True):
    Ys, _, _ = standardize(Y)
    rng = np.random.default_rng(seed)
    B, S, nu, XtX_inv = posterior(Ys, p, lam, decay)
    D = draw_posterior(B, S, nu, XtX_inv, n_draws, rng)
    out = dict(
        P_to_T=summarize(lag_sum(D, p, 2, 1, 0)),
        T_to_P=summarize(lag_sum(D, p, 2, 0, 1)),
    )
    if do_forecast:
        out["forecast_gain_T"] = rolling_forecast_gain(Y, p, lam, decay)
    return out


def simulate(T, coupling_PT=0.0, phi=0.3, rng=None):
    A = np.array([[phi, coupling_PT], [0.0, phi]])
    y = np.zeros((T + 50, 2))
    for t in range(1, T + 50):
        y[t] = A @ y[t - 1] + rng.standard_normal(2)
    return y[50:]


def validate(n_sims=200, T=300, seed=20261115):
    rng = np.random.default_rng(seed)
    res = {}
    for name, c in [("null", 0.0), ("coupled_-0.25", -0.25)]:
        hit_PT = hit_TP = 0
        gains = []
        for _ in range(n_sims):
            y = simulate(T, c, rng=rng)
            r = analyse_cell(y, n_draws=200, seed=int(rng.integers(1e9)), do_forecast=(len(gains) < 30))
            hit_PT += r["P_to_T"]["excludes_zero"]
            hit_TP += r["T_to_P"]["excludes_zero"]
            if "forecast_gain_T" in r:
                gains.append(r["forecast_gain_T"])
        res[name] = dict(P_to_T_ci_excludes_zero=hit_PT / n_sims,
                         T_to_P_ci_excludes_zero=hit_TP / n_sims,
                         mean_forecast_gain=float(np.mean(gains)))
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2))
