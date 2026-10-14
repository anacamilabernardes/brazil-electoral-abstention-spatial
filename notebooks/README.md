# Jupyter notebooks

These notebooks are **unexecuted research templates**; no official election data, calculated results, or geocoded polling-place records are included.

## Notebooks
- [01_municipal_spatial_eda.ipynb](01_municipal_spatial_eda.ipynb): Validate normalized municipal turnout, summarize the observed 2022 second round, calculate Moran's I with audited geometries, and illustrate the historical round-change benchmark.
- [02_polling_place_data_audit.ipynb](02_polling_place_data_audit.ipynb): Audit section-to-establishment mapping quality and aggregate verified polling-place turnout.

## Run
From the repository root:
```bash
python -m pip install -e ".[dev]"
jupyter lab
```
Open a notebook in JupyterLab and run its cells in sequence. All data checks will report missing input files rather than simulating election observations.

## Inputs (not tracked in Git)
```text
data/processed/municipal_panel.csv
data/geospatial/municipalities_2025.shp   # plus its sidecar files
data/processed/section_turnout.csv
data/processed/section_place_mapping.csv
data/processed/polling_places.csv
```
Normalize source files first using [the data dictionary](../docs/data-dictionary.md). When using Shapefile, keep the required .dbf, .shx and .prj sidecar files. If boundaries or turnout units do not align, fix the crosswalk; do not silently drop municipalities.

## Reporting requirements
State the data vintage, publication cutoff, number of municipalities/establishments retained, mapping coverage, treatment of geographic islands, and model version. Do not present the baseline as a validated 2026 election forecast.
