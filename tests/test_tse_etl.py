"""Synthetic inputs only; official TSE files are not included in Git."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from abstention_spatial.tse_etl import (
    harmonize_zones, load_crosswalk, read_csv_chunks, read_munzona,
)


def make_zip(path: Path, filename: str, text: str) -> Path:
    with ZipFile(path, "w") as z:
        z.writestr(filename, text.encode("latin-1"))
    return path


def munzona(rows: list[list[object]]) -> str:
    head = "ANO_ELEICAO;NR_TURNO;SG_UF;CD_MUNICIPIO;NR_ZONA;CD_CARGO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES"
    return head + "\n" + "\n".join(";".join(map(str, row)) for row in rows) + "\n"


def test_munzona_filters_nonpresident_zz_future_round_and_chunks(tmp_path):
    z = make_zip(tmp_path / "result.zip", "detalhe.csv", munzona([
        [2026, 1, "SP", "71072", 1, 1, 100, 80, 20],
        [2026, 1, "SP", "71072", 1, 3, 100, 80, 20],
        [2026, 1, "ZZ", "99999", 1, 1, 50, 40, 10],
        [2026, 2, "SP", "71072", 1, 1, 100, 75, 25],
        [2026, 1, "RJ", "60011", 2, 1, 200, 180, 20],
    ]))
    zones, audit = read_munzona(z, 2026, max_round=1, chunksize=2)
    assert len(zones) == 2
    assert zones["eligible"].sum() == 300
    assert set(zones["round"]) == {1}
    assert audit["other_cargo_rows"] == 1
    assert audit["out_of_scope_zz_rows"] == 1
    assert audit["future_round_rows"] == 1


def test_munzona_refuses_duplicate_zone_across_chunks(tmp_path):
    z = make_zip(tmp_path / "dup.zip", "a.csv", munzona([
        [2022, 1, "SP", "71072", 1, 1, 100, 80, 20],
        [2022, 1, "SP", "71072", 1, 1, 100, 80, 20],
    ]))
    with pytest.raises(ValueError, match="Duplicate"):
        read_munzona(z, 2022, chunksize=1)


def test_munzona_refuses_inconsistent_counts(tmp_path):
    z = make_zip(tmp_path / "bad.zip", "a.csv", munzona([
        [2022, 1, "SP", "71072", 1, 1, 100, 80, 21],
    ]))
    with pytest.raises(ValueError, match="Inconsistent"):
        read_munzona(z, 2022)


def test_munzona_refuses_ambiguous_office(tmp_path):
    data = munzona([[2022, 1, "SP", "71072", 1, 1, 100, 80, 20]])
    data = data.replace("CD_CARGO;", "")
    data = data.replace(";1;100", ";100")
    z = make_zip(tmp_path / "bad.zip", "a.csv", data)
    with pytest.raises(ValueError, match="office"):
        read_munzona(z, 2022)


def test_munzona_refuses_zip_with_multiple_csv_without_member(tmp_path):
    path = tmp_path / "archive.zip"
    with ZipFile(path, "w") as z:
        z.writestr("a.csv", "ONE;TWO\na;b\n")
        z.writestr("b.csv", "ONE;TWO\nc;d\n")
    with pytest.raises(ValueError, match="select --member"):
        list(read_csv_chunks(path))


def test_crosswalk_preserves_leading_zeros_and_harmonizes(tmp_path):
    path = make_zip(tmp_path / "crosswalk.zip", "municipio.csv",
                    "SG_UF;CD_MUNICIPIO_TSE;CD_MUNICIPIO_IBGE\n"
                    "AC;1120;1200013\nSP;71072;3550308\n")
    crosswalk = load_crosswalk(path)
    assert crosswalk.loc[crosswalk["uf"] == "AC", "tse_code"].iloc[0] == "01120"
    z = make_zip(tmp_path / "turnout.zip", "source.csv", munzona([
        [2022, 1, "AC", "01120", 1, 1, 50, 40, 10],
        [2022, 1, "SP", "71072", 1, 1, 100, 80, 20],
        [2022, 1, "SP", "71072", 2, 1, 200, 150, 50],
    ]))
    zones, _ = read_munzona(z, 2022)
    joined, panel = harmonize_zones(zones, crosswalk)
    assert len(joined) == 3
    assert set(panel["municipality_code"]) == {"1200013", "3550308"}
    assert panel["absent"].sum() == 80
    assert panel.loc[panel["municipality_code"] == "3550308", "eligible"].iloc[0] == 300


def test_crosswalk_refuses_collision(tmp_path):
    path = make_zip(tmp_path / "crosswalk.zip", "municipio.csv",
                    "SG_UF;CD_MUNICIPIO_TSE;CD_MUNICIPIO_IBGE\n"
                    "SP;71072;3550308\nSP;71072;3550309\n")
    with pytest.raises(ValueError, match="not unique"):
        load_crosswalk(path)


def test_harmonize_fails_unmapped(tmp_path):
    mapping = pd.DataFrame({"uf": ["SP"], "tse_code": ["71072"], "municipality_code": ["3550308"]})
    zones = pd.DataFrame({
        "year": [2022], "round": [1], "uf": ["RJ"], "tse_code": ["60011"],
        "electoral_zone": ["0001"], "eligible": [100], "turnout": [90], "absent": [10],
    })
    with pytest.raises(ValueError, match="Missing official IBGE mapping"):
        harmonize_zones(zones, mapping)


def test_official_archive_selects_br_once_and_keeps_transit(tmp_path):
    path = tmp_path / "national.zip"
    data = munzona([[2014, 1, "SP", "71072", 1, 1, 100, 80, 20],
                    [2014, 1, "SP", "71072", 1, 1, 10, 8, 2]])
    lines = data.splitlines()
    data = lines[0] + ";ST_VOTO_EM_TRANSITO\n" + lines[1] + ";N\n" + lines[2] + ";S\n"
    with ZipFile(path, "w") as z:
        z.writestr("detalhe_votacao_munzona_2014_BR.csv", data)
        z.writestr("detalhe_votacao_munzona_2014_BRASIL.csv", data)
        z.writestr("detalhe_votacao_munzona_2014_SP.csv", data)
    zones, audit = read_munzona(path, 2014, chunksize=1)
    assert zones["eligible"].sum() == 110
    assert audit["transit_rows"] == 1
    crosswalk = pd.DataFrame({"uf": ["SP"], "tse_code": ["71072"], "municipality_code": ["3550308"]})
    _, panel = harmonize_zones(zones, crosswalk)
    assert panel["eligible"].tolist() == [110]


def test_uninstalled_electors_are_not_imputed_as_absent(tmp_path):
    data = munzona([[2022, 1, "SP", "71072", 1, 1, 100, 70, 20]])
    head, row = data.strip().splitlines()
    path = make_zip(tmp_path / "a.zip", "a.csv", head + ";QT_ELEITORES_SECOES_NAO_INSTALADAS\n" + row + ";10\n")
    zones, audit = read_munzona(path, 2022)
    assert zones["absent"].tolist() == [20]
    assert zones["uninstalled"].tolist() == [10]
    assert audit["uninstalled_electors"] == 10


def test_discrepancy_requires_opt_in_and_preserves_counts(tmp_path):
    path = make_zip(tmp_path / "a.zip", "a.csv", munzona([[2014, 1, "SP", "71072", 1, 1, 100, 70, 28]]))
    with pytest.raises(ValueError, match="Inconsistent"):
        read_munzona(path, 2014)
    zones, audit = read_munzona(path, 2014, allow_discrepancies=True)
    assert zones["absent"].tolist() == [28]
    assert audit["unaccounted_electors"] == 2
    assert len(audit["count_discrepancies"]) == 1


def test_direct_reader_never_ingests_2026_round_two(tmp_path):
    path = make_zip(tmp_path / "a.zip", "a.csv", munzona([
        [2026, 1, "SP", "71072", 1, 1, 100, 80, 20],
        [2026, 2, "SP", "71072", 1, 1, 100, 70, 30],
    ]))
    zones, audit = read_munzona(path, 2026)
    assert zones["round"].tolist() == [1]
    assert audit["future_round_rows"] == 1


def test_source_generation_after_cutoff_is_rejected(tmp_path):
    data = munzona([[2026, 1, "SP", "71072", 1, 1, 100, 80, 20]])
    head, row = data.strip().splitlines()
    path = make_zip(tmp_path / "a.zip", "a.csv", head + ";DT_GERACAO\n" + row + ";15/10/2026\n")
    with pytest.raises(ValueError, match="exceeds forecasting cutoff"):
        read_munzona(path, 2026)
