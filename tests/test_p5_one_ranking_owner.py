"""Phase 5.5 / RC10 (ACK 8 Oct 2026, "Expectancy"): one ranking owner for the Lab book and the trade summary.

Business rules:
- Decision groups: lane A, B, C (unassigned last), then the thesis readiness inside each lane (accepted trigger first,
  then waiting, then not measured / not adopted / closed, missing last).
- Within a group: expected option multiple = lane holdout hit rate x option value at the median time - 1 premium.
  Long options are judged on expectancy and convexity, not hit rate (ACK 7 Oct 2026). It is a conditional estimate,
  labelled as such, until the outcome scorer calibrates it. A row without it ranks after rows with it (missing is
  never neutral). Ties: more replay evidence first, then ticker.
- The retired priority score no longer orders the book; the trade summary shows the book's rank instead of
  re-sorting by value (Codex 7 Oct RC10: two views, two orders).
"""
from pathlib import Path

from contracts.lab_control import FINAL_BOOK_FIELDS, build_final_opportunity_book
from domain.opportunity_rank import expected_option_multiple, rank_key

ROOT = Path(__file__).resolve().parents[1]


def _sig(ticker, lane="A", ready="READY_FOR_HUMAN_REVIEW", p=0.6, v=2.5, n=40, priority=0.0):
    return {"ticker": ticker, "trade_lane": lane, "thesis__readiness": ready, "trade_lane_hit_holdout": p,
            "anticipated_value_multiple_q50": v, "anticipated_evidence_n": n, "priority_score": priority,
            "lab_verdict": "MANUAL_REVIEW"}


def test_expected_multiple_is_hit_rate_times_value_less_the_premium():
    assert round(expected_option_multiple(_sig("A")), 6) == 0.5
    assert expected_option_multiple(_sig("A", v=None)) is None
    assert expected_option_multiple(_sig("A", p="")) is None


def test_groups_then_expectancy_then_evidence_then_ticker():
    rows = [_sig("LANEB", lane="B", p=0.9, v=9.0), _sig("WAIT", ready="WAIT_TRIGGER", p=0.9, v=9.0),
            _sig("LOW", p=0.5, v=1.5), _sig("HIGH", p=0.6, v=3.0), _sig("NOVAL", v=None),
            _sig("TIE_FEW", p=0.6, v=2.5, n=10), _sig("TIE_MANY", p=0.6, v=2.5, n=90), _sig("NOLANE", lane="")]
    order = [r["ticker"] for r in sorted(rows, key=rank_key)]
    assert order == ["HIGH", "TIE_MANY", "TIE_FEW", "LOW", "NOVAL", "WAIT", "LANEB", "NOLANE"]


def test_the_book_rank_comes_from_the_one_owner_not_the_priority_score():
    book = build_final_opportunity_book("RUN", [_sig("LOWVALUE", p=0.5, v=1.2, priority=99.0),
                                                _sig("HIGHVALUE", p=0.7, v=3.0, priority=1.0)])
    ranks = {r["ticker"]: r["lab_rank"] for r in book}
    assert ranks == {"HIGHVALUE": 1, "LOWVALUE": 2}
    row = next(r for r in book if r["ticker"] == "HIGHVALUE")
    assert abs(float(row["rank_expected_multiple"]) - 1.1) < 1e-9
    assert row["rank_group"] == "A|READY_FOR_HUMAN_REVIEW"
    assert "conditional" in row["rank_basis"].lower()
    assert {"rank_expected_multiple", "rank_group", "rank_basis"} <= set(FINAL_BOOK_FIELDS)


def test_the_trade_summary_shows_the_book_rank_instead_of_re_sorting():
    js = (ROOT / "intelligence-lab" / "static" / "trade-summary.js").read_text(encoding="utf-8")
    body = js.split("function renderTradeSummaryTable", 1)[1].split("\n}\n", 1)[0]
    assert "lab_rank" in body and "anticipated_value_multiple_q50) ?? -1" not in body


def test_the_lab_server_rank_is_the_same_owner():
    # A third order existed: intelligence_lab._finalise_lab_priority_ranking re-ranked by action bucket and the
    # retired research priority score, and the Lab table sorts by that priority_rank.
    import importlib.util
    spec = importlib.util.spec_from_file_location("ilab_rank", ROOT / "intelligence-lab" / "intelligence_lab.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    sigs = [_sig("LOWVALUE", p=0.5, v=1.2, priority=99.0), _sig("HIGHVALUE", p=0.7, v=3.0, priority=1.0),
            _sig("LANEC", lane="C", p=0.9, v=9.0, priority=50.0)]
    for s in sigs:
        s["research_priority_score"] = s["priority_score"]
    lab._finalise_lab_priority_ranking(sigs)
    assert {s["ticker"]: s["priority_rank"] for s in sigs} == {"HIGHVALUE": 1, "LOWVALUE": 2, "LANEC": 3}


def test_blocked_rows_sink_below_every_actionable_or_review_row():
    # ACK 8 Oct 2026 "Blocked sink": keeps the 18 Sep rule (review above BLOCKED) inside the one owner.
    rows = [{**_sig("GRAL", p=0.66, v=2.66), "lab_verdict": "BLOCKED"}, _sig("WEAKC", lane="C", p=0.2, v=1.0)]
    assert [r["ticker"] for r in sorted(rows, key=rank_key)] == ["WEAKC", "GRAL"]


def test_the_book_is_ranked_on_its_final_rows_so_a_late_block_still_sinks(monkeypatch):
    # Live run 20261008_220129: BRO, FA and ISRG were blocked by the materializer (INVALIDATION_MISSING) after the
    # sort, sat at ranks 2348-2351 among unblocked rows, and shifted 441 ranks. The rank must use the final rows.
    import contracts.lab_control as lc
    real = lc.opportunity_book_row

    def late_blocking_row(sig, run_id, rank, **kw):
        row = real(sig, run_id, rank, **kw)
        if sig["ticker"] == "LATE":
            row["lab_verdict"] = "BLOCKED"          # what the materializer does for a missing invalidation
        return row

    monkeypatch.setattr(lc, "opportunity_book_row", late_blocking_row)
    book = lc.build_final_opportunity_book("RUN", [_sig("LATE", p=0.9, v=9.0), _sig("PLAIN", p=0.5, v=1.5)])
    by = {r["ticker"]: r for r in book}
    assert by["PLAIN"]["lab_rank"] == 1 and by["LATE"]["lab_rank"] == 2
    assert by["LATE"]["priority_rank"] == 2
    assert [r["ticker"] for r in book] == ["PLAIN", "LATE"]
