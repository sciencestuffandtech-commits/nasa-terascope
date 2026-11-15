import json
from pathlib import Path
import numpy as np
from . import real_run as rr

PROC = Path("data/processed")


def get_mask(lat, lon):
    from global_land_mask import globe
    LON, LAT = np.meshgrid(((np.asarray(lon) + 180) % 360) - 180, lat)
    return globe.is_land(LAT, LON)


def main(proc=PROC):
    z = np.load(proc / "bvar_cells.npz")
    lm = get_mask(z["lat"], z["lon"])
    ok = np.isfinite(z["pt_med"])
    res = np.column_stack([z[k][ok] for k in rr.FIELDS])
    land = lm[ok]
    cfg = rr.load_cfg(); lvl = cfg["bvar"]["credible_level"]
    split = dict(all=rr.summarise(res, lvl), land=rr.summarise(res[land], lvl), ocean=rr.summarise(res[~land], lvl),
                 n_land=int(land.sum()), n_ocean=int((~land).sum()))
    sp = proc / "bvar_summary.json"
    d = json.loads(sp.read_text(encoding="utf-8"))
    d["land_split_from_saved"] = split
    sp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    for k in ("land", "ocean"):
        s = split[k]
        print(f"{k.upper():5s} n={s['n']}  P->T excl0={s['frac_PtoT_excl0']:.3f} (neg {s['frac_PtoT_negative']:.3f}, pos {s['frac_PtoT_positive']:.3f})"
              f"   T->P excl0={s['frac_TtoP_excl0']:.3f} (neg {s['frac_TtoP_negative']:.3f}, pos {s['frac_TtoP_positive']:.3f})"
              f"   median P->T={s['median_PtoT']:.3f}  median fc gain={s.get('median_forecast_gain_T', float('nan')):.4f}")
    return split


if __name__ == "__main__":
    main()
