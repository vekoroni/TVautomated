"""Business rules for the measured sheet (ACK 10 Oct 2026).

The runner's board build writes one page of facts AVSHUNTER measured itself, with instructions, for ACK
to paste into ChatGPT before asking for the US Money Index, the event payload and the news enrichment.
ChatGPT then adds only the news layer (geopolitics, Hormuz, fund flows, unscheduled events, candidate
tickers) and cannot contradict the local numbers: one owner per fact. The sheet carries measured facts
only - never an LLM's published numbers - and states what is missing. No network.
"""

from __future__ import annotations

from macro_board import measured_sheet as ms

CFG = {
    "title": "AVSHUNTER measured sheet",
    "instructions": [
        "Use every number in this sheet exactly as given; do not restate, round or replace it.",
        "In the US Money Index, set the measured components from the table below and score only {llm_components}.",
        "Report the total as measured points plus your {llm_weight} news points over 100.",
    ],
    "needed_from_you": ["Geopolitics and Hormuz with source and time.", "Weekly fund flows with source and week."],
    "release_sessions_ahead": 5,
    "focus": ["SPY", "QQQ"],
}


def _payload():
    return {
        "as_of_session": "2026-10-09", "built_at_utc": "2026-10-10T11:45:57+00:00",
        "build": {"kind": "EVENING", "source": "runner", "run_session": "PostClose"},
        "conditions": {"meta": [{"key": "yields", "label": "10Y yield", "measured": "20-session change in 10Y"}],
                       "current": {"yields": "RISING"}, "current_values": {"yields": 5.28}},
        "money_index": {
            "reading": {"score": 54.9, "band": "TRANSITION", "missing": [], "measured_weight": 76,
                        "components": [{"key": "rates", "label": "10Y yield (20-session change)", "unit": "bp", "value": 33.0,
                                        "percentile": 0.9365, "points": 9.61, "weight": 10.0, "published_key": "rates_confirmation"},
                                       {"key": "oil", "label": "Oil (USO, 20-session change)", "unit": "%", "value": -4.42,
                                        "percentile": 0.1865, "points": 0.0, "weight": 12.0, "published_key": "oil_breakout"}]},
            "per_etf": {"SPY": {"band_evidence": {"5": {"lean": "NO_CLEAR_LEAN", "analog": {"mean_pct": 0.42, "n_eff": 83},
                                                        "base": {"mean_pct": 0.21}}}}},
            "settings": {"published_only": [{"key": "geopolitical_escalation", "label": "Geopolitical escalation", "weight": 12},
                                            {"key": "hormuz_impairment", "label": "Hormuz impairment", "weight": 12}]},
        },
        "review": {"instruments": {"SPY": {"label": "ACCEPTED", "direction": "UP", "gap_pct": 0.3, "close_pct": 0.6},
                                   "TLT": {"label": "ABSORBED", "direction": "NONE", "gap_pct": -0.1, "close_pct": -0.2}}},
        "opportunity": {"leadership": {"windows": {"20": {"leader": "QQQ", "qqq_minus_spy_pp": 3.2}},
                                       "breadth": {"state": "CONCENTRATED", "rsp_minus_spy_20d_pp": -2.72}}},
        "session_plan": {"instruments": {"SPY": {"reference": 778.57, "basis": "CLOSE", "daily_move_pct": 0.63, "implied_move_pct": 0.47,
                                                 "up": {"trigger": {"label": "252d high", "level": 781.62}},
                                                 "down": {"trigger": {"label": "GEX flip (2026-10-05)", "level": 776.5}}}}},
        "decision_points": {"calendar": [{"date": "2026-10-14", "sessions_ahead": 3, "kind": "RELEASE", "name": "CPI", "time_et": "08:30"},
                                         {"date": "2026-10-28", "sessions_ahead": 13, "kind": "FOMC", "name": "FOMC rate decision", "time_et": "14:00"}]},
        "overnight": {"status": "STALE", "us_reference_session": "2026-10-08",
                      "groups": {"us_futures": [{"name": "S&P 500 e-mini", "change_pct": 0.06, "state": "OK"}]},
                      "releases_today": [{"name": "Jobless claims", "time_et": "08:30", "state": "RELEASED", "value": 197000.0, "prior": 199000.0}]},
        "intel": {"usmi": {"score": 83, "summary": "LLM SUMMARY TEXT"}, "enrichment": {"summary": "LLM NEWS TEXT"},
                  "vix_engine": [{"Date": "2026-10-08", "VIX_Direct": 15.41, "VIX_Structure": "CONTANGO", "VIX3M_Proxy": 18.08}]},
    }


def test_the_sheet_names_the_close_it_describes_the_build_and_when_it_was_measured():
    text = ms.render(_payload(), CFG)
    assert text.startswith("# AVSHUNTER measured sheet")
    assert "2026-10-09" in text and "EVENING" in text and "2026-10-10T11:45:57+00:00" in text


def test_the_instructions_are_included_and_map_each_measured_component_to_its_published_key():
    text = ms.render(_payload(), CFG)
    assert "Use every number in this sheet exactly as given" in text
    assert "score only geopolitical_escalation, hormuz_impairment" in text and "your 24 news points" in text
    assert "rates_confirmation" in text and "oil_breakout" in text
    assert "Weekly fund flows with source and week." in text


def test_each_measured_component_carries_value_percentile_and_points_and_missing_is_written_missing():
    p = _payload()
    text = ms.render(p, CFG)
    assert "| 10Y yield (20-session change) | rates_confirmation | +33 bp | 94th | 9.6 / 10 |" in text
    assert "Measured total: 54.9 / 100 over 76 weight (TRANSITION)" in text
    p["money_index"]["reading"].update({"score": None, "band": "MISSING", "missing": ["oil"]})
    p["money_index"]["reading"]["components"][1].update({"value": None, "percentile": None, "points": None})
    gap = ms.render(p, CFG)
    assert "| Oil (USO, 20-session change) | oil_breakout | MISSING | MISSING | MISSING / 12 |" in gap
    assert "Measured total: MISSING (missing: oil)" in gap


def test_no_published_llm_number_or_text_is_carried_into_the_sheet():
    text = ms.render(_payload(), CFG)
    assert "LLM SUMMARY TEXT" not in text and "LLM NEWS TEXT" not in text
    assert "83/100" not in text and "83 / 100" not in text and "published" not in text.lower().replace("published key", "")


def test_an_overnight_capture_from_another_close_is_reported_as_not_captured():
    text = ms.render(_payload(), CFG)
    assert "Overnight: not captured after the 2026-10-09 close" in text and "S&P 500 e-mini" not in text
    p = _payload()
    p["overnight"].update({"status": "FRESH", "us_reference_session": "2026-10-09"})
    fresh = ms.render(p, CFG)
    assert "S&P 500 e-mini" in fresh and "+0.06%" in fresh and "Jobless claims" in fresh and "197000" in fresh


def test_the_reaction_levels_and_releases_ahead_are_carried():
    text = ms.render(_payload(), CFG)
    assert "| SPY | accepted up | +0.30% | +0.60% |" in text and "| TLT | absorbed | -0.10% | -0.20% |" in text
    assert "SPY 778.57 (close): above 252d high 781.62, below GEX flip (2026-10-05) 776.50" in text
    assert "CPI" in text and "FOMC" not in text                                  # 13 sessions away, beyond 5
    assert "Breadth: CONCENTRATED" in text and "VIX 15.41" in text


def test_the_same_payload_gives_the_same_sheet():
    assert ms.render(_payload(), CFG) == ms.render(_payload(), CFG)


def test_the_real_instructions_keep_chatgpts_money_index_valid_under_the_pipeline_contract():
    # contracts/us_money_index_contract.py: weights total 100, score <= weight, current_score equals
    # current_state.risk_off_transmission_score and reconciles to the component total within 1 point.
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "macro_board_config_v1.json").read_text(encoding="utf-8"))
    mi = cfg["money_index"]
    assert sum(c["weight"] for c in mi["components"]) + sum(c["weight"] for c in mi["published_only"]) == 100
    text = " ".join(cfg["measured_sheet"]["instructions"])
    assert "current_state.risk_off_transmission_score" in text and "risk_off_transmission_score.current_score" in text
    assert "sum of all nine component scores" in text
    for c in mi["components"]:
        assert c["published_key"] in ms.render({"money_index": {"reading": {"components": [c]}, "settings": mi}}, cfg["measured_sheet"])


def test_percentiles_read_as_ordinals_and_conditions_carry_states_with_explicit_rates_not_bare_numbers():
    p = _payload()
    p["money_index"]["reading"]["components"][0]["percentile"] = 0.9087
    p["conditions"]["meta"].append({"key": "curve_level", "label": "Curve level"})
    p["conditions"]["current"]["curve_level"] = "STEEP"
    p["conditions"]["current_values"]["curve_level"] = 0.51
    text = ms.render(p, CFG)
    assert "| 91st |" in text and "91th" not in text
    assert "Conditions (20-session readings): 10Y yield RISING; Curve level STEEP." in text
    assert "Rates: 10Y 5.28%; 2s10s +0.51 pts (FRED, publication-lagged)." in text
    assert "lean no clear lean" not in text and "no clear lean" in text



def test_scheduled_releases_measured_locally_carry_their_surprise_basis_and_event_day_history():
    p = _payload()
    p["scheduled_events"] = {"released": [{"name": "Jobless claims", "series_id": "ICSA", "release_id": 180, "time_et": "08:30", "actual": 197000.0,
                  "previous": 199000.0, "observation_date": "2026-10-03", "revision_of_previous": 1000.0,
                  "previous_as_first_known": 198000.0, "unit": "claims", "change": -2000.0, "status": "RELEASED",
                  "surprise": {"label": "IN_LINE_WITH_OWN_TREND", "z": -0.3,
                               "basis": "change vs its own past 36 changes; not a consensus surprise"},
                  "event_day": {"SPY": {"ratio": 1.1, "n": 200}, "TLT": {"ratio": 1.3, "n": 200}}}],
                             "upcoming": [{"name": "PPI", "date": "2026-10-15", "time_et": "08:30", "sessions_ahead": 4,
                                           "event_day": {"SPY": {"ratio": 1.2, "n": 58}}}]}
    text = ms.render(p, CFG)
    assert "Released 08:30 ET: Jobless claims 197000 (observation 2026-10-03; change -2000 claims; previous 199000" in text
    assert "revised +1000 since first published" in text
    assert "in line with own trend (z -0.3), not a consensus surprise" in text
    assert "SPY moves 1.1x a normal day on its release days (200 days)" in text
    assert "2026-10-15 08:30 PPI (SPY 1.2x a normal day)" in text
    assert "CPI" not in text                                                     # the board calendar is replaced, not merged
