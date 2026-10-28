from datetime import date
from pathlib import Path
from zipfile import ZipFile
import json
import sqlite3

import pandas as pd
import pytest

from abstention_spatial.sections import build_sections, normalize_chunk
from abstention_spatial.sources import sha256_file


def row(year=2026, **values):
    data = dict(ANO_ELEICAO=str(year), NR_TURNO="1", SG_UF="SP", CD_MUNICIPIO="71072",
                NR_ZONA="1", NR_SECAO="1", CD_CARGO="1", DT_GERACAO="05/10/2026",
                QT_APTOS="100", QT_COMPARECIMENTO="80", QT_ABSTENCOES="20",
                NR_LOCAL_VOTACAO="1")
    data.update(values)
    return data


def fixture(tmp_path, rows):
    raw = tmp_path / "raw"
    raw.mkdir()
    crosswalk = "SG_UF;CD_MUNICIPIO_TSE;CD_MUNICIPIO_IBGE\nSP;71072;3550308\nRJ;60011;3304557\n"
    with ZipFile(raw / "municipio_tse_ibge.zip", "w") as z:
        z.writestr("crosswalk.csv", crosswalk)
    with ZipFile(raw / "detalhe_votacao_secao_2026.zip", "w") as z:
        z.writestr("detalhe_votacao_secao_2026_BR.csv", pd.DataFrame(rows).to_csv(index=False, sep=";").encode("latin-1"))
        # An overlapping export must never be concatenated with BR.
        z.writestr("detalhe_votacao_secao_2026_BRASIL.csv", pd.DataFrame(rows).to_csv(index=False, sep=";").encode("latin-1"))
    return raw


def test_cutoff_excludes_future_outcomes_before_parsing_counts():
    frame = pd.DataFrame([row(), row(NR_TURNO="2", QT_APTOS="invalid", DT_GERACAO="30/10/2026")])
    data, audit = normalize_chunk(frame, 2026)
    assert len(data) == 1
    assert audit["future_round_rows"] == 1
    assert data["section_id"].tolist() == ["0001"]
    assert data["polling_place_code"].tolist() == ["0001"]
    with pytest.raises(ValueError, match="cannot exceed"):
        normalize_chunk(frame, 2026, cutoff=date(2026, 10, 25))


@pytest.mark.parametrize("field", ["DT_GERACAO", "DT_RECEBIMENTO_BU_HOR_TSE", "DT_PRIM_TOT_PARCIAL_HOR_TSE"])
def test_section_future_dates_rejected(field):
    with pytest.raises(ValueError, match="cutoff"):
        normalize_chunk(pd.DataFrame([row(**{field: "15/10/2026"})]), 2026)


def test_uninstalled_is_supported_by_explicit_source_flag():
    data, _ = normalize_chunk(pd.DataFrame([row(2022, QT_APTOS="84", QT_COMPARECIMENTO="0", QT_ABSTENCOES="0", ST_SECAO_INSTALADA="Nao")]), 2022)
    assert data.uninstalled.tolist() == [84]
    assert data.unaccounted.tolist() == [0]
    assert data.absent.tolist() == [0]
    assert data.count_quality.tolist() == ["uninstalled"]
    with pytest.raises(ValueError, match="Uninstalled section"):
        normalize_chunk(pd.DataFrame([row(ST_SECAO_INSTALADA="Nao")]), 2026)


def test_legacy_residual_kept_unknown_and_requires_opt_in():
    frame = pd.DataFrame([row(2014, QT_APTOS="2", QT_COMPARECIMENTO="0", QT_ABSTENCOES="0")])
    with pytest.raises(ValueError, match="opt-in"):
        normalize_chunk(frame, 2014)
    data, _ = normalize_chunk(frame, 2014, allow_discrepancies=True)
    assert data.section_installed.isna().all()
    assert data.unaccounted.tolist() == [2]
    assert data.uninstalled.tolist() == [0]


def test_unknown_flags_and_zero_denominator_are_not_imputed():
    data, _ = normalize_chunk(pd.DataFrame([row(QT_APTOS="0", QT_COMPARECIMENTO="0", QT_ABSTENCOES="0", ST_SECAO_INSTALADA="#NULO#")]), 2026)
    assert data.abstention_rate.isna().all()
    assert data.section_installed.isna().all()
    assert data.count_quality.tolist() == ["zero_eligible"]


def test_small_end_to_end_build_and_reproducible_export(tmp_path):
    raw = fixture(tmp_path, [row(), row(NR_SECAO="2", QT_APTOS="200", QT_COMPARECIMENTO="150", QT_ABSTENCOES="50", ST_SECAO_INSTALADA="Sim"), row(NR_TURNO="2"), row(SG_UF="ZZ", CD_MUNICIPIO="99999")])
    args = dict(raw_dir=raw, years=(2026,), ufs=("SP",), chunksize=1)
    first = build_sections(output_dir=tmp_path / "out1", **args)
    second = build_sections(output_dir=tmp_path / "out2", **{**args,"chunksize":2})
    assert first["rows"] == 2
    assert first["source_audit"]["2026"]["future_round_rows"] == 1
    assert first["source_audit"]["2026"]["foreign_rows"] == 1
    assert first["national_domestic_by_year_round"][0]["eligible"] == 300
    with sqlite3.connect(tmp_path / "out1/section_panel.sqlite") as db:
        assert db.execute("select typeof(eligible),sum(eligible),sum(absent) from sections").fetchone() == ("integer", 300, 70)
        assert db.execute("select source_row from sections order by source_row").fetchall() == [(1,), (2,)]
    assert sha256_file(tmp_path / "out1/section_panel.csv.gz") == sha256_file(tmp_path / "out2/section_panel.csv.gz")
    csv = pd.read_csv(tmp_path / "out1/section_panel.csv.gz", dtype={"section_id":str,"municipality_code":str})
    assert csv.section_id.tolist() == ["0001", "0002"]
    assert csv.municipality_code.eq("3550308").all()


def test_duplicate_across_chunks_cannot_publish(tmp_path):
    raw = fixture(tmp_path, [row(), row()])
    with pytest.raises(ValueError, match="Duplicate section key"):
        build_sections(raw_dir=raw, output_dir=tmp_path / "out", years=(2026,),ufs=("SP",),chunksize=1)
    assert not (tmp_path / "out/section_panel.sqlite").exists()


def test_national_coverage_cannot_silently_accept_one_uf(tmp_path):
    raw = fixture(tmp_path, [row()])
    with pytest.raises(ValueError, match="Incomplete UF/round coverage"):
        build_sections(raw_dir=raw, output_dir=tmp_path / "out", years=(2026,))


def test_unmapped_section_municipality_fails(tmp_path):
    raw = fixture(tmp_path, [row(CD_MUNICIPIO="99998")])
    with pytest.raises(ValueError, match="Unmapped"):
        build_sections(raw_dir=raw, output_dir=tmp_path / "out", years=(2026,), ufs=("SP",))
