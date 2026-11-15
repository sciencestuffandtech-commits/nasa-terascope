import time
from pathlib import Path
import earthaccess, xarray as xr

VAR = "SoilMoi0_10cm_inst"
out = Path("data/raw/soil")
out.mkdir(parents=True, exist_ok=True)
earthaccess.login()
hits = earthaccess.search_data(short_name="GLDAS_NOAH025_M", version="2.1", temporal=("2000-01-01", "2025-12-31"))
print("files found:", len(hits))
session = earthaccess.get_requests_https_session()


def urls(g):
    rel = g["umm"]["RelatedUrls"]
    dap = next(u["URL"] for u in rel if u.get("Type") == "USE SERVICE API" and "opendap" in u["URL"].lower())
    fname = next(u["URL"] for u in rel if u.get("Type") == "GET DATA" and u["URL"].endswith(".nc4")).rsplit("/", 1)[1]
    return "dap4://" + dap.removesuffix(".html").split("://", 1)[1], fname


for k, g in enumerate(hits):
    dap, fname = urls(g)
    dst = out / f"soil_{fname}"
    if dst.exists():
        continue
    for attempt in range(3):
        try:
            with xr.open_dataset(dap, engine="pydap", session=session) as ds:
                ds[[VAR]].load().to_netcdf(dst)  # only this variable is transferred
            break
        except Exception as e:
            dst.unlink(missing_ok=True)
            print(f"[{k}] {fname} attempt {attempt + 1} failed: {type(e).__name__}: {e}")
            if attempt == 2:
                raise SystemExit("stopping. Re-run to resume, finished months are skipped.")
            time.sleep(5)
    if k % 25 == 0:
        print(f"{k + 1}/{len(hits)}")
print("done")