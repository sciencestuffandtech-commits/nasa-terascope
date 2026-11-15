import argparse, json, sys, time, warnings
import numpy as np
import pymannkendall as mk
from joblib import Parallel, delayed
from ..pipeline.load import ROOT, load_config
from ..pipeline.stats import to_year_month, seasonal_sen_per_year, sen_ci_per_year
from ..pipeline.bootstrap import bootstrap_ci

warnings.filterwarnings("ignore")


def ar1(phi, n, rng):
    e = rng.normal(size=n); x = np.empty(n); x[0] = e[0]; s = np.sqrt(1 - phi ** 2)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * e[i]
    return x


def make_series(sc, sim, rng):
    n_y = sim["n_years"]; n = n_y * 12; t = np.arange(n)
    cycle = sim["cycle_amplitude"] * np.sin(2 * np.pi * t / 12)
    noise = ar1(sc["phi"], n, rng) if sc.get("phi") else rng.normal(size=n)
    noise = noise * sim["noise_sd"]
    if sc.get("annual_rho"):
        a = ar1(sc["annual_rho"], n_y, rng) * sim["annual_component_sd"]
        noise = noise + np.repeat(a, 12)
    x = cycle + sc.get("slope_per_year", 0.0) * t / 12.0 + noise
    if sc.get("missing_fraction"):
        k = int(round(sc["missing_fraction"] * n))
        x[rng.choice(n, k, replace=False)] = np.nan
    return x


def one_sim(name, sc, k, cfg, do_boot):
    sim, bt = cfg["simulation"], cfg["bootstrap"]
    rng = np.random.default_rng(np.random.SeedSequence([sim["base_seed"], sim["scenario_order"].index(name), k]))
    x = make_series(sc, sim, rng); X = to_year_month(x)
    truth = sc.get("slope_per_year", 0.0)
    r = {"slope": seasonal_sen_per_year(X) - truth}
    has_nan = bool(np.isnan(x).any())
    plain = mk.seasonal_test(x, period=12)
    r["p_plain"] = float(plain.p)
    lo, hi = sen_ci_per_year(X, plain.var_s); r["ci_plain"] = (lo <= truth <= hi)
    if has_nan:
        r["p_corr"] = None; r["ci_corr"] = None
    else:
        corr = mk.correlated_seasonal_test(x, period=12)
        r["p_corr"] = float(corr.p)
        lo, hi = sen_ci_per_year(X, corr.var_s); r["ci_corr"] = (lo <= truth <= hi)
    if do_boot and sc.get("boot", False):
        for L in [bt["block_length_primary"]] + list(bt["block_length_sensitivity"]):
            lo, hi = bootstrap_ci(X, L, bt["B"], rng, bt["ci"]); r[f"boot_L{L}"] = (lo <= truth <= hi)
    return r


def summarise(name, sc, rs, cfg):
    sim, a = cfg["simulation"], cfg["alpha"]
    out = {"n_sims": len(rs), "true_slope_per_year": sc.get("slope_per_year", 0.0)}
    for key in ("p_plain", "p_corr"):
        ps = [r[key] for r in rs if r[key] is not None]
        out[("rate_" + key[2:])] = (float(np.mean(np.array(ps) < a)) if ps else None)
    for key in ("ci_plain", "ci_corr") + tuple(k for k in rs[0] if k.startswith("boot_")):
        v = [r[key] for r in rs if r.get(key) is not None]
        out["cov_" + key] = float(np.mean(v)) if v else None
    sl = np.array([r["slope"] for r in rs])
    out["bias_per_year"], out["rmse_per_year"] = float(sl.mean()), float(np.sqrt((sl ** 2).mean()))
    return out


def verdicts(name, s, cfg):
    sim = cfg["simulation"]; v = []
    lo, hi = sim["fp_pass_window"]
    if name in ("S0", "S1"):
        for k in ("rate_corr", "rate_plain"):
            if s[k] is not None:
                v.append(f"{k}={s[k]:.3f} {'PASS' if lo <= s[k] <= hi else 'FAIL'} (window {lo}-{hi})")
    if name in ("S2", "S3", "S4"):
        for k in ("rate_corr", "rate_plain"):
            if s[k] is not None:
                v.append(f"{k}={s[k]:.3f}" + (" ANTI-CONSERVATIVE: state in Limitations" if s[k] > sim["fp_report_threshold"] else ""))
    if name in ("S0", "S1", "T1", "T2", "T3"):
        for k, val in s.items():
            if k.startswith("cov_") and val is not None:
                v.append(f"{k}={val:.3f} {'PASS' if val >= sim['coverage_min'] else 'FAIL'} (min {sim['coverage_min']})")
    if name.startswith("T"):
        v.append(f"power corr={s['rate_corr']:.3f} plain={s['rate_plain']:.3f}")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None); ap.add_argument("--scenarios", default=None)
    ap.add_argument("--no-boot", action="store_true"); ap.add_argument("--workers", type=int, default=-1)
    args = ap.parse_args()
    cfg = load_config(); sim = cfg["simulation"]
    N = args.n or sim["n_sims"]
    names = args.scenarios.split(",") if args.scenarios else sim["scenario_order"]
    results = {}; t0 = time.time()
    for name in names:
        sc = sim["scenarios"][name]
        rs = Parallel(n_jobs=args.workers)(delayed(one_sim)(name, sc, k, cfg, not args.no_boot) for k in range(N))
        s = summarise(name, sc, rs, cfg); s["verdicts"] = verdicts(name, s, cfg); results[name] = s
        print(f"\n[{name}] {sc['desc']}   ({time.time() - t0:.0f}s)")
        for k, val in s.items():
            if k not in ("verdicts",):
                print(f"   {k}: {val if not isinstance(val, float) else round(val, 4)}")
        for line in s["verdicts"]:
            print("   >>", line)
    out = ROOT / "data" / "validation"; out.mkdir(parents=True, exist_ok=True)
    (out / "simulation_results.json").write_text(json.dumps({"config_simulation": sim, "bootstrap": cfg["bootstrap"], "alpha": cfg["alpha"], "n_sims_run": N, "results": results}, indent=2), encoding="utf-8")
    print("\nwrote data/validation/simulation_results.json")


if __name__ == "__main__":
    main()
