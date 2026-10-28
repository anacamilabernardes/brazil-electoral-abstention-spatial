"""Checked aggregate election computations and historical-change baseline."""

import numpy as np
import pandas as pd


KEY = ["municipality_code", "year", "round"]


def validate_municipal_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Return checked input; refuse duplicates and inconsistent turnout counts."""
    required = set(KEY + ["eligible", "turnout", "absent"])
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    result = df.copy()
    result["municipality_code"] = result["municipality_code"].astype("string")
    if result[KEY].isna().any().any() or result.duplicated(KEY).any():
        raise ValueError("Null or duplicate municipality/year/round keys")
    if not result["municipality_code"].str.fullmatch(r"\d{7}").all():
        raise ValueError("municipality_code must be a seven-digit IBGE code")
    if not result["round"].isin([1, 2]).all():
        raise ValueError("round must be 1 or 2")
    for col in ["uninstalled", "unaccounted"]:
        if col not in result:
            result[col] = 0
    for col in ["eligible", "turnout", "absent", "uninstalled", "unaccounted"]:
        val = pd.to_numeric(result[col], errors="coerce")
        if val.isna().any() or not np.isfinite(val).all() or (val % 1 != 0).any():
            raise ValueError(f"{col} must be finite nonnegative integers")
        result[col] = val.astype("int64")
    if ((result["eligible"] <= 0) | (result["turnout"] < 0) |
        (result["absent"] < 0) | (result["uninstalled"] < 0) | (result["unaccounted"] < 0) |
        (result["turnout"] + result["absent"] + result["uninstalled"] + result["unaccounted"] != result["eligible"])).any():
        raise ValueError("Election count constraints violated")
    result["abstention_rate"] = result["absent"] / result["eligible"]
    return result


def historical_round_change(
    panel: pd.DataFrame, historical_year: int, target_year: int, shrinkage: float = 20000
) -> pd.DataFrame:
    """Illustrative pre-election baseline; tune shrinkage using earlier elections."""
    if shrinkage < 0:
        raise ValueError("shrinkage must be nonnegative")
    df = validate_municipal_panel(panel)
    hist = df[df["year"] == historical_year]
    p1 = hist[hist["round"] == 1][["municipality_code", "eligible", "abstention_rate"]]
    p2 = hist[hist["round"] == 2][["municipality_code", "abstention_rate"]]
    paired = p1.merge(p2, on="municipality_code", how="inner",
                      suffixes=("_r1", "_r2"), validate="one_to_one")
    if paired.empty:
        raise ValueError("No historical municipalities observed in both rounds")
    paired["delta"] = paired["abstention_rate_r2"] - paired["abstention_rate_r1"]
    avg = np.average(paired["delta"], weights=paired["eligible"])
    paired["weight"] = paired["eligible"] / (paired["eligible"] + shrinkage)
    paired["delta_hat"] = paired["weight"] * paired["delta"] + (1 - paired["weight"]) * avg
    target = df[(df["year"] == target_year) & (df["round"] == 1)][
        ["municipality_code", "eligible", "abstention_rate"]
    ].copy()
    if target.empty:
        raise ValueError("Target first-round records not available")
    result = target.merge(paired[["municipality_code", "delta_hat"]],
                          on="municipality_code", how="left", validate="one_to_one")
    result["delta_hat"] = result["delta_hat"].fillna(avg)
    result["predicted_rate"] = (result["abstention_rate"] + result["delta_hat"]).clip(0, 1)
    result["eligible_assumption"] = result["eligible"]
    result["predicted_absent"] = result["predicted_rate"] * result["eligible_assumption"]
    return result
