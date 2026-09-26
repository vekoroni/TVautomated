"""A stored-run audit must disclose its grain and never infer trade outcomes."""

from tools.avs_int001_horizon_audit import audit_rows


def test_audit_counts_legacy_increment_false_review_without_reclassifying_trade():
    result = audit_rows([{
        "time_horizon": "6_10d", "signal_price": 100, "target_price": 110,
        "garch_expected_move_1_5d": 5, "garch_expected_move_6_10d": 2,
    }])
    assert result["by_horizon"]["6_10D"]["legacy_false_review"] == 1
    assert "not a trading outcome" in result["meaning"]


def test_audit_does_not_complete_a_missing_legacy_path():
    result = audit_rows([{
        "time_horizon": "6_10d", "signal_price": 100, "target_price": 110,
        "garch_expected_move_6_10d": 2,
    }])
    assert result["by_horizon"]["6_10D"]["not_comparable"] == 1
