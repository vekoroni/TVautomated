"""BEH-001 phase 2B: expression search per behavioural candidate (C-01, C-03 handoff, C-07).

Business rules:
- Each routed candidate is interrogated for a contract on its own side, with its own
  outcome level and invalidation; opposite-side candidates on one ticker are both evaluated.
- The chain is the one the existing Options path already acquired for the ticker: no new
  provider request, and no chain for a ticker the governed direction record did not
  authorise (that existing constraint is recorded, not hidden).
- Capacity is a resource deferral with its rank, never a behavioural rejection.
- Runway stays the existing authority (C-06 is phase 3); liquidity is an Options attribute.
- One candidate's failure never affects another candidate or the per-ticker outputs.
"""
import pandas as pd

from scripts.options_candidate_lane import evaluate_candidate_expressions


def rec(ticker, side, rank, outcome=12.0, invalidation=9.0, kind="Spring Candidate"):
    return {"Candidate_ID": f"{ticker}|1d|CAMPAIGN|{kind}|{rank}", "Ticker": ticker, "Direction": side,
            "Signal_State": "DETECTED", "Handoff_Rank": rank, "Outcome_Level": outcome,
            "Invalidation_Level": invalidation, "Timeframe": "1d", "Duration_Remaining_Q80_Bars": 22}


class Calls:
    def __init__(self):
        self.chains, self.selected = [], []

    def fetch(self, ticker):
        self.chains.append(ticker)
        if ticker == "ERR":
            raise RuntimeError("boom")
        return pd.DataFrame({"right": ["C", "P"]})

    def parse(self, row):
        return {"ticker": row["ticker"], "spot": 10.0, "direction": "CALL", "structural_target": 11.0,
                "invalidation_spot": 9.5, "horizon_bucket": "6_10d", "hold_days": 10}

    def select(self, chain, ctx):
        self.selected.append((ctx["ticker"], ctx["direction"], ctx["structural_target"], ctx["invalidation_spot"]))
        if ctx["direction"] == "PUT" and ctx["ticker"] == "AAA":
            return None
        return {"symbol": f"{ctx['ticker']}_{ctx['direction']}", "dte": 30, "delta": 0.45, "spread_pct": 4.0,
                "_valuer": object()}


RECORDS = [rec("AAA", "BULL", 1), rec("AAA", "BEAR", 2, outcome=8.0, invalidation=11.0),
           rec("BBB", "BULL", 3), rec("ZZZ", "BULL", 4), rec("AAA", "BULL", 5, kind="LPS")]
ROWS = {"AAA": {"ticker": "AAA"}, "BBB": {"ticker": "BBB"}}
RESULTS = {"AAA": {"option_chain_dataset_id": "ds1"}, "BBB": {"option_chain_dataset_id": "",
                                                               "stand_down_reason": "No governed long CALL/PUT direction"}}


def run(capacity=4):
    calls = Calls()
    out = evaluate_candidate_expressions(RECORDS, ROWS, RESULTS, fetch_chain=calls.fetch,
                                         parse_context=calls.parse, select_contract=calls.select,
                                         max_candidates=capacity)
    return {r["Candidate_ID"]: r for r in out}, calls


def test_opposite_side_candidates_on_one_ticker_are_both_evaluated_with_their_own_levels():
    out, calls = run()
    assert ("AAA", "CALL", 12.0, 9.0) in calls.selected and ("AAA", "PUT", 8.0, 11.0) in calls.selected
    assert out["AAA|1d|CAMPAIGN|Spring Candidate|1"]["Expression_Status"] == "CONTRACT_FOUND"
    assert out["AAA|1d|CAMPAIGN|Spring Candidate|1"]["contract__symbol"] == "AAA_CALL"
    assert out["AAA|1d|CAMPAIGN|Spring Candidate|2"]["Expression_Status"] == "NO_CONTRACT_FIT"


def test_no_new_chain_requests_and_unauthorised_chains_are_recorded():
    out, calls = run()
    assert calls.chains == ["AAA"]                     # once per ticker, only where already acquired
    assert out["BBB|1d|CAMPAIGN|Spring Candidate|3"]["Expression_Status"] == "NOT_ROUTED:CHAIN_NOT_AUTHORISED_BY_GDR"
    assert out["ZZZ|1d|CAMPAIGN|Spring Candidate|4"]["Expression_Status"] == "NOT_ROUTED:TICKER_OUTSIDE_OPTIONS_SCOPE"


def test_capacity_is_a_resource_deferral_with_rank():
    out, _ = run(capacity=4)
    assert out["AAA|1d|CAMPAIGN|LPS|5"]["Expression_Status"] == "DEFERRED_RESOURCE:5"


def test_runway_stays_existing_and_duration_travels_beside_it():
    out, _ = run()
    row = out["AAA|1d|CAMPAIGN|Spring Candidate|1"]
    assert row["runway_authority"] == "EXISTING_OPTIONS_POLICY:6_10d"
    assert row["Duration_Remaining_Q80_Bars"] == 22
    assert "contract___valuer" not in row               # only plain values travel


def test_one_failure_never_affects_others():
    calls = Calls()
    records = RECORDS + [rec("ERR", "BULL", 0)]
    rows = {**ROWS, "ERR": {"ticker": "ERR"}}
    results = {**RESULTS, "ERR": {"option_chain_dataset_id": "ds2"}}
    out = {r["Candidate_ID"]: r for r in evaluate_candidate_expressions(
        records, rows, results, fetch_chain=calls.fetch, parse_context=calls.parse,
        select_contract=calls.select, max_candidates=10)}
    assert out["ERR|1d|CAMPAIGN|Spring Candidate|0"]["Expression_Status"].startswith("ERROR:")
    assert out["AAA|1d|CAMPAIGN|Spring Candidate|1"]["Expression_Status"] == "CONTRACT_FOUND"


def test_options_run_writes_the_lane_after_its_own_outputs_and_never_fails():
    from pathlib import Path
    source = Path("scripts/avshunter_options_intelligence.py").read_text(encoding="utf-8")
    body = source[source.index("def run_options_layer("):]
    hook = body.index("_run_candidate_expression_lane(vanguard_csv")
    assert body.index("out_df.to_csv(out_path") < hook
    assert body.index("out_df.to_csv(latest_path") < hook
    block = body[hook - 300:hook + 300]
    assert "try:" in block and "except Exception" in block


def test_lane_helper_reads_the_packet_and_writes_one_row_per_candidate(tmp_path, monkeypatch):
    import json
    import scripts.avshunter_options_intelligence as oi
    run = tmp_path / "R1"
    (run / "vanguard").mkdir(parents=True)
    packet_dir = run / "forecast" / "behavioural_candidate_packet_v1"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet.json").write_text(json.dumps({"records": RECORDS}), encoding="utf-8")
    calls = Calls()
    monkeypatch.setattr(oi, "fetch_chain", calls.fetch)
    monkeypatch.setattr(oi, "parse_structural_context", calls.parse)
    monkeypatch.setattr(oi, "select_best_contract", calls.select)
    eligible = pd.DataFrame([{"ticker": "AAA"}, {"ticker": "BBB"}])
    results = [{"ticker": "AAA", "option_chain_dataset_id": "ds1"}, {"ticker": "BBB"}]
    path = oi._run_candidate_expression_lane(str(run / "vanguard" / "vanguard_signals.csv"), eligible, results,
                                             "R1", str(tmp_path))
    lane = pd.read_csv(path)
    assert len(lane) == len(RECORDS)
    assert (lane["Expression_Status"] == "CONTRACT_FOUND").sum() == 2
    assert oi._run_candidate_expression_lane(str(tmp_path / "X" / "vanguard" / "v.csv"), eligible, results,
                                             "R1", str(tmp_path)) is None
