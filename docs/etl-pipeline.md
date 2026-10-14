# Municipal spatial ETL: TSE + IBGE

## Status and boundaries of trust

The Python ETL package implements official-source discovery, explicit ZIP downloads, SHA-256 source receipts, chunked turnout ingestion, code harmonization, geographic joins and a quality-audit report. It has been exercised with synthetic tests, a real Brasilia smoke test, and the full official 2014/2018/2022/2026 national archives. See [execution audit](execution-audit-2026-10-14.md). This is data engineering groundwork, not a validated 2026 forecast.

The `reconcile` command compares independently transcribed report totals with matched source universes. Complete reference coverage remains unavailable. The pipeline does not perform historical boundary backcasting, socioeconomic-feature enrichment, or polling-place geocoding. Failing data/schema checks must be resolved before publishing results.

## Official download sources

| Download key | Source | URL |
| --- | --- | --- |
| tse-munzona-2014 | TSE 2014 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2014.zip |
| tse-munzona-2018 | TSE 2018 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2018.zip |
| tse-munzona-2022 | TSE 2022 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip |
| tse-munzona-2026 | TSE 2026 municipality/zone election results | https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2026.zip |
| tse-ibge-crosswalk | TSE official municipal code correspondence (retrieved 2026-10-14) | https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip |
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

The turnout reader automatically selects exactly `detalhe_votacao_munzona_YEAR_BR.csv` when present. This contains the presidential office for all domestic UFs and overseas voting. `BRASIL` also contains those same records and other offices; state CSVs in the inspected archives contain state offices. These files must never be concatenated together. For an explicit override use `--member 2022=detalhe_votacao_munzona_2022_BRASIL.csv`. Unknown multi-CSV layouts still fail closed.

Inspect actual schemas and execute an offline Brasilia smoke test before national processing:

    python scripts/audit_sources.py --raw-dir data/raw --output-dir data/processed/audit

## Offline build

    python -m abstention_spatial.pipeline build --years 2014 2018 2022 2026 --cutoff 2026-10-14 --raw-dir data/raw --output-dir data/processed --spatial-dir data/geospatial --allow-discrepancies

The documented 2014 archive has four domestic source discrepancies totaling eight electors. Strict mode rejects them. `--allow-discrepancies` preserves source counts and records positive unexplained residuals in `unaccounted`, with exact source keys in QA; it never increases abstentions or permits negative residuals. This is an audit dataset requiring further review before modeling.

By default, both historical rounds and 2026 round one must exist, and each included year/round must cover all **27 Brazilian UFs** (including the Federal District), rather than silently building incomplete national data. For a deliberate region-only analysis, add --allow-partial. QA also lists crosswalk codes without observations for every year/round; differences are reported without inventing historical observations. External TSE totals and historical municipal roster validation remain mandatory.

For an adjusted crosswalk schema, inspect the CSV column names before using:

    python -m abstention_spatial.pipeline build --crosswalk-columns CD_MUNICIPIO_TSE CD_MUNICIPIO_IBGE SG_UF

The build runs completely **offline** against the downloaded files. It records a cutoff date: 2026 second-round rows are always excluded, and cutoffs after 14 October 2026 are rejected. Relevant generation and last-totalization dates after the cutoff are rejected. A first-round 2026 cutoff before 4 October is rejected. Retrieving a revised raw file after a forecast cutoff does not retroactively recreate a frozen as-of dataset.

## Source assumptions and defenses

### Electoral files

This ETL uses TSE municipality/zone detailed apportionment results, **not** candidate-by-candidate voting records. Required fields include NR_TURNO, SG_UF, CD_MUNICIPIO, NR_ZONA, QT_APTOS, QT_COMPARECIMENTO and QT_ABSTENCOES, plus CD_CARGO (or DS_CARGO) to isolate the presidential office. ANO_ELEICAO is checked when supplied. Delimited Latin-1 text is read in chunks from ZIP.

We select president (CD_CARGO=1) **before summing any turnout counts**, because denominators can be repeated across offices and candidates. Count fields must be nonnegative integers. The accounting identity is `eligible = turnout + absent + uninstalled + unaccounted`. `uninstalled` comes from `QT_ELEITORES_SECOES_NAO_INSTALADAS`; `unaccounted` is a flagged residual, zero in strict mode. Source abstention counts are preserved. Duplicate municipality/zone/year/round/**transit** keys are errors even across chunks. In 2014, `ST_VOTO_EM_TRANSITO=S` identifies separate additive destination records; these are retained, and their destination geography must not be interpreted as voters' residence. Missing or ambiguous office identifiers are errors.

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
| data/geospatial/municipalities_2025.gpkg | `municipalities_2025`: unique polygons; `municipal_panel`: spatial municipality/year/round counts, EPSG:4674 |

Economic or demographic features are **not invented** by the ETL. They need their own dated/validated import before running multivariate spatial models.

## Quality gates remaining before research publication

- Reconcile eligible, present and absent against TSE official totalization by UF, election year and round.
- Inspect excluded ZZ rows, spatial unmatched/unused polygon lists, coverage and all input SHA-256 values.
- Assess changes in municipal geography across 2014–2026 rather than treating 2025 borders as timeless.
- Examine TSE's [2026 results warning](https://dadosabertos.tse.jus.br/dataset/resultados-2026) concerning **39 duplicated eligible-voter registrations**. This implementation does **not** allocate or subtract 39 records from specific municipalities without evidence.
- Freeze and version a genuinely pre-election data snapshot for prospective model validation.
- Confirm the live TSE source schema against the assumptions above before any national model training.

The included tests use entirely synthetic and local data and do not attempt to download official archives in CI.

## Independent reference comparison

    python -m abstention_spatial.pipeline reconcile --report data/processed/etl_qa_report.json --references docs/official-reference-totals.csv --output data/processed/reconciliation.json

The checked-in small reference CSV records source URLs, PDF members/pages or HTML locators, and publication dates or catalog years. Year-only dates must precede the cutoff year. Partial references compare only published metrics and return incomplete coverage, never an invented zero. Raw PDFs remain outside Git. The command returns exit code 1 for a mismatch and leaves observed values and differences visible. The audited snapshot has a 669-person 2018 round-two abstention difference; do not suppress this exit code in publication gates. Both 2014 rounds now match the official 2016 TSE publication, page 56. The 2014 section residuals and the 2018 state category difference are detailed in [the follow-up investigation](discrepancy-investigation.md). A matched subset does not certify the entire panel.

Downloads now retain `.zip.receipt.json` sidecars. Builds verify receipt hashes when available and leave custom inputs unattributed when no matching receipt exists. A generation date before the cutoff alone does not prove historical availability; preserve the downloaded snapshot and its original observation receipt.
