"""DIR-002 DWN-10: new-policy Lab display cannot invent a side."""

import importlib.util
from pathlib import Path


def _lab():
    path = Path(__file__).resolve().parents[1] / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("dir002_lab_authority", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_policy_displays_only_canonical_thesis_or_governed_side() -> None:
    lab = _lab()
    assert lab._dir002_lab_direction({
        "dir_calc_version": "dir_v1.3.0",
        "thesis__side": "BEAR",
        "governed_direction": "PUT",
        "selected_contract_side": "CALL",
        "layer2__edge_direction": "CALL",
    }) == "PUT"


def test_unassigned_thesis_cannot_be_recovered_from_contract_or_vanguard() -> None:
    lab = _lab()
    assert lab._dir002_lab_direction({
        "dir_calc_version": "dir_v1.3.0",
        "thesis__side": "UNASSIGNED",
        "governed_direction": "UNRESOLVED",
        "selected_contract_side": "CALL",
        "layer2__edge_direction": "CALL",
        "dominant_trend": "BULLISH",
    }) == ""


def test_new_policy_missing_or_conflicting_owner_does_not_fall_through() -> None:
    lab = _lab()
    assert lab._dir002_lab_direction({
        "dir_calc_version": "dir_v1.3.0",
        "selected_contract_side": "CALL",
    }) == ""
    assert lab._dir002_lab_direction({
        "dir_calc_version": "dir_v1.3.0",
        "thesis__side": "BULL",
        "governed_direction": "PUT",
    }) == ""


def test_historical_row_uses_existing_replay_reader() -> None:
    lab = _lab()
    assert lab._dir002_lab_direction({"dir_calc_version": "dir_v1.2.0"}) is None
