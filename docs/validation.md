# Validation and model governance

## Backtesting
- Fit models using information available before the 2018 second round; evaluate against 2018 outcomes (historical information permitting).
- Repeat with information available before the 2022 second round; evaluate against 2022.
- Use the 2026 first round for October 2026 predictions and defer second-round labels until after the election.

Never train on the held-out election's future labels or on covariates with later publication dates.

## Spatial checks
Use grouped geographic validation (blocks of neighboring municipalities; region/UF robustness analyses), tests by electorate-size strata, and checks on spatial residuals. Compare Queen, Rook, kNN and distance weights with documented island handling.

## Metrics
- Electorate-weighted MAE and RMSE of municipal percentage-point errors.
- Absolute error in predicted absent counts and electorally weighted country/state rates.
- Proper interval scores and observed coverage at nominal 80% and 95%.
- Distribution of errors by region, population density and electorate size.

## Quality gates
All aggregation invariants pass; geographic joins preserve intended units; no future-data leakage; models outperform simple baselines out of time or remain exploratory; uncertainty coverage is reported. Forecast freeze includes training files' hashes, feature-release timestamps, code commit and model version.

No fabricated performance claims: evaluation metrics remain **not available** until real data have been ingested and tests executed.
