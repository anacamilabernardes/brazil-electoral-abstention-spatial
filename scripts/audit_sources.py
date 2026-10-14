"""Inspect downloaded official schemas and run a derived Brasília smoke test offline.

Usage: python scripts/audit_sources.py --raw-dir data/raw --output-dir data/processed/audit
"""
import argparse
import csv
import io
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd

from abstention_spatial.pipeline import build
from abstention_spatial.sources import OFFICIAL_ARCHIVES, official_path, receipt, save_json
from abstention_spatial.tse_etl import YEARS, load_crosswalk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/audit"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit = {"sources": {}, "election_schemas": {}}
    for key in OFFICIAL_ARCHIVES:
        path = official_path(key, args.raw_dir)
        with ZipFile(path) as archive:
            audit["sources"][key] = {
                **receipt(path, source_url=OFFICIAL_ARCHIVES[key]),
                "members": [{"name": i.filename, "uncompressed_bytes": i.file_size}
                            for i in archive.infolist()],
            }
            if key.startswith("tse-munzona-"):
                year = int(key.rsplit("-", 1)[1])
                schemas = {}
                for scope in ("BR", "BRASIL", "AC"):
                    member = f"detalhe_votacao_munzona_{year}_{scope}.csv"
                    with archive.open(member) as binary:
                        reader = csv.DictReader(io.TextIOWrapper(binary, encoding="latin-1"), delimiter=";")
                        rows = list(reader)
                    schemas[scope] = {
                        "columns": reader.fieldnames, "rows": len(rows),
                        "presidential_rows": sum(r["CD_CARGO"] == "1" for r in rows),
                        "presidential_ufs": sorted({r["SG_UF"] for r in rows if r["CD_CARGO"] == "1"}),
                    }
                audit["election_schemas"][str(year)] = schemas
    crosswalk = load_crosswalk(official_path("tse-ibge-crosswalk", args.raw_dir))
    audit["crosswalk_rows"] = len(crosswalk)
    geometry = official_path("ibge-municipalities-2025", args.raw_dir)
    boundaries = gpd.read_file(f"zip://{geometry.resolve().as_posix()}")
    audit["ibge_schema"] = {"columns": list(boundaries.columns), "features": len(boundaries),
                            "crs": str(boundaries.crs), "invalid": int((~boundaries.is_valid).sum())}
    save_json(args.output_dir / "source_schema_audit.json", audit)

    # Exact official rows, selected without modifying any count or identifier.
    subset = args.output_dir / "smoke_raw"
    subset.mkdir(exist_ok=True)
    original = official_path("tse-munzona-2026", args.raw_dir)
    member = "detalhe_votacao_munzona_2026_BR.csv"
    with ZipFile(original) as archive, archive.open(member) as binary:
        reader = csv.DictReader(io.TextIOWrapper(binary, encoding="latin-1"), delimiter=";")
        fields = reader.fieldnames
        rows = [r for r in reader if r["SG_UF"] == "DF" and r["NR_TURNO"] == "1"]
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=fields, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    with ZipFile(subset / original.name, "w") as archive:
        archive.writestr(member, text.getvalue().encode("latin-1"))
    save_json(subset / "subset_provenance.json", {
        "parent": receipt(original, source_url=OFFICIAL_ARCHIVES["tse-munzona-2026"]),
        "member": member, "filter": {"SG_UF": "DF", "NR_TURNO": "1"}, "rows": len(rows),
    })
    result = build(raw_dir=subset, output_dir=args.output_dir / "smoke",
                   spatial_dir=args.output_dir / "smoke_geo", years=(2026,),
                   crosswalk_file=official_path("tse-ibge-crosswalk", args.raw_dir),
                   ibge_file=geometry, allow_partial_coverage=True, chunksize=7)
    print(result["row_counts"])


if __name__ == "__main__":
    main()
