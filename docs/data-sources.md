# Data acquisition and provenance

| Data | Primary source | Role |
| --- | --- | --- |
| Historical turnout and abstention | https://dadosabertos.tse.jus.br/ | Eligible, turnout, absent, round |
| 2026 election results | https://dadosabertos.tse.jus.br/dataset/resultados-2026 | Current first-round turnout information; verify exact file layouts |
| Electorate characteristics | https://dadosabertos.tse.jus.br/ | Age, education, gender aggregates |
| Municipal geometries | https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15774-malhas | Municipal join key and spatial adjacency |
| Municipal population and socioeconomic features | https://sidra.ibge.gov.br/ | Covariates with observation/reference dates |
| Supplementary economic series | https://www.ipeadata.gov.br/ | Covariates |
| Weather | https://portal.inmet.gov.br/ | Election-day context |
| Polling place address and section allocation | TSE and regional electoral courts (TREs) | Establishment mapping; availability varies |

## Implemented TSE/IBGE ETL

The versioned municipality × election × round pipeline is described in [Municipal spatial ETL](etl-pipeline.md). It ingests the TSE `detalhe_votacao_munzona` series, the TSE↔IBGE municipality-code crosswalk, and IBGE 2025 municipal geometries, records SHA-256 provenance, filters the presidential office, validates domestic zone turnout counts, and publishes checked municipality aggregates and a GeoPackage. The 2026 build explicitly enforces an information cutoff of 14 October 2026. The full official files were processed on 14 October 2026; see [execution audit](execution-audit-2026-10-14.md) for hashes, schemas, discrepancies and reconciliation.

Section-level and establishment-level ETL, complete reconciliation and socioeconomic feature acquisition remain separate development milestones.

## ETL rules
1. Keep raw downloads unmodified outside version control; record download URL, retrieval timestamp, vintage, SHA-256 and licensing conditions.
2. Inspect each dataset dictionary; never assume election result files identify eligible voters at every output grain.
3. Harmonize municipal TSE-to-IBGE codes explicitly, maintaining a reviewed crosswalk for nontrivial cases.
4. Deduplicate at the **source reporting grain**: the implemented detailed municipality/zone export uses election × round × municipality × zone × selected office (president). Section-level files, when added later, require their own finer section key.
5. Verify `eligible > 0` and `0 <= absent <= eligible`; preserve source abstentions and account separately for uninstalled electors and explicitly flagged unexplained residuals. Reconcile against published official totals at matched reporting grain.
6. Preserve columns for covariate reference year, publication/availability date, denominator definitions and imputations.
7. Track section reallocation, changed establishment addresses and geography boundary vintages.
8. Forecast features must have been known by their simulation cutoff.

Do not commit identifying voter data or downloaded source datasets to this repository.
