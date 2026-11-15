import hashlib, json
import numpy as np
from .load import ROOT, load_config, open_raw, list_files, apply_units, standardise, last_complete_year, choose_block_factor

KEYS = ("title", "institution", "source", "version", "product_version", "history", "references", "doi", "DOI",
        "summary", "comment", "Conventions", "time_coverage_start", "time_coverage_end")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    cfg = load_config(); lock = {}
    for pid, p in cfg["products"].items():
        if not p.get("enabled", True):
            print(f"[{pid}] disabled, skipped"); continue
        if not p.get("variable"):
            print(f"[{pid}] variable not set in config.yaml, skipped"); continue
        files = [f for f in list_files(p) if f.exists()]
        if not files:
            print(f"[{pid}] MISSING {p.get('files') or p.get('file')} (see data/README.md)"); continue
        first, ys, ms, fins, anyok = None, [], [], [], []
        for path in files:
            v, la, lo, y, m, attrs = open_raw(path, p["variable"], p.get("date_regex"))
            v, la, lo = standardise(apply_units(v, p), la, lo, p.get("valid_range"))
            first = first or (la, lo, attrs)
            ys.append(y); ms.append(m)
            fin = np.isfinite(v).reshape(len(v), -1)
            fins.append(fin.mean(1)); anyok.append(fin.any(1))
        years, months = np.concatenate(ys), np.concatenate(ms)
        o = np.argsort(years * 12 + months); years, months = years[o], months[o]
        fin, ok = np.concatenate(fins)[o], np.concatenate(anyok)[o]
        la, lo, attrs = first
        dummy = np.where(ok, 1.0, np.nan).reshape(-1, 1, 1)
        info = {
            "files": [str(f.relative_to(ROOT)) for f in files][:3] + (["..."] if len(files) > 3 else []), "n_files": len(files),
            "sha256": sha256(files[0]) if len(files) == 1 else hashlib.sha256("\n".join(f"{f.name} {f.stat().st_size}" for f in files).encode()).hexdigest(),
            "sha256_kind": "file" if len(files) == 1 else "manifest of filenames+sizes",
            "variable": p["variable"], "units_in_file": attrs["variable"].get("units"), "units_in_config": p["units"],
            "scale": p.get("scale", 1), "offset": p.get("offset", 0),
            "grid_lat_lon": [len(la), len(lo)], "lat_range": [float(la.min()), float(la.max())], "lon_range": [float(lo.min()), float(lo.max())],
            "lat_step": float(abs(la[1] - la[0])), "lon_step": float(abs(lo[1] - lo[0])),
            "first_month": f"{years[0]}-{months[0]:02d}", "last_month": f"{years[-1]}-{months[-1]:02d}",
            "last_complete_year": last_complete_year(dummy, years, months),
            "months_with_no_data_at_all": [f"{y}-{m:02d}" for y, m, k in zip(years, months, ok) if not k][:50],
            "min_monthly_global_valid_fraction": float(fin.min()),
            "block_factor_for_cap": choose_block_factor(len(la), len(lo), cfg["grid_cap_cells"]),
            "file_attributes": {k: str(v) for k, v in attrs["global"].items() if k in KEYS},
            "variable_attributes": {k: str(v) for k, v in attrs["variable"].items()},
        }
        lock[pid] = info
        print(f"\n[{pid}] {len(files)} file(s)  grid {info['grid_lat_lon']}  {info['first_month']}..{info['last_month']}  last complete year {info['last_complete_year']}")
        print(f"   units in file: {info['units_in_file']!r} vs config {p['units']!r} (scale {info['scale']}, offset {info['offset']})   step {info['lat_step']}°x{info['lon_step']}°   block factor {info['block_factor_for_cap']}")
        todo = [k for k in ("version", "doi", "url", "discontinuity_registry") if not p.get(k)]
        print("   STILL TO FILL IN config.yaml (VERIFY):", todo or "nothing")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "product_lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    print("\nwrote data/product_lock.json")


if __name__ == "__main__":
    main()
