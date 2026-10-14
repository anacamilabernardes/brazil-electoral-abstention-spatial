from datetime import date
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from abstention_spatial.pipeline import cutoff_round, build, main


def zipped(path, member, text):
    with ZipFile(path, "w") as z:
        z.writestr(member, text.encode("latin-1"))


def test_cutoff_enforces_first_round_2026():
    assert cutoff_round(2026, date(2026, 10, 14)) == 1
    with pytest.raises(ValueError, match="cannot exceed"):
        cutoff_round(2026, date(2026, 10, 25))
    with pytest.raises(ValueError, match="not observable"):
        cutoff_round(2026, date(2026, 10, 3))


def test_complete_small_fixture_pipeline(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    zipped(raw / "municipio_tse_ibge.zip", "municipios.csv",
           "SG_UF;CD_MUNICIPIO_TSE;CD_MUNICIPIO_IBGE\nSP;71072;3550308\nRJ;60011;3304557\n")
    columns = "ANO_ELEICAO;NR_TURNO;SG_UF;CD_MUNICIPIO;NR_ZONA;CD_CARGO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES\n"
    zipped(raw / "detalhe_votacao_munzona_2022.zip", "2022.csv", columns +
           "2022;1;SP;71072;1;1;100;80;20\n"
           "2022;2;SP;71072;1;1;100;75;25\n"
           "2022;1;RJ;60011;2;1;200;170;30\n"
           "2022;2;RJ;60011;2;1;200;168;32\n")
    zipped(raw / "detalhe_votacao_munzona_2026.zip", "2026.csv", columns +
           "2026;1;SP;71072;1;1;100;82;18\n"
           "2026;2;SP;71072;1;1;100;70;30\n"
           "2026;1;RJ;60011;2;1;200;175;25\n")
    polygons = gpd.GeoDataFrame({"CD_MUN": ["3550308", "3304557"]},
                                 geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                                           Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])],
                                 crs="EPSG:4674")
    shape_path = raw / "municipalities.gpkg"
    polygons.to_file(shape_path, driver="GPKG")
    report = build(raw_dir=raw, output_dir=tmp_path / "out",
                   spatial_dir=tmp_path / "geo", years=(2022, 2026),
                   cutoff=date(2026, 10, 14), ibge_file=shape_path,
                   chunksize=2, allow_partial_coverage=True)
    panel = pd.read_csv(tmp_path / "out/municipal_panel.csv", dtype={"municipality_code": str})
    assert len(panel) == 6
    assert panel.loc[panel["year"] == 2026, "round"].eq(1).all()
    assert report["source_audit"]["2026"]["future_round_rows"] == 1
    assert report["geography_audit"]["matched_municipalities"] == 2
    assert (tmp_path / "out/etl_qa_report.json").exists()
    assert (tmp_path / "geo/municipalities_2025.gpkg").exists()
    assert len(gpd.read_file(tmp_path / "geo/municipalities_2025.gpkg", layer="municipalities_2025")) == 2
    spatial = gpd.read_file(tmp_path / "geo/municipalities_2025.gpkg", layer="municipal_panel")
    assert len(spatial) == 6
    assert spatial["absent"].sum() == panel["absent"].sum()
    assert int(panel["absent"].sum()) == 20 + 25 + 30 + 32 + 18 + 25
    # A destination locked by a Windows GIS reader must not publish new CSVs.
    output = tmp_path / "out/municipal_panel.csv"
    output.write_text("previous run sentinel")
    replace = Path.replace
    def locked(self, target):
        if self.suffix == ".gpkg":
            raise PermissionError("locked GeoPackage")
        return replace(self, target)
    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(PermissionError, match="locked GeoPackage"):
        build(raw_dir=raw, output_dir=tmp_path / "out", spatial_dir=tmp_path / "geo",
              years=(2022, 2026), ibge_file=shape_path, allow_partial_coverage=True)
    assert output.read_text() == "previous run sentinel"



def test_build_fails_missing_inputs_without_writing(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing offline official inputs"):
        build(raw_dir=tmp_path / "raw", output_dir=tmp_path / "output",
              spatial_dir=tmp_path / "geo", years=(2018,))
    assert not (tmp_path / "output/municipal_panel.csv").exists()


def test_cli_source_listing(capsys):
    assert main(["sources"]) == 0
    assert "tse-munzona-2022" in capsys.readouterr().out


def test_national_build_rejects_missing_historical_round(tmp_path, monkeypatch):
    import abstention_spatial.pipeline as pipeline
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("municipio_tse_ibge.zip", "BR_Municipios_2025.zip", "detalhe_votacao_munzona_2018.zip"):
        (raw / name).write_bytes(b"placeholder")
    monkeypatch.setattr(pipeline, "load_crosswalk", lambda *a, **k: pd.DataFrame())
    zones = pd.DataFrame({"year": [2018], "round": [1], "uf": ["SP"]})
    monkeypatch.setattr(pipeline, "read_munzona", lambda *a, **k: (zones, {}))
    with pytest.raises(ValueError, match="Incomplete round coverage"):
        build(raw_dir=raw, output_dir=tmp_path / "out", spatial_dir=tmp_path / "geo", years=(2018,))
