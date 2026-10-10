"""Phase 5.4 (ACK 8 Oct 2026, MarketData spend approved): the Morning intraday build-up covers every adopted thesis.

Business rules:
- The build-up (advisory, never decides) is calculated for GO rows AND for every row whose thesis is adopted - its
  trigger accepted (READY_FOR_HUMAN_REVIEW) or still waiting (WAIT_TRIGGER), where the build-up toward the trigger is
  most informative. Before: GO rows only.
- Rows without an adopted thesis and rows without live data are not calculated; the stable worklist is unchanged.
"""
from morning_gate import _market_structure_populations


def test_adopted_theses_are_calculated_beside_go_rows():
    live = {t: {"live_price": 10.0} for t in ("GOO", "RDY", "WAI", "CLS", "NON")}
    results = [{"ticker": "GOO", "verdict": "GO"},
               {"ticker": "RDY", "verdict": "FLAG", "thesis__readiness": "READY_FOR_HUMAN_REVIEW"},
               {"ticker": "WAI", "verdict": "FLAG", "thesis__readiness": "WAIT_TRIGGER"},
               {"ticker": "CLS", "verdict": "FLAG", "thesis__readiness": "CLOSED_INVALIDATED"},
               {"ticker": "NON", "verdict": "BLOCK"}]
    worklist, calc, calc_live = _market_structure_populations(results, live)
    assert worklist == ("CLS", "GOO", "NON", "RDY", "WAI")
    assert [r["ticker"] for r in calc] == ["GOO", "RDY", "WAI"]
    assert set(calc_live) == {"GOO", "RDY", "WAI"}


def test_an_adopted_thesis_without_live_data_is_not_calculated():
    _, calc, _ = _market_structure_populations(
        [{"ticker": "WAI", "verdict": "FLAG", "thesis__readiness": "WAIT_TRIGGER"}], {})
    assert calc == []
