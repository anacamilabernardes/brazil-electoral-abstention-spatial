# Research and implementation roadmap

## Phase 0 — Repository foundation
English documentation, package scaffold, tests and data contract. No downloaded data committed.

## Phase 1 — TSE/IBGE harmonization (ETL scaffold implemented; official ingestion pending)
Implemented: explicit official archive URL manifest and ZIP downloader; TSE president-only municipality/zone turnout normalization; validated TSE-to-IBGE code joins; 2025 IBGE polygon ingestion; municipal panel, GeoPackage, provenance and coverage reports; synthetic tests and CI configuration.

Outstanding: execute against the full official archives, inspect/adjust real schemas, independently reconcile national/state totals, audit historical crosswalk/geography vintages, and freeze October 2026 source snapshots.

## Phase 2 — Spatial exploration
Produce mapping data, Moran's I/LISA, sensitivity analyses for spatial weights, residual checks and descriptive reporting.

## Phase 3 — Econometric estimation
Run OLS, SAR, SEM, SDM and feasible panel models. Interpret spatial impact measures, not only coefficients.

## Phase 4 — Operational 2026 model
Fit historical within-election change baselines and binomial spatial alternatives. Backtest on held-out elections, calibrate uncertainty, freeze Oct 2026 predictions with a declared cutoff.

## Phase 5 — Polling-place extension
Acquire verified section-to-place links, geocode establishments, document ambiguous matches and estimate within-municipality variation.

## Phase 6 — Reproducibility and dashboard
Version inputs and results, document diagnostics and build municipal/place maps for research review.

### Proposed first issues
1. Audit TSE turnout dataset schemas (2014/2018/2022/2026).
2. Implement geography code harmonization and state reconciliation.
3. Build municipal adjacency matrix with island handling.
4. Establish historical time-split forecast benchmark.
5. Investigate section-to-establishment mapping availability.
