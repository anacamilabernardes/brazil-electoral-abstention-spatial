"""Verify saved ETL CSVs and GeoPackage without loading all repeated geometries."""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from abstention_spatial.core import validate_municipal_panel
from abstention_spatial.sources import receipt, save_json
from abstention_spatial.tse_etl import COUNT_COLUMNS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--geopackage", type=Path, required=True)
    args = parser.parse_args()
    panel = validate_municipal_panel(pd.read_csv(args.processed_dir / "municipal_panel.csv",
                                                dtype={"municipality_code": str}))
    if panel.loc[panel.year == 2026, "round"].ne(1).any():
        raise ValueError("Unexpected 2026 second-round data")
    db = sqlite3.connect(args.geopackage)
    try:
        if db.execute("pragma quick_check").fetchone()[0] != "ok":
            raise ValueError("GeoPackage failed SQLite integrity check")
        if db.execute("select count(*) from municipal_panel").fetchone()[0] != len(panel):
            raise ValueError("GeoPackage panel row count differs from CSV")
        for column in COUNT_COLUMNS:
            if db.execute(f"select sum({column}) from municipal_panel").fetchone()[0] != int(panel[column].sum()):
                raise ValueError(f"GeoPackage {column} total differs from CSV")
        if db.execute("select count(*) from municipalities_2025").fetchone()[0] != panel.municipality_code.nunique():
            raise ValueError("GeoPackage geometry coverage differs from CSV")
        if db.execute("select count(*) from municipal_panel where year=2026 and round=2").fetchone()[0]:
            raise ValueError("GeoPackage contains 2026 second-round data")
        if db.execute("select count(*) from (select municipality_code,year,round,count(*) n from municipal_panel group by 1,2,3 having n>1)").fetchone()[0]:
            raise ValueError("Duplicate GeoPackage panel keys")
        layers = db.execute("select table_name,srs_id from gpkg_contents").fetchall()
        if dict(layers) != {"municipalities_2025": 4674, "municipal_panel": 4674}:
            raise ValueError("Unexpected GeoPackage layers or CRS")
    finally:
        db.close()
    files = list(args.processed_dir.glob("*.csv")) + [args.geopackage]
    result = {"status": "verified", "panel_rows": len(panel),
              "unique_municipalities": int(panel.municipality_code.nunique()),
              "gpkg_layers": layers, "artifacts": {p.name: receipt(p) for p in files}}
    save_json(args.processed_dir / "artifact_validation.json", result)
    print(result["status"], result["panel_rows"])


if __name__ == "__main__":
    main()
