"""Trace historical turnout discrepancies using downloaded official section archives.

Offline: python scripts/investigate_discrepancies.py --raw-dir data/raw --output data/processed/discrepancy_investigation.json
Downloads are intentionally separate; see docs/discrepancy-investigation.md.
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from abstention_spatial.pipeline import input_receipt
from abstention_spatial.sources import save_json
from abstention_spatial.tse_etl import digits, read_csv_chunks, require_columns

KEYS = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA"]
COUNTS = ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]


def chunks(path, member, year):
    for chunk in read_csv_chunks(path, member=member, chunksize=100000):
        require_columns(chunk, set(KEYS + COUNTS + ["CD_CARGO", "ANO_ELEICAO"]))
        if chunk.ANO_ELEICAO.ne(str(year)).any():
            raise ValueError("Mismatched archive year")
        if "DT_GERACAO" in chunk:
            generated = pd.to_datetime(chunk.DT_GERACAO, format="%d/%m/%Y", errors="raise").dt.date
            if generated.gt(date(2026, 10, 14)).any():
                raise ValueError("Source generation exceeds forecasting cutoff")
        chunk = chunk.loc[chunk.CD_CARGO.eq("1")].copy()
        if not chunk.NR_TURNO.isin(["1", "2"]).all():
            raise ValueError("Unexpected historical round")
        chunk["CD_MUNICIPIO"] = digits(chunk.CD_MUNICIPIO, "CD_MUNICIPIO", maxlen=5).str.zfill(5)
        chunk["NR_ZONA"] = digits(chunk.NR_ZONA, "NR_ZONA", maxlen=4).str.zfill(4)
        for c in COUNTS:
            chunk[c] = pd.to_numeric(digits(chunk[c], c)).astype("int64")
        yield chunk


def investigate(raw_dir):
    result = {"cutoff_date": "2026-10-14", "years": {}}
    for year in (2014, 2018):
        section_path = raw_dir / f"detalhe_votacao_secao_{year}.zip"
        zone_path = raw_dir / f"detalhe_votacao_munzona_{year}.zip"
        section_member = f"detalhe_votacao_secao_{year}_BR.csv"
        zone_member = f"detalhe_votacao_munzona_{year}_BR.csv"
        frames, evidence = [], []
        section_rows = 0
        for chunk in chunks(section_path, section_member, year):
            require_columns(chunk, {"NR_SECAO"})
            section_rows += len(chunk)
            chunk["residual"] = chunk.QT_APTOS - chunk.QT_COMPARECIMENTO - chunk.QT_ABSTENCOES
            domestic = chunk.SG_UF.ne("ZZ")
            selected = domestic & (chunk.residual.ne(0) if year == 2014 else chunk.QT_COMPARECIMENTO.eq(0))
            # Only the six relevant public aggregate section rows are retained.
            evidence.extend(chunk.loc[selected].to_dict("records"))
            frames.append(chunk.groupby(KEYS, as_index=False)[COUNTS].sum())
        sections = pd.concat(frames).groupby(KEYS, as_index=False)[COUNTS].sum()
        zones = pd.concat(list(chunks(zone_path, zone_member, year)))
        # Section exports have no transit flag; aggregate N and S at zone grain.
        zones = zones.groupby(KEYS, as_index=False)[COUNTS].sum()
        comparison = zones.merge(sections, on=KEYS, how="outer", suffixes=("_zone", "_section"), indicator=True)
        difference = comparison["_merge"].ne("both")
        for c in COUNTS:
            comparison[c + "_difference"] = comparison[c + "_zone"] - comparison[c + "_section"]
            difference |= comparison[c + "_difference"].ne(0)
        result["years"][str(year)] = {
            "section_archive": input_receipt(section_path), "zone_archive": input_receipt(zone_path),
            "section_member": section_member, "zone_member": zone_member,
            "presidential_section_rows": section_rows, "compared_zone_keys": len(comparison),
            "zone_keys_with_differences": int(difference.sum()),
            "selected_section_evidence": evidence,
            "state_totals": zones.groupby(["NR_TURNO", "SG_UF"], as_index=False)[COUNTS].sum().to_dict("records"),
        }
    # Independent PDF transcriptions: 296_BR_BRASIL_2018_T2_PRESIDENTE.pdf.
    # Keep raw source differences and the report's separate category visible.
    references = {
        "ES": {"page": 16, "eligible": 2754749, "turnout": 2178495,
               "absent": 575920, "uncounted_section_electors": 334},
        "PR": {"page": 36, "eligible": 7972415, "turnout": 6595854,
               "absent": 1376226, "uncounted_section_electors": 335},
    }
    comparisons = []
    for uf, ref in references.items():
        observed = next(r for r in result["years"]["2018"]["state_totals"]
                        if r["SG_UF"] == uf and r["NR_TURNO"] == "2")
        comparisons.append({"uf": uf, "report": ref, "observed": observed,
                            "difference": {name: observed[column] - ref[name]
                                           for name, column in zip(("eligible", "turnout", "absent"), COUNTS)}})
    result["2018_state_report_comparisons"] = comparisons
    result["2018_state_report_source"] = {
        "archive": input_receipt(raw_dir / "Relatorio_Resultado_Totalizacao_2018_BR.zip"),
        "member": "296_BR_BRASIL_2018_T2_PRESIDENTE.pdf", "published_date": "2019-02-27",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/discrepancy_investigation.json"))
    args = parser.parse_args()
    result = investigate(args.raw_dir)
    save_json(args.output, result)
    for year, audit in result["years"].items():
        print(year, audit["compared_zone_keys"], "keys;", audit["zone_keys_with_differences"], "differences")
    return int(any(x["zone_keys_with_differences"] for x in result["years"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
