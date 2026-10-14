"""Strict ingestion of TSE *turnout* from office-filtered munzona result archives.

Important: vote-by-candidate/party files are NOT valid turnout inputs because
QT_APTOS repeats across candidates. This reader accepts only verified
'detalhe_votacao_munzona' CSVs (or a controlled normalized fixture).
"""

from __future__ import annotations

import csv
import io
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterator

import pandas as pd

from .core import validate_municipal_panel

YEARS = (2014, 2018, 2022, 2026)
COUNTS = {"QT_APTOS": "eligible", "QT_COMPARECIMENTO": "turnout", "QT_ABSTENCOES": "absent"}
COUNT_COLUMNS = [*COUNTS.values(), "uninstalled", "unaccounted"]
UF_CODES = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
MANDATORY = {"NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", *COUNTS}


def canon(name: str) -> str:
    return "".join(
        c if c.isalnum() else "_"
        for c in unicodedata.normalize("NFKD", str(name).strip().upper())
        if not unicodedata.combining(c)
    ).strip("_")


def read_csv_chunks(
    path: Path, *, member: str | None = None, chunksize: int = 200_000,
    encoding: str = "latin-1", delimiter: str | None = None,
) -> Iterator[pd.DataFrame]:
    """Stream a CSV or one named ZIP CSV without unpacking arbitrary archives."""
    path = Path(path)
    if chunksize < 1:
        raise ValueError("chunksize must be positive")

    def read(stream: io.TextIOBase) -> Iterator[pd.DataFrame]:
        sample = stream.read(8192)
        stream.seek(0) if stream.seekable() else None
        if not stream.seekable():
            raise ValueError("CSV input stream must be seekable")
        sep = delimiter
        if sep is None:
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=";,|\t").delimiter
            except csv.Error:
                raise ValueError("Cannot detect delimiter; specify --delimiter") from None
        if sep not in (";", ",", "|", "\t"):
            raise ValueError("Unsupported delimiter")
        for chunk in pd.read_csv(
            stream, sep=sep, dtype=str, keep_default_na=False,
            chunksize=chunksize, on_bad_lines="error", low_memory=False,
        ):
            chunk.columns = [canon(c) for c in chunk.columns]
            if chunk.columns.duplicated().any():
                raise ValueError("Ambiguous duplicate column names after normalization")
            yield chunk

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [s for s in archive.namelist() if s.lower().endswith(".csv") and not s.endswith("/")]
            if member is None:
                if len(names) != 1:
                    raise ValueError(f"Archive contains {len(names)} CSVs; select --member explicitly: {names[:12]}")
                chosen = names[0]
            else:
                if member not in names:
                    raise ValueError(f"CSV member not found in archive: {member}")
                chosen = member
            with archive.open(chosen) as binary, io.TextIOWrapper(
                binary, encoding=encoding, errors="strict", newline=""
            ) as stream:
                # TextIOWrapper around ZipExtFile supports seek() by reopening and
                # replaying, but may be expensive for large compressed archives.
                # Read the 8KB peek and rewind only once, before chunk processing.
                yield from read(stream)
    else:
        with path.open("r", encoding=encoding, errors="strict", newline="") as stream:
            yield from read(stream)


def require_columns(frame: pd.DataFrame, expected: set[str]) -> None:
    absent = expected - set(frame.columns)
    if absent:
        raise ValueError(f"Missing required source columns: {sorted(absent)}; found: {list(frame.columns)}")


def digits(series: pd.Series, name: str, *, maxlen: int | None = None) -> pd.Series:
    values = series.astype("string").str.strip()
    valid = values.str.fullmatch(r"[0-9]+", na=False)
    if maxlen is not None:
        valid &= values.str.len() <= maxlen
    if not valid.all():
        raise ValueError(f"Invalid {name}: examples {values[~valid].head(3).tolist()}")
    return values


def integer_counts(frame: pd.DataFrame, *, allow_discrepancies: bool = False) -> pd.DataFrame:
    out = frame.copy()
    for original, standardized in COUNTS.items():
        source = digits(out[original], original)
        out[standardized] = pd.to_numeric(source, errors="raise").astype("int64")
    out["uninstalled"] = (
        pd.to_numeric(digits(out["QT_ELEITORES_SECOES_NAO_INSTALADAS"],
                             "QT_ELEITORES_SECOES_NAO_INSTALADAS")).astype("int64")
        if "QT_ELEITORES_SECOES_NAO_INSTALADAS" in out else 0
    )
    out["unaccounted"] = out["eligible"] - out["turnout"] - out["absent"] - out["uninstalled"]
    wrong = (out["eligible"] <= 0) | (out["unaccounted"] < 0)
    if not allow_discrepancies:
        wrong |= out["unaccounted"] != 0
    if wrong.any():
        raise ValueError(f"Inconsistent turnout counts in {int(wrong.sum())} TSE rows")
    return out


def read_munzona(path: Path, year: int, *,
                 max_round: int = 2, member: str | None = None,
                 chunksize: int = 200_000, cutoff: date = date(2026, 10, 14),
                 allow_discrepancies: bool = False) -> tuple[pd.DataFrame, dict]:
    """Read one election-year archive, filter president before counting eligible.

    Duplicate per-zone/transit keys, ambiguous office identification, mixed years and
    missing round 1 are fatal. International district ZZ is reported separately
    because it has no IBGE municipality polygon.
    """
    if year not in YEARS or max_round not in (1, 2):
        raise ValueError("Unsupported year or round bound")
    if cutoff > date(2026, 10, 14):
        raise ValueError("cutoff cannot exceed 2026-10-14")
    if year == 2026:
        if cutoff < date(2026, 10, 4):
            raise ValueError("First-round 2026 turnout was not observable by this cutoff")
        max_round = 1
    if member is None and Path(path).suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            expected = f"detalhe_votacao_munzona_{year}_BR.csv"
            matches = [n for n in archive.namelist() if n == expected]
            if len(matches) == 1:
                member = matches[0]
    frames: list[pd.DataFrame] = []
    seen: set[tuple] = set()
    audit: dict = {"year": year, "source": str(path), "out_of_scope_zz_rows": 0,
                   "other_cargo_rows": 0, "future_round_rows": 0, "source_rows": 0,
                   "domestic_president_rows": 0, "member": member,
                   "count_discrepancies": [], "zz_totals_by_round": {}}
    for chunk in read_csv_chunks(path, member=member, chunksize=chunksize):
        require_columns(chunk, MANDATORY)
        if "ANO_ELEICAO" in chunk.columns:
            mismatch = chunk["ANO_ELEICAO"].astype(str).str.strip() != str(year)
            if mismatch.any():
                raise ValueError("Archive contains a mismatched ANO_ELEICAO")
        if "CD_CARGO" not in chunk.columns and "DS_CARGO" not in chunk.columns:
            raise ValueError("Cannot identify a single office; refusing possible voter double-counting")
        audit["source_rows"] += len(chunk)
        if "CD_CARGO" in chunk.columns:
            office = chunk["CD_CARGO"].astype(str).str.strip().str.lstrip("0") == "1"
        else:
            office = chunk["DS_CARGO"].map(canon) == "PRESIDENTE"
        audit["other_cargo_rows"] += int((~office).sum())
        chunk = chunk.loc[office].copy()
        if chunk.empty:
            continue
        turns = digits(chunk["NR_TURNO"], "NR_TURNO")
        if not turns.isin(["1", "2"]).all():
            raise ValueError("Unexpected NR_TURNO in presidential records")
        audit["future_round_rows"] += int((turns.astype(int) > max_round).sum())
        chunk = chunk.loc[turns.astype(int) <= max_round].copy()
        if chunk.empty:
            continue
        for field in ("DT_GERACAO", "DT_ULTIMA_TOTALIZACAO"):
            if field in chunk:
                dates = pd.to_datetime(chunk[field], format="%d/%m/%Y", errors="raise").dt.date
                if (dates > cutoff).any():
                    raise ValueError(f"{field} exceeds forecasting cutoff")
        ufs = chunk["SG_UF"].astype(str).str.strip().str.upper()
        audit["out_of_scope_zz_rows"] += int((ufs == "ZZ").sum())
        for turn, foreign in chunk.loc[ufs == "ZZ"].groupby("NR_TURNO"):
            totals = audit["zz_totals_by_round"].setdefault(str(turn), {c: 0 for c in COUNTS.values()})
            for original, standardized in COUNTS.items():
                totals[standardized] += int(pd.to_numeric(digits(foreign[original], original)).sum())
        chunk = chunk.loc[ufs != "ZZ"].copy()
        if chunk.empty:
            continue
        if not ufs.loc[chunk.index].isin(UF_CODES).all():
            raise ValueError("Invalid domestic SG_UF")
        chunk["tse_code"] = digits(chunk["CD_MUNICIPIO"], "CD_MUNICIPIO", maxlen=5).str.zfill(5)
        chunk["electoral_zone"] = digits(chunk["NR_ZONA"], "NR_ZONA", maxlen=4).str.zfill(4)
        chunk["round"] = digits(chunk["NR_TURNO"], "NR_TURNO").astype(int)
        chunk["uf"] = ufs.loc[chunk.index]
        if "ST_VOTO_EM_TRANSITO" in chunk:
            chunk["transit"] = chunk["ST_VOTO_EM_TRANSITO"].str.strip().str.upper()
            if not chunk["transit"].isin(["N", "S"]).all():
                raise ValueError("Unexpected ST_VOTO_EM_TRANSITO")
        else:
            chunk["transit"] = "N"
        chunk = integer_counts(chunk, allow_discrepancies=allow_discrepancies)
        keys = ["round", "uf", "tse_code", "electoral_zone", "transit"]
        audit["count_discrepancies"].extend(
            chunk.loc[chunk["unaccounted"] != 0, keys + COUNT_COLUMNS].to_dict("records")
        )
        if chunk.duplicated(keys).any():
            raise ValueError("Duplicate president-zone turnout records in source chunk")
        for values in chunk[keys].itertuples(index=False, name=None):
            if values in seen:
                raise ValueError("Duplicate president-zone turnout record across chunks")
            seen.add(values)
        audit["domestic_president_rows"] += len(chunk)
        frames.append(chunk[keys + COUNT_COLUMNS])
    if not frames:
        raise ValueError(f"No eligible domestic presidential turnout records for {year}")
    zones = pd.concat(frames, ignore_index=True)
    if 1 not in zones["round"].unique():
        raise ValueError("No first-round data present")
    zones.insert(0, "year", year)
    audit["uninstalled_electors"] = int(zones["uninstalled"].sum())
    audit["unaccounted_electors"] = int(zones["unaccounted"].sum())
    audit["transit_rows"] = int(zones["transit"].eq("S").sum())
    audit["rounds_ingested"] = sorted(int(i) for i in zones["round"].unique())
    audit["domestic_eligible_by_round"] = {
        str(k): int(v) for k, v in zones.groupby("round")["eligible"].sum().items()
    }
    return zones, audit


TSE_CODE_ALIASES = (
    "CD_MUNICIPIO_TSE", "CODIGO_MUNICIPIO_TSE", "COD_MUNICIPIO_TSE",
    "CODIGO_TSE", "COD_TSE", "CD_TSE", "COD_TSE_MUNICIPIO", "CD_MUNICIPIO",
)
IBGE_CODE_ALIASES = (
    "CD_MUNICIPIO_IBGE", "CODIGO_MUNICIPIO_IBGE", "COD_MUNICIPIO_IBGE",
    "CODIGO_IBGE", "COD_IBGE", "CD_IBGE", "GEOCODIGO_IBGE", "CD_GEOCODIGO",
)
UF_ALIASES = ("SG_UF", "SIGLA_UF", "UF")


def _select_column(columns: list[str], options: tuple[str, ...], name: str) -> str:
    existing = [col for col in options if col in columns]
    if not existing:
        raise ValueError(f"Missing {name} in crosswalk; available columns: {columns}")
    return existing[0]


def load_crosswalk(path: Path, *, member: str | None = None,
                   columns: tuple[str, str, str] | None = None) -> pd.DataFrame:
    """Normalize the official TSE/IBGE join. Optional exact column overrides: TSE, IBGE, UF."""
    frames = list(read_csv_chunks(path, member=member))
    if len(frames) == 0:
        raise ValueError("Empty crosswalk")
    frame = pd.concat(frames, ignore_index=True)
    fields = list(frame.columns)
    if columns is None:
        tse_col = _select_column(fields, TSE_CODE_ALIASES, "TSE municipal code")
        ibge_col = _select_column(fields, IBGE_CODE_ALIASES, "IBGE municipal code")
        uf_col = _select_column(fields, UF_ALIASES, "state abbreviation")
    else:
        tse_col, ibge_col, uf_col = (canon(n) for n in columns)
        require_columns(frame, {tse_col, ibge_col, uf_col})
    out = pd.DataFrame({
        "tse_code": digits(frame[tse_col], tse_col, maxlen=5).str.zfill(5),
        "municipality_code": digits(frame[ibge_col], ibge_col).str.zfill(7),
        "uf": frame[uf_col].astype("string").str.strip().str.upper(),
    })
    if not out["municipality_code"].str.fullmatch(r"\d{7}").all():
        raise ValueError("IBGE municipality codes must be seven digits")
    if not out["uf"].str.fullmatch(r"[A-Z]{2}").all():
        raise ValueError("Malformed UF in crosswalk")
    if out.duplicated(["uf", "tse_code"]).any():
        raise ValueError("Crosswalk is not unique by UF/TSE code")
    if out.duplicated(["municipality_code"]).any():
        raise ValueError("Crosswalk is not unique by IBGE code")
    if out.empty:
        raise ValueError("Empty crosswalk")
    return out.sort_values(["uf", "tse_code"]).reset_index(drop=True)


def harmonize_zones(zones: pd.DataFrame, crosswalk: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map zone counts to IBGE codes and produce checked municipal panel.

    Missing identifiers fail without dropping rows. The zone-level table is
    retained for later establishment-level linkage and audit.
    """
    joined = zones.merge(crosswalk, on=["uf", "tse_code"], how="left",
                         validate="many_to_one", indicator=True)
    missing = joined["municipality_code"].isna()
    if missing.any():
        sample = joined.loc[missing, ["year", "uf", "tse_code"]].drop_duplicates().head(10)
        raise ValueError(f"Missing official IBGE mapping ({int(missing.sum())} rows): {sample.to_dict('records')}")
    joined = joined.drop(columns=["_merge"])
    key = ["municipality_code", "year", "round"]
    panel = joined.groupby(key, as_index=False, sort=True)[
        COUNT_COLUMNS
    ].sum()
    panel = validate_municipal_panel(panel)
    for col in COUNT_COLUMNS:
        if int(panel[col].sum()) != int(joined[col].sum()):
            raise ValueError(f"Aggregation changed total {col}")
    return joined, panel
