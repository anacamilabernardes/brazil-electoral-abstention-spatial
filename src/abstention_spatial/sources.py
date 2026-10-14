"""Pinned *source URLs*, downloads, and integrity receipts for official archives."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TSE_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
IBGE_BASE = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_municipais/municipio_2025/Brasil"
)

OFFICIAL_ARCHIVES: dict[str, str] = {
    **{
        f"tse-munzona-{year}": (
            f"{TSE_BASE}/detalhe_votacao_munzona/detalhe_votacao_munzona_{year}.zip"
        )
        for year in (2014, 2018, 2022, 2026)
    },
    "tse-ibge-crosswalk": f"{TSE_BASE}/municipio_tse_ibge/municipio_tse_ibge.zip",
    "ibge-municipalities-2025": f"{IBGE_BASE}/BR_Municipios_2025.zip",
}


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(block_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receipt(path: Path, *, source_url: str | None = None) -> dict:
    """The timestamp is a retrieval/processing observation, not a source release date."""
    path = Path(path)
    return {
        "filename": path.name,
        "source_url": source_url,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def official_path(name: str, raw_dir: Path) -> Path:
    if name not in OFFICIAL_ARCHIVES:
        raise ValueError(f"Unknown official archive: {name}")
    return Path(raw_dir) / Path(OFFICIAL_ARCHIVES[name]).name


def download_official(
    name: str, raw_dir: Path, *, timeout: int = 120, max_bytes: int = 2 * 1024**3
) -> dict:
    """Download an enumerated HTTPS source atomically; never replace an existing file.

    A pre-existing archive is rehashed and returned unchanged. Delete an existing
    file deliberately to fetch a new official revision. HTTPS redirects are allowed
    only to the original host (not arbitrary domains).
    """
    if name not in OFFICIAL_ARCHIVES:
        raise ValueError(f"Unknown official archive: {name}")
    url = OFFICIAL_ARCHIVES[name]
    dest = official_path(name, raw_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.stat().st_size == 0:
            raise ValueError(f"Empty cached archive: {dest}")
        return {"name": name, "cached": True, **receipt(dest, source_url=url)}
    part = dest.with_name(dest.name + ".part")
    if part.exists():
        raise FileExistsError(f"Incomplete download exists: {part}; remove it after review")
    from urllib.parse import urlparse

    request = Request(url, headers={"User-Agent": "abstention-spatial-research/0.2"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if urlparse(response.geturl()).hostname != urlparse(url).hostname:
                raise ValueError("Unexpected redirect host; aborting download")
            total = 0
            with part.open("xb") as stream:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Archive exceeded maximum allowed size")
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        if total == 0:
            raise ValueError("Empty response from official source")
        with part.open("rb") as check:
            signature = check.read(4)
        if signature[:2] != b"PK":
            raise ValueError("Official URL did not return a ZIP archive")
        os.replace(part, dest)
    except (OSError, URLError, HTTPError, ValueError):
        part.unlink(missing_ok=True)
        raise
    result = {"name": name, "cached": False, **receipt(dest, source_url=url)}
    save_json(dest.with_suffix(dest.suffix + ".receipt.json"), result)
    return result


def save_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique intermediate filename prevents accidental partial overwrite.
    part = path.with_name(path.name + ".part")
    if part.exists():
        raise FileExistsError(f"Pending output exists: {part}")
    try:
        part.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
