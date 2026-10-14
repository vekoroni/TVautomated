"""Day story (ACK 14 Oct 2026): "lists the possible scenarios and the news and an explicit trade analysis
for the day ... using the data to come up with narratives and how it would impact tickers ... why the
flow of money is going into that sector or why it's coming out".

ACK's choices: narrator = both, clearly labelled (measured templates + a Claude narrative fed only the
measured facts); option-flow footprints included; impact on sector ETFs and pipeline candidates.
Business rules, written before the engine."""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from macro_board import day_story as ds

BANDS = {"1": 0.1, "5": 0.25, "20": 0.5}
WINDOWS = {"day": "1", "short": "5", "long": "20"}


# --- money flow: what the tape says, never assumed -------------------------------------------------

def test_a_month_long_leader_now_trailing_the_market_is_money_turning_out():
    flow = ds.money_flow({"1": -0.03, "5": -2.69, "20": 4.10}, BANDS, WINDOWS)
    assert flow["label"] == "TURNING_OUT"
    assert "-2.69" in flow["text"] and "+4.10" in flow["text"]


def test_steady_outperformance_is_inflow_and_steady_underperformance_is_outflow():
    assert ds.money_flow({"1": 0.2, "5": 1.0, "20": 2.0}, BANDS, WINDOWS)["label"] == "INFLOW"
    assert ds.money_flow({"1": -0.2, "5": -1.0, "20": -2.0}, BANDS, WINDOWS)["label"] == "OUTFLOW"
    assert ds.money_flow({"1": 0.2, "5": 1.0, "20": -2.0}, BANDS, WINDOWS)["label"] == "TURNING_IN"


def test_in_line_is_no_flow_but_missing_is_missing_never_neutral():
    assert ds.money_flow({"1": 0.0, "5": 0.1, "20": 3.0}, BANDS, WINDOWS)["label"] == "NONE"
    missing = ds.money_flow({"1": 0.1, "5": None, "20": 3.0}, BANDS, WINDOWS)
    assert missing["label"] == "MISSING" and "missing" in missing["text"].lower()


def test_share_volume_footprint_compares_the_last_session_with_its_own_average():
    idx = pd.bdate_range("2026-01-01", periods=25)
    vol = pd.Series([100.0] * 24 + [250.0], index=idx)
    fp = ds.volume_footprint(vol, window=20)
    assert fp["ratio"] == pytest.approx(2.5)
    assert ds.volume_footprint(pd.Series([100.0] * 5, index=idx[:5]), window=20)["ratio"] is None


# --- option-flow footprints: against the ticker's own history ---------------------------------------

def _flow_history(n=30, last_put_volume=840, last_iv=0.18, last_oi=None):
    dates = [str(d.date()) for d in pd.bdate_range("2026-08-01", periods=n)]
    rows = []
    for i, d in enumerate(dates):
        last = i == n - 1
        rows.append({"quote_date": d, "call_volume": 1000.0, "put_volume": float(last_put_volume if last else 800 + (i % 5) * 20),
                     "call_oi": 50000.0, "put_oi": float(last_oi if (last and last_oi) else 40000.0),
                     "atm_iv_pct": (last_iv if last else 0.18) * 100, "skew_pts": 5.0, "contracts": 200.0})
    return pd.DataFrame(rows)


CFG_FLOW = {"min_history_dates": 15, "max_age_sessions": 1, "heavy_volume_ratio": 2.0, "unusual_pctile": 0.9,
            "oi_change_unusual_pct": 10.0, "iv_change_unusual_pts": 1.5, "skew_change_unusual_pts": 1.0,
            "iv_max_median_change_ratio": 0.15, "skew_max_median_change_pts": 3.5, "coverage_tolerance_pct": 10.0}
SESSIONS = pd.bdate_range("2026-08-01", periods=30)


def test_heavy_put_buying_is_flagged_against_the_tickers_own_history():
    fp = ds.footprint(_flow_history(last_put_volume=3000), session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["status"] == "OK"
    keys = [f["key"] for f in fp["flags"]]
    assert "HEAVY_PUT_VOLUME" in keys and "HIGH_PUT_CALL_RATIO" in keys
    assert fp["lean"] == "PUT_SIDE"
    assert fp["put_volume_vs_median"] == pytest.approx(3000 / 840, rel=1e-3)


def test_a_quiet_options_day_has_no_flags_and_no_lean():
    fp = ds.footprint(_flow_history(last_put_volume=840), session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["status"] == "OK" and fp["flags"] == [] and fp["lean"] == "NONE"


def test_iv_jump_and_open_interest_build_are_measured_from_the_previous_stored_date():
    fp = ds.footprint(_flow_history(last_iv=0.21, last_oi=46000), session=str(SESSIONS[-1].date()), sessions=SESSIONS,
                      cfg=CFG_FLOW)
    assert fp["atm_iv_change_pts"] == pytest.approx(3.0)
    assert fp["put_oi_change_pct"] == pytest.approx(15.0)
    keys = [f["key"] for f in fp["flags"]]
    assert "IV_JUMP" in keys and "PUT_OI_BUILD" in keys
    assert fp["prior_date"] == str(SESSIONS[-2].date())


def test_no_chain_for_the_session_is_missing_and_thin_history_raises_no_flags():
    hist = _flow_history()
    old = ds.footprint(hist.iloc[:-3], session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert old["status"] == "MISSING" and old["flags"] == []
    thin = ds.footprint(_flow_history(n=8, last_put_volume=5000), session=str(SESSIONS[7].date()), sessions=SESSIONS,
                        cfg=CFG_FLOW)
    assert thin["status"] == "THIN" and thin["flags"] == []


def test_flow_history_reads_the_stored_surface_read_only(tmp_path):
    db = tmp_path / "phantom.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE iv_surface_history (ticker TEXT, quote_date TEXT, dte_bucket TEXT, side TEXT, "
                "contract_count INTEGER, atm_iv REAL, median_iv REAL, iv_entropy REAL, skew_25d REAL, "
                "put_call_iv_spread REAL, median_spread_pct REAL, total_open_interest INTEGER, total_volume INTEGER, "
                "created_at_utc TEXT)")
    for bucket, vol in (("0_7", 10), ("8_30", 100)):
        for side, iv in (("call", 0.20), ("put", 0.24)):
            con.execute("INSERT INTO iv_surface_history VALUES ('XLK','2026-10-13',?,?,1,?,0,0,0.05,0,0,1000,?, '')",
                        (bucket, side, iv, vol))
    con.commit()
    con.close()
    hist = ds.load_flow_history(db, ["XLK", "XLF"], as_of="2026-10-13", lookback_dates=60, front_bucket="8_30")
    row = hist["XLK"].iloc[-1]
    assert row["call_volume"] == 110 and row["put_volume"] == 110            # all buckets summed
    assert row["atm_iv_pct"] == pytest.approx(22.0)                          # front bucket, call/put mean
    assert row["skew_pts"] == pytest.approx(5.0)
    assert row["contracts"] == 4                                             # 2 buckets x 2 sides, 1 contract each
    assert "XLF" not in hist


# --- why: drivers tied to measured sensitivities, cross-asset moves and published items ------------

SENS = {"5": {"yields": {"state": "RISING", "excess_pct": -0.48, "t": -2.4, "n_eff_in": 151},
              "dollar": {"state": "STRENGTHENING", "excess_pct": 0.05, "t": 0.3, "n_eff_in": 100},
              "credit": {"state": "STABLE", "excess_pct": 0.31, "t": 2.2, "n_eff_in": 120}}}
LABELS = {"yields": "10y yields", "dollar": "Dollar", "credit": "Credit spreads"}


def test_only_conditions_with_a_measured_sector_response_become_drivers_and_fit_is_stated():
    drivers = ds.macro_drivers(SENS, horizon="5", flow_label="OUTFLOW", min_abs_t=2.0, labels=LABELS,
                               changes=[{"condition": "yields", "session": "2026-10-12", "from": "FLAT", "to": "RISING"}],
                               recent_sessions=["2026-10-09", "2026-10-12", "2026-10-13"])
    assert [d["condition"] for d in drivers] == ["yields", "credit"]          # ranked by |t|, dollar dropped
    assert drivers[0]["fit"] == "CONSISTENT" and drivers[1]["fit"] == "AGAINST"
    assert drivers[0]["recent_change"] == "2026-10-12"
    assert "-0.48" in drivers[0]["text"] and "t -2.4" in drivers[0]["text"]


def test_cross_asset_driver_uses_measured_co_movement_and_the_assets_own_move():
    idx = pd.bdate_range("2026-01-01", periods=80)
    rng = np.random.default_rng(1)
    tlt = pd.Series(rng.normal(0, 0.01, 80), index=idx)
    rel = tlt * 0.8 + pd.Series(rng.normal(0, 0.002, 80), index=idx)          # XLRE relative moves with TLT
    uup = pd.Series(rng.normal(0, 0.01, 80), index=idx)                       # unrelated
    drivers = ds.cross_asset_drivers(rel, pd.DataFrame({"TLT": tlt, "UUP": uup}),
                                     window=60, min_abs_corr=0.3, short=5, flow_label="OUTFLOW",
                                     names={"TLT": "long Treasuries", "UUP": "US dollar"})
    assert [d["asset"] for d in drivers] == ["TLT"]
    d = drivers[0]
    assert d["corr"] > 0.9
    expected_fit = "CONSISTENT" if d["asset_move_pct"] < 0 else "AGAINST"
    assert d["fit"] == expected_fit


def test_published_news_is_matched_to_sectors_by_keyword_and_labelled_as_published():
    items = [{"name": "Major US bank earnings", "institution": "JPMorgan Chase", "what_changed": "EPS beat",
              "surprise": "mixed", "time_utc": "2026-10-13T10:34:00Z", "source": "event payload (LLM)"},
             {"name": "Oil inventories", "institution": "EIA", "what_changed": "draw", "surprise": None}]
    matched = ds.match_news(items, {"XLF": ["bank", "JPMorgan"], "XLE": ["oil", "crude"], "XLK": ["semiconductor"]})
    assert [i["name"] for i in matched["XLF"]] == ["Major US bank earnings"]
    assert [i["name"] for i in matched["XLE"]] == ["Oil inventories"]
    assert "XLK" not in matched
    assert matched["XLF"][0]["label"] == "PUBLISHED"


# --- ticker impact: pipeline candidates against their sector's flow ---------------------------------

def test_candidates_are_read_against_their_sectors_money_flow():
    cands = [{"ticker": "NVDA", "direction": "CALL", "sector_etf": "XLK", "link_corr": 0.7, "verdict": "ARMED"},
             {"ticker": "AMD", "direction": "PUT", "sector_etf": "XLK", "link_corr": 0.6, "verdict": "ARMED"},
             {"ticker": "OKLO", "direction": "PUT", "sector_etf": "XLU", "link_corr": 0.2, "verdict": "ARMED"},
             {"ticker": "JPM", "direction": "CALL", "sector_etf": "XLF", "link_corr": 0.8, "verdict": "ARMED"},
             {"ticker": "ZZZ", "direction": "CALL", "sector_etf": None, "link_corr": None, "verdict": "ARMED"}]
    flows = {"XLK": "TURNING_OUT", "XLU": "INFLOW", "XLF": "NONE"}
    out = ds.candidate_links(cands, flows, min_link_corr=0.4)
    rel = {c["ticker"]: c["relation"] for etf in out.values() for c in etf}
    assert rel == {"NVDA": "AGAINST_FLOW", "AMD": "WITH_FLOW", "OKLO": "STOCK_SPECIFIC", "JPM": "NO_FLOW_READ",
                   "ZZZ": "NO_SECTOR"}


# --- trade analysis: explicit side, trigger, invalidation, expression and record --------------------

ROOM = {"current": 100.0, "daily_move_pct": 1.0,
        "above": {"name": "sma50", "level": 103.0, "distance_pct": 3.0, "distance_daily_moves": 3.0},
        "below": {"name": "sma200", "level": 98.0, "distance_pct": -2.0, "distance_daily_moves": 2.0}}


def test_outflow_means_puts_triggered_below_and_invalidated_above():
    idea = ds.trade_idea("XLK", flow={"label": "TURNING_OUT"}, room=ROOM, expression={"pricing": "CHEAP"},
                         drivers=[{"fit": "CONSISTENT"}, {"fit": "AGAINST"}, {"fit": "CONSISTENT"}],
                         footprint={"status": "OK", "lean": "PUT_SIDE"}, persistence=None, live=[])
    assert idea["side"] == "PUT"
    assert idea["trigger"]["level"] == 98.0 and idea["invalidation"]["level"] == 103.0
    assert idea["balance"] == {"with": 3, "against": 1}                          # 2 drivers + options footprint


def test_no_flow_is_stand_aside_with_what_would_make_it_a_trade():
    idea = ds.trade_idea("XLP", flow={"label": "NONE"}, room=ROOM, expression={"pricing": "FAIR"},
                         drivers=[], footprint={"status": "MISSING", "lean": "NONE"}, persistence=None, live=[])
    assert idea["side"] == "STAND_ASIDE"
    assert "103.00" in idea["text"] and "98.00" in idea["text"]


def test_missing_room_states_the_trigger_is_missing():
    idea = ds.trade_idea("XLB", flow={"label": "INFLOW"}, room={}, expression={"pricing": "UNKNOWN"}, drivers=[],
                         footprint={"status": "MISSING", "lean": "NONE"}, persistence=None, live=[])
    assert idea["side"] == "CALL" and idea["trigger"] is None and "missing" in idea["text"].lower()


# --- measured against reality: does the flow label persist? ----------------------------------------

def _tape(n=300, drift=0.0):
    idx = pd.bdate_range("2025-01-01", periods=n)
    spy = pd.Series(100 * np.cumprod(np.full(n, 1.0005)), index=idx)
    rng = np.random.default_rng(3)
    sector = pd.Series(100 * np.cumprod(1.0005 + drift + rng.normal(0, 0.004, n)), index=idx)
    closes = pd.DataFrame({"SPY": spy, "XLK": sector})
    return closes, closes.copy()


def test_flow_persistence_record_compares_each_label_with_all_sessions():
    closes, opens = _tape()
    rec = ds.flow_persistence(opens, closes, "XLK", benchmark="SPY", bands=BANDS, windows=WINDOWS, horizons=[5],
                              min_n_eff=5)
    assert set(rec["5"]["labels"]) >= {"INFLOW", "OUTFLOW"}
    all_n = rec["5"]["all"]["n"]
    assert sum(v["n"] for v in rec["5"]["labels"].values()) <= all_n
    for v in rec["5"]["labels"].values():
        assert "flow_side_rate" in v and "mean_rel_pp" in v


def test_the_ledger_is_idempotent_per_session_and_ticker(tmp_path):
    path = tmp_path / "ledger.jsonl"
    rows = [{"session": "2026-10-13", "ticker": "XLK", "flow": "TURNING_OUT", "kind": "EVENING"}]
    assert ds.record_stories(path, rows) == 1
    assert ds.record_stories(path, rows) == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_the_live_ledger_is_scored_once_the_horizon_has_passed():
    closes, opens = _tape(n=40, drift=0.002)
    s = [str(d.date()) for d in closes.index]
    ledger = [{"session": s[10], "ticker": "XLK", "flow": "INFLOW"}, {"session": s[-2], "ticker": "XLK", "flow": "INFLOW"}]
    score = ds.score_ledger(ledger, opens, closes, benchmark="SPY", horizons=[5])
    assert score["5"]["scored"] == 1 and score["5"]["pending"] == 1


# --- the AI narrative: fed only measured facts, labelled, never breaks the build --------------------

FACTS = {"session": "2026-10-13", "stories": [{"ticker": "XLK", "flow": "TURNING_OUT", "rel_5d_pp": -2.69,
                                                "rel_20d_pp": 4.10}]}
AI_CFG = {"enabled": True, "model": "claude-opus-5-5", "effort": "medium", "max_tokens": 4000,
          "call_on_build_kinds": ["MORNING", "EVENING"], "prompt_version": "test", "timeout_seconds": 30,
          "fallbacks": "default"}


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.content, self.stop_reason, self.model = [_Block(text)], stop, "claude-opus-5-5"


class _Client:
    def __init__(self, text=None, error=None):
        self.calls, self.text, self.error = [], text, error
        outer = self

        class _M:
            def create(self, **kw):
                outer.calls.append(kw)
                if outer.error:
                    raise outer.error
                return _Resp(outer.text)

        class _B:
            messages = _M()

        self.beta = _B()


GOOD = json.dumps({"overview": "Money left XLK: -2.69 pts vs SPY over 5 sessions after +4.10 over 20.",
                   "sectors": [{"ticker": "XLK", "money_flow": "TURNING_OUT", "story": "Leader giving back -2.69."}],
                   "tickers": [], "risks": ["A 7.5 pt rebound would undo it."], "would_change_view": []})


def test_disabled_or_wrong_build_kind_makes_no_call(tmp_path):
    client = _Client(GOOD)
    off = ds.ai_narrative(FACTS, {**AI_CFG, "enabled": False}, cache_dir=tmp_path, session="2026-10-13",
                          kind="EVENING", client_factory=lambda: client)
    assert off["status"] == "DISABLED" and client.calls == []
    other = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="INTRADAY",
                            client_factory=lambda: client)
    assert other["status"] == "NOT_CALLED" and client.calls == []


def test_the_prompt_carries_only_the_measured_facts_and_the_output_is_verified(tmp_path):
    client = _Client(GOOD)
    out = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING",
                          client_factory=lambda: client)
    assert out["status"] == "OK" and out["label"].startswith("AI NARRATIVE")
    sent = client.calls[0]
    assert sent["model"] == "claude-opus-5-5"
    assert json.dumps(FACTS, sort_keys=True) in sent["messages"][0]["content"]
    assert out["verification"]["unverified_numbers"] == ["7.5"]
    assert out["verification"]["flow_disagreements"] == []


def test_a_cached_narrative_for_the_same_facts_is_reused_without_a_call(tmp_path):
    first = _Client(GOOD)
    ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING", client_factory=lambda: first)
    second = _Client(GOOD)
    out = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING",
                          client_factory=lambda: second)
    assert out["status"] == "OK" and out["cached"] is True and second.calls == []


def test_api_failure_or_missing_credentials_never_breaks_the_build(tmp_path):
    out = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING",
                          client_factory=lambda: _Client(error=RuntimeError("boom")))
    assert out["status"] == "FAILED" and "RuntimeError" in out["reason"]

    def no_creds():
        raise RuntimeError("ANTHROPIC_WORKSPACE_ID is required")
    out = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path / "x", session="2026-10-13", kind="EVENING",
                          client_factory=no_creds)
    assert out["status"] == "UNAVAILABLE"


def test_an_ai_flow_call_that_contradicts_the_measured_flow_is_flagged(tmp_path):
    bad = json.dumps({"overview": "x", "sectors": [{"ticker": "XLK", "money_flow": "INFLOW", "story": "in"}],
                      "tickers": [], "risks": [], "would_change_view": []})
    out = ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING",
                          client_factory=lambda: _Client(bad))
    assert out["verification"]["flow_disagreements"] == ["XLK"]


# --- the record decides whether a flow is followed or faded (measured 14 Oct 2026: leaders that turn out
# have bounced back over the next 5 sessions, e.g. XLK +0.39 pts, t 2.0) -----------------------------

REC = {"5": {"labels": {"TURNING_OUT": {"n": 300, "n_eff": 61, "mean_rel_pp": 0.39, "t": 2.02, "excess_vs_all_pp": 0.22,
                                         "flow_side_rate": 0.38, "thin": False},
                        "OUTFLOW": {"n": 400, "n_eff": 119, "mean_rel_pp": -0.25, "t": -2.4, "excess_vs_all_pp": -0.17,
                                    "flow_side_rate": 0.56, "thin": False},
                        "INFLOW": {"n": 50, "n_eff": 9, "mean_rel_pp": 0.9, "t": 2.5, "excess_vs_all_pp": 0.8,
                                   "flow_side_rate": 0.6, "thin": True},
                        "TURNING_IN": {"n": 300, "n_eff": 70, "mean_rel_pp": 0.05, "t": 0.3, "excess_vs_all_pp": 0.0,
                                       "flow_side_rate": 0.5, "thin": False}}}}


def test_the_measured_record_says_whether_this_flow_has_followed_through_or_reversed():
    assert ds.persistence_verdict("TURNING_OUT", REC, "5", min_abs_t=2.0) == "REVERSES"
    assert ds.persistence_verdict("OUTFLOW", REC, "5", min_abs_t=2.0) == "FOLLOWS"
    assert ds.persistence_verdict("INFLOW", REC, "5", min_abs_t=2.0) == "THIN"
    assert ds.persistence_verdict("TURNING_IN", REC, "5", min_abs_t=2.0) == "NO_CLEAR_RECORD"
    assert ds.persistence_verdict("NONE", REC, "5", min_abs_t=2.0) is None


def test_a_flow_that_has_reversed_in_history_counts_against_following_it():
    idea = ds.trade_idea("XLK", flow={"label": "TURNING_OUT"}, room=ROOM, expression={"pricing": "FAIR"},
                         drivers=[], footprint={"status": "MISSING", "lean": "NONE"}, persistence="text",
                         live=[], record="REVERSES")
    assert idea["side"] == "PUT" and idea["record"] == "REVERSES"
    assert idea["balance"] == {"with": 0, "against": 1}
    assert "reversed" in idea["text"]


# --- stored-surface accuracy (measured 14 Oct 2026: stored 25-delta skew moves 10-50 pts a day for half the
# sector ETFs, e.g. XLB 50, XLU 34, against 1.7 for SPY; chain coverage changes day to day) ----------------

def test_an_unstable_stored_skew_series_is_not_read():
    h = _flow_history()
    h["skew_pts"] = [(-20.0 if i % 2 else 25.0) for i in range(len(h))]
    h.loc[h.index[-1], "skew_pts"] = -30.0
    fp = ds.footprint(h, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["skew_status"] == "UNRELIABLE" and fp["skew_change_pts"] is None
    assert not [f for f in fp["flags"] if f["key"].startswith("SKEW")]


def test_an_iv_change_must_be_unusual_against_the_tickers_own_day_to_day_changes():
    h = _flow_history()
    h["atm_iv_pct"] = [18.0 + (1.0 if i % 2 else -1.0) for i in range(len(h))]   # +-2 pts every day
    h.loc[h.index[-1], "atm_iv_pct"] = h["atm_iv_pct"].iloc[-2] + 2.0
    fp = ds.footprint(h, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["iv_status"] == "OK"
    assert not [f for f in fp["flags"] if f["key"].startswith("IV_")]


def test_open_interest_is_not_compared_across_a_change_in_chain_coverage():
    h = _flow_history(last_oi=46000)
    h.loc[h.index[-1], "contracts"] = 240.0                                     # +20% coverage
    fp = ds.footprint(h, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["put_oi_change_pct"] is None and "coverage" in fp["coverage_note"]
    assert not [f for f in fp["flags"] if f["key"].endswith("OI_BUILD")]


def test_volume_is_compared_only_with_dates_of_comparable_coverage():
    h = _flow_history(last_put_volume=1700)
    h.loc[h.index[:10], ["put_volume", "contracts"]] = [300.0, 80.0]          # thin early captures
    fp = ds.footprint(h, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["put_volume_vs_median"] == pytest.approx(1700 / 840, rel=1e-3)


def test_iv_stability_is_judged_relative_to_the_iv_level():
    calm_high_iv = _flow_history()
    calm_high_iv["atm_iv_pct"] = [35.0 + (1.25 if i % 2 else -1.25) for i in range(len(calm_high_iv))]   # 2.5 pts at 35%
    assert ds.footprint(calm_high_iv, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)["iv_status"] == "OK"
    noisy = _flow_history()
    noisy["atm_iv_pct"] = [20.0 + (4.5 if i % 2 else -4.5) for i in range(len(noisy))]                   # 9 pts at 20%
    fp = ds.footprint(noisy, session=str(SESSIONS[-1].date()), sessions=SESSIONS, cfg=CFG_FLOW)
    assert fp["iv_status"] == "UNRELIABLE" and fp["atm_iv_change_pts"] is None


def test_a_build_that_may_not_call_shows_the_sessions_earlier_narrative_labelled_as_such(tmp_path):
    ds.ai_narrative(FACTS, AI_CFG, cache_dir=tmp_path, session="2026-10-13", kind="EVENING",
                    client_factory=lambda: _Client(GOOD))
    later = _Client(GOOD)
    out = ds.ai_narrative({**FACTS, "next_session": "2026-10-14"}, AI_CFG, cache_dir=tmp_path, session="2026-10-13",
                          kind="INTRADAY", client_factory=lambda: later)
    assert out["status"] == "OK" and out["earlier_build"] is True and later.calls == []
