# Brazilian Electoral Abstention: Spatial Econometrics and Forecasting

**Research-stage, open and reproducible Python project** for understanding the geography of electoral abstention in Brazil and developing uncertainty-aware forecasts for the **2026 second round (25 October 2026)**.

> Status (14 October 2026): official national archives have been processed into 38,991 municipal panel rows and a GeoPackage. Six of seven national reference comparisons match; the 2018 round-two abstention difference is traced to 334 + 335 uncounted-section electors. The 2014 residuals are traced to two sections and remain unclassified. See the [discrepancy investigation](docs/discrepancy-investigation.md) and [execution audit](docs/execution-audit-2026-10-14.md). No validated forecasts or geocoded polling-place database exist.

## Research questions
1. Is municipal abstention spatially autocorrelated?
2. Which socioeconomic, demographic and accessibility variables are associated with abstention?
3. Are patterns stable across elections and rounds?
4. How much heterogeneity exists between polling places within municipalities?
5. Do spatial models improve out-of-time forecast accuracy?

## Analytical levels
- **Municipal:** municipality × election × round, harmonized geographic identifiers, TSE turnout counts and IBGE covariates.
- **Polling place:** establishment × election × round, built from *validated* section-to-establishment links. Section numbers are identifiers, not coordinates; proximity between establishments is not equivalent to voters' travel distance.

## Architecture
```text
Official TSE/IBGE data
  -> provenance-checked source files
  -> normalized municipal/section/establishment tables
  -> reviewed municipality geometries and spatial weights
  -> spatial diagnostics and interpretable econometric models
  -> temporal backtesting and uncertainty calibration
  -> aggregate municipality, state, and national research outputs
```

Poll-place analysis is a separate, nested extension requiring verified section-to-establishment linkage.

## Models
OLS and historical-change baselines; exploratory Moran's I and local LISA; SAR, SEM and Spatial Durbin specifications; then a hierarchical binomial or beta-binomial spatial model for counts and calibrated prediction intervals. Spatial associations must not be represented as individual-level or causal effects.

## Quick start
```bash
conda create -n abstention-spatial python=3.11 -y
conda activate abstention-spatial
pip install -e ".[dev]"
pytest -q
python -m abstention_spatial.cli --help
```

See [data preparation](docs/data-sources.md), [methodology](docs/methodology.md), [model specification](docs/statistical-models.md), [2026 forecasting](docs/forecasting-2026.md), [validation](docs/validation.md) and [roadmap](docs/roadmap.md). Explore the [municipal spatial notebook](notebooks/01_municipal_spatial_eda.ipynb) and the [polling-place linkage audit](notebooks/02_polling_place_data_audit.ipynb).

**Input files are not bundled.** Review the [ETL guide](docs/etl-pipeline.md) and [data dictionary](docs/data-dictionary.md) before running the ingestion CLI. The project does not yet include a trained or empirically validated national forecasting service.

## Municipal TSE–IBGE ETL (offline, reproducible)

The ETL fetches *explicitly selected* TSE election archives (2014, 2018, 2022, 2026), the official TSE-to-IBGE municipality-code crosswalk, and IBGE 2025 municipal boundaries. It validates presidential-election turnout once per municipality/zone, checks identifiers and eligible/turnout/absent totals, aggregates a municipality × election × round panel, and writes a GeoPackage plus SHA-256 provenance and QA reports.

```bash
# Review sources without downloading anything:
python -m abstention_spatial.pipeline sources

# After reviewing documented source URLs and file formats:
python -m abstention_spatial.pipeline download --names tse-munzona-2014 tse-munzona-2018 tse-munzona-2022 tse-munzona-2026 tse-ibge-crosswalk ibge-municipalities-2025

# Offline build; as-of cutoff excludes any future 2026 round-two rows:
python -m abstention_spatial.pipeline build --years 2014 2018 2022 2026 --cutoff 2026-10-14 --allow-discrepancies
```

**Important:** `--allow-discrepancies` explicitly preserves the documented 2014 residuals in `unaccounted`; strict builds reject those rows. Reconciliation limitations remain. Downloaded inputs and generated outputs are gitignored. Both municipal/zone and section turnout ETLs are available; socioeconomic covariates require separate dated imports. Read the [full ETL operating guide](docs/etl-pipeline.md) before running it.

## National section turnout base

The [section ETL](docs/section-etl.md) provides **3,203,211** presidential section/year/round records for 2014, 2018, 2022 and the first round of 2026, covering the 26 states and DF. It preserves source counts, unknown status flags, historical residuals and TSE-to-IBGE mapping. SQLite and CSV.gz outputs retain source-row provenance and the 14 October 2026 cutoff. The test suite passes 50 tests.

```bash
python -m abstention_spatial.pipeline download --names tse-sections-2014 tse-sections-2018 tse-sections-2022 tse-sections-2026 tse-ibge-crosswalk
python -m abstention_spatial.sections --years 2014 2018 2022 2026 --cutoff 2026-10-14 --allow-discrepancies --output-dir data/processed/sections-national
python scripts/verify_sections.py --output-dir data/processed/sections-national
```

## Scope and integrity
Aggregate electoral participation only. Do not infer how abstainers would have voted or individual voter preferences from aggregate results. Avoid publication of potentially disclosive small-cell information. Keep data provenance and cutoff dates alongside each estimate.

## Repository structure
```text
docs/                     Research protocol and data dictionary
src/abstention_spatial/   ETL, baselines and spatial diagnostics
tests/                    Unit tests
notebooks/                Data checks and exploratory notebooks
data/raw/                 Unmodified downloaded TSE/IBGE files (gitignored)
data/processed/           Harmonized tables (gitignored)
outputs/                  Generated artifacts (gitignored)
```

## Sources
[TSE open data](https://dadosabertos.tse.jus.br/) · [IBGE municipal boundaries](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15774-malhas) · [IBGE SIDRA](https://sidra.ibge.gov.br/) · [INMET](https://portal.inmet.gov.br/).

## License
Licensing decision pending. Do not assume an open-source license until one is explicitly adopted.
