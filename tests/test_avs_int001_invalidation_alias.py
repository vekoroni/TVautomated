"""Lab stop alias follows only the governed, side-checked price."""

from contracts.lab_control import opportunity_book_row


def _row(**overrides):
    signal = {
        "ticker": "TEST", "pipeline_mode": "MORNING_VALIDATION",
        "direction": "CALL", "signal_price": 100.0,
        "target_price": 110.0, "invalidation_price": 90.0,
        "invalidation_state": "AVAILABLE", "invalidation_source": "WYCKOFF_VALIDATION",
    }
    signal.update(overrides)
    return opportunity_book_row(signal, "20260925_061649", 1)


def test_available_invalidation_has_matching_stop_alias_for_lab_consumers():
    result = _row()
    assert result["invalidation_price"] == 90.0
    assert result["invalidation_spot"] == result["invalidation_price"]
    assert result["invalidation_source"] == "WYCKOFF_VALIDATION"


def test_wrong_side_invalidation_is_not_reintroduced_by_alias():
    result = _row(invalidation_price=105.0)
    assert result["invalidation_price"] in (None, "")
    assert result["invalidation_spot"] in (None, "")


def test_missing_invalidation_remains_a_review_row_not_a_fabricated_zero():
    result = _row(invalidation_price="", invalidation_state="MISSING_AUTHORITATIVE_STOP")
    assert result["invalidation_spot"] in (None, "")
    assert result["lab_tradeable"] is False


def test_unattributed_invalidation_cannot_acquire_execution_authority():
    result = _row(invalidation_source="")
    assert result["invalidation_price"] == 90.0
    assert result["invalidation_spot"] in (None, "")
    assert result["lab_tradeable"] is False
