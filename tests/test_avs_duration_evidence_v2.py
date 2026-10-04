"""Duration evidence v2 (ACK 3 Oct 2026; anticipated-move design §4 / §9 step 3).

Business rules:
- Production duration evidence is rebuilt on the refreshed bars (to 2026-10-01) for the original panel.
- Its calibration on the 500-ticker holdout is recorded with the evidence, as measured against criteria fixed
  before the results: timing passed (q50 59.2% in [40, 60]; q80 83.2% in [70, 90]); probability did not
  (top band predicted 0.85, observed 0.79). Labels say what was measured (R6): timing is holdout-calibrated,
  probability stays in-sample.
- v1 is kept (repair, don't delete); the policy points at v2.
"""
import json
from pathlib import Path

from domain.structure_behaviour.duration import attach_duration, load_duration_evidence
from domain.structure_behaviour.policy import load_policy

ROOT = Path(__file__).resolve().parents[1]


def test_production_points_at_v2_with_its_holdout_calibration():
    path = ROOT / load_policy()["duration"]["evidence_path"]
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["version"] == "beh001_duration_evidence_v3"   # step 4a: adds OUTCOME_FROM_DETECTION
    assert evidence["data_end"] == "2026-10-01"
    cal = evidence["holdout_calibration"]
    assert cal["timing_state"] == "HOLDOUT_PASS"
    assert cal["probability_state"] == "HOLDOUT_FAIL_UPPER_BANDS_OVERSTATED"
    assert cal["timing_outcome_from_detection"]["share_le_q80"] > 0.8
    assert (ROOT / "config" / "beh001_duration_evidence_v1.json").exists()
    assert (ROOT / "config" / "beh001_duration_evidence_v2.json").exists()


def test_v2_attaches_to_a_live_candidate():
    evidence = load_duration_evidence(ROOT / load_policy()["duration"]["evidence_path"])
    c = {"Signal_State": "DETECTED", "Direction": "BEAR", "Timeframe": "1d", "Structure_Scope": "LOCAL",
         "Signal_Type": "Seller Absorption Breakdown", "Age_Bars": 1, "As_Of": "2026-10-02"}
    attach_duration([c], evidence)
    assert c["Duration_Status"] not in {"EVIDENCE_NOT_CAUSAL", "NO_EVIDENCE_FILE"}
