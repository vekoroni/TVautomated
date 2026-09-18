"""Signal tickets and their forward track record (ACK 17 Sep 2026) — decision support, measured by return only.

Rules:
  S1 a ticket is considered only from the morning Lab book (pipeline mode MORNING_VALIDATION) for a CALL/PUT row whose
     final action is not blocked, with a morning gate row, an evening valuation with the same direction, intact price
     history, a forecast, and stop/target/hold defined; anything missing is a named rejection, never a default;
  S2 the thesis is judged where it stands at issue: price or today's range through the stop is
     THESIS_INVALIDATED_INTRADAY; through the target is TARGET_ALREADY_REACHED; a move that has started is re-valued;
  S3 a delayed option quote is brought to issue: bid and ask shift by delta x (live spot - spot at quote time); a
     missing bar or delta leaves the quote unadjusted and flagged; quote age is recorded as a flag, never a gate;
  S4 rank, don't gate (R11; ACK 18 Sep 2026): hard exclusions are facts only — the contract must be priceable,
     carry an executable two-sided quote within the ticket spread limit and be holdable past the issue session; the
     cautious value must be present because it is the ranking key, but NO forecast threshold vetoes a candidate.
     OPTION-ONLY for the trial (the share spread estimate is floored at zero). Limit = adjusted mid, scored from the
     adjusted ask. The share valuation is recorded beside the ticket and never issues or vetoes one;
  S4b the contract must outlive the plan (backtest 17 Sep 2026: tickets held contracts covering a median 0.54 of
     their planned hold, the expiry cap was the most common exit, and contracts with 10 or fewer days to expiry
     returned -75.6%): days to expiry at least the governed cover multiple of the planned hold in calendar days,
     never below the governed floor, and moneyness no further out of the money than the governed limit;
  S5 context (O4 stance, O2 availability, H9R event) is recorded and never changes eligibility or rank; candidates
     rank by the option's cautious value and the top N per session (governed daily cap) are issued; every candidate
     below the cap is recorded with its rank, so the denominator is kept;
  S6 exit: first of issue-session close beyond the stop; a later session touching stop or target (both = stop); the
     planned hold; for options the last usable session. Options exit at the end-of-day bid (missing =
     MARK_UNAVAILABLE); shares at the stop level or worse open, the target level, or the close, less half the spread;
  S7 the track record reaches EVIDENCE_SUPPORTS only with the minimum closed signals and issue sessions and a lower
     interval bound (clustered by issue session) above zero;
  S8 issuing and scoring are idempotent; the report shows the signal track record.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import sqlite3

import pandas as pd
import pytest

from avshunter.c12_outcome import service, signal_service
from avshunter.c12_outcome import signals as sig
from avshunter.c12_outcome.adapters import intraday, storage
from avshunter.c12_outcome.model import Bar
from avshunter.config import ConfigRegistry
from avshunter.config.adapters import load_documents, load_lock

EVIDENCE = date(2026, 9, 17)
ISSUE = date(2026, 9, 18)
NOW = datetime(2026, 9, 18, 14, 50, tzinfo=timezone.utc)
SYMBOL = "ABC261016C00100000"


def settings(**overrides):
    base = dict(signal_version="SIG-V1", blocked_final_actions=("BLOCK", "CONTRACT_REPAIR"),
                required_price_history_state="INTACT", contract_exit_buffer=2,
                contract_multiplier=100.0, o4_extreme_quantile=0.2, min_closed_signals=6, min_issue_sessions=3,
                interval_z=1.645, min_dte_cover=1.5, min_contract_dte_days=21, max_out_of_the_money=0.05,
                max_entry_spread_fraction=0.10, max_tickets_per_session=5)
    base.update(overrides)
    return sig.SignalSettings(**base)


def book_row(**overrides):
    row = dict(ticker="ABC", pipeline_mode="MORNING_VALIDATION", final_action="MANUAL_REVIEW", final_direction="CALL",
               morning_selected_contract_symbol=SYMBOL)
    row.update(overrides)
    return row


def gate_row(**overrides):
    row = dict(ticker="ABC", live_price=102.0, live_high=103.0, live_low=99.0, live_fetched_at="2026-09-18T14:45:00Z",
               live_contract_symbol=SYMBOL, live_contract_bid=4.8, live_contract_ask=5.0, live_contract_delta=0.5,
               live_contract_iv=0.35, selected_quote_timestamp_utc="2026-09-18T14:30:00Z",
               execution_viability_state="EXECUTABLE_QUOTE")
    row.update(overrides)
    return row


def valuation_row(**overrides):
    row = dict(ticker="ABC", final_direction="CALL", contract_occ_symbol=SYMBOL, contract_iv=0.30, underlying_price=100.0,
               structural_target=110.0, target_spot=108.0, invalidation_spot=95.0, layer2__recommended_hold_days=5,
               l3_price_history_state="INTACT", l3_forward_realised_vol=0.30, l3_forward_realised_vol_raw=None,
               emp_share_spread_estimate=0.002, pcr_oi=0.5)
    row.update(overrides)
    return row


def revaluation(**overrides):
    out = dict(emp_path_quality_flag="OK", emp_expression_preference="OPTION", emp_path_r_cautious=0.12,
               emp_path_r_central=0.30, emp_path_r_upside=0.55, emp_path_p_target_first_central=0.4,
               emp_path_p_stop_first_central=0.3, emp_share_r_cautious=0.01, emp_share_r_central=0.02,
               emp_share_r_upside=0.04)
    out.update(overrides)
    return out


def last_usable(expiry: date) -> date:
    return date(2026, 10, 14)


def prepare(book=None, gate=None, valuation=None, spot=101.0):
    return sig.prepare(book_row(**(book or {})), gate_row(**(gate or {})), valuation_row(**(valuation or {})), spot,
                       settings(), issue_session=ISSUE, last_usable_for=last_usable, rate=0.045)


# --- S1 / S2 -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("book, gate, valuation, reason", [
    (dict(pipeline_mode="EOD"), {}, {}, "BOOK_NOT_MORNING_VALIDATED"),
    (dict(final_action="BLOCK"), {}, {}, "FINAL_ACTION_BLOCKED"),
    (dict(final_action="CONTRACT_REPAIR"), {}, {}, "FINAL_ACTION_BLOCKED"),
    (dict(final_direction="STRANGLE"), {}, {}, "DIRECTION_NOT_CALL_OR_PUT"),
    ({}, {}, dict(final_direction="PUT"), "DIRECTION_CHANGED_SINCE_VALUATION"),
    ({}, {}, dict(l3_price_history_state="BREAK_TRUNCATED"), "PRICE_HISTORY_NOT_INTACT"),
    ({}, {}, dict(structural_target=None, target_spot=None), "STOP_OR_TARGET_UNDEFINED"),
    ({}, {}, dict(layer2__recommended_hold_days=None), "HOLD_UNDEFINED"),
    ({}, dict(live_price=None), {}, "LIVE_PRICE_MISSING"),
    ({}, dict(live_low=94.5), {}, "THESIS_INVALIDATED_INTRADAY"),
    ({}, dict(live_price=94.0, live_low=93.0), {}, "THESIS_INVALIDATED_INTRADAY"),
    ({}, dict(live_high=110.5), {}, "TARGET_ALREADY_REACHED"),
    ({}, {}, dict(l3_forward_realised_vol=None), "FORECAST_UNAVAILABLE"),
])
def test_s1_s2_named_rejections(book, gate, valuation, reason):
    assert prepare(book, gate, valuation)[0] == reason


def test_s1_missing_gate_or_valuation():
    assert sig.prepare(book_row(), None, valuation_row(), None, settings(), issue_session=ISSUE,
                       last_usable_for=last_usable, rate=0.045)[0] == "MORNING_GATE_ROW_MISSING"
    assert sig.prepare(book_row(), gate_row(), None, None, settings(), issue_session=ISSUE,
                       last_usable_for=last_usable, rate=0.045)[0] == "VALUATION_MISSING"


@pytest.mark.parametrize("symbol, hold, reason", [
    ("ABC261016C00100000", 40, "CONTRACT_EXPIRES_BEFORE_PLAN"),     # 28 days vs 1.5 x 56 calendar days
    ("ABC260930C00100000", 5, "CONTRACT_DTE_BELOW_FLOOR"),          # 12 days, floor 21
    ("ABC261016C00130000", 5, "MONEYNESS_TOO_FAR_OUT_OF_THE_MONEY"),  # strike 130 vs spot 102
])
def test_s4b_contract_must_outlive_the_plan(symbol, hold, reason):
    result = sig.prepare(book_row(morning_selected_contract_symbol=symbol),
                         gate_row(live_contract_symbol=symbol),
                         valuation_row(contract_occ_symbol=symbol, layer2__recommended_hold_days=hold),
                         101.0, settings(), issue_session=ISSUE, last_usable_for=last_usable, rate=0.045)
    assert result[0] == reason


def test_s4b_contract_covering_the_plan_passes():
    reason, p = prepare(valuation=dict(layer2__recommended_hold_days=10))   # 28 days vs 1.5 x 14 = 21
    assert reason is None and p.option_executable


def test_s2_started_move_is_revalued_from_the_current_price():
    reason, p = prepare(gate=dict(live_price=106.0, live_high=107.0))
    assert reason is None and p.live_spot == 106.0 and p.path_inputs["spot"] == 106.0
    assert p.path_inputs["target"] == 110.0 and p.path_inputs["invalidation"] == 95.0
    assert p.path_inputs["dte"] == (date(2026, 10, 16) - ISSUE).days and p.path_inputs["strike"] == 100.0


# --- S3 ----------------------------------------------------------------------------------------------------------

def test_s3_delayed_quote_shifted_by_delta_and_flagged():
    reason, p = prepare(spot=101.0)                          # live 102, spot at quote 101, delta 0.5 -> +0.5
    assert reason is None and p.adjustment_state == "DELTA_ADJUSTED_TO_ISSUE"
    assert (p.bid, p.ask, p.shift) == pytest.approx((5.3, 5.5, 0.5))
    assert p.path_inputs["bid"] == pytest.approx(5.3) and p.path_inputs["ask"] == pytest.approx(5.5)
    assert p.quote_state == "QUOTE_CURRENT_SESSION" and p.quote_bid == 4.8


def test_s3_put_delta_moves_premium_the_other_way():
    put = "ABC261016P00100000"
    reason, p = prepare(book=dict(final_direction="PUT", morning_selected_contract_symbol=put),
                        gate=dict(live_contract_symbol=put, live_contract_delta=-0.4, live_high=103.0, live_low=97.0),
                        valuation=dict(final_direction="PUT", contract_occ_symbol=put, structural_target=90.0,
                                       invalidation_spot=105.0), spot=101.0)
    assert reason is None and p.shift == pytest.approx(-0.4) and p.ask == pytest.approx(4.6)


def test_s3_unadjusted_quotes_are_flagged_not_rejected():
    reason, p = prepare(spot=None)
    assert reason is None and p.adjustment_state == "NOT_ADJUSTED_BAR_MISSING" and p.ask == 5.0
    reason, p = prepare(gate=dict(live_contract_delta=None))
    assert reason is None and p.adjustment_state == "NOT_ADJUSTED_DELTA_MISSING"
    reason, p = prepare(gate=dict(selected_quote_timestamp_utc="2026-09-17T19:59:00Z"))
    assert reason is None and p.quote_state == "QUOTE_PRIOR_SESSION"


def test_s3_live_iv_missing_falls_back_to_evening_contract_iv():
    reason, p = prepare(gate=dict(live_contract_iv=None))
    assert reason is None and p.iv == 0.30 and p.iv_source == "EVENING_CONTRACT"


# --- S4 ----------------------------------------------------------------------------------------------------------

def test_s4_option_ticket_at_issue_premium():
    _, p = prepare(spot=101.0)
    reason, fields = sig.decide(p, revaluation(), settings())
    assert reason is None and fields["expression"] == "OPTION" and fields["contract_symbol"] == SYMBOL
    assert fields["limit_price"] == pytest.approx(5.4) and fields["scored_entry"] == pytest.approx(5.5)
    assert fields["reference_spot"] == 102.0 and fields["r_cautious"] == 0.12


@pytest.mark.parametrize("gate, reval, reason", [
    ({}, dict(emp_path_quality_flag="NO_MARKET"), "REVALUATION_NOT_OK:NO_MARKET"),
    ({}, dict(emp_path_r_cautious=None), "CAUTIOUS_UNAVAILABLE"),
    (dict(execution_viability_state="BLOCKED_WIDE_SPREAD"), {}, "OPTION_NOT_EXECUTABLE"),
    (dict(live_contract_bid=4.0, live_contract_ask=5.0), {}, "SPREAD_ABOVE_TICKET_MAXIMUM"),   # 22% of mid
])
def test_s4_factual_exclusions(gate, reval, reason):
    _, p = prepare(gate=gate)
    assert sig.decide(p, revaluation(**reval), settings())[0] == reason


@pytest.mark.parametrize("cautious", [-0.60, -0.05, 0.0, 0.12])
def test_s4_r11_no_forecast_vetoes_a_candidate(cautious):
    """Rank, don't gate: however poor the cautious value, a factually tradeable candidate is kept for ranking."""
    _, p = prepare(spot=101.0)
    reason, fields = sig.decide(p, revaluation(emp_path_r_cautious=cautious), settings())
    assert reason is None and fields["r_cautious"] == cautious


def test_s4_option_not_holdable_past_issue():
    _, p = sig.prepare(book_row(), gate_row(), valuation_row(), 101.0, settings(), issue_session=ISSUE,
                       last_usable_for=lambda expiry: ISSUE, rate=0.045)
    assert sig.decide(p, revaluation(), settings())[0] == "OPTION_NOT_EXECUTABLE"


def test_s4_option_only_share_values_recorded_never_decide():
    _, p = prepare(spot=101.0)
    for share in (dict(emp_expression_preference="SHARES", emp_share_r_cautious=0.50),
                  dict(emp_expression_preference="NEITHER", emp_share_r_cautious=-0.2),
                  dict(emp_expression_preference="PREFERENCE_UNAVAILABLE", emp_share_r_cautious=None)):
        reason, fields = sig.decide(p, revaluation(**share), settings())
        assert reason is None and fields["expression"] == "OPTION" and fields["r_cautious"] == 0.12
        assert fields["share_r_cautious"] == share["emp_share_r_cautious"]
        assert fields["value_model_preference"] == share["emp_expression_preference"]


# --- S5 ----------------------------------------------------------------------------------------------------------

def test_s5_daily_cap_issues_top_n_and_records_the_rest():
    _, p = prepare(spot=101.0)
    cautious = {"A1": 0.2, "A2": -0.1, "A3": 0.05, "A4": -0.4, "A5": 0.0, "A6": -0.2, "A7": 0.1}
    decided = [(t, dict(sig.decide(p, revaluation(emp_path_r_cautious=c), settings())[1])) for t, c in cautious.items()]
    ranked = sig.rank_tickets(decided, {}, settings(), run_id="r", evidence_session=EVIDENCE, issue_session=ISSUE,
                              h9r_tickers=set())
    issued, held_back = sig.apply_daily_cap(ranked, settings(max_tickets_per_session=5))
    assert [t.ticker for t in issued] == ["A1", "A7", "A3", "A5", "A2"]
    assert [(t.ticker, t.rank) for t in held_back] == [("A6", 6), ("A4", 7)]


def test_s5_context_recorded_never_ranks():
    pcr = {"AAA": 3.0, "BBB": 0.2, "CCC": 1.0, "DDD": None, "EEE": 1.1}
    cautious = {"AAA": 0.30, "BBB": 0.05, "CCC": 0.10, "DDD": 0.20, "EEE": 0.15}
    _, p = prepare(spot=101.0)
    decided = [(t, dict(sig.decide(p, revaluation(emp_path_r_cautious=cautious[t]), settings())[1])) for t in pcr]
    tickets = sig.rank_tickets(decided, {t: {"pcr_oi": x} for t, x in pcr.items()}, settings(), run_id="r",
                               evidence_session=EVIDENCE, issue_session=ISSUE, h9r_tickers={"CCC"})
    assert [t.ticker for t in tickets] == ["AAA", "DDD", "EEE", "CCC", "BBB"]
    by = {t.ticker: t for t in tickets}
    assert (by["AAA"].o4_stance, by["BBB"].o4_stance, by["CCC"].o4_stance, by["DDD"].o4_stance) == \
        ("AGAINST", "WITH", "MIDDLE", "UNAVAILABLE")
    assert by["CCC"].h9r_gap_up_event and not by["AAA"].h9r_gap_up_event and by["AAA"].o2_state == "UNAVAILABLE"


# --- S6 ----------------------------------------------------------------------------------------------------------

def ticket(**overrides):
    _, p = prepare(spot=None)
    _, fields = sig.decide(p, revaluation(), settings())
    t = sig.rank_tickets([("ABC", fields)], {}, settings(), run_id="r", evidence_session=EVIDENCE, issue_session=ISSUE,
                         h9r_tickers=set())[0]
    return sig.replace_ticket(t, **overrides)


def bars(*rows):
    sessions = [ISSUE] + [date(2026, 9, 21 + k) for k in range(len(rows) - 1)]
    return [Bar(d, *r) for d, r in zip(sessions, rows)]


def test_s6_exit_plan():
    t = ticket(hold_sessions=3)
    flat = (100, 101, 99, 100)
    plan = sig.plan_exit(t, bars(flat, flat, (100, 111, 99, 108), flat), as_of=date(2026, 9, 24))
    assert (plan.reason, plan.session, plan.level) == ("TARGET", date(2026, 9, 22), 110.0)
    assert sig.plan_exit(t, bars(flat, (100, 112, 94, 100)), as_of=date(2026, 9, 21)).reason == "STOP"
    assert sig.plan_exit(t, bars(flat, (93, 100, 92, 97)), as_of=date(2026, 9, 21)).fill_price == 93
    assert sig.plan_exit(t, bars((100, 101, 94, 94.5)), as_of=ISSUE).session == ISSUE
    plan = sig.plan_exit(t, bars(flat, flat, flat, flat), as_of=date(2026, 9, 23))
    assert (plan.reason, plan.session) == ("HOLD_COMPLETE", date(2026, 9, 23))
    assert sig.plan_exit(t, bars(flat, flat), as_of=date(2026, 9, 21)).state == "PENDING"
    capped = ticket(hold_sessions=3, last_usable_session=date(2026, 9, 21))
    assert sig.plan_exit(capped, bars(flat, flat), as_of=date(2026, 9, 21)).reason == "CONTRACT_LAST_USABLE"


def test_s6_marks():
    t = ticket(hold_sessions=1)
    plan = sig.plan_exit(t, bars((100, 101, 99, 100), (100, 101, 99, 100)), as_of=date(2026, 9, 21))
    out = sig.mark_signal(t, plan, bid=6.0)
    assert out.state == "CLOSED" and out.return_on_capital == pytest.approx(6.0 / 5.0 - 1)
    assert sig.mark_signal(t, plan, bid=None).state == "MARK_UNAVAILABLE"
    shares = ticket(expression="SHARES", side="LONG", contract_symbol=None, limit_price=100.5, scored_entry=100.5,
                    share_spread=0.01, hold_sessions=5, last_usable_session=None)   # marking kept for later use
    plan = sig.plan_exit(shares, bars((100.2, 101, 99.5, 100.5), (101, 111, 100, 109)), as_of=date(2026, 9, 21))
    out = sig.mark_signal(shares, plan, bid=None)
    assert out.return_on_capital == pytest.approx(110.0 * 0.995 / 100.5 - 1)


# --- S7 ----------------------------------------------------------------------------------------------------------

def test_s7_track_record_gate():
    s = settings(min_closed_signals=6, min_issue_sessions=3)
    assert sig.evaluate([(ISSUE, 0.5)] * 3, s)["verdict"] == "INSUFFICIENT_EVIDENCE"
    good = [(date(2026, 9, 18 + k % 4), 0.20 + 0.01 * k) for k in range(12)]
    assert sig.evaluate(good, s)["verdict"] == "EVIDENCE_SUPPORTS"
    mixed = [(date(2026, 9, 18 + k % 4), (-1) ** k * 0.3) for k in range(12)]
    assert sig.evaluate(mixed, s)["verdict"] == "NOT_SUPPORTED"
    assert sig.max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(0.5)


def test_registered_settings_load_from_configuration():
    snap = ConfigRegistry.from_documents(load_documents(), load_lock()).resolve(ISSUE)
    s = sig.settings_from_snapshot(snap)
    assert s.signal_version == "SIG-V1" and "BLOCK" in s.blocked_final_actions and s.min_closed_signals == 40
    assert (s.min_dte_cover, s.min_contract_dte_days, s.max_out_of_the_money) == (1.5, 21, 0.05)
    assert (s.max_entry_spread_fraction, s.max_tickets_per_session) == (0.10, 5)


# --- intraday adapter ----------------------------------------------------------------------------------------------

def test_spot_at_uses_last_completed_bar(tmp_path):
    folder = tmp_path / ISSUE.isoformat() / "ABC"
    folder.mkdir(parents=True)
    pd.DataFrame({"timestamp_utc": pd.to_datetime(["2026-09-18T14:20:00Z", "2026-09-18T14:25:00Z",
                                                   "2026-09-18T14:30:00Z"], utc=True),
                  "close": [100.5, 101.0, 101.5], "interval_minutes": [5, 5, 5]}).to_parquet(folder / "a.parquet")
    assert intraday.spot_at("ABC", ISSUE, "2026-09-18T14:32:00Z", tmp_path) == 101.0
    assert intraday.spot_at("ABC", ISSUE, "2026-09-18T14:10:00Z", tmp_path) is None
    assert intraday.spot_at("XYZ", ISSUE, "2026-09-18T14:32:00Z", tmp_path) is None
    # a bar that closed more than one interval before the quote is not the price at quote time (smoke test 17 Sep)
    assert intraday.spot_at("ABC", ISSUE, "2026-09-18T15:10:00Z", tmp_path) is None
    assert intraday.spot_at("ABC", ISSUE, "2026-09-18T14:39:59Z", tmp_path) == 101.5


# --- S8 service ----------------------------------------------------------------------------------------------------

THESIS = "ABC:CALL:2026-09-17:OLM2"


def seed_morning_chain(ledger, ticker: str, thesis_id: str, run_id: str) -> str:
    """The morning handoff's own events for a thesis: a candidate decision, then an execution decision."""
    from canonical_data.decision_outcome_ledger import make_ledger_event
    candidate = make_ledger_event(event_type="CANDIDATE_DECISION", occurred_at_utc="2026-09-18T14:40:00Z",
                                  run_id=run_id, ticker=ticker, thesis_id=thesis_id,
                                  payload={"decision_stage": "MORNING_VALIDATION"})
    ledger.append(candidate)
    execution = make_ledger_event(event_type="EXECUTION_DECISION", occurred_at_utc="2026-09-18T14:41:00Z",
                                  run_id=run_id, ticker=ticker, thesis_id=thesis_id,
                                  previous_event_id=candidate.event_id,
                                  payload={"decision_stage": "MORNING_VALIDATION"})
    ledger.append(execution)
    return execution.event_id


def test_s8_tickets_and_outcomes_live_in_the_decision_ledger(tmp_path):
    """S8 (ACK 18 Sep 2026): one owner per fact — issued tickets are PRESENTATION_DECISION events chained to the
    thesis's morning decision, every other candidate with a thesis is recorded as NOT_PRESENTED with its reason,
    and ticket outcomes are counterfactual OUTCOME events chained to the presentation. Idempotent throughout."""
    from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger
    run_id = "20260917_220000"
    runs = tmp_path / "runs"
    for folder in ("intelligence_lab", "options", "morning_validation"):
        (runs / run_id / folder).mkdir(parents=True)
    books = [book_row(thesis_id=THESIS),
             book_row(ticker="XYZ", thesis_id="XYZ:CALL:2026-09-17:OLM2", final_action="BLOCK"),
             book_row(ticker="NOID"),                                             # no thesis identity
             book_row(ticker="NOCHAIN", thesis_id="NOCHAIN:CALL:2026-09-17:OLM2")]  # no morning decision yet
    pd.DataFrame(books).to_csv(runs / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv", index=False)
    pd.DataFrame([valuation_row(ticker=b["ticker"]) for b in books]).to_csv(
        runs / run_id / "options" / f"options_intelligence_{run_id}.csv", index=False)
    pd.DataFrame([gate_row(ticker=b["ticker"]) for b in books]).to_csv(
        runs / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv", index=False)
    snap = ConfigRegistry.from_documents(load_documents(), load_lock()).resolve(ISSUE)
    store = storage.connect(tmp_path / "scoring.sqlite")
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    abc_execution = seed_morning_chain(ledger, "ABC", THESIS, run_id)
    seed_morning_chain(ledger, "XYZ", "XYZ:CALL:2026-09-17:OLM2", run_id)
    seen = []
    stub = lambda inputs: (seen.append(inputs), revaluation())[1]  # noqa: E731

    first = signal_service.issue_signals(store, runs, run_id, snap, NOW, ISSUE, ledger=ledger,
                                         bar_root=tmp_path / "bars", revalue=stub, rate=0.045,
                                         settings_override=settings())
    # a ticket that cannot be recorded is never issued: every issued ticket must be measurable
    assert first["status"] == "ISSUED" and first["issued"] == 1
    assert first["missing_thesis_identity"] == ["NOID"]
    assert first["ledger_chain_unavailable"] == ["NOCHAIN"]
    presentations = [e for e in ledger.events_by_type("PRESENTATION_DECISION")
                     if e.payload.get("decision_stage") == "SIGNAL_TICKET"]
    by_ticker = {e.ticker: e for e in presentations}
    assert set(by_ticker) == {"ABC", "XYZ"}
    assert by_ticker["ABC"].previous_event_id == abc_execution
    assert by_ticker["ABC"].payload["human_response"] == "NOT_YET_RECORDED"
    assert by_ticker["ABC"].payload["presented"] is True and by_ticker["ABC"].payload["rank"] == 1
    assert by_ticker["XYZ"].payload["human_response"] == "NOT_PRESENTED"
    assert by_ticker["XYZ"].payload["reason"] == "FINAL_ACTION_BLOCKED"
    assert "ABC" in (runs / run_id / "signals" / f"signal_tickets_{run_id}_{ISSUE.isoformat()}.md").read_text(encoding="utf-8")
    again = signal_service.issue_signals(store, runs, run_id, snap, NOW, ISSUE, ledger=ledger,
                                         bar_root=tmp_path / "bars", revalue=stub, rate=0.045,
                                         settings_override=settings())
    assert again["new_events"] == 0
    assert signal_service.issue_signals(store, runs, run_id, snap, NOW, date(2026, 9, 22), ledger=ledger,
                                        bar_root=tmp_path, revalue=stub, rate=0.045,
                                        settings_override=settings())["status"] == "STALE_BOOK"

    chain_db, price_db = tmp_path / "chains.db", tmp_path / "prices.sqlite"
    con = sqlite3.connect(chain_db)
    con.execute("CREATE TABLE chain_snapshots (ticker TEXT, quote_date TEXT, option_symbol TEXT, bid REAL, ask REAL)")
    con.execute("INSERT INTO chain_snapshots VALUES ('ABC', '2026-09-21', ?, 7.0, 7.3)", (SYMBOL,))
    con.commit(); con.close()
    con = sqlite3.connect(price_db)
    con.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, open REAL, high REAL, low REAL, close REAL, "
                "volume REAL, bar_status TEXT)")
    con.executemany("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?,?)", [
        ("ABC", "2026-09-18", 100, 103, 99, 102, 1e6, "COMPLETE"),
        ("ABC", "2026-09-21", 102, 111, 101, 109, 1e6, "COMPLETE")])
    con.commit(); con.close()
    early = signal_service.score_signals(ledger, ISSUE, snap, NOW, chain_db=chain_db, price_db=price_db,
                                         settings_override=settings())
    assert early["new_outcomes"] == 0 and early["states"].get("PENDING") == 1
    scored = signal_service.score_signals(ledger, date(2026, 9, 21), snap, NOW, chain_db=chain_db,
                                          price_db=price_db, settings_override=settings())
    assert scored["new_outcomes"] == 1
    outcomes = [e for e in ledger.events_by_type("OUTCOME") if e.payload.get("decision_stage") == "SIGNAL_TICKET"]
    assert len(outcomes) == 1 and outcomes[0].previous_event_id == by_ticker["ABC"].event_id
    assert outcomes[0].payload["is_counterfactual"] is True and outcomes[0].payload["exit_reason"] == "TARGET"
    assert outcomes[0].payload["return_on_capital"] == pytest.approx(7.0 / 5.0 - 1)
    assert signal_service.score_signals(ledger, date(2026, 9, 21), snap, NOW, chain_db=chain_db, price_db=price_db,
                                        settings_override=settings())["new_outcomes"] == 0
    report = signal_service.signal_section(ledger, snap)
    assert any("Signal track record" in line for line in report)
    assert not {"signal_tickets", "signal_outcomes", "signal_rejections"} & {
        r[0] for r in store.execute("SELECT name FROM sqlite_master WHERE type='table'")}
