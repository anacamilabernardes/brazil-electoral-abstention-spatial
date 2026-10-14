# Municipal spatial ETL: TSE + IBGE

## Status and boundaries of trust

The Python ETL package implements official-source discovery, explicit ZIP downloads, SHA-256 source receipts, chunked turnout ingestion, code harmonization, geographic joins and a quality-audit report. It has been exercised with synthetic datasets, **not yet with full official national archives**. This is data engineering groundwork, not a validated 2026 forecast.

It does not currently perform independently verified reconciliation to the final officially published TSE totals, historical boundary backcasting, socioeconomic-feature enrichment, or polling-place geocoding. Failing data/schema checks must be resolved before publishing results.

## Official download sources

| Download key | Source | URL |
| --- | --- | --- |
| tse-munzona-2014 | TSE 2014 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2014.zip |
| tse-munzona-2018 | TSE 2018 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2018.zip |
| tse-munzona-2022 | TSE 2022 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip |
| tse-munzona-2026 | TSE 2026 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2026.zip |
| tse-ibge-crosswalk | TSE official 2025 municipal code correspondence | https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip |
| ibge-municipalities-2025 | IBGE 2025 municipality geometry | https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/Brasil/BR_Municipios_2025.zip |

Official landing pages: [TSE 2014](https://dadosabertos.tse.jus.br/dataset/resultados-2014), [TSE 2018](https://dadosabertos.tse.jus.br/dataset/resultados-2018), [TSE 2022](https://dadosabertos.tse.jus.br/dataset/resultados-2022), [TSE 2026](https://dadosabertos.tse.jus.br/dataset/resultados-2026), [municipality-code crosswalk](https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge), [IBGE boundaries](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15774-malhas).

## Installation

Run from the repository root (Python 3.11+):

    python -m venv .venv
    # Activate the environment (.venv/Scripts/activate on Windows).
    python -m pip install -e ".[dev]"
    python -m pytest -q
    python -m abstention_spatial.pipeline sources

The package also provides the abstention-etl console command.

## Download (explicit opt-in)

    python -m abstention_spatial.pipeline download --names tse-munzona-2014 tse-munzona-2018 tse-munzona-2022 tse-munzona-2026 tse-ibge-crosswalk ibge-municipalities-2025 --raw-dir data/raw

Official downloads can be very large (the IBGE countrywide municipality ZIP alone is hundreds of MB). No download occurs as part of import, build, unit tests, or package installation. Existing nonempty archives are rehashed, not automatically replaced. Record and archive prior versions before fetching source revisions.

The ZIP reader expects **one verified CSV member** unless an explicit member is supplied programmatically. If a source archive has several CSVs, it deliberately stops rather than choosing an arbitrary UF or double-counting a nationwide file. Inspect the archive and extract a reviewed CSV or select a reviewed ZIP member. The crosswalk can be supplied separately with --crosswalk.

## Offline build

    python -m abstention_spatial.pipeline build --years 2014 2018 2022 2026 --cutoff 2026-10-14 --raw-dir data/raw --output-dir data/processed --spatial-dir data/geospatial

By default, each included year/round must cover all **27 Brazilian UFs** (including the Federal District), rather than silently building incomplete national data. For a deliberate region-only analysis, add --allow-partial. This checks state coverage, not complete municipal-level registration coverage; external TSE totals and municipal roster validation remain mandatory.

For an adjusted crosswalk schema, inspect the CSV column names before using:

    python -m abstention_spatial.pipeline build --crosswalk-columns CD_MUNICIPIO_TSE CD_MUNICIPIO_IBGE SG_UF

The build runs completely **offline** against the downloaded files. It records a cutoff date: the 2026 second-round rows are excluded for 14 October 2026 even if a later raw archive contains them. A first-round 2026 cutoff before 4 October is rejected. Retrieving a revised raw file after a forecast cutoff does not retroactively recreate a frozen as-of dataset.

## Source assumptions and defenses

### Electoral files

This ETL uses TSE municipality/zone detailed apportionment results, **not** candidate-by-candidate voting records. Required fields include NR_TURNO, SG_UF, CD_MUNICIPIO, NR_ZONA, QT_APTOS, QT_COMPARECIMENTO and QT_ABSTENCOES, plus CD_CARGO (or DS_CARGO) to isolate the presidential office. ANO_ELEICAO is checked when supplied. Delimited Latin-1 text is read in chunks from ZIP.

We select president (CD_CARGO=1) **before summing any turnout counts**, because denominators can be repeated across offices and candidates. All source numeric fields must be nonnegative integers; eligible must equal turnout plus absent. Duplicate municipality/zone/year/round keys are errors even across chunks. Missing or ambiguous office identifiers are errors.

The international voting district SG_UF=ZZ is explicitly excluded from the **domestic municipal spatial estimand**, and excluded rows are counted in the audit. National domestic totals cannot be compared to TSE totals including overseas votes without adjusting the reference universe.

### TSE–IBGE correspondence

TSE municipality codes are five-digit strings and IBGE geocodes are seven-digit strings, which must not be joined by name or treated as interchangeable. The official 2025 crosswalk is keyed by UF and TSE code and required to be one-to-one with IBGE municipality IDs. Missing matches or collisions fail the build. Historical municipality changes need a separate crosswalk-vintage sensitivity analysis.

### IBGE geometry

The 2025 ZIP is read as a single Shapefile with necessary sidecars; only expected file types are copied to a temporary directory to avoid arbitrary ZIP extraction. Data must have a declared CRS, valid polygons, unique seven-digit CD_MUN IDs and full coverage of every municipality in the normalized election panel. The output is converted to **EPSG:4674** in GeoPackage format. Unexpected extra geographic features are reported, not silently treated as municipalities.

## Outputs (gitignored)

| Artifact | Description |
| --- | --- |
| data/processed/municipal_zone_turnout.csv | Year, round, UF, TSE code and electoral zone, official IBGE code and checked counts |
| data/processed/municipal_panel.csv | One municipality × year × round: eligible, turnout, absent and abstention_rate |
| data/processed/municipality_crosswalk.csv | Audited TSE-code to IBGE-code table |
| data/processed/domestic_totals.csv | Domestic annual/round aggregates, excluding ZZ |
| data/processed/etl_qa_report.json | Input hashes, cutoff, exclusions, source counts, UF coverage, unmatched geometry and reconciliation caveats |
| data/geospatial/municipalities_2025.gpkg | Matched municipality polygon geometries, EPSG:4674 |

Economic or demographic features are **not invented** by the ETL. They need their own dated/validated import before running multivariate spatial models.

## Quality gates remaining before research publication

- Reconcile eligible, present and absent against TSE official totalization by UF, election year and round.
- Inspect excluded ZZ rows, spatial unmatched/unused polygon lists, coverage and all input SHA-256 values.
- Assess changes in municipal geography across 2014–2026 rather than treating 2025 borders as timeless.
- Examine TSE's [2026 results warning](https://dadosabertos.tse.jus.br/dataset/resultados-2026) concerning **39 duplicated eligible-voter registrations**. This implementation does **not** allocate or subtract 39 records from specific municipalities without evidence.
- Freeze and version a genuinely pre-election data snapshot for prospective model validation.
- Confirm the live TSE source schema against the assumptions above before any national model training.

The included tests use entirely synthetic and local data and do not attempt to download official archives in CI.
