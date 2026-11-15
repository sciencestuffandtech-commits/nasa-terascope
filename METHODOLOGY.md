Terrascope: Methods
Overview

Terrascope estimates long-term trends in gridded monthly NASA Earth-observation data and measures how strongly the data support each trend. Seasonal cycles, serial correlation, missing observations, product discontinuities and thousands of simultaneous tests can all produce spurious trends. The pipeline therefore separates a measured change, a statistically detectable trend, a trend that is stable under sensitivity analysis, and cases where the data cannot support any conclusion.


Data

Three products cover January 2001 to December 2025 (300 months): NASA GISS GISTEMP v4 near-surface temperature anomaly on a 2° grid (Lenssen et al., 2024); GPCP Monthly Satellite-Gauge Precipitation V3.3 on a 0.5° grid; and NASA GLDAS Noah Land Surface Model L4 monthly V2.1 soil moisture (0-10 cm) on a 0.25° grid (Rodell et al., 2004), retrieved through NASA Earthdata OPeNDAP. Grids above 20,000 cells are block-averaged once, area-weighted, to 2° (factor 4 for GPCP, 8 for GLDAS, giving 75 by 180 cells from 59°S to 89°N, nested in the GISTEMP grid).


Cell eligibility

A cell is tested only if every calendar month has at least 20 valid years with no run of more than three missing years, no more than half of its values are identical, and no month is missing. Other cells are labelled insufficient data or insufficient variability.


Trend estimation

Each cell is arranged as a year by calendar-month matrix, so every month is compared only with the same month. Significance uses the seasonal Mann-Kendall test (Hirsch et al., 1982) with the Hamed-Rao autocorrelation correction (Hamed and Rao, 1998), applied through pyMannKendall (Hussain and Mahmud, 2019) and checked against independent code. Magnitude is the seasonal Sen slope (Sen, 1968) per decade, with an analytical 95% interval using the corrected variance, and a residual year-block bootstrap (1,000 replicates, three-year blocks; Künsch, 1989).


Multiple testing

The test family was fixed in advance as all tested cells. Benjamini-Hochberg control at q = 0.10 (Benjamini and Hochberg, 1995) defines the significance mask. Because neighbouring cells are correlated, Benjamini-Yekutieli (2001) and uncorrected counts are also stored.


Stability and evidence classification

Each cell is assessed on five components: C1, q ≤ 0.10; C2, the Sen-slope interval excludes zero; f, the share of rolling 15-year windows with the same slope sign; C4, the annual-mean test agrees in sign; and C5, an unresolved product discontinuity. A fixed decision list gives one of five classes: robustly detectable, probable, uncertain, no statistically detectable trend, or insufficient data.


Comparison

For two to six locations, a paired year-block bootstrap tests the trend difference, and locations are declared different only if the 95% interval excludes zero. Association between variables uses detrended Spearman correlation with a block-bootstrap interval, and is exploratory.


Validation

Simulations (25 years, 1,000 replicates) covered null, stress and trend scenarios, with criteria fixed beforehand: a false-positive rate of 0.035 to 0.065 and interval coverage of at least 0.92. Unit tests cover loading, block averaging, completeness, ties and eligibility.


BVAR

TThe hypothesis is that the cumulative lagged effect of precipitation (and, separately, soil moisture) on temperature is negative over land. For cells eligible for both variables, each cell's Sen trend is removed, each calendar month is scaled by its standard deviation, and the series are standardised. A two-variable vector autoregression with three monthly lags uses a Minnesota prior (Litterman, 1986; Bańbura et al., 2010) with tightness 0.2, an analytical posterior and 300 draws, giving a 90% credible interval for the summed lag coefficients. Forecast gain compares rolling one-step temperature forecasts over the last 60 months with a temperature-only model. Calibration shifts the second variable by whole years in 300 cells, three times, and requires 6% to 14% of intervals to exclude zero.


Soil moisture results

Of 3,692 tested soil moisture cells, 1,576 (42.7%) show a significant trend at q = 0.10, and 560 (15.2%) under Benjamini-Yekutieli. Among 3,619 land cells eligible for both variables, 19.8% have a 90% interval for soil moisture to temperature excluding zero (15.9% negative, 3.8% positive), against 10% expected by chance, with a median coefficient of −0.025. Calibration passed (9.3%). The reverse direction excluded zero in 24.7% of cells. The median forecast gain was −0.003, positive in 35.7% of cells, so this is an in-sample association, not a predictor. The spatial field null was not run.


Reproducibility

Seeds are stored in the configuration file, and each result records dataset version, grid, block factor, period and cell counts. If a data file is missing, Terrascope returns an error and never substitutes other data.


References

Bańbura, Giannone and Reichlin (2010), J. Applied Econometrics 25. Benjamini and Hochberg (1995), JRSS B 57. Benjamini and Yekutieli (2001), Annals of Statistics 29. Hamed and Rao (1998), J. Hydrology 204. Hirsch, Slack and Smith (1982), Water Resources Research 18. Hussain and Mahmud (2019), JOSS 4(39). Künsch (1989), Annals of Statistics 17. Lenssen et al. (2024), JGR Atmospheres, doi:10.1029/2023JD040179. Litterman (1986), J. Business and Economic Statistics 4. Rodell et al. (2004), BAMS 85, doi:10.1175/BAMS-85-3-381. Sen (1968), JASA 63.