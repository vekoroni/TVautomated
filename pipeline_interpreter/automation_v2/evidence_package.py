"""Assemble verified capture and Lab artifacts into one staged ticker package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_KINDS = (
    "daily", "4h", "1h", "15m", "5m", "options_chain",
    "options_chain_greeks", "tape", "orderbook",
    "orderbook_imbalance_open", "orderbook_imbalance_close", "short",
)
SCREEN_KIND = {
    "options": "options_chain",
    "greeks": "options_chain_greeks",
    "tape": "tape",
    "orderbook": "orderbook",
    "short": "short",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_files(root: Path) -> tuple[Path, ...]:
    found = []
    try:
        for path in root.rglob("*.json"):
            try:
                if path.is_file():
                    found.append(path)
            except OSError:
                continue
    except OSError:
        pass
    return tuple(found)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _newest(
    manifests: list[tuple[Path, dict[str, Any]]]
) -> tuple[Path, dict[str, Any]] | None:
    if not manifests:
        return None
    return max(manifests, key=lambda item: item[0].stat().st_mtime_ns)


def _resolve_asset(manifest: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (manifest.parent / candidate).resolve()


def _discover(
    root: Path, ticker: str
) -> tuple[dict[str, Path], Path | None, list[str]]:
    symbol = ticker.upper()
    timeframes, screens, crosses, labs = [], [], [], []
    for path in _json_files(root):
        payload = _load(path)
        if not payload or str(payload.get("ticker", "")).upper() != symbol:
            continue
        schema = str(payload.get("schema_version", ""))
        if schema.startswith("capture_v1.timeframe") and payload.get("status") == "captured":
            timeframes.append((path, payload))
        elif schema == "capture_v1.ticker_market_screen.1" and payload.get("status") == "mapped":
            screens.append((path, payload))
        elif schema == "capture_v1.noii_cross.1" and payload.get("status") == "captured":
            crosses.append((path, payload))
        elif schema == "automation_v2.lab_structured.1" and payload.get("status") == "staged":
            labs.append((path, payload))

    assets: dict[str, Path] = {}
    findings: list[str] = []
    selected_timeframes = _newest(timeframes)
    if selected_timeframes:
        manifest, payload = selected_timeframes
        for value in payload.get("assets", []):
            raw = value if isinstance(value, str) else value.get("path") or value.get("filename")
            if not raw:
                continue
            source = _resolve_asset(manifest, raw)
            stem = source.stem.lower()
            for kind in ("daily", "4h", "1h", "15m", "5m"):
                if stem.endswith(f"_{kind}"):
                    assets[kind] = source

    newest_by_screen: dict[str, tuple[Path, dict[str, Any]]] = {}
    for manifest, payload in screens:
        screen = str(payload.get("screen", "")).lower()
        current = newest_by_screen.get(screen)
        if current is None or manifest.stat().st_mtime_ns > current[0].stat().st_mtime_ns:
            newest_by_screen[screen] = (manifest, payload)
    for screen, selected in newest_by_screen.items():
        kind = SCREEN_KIND.get(screen)
        if not kind:
            continue
        manifest, payload = selected
        canonical = payload.get("assets", [])
        raw = canonical[0].get("filename") if canonical else None
        if raw:
            source = _resolve_asset(manifest, raw)
        else:
            raw = payload.get("market_screen", {}).get("diagnostic")
            source = _resolve_asset(manifest, raw) if raw else Path()
        if str(source):
            assets[kind] = source

    selected_crosses = _newest(crosses)
    if selected_crosses:
        manifest, payload = selected_crosses
        for item in payload.get("assets", []):
            phase = item.get("phase")
            if phase in {"open", "close"}:
                assets[f"orderbook_imbalance_{phase}"] = _resolve_asset(
                    manifest, item["filename"]
                )

    selected_lab = _newest(labs)
    lab_manifest = selected_lab[0] if selected_lab else None
    for kind in REQUIRED_KINDS:
        source = assets.get(kind)
        if source is None:
            findings.append(f"MISSING_ASSET:{kind}")
        elif not source.is_file():
            findings.append(f"ASSET_NOT_READABLE:{kind}:{source}")
    if lab_manifest is None:
        findings.append("MISSING_STRUCTURED_LAB_MANIFEST")
    return assets, lab_manifest, findings


def assemble_evidence_package(
    *,
    ticker: str,
    staging_root: Path,
    output_directory: Path,
) -> tuple[Path, tuple[str, ...]]:
    symbol = ticker.strip().upper()
    assets, lab_manifest, findings = _discover(staging_root.resolve(), symbol)
    final = output_directory.resolve()
    if final.exists():
        raise FileExistsError(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=final.parent))
    records = []
    try:
        for kind, source in sorted(assets.items()):
            if not source.is_file():
                continue
            target = stage / f"{symbol}_{kind}{source.suffix.lower()}"
            shutil.copy2(source, target)
            records.append({
                "kind": kind, "filename": target.name,
                "source": str(source), "sha256": _sha256(target),
            })
        lab_record = None
        if lab_manifest and lab_manifest.is_file():
            target = stage / f"{symbol}_lab_structured.json"
            shutil.copy2(lab_manifest, target)
            lab_record = {
                "filename": target.name, "source": str(lab_manifest),
                "sha256": _sha256(target),
            }
        manifest = stage / "ticker_evidence_package.json"
        manifest.write_text(json.dumps({
            "schema_version": "automation_v2.evidence_package.1",
            "ticker": symbol,
            "status": "complete" if not findings else "incomplete",
            "required_kinds": list(REQUIRED_KINDS),
            "assets": records,
            "structured_lab": lab_record,
            "findings": findings,
            "published": False,
        }, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(stage, final)
        return final / manifest.name, tuple(findings)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

