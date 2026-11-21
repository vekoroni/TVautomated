"""AVS-MACRO-TRIAGE-001 T2: one board macro row per Lane B hand-off name (approved by ACK 20 Nov 2026).

The join reads the hand-off and the board's latest per-ETF intelligence and writes triage_macro_context_<session>
into the hand-off folder, keyed by ledger id. The Lab rank, side and contract are copied, never changed; the view
order is display only. money_tag: measured and packet agree -> that word; they disagree -> MIXED (ACK decision 1);
one missing -> the other, with a note; a stock-specific name -> MIXED with a note. Missing is never neutral.
Business rules, written before the code."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from macro_board import triage_context as tc

CFG = {"min_link_corr": 0.4, "corr_window_sessions": 60}


def _etf(stance, packet, *, label=None, kill=None, live=(), agreement="AGREE"):
    label = label or {"LEAN_IN": "INFLOW", "AVOID": "OUTFLOW", "NEUTRAL": "NONE"}.get(stance, "MISSING")
    return {"stance_measured": stance, "stance_measured_source": "MEASURED", "stance_packet": packet,
            "stance_packet_source": "LLM_PACKET", "stance_agreement": agreement,
            "relative_performance": {"label": label, "text": f"rel text {label}", "relative_pp": {"5": 1.0}},
            "volume_ratio": 1.2, "record": "NO_CLEAR_RECORD",
            "reasons_for": [{"source": "MEASURED", "text": "for one"}],
            "reasons_against": [{"source": "LLM_PACKET", "text": "against one"}],
            "echo_note": "not independent confirmation", "live_scenarios": list(live),
            "decision_scenarios": [{"kind": "CONTINUATION", "applies": True}, {"kind": "REVERSAL", "applies": True},
                                   {"kind": "ALTERNATIVE", "applies": False}, {"kind": "STAND_ASIDE", "applies": False}],
            "kill_level": kill, "missing_reason": None if stance != "MISSING" else "no board read"}


INTEL = {"meta": {"version": "etf_intelligence_v1", "as_of_session": "2026-11-19", "build_kind": "EVENING",
                  "built_at_utc": "2026-11-19T23:42:49+00:00", "next_session": "2026-11-20"},
         "events_next_close": [{"name": "Jobless claims", "time_et": "08:30", "kind": "RELEASE"}],
         "etfs": {"XLK": _etf("AVOID", "AVOID", kill={"name": "sma50", "level": 205.3},
                              live=[{"id": "narrow_high", "state": "TRIGGERED", "side": "PUT", "verdict": "THIN",
                                     "beats_the_tries": False}]),
                  "XLY": _etf("LEAN_IN", "AVOID", agreement="DISAGREE", kill={"name": "sma50", "level": 114.17}),
                  "XLF": _etf("LEAN_IN", "NONE", agreement="ONE_SOURCE", kill={"name": "sma20", "level": 54.0}),
                  "XLE": _etf("NEUTRAL", "AVOID", agreement="PARTIAL"),
                  "XLV": _etf("MISSING", "LEAN_IN", agreement="MISSING")}}

HANDOFF = pd.DataFrame([
    # lb_order, batch, ledger, ticker, sector_etf, direction, contract, lab_rank
    (1, 1, "L1", "AAPL", "XLK", "PUT", "AAPL261218P00200000", 40),
    (2, 1, "L2", "MSFT", "XLK", "CALL", "MSFT261218C00500000", 5),
    (3, 1, "L3", "AMZN", "XLY", "CALL", "AMZN261218C00200000", 12),
    (4, 2, "L4", "JPM", "XLF", "CALL", "JPM261218C00300000", 900),
    (5, 2, "L5", "XOM", "XLE", "PUT", "XOM261218P00100000", 7),
    (6, 2, "L6", "OKLO", "XLK", "PUT", "OKLO261218P00050000", 3),
    (7, 3, "L7", "ZZZ", None, "CALL", "ZZZ261218C00010000", 1),
    (8, 3, "L8", "UNH", "XLV", "CALL", "UNH261218C00300000", 2),
    (9, 3, "L9", "NVDA", "XLK", "UNRESOLVED", None, 8),
], columns=["lb_order", "lb_batch", "lb_ledger_id", "ticker", "sector_etf", "direction", "contract_symbol", "lab_rank"])

LINKS = {"AAPL": {"corr": 0.7, "beta": 1.1, "n": 60}, "MSFT": {"corr": 0.8, "beta": 1.0, "n": 60},
         "AMZN": {"corr": 0.75, "beta": 1.2, "n": 60}, "JPM": {"corr": 0.85, "beta": 1.0, "n": 60},
         "XOM": {"corr": 0.9, "beta": 1.0, "n": 60}, "OKLO": {"corr": 0.1, "beta": 0.3, "n": 60},
         "UNH": {"corr": 0.6, "beta": 0.9, "n": 60}, "NVDA": {"corr": 0.7, "beta": 1.5, "n": 60}}


def _rows():
    return {r["ledger_id"]: r for r in tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-20")}


def test_one_row_per_hand_off_row_keyed_by_ledger_id_with_lab_fields_copied_unchanged():
    rows = tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-20")
    assert [r["ledger_id"] for r in rows] == list(HANDOFF["lb_ledger_id"])
    for r, (_, h) in zip(rows, HANDOFF.iterrows()):
        assert (r["ticker"], r["side"], r["lab_rank"], r["lb_batch"], r["lb_order"], r["contract_symbol"]) == \
               (h["ticker"], h["direction"], h["lab_rank"], h["lb_batch"], h["lb_order"], h["contract_symbol"])


@pytest.mark.parametrize("ledger,tag", [
    ("L1", "WITH"),          # measured AVOID + packet AVOID, a put: both with
    ("L2", "AGAINST"),       # same ETF, a call: both against
    ("L3", "MIXED"),         # measured with the call, packet against: disagreement is MIXED, never averaged
    ("L4", "WITH"),          # packet silent: the measured word, with a note
    ("L5", "MIXED"),         # measured no edge, packet with: not agreement
    ("L8", "WITH"),          # measured missing: the packet word, with a note
])
def test_money_tag_follows_the_agreement_table(ledger, tag):
    assert _rows()[ledger]["money_tag"] == tag


def test_one_source_and_missing_cases_say_which_source_is_missing():
    rows = _rows()
    assert "packet silent" in rows["L4"]["money_why"] and "measured read missing" in rows["L8"]["money_why"]


def test_a_stock_specific_name_is_mixed_with_a_note():
    r = _rows()["L6"]
    assert r["link_state"] == "WEAK" and r["side_fit_measured"] == "STOCK_SPECIFIC"
    assert r["money_tag"] == "MIXED" and "stock-specific" in r["money_why"]


def test_a_missing_sector_etf_is_no_sector_and_an_unresolved_side_is_no_side():
    rows = _rows()
    assert rows["L7"]["sector_etf"] == "MISSING" and rows["L7"]["side_fit_measured"] == "NO_SECTOR"
    assert rows["L7"]["money_tag"] == "NO_READ"
    assert rows["L9"]["side_fit_measured"] == "NO_SIDE" and rows["L9"]["money_tag"] == "NO_SIDE"


def test_a_missing_link_is_missing_not_stock_specific():
    links = dict(LINKS, AAPL={"corr": None, "beta": None, "n": 3})
    r = {x["ledger_id"]: x for x in tc.build_rows(HANDOFF, INTEL, links, CFG, session="2026-11-20")}["L1"]
    assert r["link_state"] == "MISSING" and r["side_fit_measured"] == "LINK_MISSING"


def test_macro_columns_cite_their_sources_and_the_build():
    r = _rows()["L1"]
    assert r["macro_sector_agreement"].startswith("AGREE") and "LLM" in r["macro_sector_agreement"]
    assert "narrow_high TRIGGERED" in r["macro_scenario_ids"] and "CONTINUATION" in r["macro_scenario_ids"]
    assert "205.30" in r["macro_kill_switch"] and "above" in r["macro_kill_switch"] and "EVENING" in r["macro_kill_switch"]
    assert "[MEASURED] for one" in r["reasons_for"] and "[LLM_PACKET] against one" in r["reasons_against"]
    assert r["board_build_kind"] == "EVENING" and r["board_built_at_utc"].startswith("2026-11-19T23:42")
    assert "Jobless claims" in r["events_next_close"]
    text = json.dumps(list(_rows().values())).lower()
    assert "fund flow" not in text and "money is" not in text


def test_the_view_order_is_display_only_and_never_alters_lab_rank():
    rows = tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-20")
    assert sorted(r["macro_view_order"] for r in rows) == list(range(1, len(rows) + 1))
    by_order = sorted(rows, key=lambda r: r["macro_view_order"])
    assert [r["ledger_id"] for r in by_order[:3]] == ["L8", "L1", "L4"]   # WITH first, then by lab_rank
    assert [r["lab_rank"] for r in rows] == list(HANDOFF["lab_rank"])


def test_a_board_built_for_another_session_is_flagged_on_every_row():
    rows = tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-21")
    assert all(r["board_session_note"].startswith("OLDER_BUILD") for r in rows)
    assert all(r["board_session_note"] == "MATCH" for r in _rows().values())


def _folder(tmp_path):
    folder = tmp_path / "lab_2026-11-20"
    folder.mkdir()
    HANDOFF.to_csv(folder / "handoff.csv", index=False)
    (folder / "receipt.json").write_text(json.dumps({"session": "2026-11-20", "built_at_utc": "2026-11-20T10:43:00Z"}),
                                         encoding="utf-8")
    intel = tmp_path / "etf_intelligence_latest.json"
    intel.write_text(json.dumps(INTEL), encoding="utf-8")
    return folder, intel


def test_run_writes_csv_and_json_with_the_build_and_refresh_overwrites_atomically(tmp_path):
    folder, intel = _folder(tmp_path)
    out = tc.run(folder, intel, CFG, link_reader=lambda pairs, end: LINKS)
    frame = pd.read_csv(out["csv"])
    assert len(frame) == len(HANDOFF) and frame["ledger_id"].is_unique
    meta = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
    assert meta["board"]["build_kind"] == "EVENING" and meta["rows"] == len(HANDOFF)
    assert meta["counts"]["money_tag"]["WITH"] == 3 and "authority" in meta
    tc.run(folder, intel, CFG, link_reader=lambda pairs, end: LINKS)
    assert not list(folder.glob("*.tmp")) and Path(out["csv"]).name == "triage_macro_context_2026-11-20.csv"


def test_a_missing_board_file_stops_with_a_clear_message_and_writes_nothing(tmp_path):
    folder, _ = _folder(tmp_path)
    with pytest.raises(tc.ContextError, match="board intelligence file not found"):
        tc.run(folder, tmp_path / "nope.json", CFG, link_reader=lambda *a: LINKS)
    assert not list(folder.glob("triage_macro_context_*"))


def test_a_missing_hand_off_stops_with_a_clear_message(tmp_path):
    _, intel = _folder(tmp_path)
    with pytest.raises(tc.ContextError, match="handoff.csv not found"):
        tc.run(tmp_path / "lab_missing", intel, CFG, link_reader=lambda *a: LINKS)


def test_a_board_built_after_the_hand_off_session_is_called_newer_not_older():
    rows = tc.build_rows(HANDOFF, INTEL, LINKS, CFG, session="2026-11-19")
    assert all(r["board_session_note"].startswith("NEWER_BUILD") for r in rows)


def test_mixed_rows_never_claim_the_two_sources_agree_when_neither_leans():
    intel = json.loads(json.dumps(INTEL))
    intel["etfs"]["XLK"]["stance_packet"] = "NEUTRAL"
    rows = {r["ledger_id"]: r for r in tc.build_rows(HANDOFF, intel, LINKS, CFG, session="2026-11-20")}
    assert rows["L6"]["money_tag"] == "MIXED" and "agree" not in rows["L6"]["money_why"]       # stock-specific
    assert rows["L1"]["money_tag"] == "MIXED" and "agree" not in rows["L1"]["money_why"]       # packet neutral
    assert "neither" not in rows["L5"]["money_why"] and "no clear edge" in rows["L5"]["money_why"]
    assert "1.20x" in rows["L1"]["sector_check"]


# --- T3: refresh after each board build ---------------------------------------------------------------------------

def test_a_refresh_counts_the_names_whose_money_tag_changed_since_the_previous_file(tmp_path):
    folder, intel = _folder(tmp_path)
    first = tc.run(folder, intel, CFG, link_reader=lambda pairs, end: LINKS)
    assert first["meta"]["changed_money_tag"] is None                     # nothing to compare with
    moved = json.loads(json.dumps(INTEL))
    moved["meta"]["built_at_utc"] = "2026-11-20T12:05:00+00:00"
    moved["etfs"]["XLK"]["stance_measured"], moved["etfs"]["XLK"]["relative_performance"]["label"] = "LEAN_IN", "INFLOW"
    intel.write_text(json.dumps(moved), encoding="utf-8")
    second = tc.run(folder, intel, CFG, link_reader=lambda pairs, end: LINKS)
    # AAPL put WITH -> MIXED, MSFT call AGAINST -> MIXED; OKLO stays stock-specific; NVDA stays NO_SIDE
    assert second["meta"]["changed_money_tag"] == 2
    assert second["meta"]["previous_board_built_at_utc"] == "2026-11-19T23:42:49+00:00"


def test_the_next_session_refresh_uses_the_boards_next_session_and_skips_when_no_hand_off_exists(tmp_path):
    root = tmp_path / "handoff"
    root.mkdir()
    folder, intel = _folder(tmp_path)
    out = tc.refresh_next_session(root, intel, CFG, link_reader=lambda pairs, end: LINKS)
    assert out["skipped"] and "2026-11-20" in out["skipped"]
    folder.rename(root / "lab_2026-11-20")
    out = tc.refresh_next_session(root, intel, CFG, link_reader=lambda pairs, end: LINKS)
    assert Path(out["csv"]).parent.name == "lab_2026-11-20" and out["meta"]["board_session_note"] == "MATCH"


def test_the_runner_wrapper_script_calls_the_next_session_refresh():
    text = (Path(__file__).resolve().parents[2] / "scripts" / "refresh_triage_macro_context.py").read_text(encoding="utf-8")
    assert "--next-session" in text and "triage_context" in text


# --- T6: the board's Day story shows the triaged names -------------------------------------------------------------

IMPACT_CFG = dict(CFG, max_batches=2)


def _impact_root(tmp_path, *, triage=True, cards=()):
    root = tmp_path / "handoff"
    folder = root / "lab_2026-11-20"
    folder.mkdir(parents=True)
    HANDOFF.to_csv(folder / "handoff.csv", index=False)
    (folder / "receipt.json").write_text(json.dumps({"session": "2026-11-20"}), encoding="utf-8")
    if triage:
        pd.DataFrame([{"deep_mine_rank": "2", "ticker": "MSFT", "ledger_id": "L2"},
                      {"deep_mine_rank": "1 (lead)", "ticker": "AAPL", "ledger_id": "L1"}]).to_csv(
            folder / "batch1_triage_2026-11-20.csv", index=False)
        pd.DataFrame([{"deep_mine_rank": "31", "ticker": "XOM", "ledger_id": "L5"}]).to_csv(
            folder / "batch2_triage_2026-11-20.csv", index=False)
    for name in cards:
        (folder / name).write_text("<html></html>", encoding="utf-8")
    return root


def test_the_day_story_lists_the_triaged_names_by_batch_with_this_builds_macro_reading(tmp_path):
    root = _impact_root(tmp_path, cards=("AAPL_deep_dive_2026-11-20_v1.html", "AAPL_deep_dive_2026-11-20.html"))
    out = tc.board_ticker_impact(INTEL, root, IMPACT_CFG, link_reader=lambda pairs, end: LINKS,
                                 board_dir=tmp_path / "macro_board" / "output")
    assert out["status"] == "TRIAGE" and out["session"] == "2026-11-20"
    assert [(r["batch"], r["ticker"]) for r in out["rows"]] == [(1, "AAPL"), (1, "MSFT"), (2, "XOM")]
    aapl = out["rows"][0]
    assert aapl["money_tag"] == "WITH" and aapl["deep_mine_rank"] == "1 (lead)" and aapl["sector_etf"] == "XLK"
    assert aapl["card"].endswith("handoff/lab_2026-11-20/AAPL_deep_dive_2026-11-20.html") and not aapl["card"].startswith("/")
    assert out["rows"][1]["card"] is None
    assert out["counts"]["money_tag"] == {"WITH": 1, "AGAINST": 1, "MIXED": 1}
    assert out["board_built_at_utc"] == INTEL["meta"]["built_at_utc"]


def test_before_the_triage_runs_the_first_hand_off_batches_are_shown_labelled_not_triaged(tmp_path):
    out = tc.board_ticker_impact(INTEL, _impact_root(tmp_path, triage=False), IMPACT_CFG,
                                 link_reader=lambda pairs, end: LINKS, board_dir=tmp_path)
    assert out["status"] == "HANDOFF_NOT_TRIAGED"
    assert {r["batch"] for r in out["rows"]} == {1, 2} and len(out["rows"]) == 6


def test_without_a_hand_off_for_the_next_session_the_board_keeps_the_pipeline_candidates(tmp_path):
    root = tmp_path / "handoff"
    root.mkdir()
    out = tc.board_ticker_impact(INTEL, root, IMPACT_CFG, link_reader=lambda pairs, end: LINKS, board_dir=tmp_path)
    assert out["status"] == "NO_HANDOFF" and "2026-11-20" in out["note"] and out["rows"] == []


def test_a_failure_is_reported_not_raised(tmp_path):
    def broken(pairs, end):
        raise OSError("store locked")
    out = tc.board_ticker_impact(INTEL, _impact_root(tmp_path), IMPACT_CFG, link_reader=broken, board_dir=tmp_path)
    assert out["status"] == "FAILED" and "store locked" in out["note"] and out["rows"] == []


def _board_config():
    return {"rotation": {"sectors": ["XLK", "XLY", "XLF", "XLE", "XLV"], "industries": []},
            "day_story": {"driver_horizon": "5", "triage_impact": {"max_batches": 4, "handoff_root": "x"}},
            "etf_intelligence": {"version": "etf_intelligence_v1", "max_reasons": 2},
            "session_plan": {"min_link_corr": 0.4}, "money_index": {"corr_window_sessions": 60}}


def test_the_board_build_attaches_the_triage_impact_to_the_day_story_and_skips_as_of_builds(tmp_path):
    from macro_board import build_board as bb
    payload = {"as_of_session": "2026-11-19", "built_at_utc": "x", "build": {"kind": "EVENING"},
               "session_plan": {"next_session": "2026-11-20"}, "day_story": {"status": "OK", "stories": []}}
    root = _impact_root(tmp_path)
    bb.attach_triage_impact(payload, _board_config(), price_db=tmp_path / "none.sqlite", output_dir=tmp_path, as_of=None,
                            handoff_root=root, link_reader=lambda pairs, end: LINKS)
    assert payload["day_story"]["triage_impact"]["status"] == "TRIAGE"
    bb.attach_triage_impact(payload, _board_config(), price_db=tmp_path / "none.sqlite", output_dir=tmp_path,
                            as_of="2026-10-01", handoff_root=root, link_reader=lambda pairs, end: LINKS)
    assert payload["day_story"]["triage_impact"]["status"] == "AS_OF_BUILD"


def test_the_live_board_config_carries_the_triage_impact_settings():
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "macro_board_config_v1.json").read_text(encoding="utf-8"))
    t = cfg["day_story"]["triage_impact"]
    assert int(t["max_batches"]) == 4 and t["handoff_root"] == "data/scratch/workaround/handoff"
