"""IBGE municipality boundary extraction, validation and spatial coverage checks."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import geopandas as gpd
import pandas as pd


ALLOWED_SHP_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def load_ibge_boundaries(source: Path) -> gpd.GeoDataFrame:
    """Load 2025 IBGE Shapefile or ZIP without unsafe arbitrary path extraction.

    Archive is expected to contain exactly one municipal .shp and its sidecars.
    """
    source = Path(source)
    if source.suffix.lower() != ".zip":
        return normalize_ibge_boundaries(gpd.read_file(source))
    with zipfile.ZipFile(source) as archive:
        files = [f for f in archive.infolist() if not f.is_dir()]
        candidates = [f for f in files if f.filename.lower().endswith(".shp")]
        if len(candidates) != 1:
            raise ValueError(f"Expected one .shp in IBGE archive; found {len(candidates)}")
        shp = candidates[0]
        # Flatten only entries with the same stem, regardless of ZIP directory.
        shp_name = PurePosixPath(shp.filename).name
        stem = shp_name[:-4]
        selected = [f for f in files if PurePosixPath(f.filename).name.lower().startswith(stem.lower() + ".")
                    and PurePosixPath(f.filename).suffix.lower() in ALLOWED_SHP_EXTENSIONS]
        needed = {".shp", ".shx", ".dbf"}
        available = {PurePosixPath(f.filename).suffix.lower() for f in selected}
        if not needed.issubset(available):
            raise ValueError(f"Missing essential Shapefile sidecars: {needed - available}")
        # Protect against archives with path traversal and implausible size.
        if sum(i.file_size for i in selected) > 3 * 1024**3:
            raise ValueError("IBGE archive uncompressed size exceeds safety threshold")
        with tempfile.TemporaryDirectory(prefix="ibge_municipal_") as folder:
            directory = Path(folder)
            for member in selected:
                ext = PurePosixPath(member.filename).suffix.lower()
                dest = directory / (stem + ext)
                with archive.open(member) as reader, dest.open("wb") as writer:
                    import shutil
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
            result = gpd.read_file(directory / shp_name)
    return normalize_ibge_boundaries(result)


def normalize_ibge_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError("IBGE geometries have no CRS; cannot assume EPSG:4674")
    if "CD_MUN" in gdf.columns:
        key = "CD_MUN"
    elif "municipality_code" in gdf.columns:
        key = "municipality_code"
    else:
        raise ValueError(f"No municipality code (CD_MUN) in IBGE geometry: {list(gdf.columns)}")
    out = gdf[[key, "geometry"]].rename(columns={key: "municipality_code"}).copy()
    out["municipality_code"] = out["municipality_code"].astype("string").str.strip()
    if out["municipality_code"].isna().any() or not out["municipality_code"].str.fullmatch(r"[0-9]{7}").all():
        raise ValueError("IBGE boundary codes must have exactly 7 digits")
    if out["municipality_code"].duplicated().any():
        raise ValueError("Duplicate municipal polygons; cannot join one-to-one")
    if out.geometry.isna().any() or out.geometry.is_empty.any():
        raise ValueError("Missing or empty IBGE geometries")
    invalid = ~out.geometry.is_valid
    if invalid.any():
        raise ValueError(f"Invalid IBGE polygons: {int(invalid.sum())}; review before repairing")
    if not out.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Expected Polygon/MultiPolygon geometries")
    return out.to_crs("EPSG:4674").sort_values("municipality_code").reset_index(drop=True)


def geometry_coverage(
    panel: pd.DataFrame, boundaries: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, dict]:
    """Match geography to panel, report extras and fail on any missing panel geometry.

    This function returns geometries for covered municipalities only. 2025
    published IBGE archive includes units other than ordinary municipalities;
    extras remain visible in the QA report, never coerced into turnout rows.
    """
    unique = panel["municipality_code"].drop_duplicates()
    matched = boundaries.merge(pd.DataFrame({"municipality_code": unique}),
                               on="municipality_code", how="right",
                               validate="one_to_one", indicator=True)
    missing = matched.loc[matched["_merge"] == "right_only", "municipality_code"].tolist()
    extras = boundaries.loc[~boundaries["municipality_code"].isin(unique), "municipality_code"].tolist()
    audit = {
        "unique_panel_municipalities": int(unique.size),
        "geometry_features_in_source": len(boundaries),
        "matched_municipalities": int(unique.size - len(missing)),
        "missing_geometry_codes": missing,
        "unused_geometry_codes": extras,
    }
    if missing:
        raise ValueError(f"Missing IBGE geometries for {len(missing)} panel municipalities: {missing[:15]}")
    return gpd.GeoDataFrame(matched.drop(columns=["_merge"]),
                            geometry="geometry", crs=boundaries.crs), audit
