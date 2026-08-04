"""Machine-readable legacy-versus-shadow artifact comparison."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .compatibility import ArtifactContract
from .models import CAPITAL_DENIED, EXECUTION_NONE


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    ticker: str
    legacy_complete: bool
    shadow_complete: bool
    sovereign_preserved: bool
    differences: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.shadow_complete and self.sovereign_preserved


def compare_legacy_to_shadow(
    legacy: ArtifactContract, shadow_dir: str | Path
) -> ComparisonReport:
    root = Path(shadow_dir)
    differences = []
    manifest_path = root / "artifact_manifest.json"
    if not manifest_path.is_file():
        return ComparisonReport(
            ticker=legacy.ticker,
            legacy_complete=legacy.complete,
            shadow_complete=False,
            sovereign_preserved=False,
            differences=("SHADOW_MISSING:artifact_manifest.json",),
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_names = {item["name"] for item in manifest.get("artifacts", ())}
    required_patterns = (
        "raw_response_",
        "raw_story_",
        "ticker_" + legacy.ticker.lower() + "_trade_brief_",
        "ticker_" + legacy.ticker.lower() + "_interpreter_",
    )
    for prefix in required_patterns:
        if not any(name.startswith(prefix) for name in artifact_names):
            differences.append(f"SHADOW_MISSING_PREFIX:{prefix}")
    expected_sidecar = f"_{legacy.ticker}_interpreter.json"
    if not any(name.endswith(expected_sidecar) for name in artifact_names):
        differences.append(f"SHADOW_MISSING_SUFFIX:{expected_sidecar}")
    csv_files = tuple(root.glob(f"ticker_{legacy.ticker.lower()}_trade_brief_*.csv"))
    sovereign = False
    if len(csv_files) == 1:
        with csv_files[0].open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle), {})
        sovereign = (
            row.get("execution_permission") == EXECUTION_NONE
            and row.get("capital_permission") == CAPITAL_DENIED
            and row.get("eil_action") == "STOP"
            and row.get("final_verdict") not in {"GO", "EXEC"}
        )
        if not sovereign:
            differences.append("SOVEREIGN_OUTPUT_MISMATCH")
    else:
        differences.append(f"SHADOW_TRADE_BRIEF_COUNT:{len(csv_files)}")
    if not legacy.complete:
        differences.extend(f"LEGACY_KNOWN_MISSING:{item}" for item in legacy.missing_required)
    shadow_complete = bool(manifest.get("complete")) and not any(
        item.startswith("SHADOW_") for item in differences
    )
    return ComparisonReport(
        ticker=legacy.ticker,
        legacy_complete=legacy.complete,
        shadow_complete=shadow_complete,
        sovereign_preserved=sovereign,
        differences=tuple(differences),
    )
