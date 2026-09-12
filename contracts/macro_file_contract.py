"""Shared file contract for the AVSHUNTER Macro bounded context."""

from __future__ import annotations

from pathlib import Path


MARKET_DATA_DIRECTORY_NAME = "market_data"
GEX_PROXY_FILENAME = "avshunter_gex_proxy.csv"
GEX_BY_STRIKE_FILENAME = "avshunter_gex_by_strike.csv"
GEX_MANIFEST_FILENAME = "avshunter_gex_run_manifest.json"
GEX_ERRORS_FILENAME = "avshunter_gex_errors.txt"


def market_data_directory(repository_root: Path | str) -> Path:
    """Return the one governed compatibility directory used by Macro producers."""

    return Path(repository_root) / "dropbox" / MARKET_DATA_DIRECTORY_NAME


def market_data_directory_from_dropbox(dropbox_root: Path | str) -> Path:
    """Return the Macro input directory from a configured Dropbox root."""

    return Path(dropbox_root) / MARKET_DATA_DIRECTORY_NAME


__all__ = [
    "GEX_BY_STRIKE_FILENAME",
    "GEX_ERRORS_FILENAME",
    "GEX_MANIFEST_FILENAME",
    "GEX_PROXY_FILENAME",
    "MARKET_DATA_DIRECTORY_NAME",
    "market_data_directory",
    "market_data_directory_from_dropbox",
]
