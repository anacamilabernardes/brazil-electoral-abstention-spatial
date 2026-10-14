"""Spatial diagnostic helpers (requires properly joined municipal geometry)."""

import numpy as np
import geopandas as gpd
from esda.moran import Moran
from libpysal.weights import Queen


def municipal_moran(gdf: gpd.GeoDataFrame, column: str):
    """Compute global Moran's I; refuse unmatched or isolated geography."""
    if gdf.empty or gdf.geometry.isna().any() or gdf[column].isna().any():
        raise ValueError("Complete geometry and outcome required")
    if gdf["municipality_code"].duplicated().any():
        raise ValueError("Duplicate municipal geometries")
    ordered = gdf.sort_values("municipality_code").reset_index(drop=True)
    w = Queen.from_dataframe(ordered, use_index=False)
    if w.islands:
        raise ValueError(f"Island municipalities require explicit handling: {w.islands}")
    w.transform = "r"
    return Moran(np.asarray(ordered[column], dtype=float), w, permutations=999)
