"""BEH-001 phase 2A: the candidate packet (C-02, C-03 handoff, C-07).

Business rules:
- Every live directed candidate of every ticker read appears exactly once,
  whatever Discovery decided about the ticker (Discovery's outcome is an attribute).
- Monitoring observations travel separately; failed candidates keep their successor link.
- Vanguard is a per-ticker fact: its fields join each candidate by ticker without
  duplicating Vanguard; a ticker Vanguard did not run says so, with the reason.
- Candidates are ranked by behaviour and time only: ACTIVATED first, then DETECTED by
  shortest median remaining time to activation, then Candidate_ID.
- Publishing is immutable and never fails the Evening.
"""
import json

import pandas as pd

from contracts.behavioural_candidate_packet import load_or_publish_candidate_packet, publish_candidate_packet_safely
from domain.structure_behaviour.handoff_packet import build_candidate_packet

POLICY = json.loads(open("config/beh001_handoff_v1.json", encoding="utf-8").read())


def cand(ticker, kind, state, direction="BULL", q50=None, outcome="SURVIVE", parent=None, label="2026-09-01"):
    return {"Candidate_ID": f"{ticker}|1d|CAMPAIGN|{kind}|{label}", "Ticker": ticker, "Timeframe": "1d",
            "Signal_Type": kind, "Signal_State": state, "Direction": direction,
            "Duration_Remaining_Q50_Bars": q50, "Discovery_Outcome": outcome, "Parent_Candidate_ID": parent}


CANDIDATES = [
    cand("AAA", "Spring Candidate", "DETECTED", q50=9),
    cand("AAA", "Upthrust Candidate", "ACTIVATED", direction="BEAR"),
    cand("BBB", "Spring Candidate", "DETECTED", q50=2, outcome="DROP"),
    cand("BBB", "Mature Trend Exhaustion", "MONITOR", direction=None),
    cand("CCC", "Spring Candidate", "FAILED"),
    cand("CCC", "Failed Spring Continuation", "DETECTED", direction="BEAR", q50=None,
         parent="CCC|1d|CAMPAIGN|Spring Candidate|2026-09-01"),
]
PASS = [{"ticker": "AAA", "verdict": "PASS", "final_recommendation": "WATCH", "layer2__edge_quality": "WEAK"}]
REJECT = [{"ticker": "CCC", "reason_code": "DATA_FAILURE_NO_OHLCV"}]


def packet():
    return build_candidate_packet("R1", CANDIDATES, PASS, REJECT, POLICY)


def test_every_live_directed_candidate_appears_once_whatever_discovery_decided():
    p = packet()
    ids = [r["Candidate_ID"] for r in p["records"]]
    assert len(ids) == len(set(ids)) == 4
    dropped = [r for r in p["records"] if r["Ticker"] == "BBB"][0]
    assert dropped["Discovery_Outcome"] == "DROP"


def test_monitoring_and_failed_travel_separately():
    p = packet()
    assert [m["Signal_Type"] for m in p["monitoring"]] == ["Mature Trend Exhaustion"]
    assert [f["Ticker"] for f in p["failed"]] == ["CCC"]
    successor = [r for r in p["records"] if r["Ticker"] == "CCC"][0]
    assert successor["Parent_Candidate_ID"] == p["failed"][0]["Candidate_ID"]


def test_vanguard_joins_by_ticker_and_absence_is_stated():
    p = packet()
    by = {r["Candidate_ID"]: r for r in p["records"]}
    aaa = [r for r in p["records"] if r["Ticker"] == "AAA"]
    assert all(r["vanguard__status"] == "PASS" and r["vanguard__layer2__edge_quality"] == "WEAK" for r in aaa)
    assert "edge_direction_status" in aaa[0]["vanguard__fields_missing"]
    assert [r for r in p["records"] if r["Ticker"] == "CCC"][0]["vanguard__status"] == "REJECT:DATA_FAILURE_NO_OHLCV"
    assert [r for r in p["records"] if r["Ticker"] == "BBB"][0]["vanguard__status"] == "VANGUARD_NOT_RUN"
    assert p["counts"]["vanguard_rows_joined"] == 1


def test_ranking_uses_behaviour_and_time_only():
    order = [r["Candidate_ID"].split("|")[0] + ":" + r["Signal_State"] for r in packet()["records"]]
    assert order == ["AAA:ACTIVATED", "BBB:DETECTED", "AAA:DETECTED", "CCC:DETECTED"]
    assert [r["Handoff_Rank"] for r in packet()["records"]] == [1, 2, 3, 4]


def test_publication_is_immutable_and_never_fails_the_evening(tmp_path):
    run = tmp_path / "R1"
    (run / "discovery").mkdir(parents=True)
    (run / "vanguard").mkdir()
    pd.DataFrame(CANDIDATES).to_csv(run / "discovery" / "behavioural_candidates_R1.csv", index=False)
    pd.DataFrame(PASS).to_csv(run / "vanguard" / "vanguard_signals.csv", index=False)
    pd.DataFrame(REJECT).to_csv(run / "vanguard" / "vanguard_rejects.csv", index=False)
    first = load_or_publish_candidate_packet(run)
    again = load_or_publish_candidate_packet(run)
    assert first == again and first["counts"]["records"] == 4
    missing = tmp_path / "R2"
    missing.mkdir()
    status = publish_candidate_packet_safely(missing)
    assert status.startswith("CANDIDATE_PACKET_UNAVAILABLE:")


def test_status_is_recorded_for_the_run_manifest(tmp_path):
    run = tmp_path / "R3"
    run.mkdir()
    publish_candidate_packet_safely(run)
    status = json.loads((run / "forecast" / "behavioural_candidate_packet_v1" / "status.json").read_text())
    assert status["status"].startswith("CANDIDATE_PACKET_UNAVAILABLE:")


def test_evening_wiring_never_aborts_on_the_packet():
    from pathlib import Path
    source = Path("intelligent_orchestrator.py").read_text(encoding="utf-8")
    block = source[source.index("BEH-001 phase 2A"):source.index("PHASE 8a: Options Intelligence")]
    assert "publish_candidate_packet_safely" in block and "return False" not in block
