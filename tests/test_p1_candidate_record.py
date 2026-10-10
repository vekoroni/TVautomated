"""Phase 1: the CandidateRecord contract (design §9).

Business rules:
- Every engine candidate becomes a CandidateRecord carrying ITS OWN levels, a family label, the proposed side,
  and contributor fields with an explicit status (MEASURED / NOT_MEASURED + reason) - never a neutral default.
- Every known engine signal type has a family; an unknown type is labelled UNCLASSIFIED, never guessed.
- A compression candidate is linked to its compression episode (episode start of its timeframe).
- Level geometry is checked against the price without changing the levels: COMPLETE / WRONG_SIDE / INCOMPLETE /
  NOT_DIRECTED. A label, not a gate.
"""
from contracts.candidate_record import (CANDIDATE_RECORD_VERSION, FAMILY_BY_SIGNAL_TYPE, enrich_candidate,
                                        family_of)
import avshunter_discovery_ULTIMATE as disc

KNOWN_TYPES = ["Crabel Compression Breakout", "SOW -> LPSY continuation", "SOS -> LPS continuation",
               "Trend Continuation after Shallow Test", "Hinge / Apex Expansion", "Seller Absorption Breakdown",
               "Upthrust Candidate", "Failed Spring Continuation", "Buyer Absorption Breakout", "Spring Candidate",
               "Failed Upthrust Continuation", "Mature Trend Exhaustion", "Change-of-Behaviour Reversal",
               "UTAD Test"]
BULL = {"Candidate_ID": "X|1d|CAMPAIGN|SOS -> LPS continuation|2026-09-01", "Timeframe": "1d",
        "Signal_Type": "SOS -> LPS continuation", "Signal_State": "DETECTED", "Direction": "BULL",
        "Trigger_Level": 104.0, "Invalidation_Level": 95.0, "Outcome_Level": 115.0}


def test_every_engine_signal_type_has_a_family():
    assert all(family_of(t) != "UNCLASSIFIED" for t in KNOWN_TYPES)
    assert set(KNOWN_TYPES) <= set(FAMILY_BY_SIGNAL_TYPE)
    assert family_of("Something New") == "UNCLASSIFIED"


def test_record_keeps_its_own_levels_and_adds_contract_fields():
    r = enrich_candidate(dict(BULL), close=100.0, atr_daily=2.0, readings={})
    assert (r["Trigger_Level"], r["Invalidation_Level"], r["Outcome_Level"]) == (104.0, 95.0, 115.0)
    assert r["Record_Version"] == CANDIDATE_RECORD_VERSION
    assert r["Family"] == "CONTINUATION" and r["Proposed_Side"] == "BULL"
    assert r["Distance_To_Trigger_ATR"] == 2.0 and r["Distance_To_Trigger_ATR_Status"] == "MEASURED"
    assert r["Levels_Status"] == "COMPLETE"


def test_missing_atr_is_not_measured_not_zero():
    r = enrich_candidate(dict(BULL), close=100.0, atr_daily=None, readings={})
    assert r["Distance_To_Trigger_ATR"] is None
    assert r["Distance_To_Trigger_ATR_Status"].startswith("NOT_MEASURED")


def test_wrong_side_levels_are_labelled_not_changed():
    bad = dict(BULL, Outcome_Level=98.0)
    r = enrich_candidate(bad, close=100.0, atr_daily=2.0, readings={})
    assert r["Levels_Status"] == "WRONG_SIDE" and r["Outcome_Level"] == 98.0


def test_undirected_candidate_is_labelled():
    r = enrich_candidate(dict(BULL, Direction=None), close=100.0, atr_daily=2.0, readings={})
    assert r["Levels_Status"] == "NOT_DIRECTED" and r["Proposed_Side"] is None


def test_compression_candidate_links_to_its_episode():
    c = dict(BULL, Signal_Type="Crabel Compression Breakout")
    r = enrich_candidate(c, close=100.0, atr_daily=2.0,
                         readings={"1d": {"Compression_Episode_Start": "2026-09-20"}})
    assert r["Family"] == "COMPRESSION" and r["Compression_Episode_Start"] == "2026-09-20"


def test_discovery_enriches_every_engine_candidate():
    beh = {"candidates": [dict(BULL), dict(BULL, Candidate_ID="Y", Direction=None)], "readings": {}}
    disc._enrich_candidate_records(beh, close=100.0, atr_daily=2.0)
    assert all(c["Record_Version"] == CANDIDATE_RECORD_VERSION for c in beh["candidates"])
