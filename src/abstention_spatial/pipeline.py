"""Reproducible TSE -> IBGE municipal spatial panel pipeline.

Command-line entry point: python -m abstention_spatial.pipeline
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from .ibge_etl import geometry_coverage, load_ibge_boundaries
from .sources import OFFICIAL_ARCHIVES, download_official, official_path, receipt, save_json
from .tse_etl import YEARS, harmonize_zones, load_crosswalk, read_munzona

FORECAST_CUTOFF = date(2026, 10, 14)
SECOND_ROUND_DATE = date(2026, 10, 25)
UF_CODES = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def cutoff_round(year: int, cutoff: date) -> int:
    """Enforce conservative pre-election partition on the 2026 archive."""
    if year == 2026:
        if cutoff < date(2026, 10, 4):
            raise ValueError("First-round 2026 turnout was not observable by this cutoff")
        return 1 if cutoff < SECOND_ROUND_DATE else 2
    if cutoff.year < year:
        raise ValueError(f"Year {year} is in the future relative to cutoff")
    return 2


def _write_csv(frame: pd.DataFrame, file: Path) -> None:
    frame.to_csv(file, index=False, encoding="utf-8")


def build(
    *, raw_dir: Path, output_dir: Path, spatial_dir: Path,
    years: tuple[int, ...] = YEARS, cutoff: date = FORECAST_CUTOFF,
    crosswalk_file: Path | None = None, ibge_file: Path | None = None,
    crosswalk_columns: tuple[str, str, str] | None = None,
    members: dict[int, str] | None = None,
    chunksize: int = 200_000, allow_partial_coverage: bool = False,
) -> dict:
    """Create validated CSV + GeoPackage outputs; refuse partial or unmatched inputs.

    No source is fetched implicitly. Build is offline to make backtests
    reproducible. All artifact writes are staged before committing outputs.
    """
    raw_dir, output_dir, spatial_dir = map(Path, (raw_dir, output_dir, spatial_dir))
    years = tuple(sorted(set(years)))
    if not years or any(y not in YEARS for y in years):
        raise ValueError(f"years must be a nonempty subset of {YEARS}")
    if output_dir.resolve() == spatial_dir.resolve():
        raise ValueError("output_dir and spatial_dir must be distinct")
    mapping = Path(crosswalk_file) if crosswalk_file else official_path("tse-ibge-crosswalk", raw_dir)
    geometry = Path(ibge_file) if ibge_file else official_path("ibge-municipalities-2025", raw_dir)
    archives = {y: official_path(f"tse-munzona-{y}", raw_dir) for y in years}
    inputs = {"crosswalk": mapping, "ibge_boundaries": geometry,
              **{f"tse_munzona_{y}": p for y, p in archives.items()}}
    missing = [str(p) for p in inputs.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing offline official inputs: {missing}")
    if chunksize < 1:
        raise ValueError("chunksize must be positive")

    crosswalk = load_crosswalk(mapping, columns=crosswalk_columns)
    read_reports = {}
    zones_by_year = []
    for y in years:
        max_round = cutoff_round(y, cutoff)
        zones, report = read_munzona(
            archives[y], y, max_round=max_round,
            member=(members or {}).get(y), chunksize=chunksize,
        )
        read_reports[str(y)] = report
        zones_by_year.append(zones)
    zones = pd.concat(zones_by_year, ignore_index=True)
    unexpected_ufs = set(zones["uf"]) - UF_CODES
    if unexpected_ufs:
        raise ValueError(f"Unknown domestic UF identifiers: {sorted(unexpected_ufs)}")
    state_coverage = {}
    for (year, turn), subset in zones.groupby(["year", "round"]):
        observed = set(subset["uf"])
        missing_ufs = sorted(UF_CODES - observed)
        state_coverage[f"{year}-{turn}"] = {
            "uf_count": len(observed), "missing_ufs": missing_ufs,
        }
        if missing_ufs and not allow_partial_coverage:
            raise ValueError(
                f"Incomplete national source for {year} round {turn}; "
                f"missing UFs: {missing_ufs}; use --allow-partial only for a regional study"
            )
    domestic_zones, panel = harmonize_zones(zones, crosswalk)
    boundaries = load_ibge_boundaries(geometry)
    panel_geometries, geo_report = geometry_coverage(panel, boundaries)
    if len(panel_geometries) != panel["municipality_code"].nunique():
        raise ValueError("Spatial join is not one-to-one")
    # Foreign districts are intentionally excluded, and documented in the QA output.
    # National totals are domestic only, matching the municipal spatial universe.
    nation = panel.groupby(["year", "round"], as_index=False)[
        ["eligible", "turnout", "absent"]
    ].sum()
    nation["abstention_rate"] = nation["absent"] / nation["eligible"]

    report = {
        "status": "complete_from_supplied_archives_not_officially_reconciled",
        "cutoff_date": cutoff.isoformat(),
        "years": list(years),
        "reference_geometry_year": 2025,
        "source_files": {name: receipt(path, source_url=(OFFICIAL_ARCHIVES.get(
            f"tse-munzona-{name.split('_')[-1]}" if name.startswith("tse_munzona")
            else ("tse-ibge-crosswalk" if name == "crosswalk" else "ibge-municipalities-2025")
        ))) for name, path in inputs.items()},
        "row_counts": {
            "zones": len(domestic_zones),
            "municipal_panel": len(panel),
            "unique_municipalities": int(panel["municipality_code"].nunique()),
        },
        "source_audit": read_reports,
        "geography_audit": geo_report,
        "state_coverage": state_coverage,
        "allow_partial_coverage": allow_partial_coverage,
        "national_domestic_by_year_round": nation.to_dict("records"),
        "warnings": [
            "Totals are domestic only; foreign voting district ZZ is excluded from the IBGE spatial panel.",
            "A 2025 crosswalk and municipal boundary vintage were applied to historical years; audit changes in municipal geography.",
            "TSE reports 39 duplicated eligible registrations in its 2026 results/TTE files; do not allocate or subtract them by municipality without documented evidence.",
            "Published official totals have not been checked externally by this offline build; reconcile before interpreting or publishing forecasts.",
            "2026 second-round observations cannot be used before 25 October 2026; cutoff enforced in code.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    spatial_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="abstention_etl_") as staging_dir:
        stage = Path(staging_dir)
        csv_stage = stage / "csv"
        shp_stage = stage / "spatial"
        csv_stage.mkdir()
        shp_stage.mkdir()
        _write_csv(domestic_zones, csv_stage / "municipal_zone_turnout.csv")
        _write_csv(panel, csv_stage / "municipal_panel.csv")
        _write_csv(crosswalk, csv_stage / "municipality_crosswalk.csv")
        _write_csv(nation, csv_stage / "domestic_totals.csv")
        geo_target = shp_stage / "municipalities_2025.gpkg"
        panel_geometries.to_file(geo_target, driver="GPKG", layer="municipalities_2025")
        report["output_counts"] = {
            "municipal_panel_rows": len(pd.read_csv(csv_stage / "municipal_panel.csv")),
            "geometry_rows": len(panel_geometries),
        }
        save_json(csv_stage / "etl_qa_report.json", report)
        # Outputs are only published after *all* validation and staging completes.
        output_dir.mkdir(parents=True, exist_ok=True)
        spatial_dir.mkdir(parents=True, exist_ok=True)
        for file in csv_stage.iterdir():
            file.replace(output_dir / file.name)
        geo_target.replace(spatial_dir / geo_target.name)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline reproducible TSE/IBGE spatial ETL")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sources", help="Print verified official source URLs")
    downloader = sub.add_parser("download", help="Download explicitly selected official archives")
    downloader.add_argument("--names", nargs="+", required=True, choices=sorted(OFFICIAL_ARCHIVES))
    downloader.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    builder = sub.add_parser("build", help="Build the validated municipal spatial panel offline")
    builder.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    builder.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    builder.add_argument("--spatial-dir", type=Path, default=Path("data/geospatial"))
    builder.add_argument("--years", nargs="+", type=int, default=list(YEARS))
    builder.add_argument("--cutoff", type=date.fromisoformat, default=FORECAST_CUTOFF)
    builder.add_argument("--crosswalk", type=Path)
    builder.add_argument("--ibge", type=Path)
    builder.add_argument("--crosswalk-columns", nargs=3, metavar=("TSE", "IBGE", "UF"))
    builder.add_argument("--chunksize", type=int, default=200_000)
    builder.add_argument("--allow-partial", action="store_true", help="Accept incomplete UF coverage for an explicitly regional study")
    args = parser.parse_args(argv)
    if args.command == "sources":
        for name, url in OFFICIAL_ARCHIVES.items():
            print(f"{name}: {url}")
    elif args.command == "download":
        for name in args.names:
            rec = download_official(name, args.raw_dir)
            print(json.dumps(rec, ensure_ascii=False))
    elif args.command == "build":
        report = build(raw_dir=args.raw_dir, output_dir=args.output_dir,
                       spatial_dir=args.spatial_dir, years=tuple(args.years),
                       cutoff=args.cutoff, crosswalk_file=args.crosswalk,
                       ibge_file=args.ibge,
                       crosswalk_columns=tuple(args.crosswalk_columns) if args.crosswalk_columns else None,
                       chunksize=args.chunksize,
                       allow_partial_coverage=args.allow_partial)
        print(json.dumps({"status": report["status"], "row_counts": report["row_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
