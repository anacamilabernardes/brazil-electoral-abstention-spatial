"""Independently reopen section outputs and compare them with TSE zone counts."""
import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from abstention_spatial.sources import official_path, save_json, sha256_file
from abstention_spatial.tse_etl import read_munzona


def verify(raw_dir, output_dir):
    qa = json.loads((output_dir / "section_qa_report.json").read_text(encoding="utf-8"))
    for name, expected in qa["artifacts"].items():
        if sha256_file(output_dir / name) != expected["sha256"]:
            raise ValueError(f"Output hash mismatch: {name}")
    db = sqlite3.connect(output_dir / "section_panel.sqlite")
    try:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        if db.execute("SELECT COUNT(*) FROM sections WHERE year=2026 AND round<>1").fetchone()[0]:
            raise ValueError("2026 future-round leakage")
        if db.execute("SELECT COUNT(*) FROM sections WHERE eligible<>turnout+absent+uninstalled+unaccounted").fetchone()[0]:
            raise ValueError("Section count identity failed")
        observed = pd.read_sql_query("SELECT year,round,uf,tse_code,electoral_zone,SUM(eligible) AS eligible,SUM(turnout) AS turnout,SUM(absent) AS absent,SUM(uninstalled) AS uninstalled,SUM(unaccounted) AS unaccounted FROM sections GROUP BY year,round,uf,tse_code,electoral_zone", db)
        counts = ["eligible", "turnout", "absent", "uninstalled", "unaccounted"]
        keys = ["year", "round", "uf", "tse_code", "electoral_zone"]
        expected_frames=[]
        for year in qa["years"]:
            zones, _ = read_munzona(official_path(f"tse-munzona-{year}",raw_dir),year,allow_discrepancies=True)
            zones=zones.loc[zones.uf.isin(qa["selected_ufs"])]
            expected_frames.append(zones.groupby(keys,as_index=False)[counts].sum())
        expected=pd.concat(expected_frames,ignore_index=True)
        comparison=observed.merge(expected,on=keys,how="outer",suffixes=("_sections","_zones"),indicator=True)
        bad=comparison["_merge"].ne("both")
        for c in counts:
            comparison[c+"_difference"]=comparison[c+"_sections"]-comparison[c+"_zones"]
            bad |= comparison[c+"_difference"].ne(0)
        mismatches=comparison.loc[bad]
        mismatches.to_csv(output_dir / "section_zone_mismatches.csv",index=False)
        # Read the portable export independently, using only necessary columns.
        exported_rows=0
        exported={c:0 for c in counts}
        for chunk in pd.read_csv(output_dir / "section_panel.csv.gz",usecols=["year","round"]+counts,chunksize=100000):
            if ((chunk.year==2026)&(chunk["round"]!=1)).any():
                raise ValueError("CSV contains excluded outcomes")
            exported_rows+=len(chunk)
            for c in counts:exported[c]+=int(chunk[c].sum())
        stored={c:int(observed[c].sum()) for c in counts}
        if exported_rows!=qa["rows"] or exported!=stored:
            raise ValueError("CSV and SQLite rows/counts differ")
        zero_turnout=pd.read_sql_query("SELECT year,round,uf,tse_code,electoral_zone,section_id,municipality_code,eligible,turnout,absent,uninstalled,unaccounted,section_installed,count_quality FROM sections WHERE eligible>0 AND turnout=0 ORDER BY year,round,uf,tse_code,electoral_zone,section_id",db)
        zero_turnout["section_installed"] = zero_turnout["section_installed"].astype("Int64")
        zero_turnout.to_csv(output_dir / "section_zero_turnout_review.csv",index=False)
        result={"status":"verified" if mismatches.empty else "zone_mismatch", "cutoff_date":qa["cutoff_date"],"rows":exported_rows,"csv_sqlite_totals":stored,"zone_keys_compared":len(comparison),"zone_keys_with_mismatches":len(mismatches),"zone_keys_by_year":comparison.groupby("year").size().to_dict(),"zero_turnout_positive_eligible_rows":len(zero_turnout),"state_coverage":qa["state_coverage"]}
        save_json(output_dir / "section_validation.json",result)
        return result
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir",type=Path,default=Path("data/raw"))
    parser.add_argument("--output-dir",type=Path,default=Path("data/processed/sections-national"))
    args=parser.parse_args()
    result=verify(args.raw_dir,args.output_dir)
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="verified" else 1


if __name__=="__main__":
    raise SystemExit(main())
