"""Reproducible TSE -> IBGE municipal spatial panel pipeline.

Command-line entry point: python -m abstention_spatial.pipeline
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from .ibge_etl import geometry_coverage, load_ibge_boundaries
from .sources import OFFICIAL_ARCHIVES, download_official, official_path, receipt, save_json
from .tse_etl import COUNT_COLUMNS, YEARS, harmonize_zones, load_crosswalk, read_munzona

FORECAST_CUTOFF = date(2026, 10, 14)
UF_CODES = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def cutoff_round(year: int, cutoff: date) -> int:
    """Enforce conservative pre-election partition on the 2026 archive."""
    if cutoff > FORECAST_CUTOFF:
        raise ValueError("cutoff cannot exceed 2026-10-14")
    if year == 2026:
        if cutoff < date(2026, 10, 4):
            raise ValueError("First-round 2026 turnout was not observable by this cutoff")
        return 1
    if cutoff.year < year:
        raise ValueError(f"Year {year} is in the future relative to cutoff")
    return 2


def _write_csv(frame: pd.DataFrame, file: Path) -> None:
    frame.to_csv(file, index=False, encoding="utf-8")


def input_receipt(path: Path) -> dict:
    """Hash supplied bytes; only attribute a URL when a matching download receipt exists."""
    current = receipt(path)
    sidecar = path.with_suffix(path.suffix + ".receipt.json")
    if sidecar.is_file():
        downloaded = json.loads(sidecar.read_text(encoding="utf-8"))
        if downloaded.get("sha256") != current["sha256"]:
            raise ValueError(f"Input differs from its download receipt: {path}")
        current["download_receipt"] = downloaded
        current["source_url"] = downloaded.get("source_url")
    return current


def build(
    *, raw_dir: Path, output_dir: Path, spatial_dir: Path,
    years: tuple[int, ...] = YEARS, cutoff: date = FORECAST_CUTOFF,
    crosswalk_file: Path | None = None, ibge_file: Path | None = None,
    crosswalk_columns: tuple[str, str, str] | None = None,
    members: dict[int, str] | None = None,
    chunksize: int = 200_000, allow_partial_coverage: bool = False,
    allow_discrepancies: bool = False,
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
    for y in years:
        cutoff_round(y, cutoff)
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

    input_receipts = {name: input_receipt(path) for name, path in inputs.items()}
    crosswalk = load_crosswalk(mapping, columns=crosswalk_columns)
    read_reports = {}
    zones_by_year = []
    for y in years:
        max_round = cutoff_round(y, cutoff)
        zones, report = read_munzona(
            archives[y], y, max_round=max_round,
            member=(members or {}).get(y), chunksize=chunksize, cutoff=cutoff,
            allow_discrepancies=allow_discrepancies,
        )
        read_reports[str(y)] = report
        zones_by_year.append(zones)
    zones = pd.concat(zones_by_year, ignore_index=True)
    unexpected_ufs = set(zones["uf"]) - UF_CODES
    if unexpected_ufs:
        raise ValueError(f"Unknown domestic UF identifiers: {sorted(unexpected_ufs)}")
    if not allow_partial_coverage:
        for y in years:
            expected_rounds = {1} if y == 2026 else {1, 2}
            observed_rounds = set(zones.loc[zones["year"] == y, "round"])
            if observed_rounds != expected_rounds:
                raise ValueError(f"Incomplete round coverage for {y}: {sorted(observed_rounds)}")
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
        COUNT_COLUMNS
    ].sum()
    nation["abstention_rate"] = nation["absent"] / nation["eligible"]

    report = {
        "status": ("complete_with_unexplained_source_discrepancies_not_officially_reconciled"
                   if panel["unaccounted"].any() else
                   "complete_from_supplied_archives_not_officially_reconciled"),
        "cutoff_date": cutoff.isoformat(),
        "years": list(years),
        "reference_geometry_year": 2025,
        "source_files": input_receipts,
        "municipality_coverage_by_year_round": {
            f"{y}-{turn}": {
                "observed": int(group["municipality_code"].nunique()),
                "crosswalk_codes_without_observations": sorted(set(crosswalk["municipality_code"]) - set(group["municipality_code"])),
            } for (y, turn), group in panel.groupby(["year", "round"])
        },
        "row_counts": {
            "zones": len(domestic_zones),
            "municipal_panel": len(panel),
            "unique_municipalities": int(panel["municipality_code"].nunique()),
        },
        "source_audit": read_reports,
        "geography_audit": geo_report,
        "state_coverage": state_coverage,
        "allow_partial_coverage": allow_partial_coverage,
        "allow_discrepancies": allow_discrepancies,
        "national_domestic_by_year_round": nation.to_dict("records"),
        "warnings": [
            "Totals are domestic only; foreign voting district ZZ is excluded from the IBGE spatial panel.",
            "A cutoff-date crosswalk snapshot and 2025 municipal boundaries were applied to historical years; audit changes in municipal geography.",
            "TSE reports 39 duplicated eligible registrations in its 2026 results/TTE files; do not allocate or subtract them by municipality without documented evidence.",
            "Published official totals have not been checked externally by this offline build; reconcile before interpreting or publishing forecasts.",
            "2026 second-round observations are always excluded; cutoff cannot exceed 14 October 2026.",
            "Official absent counts are preserved. Uninstalled and unexplained electors are separate fields; review nonzero unaccounted before modeling.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    spatial_dir.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as staging:
        csv_stage = Path(staging.enter_context(tempfile.TemporaryDirectory(
            prefix="abstention_etl_", dir=output_dir.parent)))
        shp_stage = Path(staging.enter_context(tempfile.TemporaryDirectory(
            prefix="abstention_spatial_", dir=spatial_dir.parent)))
        _write_csv(domestic_zones, csv_stage / "municipal_zone_turnout.csv")
        _write_csv(panel, csv_stage / "municipal_panel.csv")
        _write_csv(crosswalk, csv_stage / "municipality_crosswalk.csv")
        _write_csv(nation, csv_stage / "domestic_totals.csv")
        geo_target = shp_stage / "municipalities_2025.gpkg"
        panel_geometries.to_file(geo_target, driver="GPKG", layer="municipalities_2025")
        spatial_panel = panel_geometries.merge(panel, on="municipality_code", validate="one_to_many")
        spatial_panel.to_file(geo_target, driver="GPKG", layer="municipal_panel")
        report["output_counts"] = {
            "municipal_panel_rows": len(pd.read_csv(csv_stage / "municipal_panel.csv")),
            "geometry_rows": len(panel_geometries),
        }
        save_json(csv_stage / "etl_qa_report.json", report)
        # Outputs are only published after *all* validation and staging completes.
        output_dir.mkdir(parents=True, exist_ok=True)
        spatial_dir.mkdir(parents=True, exist_ok=True)
        # On Windows a GIS reader can lock the destination GeoPackage. Attempt
        # its replacement first so that this failure cannot publish new CSVs.
        # This is not a multi-file filesystem transaction; use fresh run folders.
        geo_target.replace(spatial_dir / geo_target.name)
        for file in csv_stage.iterdir():
            file.replace(output_dir / file.name)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline reproducible TSE/IBGE spatial ETL")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sources", help="Print verified official source URLs")
    reconciler = sub.add_parser("reconcile", help="Compare a build QA report against reviewed official reference totals")
    reconciler.add_argument("--report", type=Path, required=True)
    reconciler.add_argument("--references", type=Path, required=True)
    reconciler.add_argument("--output", type=Path, required=True)
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
    builder.add_argument("--allow-discrepancies", action="store_true", help="Preserve unexplained positive count residuals in an explicitly flagged audit dataset")
    builder.add_argument("--member", action="append", default=[], metavar="YEAR=CSV", help="Override the reviewed national BR member for an election year")
    builder.add_argument("--allow-partial", action="store_true", help="Accept incomplete UF coverage for an explicitly regional study")
    args = parser.parse_args(argv)
    if args.command == "sources":
        for name, url in OFFICIAL_ARCHIVES.items():
            print(f"{name}: {url}")
    elif args.command == "reconcile":
        from .reconciliation import reconcile
        result = reconcile(json.loads(args.report.read_text(encoding="utf-8")), args.references)
        save_json(args.output, result)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "matched_available_references" else 1
    elif args.command == "download":
        for name in args.names:
            rec = download_official(name, args.raw_dir)
            print(json.dumps(rec, ensure_ascii=False))
    elif args.command == "build":
        report = build(raw_dir=args.raw_dir, output_dir=args.output_dir,
                       spatial_dir=args.spatial_dir, years=tuple(args.years),
                       cutoff=args.cutoff, crosswalk_file=args.crosswalk,
                       members=dict((int(item.split("=", 1)[0]), item.split("=", 1)[1]) for item in args.member),
                       allow_discrepancies=args.allow_discrepancies,
                       ibge_file=args.ibge,
                       crosswalk_columns=tuple(args.crosswalk_columns) if args.crosswalk_columns else None,
                       chunksize=args.chunksize,
                       allow_partial_coverage=args.allow_partial)
        print(json.dumps({"status": report["status"], "row_counts": report["row_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
