# Second-round 2026 forecasting protocol

**Target election:** 25 October 2026. **Prospective information cutoff:** 14 October 2026 (America/Sao_Paulo), subject to later explicitly versioned forecast runs.

## Forecast target
For each municipality `m`: second-round absent / second-round eligible. Report municipality, state and national predictions with uncertainty. Aggregate expected absent counts and expected eligible counts: do not take an unweighted mean of municipal rates.

## Initial baseline
Compute the 2022 within-municipality change `delta_m = A_2022,r2 - A_2022,r1`. Shrink locality changes toward their electorate-weighted mean, tuning shrinkage only by **earlier** backtests (not arbitrarily). For 2026 `Ahat_2026,r2 = clip(A_2026,r1 + delta_hat_m, 0, 1)`. This is a benchmark, not an established empirical forecast.

## Spatial extension
Fit historical change/panel features and/or a hierarchical binomial spatial model to pre-cutoff observations. Do not use actual 2026 round-two rates, neighboring realized round-two outcomes, or final election-day weather known only after the cutoff. Spatially lagged outcomes in SAR/SDM must be solved jointly rather than substituted from unseen target data.

## Eligible denominator
Use explicitly provisional second-round eligible counts until confirmed. Quantify sensitivity to denominator changes and avoid claims of exact national absent counts without a credible denominator.

## Output contract
`municipality_code, cutoff_date, model_version, predicted_rate, predicted_absent, eligible_assumption, lower_80, upper_80, lower_95, upper_95, data_version`.

Intervals are required for official forecast publication and must be tested for empirical coverage. No official forecast is emitted by the initial code scaffold.

## Evaluation after the election
Freeze predictions with commit SHA and data snapshot prior to election day; compare against published TSE results after reconciliation.
