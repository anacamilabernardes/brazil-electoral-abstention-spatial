# National section turnout ETL: execution and operating guide

Execution date and forecasting cutoff: **14 October 2026**.

## Delivered dataset

The four official TSE section archives were processed into **3,203,211 domestic presidential section/year/round records**, covering all **26 states and the Federal District** in every requested year/round. Historical years 2014, 2018 and 2022 contain both rounds; 2026 contains only the first round. All records have a validated official TSE-to-IBGE municipal mapping, covering 5,571 distinct municipalities across the four years.

| Year | Round | Domestic section records | UFs |
| --- | --- | ---: | ---: |
| 2014 | 1 | 427940 | 27 |
| 2014 | 2 | 427940 | 27 |
| 2018 | 1 | 453706 | 27 |
| 2018 | 2 | 453706 | 27 |
| 2022 | 1 | 471011 | 27 |
| 2022 | 2 | 471011 | 27 |
| 2026 | 1 | 497897 | 27 |

A record identifies an election-specific reporting section, not a section tracked unchanged over time. The source export contains the reporting sections supplied by TSE; this is not a reconstruction of every aggregated section in the electoral register. No cross-election section correspondence, section coordinates or voter-level observations are inferred.

The SQLite database and compressed CSV contain the same 21 normalized columns. A real first-round 2026 DF smoke test produced **6,969 section records**, one municipality and first-round data only. The extended automated suite passes **50 tests**.

## Acquisition and actual schemas

The [TSE 2022 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2022) and [TSE 2026 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2026) supplied the download links. The new downloads total **420,745,388 bytes**. The 2014 and 2018 archives had already been downloaded for the discrepancy investigation and were reused unchanged. Each archive has a SHA-256 receipt and an observation timestamp on 14 October 2026.

| Year | Archive bytes | Presidential CSV schema fields | First CSV record generation date |
| --- | ---: | ---: | --- |
| 2014 | 73594893 | 28 | 2021-07-28 |
| 2018 | 256133172 | 37 | 2024-02-15 |
| 2022 | 243822213 | 37 | 2024-02-15 |
| 2026 | 176923175 | 37 | 2026-10-05 |

The inspected files are semicolon-delimited Latin-1 CSVs. Each archive has overlapping `BR`, `BRASIL` and UF exports. The build selects exactly one `detalhe_votacao_secao_YEAR_BR.csv` and filters `CD_CARGO=1`; it never concatenates overlapping members or sums across offices/candidates.

The 2014 schema has no installed/annulled section flags. The 2018 schema has flag columns but the inspected presidential rows use unknown source values. The 2022 and 2026 archives provide explicit `Sim`/`Nao` flags. Missing/unknown flags remain null; they are never assumed to mean that a section functioned.

## Reproduce

Use the existing repository environment. No additional Python package is required; SQLite and gzip are from the standard library.

```powershell
python -m abstention_spatial.pipeline download --names tse-sections-2014 tse-sections-2018 tse-sections-2022 tse-sections-2026 tse-ibge-crosswalk

# Small real-data smoke test before the national build:
python -m abstention_spatial.sections --years 2026 --ufs DF --chunksize 25000 --output-dir data/processed/section-smoke

# National output includes all 27 UFs by default:
python -m abstention_spatial.sections --years 2014 2018 2022 2026 --cutoff 2026-10-14 --allow-discrepancies --chunksize 25000 --output-dir data/processed/sections-national

# Independent saved-file and source-aggregate verification:
python scripts/verify_sections.py --raw-dir data/raw --output-dir data/processed/sections-national
python -m pytest -q
```

The build is offline and chunked. It stages the SQLite database and CSV before publishing. The database is replaced first so a Windows GIS/database lock cannot cause CSVs to be published before that failure; multi-file publication is not transactional, so use a fresh run directory. Source archives and large generated outputs are gitignored.

The 2014 source residuals require explicit `--allow-discrepancies`. Strict mode rejects them. Both modes reject negative accounting residuals and contradictory explicit uninstalled-section counts. National builds require all 27 UFs in both historical rounds and 2026 round one. `--ufs DF` is an explicitly regional build, recorded in QA; it must not be presented as national.

The cutoff cannot exceed 14 October 2026. First-round 2026 data cannot be used before 4 October. Second-round 2026 rows are excluded before their outcome counts are parsed. Source generation, election-day, BU-receipt and first-totalization dates after the cutoff are rejected for the selected domestic presidential records. Original retrieval receipts and file hashes are preserved; a source generation date alone does not reconstruct historical availability.

## Normalized schema

Composite primary key: `(year, round, uf, tse_code, electoral_zone, section_id)`.

| Field | Storage type | Meaning |
| --- | --- | --- |
| year, round | integer | Election year and round |
| uf | text | Official domestic UF abbreviation, including DF |
| tse_code | text | Five-digit TSE municipality code |
| electoral_zone | text | Zero-padded zone identifier, four digits |
| section_id | text | Zero-padded section identifier, at least four digits |
| municipality_code | text | Seven-digit official IBGE municipal mapping |
| polling_place_code | nullable text | Source `NR_LOCAL_VOTACAO`, zero-padded identifier; not a coordinate |
| eligible | integer | Unmodified source `QT_APTOS` |
| turnout | integer | Unmodified source `QT_COMPARECIMENTO` |
| absent | integer | Unmodified source `QT_ABSTENCOES` |
| uninstalled | integer | Eligible registrations explicitly marked as belonging to an uninstalled section |
| unaccounted | integer | Positive residual still unsupported by a source category |
| abstention_rate | nullable real | `absent / eligible`; null if eligible is zero |
| section_installed, section_annulled | nullable integer | 1=yes, 0=no, null=unknown/unavailable |
| count_quality | text | Accounting category: balanced, uninstalled, unaccounted or zero_eligible |
| source_id | text | Archive receipt key, e.g. `tse-sections-2026` |
| source_row | integer | Logical CSV record number, starting at 1 after the header; not a physical line number |
| source_generated_date | text | Source generation date in ISO format |
| cutoff_date | text | Enforced information cutoff in ISO format |

SQLite enforces unique keys and nonnegative integer counts, with `eligible = turnout + absent + uninstalled + unaccounted`. Duplicate section keys across chunks fail, as do missing municipal mappings. CSV output has fixed key/column order and gzip metadata; nullable flags are serialized as integers so their representation does not change with chunk boundaries. Regression coverage compares exports built with different chunk sizes.

`count_quality=balanced` means the count identity holds, not that all reporting issues are resolved. Review the zero-turnout list and the historical discrepancy documentation before fitting models. In particular, a zero reported absentee count in an uninstalled section must not be interpreted as evidence that no voter abstained.

## Data-quality findings

- **2014:** Aracaju/SE zone 27 section 392 and Nossa Senhora do Socorro/SE zone 34 section 255 each have eligible=2, turnout=0 and absent=0 in both rounds. The base retains eight elector-round residual units across four rows. Operational classification remains unknown; no absentee count is imputed.
- **2018:** Vila Valerio/ES zone 37 section 87 and Santo Antonio do Sudoeste/PR zone 83 section 15 retain source absentee counts of 334 and 335. The older national PDF excludes those counts as uncounted-section electors, explaining the +669 reference difference. Missing source flags are not used to fabricate a classification or adjust the counts.
- **2022:** Manaus/AM zone 68 section 797 explicitly has `ST_SECAO_INSTALADA=Nao`, 84 eligible registrations and zero turnout/absent in each round. These are preserved as 84 uninstalled electors per round, rather than 84 invented absentees.
- **2026:** All domestic counts balance in the downloaded first-round snapshot. TSE's warning about 39 duplicate registrations is retained at source level; no arbitrary municipal/section allocation or subtraction is performed. Overseas voting is excluded from this domestic base.

See [historical discrepancy investigation](discrepancy-investigation.md) for the independent report references. The national section aggregates reproduce the previously delivered municipal panel, while the original 2018 PDF category difference remains a documented reference mismatch.

## Independent saved-file validation

Reopening the delivered database and CSV verified **3,203,211 rows**, SQLite integrity, the cutoff exclusion, and equality of all five count totals. Aggregating sections matched **43,044 domestic zone keys** across the four years with **zero mismatches**, including the separate uninstalled/unaccounted fields. The difference from the earlier 43,274 zone/transit rows is the 230 separate 2014 transit rows, summed into their zone keys for this comparison.

The review export contains **10 positive-electorate records with zero turnout**: the four known 2014 residual rows, two other 2014 rows with reported absentees and unknown section status, the two 2018 category-discrepancy rows, and the two explicitly uninstalled 2022 rows. These are retained as review evidence; zero turnout alone is not an automatic error or an operational classification.

The checked-in QA snapshot and validation summary are in `docs/audit/2026-10-14/sections/`. Exact output sizes and SHA-256 hashes are recorded in QA. No model performance metrics are generated.

## Artifacts and analysis access

| Artifact | Purpose |
| --- | --- |
| section_panel.sqlite | Full normalized `sections` table, primary key and municipal index |
| section_panel.csv.gz | Portable compressed copy of the same normalized records |
| section_state_totals.csv | Section counts and turnout aggregates by year/round/UF |
| section_municipal_totals.csv | Section counts aggregated to IBGE municipality/year/round |
| section_qa_report.json | Input receipts, actual members/schemas, cutoff, exclusions, quality and artifact hashes |
| section_validation.json | Independent SQLite/CSV checks and source zone reconciliation |
| section_zone_mismatches.csv | Any discrepancies against official municipality/zone counts |
| section_zero_turnout_review.csv | Positive-electorate sections with zero turnout, retained for review |

Query a manageable subset without loading all records:

```python
import sqlite3
import pandas as pd

with sqlite3.connect("data/processed/sections-national/section_panel.sqlite") as db:
    sp_2026 = pd.read_sql_query(
        "SELECT * FROM sections WHERE year=? AND round=? AND uf=?",
        db, params=(2026, 1, "SP"),
    )

# For the portable file, retain text identifiers and process in chunks:
for chunk in pd.read_csv(
    "data/processed/sections-national/section_panel.csv.gz",
    dtype={"tse_code": str, "electoral_zone": str, "section_id": str,
           "municipality_code": str, "polling_place_code": str},
    chunksize=100000,
):
    pass  # aggregate or select the required rows
```

The municipal GeoPackage can be joined through `municipality_code` when municipal geometry is needed. No polygon or coordinate is assigned to a polling place or section by this ETL. Large source archives, source address text and generated bases are not committed to Git; the PR includes code, tests, English documentation and small QA/validation summaries only.
