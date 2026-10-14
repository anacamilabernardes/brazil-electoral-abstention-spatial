"""Chunked national presidential section turnout ETL with SQLite integrity gates."""
from __future__ import annotations

import argparse
import gzip
import io
import json
import sqlite3
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from .pipeline import FORECAST_CUTOFF, cutoff_round, input_receipt
from .sources import official_path, receipt, save_json
from .tse_etl import COUNTS, UF_CODES, YEARS, canon, digits, load_crosswalk, read_csv_chunks, require_columns

KEY = ["year", "round", "uf", "tse_code", "electoral_zone", "section_id"]
COLUMNS = KEY + ["municipality_code", "polling_place_code", "eligible", "turnout", "absent",
                 "uninstalled", "unaccounted", "abstention_rate", "section_installed",
                 "section_annulled", "count_quality", "source_id", "source_row",
                 "source_generated_date", "cutoff_date"]
REQUIRED = {"ANO_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO",
            "CD_CARGO", "DT_GERACAO", *COUNTS}
UNKNOWN = {"", "NULO", "NE", "1", "3"}
RAW_UNKNOWN = {"", "#NULO#", "#NE#", "-1", "-3"}


def flag(series: pd.Series) -> pd.Series:
    """Keep unknown source flags null, rather than assuming a section functioned."""
    text = series.map(canon)
    if not text.isin({"SIM", "S", "NAO", "N"} | UNKNOWN).all():
        raise ValueError("Unexpected section status flag")
    return text.map({"SIM": 1, "S": 1, "NAO": 0, "N": 0}).astype("Int64")


def normalize_chunk(frame: pd.DataFrame, year: int, *, cutoff: date = FORECAST_CUTOFF,
                    allow_discrepancies: bool = False) -> tuple[pd.DataFrame, dict]:
    """Normalize one chunk, excluding foreign and future-round rows before counts."""
    max_round = cutoff_round(year, cutoff)
    require_columns(frame, REQUIRED)
    if frame.ANO_ELEICAO.str.strip().ne(str(year)).any():
        raise ValueError("Mismatched ANO_ELEICAO")
    office = frame.CD_CARGO.str.strip().str.lstrip("0").eq("1")
    stats = {"source_rows": len(frame), "other_office_rows": int((~office).sum()),
             "future_round_rows": 0, "foreign_rows": 0}
    out = frame.loc[office].copy()
    out["source_row"] = out.index + 1  # logical CSV record, excluding the header
    turns = digits(out.NR_TURNO, "NR_TURNO")
    if not turns.isin(["1", "2"]).all():
        raise ValueError("Unexpected presidential round")
    stats["future_round_rows"] = int(turns.astype(int).gt(max_round).sum())
    out = out.loc[turns.astype(int).le(max_round)].copy()
    out["uf"] = out.SG_UF.str.strip().str.upper()
    stats["foreign_rows"] = int(out.uf.eq("ZZ").sum())
    out = out.loc[out.uf.ne("ZZ")].copy()
    if not out.uf.isin(UF_CODES).all():
        raise ValueError("Unknown domestic UF")
    generated = pd.to_datetime(out.DT_GERACAO, format="%d/%m/%Y", errors="raise")
    if generated.dt.date.gt(cutoff).any():
        raise ValueError("Source generation exceeds cutoff")
    for field in ["DT_ELEICAO", "DT_RECEBIMENTO_BU_HOR_TSE", "DT_PRIM_TOT_PARCIAL_HOR_TSE"]:
        if field in out:
            values = out[field].loc[~out[field].str.strip().isin(RAW_UNKNOWN)]
            if not values.empty:
                parsed = pd.to_datetime(values.str.slice(0, 10), format="%d/%m/%Y", errors="raise")
                if parsed.dt.date.gt(cutoff).any():
                    raise ValueError(f"{field} exceeds cutoff")
    out["year"] = year
    out["round"] = out.NR_TURNO.astype(int)
    out["tse_code"] = digits(out.CD_MUNICIPIO, "CD_MUNICIPIO", maxlen=5).str.zfill(5)
    out["electoral_zone"] = digits(out.NR_ZONA, "NR_ZONA", maxlen=4).str.zfill(4)
    out["section_id"] = digits(out.NR_SECAO, "NR_SECAO").str.zfill(4)
    out["polling_place_code"] = pd.Series(pd.NA, index=out.index, dtype="string")
    if "NR_LOCAL_VOTACAO" in out:
        available = ~out.NR_LOCAL_VOTACAO.str.strip().isin(RAW_UNKNOWN)
        out.loc[available, "polling_place_code"] = digits(out.loc[available, "NR_LOCAL_VOTACAO"], "NR_LOCAL_VOTACAO").str.zfill(4)
    for original, normalized in COUNTS.items():
        out[normalized] = pd.to_numeric(digits(out[original], original)).astype("int64")
    for original, normalized in [("ST_SECAO_INSTALADA", "section_installed"),
                                 ("ST_SECAO_ANULADA", "section_annulled")]:
        out[normalized] = flag(out[original]) if original in out else pd.Series(pd.NA, index=out.index, dtype="Int64")
    residual = out.eligible - out.turnout - out.absent
    not_installed = out.section_installed.eq(0).fillna(False)
    if ((out.turnout.gt(0) | out.absent.gt(0)) & not_installed).any():
        raise ValueError("Uninstalled section has turnout or abstention counts")
    out["uninstalled"] = out.eligible.where(not_installed, 0)
    out["unaccounted"] = residual - out.uninstalled
    if out.unaccounted.lt(0).any():
        raise ValueError("Negative source count residual")
    if not allow_discrepancies and out.unaccounted.ne(0).any():
        raise ValueError("Unexplained source count residual; explicit audit opt-in required")
    out["abstention_rate"] = out.absent.div(out.eligible.where(out.eligible.ne(0)))
    out["count_quality"] = "balanced"
    out.loc[out.eligible.eq(0), "count_quality"] = "zero_eligible"
    out.loc[out.uninstalled.gt(0), "count_quality"] = "uninstalled"
    out.loc[out.unaccounted.gt(0), "count_quality"] = "unaccounted"
    out["source_id"] = f"tse-sections-{year}"
    out["source_generated_date"] = generated.dt.strftime("%Y-%m-%d")
    out["cutoff_date"] = cutoff.isoformat()
    if out.duplicated(KEY).any():
        raise ValueError("Duplicate section key within source chunk")
    return out, stats


def export_csv(db: sqlite3.Connection, target: Path, chunksize: int) -> None:
    # Stable column and key order, and fixed gzip metadata, for reproducible exports.
    with target.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary,mode="wb",filename="",mtime=0) as compressed:
            with io.TextIOWrapper(compressed,encoding="utf-8",newline="") as text:
                first = True
                for chunk in pd.read_sql_query("SELECT * FROM sections ORDER BY year,round,uf,tse_code,electoral_zone,section_id", db, chunksize=chunksize):
                    # SQLite nullable flags otherwise become 1.0/0.0 in
                    # chunks spanning a legacy year with missing flags.
                    for field in ("section_installed", "section_annulled"):
                        chunk[field] = chunk[field].astype("Int64")
                    chunk.to_csv(text,index=False,header=first,lineterminator="\n")
                    first = False


def create_table(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE sections (
        year INTEGER NOT NULL CHECK(year IN (2014,2018,2022,2026)),
        round INTEGER NOT NULL CHECK(round IN (1,2) AND NOT(year=2026 AND round=2)),
        uf TEXT NOT NULL, tse_code TEXT NOT NULL, electoral_zone TEXT NOT NULL,
        section_id TEXT NOT NULL, municipality_code TEXT NOT NULL, polling_place_code TEXT,
        eligible INTEGER NOT NULL CHECK(eligible>=0), turnout INTEGER NOT NULL CHECK(turnout>=0),
        absent INTEGER NOT NULL CHECK(absent>=0), uninstalled INTEGER NOT NULL CHECK(uninstalled>=0),
        unaccounted INTEGER NOT NULL CHECK(unaccounted>=0), abstention_rate REAL,
        section_installed INTEGER CHECK(section_installed IN (0,1)),
        section_annulled INTEGER CHECK(section_annulled IN (0,1)), count_quality TEXT NOT NULL,
        source_id TEXT NOT NULL, source_row INTEGER NOT NULL, source_generated_date TEXT NOT NULL,
        cutoff_date TEXT NOT NULL,
        PRIMARY KEY(year,round,uf,tse_code,electoral_zone,section_id),
        CHECK(eligible=turnout+absent+uninstalled+unaccounted)) WITHOUT ROWID""")


def build_sections(*, raw_dir: Path, output_dir: Path, years: tuple[int, ...] = YEARS,
                   cutoff: date = FORECAST_CUTOFF, chunksize: int = 25000,
                   allow_discrepancies: bool = False, ufs: tuple[str, ...] | None = None) -> dict:
    """Offline, bounded-memory build; publish a SQLite base and deterministic CSV.gz."""
    years = tuple(sorted(set(years)))
    if not years or any(y not in YEARS for y in years):
        raise ValueError("Unsupported section years")
    for y in years:
        cutoff_round(y, cutoff)
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    selected_ufs = set(ufs) if ufs else set(UF_CODES)
    if not selected_ufs or not selected_ufs.issubset(UF_CODES):
        raise ValueError("Unknown UF filter")
    raw_dir, output_dir = Path(raw_dir), Path(output_dir)
    crosswalk_path = official_path("tse-ibge-crosswalk", raw_dir)
    crosswalk = load_crosswalk(crosswalk_path)
    inputs = {f"tse-sections-{y}": official_path(f"tse-sections-{y}", raw_dir) for y in years}
    report = {"cutoff_date": cutoff.isoformat(), "years": list(years), "office": "president",
              "selected_ufs": sorted(selected_ufs), "chunksize": chunksize, "source_audit": {},
              "source_files": {k: input_receipt(p) for k, p in inputs.items()},
              "crosswalk": input_receipt(crosswalk_path), "warnings": [
                  "Section identifiers are election-specific; no historical section correspondence is inferred.",
                  "Foreign district ZZ is excluded. These are domestic presidential turnout records.",
                  "Unknown section status remains null. Zero counts do not establish why a section did not function.",
                  "Polling-place codes are identifiers, not coordinates or geocoded establishments.",
                  "Counts are preserved from source snapshots; report-category discrepancies remain documented.",
              ]}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="section_etl_", dir=output_dir.parent) as folder:
        stage = Path(folder)
        target = stage / "section_panel.sqlite"
        db = sqlite3.connect(target)
        try:
            db.execute("PRAGMA cache_size=-32768")
            db.execute("PRAGMA temp_store=FILE")
            create_table(db)
            for y, path in ((y, inputs[f"tse-sections-{y}"]) for y in years):
                member = f"detalhe_votacao_secao_{y}_BR.csv"
                with zipfile.ZipFile(path) as archive:
                    if archive.namelist().count(member) != 1:
                        raise ValueError(f"Expected exactly one national presidential section member: {member}")
                    members = [{"name": m.filename, "bytes_uncompressed": m.file_size} for m in archive.infolist()]
                audit = {"member": member, "members": members, "schema": [], "source_rows": 0,
                         "other_office_rows": 0, "future_round_rows": 0, "foreign_rows": 0,
                         "uf_filter_excluded_rows": 0, "rows_written": 0}
                report["source_audit"][str(y)] = audit
                for raw in read_csv_chunks(path, member=member, chunksize=chunksize):
                    audit["schema"] = list(raw.columns)
                    chunk, stats = normalize_chunk(raw, y, cutoff=cutoff, allow_discrepancies=allow_discrepancies)
                    for field, value in stats.items():
                        audit[field] += value
                    audit["uf_filter_excluded_rows"] += int((~chunk.uf.isin(selected_ufs)).sum())
                    chunk = chunk.loc[chunk.uf.isin(selected_ufs)]
                    if chunk.empty:
                        continue
                    chunk = chunk.merge(crosswalk, on=["uf", "tse_code"], how="left", validate="many_to_one")
                    if chunk.municipality_code.isna().any():
                        raise ValueError("Unmapped section municipality")
                    records = chunk[COLUMNS].astype(object).where(chunk[COLUMNS].notna(), None)
                    try:
                        db.executemany("INSERT INTO sections VALUES (" + ",".join("?" for _ in COLUMNS) + ")",
                                       records.itertuples(index=False, name=None))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(f"Duplicate section key or invalid counts across chunks: {exc}") from exc
                    db.commit()
                    audit["rows_written"] += len(chunk)
                for turn in ([1] if y == 2026 else [1, 2]):
                    observed = {x[0] for x in db.execute("SELECT DISTINCT uf FROM sections WHERE year=? AND round=?", (y, turn))}
                    if observed != selected_ufs:
                        raise ValueError(f"Incomplete UF/round coverage: {y}-{turn}; missing {sorted(selected_ufs-observed)}")
            db.execute("CREATE INDEX sections_municipality ON sections(municipality_code,year,round)")
            totals = pd.read_sql_query("SELECT year,round,uf,COUNT(*) AS sections, SUM(eligible) AS eligible, SUM(turnout) AS turnout, SUM(absent) AS absent, SUM(uninstalled) AS uninstalled, SUM(unaccounted) AS unaccounted FROM sections GROUP BY year,round,uf", db)
            totals.to_csv(stage / "section_state_totals.csv", index=False)
            municipal = pd.read_sql_query("SELECT municipality_code,year,round,SUM(eligible) AS eligible,SUM(turnout) AS turnout,SUM(absent) AS absent,SUM(uninstalled) AS uninstalled,SUM(unaccounted) AS unaccounted FROM sections GROUP BY municipality_code,year,round", db)
            municipal.to_csv(stage / "section_municipal_totals.csv", index=False)
            report["state_coverage"] = [{"year": int(y), "round": int(t), "uf_count": int(g.uf.nunique()), "sections": int(g.sections.sum())} for (y,t),g in totals.groupby(["year","round"])]
            report["national_domestic_by_year_round"] = totals.groupby(["year","round"],as_index=False)[["sections","eligible","turnout","absent","uninstalled","unaccounted"]].sum().to_dict("records")
            report["quality_counts"] = pd.read_sql_query("SELECT year,round,count_quality,COUNT(*) AS rows,SUM(unaccounted) AS unaccounted FROM sections GROUP BY year,round,count_quality",db).to_dict("records")
            report["rows"] = int(db.execute("SELECT COUNT(*) FROM sections").fetchone()[0])
            report["unique_municipalities"] = int(db.execute("SELECT COUNT(DISTINCT municipality_code) FROM sections").fetchone()[0])
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            report["status"] = "complete_with_source_residuals" if any(x["unaccounted"] for x in report["quality_counts"]) else "complete"
            export_csv(db, stage / "section_panel.csv.gz", chunksize)
            db.commit()
        finally:
            db.close()
        report["artifacts"] = {p.name: receipt(p) for p in stage.iterdir()}
        save_json(stage / "section_qa_report.json", report)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Replace the potentially locked database first; use fresh run directories.
        target.replace(output_dir / target.name)
        for file in stage.iterdir():
            file.replace(output_dir / file.name)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir",type=Path,default=Path("data/raw"))
    parser.add_argument("--output-dir",type=Path,default=Path("data/processed/sections"))
    parser.add_argument("--years",nargs="+",type=int,default=list(YEARS))
    parser.add_argument("--cutoff",type=date.fromisoformat,default=FORECAST_CUTOFF)
    parser.add_argument("--chunksize",type=int,default=25000)
    parser.add_argument("--allow-discrepancies",action="store_true")
    parser.add_argument("--ufs",nargs="+",choices=sorted(UF_CODES))
    args=parser.parse_args(argv)
    report=build_sections(raw_dir=args.raw_dir,output_dir=args.output_dir,years=tuple(args.years),cutoff=args.cutoff,chunksize=args.chunksize,allow_discrepancies=args.allow_discrepancies,ufs=tuple(args.ufs) if args.ufs else None)
    print(json.dumps({"status":report["status"],"rows":report["rows"],"state_coverage":report["state_coverage"]},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
