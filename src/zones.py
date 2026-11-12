"""Four exposure bands for the hotspot map."""

import pandas as pd


def hotspot_level(score):
    if pd.isna(score):
        return "No data"
    return ("Low", "Moderate", "High", "Very high")[min(3, int(score * 4))]
