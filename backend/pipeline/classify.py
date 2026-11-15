from __future__ import annotations


def classify(eligible: bool, c1: bool, c2: bool, f_sign: float, c4: bool, c5: bool, cfg: dict) -> str:
    st = cfg["stability"]; rob, prob = st["robust_agreement"], st["probable_agreement"]
    if not eligible:
        return "Insufficient data"
    if not c1 and not c2:
        return "No statistically detectable trend"
    if c1 and c2 and c4 and f_sign >= rob and not c5:
        return "Robustly detectable trend"
    if c1 and c2 and not c5 and f_sign >= prob and (c4 or f_sign >= rob):
        return "Probable trend"
    return "Uncertain trend"


def explain(cls: str, slope_per_decade: float, units: str) -> str:
    up = slope_per_decade > 0
    direction, noun = ("positive", "increase") if up else ("negative", "decrease")
    if cls == "Robustly detectable trend":
        return (f"The estimated trend is {direction} and its confidence interval excludes zero. The direction holds under the "
                f"main sensitivity checks. This supports a statistically detectable {noun} in the selected dataset, ")
    if cls == "Probable trend":
        return (f"The estimated trend is {direction} with substantial statistical evidence")
    if cls == "Uncertain trend":
        return (f"The estimated direction is {direction}, but it is sensitive to the analysis period")
    if cls == "No statistically detectable trend":
        return ("The available observations do not provide sufficient statistical evidence to distinguish a trend.")
    return "This cell does not meet the data requirements for a trend conclusion."
