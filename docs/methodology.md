# Research methodology

## Design
Two connected observational spatial scales: municipality and polling establishment. Preserve the vote/turnout round, election date and geography vintage. Use historical elections (2014, 2018 and 2022), then first-round 2026 as information available by the forecast cutoff.

## Outcome
For locality `i`, election `t`, round `r`: `abstention_rate = absent / eligible`, with `absent = eligible - turnout`. Only aggregate turnout records once per section/round: candidate- or office-level results can duplicate denominators. A second-round prediction has its own (possibly provisional) eligible-voter denominator.

## Spatial analysis
Construct municipal Queen and Rook contiguity weights based on harmonized polygons; compare against metric kNN and distance thresholds as sensitivity analyses. Explicitly inspect islands, disconnected components and changes in municipal boundaries. Row-standardization is documented, not silently assumed. Map descriptive choropleths, global Moran's I and local indicators of spatial association; account for multiple testing for LISA clusters.

## Explanatory analysis
Compare nonspatial baselines with SAR, SEM and SDM; assess residual autocorrelation, coefficient stability and direct/indirect impacts. Spatial lag of the dependent variable is simultaneous and must be estimated as such. Spatial correlation alone is not evidence of contagion or causality. Include sensitivity analyses by region, electorate size, covariate definitions and matrix W.

## Predictive analysis
Model absent counts conditional on eligible counts with a binomial or overdispersed beta-binomial likelihood. Add structured spatial effects (e.g. CAR/BYM2) and election/municipality random effects as justified. Keep predictive target and explanatory estimand distinct. Estimate uncertainty from both the outcome model and uncertainty in the second-round denominator.

## Polling places
Create a longitudinal join table with section ID, establishment ID, election, mapping source and validity window. Verify addresses and coordinates. A place-level kNN graph measures establishment proximity only; claims about residential accessibility require voter catchments or independent travel-time data.

## Bias and ethics
Ecological fallacy, registration changes, section reassignment, turnout reporting differences, missing data and small-cell disclosure are principal concerns. No inference about individual electoral preference or votes forgone.
