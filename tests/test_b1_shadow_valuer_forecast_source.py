"""B1 — the shadow contract valuer must be able to find the Layer 3 forecast (ACK, 25 Sep 2026).

Root cause (Enhancements/research/rca/B1_SHADOW_CONTRACT_VALUER_RCA_AND_DESIGN_20260925.md): the valuer reads
`l3_forward_realised_vol_raw` from the signal row, but the Layer 3 forecast is produced by garch_runner in
Phase 10a, after Options Intelligence. In production no row carries it at selection time, so every row has
been VALUE_INPUTS_UNAVAILABLE since the shadow was switched on.

Business rules (ACK):
- The valuer may read the most recent Layer 3 forecast already on disk for the ticker, never a future run's,
  and must record where it came from and how old it is (fresh or flagged).
- A clipped forecast is never used for value (ACK 17 Sep 2026).
- The selected contract is unchanged: value_selection_mode stays SHADOW.
- When no forecast exists anywhere, behaviour is exactly today's: flagged, never defaulted.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import avshunter_options_intelligence as oi

FIELDS = ["ticker", "l3_forward_realised_vol", "l3_forward_realised_vol_raw", "l3_forecast_state"]


def _contract(symbol: str, dte: float, *, spread: float = 0.08, delta: float = 0.50, strike: float = 100.0,
              mid: float = 2.0) -> dict:
    half = mid * spread / 2.0
    return {
        "symbol": symbol, "underlying": "TEST", "right": "C", "strike": strike,
        "expiration_date": f"exp{int(dte)}", "dte": dte, "mark": mid, "bid": mid - half, "ask": mid + half,
        "bid_size": 10, "ask_size": 10, "delta": delta, "gamma": 0.03, "theta": -0.03, "vega": 0.08,
        "implied_vol": 0.40, "open_interest": 100, "volume": 20, "spread_pct": spread,
        "quote_quality": "TWO_SIDED", "quality_flags": (), "quote_fields_complete": True, "mark_synthetic": False,
        "quote_timestamp_utc": "2026-09-24T20:00:00Z",
    }


_CHAIN = [_contract("S29A", 29.0), _contract("S29B", 29.0, delta=0.30, strike=105.0),
          _contract("S64A", 64.0, mid=3.0), _contract("S92A", 92.0, mid=3.6)]


def _production_ctx() -> dict:
    """The production shape: the signal row is the Vanguard enriched row, which carries no l3_* field."""
    row = pd.Series({"ticker": "TEST", "direction": "CALL", "horizon_bucket": "1_5d", "current_price": 100.0,
                     "target_price": 110.0, "invalidation_spot": 95.0, "invalidation_state": "AVAILABLE"})
    structural = oi.parse_structural_context(row)
    return {"ticker": "TEST", "direction": "CALL", "spot": 100.0, "horizon_bucket": "1_5d",
            "structural_target": 110.0, "invalidation_spot": 95.0, "hold_days": 5,
            "dte_window": oi.governed_dte_window("1_5d"), "dte_config": oi.governed_dte_config("1_5d"),
            "_signal_row": {"ticker": "TEST", "final_direction": "CALL", "underlying_price": 100.0,
                            "structural_target": 110.0, "invalidation_spot": 95.0},
            **{k: structural[k] for k in ("contract_runway_floor_days", "contract_min_holdable_dte",
                                          "contract_runway_basis", "contract_runway_hold_sessions")}}


def _write_forecast(runs_dir: Path, run_id: str, ticker: str, raw: float, state: str = "FORECAST_OK") -> None:
    folder = runs_dir / run_id / "qomega"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"garch_forecasts_{run_id}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({"ticker": ticker, "l3_forward_realised_vol": raw, "l3_forward_realised_vol_raw": raw,
                    "l3_forecast_state": state})


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(oi, "_L3_RUNS_DIR", tmp_path, raising=False)
    if hasattr(oi, "_L3_FORECAST_CACHE"):
        oi._L3_FORECAST_CACHE.clear()
    monkeypatch.setitem(oi.CONTRACT_SELECTION, "value_selection_mode", "SHADOW")
    yield tmp_path
    oi.set_active_run_context(None, None)
    if hasattr(oi, "_L3_FORECAST_CACHE"):
        oi._L3_FORECAST_CACHE.clear()


def _select(ctx):
    return oi.select_best_contract(pd.DataFrame(_CHAIN), ctx)


# ── Characterisation: today's behaviour, pinned ──────────────────────────────────────────────────────────
def test_characterisation_production_row_without_forecast_is_unavailable(runs_dir):
    oi.set_active_run_context("20260925_061649", str(runs_dir / "20260925_061649"))
    selected = _select(_production_ctx())
    assert selected["contract_value_basis"] == "SCORE_FALLBACK_VALUE_UNAVAILABLE"
    assert selected["contract_value_quality_flag"] == "VALUE_INPUTS_UNAVAILABLE"
    assert selected["contract_value_best_symbol"] is None
    assert selected.get("contract_value_forecast_source", "UNAVAILABLE") == "UNAVAILABLE"


# ── Business rules: fail until the change lands ──────────────────────────────────────────────────────────
def test_the_forecast_on_disk_for_the_active_run_is_used_at_age_zero(runs_dir):
    run_id = "20260925_061649"
    _write_forecast(runs_dir, run_id, "TEST", 0.35)
    oi.set_active_run_context(run_id, str(runs_dir / run_id))
    score_choice = _select(_production_ctx())["contract_value_score_choice_symbol"]
    selected = _select(_production_ctx())
    assert selected["symbol"] == score_choice                              # SHADOW: selection unchanged
    assert selected["contract_value_basis"] == "SCORE_VALUE_SHADOW"
    assert selected["contract_value_quality_flag"] == "OK"
    assert selected["contract_value_best_symbol"] is not None
    assert selected["contract_value_forecast_source"] == "L3_ON_DISK"
    assert selected["contract_value_forecast_run_id"] == run_id
    assert selected["contract_value_forecast_age_sessions"] == 0
    alternatives = json.loads(selected["contract_value_alternatives"])
    assert all(a["quality_flag"] == "OK" and a["r_central"] is not None for a in alternatives)


def test_the_previous_runs_forecast_is_used_and_its_age_is_recorded(runs_dir):
    _write_forecast(runs_dir, "20260924_085940", "TEST", 0.35)           # previous session's run
    oi.set_active_run_context("20260925_061649", str(runs_dir / "20260925_061649"))  # no forecast of its own
    selected = _select(_production_ctx())
    assert selected["contract_value_quality_flag"] == "OK"
    assert selected["contract_value_forecast_source"] == "L3_ON_DISK"
    assert selected["contract_value_forecast_run_id"] == "20260924_085940"
    assert selected["contract_value_forecast_age_sessions"] == 1          # 24 Sep -> 25 Sep, one XNYS session


def test_age_uses_the_session_each_run_processed_not_the_local_run_date(runs_dir):
    """A run id carries the local date, one day after the US session it processed. Friday's close is run on
    Saturday morning here, so run-id dates would count zero sessions; run_meta's session_date is the authority."""
    _write_forecast(runs_dir, "20260925_061649", "TEST", 0.35)           # processed session 2026-09-24
    (runs_dir / "20260925_061649" / "run_meta.json").write_text(json.dumps({"session_date": "2026-09-24"}), encoding="utf-8")
    (runs_dir / "20260926_061500").mkdir()
    (runs_dir / "20260926_061500" / "run_meta.json").write_text(json.dumps({"session_date": "2026-09-25"}), encoding="utf-8")
    oi.set_active_run_context("20260926_061500", str(runs_dir / "20260926_061500"))  # tonight: session 2026-09-25
    selected = _select(_production_ctx())
    assert selected["contract_value_forecast_run_id"] == "20260925_061649"
    assert selected["contract_value_forecast_age_sessions"] == 1


def test_a_future_runs_forecast_is_never_used(runs_dir):
    _write_forecast(runs_dir, "20260926_061649", "TEST", 0.35)           # newer than the active run
    oi.set_active_run_context("20260925_061649", str(runs_dir / "20260925_061649"))
    selected = _select(_production_ctx())
    assert selected["contract_value_quality_flag"] == "VALUE_INPUTS_UNAVAILABLE"
    assert selected["contract_value_forecast_source"] == "UNAVAILABLE"


def test_a_clipped_forecast_is_refused(runs_dir):
    run_id = "20260925_061649"
    _write_forecast(runs_dir, run_id, "TEST", 0.35, state="CLIPPED_AT_CAP")
    oi.set_active_run_context(run_id, str(runs_dir / run_id))
    selected = _select(_production_ctx())
    assert selected["contract_value_quality_flag"] == "VALUE_INPUTS_UNAVAILABLE"
    assert selected["contract_value_forecast_source"] == "UNAVAILABLE"


def test_a_forecast_on_the_signal_row_still_wins_and_says_so(runs_dir):
    run_id = "20260925_061649"
    _write_forecast(runs_dir, run_id, "TEST", 0.90)                       # would be used only as a fallback
    oi.set_active_run_context(run_id, str(runs_dir / run_id))
    ctx = _production_ctx()
    ctx["_signal_row"]["l3_forward_realised_vol_raw"] = 0.35
    selected = _select(ctx)
    assert selected["contract_value_quality_flag"] == "OK"
    assert selected["contract_value_forecast_source"] == "SIGNAL_ROW_L3"
    assert selected["contract_value_forecast_age_sessions"] == 0


def test_the_lab_book_projection_carries_the_new_fields():
    from contracts import lab_control
    projected = set(lab_control.CONTRACT_VALUE_LAB_FIELDS) if hasattr(lab_control, "CONTRACT_VALUE_LAB_FIELDS") else set()
    source = Path(lab_control.__file__).read_text(encoding="utf-8")
    for field in ("contract_value_forecast_source", "contract_value_forecast_run_id", "contract_value_forecast_age_sessions"):
        assert field in projected or f'"{field}"' in source
