"""Phase 3: the legacy trigger layer has no direction of its own (P3: one direction owner).

Business rule: trigger_layer._direction may only READ the governed direction already on the row
(options_direction / direction). It must never derive a side from precor intent, dominant trend or VWAP bias -
Phase 0 found precor intent opposite to the thesis on 626 of 903 rows. No governed direction -> NONE.
"""
import trigger_layer as tl


def test_governed_direction_is_read():
    assert tl._direction({"options_direction": "PUT"}) == "PUT"
    assert tl._direction({"direction": "CALL"}) == "CALL"


def test_no_side_is_derived_from_legacy_fields():
    assert tl._direction({"precor_intent": "BUY_SETUP"}) == "NONE"
    assert tl._direction({"dominant_trend": "BEARISH"}) == "NONE"
    assert tl._direction({"vwap_bias": "ABOVE"}) == "NONE"
    assert tl._direction({"direction": "UNRESOLVED", "precor_intent": "SELL", "dominant_trend": "BULLISH"}) == "NONE"
