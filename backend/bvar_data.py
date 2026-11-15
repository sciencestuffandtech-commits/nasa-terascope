from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
import numpy as np

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"


class Missing(Exception):
    pass


@lru_cache(maxsize=4)
def _load(proc_str: str, tag: str = ""):
    p = Path(proc_str) / f"bvar{tag}_cells.npz"
    if not p.exists():
        raise Missing("no BVAR results. Run: python -m backend.analysis.real_run" + (" --second soil" if tag else ""))
    z = np.load(p)
    return {k: z[k] for k in z.files}


def _r(a, nd):
    return [[None if not np.isfinite(v) else round(float(v), nd) for v in row] for row in a]


def _excl(lo, hi):
    out = np.full(lo.shape, np.nan)
    ok = np.isfinite(lo) & np.isfinite(hi)
    out[ok] = ((lo[ok] > 0) | (hi[ok] < 0)).astype(float)
    return out


def map_payload(proc: Path = PROC, tag: str = "") -> dict:
    z = _load(str(proc), tag)
    pe, te = _excl(z["pt_lo"], z["pt_hi"]), _excl(z["tp_lo"], z["tp_hi"])
    to_int = lambda a: [[None if not np.isfinite(v) else int(v) for v in row] for row in a]
    return dict(var="bvar", lat=z["lat"].tolist(), lon=z["lon"].tolist(),
                pt_median=_r(z["pt_med"], 3), pt_excl0=to_int(pe), tp_median=_r(z["tp_med"], 3), tp_excl0=to_int(te))


def cell_payload(lat: float, lon: float, proc: Path = PROC, tag: str = "") -> dict:
    z = _load(str(proc), tag)
    i, j = int(np.abs(z["lat"] - lat).argmin()), int(np.abs(z["lon"] - lon).argmin())
    base = dict(lat=float(z["lat"][i]), lon=float(z["lon"][j]))
    if not np.isfinite(z["pt_med"][i, j]):
        return {**base, "eligible": False,
                "reason": "Not in the BVAR set: the cell needs a completed primary trend test for BOTH variables (no gaps, enough variability)."}

    def d(p):
        lo, hi = float(z[f"{p}_lo"][i, j]), float(z[f"{p}_hi"][i, j])
        return dict(median=float(z[f"{p}_med"][i, j]), lo=lo, hi=hi, excludes_zero=bool(lo > 0 or hi < 0))
    g = z["gain"][i, j]
    return {**base, "eligible": True, "pt": d("pt"), "tp": d("tp"), "forecast_gain": None if not np.isfinite(g) else float(g)}


def _range(vals):
    return [float(min(vals)), float(max(vals))] if vals else None


def summary_payload(proc: Path = PROC, tag: str = "") -> dict:
    p = proc / f"bvar{tag}_summary.json"
    if not p.exists():
        raise Missing("no BVAR summary. Run: python -m backend.analysis.real_run" + (" --second soil" if tag else ""))
    d = json.loads(p.read_text(encoding="utf-8"))
    s = d.get("summary", {})
    sets = {"all": s.get("all_cells")}
    ls = d.get("land_split_from_saved")
    if ls:
        sets["land"], sets["ocean"] = ls.get("land"), ls.get("ocean")
    elif s.get("land_cells"):
        sets["land"], sets["ocean"] = s["land_cells"], s.get("ocean_cells")
    null = None
    reps = (s.get("field_null") or {}).get("replicates") or []
    if reps:
        g = lambda r, k: (r["all"][k] if "all" in r else r.get("frac_" + k))
        null = dict(n_reps=len(reps), **{k: _range([g(r, k) for r in reps if g(r, k) is not None])
                                          for k in ("PtoT_excl0", "PtoT_negative")})
    return dict(hypothesis=d.get("hypothesis"), calibration=d.get("calibration"), sets=sets, null=null,
                note="Null: precipitation residuals circularly shifted by whole years, same shift for every cell, so spatial correlation is kept. "
                     "Resolution is 1/(n_reps+1).",)