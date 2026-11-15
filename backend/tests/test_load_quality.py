import numpy as np
from backend.pipeline import load as L, quality as Q

CFG = L.load_config()


def test_standardise_sorts_wraps_and_masks():
    v = np.array([[[1., 2., 3.], [4., 9999., 6.]]], dtype="float32")
    out, lat, lon = L.standardise(v, [10, -10], [0, 120, 240], valid_range=[-100, 100])
    assert list(lat) == [-10, 10] and list(lon) == [-120, 0, 120]
    assert out.shape == (1, 2, 3) and np.isnan(out).sum() == 1
    assert out[0, 0, 0] == 6 and out[0, 1, 1] == 1


def test_crop_period_never_fills():
    years = np.repeat([2000, 2001], 12); months = np.tile(np.arange(1, 13), 2)
    v = np.ones((24, 1, 1), dtype="float32")
    out, y, m = L.crop_period(v, years, months, "2001-01", "2002-12")
    assert out.shape[0] == 24 and np.isfinite(out[:12]).all() and np.isnan(out[12:]).all()
    assert L.last_complete_year(out, y, m) == 2001


def test_common_period_rule():
    full = lambda a, b: (np.ones(((b - a + 1) * 12, 1, 1)), np.repeat(np.arange(a, b + 1), 12), np.tile(np.arange(1, 13), b - a + 1))
    assert L.common_period({"a": full(1990, 2025), "b": full(1983, 2025)}, "2001-01", "2025-12", 20) == ("2001-01", "2025-12")
    assert L.common_period({"a": full(1990, 2024)}, "2001-01", "2025-12", 20) == ("2000-01", "2024-12")
    assert L.common_period({"a": full(1990, 2015)}, "2001-01", "2025-12", 20) == ("1991-01", "2015-12")
    assert L.common_period({"a": full(2010, 2025)}, "2001-01", "2025-12", 20) is None


def test_block_factor_and_average():
    assert L.choose_block_factor(90, 180, 20000) == 1
    assert L.choose_block_factor(360, 720, 20000) == 4
    lat = np.array([0.5, 1.5]); lon = np.array([0.5, 1.5])
    v = np.array([[[1., 2.], [3., np.nan]]], dtype="float32")
    out, la, lo = L.block_average(v, lat, lon, 2, 0.5)
    w = np.cos(np.deg2rad(lat)); exp = (1 * w[0] + 2 * w[0] + 3 * w[1]) / (2 * w[0] + w[1])
    assert abs(out[0, 0, 0] - exp) < 1e-6 and la[0] == 1.0
    out2, _, _ = L.block_average(v, lat, lon, 2, 0.9)
    assert np.isnan(out2[0, 0, 0])


def _cube(n_years=25):
    rng = np.random.default_rng(0)
    return rng.normal(size=(n_years * 12, 1, 6)).astype("float32"), np.repeat(np.arange(2001, 2001 + n_years), 12)


def test_eligibility_codes():
    d, yrs = _cube()
    d = d.reshape(25, 12, 1, 6).copy()
    d[:, 3, 0, 1] = np.nan
    d[5:10, 7, 0, 2] = np.nan
    d[0:4, 7, 0, 3] = np.nan
    d[[1, 5, 9], 7, 0, 4] = np.nan
    d = d.reshape(300, 1, 6)
    d[:, 0, 5] = 0.0
    s = Q.eligibility(d, yrs, CFG)[0]
    assert list(s) == [0, 1, 1, 1, 0, 2], s


def test_missing_months_boundary_80pct():
    d, yrs = _cube()
    d = d.reshape(25, 12, 1, 6).copy()
    d[[0, 6, 12, 18, 24], 0, 0, 0] = np.nan
    d[[0, 6, 12, 18, 24, 3], 0, 0, 1] = np.nan
    s = Q.eligibility(d.reshape(300, 1, 6), yrs, CFG)[0]
    assert s[0] == 0 and s[1] == 1


def test_short_record_is_insufficient():
    d, yrs = _cube(19)
    assert (Q.eligibility(d, yrs, CFG) == 1).all()


def test_units_and_slice_prep():
    p = {"offset": -273.15, "valid_range": [-100, 70]}
    v = np.full((1, 2, 2), 300.0, dtype="float32"); v[0, 0, 0] = 9999
    out, la, lo, f = L.prepare_slice(v, [0.5, 1.5], [0.5, 1.5], p, CFG)
    assert f == 1 and abs(out[0, 1, 1] - 26.85) < 1e-4 and np.isnan(out[0, 0, 0])
    assert abs(L.apply_units(np.array([2.0], dtype="float32"), {"scale": 24})[0] - 48) < 1e-5


def test_concat_time_sorts_and_refuses():
    la, lo = np.array([0., 2.]), np.array([0., 2.])
    mk = lambda y, m: (np.full((1, 2, 2), y + m / 100, dtype="float32"), la, lo, np.array([y]), np.array([m]))
    v, _, _, y, m = L.concat_time([mk(2001, 3), mk(2001, 1), mk(2001, 2)])
    assert list(m) == [1, 2, 3] and abs(v[0, 0, 0] - 2001.01) < 1e-3
    for bad in ([mk(2001, 1), mk(2001, 1)], [mk(2001, 1), (np.zeros((1, 2, 2), dtype="float32"), la + 5, lo, np.array([2001]), np.array([2]))]):
        try:
            L.concat_time(bad); raise SystemExit("should have raised")
        except ValueError:
            pass


def test_config_products():
    import re
    ps = CFG["products"]
    assert ps["t2m"]["enabled"] and ps["precip"]["enabled"]
    assert not any(ps[k]["enabled"] for k in ("t2m_merra2", "precip_imerg", "soil_moisture", "ndvi", "lst"))
    assert re.search(ps["precip"]["date_regex"], "GPCPMON_L3_198301_V3.3.nc4").groups() == ("1983", "01")
    assert L.choose_block_factor(1800, 3600, 20000) == 18 and L.choose_block_factor(600, 1440, 20000) == 8


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("pass", k)
