# Statistical specifications

Let `y` be a municipal abstention-rate vector, `X` the covariate matrix, and `W` a predetermined spatial weights matrix.

- **OLS:** `y = Xβ + ε` — reference estimate.
- **SAR:** `y = ρWy + Xβ + ε` — simultaneous spatially lagged outcome.
- **SEM:** `y = Xβ + u; u = λWu + ε` — spatially structured errors.
- **SDM:** `y = ρWy + Xβ + WXθ + ε` — outcome and covariate spatial lags.
- **Panel:** time and locality effects when supported by temporal variation and identifying assumptions.

For SDM, spatial marginal effect matrix for feature `k` is `(I - ρW)^(-1) (β_k I + θ_k W)`; distinguish own, neighbors' and total impacts from raw coefficients.

**Forecasting likelihood:** `absent_it ~ Binomial(eligible_it, p_it)`, `logit(p_it) = α + X_it β + u_i + τ_t + δ_it`. Test beta-binomial overdispersion and CAR/BYM2 spatial random effects.

### Model comparison
Check feature pre-cutoff availability, residual spatial autocorrelation, conditioning, spatial-weight sensitivity, coefficient stability and held-out forecast scores. Estimators with incomparable likelihoods must not be ranked using AIC as though they shared the same estimation method.

### Practical packages
GeoPandas, libpysal, esda, spreg, statsmodels, PyMC and ArviZ. Sparse solvers are preferred for nationwide data where supported.
