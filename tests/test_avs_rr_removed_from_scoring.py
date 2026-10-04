"""R:R leaves every score and gate (ACK 3 Oct 2026: "remove R:R points as recommended").

Evidence (design step 6, holdout replay, 67,584 candidates): stop-based R:R ranks outcomes with IC ~0.015 - no
ranking information - and the anticipated move did not earn its place either (D-C: display only). Business rule:
two rows that differ only in R:R score, tier, flag and route identically. R:R stays recorded (audit tier, legacy).
"""
import inspect

import eod_candidate_engine as eod


def _row(**kw):
    base = {"ticker": "T", "direction": "CALL", "options_score": 40, "composite": 60, "trigger_quality": "STRONG",
            "eil_v3_verdict": "EXECUTE", "contract_delta": 0.45, "contract_oi": 900, "contract_volume": 120,
            "contract_bid": 1.0, "contract_ask": 1.05, "premium": 1.05, "signal_price": 100.0}
    base.update(kw)
    return base


def test_structural_conviction_ignores_rr():
    lo, bd_lo = eod.structural_conviction_score(_row(rr_underlying_reachable=0.2))
    hi, bd_hi = eod.structural_conviction_score(_row(rr_underlying_reachable=3.0))
    assert lo == hi
    assert "retired" in str(bd_hi.get("rr_quality", "")).lower()


def test_legacy_conviction_ignores_rr():
    assert eod._structural_conviction_score_legacy(_row(rr_underlying_reachable=0.2))[0] == \
        eod._structural_conviction_score_legacy(_row(rr_underlying_reachable=3.0))[0]


def test_shadow_opportunity_ignores_rr():
    assert eod._shadow_opportunity_score(_row(rr=0.5))[0] == eod._shadow_opportunity_score(_row(rr=3.0))[0]


def test_monetisation_fit_and_contract_quality_ignore_rr():
    info = {"resolved_direction": "CALL", "selected_contract_side": "CALL", "direction_call_score": 1.0,
            "direction_put_score": 0.0}
    a = eod._contract_repair_profile(_row(rr_options_reachable=0.2), info)
    b = eod._contract_repair_profile(_row(rr_options_reachable=3.0), info)
    assert a == b and "BREAKEVEN_OR_RR_CAUTION" not in str(a)
    assert eod._monetisation_fit(_row(rr_options_reachable=0.2), "A", a, info) == \
        eod._monetisation_fit(_row(rr_options_reachable=3.0), "A", a, info)


def test_superbrain_has_no_rr_gate():
    import scripts.avshunter_superbrain_layer as sb
    src = inspect.getsource(sb.assemble_execution_plan)
    assert "GATE_LOW_RR" not in src and "GATE_RR_FLOOR" not in src and "WARN_LOW_RR_EOD" not in src


def test_options_route_has_no_rr_review_flag():
    import scripts.avshunter_options_intelligence as oi
    src = inspect.getsource(oi)
    assert 'soft_review_flags.append("ESTIMATED_R_LT_1")' not in src
    assert 'soft_review_flags.append("ESTIMATED_R_MISSING")' not in src
