# Brazilian Electoral Abstention: Spatial Econometrics and Forecasting

**Research-stage, open and reproducible Python project** for understanding the geography of electoral abstention in Brazil and developing uncertainty-aware forecasts for the **2026 second round (25 October 2026)**.

> Status (14 October 2026): project scaffold only. No empirical results, validated forecasts, or geocoded polling-place database have been produced.

## Research questions
1. Is municipal abstention spatially autocorrelated?
2. Which socioeconomic, demographic and accessibility variables are associated with abstention?
3. Are patterns stable across elections and rounds?
4. How much heterogeneity exists between polling places within municipalities?
5. Do spatial models improve out-of-time forecast accuracy?

## Analytical levels
- **Municipal:** municipality × election × round, harmonized geographic identifiers, TSE turnout counts and IBGE covariates.
- **Polling place:** establishment × election × round, built from *validated* section-to-establishment links. Section numbers are identifiers, not coordinates; proximity between establishments is not equivalent to voters' travel distance.

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

See [data preparation](docs/data-sources.md), [methodology](docs/methodology.md), [model specification](docs/statistical-models.md), [2026 forecasting](docs/forecasting-2026.md), [validation](docs/validation.md) and [roadmap](docs/roadmap.md).

**Input files are not bundled.** Download and verify official TSE/IBGE data first, then normalize to the schema described in [data dictionary](docs/data-dictionary.md). The CLI currently provides a transparent municipality-level diagnostics entry point, not a trained national forecasting service.

## Scope and integrity
Aggregate electoral participation only. Do not infer how abstainers would have voted or individual voter preferences from aggregate results. Avoid publication of potentially disclosive small-cell information. Keep data provenance and cutoff dates alongside each estimate.

## Repository structure
```text
docs/                     Research protocol and data dictionary
src/abstention_spatial/   Baseline and spatial diagnostics
tests/                    Unit tests
data/raw/                 Unmodified downloaded files (gitignored)
data/processed/           Harmonized tables (gitignored)
outputs/                  Generated artifacts (gitignored)
```

## Sources
[TSE open data](https://dadosabertos.tse.jus.br/) · [IBGE municipal boundaries](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15774-malhas) · [IBGE SIDRA](https://sidra.ibge.gov.br/) · [INMET](https://portal.inmet.gov.br/).

## License
Licensing decision pending. Do not assume an open-source license until one is explicitly adopted.
