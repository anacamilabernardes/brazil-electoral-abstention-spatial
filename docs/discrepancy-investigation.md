# Historical discrepancy investigation

Investigation date and information cutoff: 14 October 2026. This follows the initial national ETL audit and updates PR #1. Original election counts are preserved; this investigation does not impute abstentions, change the forecasting cutoff, or use any 2026 second-round outcomes.

## Findings

The 2014 residuals are reproducible in two original sections, and the 2018 difference is explained arithmetically by two report categories. All section counts aggregate exactly to the previously ingested municipality/zone counts for both years. No aggregation error was found. A separately published TSE report now supplies national references for both 2014 rounds, and all six count comparisons match.

## 2014: four residual rows, two sections

The official section-detail archive identifies the domestic residuals precisely:

| UF | TSE municipality | Municipality | Zone | Section | Round | Eligible | Turnout | Absent | Residual |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SE | 31054 | Aracaju | 27 | 392 | 1 | 2 | 0 | 0 | 2 |
| SE | 31054 | Aracaju | 27 | 392 | 2 | 2 | 0 | 0 | 2 |
| SE | 31950 | Nossa Senhora do Socorro | 34 | 255 | 1 | 2 | 0 | 0 | 2 |
| SE | 31950 | Nossa Senhora do Socorro | 34 | 255 | 2 | 2 | 0 | 0 | 2 |

These are **eight elector-round residual units**, four in each round. The aggregate source does not establish eight distinct people, nor does it prove the same four individuals appeared in both rounds. Both sections have zero nominal, blank, null and separately counted annulled votes. They are ordinary-source rows, not the separately counted in-transit records.

The section export was generated on 28 July 2021; the municipality/zone export was generated on 23 February 2022. Aggregating every presidential section reproduces all **12,866** municipality/zone keys, including overseas keys and the sum of ordinary and transit records, with zero differences in eligible, turnout and absent counts. The residual is therefore already present in the official sources, rather than introduced by the pipeline.

The 2014 section schema contains no installed/uncounted status flag. The corresponding zone export reports zero uninstalled-section electors. Zero votes alone cannot distinguish an uninstalled section, an uncounted section, an administrative placeholder, or another source issue. Keep `unaccounted=2` for each affected zone/round and retain strict-mode rejection. No evidence-supported category reassignment or numerical correction is available.

## Official 2014 national references

The [TSE publication catalog](https://www.tse.jus.br/institucional/catalogo-de-publicacoes/relatorio-das-eleicoes) links the [2014 election report](https://www.tse.jus.br/institucional/catalogo-de-publicacoes/arquivos/relatorio-eleicoes-2014/@@download/file), published in **2016**. Page 56, section 2.2, gives the presidential electorate, turnout and abstention totals for both rounds. These were extracted and checked against the rendered page. The table cites the electoral repository accessed on 10 August 2015. Page 13 independently repeats turnout and abstention values.

| Round | Eligible registrations | Turnout | Absent | Difference from ETL including ZZ |
| --- | ---: | ---: | ---: | --- |
| 1 | 142822046 | 115122883 | 27698475 | 0 for all three counts |
| 2 | 142822046 | 112683879 | 30137479 | 0 for all three counts |

Both published rows themselves have `eligible - turnout - absent = 688`. The source breakdown is four domestic plus 684 overseas residual units in each round. National agreement does not resolve the domestic section classifications or justify calculating absent as eligible minus turnout.

The conventional totalization ZIP URL returned 404, and the bare publication link initially returned 403. The catalog's standard `@@download/file` endpoint with a browser user agent returned the PDF successfully. Its SHA-256, size, observed timestamp, publication year and reviewed pages are preserved in `docs/audit/2026-10-14/2014-reference-receipt.json`. Only the publication year is known, so the reference CSV stores `2016`, without inventing a month or day.

TSE's [6 October 2014 release](https://www.tse.jus.br/comunicacao/noticias/2014/Outubro/tse-divulga-dados-gerais-sobre-primeiro-turno-das-eleicoes-2014) independently gives first-round turnout and abstention. Its [28 October release](https://www.tse.jus.br/comunicacao/noticias/2014/Outubro/presidente-do-tse-proclama-resultado-provisorio-das-eleicoes-para-presidente-da-republica-no-2o-turno) gives second-round eligible registrations and turnout. These partial references are retained separately; missing values remain blank instead of being inferred from an accounting identity that is not valid here.

## 2018: exact 334 + 335 category difference

The national second-round totalization report, `296_BR_BRASIL_2018_T2_PRESIDENTE.pdf`, records 669 electors in uncounted sections. Its state summaries separate them as **334 in ES (page 16)** and **335 in PR (page 36)**. The current official section CSV has exactly two domestic presidential rows with zero turnout:

| UF | TSE municipality | Municipality | Zone | Section | Round | Eligible | Turnout | Source absent |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ES | 56227 | Vila Valerio | 37 | 87 | 2 | 334 | 0 | 334 |
| PR | 78573 | Santo Antonio do Sudoeste | 83 | 15 | 2 | 335 | 0 | 335 |

| UF | PDF eligible | CSV eligible | PDF turnout | CSV turnout | PDF absent | CSV absent | Absent difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ES | 2754749 | 2754749 | 2178495 | 2178495 | 575920 | 576254 | +334 |
| PR | 7972415 | 7972415 | 6595854 | 6595854 | 1376226 | 1376561 | +335 |

The source section export was generated on 15 February 2024. After normalizing five-digit municipality and four-digit zone identifiers, its counts reproduce all **12,546** official municipality/zone keys, including overseas records, with zero differences. The PDF excludes these 669 registrations from absentee counts as uncounted-section electors; the later CSV records them as absentees. Subtracting 669 from the CSV solely for a report-category comparison yields 31,371,704, exactly the PDF's national absent total. This is an explanatory comparison, not a change to the dataset.

The section CSV's installed/annulled flags are `#NULO#`, so it does not establish the operational cause or whether any particular voter abstained. The two section keys, zero counts, exact state differences and explicit PDF categories make the accounting explanation much more specific than an unspecified source revision. The numerical mismatch remains visible; no automatic subtraction or unsupported reclassification is applied.

## Reproduce offline

Download the two section archives from the links listed in the official [2014 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2014) and [2018 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2018):

- https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/detalhe_votacao_secao_2014.zip
- https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/detalhe_votacao_secao_2018.zip

Keep them unmodified in `data/raw`; their receipts are embedded in the checked-in investigation JSON. The existing municipality/zone archives and 2018 national report ZIP must also be present. Downloads are separate from this offline audit script.

```powershell
python scripts/investigate_discrepancies.py --raw-dir data/raw --output data/processed/discrepancy_investigation.json
python -m abstention_spatial.pipeline reconcile --report data/processed/audited-final/etl_qa_report.json --references docs/official-reference-totals.csv --output data/processed/audited-final/reconciliation.json
python -m pytest -q
```

The section audit exits 0 after finding zero section-to-zone differences. National reconciliation intentionally exits 1 because the 2018 PDF/CSV absent-count mismatch remains. Six of seven full national references now match, and both 2014 rounds have verified references. No new national CSV or GeoPackage build is needed: the ingested source counts and identifiers have not changed.

## Code and validation

The reconciliation reader now accepts catalog publication years without fabricating dates, distinguishes HTML locators from PDF page/member provenance, and compares only explicitly published metrics for partial references. A partial match reports `incomplete_reference_coverage` and cannot pass the CLI quality gate. Regression tests verify these behaviors. The full suite passes **39 tests**.

Checked-in evidence includes the six selected public aggregate section records, original archive hashes and timestamps, all state totals, section-to-zone comparison counts, targeted 2018 state report comparisons, the 2014 publication receipt, and refreshed national reconciliation. Raw ZIPs, the 145 MB source PDF, and large generated datasets remain outside Git.
