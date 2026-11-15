import numpy as np
import pymannkendall as mk
from backend.pipeline.stats import to_year_month, seasonal_sen_per_year, kendall_s, pooled_pairwise_slopes

TRUE_PER_YEAR = 0.02
rng = np.random.default_rng(1)
n_years = 25
t = np.arange(n_years * 12)
x = 8 * np.sin(2 * np.pi * (t % 12) / 12) + TRUE_PER_YEAR * (t / 12) + rng.normal(0, 0.3, t.size)
X = to_year_month(x)
own_slope, own_s, N = seasonal_sen_per_year(X), kendall_s(X), len(pooled_pairwise_slopes(X))
print(f"SYNTHETIC series. True slope {TRUE_PER_YEAR}/year = {TRUE_PER_YEAR / 12:.6f}/month")
print(f"own pooled Sen slope: {own_slope:.6f}/year   own Kendall S: {own_s}   pooled pairs N: {N}\n")

for name, fn in (("seasonal_test", mk.seasonal_test), ("correlated_seasonal_test", mk.correlated_seasonal_test)):
    r = fn(x, period=12)
    d = r._asdict()
    print(f"== {name}  (pymannkendall {getattr(mk, '__version__', '?')})")
    print("   fields returned:", list(d))
    print("   p =", d.get("p"), "  trend =", d.get("trend"), "  s =", d.get("s"), "  var_s =", d.get("var_s"), "  slope =", d.get("slope"))
    sl = d.get("slope")
    if sl is not None and own_slope:
        ratio = sl / own_slope
        unit = ("PER YEAR" if abs(ratio - 1) < 0.02 else "PER MONTH (x12 for per-year)" if abs(ratio - 1 / 12) < 0.02 * (1 / 12) + 1e-3 else "UNCLEAR")
        print(f"   slope / own_per_year = {ratio:.4f}  ->  library slope appears to be {unit}")
    print(f"   S matches own S: {d.get('s') == own_s}   has var_s: {'var_s' in d}\n")

print("Paste ALL of this output back. Do not use any library slope until the unit line above is settled.")

from backend.pipeline.stats import sen_ci_per_year
for name, fn in (("seasonal_test", mk.seasonal_test), ("correlated_seasonal_test", mk.correlated_seasonal_test)):
    v = fn(x, period=12).var_s
    lo, hi = sen_ci_per_year(X, v)
    print(f"{name}: CI per year = ({lo:.4f}, {hi:.4f})  contains 0.02: {lo <= 0.02 <= hi}")
