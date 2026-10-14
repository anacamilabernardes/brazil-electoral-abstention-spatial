# Normalized data dictionary (v0.1)

## `municipal_panel.csv`
One row per **IBGE municipality × election year × round**:
| Field | Type | Definition |
| --- | --- | --- |
| municipality_code | string | Seven-digit IBGE municipal code (preserve leading zeros) |
| year | integer | Election year |
| round | integer | 1 or 2 |
| eligible | integer | Eligible electors in reporting unit |
| turnout | integer | Electors recorded as having attended |
| absent | integer | Eligible minus turnout |
| income_pc | float, nullable | Per-capita income; unit, reference year and source metadata required |
| elderly_share | float, nullable | Defined age-threshold share, 0–1 |
| density | float, nullable | Population per km² |
| as_of_date | date | Date through which source information was available |

Composite unique key: `(municipality_code, year, round)`. A missing second round is **missing**, never zero. A 2026 second-round observation cannot appear in model training at an October 14 forecast cutoff.

## `section_turnout.csv`
One row per `(year, round, municipality_code, electoral_zone, section_id)` with `eligible`, `turnout`, `absent`, a source file/version and a mapped establishment ID where verified.

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
