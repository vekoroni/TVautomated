"""AVS-MACRO-TRIAGE-001 T1: every board build writes its per-ETF intelligence (approved by ACK 20 Nov 2026).

A compact projection of what the board already measures, per sector and industry ETF, for the Lane B triage to
read. Every item states its source (CLAUDE.md rule 6b); relative performance is never called a fund flow; missing
is never neutral; nothing here changes a pipeline rank, contract or side. Business rules, written before the code."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from macro_board import etf_intelligence as ei

CONFIG = {"rotation": {"sectors": ["XLK", "XLP", "XLE"], "industries": ["SMH"]},
          "day_story": {"driver_horizon": "5"},
          "etf_intelligence": {"version": "etf_intelligence_v1", "max_reasons": 2,
                               "output_dir": "macro_board/output/etf_intelligence"}}


def _story(t, flow, *, drivers=(), record=None, side="PUT", footprint_lean="NONE", published=(), live=()):
    trigger = {"name": "sma50", "level": 100.0, "distance_pct": -1.0, "distance_daily_moves": 0.8}
    inval = {"name": "high_252", "level": 110.0, "distance_pct": 5.0, "distance_daily_moves": 3.0}
    trade = ({"ticker": t, "side": "STAND_ASIDE", "trigger": None, "invalidation": None, "record": record,
              "text": f"{t}: no clear edge."} if side == "STAND_ASIDE" else
             {"ticker": t, "side": side, "trigger": trigger, "invalidation": inval, "record": record,
              "expression": {"pricing": "FAIR"}, "balance": {"with": 1, "against": 1}, "text": f"{t} trade text"})
    return {"ticker": t, "name": t + " name", "kind": "sector",
            "flow": {"label": flow, "text": f"{t} relative text", "relative_pp": {"1": -0.1, "5": -2.0, "20": 3.0}},
            "volume": {"ratio": 1.3, "session": "2026-11-19"},
            "footprint": {"status": "OK", "lean": footprint_lean, "text": "options text"},
            "drivers": list(drivers), "published": list(published), "persistence_text": "record text",
            "trade": trade, "live": list(live)}


def _payload(stories, *, lead=("XLP",), avoid=("XLK",), bias=None):
    return {"as_of_session": "2026-11-19", "built_at_utc": "2026-11-19T23:42:49+00:00",
            "build": {"kind": "EVENING"},
            "session_plan": {"next_session": "2026-11-20"},
            "intel": {"packet": {"sector_lead": list(lead), "sector_avoid": list(avoid)}},
            "rotation": {"packet": {"bias": bias if bias is not None else {"XLK": "HEADWIND", "XLP": "TAILWIND", "XLE": "MIXED"}}},
            "decision_points": {"calendar": [{"kind": "RELEASE", "name": "Jobless claims", "date": "2026-11-20",
                                               "time_et": "08:30", "sessions_ahead": 1, "detail": "x"},
                                              {"kind": "RELEASE", "name": "PCE", "date": "2026-11-25", "sessions_ahead": 3}]},
            "external": {"macro_packet": {"as_of": "2026-11-19T23:30:00+00:00"}},
            "day_story": {"status": "OK", "stories": stories}}


DRIVERS = [{"kind": "MACRO", "fit": "CONSISTENT", "text": "Yields rising: worse in this state (t -2.4)."},
           {"kind": "CROSS_ASSET", "asset": "TLT", "fit": "AGAINST", "corr": 0.45, "text": "TLT +1.2%; moves with it."},
           {"kind": "MACRO", "fit": "CONSISTENT", "text": "Curve flat: worse (t -2.1)."},
           {"kind": "MACRO", "fit": "CONSISTENT", "text": "Credit: worse (t -2.0)."}]


def test_every_rotation_etf_is_present_and_a_missing_read_is_missing_not_neutral():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG)
    assert set(out["etfs"]) == {"XLK", "XLP", "XLE", "SMH"}
    assert out["etfs"]["XLP"]["stance_measured"] == "MISSING" and "no board read" in out["etfs"]["XLP"]["missing_reason"]
    assert out["meta"]["build_kind"] == "EVENING" and out["meta"]["as_of_session"] == "2026-11-19"


def test_relative_performance_is_never_called_a_fund_flow():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG)
    text = json.dumps(out).lower()
    assert "fund flow" not in text and "inflow" not in text.replace('"inflow"', "") and "money" not in text
    assert out["etfs"]["XLK"]["relative_performance"]["label"] == "TURNING_OUT"


def test_measured_and_packet_stances_are_kept_apart_labelled_and_compared():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS),
                               _story("XLP", "INFLOW", side="CALL"),
                               _story("XLE", "TURNING_IN", side="CALL")]), CONFIG)
    xlk, xlp, xle = out["etfs"]["XLK"], out["etfs"]["XLP"], out["etfs"]["XLE"]
    assert xlk["stance_measured"] == "AVOID" and xlk["stance_measured_source"] == "MEASURED"
    assert xlk["stance_packet"] == "AVOID" and xlk["stance_packet_source"] == "LLM_PACKET"
    assert xlk["stance_agreement"] == "AGREE" and xlp["stance_agreement"] == "AGREE"
    assert xle["stance_packet"] == "NEUTRAL" and xle["stance_agreement"] == "PARTIAL"
    disagree = ei.project(_payload([_story("XLK", "INFLOW", side="CALL")]), CONFIG)["etfs"]["XLK"]
    assert disagree["stance_agreement"] == "DISAGREE"                       # never averaged


def test_an_etf_the_packet_does_not_cover_is_one_source():
    out = ei.project(_payload([_story("SMH", "OUTFLOW")]), CONFIG)
    assert out["etfs"]["SMH"]["stance_packet"] == "NONE" and out["etfs"]["SMH"]["stance_agreement"] == "ONE_SOURCE"


def test_packet_agreement_is_marked_as_not_independent_confirmation():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG)
    assert "not independent" in out["etfs"]["XLK"]["echo_note"]


def test_reasons_for_and_against_carry_their_source_and_are_capped():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS, record="REVERSES",
                                      published=[{"label": "PUBLISHED", "name": "Chip export rule",
                                                  "source": "event payload (LLM)"}])]), CONFIG)
    x = out["etfs"]["XLK"]
    assert len(x["reasons_for"]) == 2 and len(x["reasons_against"]) == 2
    assert all(r["source"] in ("MEASURED", "LLM_FROM_OUR_SHEET", "LLM_PACKET") for r in x["reasons_for"] + x["reasons_against"])
    assert any("reversed" in r["text"].lower() or "record" in r["text"].lower() for r in x["reasons_against"])
    assert x["published"][0]["source"] == "LLM_FROM_OUR_SHEET"


def test_each_decision_scenario_has_a_trigger_an_invalidation_and_a_horizon():
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG)
    sc = {s["kind"]: s for s in out["etfs"]["XLK"]["decision_scenarios"]}
    assert set(sc) == {"CONTINUATION", "REVERSAL", "ALTERNATIVE", "STAND_ASIDE"}
    assert sc["CONTINUATION"]["trigger"]["level"] == 100.0 and sc["CONTINUATION"]["invalidation"]["level"] == 110.0
    assert sc["REVERSAL"]["trigger"]["level"] == 110.0 and sc["REVERSAL"]["invalidation"]["level"] == 100.0
    assert all(s["horizon_sessions"] == 5 for s in sc.values())
    assert "TLT" in sc["ALTERNATIVE"]["text"]
    assert out["etfs"]["XLK"]["kill_level"]["level"] == 110.0


def test_no_edge_leaves_only_the_stand_aside_scenario_with_its_reason():
    out = ei.project(_payload([_story("XLP", "NONE", side="STAND_ASIDE")]), CONFIG)
    sc = {s["kind"]: s for s in out["etfs"]["XLP"]["decision_scenarios"]}
    assert sc["STAND_ASIDE"]["applies"] is True and sc["CONTINUATION"]["applies"] is False
    assert out["etfs"]["XLP"]["kill_level"] is None


def test_events_before_the_next_close_and_live_scenarios_are_carried():
    live = [{"scenario": "narrow_high", "ticker": "XLK", "side": "PUT", "state": "TRIGGERED",
             "record": {"verdict": "THIN", "survives_fdr": False}}]
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS, live=live)]), CONFIG)
    assert [e["name"] for e in out["events_next_close"]] == ["Jobless claims"]
    assert out["etfs"]["XLK"]["live_scenarios"] == [{"id": "narrow_high", "state": "TRIGGERED", "side": "PUT",
                                                     "verdict": "THIN", "beats_the_tries": False}]


def test_the_file_is_written_atomically_and_as_of_builds_never_replace_latest(tmp_path):
    out = ei.project(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG)
    target = tmp_path / "etf_intelligence"
    ei.write(out, target, as_of=None)
    latest = json.loads((target / "etf_intelligence_latest.json").read_text(encoding="utf-8"))
    assert latest["meta"]["version"] == "etf_intelligence_v1"
    assert (target / "etf_intelligence_2026-11-19_EVENING.json").exists()
    older = json.loads(json.dumps(out)); older["meta"]["as_of_session"] = "2026-10-01"
    ei.write(older, target, as_of="2026-10-01")
    assert json.loads((target / "etf_intelligence_latest.json").read_text(encoding="utf-8"))["meta"]["as_of_session"] == "2026-11-19"
    assert not list(target.glob("*.tmp"))


def test_authority_says_it_never_changes_a_pipeline_decision():
    out = ei.project(_payload([]), CONFIG)
    assert "never" in out["meta"]["authority"].lower() and "rank" in out["meta"]["authority"].lower()


def test_the_board_build_writes_the_file_and_a_failure_is_loud_but_keeps_the_board(tmp_path, capsys):
    from macro_board import build_board as bb
    path = bb.write_etf_intelligence(_payload([_story("XLK", "TURNING_OUT", drivers=DRIVERS)]), CONFIG, tmp_path, as_of=None)
    assert path is not None and (tmp_path / "etf_intelligence" / "etf_intelligence_latest.json").exists()
    assert bb.write_etf_intelligence({}, {"rotation": {}}, tmp_path, as_of=None) is None
    assert "ETF INTELLIGENCE NOT WRITTEN" in capsys.readouterr().out


def test_the_live_board_config_carries_the_section():
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "macro_board_config_v1.json").read_text(encoding="utf-8"))
    assert cfg["etf_intelligence"]["version"] == "etf_intelligence_v1" and int(cfg["etf_intelligence"]["max_reasons"]) >= 1
