"""Read-only evidence discovery with exact ticker identity."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .models import EvidenceItem, EvidenceManifest


_KNOWN_SUFFIXES = (
    "short",
    "options_chain",
    "orderbook_imbalance_close",
    "orderbook_imbalance_open",
    "orderbook",
    "tape",
    "options_chain_greeks",
    "daily",
    "4h",
    "1h",
    "15m",
    "5m",
    "lab_qomega",
    "lab_convexity",
    "lab_options",
    "lab_tradesetup",
    "lab_overview",
)


def filename_belongs_to_ticker(path: str | Path, ticker: str) -> bool:
    """Match an exact ticker token, preventing F from matching NFLX."""
    symbol = ticker.strip().upper()
    if not symbol:
        return False
    stem = Path(path).stem.upper()
    return re.match(rf"^{re.escape(symbol)}(?:_|$)", stem) is not None


def classify_chart_asset(path: str | Path, ticker: str) -> str:
    if not filename_belongs_to_ticker(path, ticker):
        return "unmatched"
    stem = Path(path).stem
    suffix = stem[len(ticker) :].lstrip("_").lower()
    for known in sorted(_KNOWN_SUFFIXES, key=len, reverse=True):
        if suffix == known:
            return known
    return "other"


def discover_ticker_assets(
    roots: Iterable[str | Path],
    ticker: str,
    extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp"),
) -> tuple[Path, ...]:
    """Return stable, exact-token matches without modifying source folders."""
    matches: dict[str, Path] = {}
    allowed = {extension.lower() for extension in extensions}
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in allowed
                and filename_belongs_to_ticker(path, ticker)
            ):
                matches[str(path.resolve()).lower()] = path.resolve()
    return tuple(sorted(matches.values(), key=lambda value: str(value).lower()))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_chart_manifest(
    *,
    ticker: str,
    run_id: str,
    invocation_id: str,
    as_of: str,
    assets: Iterable[str | Path],
) -> EvidenceManifest:
    items = []
    findings = []
    for asset_value in assets:
        asset = Path(asset_value)
        if not filename_belongs_to_ticker(asset, ticker):
            findings.append(f"REJECTED_AMBIGUOUS_ASSET:{asset.name}")
            continue
        if not asset.is_file():
            findings.append(f"MISSING_ASSET:{asset}")
            continue
        items.append(
            EvidenceItem(
                kind=f"chart:{classify_chart_asset(asset, ticker)}",
                source=str(asset.resolve()),
                ticker=ticker,
                run_id=run_id,
                as_of=as_of,
                sha256=sha256_file(asset),
            )
        )
    return EvidenceManifest(
        ticker=ticker,
        run_id=run_id,
        invocation_id=invocation_id,
        as_of=as_of,
        items=tuple(items),
        findings=tuple(findings),
    )
