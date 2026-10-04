"""DIR-002 VNG-11 (amended by ACK, 1 Oct 2026): an open trade contract never
removes a ticker. The held ticker is evaluated as new and the governance verdict
travels with its row; a contract without an explicit CALL/PUT direction is not
evaluated as CALL.
"""
from pathlib import Path

from vanguard.trade_governance import TradeGovernanceEngine


def test_contract_without_direction_is_not_read_as_call():
    engine = TradeGovernanceEngine.__new__(TradeGovernanceEngine)
    result = engine._check_price_invalidation(
        {"invalidation_price": 90.0, "entry_price": 100.0}, 80.0
    )
    assert result["breach"] is False
    assert "DIRECTION_MISSING" in result["reason"]


def test_held_ticker_reenters_the_line_as_new():
    """ACK, 1 Oct: a ticker re-enters every run and is evaluated through the whole
    cycle, even when a trade is already open. Governance runs alongside and its
    verdict travels with the row; it never skips the ticker."""
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_vanguard_from_packages.py").read_text(encoding="utf-8")
    branch = source[source.index("if _governance_engine and ticker in _open_tickers"):]
    branch = branch[: branch.index("END GOVERNANCE ROUTING")]
    assert "continue" not in branch
    assert "reject_rows.append" not in branch


def test_governance_verdict_is_stamped_on_the_held_tickers_rows():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from scripts.run_vanguard_from_packages import stamp_governance
    rows = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    stamp_governance(rows, {"AAA": {"verdict": "HOLD", "reason": "thesis intact"}})
    assert rows[0]["governance__open_contract"] is True
    assert rows[0]["governance__verdict"] == "HOLD"
    assert rows[0]["governance__reason"] == "thesis intact"
    assert rows[1]["governance__open_contract"] is False
    assert rows[1]["governance__verdict"] == ""
