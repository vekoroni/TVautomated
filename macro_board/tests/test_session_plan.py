"""Business rules for the Next session plan (ACK 10 Oct 2026).

The plan puts the board's pieces in a veteran's order: the call (what the market did and whether it
accepted the news), scenarios per index ETF with measured triggers, history and expression, a
time-ordered checklist for the next session, where the opportunity is, what would change the view,
and the jigsaw - every input with what it points to and whether it agrees. Sentences are assembled
from measured fields (ACK: templates, not an LLM). Research only: nothing scores or gates, and a
likelihood appears only where history measured one. No live data or network.
"""

from __future__ import annotations

import copy

from macro_board import session_plan as sp

CFG = {
    "focus": ["SPY", "QQQ", "IWM", "DIA"],
    "tape_majority": 3,
    "gap_daily_moves": 0.5,
    "history_horizons": ["1", "5"],
    "expression_horizon": "5",
    "options_cheap_below": 0.9,
    "options_rich_above": 1.1,
    "runway_multiple": 2.0,
    "usmi_risk_off_min": 60,
    "usmi_risk_on_max": 40,
    "strength_windows": ["5", "20"],
    "max_sectors": 4,
    "max_pipeline": 8,
    "max_unscheduled": 3,
    "max_counter_conditions": 4,
    "max_target_daily_moves": 50.0,
    "approach": {"UP_BROAD": "Approach up broad.", "UP_NARROW": "Approach up narrow.", "UP_UNKNOWN": "Approach up.",
                 "DOWN_BROAD": "Approach down broad.", "DOWN_NARROW": "Approach down narrow.", "DOWN_UNKNOWN": "Approach down.",
                 "MIXED": "Approach mixed.", "UNKNOWN": "Approach unknown."},
    "expression_text": {"CHEAP": "Options priced below history.", "FAIR": "Options priced in line.",
                        "RICH": "Options priced above history.", "UNKNOWN": "No option pricing."},
    "conflict_note": "Published narratives disagree with the measured tape: {pieces}.",
    "check_horizon": "5",
    "room_min_daily_moves": 0.5,
    "min_link_corr": 0.4,
    "max_candidates": 50,
    "action_text": {"ALIGNED": "Aligned: weakens if {etf} {fail} {level}.", "MIXED": "Mixed: let {etf} {confirm} {level}.",
                    "AGAINST": "Against: wait for {etf} to {confirm} {level} or stand aside.", "NO_PROPOSAL": "No pipeline proposal.",
                    "NO_SECTOR_READ": "No board read for this stock's sector ETF.",
                    "STOCK_SPECIFIC": "Stock-specific: judge on its own chart; market tape {market}."},
}


def _stats(n=100, mean=0.05, hit=0.55):
    return {"n": n, "n_eff": n, "mean_pct": mean, "hit_rate": hit, "mean_abs_pct": 0.6}


def _evidence(lean="NO_CLEAR_LEAN"):
    return {"lean": lean, "holdout": "NOT_APPLICABLE", "analog": _stats(), "base": _stats(1000, 0.02, 0.53)}


def _etf(close=100.0, direction="CALL", verdict="ARMED", ratio=0.85, status="FRESH"):
    return {"metrics": {"status": "FRESH", "close": close, "last_session": "2026-10-09", "rv20": 15.874},
            "evidence": {"1": _evidence(), "5": _evidence(), "20": _evidence()},
            "decision": {"response": {"20": {"headwinds": ["yields"], "tailwinds": ["market_breadth"], "label": "MIXED"}}},
            "options": {"status": status, "quote_date": "2026-10-08", "sessions_old": 1,
                        "moves": {"1": {"implied_move_pct": 0.8, "priced_vs_history": ratio, "analog_mean_abs_pct": 0.9},
                                  "5": {"implied_move_pct": 1.8, "priced_vs_history": ratio, "analog_mean_abs_pct": 2.1}}},
            "tastytrade": {"iv_rank_pct": 20.0, "iv_hv_diff_pct": 3.0, "iv_expected_abs_move_pct": {"1": 0.9, "5": 2.0}},
            "pipeline": {"canonical_direction": direction, "options_verdict": verdict},
            "momentum": {"evidence": {"streak": {"1": _evidence()}}}}


def _room(current=100.0):
    return {"close": 100.0, "current": current, "current_basis": "CLOSE", "daily_move_pct": 1.0,
            "levels": {"high_252": 102.0, "call_wall": 104.0, "gamma_flip": 99.0, "sma50": 97.0, "sma200": 90.0}}


def _reaction(key="ACCEPTED_UP", close_pct=0.6):
    label = key.split("_")[0] if key != "ABSORBED" else "ABSORBED"
    return {"key": key, "label": label, "close_pct": close_pct, "daily_move_pct": 1.0}


def _payload():
    etfs = {t: _etf() for t in ("SPY", "QQQ", "IWM", "DIA", "RSP")}
    etfs["XBI"] = _etf(direction="PUT")
    etfs["XLK"] = _etf(verdict="STAND_DOWN")
    return {
        "as_of_session": "2026-10-09",
        "horizons": [1, 5, 20],
        "conditions": {"meta": [{"key": "yields", "label": "10Y yield"}, {"key": "market_breadth", "label": "Breadth"},
                                {"key": "market_trend", "label": "SPY trend"}],
                       "current": {"market_trend": "ABOVE_BOTH", "yields": "RISING"}},
        "etfs": etfs,
        "review": {"headline": "SPY accepted (up) · QQQ accepted (up)",
                   "instruments": {"SPY": _reaction(), "QQQ": _reaction(), "IWM": _reaction("REJECTED_GAP_DOWN"),
                                   "DIA": _reaction("ABSORBED", 0.1)},
                   "scored": {t: {"today": _reaction(), "evidence": {"1": _evidence(), "5": _evidence()}}
                              for t in ("SPY", "QQQ", "IWM", "DIA")},
                   "unresolved": {"verdict": "TWO_WAY_RISK", "counter_case": "Relief may prove temporary."}},
        "decision_points": {
            "next_session": "2026-10-12",
            "calendar": [
                {"kind": "RELEASE", "date": "2026-10-12", "sessions_ahead": 1, "name": "Consumer sentiment", "time_et": "10:00", "source": "FRED release calendar"},
                {"kind": "RELEASE", "date": "2026-10-12", "sessions_ahead": 1, "name": "Empire State", "time_et": "08:30", "source": "FRED release calendar"},
                {"kind": "RELEASE", "date": "2026-10-14", "sessions_ahead": 3, "name": "CPI", "time_et": "08:30", "source": "FRED release calendar"},
                {"kind": "EARNINGS", "date": "2026-10-12", "sessions_ahead": 1, "name": "JPM earnings", "time_et": "BMO", "source": "MarketData"},
            ],
            "unscheduled": {"items": [{"name": "Oil and yields", "importance": "HIGH", "confirms": "oil lower", "fails": "oil higher",
                                       "source": "news enrichment (LLM)", "as_of": "2026-10-09T12:43:16Z"}]},
        },
        "opportunity": {
            "leadership": {"windows": {"1": {"leader": "SPY", "qqq_minus_spy_pp": -0.1}, "5": {"leader": "SPY", "qqq_minus_spy_pp": -0.9},
                                       "20": {"leader": "QQQ", "qqq_minus_spy_pp": 3.2}},
                           "breadth": {"state": "CONCENTRATED", "rsp_minus_spy_20d_pp": -2.72}},
            "sectors": [
                {"ticker": "XLF", "windows": {"5": {"label": "OUTPERFORMING_AND_RISING", "relative_pp": 1.2, "constituents": "CONFIRMED"},
                                              "20": {"label": "OUTPERFORMING_AND_RISING", "relative_pp": 0.8, "constituents": "UNKNOWN"}}},
                {"ticker": "XLK", "windows": {"5": {"label": "UNDERPERFORMING_AND_FALLING", "relative_pp": -1.7},
                                              "20": {"label": "OUTPERFORMING_AND_RISING", "relative_pp": 4.0}}},
                {"ticker": "XLC", "windows": {"5": {"label": "UNDERPERFORMING_AND_FALLING", "relative_pp": -2.0},
                                              "20": {"label": "UNDERPERFORMING_AND_FALLING", "relative_pp": -3.0}}},
                {"ticker": "XLU", "windows": {"5": {"label": "OUTPERFORMING_WHILE_FALLING", "relative_pp": 0.5},
                                              "20": {"label": "IN_LINE", "relative_pp": 0.1}}},
            ],
            "room": {t: _room() for t in ("SPY", "QQQ", "IWM", "DIA")},
        },
        "overnight": {"status": "STALE", "us_reference_session": "2026-10-08", "as_of": "2026-10-08T21:37:21+00:00"},
        "etf_reactions": {"SPY": {"key": "ACCEPTED_UP", "close_pct": 0.6}, "XLK": {"key": "ACCEPTED_DOWN", "close_pct": -1.2},
                          "XBI": {"key": "ACCEPTED_DOWN", "close_pct": -0.9}, "XLU": {"key": "ABSORBED", "close_pct": 0.1}},
        "etf_levels": {"XLK": {"close": 200.0, "current": 200.0, "current_basis": "CLOSE", "daily_move_pct": 1.5,
                               "above": {"name": "sma50", "level": 201.0, "distance_pct": 0.5, "distance_daily_moves": 0.33},
                               "below": {"name": "sma200", "level": 190.0, "distance_pct": -5.0, "distance_daily_moves": 3.33}},
                       "XBI": {"close": 90.0, "current": 90.0, "current_basis": "CLOSE", "daily_move_pct": 2.0,
                               "above": {"name": "sma50", "level": 95.0, "distance_pct": 5.6, "distance_daily_moves": 2.8},
                               "below": {"name": "low_252", "level": 85.0, "distance_pct": -5.6, "distance_daily_moves": 2.8}},
                       "XLU": {"close": 80.0, "current": 80.0, "current_basis": "CLOSE", "daily_move_pct": 0.8,
                               "above": {"name": "high_252", "level": 82.0, "distance_pct": 2.5, "distance_daily_moves": 3.1},
                               "below": {"name": "sma50", "level": 78.0, "distance_pct": -2.5, "distance_daily_moves": 3.1}}},
        "money_index": {"reading": {"score": 55.0, "band": "TRANSITION"},
                        "per_etf": {"XLK": {"spy": {"beta": 1.3, "corr": 0.9}, "qqq": {"beta": 1.1, "corr": 0.95}, "ic": {"ic": -0.2, "n": 200},
                                            "band_evidence": {"5": {"lean": "DOWN", "analog": _stats(80, -0.4, 0.4), "base": _stats(1000, 0.2, 0.56)}}},
                                    "XBI": {"spy": {"beta": 1.2, "corr": 0.6}, "qqq": {"beta": 1.0, "corr": 0.6}, "ic": {"ic": None, "n": 5},
                                            "band_evidence": {}},
                                    "XLU": {"spy": {"beta": 0.4, "corr": 0.3}, "qqq": {"beta": 0.2, "corr": 0.2}, "ic": {"ic": 0.1, "n": 200},
                                            "band_evidence": {"5": {"lean": "NO_CLEAR_LEAN", "analog": _stats(), "base": _stats()}}}}},
        "pipeline_candidates": {"status": "OK", "run_id": "20261008_220129", "rows": [
            {"rank": 1, "ticker": "NVDA", "canonical_direction": "CALL", "options_verdict": "ARMED", "horizon_bucket": "1_5d",
             "sector_etf": "XLK", "link": {"beta": 1.6, "corr": 0.8, "n": 60}},
            {"rank": 2, "ticker": "NEE", "canonical_direction": "PUT", "options_verdict": "ARMED", "horizon_bucket": "6_10d",
             "sector_etf": "XLU", "link": {"beta": 0.5, "corr": 0.2, "n": 60}},
            {"rank": 3, "ticker": "ZZZ", "canonical_direction": "CALL", "options_verdict": "STAND_DOWN", "horizon_bucket": "1_5d",
             "sector_etf": "XYZ", "link": {"beta": None, "corr": None, "n": 0}}]},
        "intel": {
            "packet": {"dir_bias": "MILDLY_BULLISH", "risk_on_off_switch": "SELECTIVE_RISK_ON_REDUCED_SIZE"},
            "usmi": {"score": 83, "transmission_state": "RISK_OFF_TRANSITION_CONFIRMED"},
            "events": {"verdict": {"verdict": "TWO_WAY_RISK"},
                       "counter_case": {"summary": "Relief may fade.", "reversal_or_neutralisation_conditions": ["Brent returns above 105", "10Y above 5.30"]}},
            "enrichment": {"alert_level": "AMBER", "fragility_score": 4.0},
            "bond": {"composite": {"macro_bond_score": 73, "trade_go": True}},
            "gex": [{"Ticker": "SPY", "Date": "2026-10-05", "Regime": "NEGATIVE", "Gamma_Flip": 99.0}],
            "vix_engine": [{"Date": "2026-10-08", "VIX_Direct": 15.4, "VIX_Structure": "CONTANGO"}],
            "forward_bias": [{"horizon": "short_1_5d", "direction": "NEUTRAL"}],
        },
        "external": {"macro_packet": {"status": "STALE", "as_of": "2026-10-08T22:38:14+00:00"},
                     "us_money_index": {"status": "FRESH", "as_of": "2026-10-09T11:00:22+00:00"},
                     "event_payload": {"status": "FRESH", "as_of": "2026-10-09T00:00:00+00:00"},
                     "enrichment": {"status": "FRESH", "as_of": "2026-10-09T12:43:16+00:00"},
                     "bond_state": {"status": "STALE", "as_of": "2026-10-08T22:36:31+00:00"},
                     "gex": {"status": "STALE", "as_of": "2026-10-05"},
                     "vix_engine": {"status": "STALE", "as_of": "2026-10-08"},
                     "forward_bias": {"status": "STALE", "as_of": "2026-10-08"},
                     "overnight": {"status": "STALE", "as_of": "2026-10-08T21:37:21+00:00"}},
    }


# -- the call ------------------------------------------------------------------------------------

def test_the_tape_is_up_when_most_indices_closed_up_and_a_rejected_down_gap_counts_as_buyers():
    p = _payload()
    tp = sp.tape(p["review"]["instruments"], CFG["focus"], majority=3)
    assert tp["direction"] == "UP" and tp["up"] == ["SPY", "QQQ", "IWM"] and tp["absorbed"] == ["DIA"]
    p["review"]["instruments"]["QQQ"] = _reaction("ACCEPTED_DOWN", -0.8)
    assert sp.tape(p["review"]["instruments"], CFG["focus"], majority=3)["direction"] == "MIXED"
    assert sp.tape({}, CFG["focus"], majority=3)["direction"] == "UNKNOWN"


def test_the_call_names_the_reaction_the_breadth_and_the_measured_headwinds():
    plan = sp.build(_payload(), CFG)
    call = plan["call"]
    assert call["key"] == "UP_NARROW" and call["approach"] == "Approach up narrow."
    assert call["headwinds"] == ["10Y yield"] and call["tailwinds"] == ["Breadth"]
    text = " ".join(call["sentences"])
    assert "SPY accepted (up)" in text and "2.7" in text and "10Y yield" in text


# -- scenarios ------------------------------------------------------------------------------------

def test_scenarios_use_the_nearest_levels_around_the_current_price_and_the_next_level_as_target():
    s = sp.build(_payload(), CFG)["instruments"]["SPY"]
    assert s["up"]["trigger"]["name"] == "high_252" and s["up"]["target"]["name"] == "call_wall"
    assert s["down"]["trigger"]["name"] == "gamma_flip" and s["down"]["target"]["name"] == "sma50"
    assert s["base"]["low"]["level"] == 99.0 and s["base"]["high"]["level"] == 102.0
    assert s["up"]["trigger"]["distance_pct"] == 2.0 and s["up"]["trigger"]["distance_daily_moves"] == 2.0
    assert s["implied_move_pct"] == 0.8 and "straddle" in s["implied_source"]


def test_a_later_quote_moves_the_reference_and_without_a_level_beyond_the_target_is_one_implied_move():
    p = _payload()
    p["opportunity"]["room"]["SPY"] = {**_room(current=103.0), "current_basis": "PREMARKET 08:40 ET"}
    s = sp.build(p, CFG)["instruments"]["SPY"]
    assert s["reference"] == 103.0 and s["basis"] == "PREMARKET 08:40 ET"
    assert s["up"]["trigger"]["name"] == "call_wall" and s["up"]["target"]["name"] == "one_implied_move"
    assert s["up"]["target"]["level"] == round(104.0 * 1.008, 4)
    assert s["down"]["trigger"]["name"] == "high_252" and s["down"]["target"]["name"] == "gamma_flip"


def test_a_target_further_than_the_limit_is_replaced_by_one_implied_move_and_the_far_level_is_kept():
    # 10 Oct 2026 real build: IWM's next level below was the pipeline invalidation, 14% away - not a
    # next-session target.
    p = _payload()
    p["opportunity"]["room"]["SPY"]["levels"]["sma50"] = 80.0
    del p["opportunity"]["room"]["SPY"]["levels"]["sma200"]
    s = sp.build(p, {**CFG, "max_target_daily_moves": 5.0})["instruments"]["SPY"]
    assert s["down"]["trigger"]["name"] == "gamma_flip"
    assert s["down"]["target"]["name"] == "one_implied_move" and s["down"]["target"]["level"] == round(99.0 * 0.992, 4)
    assert s["down"]["next_mapped"]["name"] == "sma50" and s["down"]["next_mapped"]["level"] == 80.0


def test_gex_levels_from_an_earlier_session_carry_their_date_wherever_they_are_quoted():
    p = _payload()
    p["opportunity"]["room"]["SPY"]["gex_as_of"] = "2026-10-05"
    plan = sp.build(p, CFG)
    s = plan["instruments"]["SPY"]
    assert s["down"]["trigger"]["label"] == "GEX flip (2026-10-05)" and s["up"]["trigger"]["label"] == "252d high"
    assert any("GEX flip (2026-10-05)" in i["item"] for i in plan["checklist"] if i["item"].startswith("SPY"))


def test_history_is_quoted_as_measured_and_a_scenario_is_marked_only_when_history_leans():
    p = _payload()
    plan = sp.build(p, CFG)["instruments"]["SPY"]
    assert plan["history_leans"] is None
    assert all(not s.get("history_leans_here") for s in (plan["up"], plan["down"], plan["base"]))
    assert "100 past sessions" in plan["history"][0]["text"] and "55%" in plan["history"][0]["text"]
    p["review"]["scored"]["SPY"]["evidence"]["1"] = _evidence("UP")
    leaned = sp.build(p, CFG)["instruments"]["SPY"]
    assert leaned["history_leans"] == "UP" and leaned["up"]["history_leans_here"] is True


def test_option_pricing_below_history_is_cheap_above_is_rich_and_missing_quotes_say_so():
    assert sp.expression(_etf(ratio=0.85), CFG)["pricing"] == "CHEAP"
    assert sp.expression(_etf(ratio=1.25), CFG)["pricing"] == "RICH"
    assert sp.expression(_etf(ratio=1.0), CFG)["pricing"] == "FAIR"
    missing = sp.expression(_etf(status="MISSING"), CFG)
    assert missing["pricing"] == "UNKNOWN" and missing["text"] == "No option pricing."
    assert sp.expression(_etf(), CFG)["runway_sessions"] == 10                    # 2 x the 5-session horizon


# -- checklist ------------------------------------------------------------------------------------

def test_the_checklist_runs_in_time_order_with_the_next_sessions_events_and_opening_levels():
    items = sp.build(_payload(), CFG)["checklist"]
    names = [i["item"] for i in items]
    assert not any("CPI" in n for n in names)                                     # three sessions away
    order = [i["phase"] for i in items]
    assert order == sorted(order, key=sp.PHASES.index)
    first = items[0]
    assert first["phase"] == "PRE_OPEN" and "PreOpen" in first["item"]           # overnight belongs to 8 Oct
    pre = [i for i in items if i["phase"] == "PRE_OPEN"]
    assert [i["time_et"] for i in pre if i["time_et"]] == sorted(i["time_et"] for i in pre if i["time_et"])
    assert any("Empire State" in i["item"] and i["time_et"] == "08:30" for i in pre)
    assert any("JPM" in i["item"] for i in pre)                                   # before the open
    opening = [i for i in items if i["phase"] == "OPEN"]
    assert any(i["item"].startswith("SPY") and "99.00" in i["item"] for i in opening)
    assert any("Consumer sentiment" in i["item"] for i in items if i["phase"] == "INTRADAY")
    assert any(i["source"] == "news enrichment (LLM)" for i in items if i["phase"] == "WATCH")


# -- jigsaw ----------------------------------------------------------------------------------------

def test_every_piece_states_what_it_points_to_and_a_missing_input_is_missing_not_neutral():
    p = _payload()
    del p["intel"]["usmi"]
    jig = sp.build(p, CFG)["jigsaw"]
    pieces = {x["key"]: x for x in jig["pieces"]}
    assert pieces["usmi"]["points"] == "MISSING" and pieces["usmi"]["stance"] == "MISSING"
    assert pieces["reaction"]["points"] == "UP" and pieces["reaction"]["stance"] == "SUPPORTS"
    assert pieces["breadth"]["stance"] == "OPPOSES"                                 # concentrated
    assert pieces["trend"]["points"] == "UP" and pieces["macro_response"]["points"] == "NEUTRAL"
    assert all({"group", "says", "points", "stance", "freshness"} <= set(x) for x in jig["pieces"])
    total = jig["agreement"]["all"]
    assert sum(total.values()) == len(jig["pieces"]) and total["MISSING"] >= 1


def test_llm_pieces_are_counted_apart_and_a_conflict_with_the_measured_tape_is_called_out():
    plan = sp.build(_payload(), CFG)
    pieces = {x["key"]: x for x in plan["jigsaw"]["pieces"]}
    assert pieces["usmi"]["group"] == "LLM" and pieces["usmi"]["points"] == "DOWN"
    assert pieces["packet"]["points"] == "UP" and pieces["event_payload"]["points"] == "NEUTRAL"
    agreement = plan["jigsaw"]["agreement"]
    assert set(agreement) >= {"MEASURED", "MODEL", "LLM", "all"}
    p = _payload()
    p["intel"]["packet"]["dir_bias"] = "BEARISH"
    conflicted = sp.build(p, CFG)
    assert conflicted["call"]["conflict"] is not None
    assert "US Money Index" in conflicted["call"]["conflict"]


def test_stale_inputs_carry_their_date_and_overnight_from_another_session_is_missing():
    pieces = {x["key"]: x for x in sp.build(_payload(), CFG)["jigsaw"]["pieces"]}
    assert pieces["gex"]["freshness"] == "STALE" and pieces["gex"]["as_of"] == "2026-10-05"
    assert pieces["overnight"]["points"] == "MISSING"


# -- opportunity and what changes the view ------------------------------------------------------------

def test_strength_and_weakness_need_every_window_and_pipeline_candidates_show_agreement_with_the_tape():
    opp = sp.build(_payload(), CFG)["opportunity"]
    assert [r["ticker"] for r in opp["strength"]] == ["XLF"]
    assert [r["ticker"] for r in opp["weakness"]] == ["XLC"]
    assert [r["ticker"] for r in opp["defensive"]] == ["XLU"]
    cands = {r["ticker"]: r for r in opp["pipeline"]}
    assert cands["SPY"]["agrees_with_tape"] is True and cands["XBI"]["agrees_with_tape"] is False
    order = list(cands)
    assert order[:4] == ["SPY", "QQQ", "IWM", "DIA"]                             # focus ETFs first, in focus order
    assert order[-1] == "XLK"                                                     # stand-downs last


def test_what_would_change_the_view_names_the_opposite_level_and_the_published_reversal_conditions():
    items = sp.build(_payload(), CFG)["change_view"]
    text = " | ".join(i["text"] for i in items)
    assert "SPY" in text and "99.00" in text
    assert any(i["source"] == "event payload (LLM)" and "Brent" in i["text"] for i in items)


def test_the_plan_does_not_change_the_payload_it_reads():
    p = _payload()
    before = copy.deepcopy(p)
    sp.build(p, CFG)
    assert p == before


# -- per ETF, with correlation, and the pipeline's candidates (ACK 10 Oct 2026) ---------------------------------

def test_every_etf_gets_its_own_reading_with_beta_and_what_spys_scenarios_imply_for_it():
    rows = {r["ticker"]: r for r in sp.build(_payload(), CFG)["etfs"]}
    xlk = rows["XLK"]
    assert xlk["reaction"] == "ACCEPTED_DOWN" and xlk["beta_spy"] == 1.3 and xlk["corr_spy"] == 0.9
    assert xlk["if_spy_down_target_pct"] == round(1.3 * -3.0, 2) and xlk["if_spy_up_target_pct"] == round(1.3 * 4.0, 2)
    assert xlk["above"]["level"] == 201.0 and xlk["band_lean"] == "DOWN"
    assert "beta estimate" in xlk["implied_note"]


def test_a_call_against_the_etfs_own_tape_and_measured_history_reads_against_with_the_level_to_watch():
    p = _payload()
    p["etfs"]["XLK"]["pipeline"] = {"canonical_direction": "CALL", "options_verdict": "ARMED"}
    xlk = {r["ticker"]: r for r in sp.build(p, CFG)["etfs"]}["XLK"]
    checks = {c["check"]: c["state"] for c in xlk["checks"]}
    assert checks["own_tape"] == "AGAINST" and checks["money_index_band"] == "AGAINST" and checks["market_tape"] == "WITH"
    assert checks["room"] == "AGAINST"                                            # 50d avg 0.33 daily moves above
    assert xlk["alignment"] == "AGAINST" and "XLK" in xlk["action"] and "201.00" in xlk["action"]


def test_an_etf_without_a_proposal_is_described_not_judged():
    xlu = {r["ticker"]: r for r in sp.build(_payload(), CFG)["etfs"]}["XLU"]
    assert xlu["alignment"] == "NO_PROPOSAL" and xlu["checks"] == []


def test_a_pipeline_stock_is_read_through_its_sector_etf_and_a_weak_link_is_labelled():
    cands = {c["ticker"]: c for c in sp.build(_payload(), CFG)["candidates"]}
    nvda = cands["NVDA"]
    assert nvda["sector_etf"] == "XLK" and nvda["link_corr"] == 0.8 and nvda["weak_link"] is False
    states = {c["check"]: c["state"] for c in nvda["checks"]}
    assert states["sector_tape"] == "AGAINST" and states["money_index_band"] == "AGAINST" and states["market_tape"] == "WITH"
    assert nvda["alignment"] == "AGAINST"
    nee = cands["NEE"]
    assert nee["weak_link"] is True and any(c["check"] == "link" and c["state"] == "NEUTRAL" for c in nee["checks"])
    assert nee["alignment"] == "STOCK_SPECIFIC" and nee["action"] == "Stock-specific: judge on its own chart; market tape against."
    zzz = cands["ZZZ"]
    assert zzz["alignment"] == "NO_SECTOR_READ" and zzz["action"] == "No board read for this stock's sector ETF."
    assert [c["ticker"] for c in sp.build(_payload(), CFG)["candidates"]] == ["NVDA", "NEE", "ZZZ"]   # pipeline order kept


def test_missing_measured_history_is_a_missing_check_not_a_neutral_one():
    p = _payload()
    p["etfs"]["XBI"]["pipeline"] = {"canonical_direction": "PUT", "options_verdict": "ARMED"}
    xbi = {r["ticker"]: r for r in sp.build(p, CFG)["etfs"]}["XBI"]
    checks = {c["check"]: c["state"] for c in xbi["checks"]}
    assert checks["money_index_band"] == "MISSING" and checks["own_tape"] == "WITH"


def test_the_pipeline_candidates_come_from_the_newest_run_in_ranked_order_calls_and_puts_only(tmp_path):
    import pandas as pd
    from macro_board import sources as src
    for run, rows in (("20261006_060401", [("OLD", "CALL")]), ("20261008_220129", [("AAA", "PUT"), ("BBB", "UNRESOLVED"), ("CCC", "CALL"), ("AAA", "CALL")])):
        d = tmp_path / run / "options"
        d.mkdir(parents=True)
        pd.DataFrame({"ticker": [r[0] for r in rows], "canonical_direction": [r[1] for r in rows],
                      "sector_etf": ["XLK"] * len(rows), "unused": [1] * len(rows)}).to_csv(d / "options_candidates_ranked.csv", index=False)
    out = src.load_pipeline_candidates(tmp_path, "options/options_candidates_ranked.csv", ["canonical_direction", "sector_etf"],
                                       sides=["CALL", "PUT"], limit=10)
    assert out["run_id"] == "20261008_220129"
    assert [(r["ticker"], r["rank"]) for r in out["rows"]] == [("AAA", 1), ("CCC", 3)]
    assert "unused" not in out["rows"][0]


def test_the_action_names_a_market_level_never_the_pipelines_own_target_and_a_put_is_confirmed_below():
    p = _payload()
    p["etfs"]["XBI"]["pipeline"] = {"canonical_direction": "PUT", "options_verdict": "ARMED"}
    p["etf_reactions"]["XBI"] = {"key": "ACCEPTED_UP", "close_pct": 0.9}
    p["etf_levels"]["XBI"] = {"close": 90.0, "current": 90.0, "current_basis": "CLOSE", "daily_move_pct": 2.0,
                              "levels": {"pipeline_target": 89.0, "sma50": 86.0, "sma200": 95.0},
                              "above": {"name": "sma200", "level": 95.0, "distance_pct": 5.6, "distance_daily_moves": 2.8},
                              "below": {"name": "pipeline_target", "level": 89.0, "distance_pct": -1.1, "distance_daily_moves": 0.56}}
    xbi = {r["ticker"]: r for r in sp.build(p, CFG)["etfs"]}["XBI"]
    assert xbi["below"]["name"] == "sma50" and xbi["alignment"] == "AGAINST"
    assert xbi["action"] == "Against: wait for XBI to break below 50d avg 86.00 or stand aside."
