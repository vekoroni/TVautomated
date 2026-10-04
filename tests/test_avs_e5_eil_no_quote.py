"""E5 (missing-means-unknown family, ACK 3 Oct 2026): the EIL does not score rows without an options quote.

Defect (live on 20261001_211641): the 205 rows with no option chain got an EIL composite of 74.75 built from
no-data defaults (liquidity 'No options bid/ask data' -> spread score 85; IV 'No IV data' -> 70 'CLEAN'), which
produced EXECUTE claims later overwritten to NOT_EVALUATED - but the composite stayed and earned Lab ranking credit
(composite weighting and the conviction bonus +2 at >= 65) and the EOD pse_score fallback.
Business rules: no options quote -> EIL NOT_EVALUATED (reason NO_OPTIONS_QUOTE), composite None; the IV component
with no IV data says NO_DATA, never CLEAN.
"""
from types import SimpleNamespace

import execution_intelligence_runner as runner


def test_no_quote_row_is_not_evaluated_and_has_no_composite():
    row = {"eil_v3_verdict": "EXECUTE", "eil_composite_score": 74.75}
    runner._eil_not_evaluated_without_quote(row, SimpleNamespace(options_bid=None, options_ask=None))
    assert row["eil_v3_verdict"] == "NOT_EVALUATED" and row["eil_composite_score"] is None
    assert row["eil_not_evaluated_reason"] == "NO_OPTIONS_QUOTE"


def test_quoted_row_is_untouched():
    row = {"eil_v3_verdict": "EXECUTE", "eil_composite_score": 74.75}
    runner._eil_not_evaluated_without_quote(row, SimpleNamespace(options_bid=1.0, options_ask=1.1))
    assert row == {"eil_v3_verdict": "EXECUTE", "eil_composite_score": 74.75}


def test_iv_component_without_data_says_no_data():
    from vanguard.execution.strategies import iv_distortion
    ctx = SimpleNamespace(iv_bid=None, iv_mid=None, iv_ask=None, options_open_interest=0, signal_direction="CALL")
    assert iv_distortion.run(ctx).verdict == "NO_DATA"
