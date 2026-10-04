"""DIR-002 DWN-11 / DSC-21 (CLAUDE.md rule 6): the post-Discovery macro
rewrite adds namespaced advisory columns; it never overwrites Discovery's
direction-authority field or writes a CALL/PUT macro vote into the row."""
import csv
from pathlib import Path

from scripts.apply_macro_enrichment_to_discovery import enrich_discovery_csv

ROOT = Path(__file__).resolve().parents[1]


def test_macro_rewrite_is_advisory_namespaced(tmp_path):
    discovery_csv = tmp_path / "discovery_candidates_ultimate_TEST.csv"
    with discovery_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "direction", "macro_direction_authority"])
        writer.writeheader()
        writer.writerow({"ticker": "INTC", "direction": "CALL", "macro_direction_authority": "NONE"})
    result = enrich_discovery_csv(
        discovery_csv,
        ROOT / "dropbox" / "macro" / "macro_intelligence_latest.json",
        ROOT / "tests" / "fixtures" / "macro_enrichment_delta_sample.json",
    )
    assert result["matched_rows"] == 1
    with discovery_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        row = next(reader)
        fields = reader.fieldnames
    assert row["macro_direction_authority"] == "NONE"
    assert row["direction"] == "CALL"
    assert "macro_direction_vote" not in fields
    assert "macro_raw_direction_hint" not in fields
    assert "macro_advisory__side_hint" in fields
    assert row["macro_advisory__authority"] == "DISPLAY_ONLY"
