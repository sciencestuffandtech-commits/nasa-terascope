from __future__ import annotations
import math
import numpy as np

ELIGIBLE, INSUFFICIENT_DATA, INSUFFICIENT_VARIABILITY = 0, 1, 2


def completeness_mask(data, n_years: int, min_frac: float, max_gap_years: int):
    T, Y, X = data.shape
    assert T == n_years * 12, "period must be whole calendar years"
    valid = np.isfinite(data).reshape(n_years, 12, Y, X)
    need = math.ceil(min_frac * n_years - 1e-9)
    ok_count = (valid.sum(axis=0) >= need).all(axis=0)
    run = np.zeros((12, Y, X), dtype=np.int16); worst = np.zeros_like(run)
    for y in range(n_years):
        run = np.where(valid[y], 0, run + 1)
        worst = np.maximum(worst, run)
    ok_gap = (worst.max(axis=0) <= max_gap_years)
    return ok_count & ok_gap


def tie_mask(data, max_identical_fraction: float, candidates=None):
    T, Y, X = data.shape
    out = np.zeros((Y, X), dtype=bool)
    cells = np.argwhere(candidates) if candidates is not None else np.ndindex(Y, X)
    for i, j in cells:
        v = data[:, i, j]; v = v[np.isfinite(v)]
        if v.size:
            out[i, j] = np.unique(v, return_counts=True)[1].max() / v.size > max_identical_fraction
    return out


def eligibility(data, years, cfg: dict):
    n_years = len(np.unique(years))
    if n_years < cfg["min_record_years_tier1"]:
        return np.full(data.shape[1:], INSUFFICIENT_DATA, dtype=np.int8)
    c, t = cfg["completeness"], cfg["tie_rule"]
    comp = completeness_mask(data, n_years, c["min_valid_year_fraction_per_month"], c["max_consecutive_missing_years"])
    tie = tie_mask(data, t["max_identical_fraction"], candidates=comp)
    status = np.full(comp.shape, INSUFFICIENT_DATA, dtype=np.int8)
    status[comp] = ELIGIBLE
    status[comp & tie] = INSUFFICIENT_VARIABILITY
    return status


def summarise(status):
    n = status.size
    return {"cells": int(n), "eligible": int((status == 0).sum()),
            "insufficient_data": int((status == 1).sum()), "insufficient_variability": int((status == 2).sum())}
