# Official-data execution audit â€” 14 October 2026

Follow-up: the [section-level discrepancy investigation](discrepancy-investigation.md) locates the residuals, explains the 2018 category difference and adds official references for both 2014 rounds.

## Result and scope

The official national TSE archives for 2014, 2018, 2022 (both rounds) and 2026 (round one only) were downloaded, inspected and processed. The normalized dataset contains **38,991 municipality/year/round rows**, **43,274 domestic zone/transit records**, and **5,571 distinct IBGE municipality codes**. All observed municipalities join to the official 2025 IBGE geometry without missing polygons. The GeoPackage contains unique municipal geometries and a spatial municipal panel, both EPSG:4674. These are data-engineering outputs, not fitted forecasts or performance metrics.

The output is an **audit dataset with unresolved source discrepancies**. Strict mode rejects the four 2014 rows with unexplained residuals. The explicit `--allow-discrepancies` run preserves all official counts, adds residual fields, and flags the result. Do not treat completion as complete official reconciliation or authorization to ignore data quality.

## Environment and tests

Windows, Python 3.12.0, Git 2.53.0. Dependencies were installed into an isolated virtual environment with `pip install -e ".[dev]"`. The observed dependency resolution is pinned in `requirements-audit-windows-py312.txt`; it is a Windows audit snapshot, not a cross-platform lock.

All 20 original tests passed after configuring temporary files inside the writable workspace. The initial default Windows sandbox temp directory caused a permission error (19 passed, one failed), resolved by changing TEMP/TMP. The initial extended suite had 32 passing tests; the follow-up suite has 39. Regression coverage includes national ZIP selection, transit grain, uninstalled electors, residual opt-in, cutoff leakage, historical round coverage, spatial layer counts, source-receipt attribution and integrity, reference-universe matching, mismatch retention and locked GeoPackage publication.

A real BrasÃ­lia smoke test retained exactly the official first-round 2026 DF rows: 19 zone records, one municipal row and one matched polygon. `scripts/audit_sources.py` reproduces the schema inspection, source hashes, subset provenance and smoke build offline. The script preserves source counts and writes a parent archive receipt plus member/filter details for its derived subset.

A national rerun encountered a destination GeoPackage locked by a concurrent inspection on Windows. Publication now attempts the GeoPackage replacement before replacing CSVs, and stages each artifact on its destination filesystem. A regression test ensures that a locked GeoPackage leaves prior CSVs untouched. The final run uses fresh output folders. Multi-file publication is not a filesystem transaction: use distinct run directories and expose them to consumers only after success.

## Reproduce

From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-audit-windows-py312.txt
.venv/Scripts/python.exe -m pip install -e . --no-deps
New-Item -ItemType Directory -Force work | Out-Null
$env:TEMP = (Resolve-Path work).Path
$env:TMP = $env:TEMP
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m abstention_spatial.pipeline download --names tse-munzona-2014 tse-munzona-2018 tse-munzona-2022 tse-munzona-2026 tse-ibge-crosswalk ibge-municipalities-2025
.venv/Scripts/python.exe scripts/audit_sources.py
.venv/Scripts/python.exe -m abstention_spatial.pipeline build --years 2014 2018 2022 2026 --cutoff 2026-10-14 --allow-discrepancies --chunksize 1000 --output-dir data/processed/audited-final --spatial-dir data/geospatial/audited-final
.venv/Scripts/python.exe -m abstention_spatial.pipeline reconcile --report data/processed/audited-final/etl_qa_report.json --references docs/official-reference-totals.csv --output data/processed/audited-final/reconciliation.json
```

Verify saved artifacts with `python scripts/verify_artifacts.py --processed-dir data/processed/audited-final --geopackage data/geospatial/audited-final/municipalities_2025.gpkg`. This reopens the GeoPackage, checks SQLite integrity, keys, CRS, layer coverage and all count totals against the CSV, then records artifact hashes.

The reconciliation command intentionally exits 1 for the documented 2018 mismatch. Omit `--allow-discrepancies` to enforce strict count accounting; the frozen 2014 archive then fails without publishing outputs. Downloads total approximately 252 MB; the GeoPackage is approximately 2.60 GB because its panel layer repeats polygon geometry for each election/round. Keep raw archives and large generated artifacts outside Git. Both layers can be read with `geopandas.read_file(path, layer="municipalities_2025")` or `layer="municipal_panel"`; filter to a single year/round before spatial weights or Moran analysis.

## Observed source schemas

All four turnout ZIPs contain 29 CSVs (BR, BRASIL, 27 domestic UFs) and a dictionary PDF. CSVs are semicolon-delimited Latin-1 with 47 fields. The BR file contains presidential records for every domestic UF and ZZ; BRASIL contains the same presidential records plus other offices. The inspected AC files contain no presidential rows. The reader selects exactly `detalhe_votacao_munzona_YEAR_BR.csv`; it never concatenates overlapping exports. Unknown multi-CSV layouts require explicit selection. `--member YEAR=CSV` supports a reviewed override.

The true 2014 reporting grain includes `ST_VOTO_EM_TRANSITO`: 230 domestic transit records share zone keys with ordinary records but represent distinct additive registrations. Both N and S are retained, with duplicate checking at municipality/zone/round/transit grain. These are destination-based figures, not a residence-based panel; do not interpret them as individual travel or residence evidence.

The official crosswalk has 5,571 unique UF/TSE and IBGE mappings. Its internal generation date is 11 October 2026, despite the portal's 2025 catalog label; the report does not claim a 2025 crosswalk snapshot. The IBGE archive contains one Shapefile plus SHX, DBF, PRJ and CPG sidecars, a README and QMD. It has 5,573 valid polygon features in EPSG:4674. Unused operational water-area features `4300001` (Lagoa Mirim) and `4300002` (Lagoa dos Patos) are reported rather than converted to electoral observations. Municipal coverage is 5,570 for every historical round and 5,571 for 2026; Boa Esperança do Norte (`5101837`) has no historical observations; no historical row is fabricated to balance the panel. Applying 2025 boundaries is code harmonization, not historical boundary backcasting.

## Count accounting and defects

Source `QT_ABSTENCOES` is retained unchanged. The normalized identity is:

`eligible = turnout + absent + uninstalled + unaccounted`

`uninstalled` is official `QT_ELEITORES_SECOES_NAO_INSTALADAS`; `unaccounted` is an explicitly flagged positive residual, not an imputed abstention. Negative residuals always fail. The absence rate is `absent / eligible`; TSE reporting may instead use eligible registrations in installed/totalized sections. Counts must be reconciled before comparing rounded rates.

- **2014:** municipality 31950 / zone 34 and municipality 31054 / zone 27 in SE each have two unexplained electors in each round (eight across four source rows). Strict mode fails; audit mode preserves and lists the exact keys. The follow-up locates these as section 392 (Aracaju) and section 255 (Nossa Senhora do Socorro), each with two eligible registrations and no turnout or abstention in both rounds. Eight is a sum of elector-round residuals, not evidence of eight distinct people; the operational cause remains unestablished.
- **2022:** municipality 02550 / zone 68 in AM has 84 uninstalled-section electors in each round. Treating eligible minus turnout as abstention would falsely add 84 in each round. Overseas uninstalled electors are excluded from domestic geography and remain part of the national-report explanation.
- **2026:** domestic counts balance. Overseas records contain 423 uninstalled electors. TSE's results landing page warns that result/TTE files include 39 duplicate registrations: 158,745,502 reported registrations versus 158,745,463 effective electors. No municipality-level allocation was available, so no arbitrary 39-person correction is applied.

The pipeline now hard-limits the cutoff to 14 October 2026, excludes all 2026 round-two rows even through direct reader calls, rejects relevant source generation/last-totalization dates after the cutoff, and checks both rounds exist in national historical builds. Matching download-receipt hashes prevent silent input replacement; custom files without receipts are not attributed to an official URL. Source generation dates and HTTP last-modified timestamps are evidence, not guarantees of historical availability. Archive the exact observed bytes and original retrieval receipts for prospective forecasts.

## Domestic totals from preserved source counts

| Year | Round | Eligible | Turnout | Absent | Uninstalled | Unaccounted |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2014 | 1 | 142468542 | 114981382 | 27487156 | 0 | 4 |
| 2014 | 2 | 142468510 | 112542006 | 29926500 | 0 | 4 |
| 2018 | 1 | 146805955 | 117161888 | 29644067 | 0 | 0 |
| 2018 | 2 | 146805947 | 115732285 | 31073662 | 0 | 0 |
| 2022 | 1 | 155758656 | 123378340 | 32380232 | 84 | 0 |
| 2022 | 2 | 155758433 | 123942648 | 31815701 | 84 | 0 |
| 2026 | 1 | 157828968 | 124934069 | 32894899 | 0 | 0 |

## Independent official reconciliation

`docs/official-reference-totals.csv` transcribes national presidential report totals, with primary-source URL, exact PDF member, publication date and page references. Reports were downloaded separately from the turnout CSVs; 2026 summary pages were visually checked after rendering. The comparison adds audited ZZ totals to domestic totals to match the reference universe; municipal geometry never includes ZZ.

| Reference | Eligible difference | Turnout difference | Absent difference | Result |
| --- | ---: | ---: | ---: | --- |
| 2014 round 1, TSE publication 2016, p. 56 | 0 | 0 | 0 | Matched |
| 2014 round 2, TSE publication 2016, p. 56 | 0 | 0 | 0 | Matched |
| 2018 round 1, report 22 Jan 2019 | 0 | 0 | 0 | Matched |
| 2018 round 2, report 27 Feb 2019 | 0 | 0 | +669 | Mismatch retained |
| 2022 round 1, report 4 Oct 2022 | 0 | 0 | 0 | Matched |
| 2022 round 2, report 31 Oct 2022 | 0 | 0 | 0 | Matched |
| 2026 round 1, report 7 Oct 2026 | 0 | 0 | 0 | Matched |

Differences are observed CSV sums minus published reference values. The 2018 second-round PDF excludes 334 electors in an ES uncounted section and 335 in a PR uncounted section. The current CSV records the same counts as absentees in Vila Valerio zone 37 section 87 and Santo Antonio do Sudoeste zone 83 section 15. Section-to-zone sums agree exactly for all 2018 keys. This explains the 669-person numerical discrepancy without changing the preserved source counts or proving the sections' operational cause. Six matched comparisons do not establish that every municipality or historical boundary is correct.

The conventional national 2014 report ZIP URL returned HTTP 404; the follow-up retrieved the official 2016 TSE election publication through its catalog download endpoint. Page 56 provides all three national counts for both 2014 rounds, all matching the archives including ZZ. Both rounds now have verified references. The two domestic sections retain unclassified residuals. Independent state-level PDF reconciliation beyond the targeted ES/PR investigation remains outstanding; state coverage alone does not establish complete municipal coverage. No forecasting performance metrics are claimed.

Primary catalog evidence: [TSE 2026 results and duplicate-registration warning](https://dadosabertos.tse.jus.br/dataset/resultados-2026), [official municipal-code correspondence](https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge), [IBGE 2025 archive listing](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/Brasil/).

## Frozen input receipts

Full schema metadata, QA and reference differences are retained under `docs/audit/2026-10-14/`. Raw archives, PDFs, CSV panels and GeoPackages remain gitignored.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| detalhe_votacao_munzona_2014.zip | 3937094 | `f9195f8988edabd5db03fdef31ad33b21ad0f02c75c8a8fa30c468ed5642460a` |
| detalhe_votacao_munzona_2018.zip | 4269741 | `df68c258a2261dff37b379f65ea5f2e8de7b3d824bb2340d8f4830274a3fabb5` |
| detalhe_votacao_munzona_2022.zip | 4422339 | `4f4fb43493c65ebf743b74430f1590343a2bdeca16fc7ab9b80827e8c51eab92` |
| detalhe_votacao_munzona_2026.zip | 2502589 | `0d5a723707c446de17e4fbcffefa408ecb6c8b9642aaf1dc627975258bb3c5b7` |
| municipio_tse_ibge.zip | 139031 | `68328ddc166806594a2aab5809ac9aa602153535d6b8a71e886c337f9f3631ca` |
| BR_Municipios_2025.zip | 237062431 | `840bbe6f73726ef9d1460ce49fdfe01a278935c41180d3c893e25ca21db083bd` |
