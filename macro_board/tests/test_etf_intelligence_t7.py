"""AVS-MACRO-TRIAGE-001 T7 (design approved by ACK 20 Nov 2026): more intelligence in the same per-ETF projection.

T7a event file read with a tolerant field-name reader; T7b US Money Index counter-evidence, triggers and sector
routing; T7c a peer reference beside SPY; T7d every board-universe ETF gets a read, so a hand-off name that is
its own sector ETF is no longer blank. Every LLM item is labelled LLM_WITH_NEWS with its as-of time; missing is
MISSING, never neutral; nothing here changes a pipeline gate, rank, contract, side or size.
Business rules, written before the code."""

from __future__ import annotations

import json
from pathlib import Path

from macro_board import etf_intelligence as ei

T7 = {"version": "etf_intelligence_v1", "max_reasons": 2, "max_events": 2,
      "event_fields": {"name": ["event_name", "name"],
                       "interpretation": ["market_perception.interpretation"],
                       "alternative_explanation": ["market_perception.alternative_explanation", "strongest_counter_case"],
                       "invalidation": ["market_perception.invalidation", "invalidation"],
                       "required_confirmation": ["market_perception.required_confirmation", "required_confirmation"],
                       "consensus": ["pre_release_consensus", "consensus", "forecast"],
                       "consensus_source": ["pre_release_consensus_source", "consensus_source"],
                       "beneficiaries": ["beneficiaries"]},
      "sector_impact_views": {"favoured_or_resilient": "FAVOURED", "adverse": "ADVERSE",
                              "high_dispersion": "HIGH_DISPERSION"},
      "usmi_trigger_keys": ["relief_confirmation", "risk_off_escalation", "invalidation", "invalidation_conditions"],
      "usmi_sector_map": {"semiconductors": ["SMH", "SOXX"], "financials": ["XLF", "KRE"]},
      "benchmarks": {"market": "SPY", "sector_peer": "RSP",
                     "industry_parent": {"SMH": "XLK", "HACK": "XLK"},
                     "group_peer": {"Broad indices": "RSP", "Rates & credit": "AGG", "Commodities & dollar": None},
                     "absolute_read": ["SPY"],
                     "derived": {"SPXS": {"underlying": "SPY", "sign": -1}, "TQQQ": {"underlying": "QQQ", "sign": 1}},
                     "no_read": {"VXX": "volatility product: no relative-performance read"}}}
CONFIG = {"rotation": {"sectors": ["XLK", "XLP"], "industries": ["SMH"], "benchmark": "SPY"},
          "universe": [{"group": "Broad indices", "tickers": ["SPY", "QQQ", "RSP"]},
                       {"group": "SPDR sectors", "tickers": ["XLK", "XLP"]},
                       {"group": "Industries & themes", "tickers": ["SMH", "HACK"]},
                       {"group": "Rates & credit", "tickers": ["TLT", "AGG"]},
                       {"group": "Commodities & dollar", "tickers": ["GLD"]},
                       {"group": "Volatility products", "tickers": ["VXX"]},
                       {"group": "Leveraged & inverse", "tickers": ["SPXS", "TQQQ"]}],
          "day_story": {"driver_horizon": "5", "flow_windows": {"day": "1", "short": "5", "long": "20"}},
          "opportunity": {"relative_band_pp": {"1": 0.1, "5": 0.25, "20": 0.5}},
          "etf_intelligence": T7}


def _m(r1, r5, r20, status="FRESH"):
    return {"metrics": {"status": status, "ret_1d": r1, "ret_5d": r5, "ret_20d": r20}}


METRICS = {"SPY": _m(0.1, 1.0, 2.0), "RSP": _m(0.0, 0.5, 1.0), "QQQ": _m(0.3, 2.0, 3.0), "XLK": _m(0.2, 0.0, 1.0),
           "XLP": _m(0.0, 2.0, 2.5), "SMH": _m(0.5, 3.0, 4.0), "HACK": _m(0.1, -1.0, 0.0), "TLT": _m(0.2, 2.0, 1.0),
           "AGG": _m(0.1, 0.5, 0.5), "GLD": _m(0.4, 3.0, 5.0), "VXX": _m(-1.0, -5.0, -9.0),
           "SPXS": _m(-0.3, -3.0, -6.0), "TQQQ": _m(0.9, 6.0, 9.0)}

EVENTS_DOC = {
    "sector_impacts": {"favoured_or_resilient": [{"sector": "Staples", "etfs": ["XLP"], "condition": "if growth fear"}],
                       "adverse": [{"sector": "Chips", "etfs": ["SMH", "XLK"], "condition": "if yields rise"}],
                       "high_dispersion": [{"sector": "Tech", "etfs": ["XLK"], "condition": "AI vs rates"}],
                       "something_new": [{"sector": "X", "etfs": ["XLE"], "condition": "?"}]},
    "counter_case": {"summary": "Growth stays resilient.", "reversal_or_neutralisation_conditions": ["Orders stabilise"]},
}
EVENTS = [  # already ordered latest first, as build_intel orders them
    {"event_name": "CPI", "forecast": "0.3%", "consensus_source": "Reuters poll",
     "market_perception": {"interpretation": "disinflation read", "alternative_explanation": "weak demand",
                           "invalidation": "yields rise", "required_confirmation": ["QQQ holds"]},
     "beneficiaries": ["Growth equities if yields fall"],
     "conditional_etf_cases": [{"instrument": "QQQ", "bullish": "tech holds", "bearish": "tech fails", "wait": "confirm"}]},
    {"name": "Claims", "pre_release_consensus": "210k", "strongest_counter_case": "seasonal noise"},
    {"event_name": "Old event", "market_perception": {"interpretation": "too old to show"}},
]
USMI = {"risk_off_transmission_score": {"current_score": None, "components": {}},
        "forward_triggers": {"relief_confirmation": ["VIX below 18"], "risk_off_escalation": ["10Y above 5.05"],
                             "invalidation": ["broad accumulation"], "invalidation_conditions": "Russell reverses",
                             "bullish_upgrade": {"x": 1}},
        "leadership": {"counterevidence": "['Staples +0.2 while tech -2.0', 'HY OAS 3.23 not a breakdown']",
                       "leadership_invalidation": "SOX outperformance and 10Y below 5.05"},
        "options_monetisation": {"sector_routing": {"semiconductors": "LONG_PUTS_WATCH_ONLY",
                                                    "financials": "WATCH_NOT_EXECUTABLE",
                                                    "metals_miners": "LONG_CALLS_PAUSED"}}}


def _story(t, label, side="CALL"):
    return {"ticker": t, "name": t, "kind": "sector", "flow": {"label": label, "text": f"{t} rel", "relative_pp": {}},
            "volume": {"ratio": 1.1}, "footprint": {}, "drivers": [], "published": [], "live": [],
            "trade": {"side": side, "trigger": {"name": "sma20", "level": 1.0}, "invalidation": {"name": "sma50", "level": 2.0}}}


def _payload(intel_extra=None):
    intel = {"packet": {"sector_lead": ["QQQ"], "sector_avoid": ["TLT"]}}
    intel.update(intel_extra or {})
    return {"as_of_session": "2026-11-19", "built_at_utc": "2026-11-19T23:42:49+00:00", "build": {"kind": "EVENING"},
            "session_plan": {"next_session": "2026-11-20"}, "intel": intel, "rotation": {"packet": {"bias": {}}},
            "decision_points": {"calendar": []}, "etfs": METRICS,
            "external": {"event_payload": {"name": "events", "status": "OK", "as_of": "2026-11-19T23:35:00+00:00"},
                         "us_money_index": {"name": "usmi", "status": "OK", "as_of": "2026-11-18T18:57:43+00:00"}},
            "day_story": {"stories": [_story("XLK", "OUTFLOW", "PUT"), _story("XLP", "INFLOW"), _story("SMH", "INFLOW")]}}


# --- T7a: event file -----------------------------------------------------------------------------------------------

def test_the_event_reader_takes_the_first_alias_present_and_records_which_field_it_used():
    out = ei.event_intelligence(EVENTS_DOC, EVENTS, T7)
    cpi, claims = out["events"]
    assert cpi["name"] == "CPI" and cpi["consensus"] == "0.3%" and cpi["fields_used"]["consensus"] == "forecast"
    assert claims["name"] == "Claims" and claims["fields_used"]["name"] == "name"
    assert claims["consensus"] == "210k" and claims["fields_used"]["consensus"] == "pre_release_consensus"
    assert claims["alternative_explanation"] == "seasonal noise"
    assert out["events_total"] == 3 and len(out["events"]) == 2  # max_events from config


def test_a_missing_perception_part_is_missing_never_blank_or_neutral():
    claims = ei.event_intelligence(EVENTS_DOC, EVENTS, T7)["events"][1]
    assert claims["interpretation"] == "MISSING" and claims["invalidation"] == "MISSING"
    assert claims["consensus_source"] == "MISSING" and claims["fields_used"]["interpretation"] is None


def test_every_event_item_is_labelled_llm_with_news():
    out = ei.event_intelligence(EVENTS_DOC, EVENTS, T7)
    assert out["source"] == "LLM_WITH_NEWS" and all(e["source"] == "LLM_WITH_NEWS" for e in out["events"])


def test_sector_impacts_map_each_named_etf_to_favoured_adverse_or_high_dispersion_and_unknown_groups_are_listed():
    out = ei.event_intelligence(EVENTS_DOC, EVENTS, T7)
    assert [v["view"] for v in out["sector_impacts"]["XLK"]] == ["ADVERSE", "HIGH_DISPERSION"]
    assert out["sector_impacts"]["XLP"][0] == {"view": "FAVOURED", "sector": "Staples", "condition": "if growth fear",
                                                "source": "LLM_WITH_NEWS"}
    assert out["unmapped_impact_groups"] == ["something_new"] and "XLE" not in out["sector_impacts"]


def test_conditional_etf_cases_and_the_counter_case_are_carried():
    out = ei.event_intelligence(EVENTS_DOC, EVENTS, T7)
    assert out["etf_cases"]["QQQ"]["bearish"] == "tech fails" and out["etf_cases"]["QQQ"]["event"] == "CPI"
    assert out["counter_case"] == {"summary": "Growth stays resilient.", "reversal_conditions": ["Orders stabilise"]}


# --- T7b: US Money Index -------------------------------------------------------------------------------------------

def test_the_empty_money_index_score_is_missing_with_its_reason_never_zero():
    out = ei.usmi_intelligence(USMI, T7)
    assert out["score"] == "MISSING" and "no current score" in out["score_note"]


def test_the_stringified_counter_evidence_is_parsed_into_items():
    out = ei.usmi_intelligence(USMI, T7)
    assert out["counterevidence"] == ["Staples +0.2 while tech -2.0", "HY OAS 3.23 not a breakdown"]
    assert out["leadership_invalidation"] == "SOX outperformance and 10Y below 5.05"


def test_a_text_list_followed_by_more_text_keeps_both_the_items_and_the_trailing_text():
    # the rev 91 file: "['a', 'b']; 17NOV NVDA ... | REV91: ..." (the list as text, then more evidence)
    doc = dict(USMI, leadership={"counterevidence": "['first item', 'second; with a semicolon'] ; later note | REV91: more"})
    out = ei.usmi_intelligence(doc, T7)
    assert out["counterevidence"] == ["first item", "second; with a semicolon", "later note | REV91: more"]


def test_only_the_configured_triggers_are_carried():
    out = ei.usmi_intelligence(USMI, T7)
    assert set(out["triggers"]) == {"relief_confirmation", "risk_off_escalation", "invalidation", "invalidation_conditions"}
    assert out["triggers"]["risk_off_escalation"] == ["10Y above 5.05"]


def test_sector_routing_reaches_its_etfs_and_an_unmapped_sector_is_listed_not_dropped():
    out = ei.usmi_intelligence(USMI, T7)
    assert out["routing"]["SOXX"] == [{"sector": "semiconductors", "routing": "LONG_PUTS_WATCH_ONLY", "source": "LLM_WITH_NEWS"}]
    assert out["routing"]["KRE"][0]["routing"] == "WATCH_NOT_EXECUTABLE"
    assert out["unmapped_routing_sectors"] == ["metals_miners"]


# --- T7a/b in the per-ETF projection -------------------------------------------------------------------------------

def test_each_etf_carries_its_event_view_its_case_and_its_routing_with_source_and_as_of():
    intel = {"event_intelligence": ei.event_intelligence(EVENTS_DOC, EVENTS, T7),
             "usmi_intelligence": ei.usmi_intelligence(USMI, T7)}
    out = ei.project(_payload(intel), CONFIG)
    xlk, smh, qqq, xlp = (out["etfs"][t] for t in ("XLK", "SMH", "QQQ", "XLP"))
    assert [v["view"] for v in xlk["event_sector_view"]] == ["ADVERSE", "HIGH_DISPERSION"]
    assert xlp["event_sector_view"][0]["view"] == "FAVOURED"
    assert out["etfs"]["TLT"]["event_sector_view"] == "NOT_NAMED"
    assert qqq["event_etf_case"]["bullish"] == "tech holds" and xlk["event_etf_case"] is None
    assert smh["usmi_routing"][0]["routing"] == "LONG_PUTS_WATCH_ONLY" and xlk["usmi_routing"] == "NOT_NAMED"
    assert out["event_intelligence"]["as_of"] == "2026-11-19T23:35:00+00:00"
    assert out["usmi_intelligence"]["as_of"] == "2026-11-18T18:57:43+00:00"


def test_without_the_event_or_money_index_files_the_items_are_missing_not_neutral():
    out = ei.project(_payload(), CONFIG)
    assert out["etfs"]["XLK"]["event_sector_view"] == "MISSING" and out["etfs"]["XLK"]["usmi_routing"] == "MISSING"
    assert out["event_intelligence"]["status"] == "MISSING" and out["usmi_intelligence"]["status"] == "MISSING"


# --- T7c: peer benchmarks ------------------------------------------------------------------------------------------

def test_sectors_compare_with_the_equal_weight_market_and_industries_with_their_parent_sector():
    out = ei.project(_payload(), CONFIG)
    xlk, smh = out["etfs"]["XLK"]["benchmarks"], out["etfs"]["SMH"]["benchmarks"]
    assert xlk["market"]["reference"] == "SPY" and xlk["peer"]["reference"] == "RSP"
    assert smh["peer"]["reference"] == "XLK"
    assert smh["peer"]["relative_pp"] == {"1": 0.3, "5": 3.0, "20": 3.0}  # SMH minus XLK, same windows
    assert smh["peer"]["source"] == "MEASURED"


def test_a_split_is_reported_when_the_market_and_peer_references_give_different_labels():
    out = ei.project(_payload(), CONFIG)
    xlk = out["etfs"]["XLK"]["benchmarks"]  # XLK vs SPY: -1.0 over 5 -> OUTFLOW; vs RSP: -0.5 -> OUTFLOW
    assert xlk["split"] == "SAME"
    tlt = out["etfs"]["TLT"]["benchmarks"]  # TLT vs SPY: +1.0 over 5, -1.0 over 20 -> TURNING_IN; vs AGG: +1.5, +0.5 -> INFLOW
    assert tlt["market"]["label"] == "TURNING_IN" and tlt["peer"]["label"] == "INFLOW" and tlt["split"] == "SPLIT"


def test_a_stale_leg_makes_the_read_missing_and_names_its_last_session_never_a_cross_date_comparison():
    # 19 Nov 2026: RSP's last bar in the price store was 20 Aug; XLK to 19 Nov against RSP to 20 Aug is meaningless
    payload = _payload()
    payload["etfs"] = dict(METRICS, RSP={"metrics": {"status": "STALE", "last_session": "2026-08-20",
                                                     "ret_1d": 0.0, "ret_5d": 0.5, "ret_20d": 1.0}},
                           AGG={"metrics": {"status": "STALE", "last_session": "2026-05-15",
                                            "ret_1d": 0.1, "ret_5d": 0.5, "ret_20d": 0.5}})
    out = ei.project(payload, CONFIG)
    peer = out["etfs"]["XLK"]["benchmarks"]["peer"]
    assert peer["label"] == "MISSING" and peer["relative_pp"] is None
    assert "RSP" in peer["text"] and "2026-08-20" in peer["text"]
    assert out["etfs"]["XLK"]["benchmarks"]["split"] == "MISSING"
    agg = out["etfs"]["AGG"]
    assert agg["stance_measured"] == "MISSING" and "2026-05-15" in agg["missing_reason"]
    assert out["etfs"]["TLT"]["benchmarks"]["market"]["label"] == "TURNING_IN"  # the fresh leg is unaffected


def _ew_config():
    cfg = json.loads(json.dumps(CONFIG))
    b = cfg["etf_intelligence"]["benchmarks"]
    b["sector_peer"] = "EW_SECTORS"
    b["baskets"] = {"EW_SECTORS": {"label": "the equal-weight 11 sectors", "members": ["XLK", "XLP"]}}
    return cfg


def test_sectors_can_compare_with_the_equal_weight_average_of_the_sector_etfs():
    # ACK 20 Nov 2026: RSP is stale in the price store; the sector peer is the equal-weight average of the 11 sectors
    peer = ei.project(_payload(), _ew_config())["etfs"]["XLK"]["benchmarks"]["peer"]
    assert peer["reference"] == "EW_SECTORS" and peer["source"] == "MEASURED"
    assert peer["relative_pp"] == {"1": 0.1, "5": -1.0, "20": -0.75}  # XLK minus the mean of XLK and XLP
    assert peer["label"] == "OUTFLOW" and "equal-weight 11 sectors" in peer["text"]
    assert "the benchmark" not in peer["text"]


def test_a_broad_index_can_use_the_sector_basket_as_its_peer():
    # ACK 20 Nov 2026: broad indices and factors also compare with the equal-weight 11 sectors (RSP is stale)
    cfg = _ew_config()
    cfg["etf_intelligence"]["benchmarks"]["group_peer"]["Broad indices"] = "EW_SECTORS"
    qqq = ei.project(_payload(), cfg)["etfs"]["QQQ"]["benchmarks"]
    assert qqq["peer"]["reference"] == "EW_SECTORS" and qqq["peer"]["relative_pp"] == {"1": 0.2, "5": 1.0, "20": 1.25}
    assert qqq["peer"]["label"] == "INFLOW" and qqq["split"] == "SAME"


def test_the_basket_needs_every_member_fresh_and_names_a_stale_one():
    payload = _payload()
    payload["etfs"] = dict(METRICS, XLP={"metrics": {"status": "STALE", "last_session": "2026-05-15",
                                                     "ret_1d": 0.0, "ret_5d": 2.0, "ret_20d": 2.5}})
    peer = ei.project(payload, _ew_config())["etfs"]["XLK"]["benchmarks"]["peer"]
    assert peer["label"] == "MISSING" and "XLP" in peer["text"] and "2026-05-15" in peer["text"]


def test_an_etf_without_a_peer_says_so():
    gld = ei.project(_payload(), CONFIG)["etfs"]["GLD"]["benchmarks"]
    assert gld["peer"]["label"] == "NO_PEER" and gld["split"] == "NO_PEER"


# --- T7d: every universe ETF ---------------------------------------------------------------------------------------

def test_every_board_universe_etf_is_in_the_projection_and_the_26_keep_their_day_story_read():
    out = ei.project(_payload(), CONFIG)
    assert set(out["etfs"]) == {"XLK", "XLP", "SMH", "SPY", "QQQ", "RSP", "HACK", "TLT", "AGG", "GLD", "VXX", "SPXS", "TQQQ"}
    assert out["etfs"]["XLK"]["coverage"] == "DAY_STORY" and out["etfs"]["XLK"]["stance_measured"] == "AVOID"
    assert out["etfs"]["XLK"]["kill_level"] == {"name": "sma50", "level": 2.0}


def test_a_universe_etf_gets_a_measured_read_against_spy_and_no_trade_idea():
    tlt = ei.project(_payload(), CONFIG)["etfs"]["TLT"]
    assert tlt["coverage"] == "UNIVERSE_READ" and tlt["stance_measured"] == "LEAN_IN"
    assert tlt["relative_performance"]["label"] == "TURNING_IN" and "SPY" in tlt["relative_performance"]["text"]
    assert tlt["stance_packet"] == "AVOID" and tlt["stance_agreement"] == "DISAGREE"
    assert tlt["kill_level"] is None and tlt["record"] is None
    kinds = {s["kind"]: s for s in tlt["decision_scenarios"]}
    assert kinds["STAND_ASIDE"]["applies"] is True and "no trade idea" in kinds["STAND_ASIDE"]["text"]
    assert not any(s["applies"] for k, s in kinds.items() if k != "STAND_ASIDE")


def test_the_market_reference_itself_gets_an_absolute_read_not_a_zero_against_itself():
    spy = ei.project(_payload(), CONFIG)["etfs"]["SPY"]
    assert spy["coverage"] == "ABSOLUTE_READ" and spy["relative_performance"]["label"] == "INFLOW"
    assert "absolute" in spy["relative_performance"]["text"].lower()


def test_an_inverse_etf_takes_its_underlyings_read_flipped_and_a_leveraged_one_unflipped():
    out = ei.project(_payload(), CONFIG)
    spxs, tqqq = out["etfs"]["SPXS"], out["etfs"]["TQQQ"]
    assert spxs["coverage"] == "DERIVED" and spxs["stance_measured"] == "AVOID" and "SPY" in spxs["derived_from"]
    assert tqqq["stance_measured"] == out["etfs"]["QQQ"]["stance_measured"] == "LEAN_IN"


def test_a_volatility_product_has_no_read_and_says_why():
    vxx = ei.project(_payload(), CONFIG)["etfs"]["VXX"]
    assert vxx["coverage"] == "NO_READ" and vxx["stance_measured"] == "MISSING"
    assert vxx["missing_reason"] == "volatility product: no relative-performance read"


def test_a_universe_etf_without_fresh_metrics_is_missing_with_its_reason():
    payload = _payload()
    payload["etfs"] = dict(METRICS, AGG=_m(None, None, None, status="MISSING"))
    agg = ei.project(payload, CONFIG)["etfs"]["AGG"]
    assert agg["stance_measured"] == "MISSING" and "AGG" in agg["missing_reason"]


def test_the_universe_reads_never_call_relative_performance_a_fund_flow():
    text = json.dumps({t: e["relative_performance"] for t, e in ei.project(_payload(), CONFIG)["etfs"].items()
                       if e.get("relative_performance")}).lower()
    assert "fund flow" not in text and "money" not in text


def test_the_live_board_config_carries_the_t7_sections():
    cfg = json.loads((Path(ei.__file__).parent / "config" / "macro_board_config_v1.json").read_text(encoding="utf-8"))
    t7 = cfg["etf_intelligence"]
    for key in ("event_fields", "max_events", "sector_impact_views", "usmi_trigger_keys", "usmi_sector_map", "benchmarks"):
        assert key in t7, key
    universe = {t for g in cfg["universe"] for t in g["tickers"]}
    b = t7["benchmarks"]
    groups = {g["group"] for g in cfg["universe"]}
    assert groups <= set(b["group_peer"]) | {"SPDR sectors", "Industries & themes", "Leveraged & inverse", "Volatility products"}
    industries = next(g["tickers"] for g in cfg["universe"] if g["group"] == "Industries & themes")
    assert set(industries) <= set(b["industry_parent"])
    leveraged = next(g["tickers"] for g in cfg["universe"] if g["group"] == "Leveraged & inverse")
    assert set(leveraged) <= set(b["derived"]) | set(b["no_read"])
    vol = next(g["tickers"] for g in cfg["universe"] if g["group"] == "Volatility products")
    assert set(vol) <= set(b["no_read"])
    assert all(u["underlying"] in universe for u in b["derived"].values())
    assert set(b["industry_parent"].values()) <= universe
    baskets = b.get("baskets") or {}
    assert {p for p in b["group_peer"].values() if p} <= universe | set(baskets)
    # ACK 20 Nov 2026: sectors, broad indices and factors compare with the equal-weight 11 sectors
    assert b["sector_peer"] == b["group_peer"]["Broad indices"] == b["group_peer"]["Factors"] == "EW_SECTORS"
    assert b["sector_peer"] in universe or b["sector_peer"] in baskets
    for basket in baskets.values():
        assert set(basket["members"]) <= universe and basket["label"]
    if b["sector_peer"] in baskets:  # ACK 20 Nov 2026: the equal-weight average of the 11 sector ETFs
        assert baskets[b["sector_peer"]]["members"] == cfg["rotation"]["sectors"]
