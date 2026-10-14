import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon
from abstention_spatial.ibge_etl import normalize_ibge_boundaries, geometry_coverage


def square(x):
    return Polygon([(x, 0), (x + 1, 0), (x + 1, 1), (x, 1)])


def fixture():
    return gpd.GeoDataFrame(
        {"CD_MUN": ["3550308", "1200013", "8888888"]},
        geometry=[square(0), square(1), square(2)], crs="EPSG:4674",
    )


def test_geometry_coverage_and_extra_feature_audit():
    geo = normalize_ibge_boundaries(fixture())
    panel = pd.DataFrame({"municipality_code": ["3550308", "1200013"]})
    matched, qa = geometry_coverage(panel, geo)
    assert len(matched) == 2
    assert qa["unused_geometry_codes"] == ["8888888"]
    assert not qa["missing_geometry_codes"]


def test_missing_geometry_fails():
    geo = normalize_ibge_boundaries(fixture())
    with pytest.raises(ValueError, match="Missing IBGE geometries"):
        geometry_coverage(pd.DataFrame({"municipality_code": ["3550308", "0123456"]}), geo)


def test_geometry_requires_crs():
    wrong = fixture().set_crs(None, allow_override=True)
    with pytest.raises(ValueError, match="no CRS"):
        normalize_ibge_boundaries(wrong)


def test_geometry_disallows_duplicate_municipality():
    wrong = fixture()
    wrong.loc[2, "CD_MUN"] = "3550308"
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_ibge_boundaries(wrong)
