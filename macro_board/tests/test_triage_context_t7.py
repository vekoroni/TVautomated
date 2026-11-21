"""AVS-MACRO-TRIAGE-001 T7 in the per-name file (design approved by ACK 20 Nov 2026).

A hand-off name that is its own sector ETF (SPY, TLT, GLD, ...) reads its own board entry with link SELF instead of
a correlation of 1.0 with itself. Each row carries the peer reference and its label, whether the market and peer
references split, the event file's view of the ETF and the US Money Index routing, each labelled. The JSON carries the
market-wide event and Money Index blocks for the merge. The Lab rank, side and contract stay unchanged.
Business rules, written before the code."""

from __future__ import annotations

import json

import pandas as pd

from macro_board import triage_context as tc

CFG = {"min_link_corr": 0.4, "corr_window_sessions": 60}


def _etf(stance, packet, label, *, coverage="UNIVERSE_READ", peer="AGG", peer_label="INFLOW", split="SPLIT",
         event_view="NOT_NAMED", routing="NOT_NAMED"):
    return {"coverage": coverage, "stance_measured": stance, "stance_measured_source": "MEASURED",
            "stance_packet": packet, "stance_packet_source": "LLM_PACKET", "stance_agreement": "DISAGREE",
            "relative_performance": {"label": label, "text": f"rel {label} vs SPY", "relative_pp": {"5": 1.0}},
            "volume_ratio": None, "record": None, "reasons_for": [], "reasons_against": [], "echo_note": "",
            "live_scenarios": [], "decision_scenarios": [{"kind": "STAND_ASIDE", "applies": True}],
            "kill_level": None, "missing_reason": None,
            "benchmarks": {"market": {"reference": "SPY", "label": label},
                           "peer": {"reference": peer, "label": peer_label}, "split": split},
            "event_sector_view": event_view, "event_etf_case": None, "usmi_routing": routing}


INTEL = {"meta": {"version": "etf_intelligence_v1", "as_of_session": "2026-11-19", "build_kind": "EVENING",
                  "built_at_utc": "2026-11-19T23:42:49+00:00", "next_session": "2026-11-20"},
         "events_next_close": [],
         "event_intelligence": {"status": "OK", "source": "LLM_WITH_NEWS", "as_of": "2026-11-19T23:35:00+00:00",
                                "events": [{"name": "CPI", "invalidation": "yields rise"}]},
         "usmi_intelligence": {"status": "OK", "source": "LLM_WITH_NEWS", "as_of": "2026-11-18T18:57:43+00:00",
                               "score": "MISSING", "counterevidence": ["x"]},
         "etfs": {"TLT": _etf("LEAN_IN", "AVOID", "TURNING_IN"),
                  "XLK": _etf("AVOID", "AVOID", "OUTFLOW", coverage="DAY_STORY", peer="RSP", peer_label="OUTFLOW",
                              split="SAME", event_view=[{"view": "ADVERSE", "condition": "if yields rise",
                                                         "source": "LLM_WITH_NEWS"}],
                              routing=[{"sector": "technology", "routing": "WATCH_ONLY", "source": "LLM_WITH_NEWS"}]),
                  "VXX": dict(_etf("MISSING", "NONE", "MISSING", coverage="NO_READ"),
                              missing_reason="volatility product: no relative-performance read", relative_performance=None)}}

HANDOFF = pd.DataFrame([
    (1, 1, "L1", "TLT", "TLT", "CALL", "TLT261218C00090000", 4),
    (2, 1, "L2", "AAPL", "XLK", "PUT", "AAPL261218P00200000", 9),
    (3, 2, "L3", "VXX", "VXX", "CALL", "VXX261218C00050000", 30),
], columns=["lb_order", "lb_batch", "lb_ledger_id", "ticker", "sector_etf", "direction", "contract_symbol", "lab_rank"])
LINKS = {"TLT": {"corr": 1.0, "beta": 1.0, "n": 60}, "AAPL": {"corr": 0.7, "beta": 1.1, "n": 60},
         "VXX": {"corr": 1.0, "beta": 1.0, "n": 60}}


def _rows():
    return {r["ticker"]: r for r in tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-20")}


def test_a_name_that_is_its_own_sector_etf_reads_its_own_entry_with_link_self():
    tlt = _rows()["TLT"]
    assert tlt["link_state"] == "SELF" and tlt["link_corr_60d"] is None and tlt["link_beta_60d"] is None
    assert tlt["side_fit_measured"] == "WITH_FLOW"  # a call on TLT while TLT outperforms SPY
    assert tlt["side_fit_packet"] == "AGAINST" and tlt["money_tag"] == "MIXED"
    assert "self" in tlt["money_why"].lower()


def test_a_self_etf_without_a_board_read_says_why():
    vxx = _rows()["VXX"]
    assert vxx["link_state"] == "SELF" and vxx["side_fit_measured"] == "NO_BOARD_READ"
    assert "volatility product" in vxx["sector_check"]


def test_each_row_carries_the_peer_reference_its_label_and_the_split():
    tlt, aapl = _rows()["TLT"], _rows()["AAPL"]
    assert tlt["peer_reference"] == "AGG" and tlt["peer_relative_label"] == "INFLOW" and tlt["benchmark_split"] == "SPLIT"
    assert aapl["peer_reference"] == "RSP" and aapl["benchmark_split"] == "SAME"


def test_each_row_carries_the_event_view_and_the_money_index_routing_with_their_source():
    tlt, aapl = _rows()["TLT"], _rows()["AAPL"]
    assert aapl["event_sector_view"] == "ADVERSE (if yields rise) [LLM_WITH_NEWS]"
    assert aapl["usmi_routing"] == "technology: WATCH_ONLY [LLM_WITH_NEWS]"
    assert tlt["event_sector_view"] == "NOT_NAMED" and tlt["usmi_routing"] == "NOT_NAMED"


def test_the_lab_fields_are_copied_unchanged():
    tlt = _rows()["TLT"]
    assert (tlt["lab_rank"], tlt["side"], tlt["contract_symbol"]) == (4, "CALL", "TLT261218C00090000")


def test_the_new_columns_are_in_the_file_and_the_json_carries_the_market_wide_blocks(tmp_path):
    folder = tmp_path / "lab_2026-11-20"
    folder.mkdir()
    HANDOFF.to_csv(folder / "handoff.csv", index=False)
    (folder / "receipt.json").write_text(json.dumps({"session": "2026-11-20"}), encoding="utf-8")
    intel_path = tmp_path / "etf_intelligence_latest.json"
    intel_path.write_text(json.dumps(INTEL), encoding="utf-8")
    out = tc.run(folder, intel_path, CFG, link_reader=lambda pairs, end: LINKS)
    frame = pd.read_csv(out["csv"])
    for col in ("peer_reference", "peer_relative_label", "benchmark_split", "event_sector_view", "usmi_routing"):
        assert col in frame.columns, col
    meta = json.loads(out["json"].read_text(encoding="utf-8"))
    assert meta["event_intelligence"]["events"][0]["invalidation"] == "yields rise"
    assert meta["usmi_intelligence"]["score"] == "MISSING"
    assert meta["counts"]["link_state"]["SELF"] == 2


def test_an_older_intelligence_file_without_t7_fields_gives_missing_not_blank():
    old = json.loads(json.dumps(INTEL))
    for e in old["etfs"].values():
        for k in ("benchmarks", "event_sector_view", "event_etf_case", "usmi_routing"):
            e.pop(k)
    old.pop("event_intelligence")
    old.pop("usmi_intelligence")
    aapl = {r["ticker"]: r for r in tc.build_rows(HANDOFF, old, LINKS, CFG, session="2026-11-20")}["AAPL"]
    assert aapl["peer_reference"] == "MISSING" and aapl["benchmark_split"] == "MISSING"
    assert aapl["event_sector_view"] == "MISSING" and aapl["usmi_routing"] == "MISSING"
