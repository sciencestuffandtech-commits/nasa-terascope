# Terrascope

An interactive web app that detects long-term trends in NASA Earth-observation data and shows how strong the evidence for each trend is. Built for the NASA Space Apps Challenge 2026, "Be an Earth System Trend Detective!".
It answers one question "what is changing, where, how fast, and how confident can we be?"


## Data

Monthly records, 2001-01 to 2025-12.

Near-surface temperature anomaly from NASA GISS GISTEMP v4 (2° grid) (https://data.giss.nasa.gov/gistemp/data_v4.html)
Precipitation from GPCP Monthly Satellite-Gauge V3.3 (0.5° grid) (https://disc.gsfc.nasa.gov/datasets/GPCPMON_3.3/summary)
Soil moisture, 0-10 cm from NASA GLDAS Noah Land Surface Model L4 monthly V2.1 (0.25° grid, block-averaged to 2°) (https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_M_2.1/summary)


## What it does

- Seasonal Mann-Kendall test with Hamed-Rao autocorrelation correction, using `pymannkendall`, cross-checked against own reference code.
- Seasonal Sen's slope in units per decade, with analytical and residual year-block bootstrap 95% confidence intervals.
- Benjamini-Hochberg false-discovery-rate control across all grid cells.
- Stability check over rolling 15-year windows, plus an annual-mean check.
- Five-level evidence class: robustly detectable, probable, uncertain, no statistically detectable trend, insufficient data.
- Map of trends with significance, regional time series, two-location comparison with a paired bootstrap, and a two-variable association view.
- A Bayesian VAR for lagged precipitation-temperature and soil moisture-temperature association. Choose the second variable in the BVAR panel.
- Dataset provenance and limitations shown with every result. No interpolation of missing data.


## Requirements

- Python 3.10 or newer
- Node.js 18 or newer
- `global-land-mask` (land/ocean split)
- `pydap` (OPeNDAP subsetting for the soil moisture download)


## Run the app

With `data/raw/` and `data/processed/` in place, run from the project root:

```bash
py start.py
```

This installs frontend packages on first run, starts the API at http://localhost:8000 and the frontend at http://localhost:5173, and opens the frontend in Chrome. Press Ctrl+C to stop both.

Manual start:

```bash
pip install -r requirements.txt
py -m uvicorn backend.app:app --port 8000

cd frontend
npm install
npm run dev
```

## Rebuild the data

Run from the project root, in this order. Both downloads need an Earthdata login.

```bash
py scripts/download_gpcp.py                     # GPCP files
py scripts/download_soil.py                     # GLDAS soil moisture, only the 0-10 cm variable, via OPeNDAP
py -m backend.pipeline.lock_products            # record product facts
py -m backend.pipeline.precompute t2m           # add --allow-unlocked while exploring
py -m backend.pipeline.precompute precip
py -m backend.pipeline.precompute soil
py -m backend.analysis.real_run                 # BVAR, precipitation and temperature
py -m backend.analysis.real_run --second soil   # BVAR, soil moisture and temperature
py -m backend.analysis.land_split               # optional land/ocean split (precipitation run)
```

GISTEMP must be downloaded manually (see Data above) into `data/raw/`.

Soil moisture results are saved separately (`bvar_soil_cells.npz`, `bvar_soil_summary.json`, `map_bvar_soil.json`), so the precipitation results are never overwritten. In the saved output, "P to T" means second variable to temperature, which is soil moisture to temperature for the soil run.


## Validate

```bash
py -m backend.validation.check_library          # verifies pymannkendall
py -m backend.validation.simulate               # synthetic benchmarks; add --n 100
py -m pytest backend/tests
```

## Citations

- Lenssen et al. (2024), GISTEMP v4, doi:10.1029/2023JD040179
- GPCP Monthly V3.3, doi:10.5067/MEASURES/GPCP/DATA306
- GLDAS Noah Land Surface Model L4 monthly V2.1, doi:10.5067/SXAVCZFAQLNO; Rodell et al. (2004), doi:10.1175/BAMS-85-3-381