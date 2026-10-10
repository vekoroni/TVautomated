"""Phase 0 characterisation (DISCOVERY_VANGUARD_REDESIGN_20261007.md §12).

These tests pin TODAY's behaviour of run 20261006_060401 from a frozen read-only extract
(tests/fixtures/phase0/). They describe defects, not desired behaviour: each later phase changes one of these
numbers deliberately, and must update the matching assertion in the same change, with the reason.
They never read live data/ and never call a provider.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "phase0"
_spec = importlib.util.spec_from_file_location("p0", ROOT / "Enhancements" / "phase0" / "p0_characterise.py")
p0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p0)

pytestmark = pytest.mark.skipif(not (FIX / "discovery.parquet").exists(), reason="phase 0 fixture not extracted")


@pytest.fixture(scope="module")
def d():
    return p0.load(FIX)


def test_funnel_today_51_go_from_1814_discovery_tickers(d):
    f = p0.funnel(d)
    assert (f["discovery_tickers"], f["vanguard_pass"], f["vanguard_reject"], f["lab_tickers"]) == (1814, 1702, 112, 1636)
    assert f["lab_go_or_go_limit"] == 51
    assert f["discovery_side"] == {"BEAR": 743, "UNASSIGNED": 645, "BULL": 426}


def test_every_vanguard_side_block_fails_on_the_timezone_seam(d):
    assert p0.funnel(d)["side_block_reason"] == {"SIDE_BLOCK_ERROR:TypeError": 1702}


def test_card_story_is_assembled_from_different_candidates(d):
    s = p0.story_mismatch(d)
    assert s["directed_thesis_candidates_in_lab"] == 1052
    assert s["setup_shown_differs_from_thesis"] == 646
    assert s["setup_differs_on_go"] == 32
    assert s["target_source"] == {"PRIOR_RANGE_EXTREME": 964}
    assert s["trigger_price_source"] == {"WBS_PHASE_C_CONFIRMED_BREAK": 1039}
    assert s["trigger_lab_vs_candidate_differs"] == 1038


def test_thesis_candidate_rarely_gets_its_own_contract(d):
    s = p0.story_mismatch(d)
    assert s["thesis_candidate_expression_status"] == {"DEFERRED_RESOURCE": 808, "CONTRACT_FOUND": 244}
    assert s["contract_options_vs_morning_differs"] == 144


def test_four_compression_producers_disagree(d):
    c = p0.compression_agreement(d)
    assert c["all_measured"] == 768 and c["all_measured_and_all_agree"] == 172
    assert c["producers"]["discovery_crabel"]["compressed"] == 339
    assert c["producers"]["engine_1d"]["compressed"] == 439


def test_direction_producers_point_opposite_ways(d):
    a = p0.direction_agreement(d)
    assert a["thesis_vs_legacy_direction"] == {"both_directed": 1006, "same": 398, "opposite": 608}
    assert a["thesis_vs_precor_intent"]["opposite"] == 626


def test_trigger_layer_never_fires_vwap_or_trap(d):
    t = p0.trigger_layer_counts(d)
    assert t["codes_containing"]["VWAP_RECLAIM"] == 0 and t["codes_containing"]["VWAP_LOSS"] == 0
    assert t["codes_containing"]["TRAP"] == 0
    assert t["trigger_primary"]["NONE"] == 814


def test_candidate_level_dispositions(d):
    c = p0.candidate_funnel(d)
    assert c["engine_candidate_records"] == 29009 and c["expression_lane_records"] == 18500
    assert c["expression_status_family"] == {"DEFERRED_RESOURCE": 16500, "CONTRACT_FOUND": 1048,
                                             "NOT_ROUTED": 949, "NO_CONTRACT_FIT": 3}


def test_discovery_recall_losses(d):
    rc = p0.lifecycle(d)["reason_code"]
    assert rc["INTRADAY_ONLY_UNTESTED"] == 1036 and rc["NO_LIVE_SETUP"] == 331
    assert rc["ELIG_INSUFFICIENT_BARS"] == 109 and rc["NO_PRICE_DATA"] == 28
