"""DWN-16: neither EV v2 copy may silently invent a CALL."""

import pytest

from scripts.ev_engine import EVInputs, ev_inputs_from_row


def test_duplicate_engine_requires_explicit_side():
    with pytest.raises(TypeError):
        EVInputs()


@pytest.mark.parametrize("direction", [None, "", "UNRESOLVED", "BULL|BEAR"])
def test_duplicate_engine_rejects_missing_or_ambiguous_side(direction):
    with pytest.raises(ValueError, match="explicit CALL or PUT"):
        ev_inputs_from_row({"ticker": "TEST", "direction": direction})


def test_duplicate_engine_accepts_explicit_put():
    assert ev_inputs_from_row({"ticker": "TEST", "direction": "PUT"}).direction == "PUT"
