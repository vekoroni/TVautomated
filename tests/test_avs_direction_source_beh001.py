"""ACK decision, 2 Oct 2026: move the fixes out of shadow into production. BEH-001 is the
production direction owner; Precor is retired as the direction owner (its Spring rule caused
80% of the shadow disagreement). Rollback stays available as the governed value."""
import json
from pathlib import Path

from contracts.direction_governance import side_assignment_runtime

CONFIG = Path(__file__).resolve().parents[1] / "config" / "dir002_side_assignment_v1.json"


def test_beh001_is_the_production_direction_source_and_rollback_remains_governed():
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert raw["production_direction_source"] == "beh001_v1"
    assert raw["rollback_value"] == "legacy_rollback"
    assert side_assignment_runtime()["production_direction_source"] == "beh001_v1"
    assert raw["cutover"]["decided_by"] == "ACK" and raw["cutover"]["date"] == "2026-10-02"
