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

## ETL rules
1. Keep raw downloads unmodified outside version control; record download URL, retrieval timestamp, vintage, SHA-256 and licensing conditions.
2. Inspect each dataset dictionary; never assume election result files identify eligible voters at every output grain.
3. Harmonize municipal TSE-to-IBGE codes explicitly, maintaining a reviewed crosswalk for nontrivial cases.
4. Deduplicate by true turnout unit (election × round × municipality × zone × section), rejecting contradictory duplicates.
5. Verify `eligible > 0` and `0 <= absent <= eligible`; reconcile sum of absent and turnout to published official totals at matched reporting grain.
6. Preserve columns for covariate reference year, publication/availability date, denominator definitions and imputations.
7. Track section reallocation, changed establishment addresses and geography boundary vintages.
8. Forecast features must have been known by their simulation cutoff.

Do not commit identifying voter data or downloaded source datasets to this repository.
