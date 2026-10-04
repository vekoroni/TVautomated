"""SOR-001: measured Crabel state must reach fusion without an absent=NONE alias."""

import pandas as pd

from avshunter_discovery_ULTIMATE import UltimateConfig, crabel_compression
from enums_structural import CrabelState
from swing_fusion import fuse_wyckoff_crabel


def _frame(*, compressed: bool) -> pd.DataFrame:
    widths = [10.0] * 33 + ([2.0] * 7 if compressed else [10.0] * 7)
    return pd.DataFrame({
        "open": [100.0] * 40,
        "high": [100.0 + width / 2 for width in widths],
        "low": [100.0 - width / 2 for width in widths],
        "close": [100.0] * 40,
        "volume": [1_000_000] * 39 + [600_000],
    })


def _wyckoff() -> dict:
    return {
        "current_phase": "C", "operator": "ACCUMULATION",
        "control_state": "BUYERS", "truth_confidence": 80,
        "phase_evidence_strength": 80, "contradictions": [],
    }


def test_qualifying_compression_state_survives_producer_to_fusion():
    measured = crabel_compression(_frame(compressed=True), UltimateConfig())
    assert measured["passed"] is True
    assert measured["state"] == CrabelState.READY
    fusion = fuse_wyckoff_crabel(_wyckoff(), measured)
    assert fusion["audit"]["crabel_state"] == CrabelState.READY
    assert fusion["alignment_score"] == 80


def test_no_compression_and_unavailable_data_are_distinct():
    none = crabel_compression(_frame(compressed=False), UltimateConfig())
    unavailable = crabel_compression(_frame(compressed=True).head(5), UltimateConfig())
    assert none["state"] == CrabelState.NONE
    assert unavailable["state"] == CrabelState.DATA_INSUFFICIENT
    assert fuse_wyckoff_crabel(_wyckoff(), unavailable)["audit"]["crabel_state"] == CrabelState.DATA_INSUFFICIENT


def test_default_production_contract_contains_typed_state():
    assert crabel_compression(_frame(compressed=True), UltimateConfig())["state"] == CrabelState.READY
