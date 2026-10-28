"""Compare source aggregates with independently transcribed official references."""
from datetime import date
from pathlib import Path

import pandas as pd

FORECAST_CUTOFF = date(2026, 10, 14)


def reconcile(report: dict, references: Path) -> dict:
    """Compare matched universes without modifying counts or concealing differences.

    References are reviewed CSV rows of national domestic or including-ZZ counts.
    Blank metrics mean not published, never zero or inferred. HTML references
    require a locator; PDF references require member and page provenance.
    """
    frame = pd.read_csv(references, dtype=str, keep_default_na=False)
    required = {"year", "round", "scope", "eligible", "turnout", "absent",
                "source_url", "published_date", "member", "pages"}
    if not required.issubset(frame):
        raise ValueError(f"Missing reference columns: {sorted(required - set(frame))}")
    if frame.duplicated(["year", "round", "scope"]).any():
        raise ValueError("Duplicate reference keys")
    if frame.empty:
        raise ValueError("Empty references")
    results = []
    for row in frame.to_dict("records"):
        kind = row.get("source_kind") or "pdf"
        if not row["source_url"].startswith("https://"):
            raise ValueError("Reference provenance is required")
        if kind == "pdf":
            if not row["member"] or not row["pages"]:
                raise ValueError("Reference provenance is required")
        elif kind == "html":
            if not row.get("locator"):
                raise ValueError("HTML reference locator is required")
        else:
            raise ValueError("Unknown reference source kind")
        published = row["published_date"]
        if len(published) == 4 and published.isdigit():
            # A catalog year establishes availability only before the cutoff year.
            # Do not invent a month/day or assume a cutoff-year publication was early.
            if int(published) >= FORECAST_CUTOFF.year:
                raise ValueError("Publication year does not establish availability by cutoff")
        elif date.fromisoformat(published) > FORECAST_CUTOFF:
            raise ValueError("Reference publication exceeds forecasting cutoff")
        year, turn = int(row["year"]), int(row["round"])
        if year == 2026 and turn != 1:
            raise ValueError("Second-round 2026 references are excluded")
        if row["scope"] not in {"domestic", "including_ZZ"}:
            raise ValueError("Unknown reference universe")
        observed = next((r for r in report["national_domestic_by_year_round"]
                         if r["year"] == year and r["round"] == turn), None)
        if observed is None:
            results.append({**row, "status": "not_processed"})
            continue
        metrics = [c for c in ("eligible", "turnout", "absent") if row[c] != ""]
        if not metrics:
            raise ValueError("Reference must publish at least one count")
        counts = {c: int(observed[c]) for c in metrics}
        if row["scope"] == "including_ZZ":
            foreign = report["source_audit"][str(year)]["zz_totals_by_round"].get(str(turn))
            if foreign is None:
                raise ValueError("Overseas reference requires recorded ZZ totals")
            counts = {c: counts[c] + int(foreign[c]) for c in counts}
        expected = {}
        for c in counts:
            if not row[c].isdigit():
                raise ValueError("Reference counts must be nonnegative integers")
            expected[c] = int(row[c])
        delta = {c: counts[c] - expected[c] for c in counts}
        results.append({**row, "observed": counts, "difference": delta,
                        "checked_metrics": metrics,
                        "unchecked_metrics": [c for c in ("eligible", "turnout", "absent") if c not in metrics],
                        "status": ("mismatch" if any(v != 0 for v in delta.values()) else
                                   "matched" if len(metrics) == 3 else "matched_partial")})
    return {"status": "mismatch" if any(r["status"] == "mismatch" for r in results)
            else ("incomplete_reference_coverage" if any(r["status"] in {"not_processed", "matched_partial"} for r in results)
                  else "matched_available_references"), "comparisons": results,
            "unreferenced_year_rounds": [
                {"year": r["year"], "round": r["round"]}
                for r in report["national_domestic_by_year_round"]
                if not any(int(x["year"]) == r["year"] and int(x["round"]) == r["round"]
                           for x in results)
            ]}
