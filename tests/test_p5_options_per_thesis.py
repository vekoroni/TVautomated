"""Phase 5.4 (ACK 8 Oct 2026, "Governing + all priced"; MarketData spend approved): Options prices every live thesis.

Business rules:
- The per-ticker contract stays the governing thesis's (side, target, invalidation already come from it).
- Every other live thesis is priced in the candidate lane on its own side and levels: all timeframes, both sides of a
  same-timeframe conflict, and both conditional sides of an undirected (UNRESOLVED) compression, labelled with the
  condition. Phase 0: 16,500 of 18,500 candidates were deferred by a 2,000 cap and undirected theses were never priced.
- No resource cap: a chain costs 1 credit (cached mode) and the lane reuses the ticker's one chain.
- A ticker with any adopted or conditional thesis has its chain acquired and recorded by the per-ticker step (one
  chain owner, provider finality reconciled), even when it has no governed side; it still gets no ticker contract.
- The legacy precor WAIT intent and the tier no longer remove tickers from Options (direction is the thesis's).
"""
from pathlib import Path

import pandas as pd

from domain.structure_behaviour.handoff_packet import build_candidate_packet
from scripts.options_candidate_lane import evaluate_candidate_expressions

ROOT = Path(__file__).resolve().parents[1]
POLICY = {"live_states": ["DETECTED", "ACTIVATED"], "monitoring_states": ["MONITOR", "OUTCOME_REACHED"],
          "vanguard_fields": ["verdict"], "version": "t"}


def _cand(cid, **kw):
    base = {"Candidate_ID": cid, "Ticker": cid.split("|")[0], "Timeframe": cid.split("|")[1],
            "Signal_State": "DETECTED", "Direction": None, "Duration_Remaining_Q50_Bars": 5}
    base.update(kw)
    return base


# ------------------------------------------------------------------ the packet routes by the thesis decision
def test_packet_routes_adopted_and_conditional_theses_for_pricing():
    cands = [
        _cand("AAA|1w|A", Direction="BULL", Adoption_State="ADOPTED", Thesis_Side="BULL"),
        _cand("AAA|1w|B", Direction="BEAR", Adoption_State="ADOPTED", Thesis_Side="BEAR"),
        _cand("BBB|1d|C", Adoption_State="UNRESOLVED", Conditional_Bull_Trigger=21.0, Conditional_Bear_Trigger=19.0),
        _cand("CCC|1d|D", Direction="BULL", Adoption_State="REFUSED"),
        _cand("DDD|1d|E", Adoption_State="UNRESOLVED"),
    ]
    packet = build_candidate_packet("RUN", cands, [], [], POLICY)
    status = {r["Candidate_ID"]: r["Handoff_Status"] for r in packet["records"]}
    assert status == {"AAA|1w|A": "DIRECTED_LIVE", "AAA|1w|B": "DIRECTED_LIVE",
                      "BBB|1d|C": "CONDITIONAL_BOTH_SIDES"}
    assert {r["Candidate_ID"] for r in packet["monitoring"]} == {"CCC|1d|D", "DDD|1d|E"}


# ------------------------------------------------------------------ the lane prices every routed thesis
class Calls:
    def __init__(self):
        self.selected = []

    def fetch(self, ticker):
        return pd.DataFrame({"right": ["C", "P"]})

    def parse(self, row):
        return {"ticker": row["ticker"], "spot": 20.0, "direction": "", "horizon_bucket": "6_10d"}

    def select(self, chain, ctx):
        self.selected.append((ctx["ticker"], ctx["direction"], ctx.get("structural_target"), ctx["invalidation_spot"]))
        return {"symbol": f"{ctx['ticker']}_{ctx['direction']}", "dte": 30, "delta": 0.45, "spread_pct": 4.0}


def _lane(records, max_candidates=None):
    calls = Calls()
    rows = {"BBB": {"ticker": "BBB"}, "AAA": {"ticker": "AAA"}}
    results = {"BBB": {"option_chain_dataset_id": "ds-b"}, "AAA": {"option_chain_dataset_id": "ds-a"}}
    out = evaluate_candidate_expressions(records, rows, results, fetch_chain=calls.fetch, parse_context=calls.parse,
                                         select_contract=calls.select, max_candidates=max_candidates)
    return out, calls


def test_a_conditional_thesis_is_priced_on_both_sides_with_its_condition():
    rec = {"Candidate_ID": "BBB|1d|C", "Ticker": "BBB", "Timeframe": "1d", "Handoff_Rank": 1,
           "Handoff_Status": "CONDITIONAL_BOTH_SIDES", "Conditional_Bull_Trigger": 21.0,
           "Conditional_Bear_Trigger": 19.0}
    out, calls = _lane([rec])
    by_side = {r["Expression_Side"]: r for r in out}
    assert set(by_side) == {"CALL", "PUT"}
    assert by_side["CALL"]["Expression_Status"] == "CONTRACT_FOUND"
    assert by_side["CALL"]["Expression_Condition"] == "CONDITIONAL: BULL if accepted above 21"
    assert by_side["PUT"]["Expression_Condition"] == "CONDITIONAL: BEAR if accepted below 19"
    # the opposite box edge is each side's invalidation; no target is invented
    assert ("BBB", "CALL", None, 19.0) in calls.selected and ("BBB", "PUT", None, 21.0) in calls.selected


def test_no_resource_cap_every_routed_thesis_is_priced():
    recs = [{"Candidate_ID": f"AAA|1d|{i}", "Ticker": "AAA", "Timeframe": "1d", "Handoff_Rank": i,
             "Handoff_Status": "DIRECTED_LIVE", "Direction": "BULL", "Outcome_Level": 25.0,
             "Invalidation_Level": 18.0} for i in range(1, 2502)]
    out, _ = _lane(recs, max_candidates=None)
    assert not any(str(r.get("Expression_Status", "")).startswith("DEFERRED_RESOURCE") for r in out)
    assert sum(r["Expression_Status"] == "CONTRACT_FOUND" for r in out) == 2501


def test_the_cap_is_removed_from_the_policy():
    import json
    policy = json.loads((ROOT / "config" / "beh001_handoff_v1.json").read_text(encoding="utf-8"))
    assert policy["expression"]["max_candidates_per_run"] is None


# ------------------------------------------------------------------ the per-ticker step owns the chain
def test_a_thesis_bearing_ticker_without_a_governed_side_gets_its_chain_recorded(monkeypatch):
    import scripts.avshunter_options_intelligence as oi
    fetched = []

    def fake_fetch(ticker):
        fetched.append(ticker)
        frame = pd.DataFrame({"right": ["C"]})
        frame.attrs["canonical_dataset_id"] = "ds-x"
        return frame

    monkeypatch.setattr(oi, "fetch_chain", fake_fetch)
    monkeypatch.setattr(oi, "parse_structural_context",
                        lambda row: {"ticker": "XXX", "spot": 20.0, "direction": "UNRESOLVED", "tier": 1, "phase": "B",
                                     "intent": "WAIT", "regime": "", "_signal_row": None})
    priceable = pd.Series({"ticker": "XXX", "thesis__adopted_count": 2, "thesis__conditional_count": 0})
    out = oi.process_ticker(priceable)
    assert fetched == ["XXX"] and out["option_chain_dataset_id"] == "ds-x"
    assert out["options_verdict"] == "STAND_DOWN" and "thesis alternatives" in out["stand_down_reason"]

    fetched.clear()
    bare = pd.Series({"ticker": "XXX", "thesis__adopted_count": 0, "thesis__conditional_count": 0})
    out = oi.process_ticker(bare)
    assert fetched == [] and "chain request suppressed" in out["stand_down_reason"]


def test_discovery_publishes_the_conditional_count():
    from contracts.thesis_record import THESIS_SPINE_FIELDS
    assert "thesis__conditional_count" in THESIS_SPINE_FIELDS


# ------------------------------------------------------------------ scope: no tier / WAIT exclusion
def test_options_scope_no_longer_excludes_by_tier_or_legacy_wait_intent():
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    scope = src.split("def run_options_layer(", 1)[1].split("if max_signals:", 1)[0]
    assert "merged['tier'].isin(ELIGIBLE_TIERS)" not in scope
    assert "eligible['precor_intent'] != 'WAIT'" not in scope
    assert "Gate 1: No directional conviction" not in src
    authorise = src.split("_chain_authorised_tickers = []\n            for", 1)[1].split("publish_options_worklist(", 1)[0]
    assert "_thesis_alternatives_priceable(" in authorise


# ------------------------------------------------------------------ the priced alternatives reach the card
def test_the_lane_is_summarised_per_ticker_for_the_options_row():
    import json
    from scripts.options_candidate_lane import summarise_by_ticker
    lane = [{"Candidate_ID": "AAA|1w|A", "Ticker": "AAA", "Timeframe": "1w", "Expression_Side": "CALL",
             "Expression_Condition": "DIRECTED", "Expression_Status": "CONTRACT_FOUND", "contract__symbol": "AAA_C",
             "contract__dte": 30, "contract__delta": 0.45},
            {"Candidate_ID": "AAA|1d|B", "Ticker": "AAA", "Timeframe": "1d", "Expression_Side": "PUT",
             "Expression_Condition": "DIRECTED", "Expression_Status": "NO_CONTRACT_FIT"}]
    out = summarise_by_ticker(lane)["AAA"]
    assert out["thesis_alternatives_count"] == 1 and out["thesis_alternatives_tested"] == 2
    alt = json.loads(out["thesis_alternatives_json"])[0]
    assert alt == {"candidate_id": "AAA|1w|A", "timeframe": "1w", "side": "CALL", "condition": "DIRECTED",
                   "symbol": "AAA_C", "dte": 30, "delta": 0.45}


def test_options_writes_the_summary_before_saving_its_rows():
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    body = src.split("out_df = _annotate_ev3_handoff_frame(pd.DataFrame(results))", 1)[1]
    assert body.index("_run_candidate_expression_lane(") < body.index("out_df.to_csv(out_path")


def test_the_book_row_and_card_carry_the_alternatives():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    from contracts.thesis_record import OPTIONS_ALTERNATIVE_FIELDS
    sig = {"ticker": "AAA", "thesis_alternatives_count": 1, "thesis_alternatives_tested": 2,
           "thesis_alternatives_json": '[{"symbol":"AAA_C"}]'}
    row = opportunity_book_row(sig, "RUN", 1)
    assert {f: row[f] for f in OPTIONS_ALTERNATIVE_FIELDS} == {f: sig[f] for f in OPTIONS_ALTERNATIVE_FIELDS}
    assert set(OPTIONS_ALTERNATIVE_FIELDS) <= set(FINAL_BOOK_FIELDS)
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    assert "Other theses priced" in card and "thesis_alternatives_json" in card
