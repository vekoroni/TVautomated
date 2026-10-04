"""Research EV is numeric when sourced, never a governed C8 value."""

from datetime import date, datetime, timezone
import hashlib
import json

from canonical_data.session_clock import advance_xnys_sessions
from contracts.expression_valuation_packet import _research_value, publish_expression_valuations
from domain.option_path_valuation import value_long_option_paths
from domain.research_path_baseline import (
    ResearchBar, build_nonoverlapping_relative_paths,
)


def _paths():
    origin = date(2024, 1, 2)
    bars = []
    for index in range(260):
        session = advance_xnys_sessions(origin, index)
        spot = 100.0 + index * 0.05
        bars.append(ResearchBar(
            session.isoformat(), spot, spot * 1.01, spot * 0.99, spot,
            datetime(2026, 9, 1, tzinfo=timezone.utc).isoformat(), f"B{index}",
        ))
    return build_nonoverlapping_relative_paths("XYZ", tuple(bars))


def _candidate():
    return {
        "option_symbol": "XYZ261120C00100000", "option_right": "CALL",
        "strike": 100.0, "ask": 4.0, "bid": 3.8, "implied_vol": 0.35,
        "contract_multiplier": 100, "expiry_date": "2026-11-20",
        "last_exit_date": "2026-10-02",
    }


def _claim():
    return {"forecast_thesis_id": "20260926_173730:XYZ:2026-09-25:DISCOVERY",
            "ticker": "XYZ", "forecast_reference_spot": 100.0,
            "forecast_target_spot": 105.0, "forecast_invalidation_spot": 95.0,
            "forecast_direction": "BULL"}


def test_research_ev_is_numeric_and_explicitly_uncalibrated():
    result = _research_value(_claim(), _candidate(), _paths(), evidence_session="2026-09-25")
    assert result["state"] == "RESEARCH_EV_UNCALIBRATED"
    assert isinstance(result["ev_fraction"], float)
    assert result["independent_20_session_paths"] >= 12
    assert result["base_mean_95_interval"]["lower_95"] <= result["base_mean_95_interval"]["upper_95"]
    assert result["assumptions"]["wyckoff_conditioned"] is False
    assert result["authority"] == "RESEARCH_ONLY"


def test_thin_history_never_receives_numeric_research_ev():
    result = _research_value(_claim(), _candidate(), _paths()[:11], evidence_session="2026-09-25")
    assert result["state"] == "RESEARCH_HISTORY_THIN"
    assert "ev_fraction" not in result


def test_missing_iv_is_not_silently_zero_or_filled():
    candidate = {**_candidate(), "implied_vol": None}
    result = _research_value(_claim(), candidate, _paths(), evidence_session="2026-09-25")
    assert result == {"state": "RESEARCH_INPUT_MISSING", "reason": "IV_OR_MULTIPLIER_MISSING"}


def test_missing_governed_geometry_is_time_only_and_not_trade_ready():
    claim = {**_claim(), "forecast_target_spot": None, "forecast_invalidation_spot": None}
    result = _research_value(claim, _candidate(), _paths(), evidence_session="2026-09-25")
    assert result["state"] == "RESEARCH_EV_UNCALIBRATED"
    assert result["exit_policy"] == "TIME_ONLY_NO_GOVERNED_BARRIERS"
    assert result["authority"] == "RESEARCH_ONLY"


def test_default_c8_pricer_still_refuses_uncalibrated_paths():
    assert value_long_option_paths(None, None)["ev_fraction"] is None


def test_packet_keeps_research_ev_separate_from_governed_c8(tmp_path, monkeypatch):
    import contracts.expression_valuation_packet as publisher

    root = tmp_path / "20260926_173730"
    c5 = root / "forecast" / "ticker_forecast_descriptive_v1"
    c5.mkdir(parents=True)
    frozen = {"packet_version": "ticker_forecast_descriptive_v1", "run_id": root.name,
              "row_count": 1, "evidence_session": "2026-09-25",
              "as_of_utc": "2026-09-26T17:37:30Z", "rows": [_claim()]}
    c5_path = c5 / "packet.json"
    c5_path.write_text(json.dumps(frozen), encoding="utf-8")
    c5_hash = hashlib.sha256(c5_path.read_bytes()).hexdigest()
    (c5 / "receipt.json").write_text(json.dumps({
        "packet_version": frozen["packet_version"], "run_id": root.name,
        "authority": "ADVISORY_ONLY", "packet_sha256": c5_hash,
    }), encoding="utf-8")
    c6_path = root / "forecast" / "expression_candidates_v1" / "packet.json"
    c6_path.parent.mkdir(parents=True)
    c6_path.write_text(json.dumps({"run_id": root.name,
        "frozen_forecast_sha256": c5_hash, "row_count": 1,
        "rows": [{"ticker": "XYZ", "forecast_thesis_id": _claim()["forecast_thesis_id"],
                  "expression_state": "CANDIDATES_UNVALUED",
                  "candidates": [{**_candidate(), "thesis_id": _claim()["forecast_thesis_id"]}]}],
    }), encoding="utf-8")

    class ReadOnlyConnection:
        def close(self):
            pass

    monkeypatch.setattr(publisher, "open_research_price_database", lambda _: ReadOnlyConnection())
    monkeypatch.setattr(publisher, "read_current_known_bars", lambda *args, **kwargs: ())
    monkeypatch.setattr(publisher, "build_nonoverlapping_relative_paths", lambda *args: _paths())
    packet = publish_expression_valuations(root, price_database_path="ignored")
    assert packet["research_ev_count"] == 1
    assert packet["numeric_valuation_count"] == 0
    row = packet["rows"][0]
    assert row["numeric_ev"] is None
    assert row["best_expression"] is None
    assert row["expressions"][0]["research_ev"]["state"] == "RESEARCH_EV_UNCALIBRATED"
    assert publish_expression_valuations(root, price_database_path="ignored") == packet
