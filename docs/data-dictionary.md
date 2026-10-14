# Normalized data dictionary (v0.2)

## `municipal_panel.csv`
One row per **IBGE municipality × election year × round**. The current ETL produces only `municipality_code`, `year`, `round`, `eligible`, `turnout`, `absent` `uninstalled`, `unaccounted` and computed `abstention_rate`; optional socioeconomic fields below are **not** produced by this release:
| Field | Type | Definition |
| --- | --- | --- |
| municipality_code | string | Seven-digit IBGE municipal code (preserve leading zeros) |
| year | integer | Election year |
| round | integer | 1 or 2 |
| eligible | integer | Eligible electors in reporting unit |
| turnout | integer | Electors recorded as having attended |
| absent | integer | Official QT_ABSTENCOES; never imputed as eligible minus turnout |
| uninstalled | integer | Electors in uninstalled sections; not counted as abstentions |
| unaccounted | integer | Positive unexplained source accounting residual; zero in strict mode |
| abstention_rate | float | absent / eligible, in [0,1] |
| income_pc | float, nullable | Per-capita income; unit, reference year and source metadata required |
| elderly_share | float, nullable | Defined age-threshold share, 0–1 |
| density | float, nullable | Population per km² |
| as_of_date | date | Date through which source information was available |

Composite unique key: `(municipality_code, year, round)`. A missing second round is **missing**, never zero. A 2026 second-round observation cannot appear in model training at an October 14 forecast cutoff.

## `municipal_zone_turnout.csv` (implemented)

`year`, `round`, `uf`, `tse_code` (five-digit string), `electoral_zone` (zero-padded string), `transit` (N/S), `municipality_code` (IBGE seven-digit string), `eligible`, `turnout`, `absent`, `uninstalled`, `unaccounted`. This table reflects TSE municipality/zone reporting grain, **not** a section-level register. International district `ZZ` is excluded and recorded in QA.

## `municipality_crosswalk.csv`, `domestic_totals.csv`, `etl_qa_report.json` and `municipalities_2025.gpkg` (implemented)

These retain identifier correspondence, per-election-round domestic totals, file hashes and source/reporting exclusions, and the matched EPSG:4674 municipal geometries. See [ETL guide](etl-pipeline.md).

## `section_panel.csv.gz` and `section_panel.sqlite` (implemented)

One domestic presidential record per `(year, round, uf, tse_code, electoral_zone, section_id)`, with an official `municipality_code`, polling-place identifier, preserved turnout counts, source status flags, accounting-quality fields and archive/row provenance. The SQLite table is `sections`. Historical years include both rounds; 2026 includes round one only. The schema, quality rules and usage examples are in the [section ETL guide](section-etl.md). Section keys are election-specific; no historical correspondence or coordinates are inferred.

## `polling_places.csv`
Establishment identifier, municipality code, address, latitude, longitude, location precision, geocoding provenance and validity dates. Never treat zone or section numbers as physical coordinates.

## `section_place_mapping.csv`
Year, round, section composite key, establishment ID, mapping evidence, validity and review status.

## `municipal_geometry`
Seven-digit IBGE code, valid geometry, reference year, CRS and source.

## `covariates.csv`
Municipality code, indicator ID, value, unit, reference year, release date and source URL.

### Acceptance tests
- Unique keys; no null identifiers, illegal counts or rate outside [0,1].
- Joined municipality coverage and missing geometries reported (do not silently drop).
- National/state reconciliation to the relevant published TSE reporting tables.
- Every predictive feature has an availability date not after the forecast cutoff.

Accounting identity: `eligible = turnout + absent + uninstalled + unaccounted`. `abstention_rate` is the official absent count divided by all eligible registrations, not the TSE installed-section reporting rate when uninstalled electors exist. Nonzero residuals require sensitivity analysis before modeling.
