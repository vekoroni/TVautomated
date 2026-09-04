from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_macro_enrichment_to_discovery import enrich_discovery_csv  # noqa: E402
from scripts.avshunter_options_intelligence import options_macro_alignment_adjustment  # noqa: E402


def test_macro_enrichment_stamps_discovery_and_options_advisory_score() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT / "data" / "output" / "qa") as tmp:
        discovery_csv = Path(tmp) / "discovery_candidates_ultimate_TEST.csv"
        with discovery_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["ticker", "tier", "phase", "precor_intent"])
            writer.writeheader()
            writer.writerow({"ticker": "INTC", "tier": "1", "phase": "MARKUP", "precor_intent": "CALL"})

        result = enrich_discovery_csv(
            discovery_csv,
            ROOT / "dropbox" / "macro" / "macro_intelligence_latest.json",
            ROOT / "tests" / "fixtures" / "macro_enrichment_delta_sample.json",
        )

        assert result["status"] == "PASS"
        assert result["matched_rows"] == 1

        with discovery_csv.open("r", encoding="utf-8", newline="") as fh:
            row = next(csv.DictReader(fh))

        assert row["macro_enrichment_theme_count"] == "1"
        assert "AI_CAPEX_SEMICONDUCTOR_MOMENTUM" in row["macro_enrichment_theme_ids"]

        adjustment = options_macro_alignment_adjustment(
            {"ticker": "INTC", "direction": "CALL"},
            None,
            row,
        )

        assert adjustment["options_macro_gate_preserved"] is False
        assert adjustment["options_macro_alignment_bonus"] >= 0.0
        assert adjustment["options_macro_alignment_label"] in {
            "MACRO_ALIGNED_OPTIONS_PLUS",
            "ALIGNED_REQUIRES_CONFIRMATION",
            "ALIGNED_WITH_MACRO_HEADWIND",
        }


if __name__ == "__main__":
    test_macro_enrichment_stamps_discovery_and_options_advisory_score()
    print("macro_enrichment_discovery_options tests passed")
