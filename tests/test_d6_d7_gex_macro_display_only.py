"""D6/D7 (ACK, 19 Sep 2026): GEX/wall and macro regime are display-only (rule 6) - never a gate, score or rank.

D6: execution_gate.py scaled position size from GEX/wall signals (WARN_LOW_RUNWAY, WARN_ABOVE_GAMMA,
WARN_TARGET_EXCEEDS_RUNWAY - all derived from gamma_flip/put_wall), affecting 81.6% of rows per the 14 Sep GEX
investigation. The warning stays (manual review); the size penalty is removed.
D7: two unmeasured macro effects removed - the options score's TRANSITIONAL regime -3, and EV v2's regime x
drift-status multiplier (which defaulted an unrecognised drift status to 0.88, biasing EV with no evidence).
"""
from __future__ import annotations

import inspect

import execution_gate as eg
import scripts.avshunter_options_intelligence as oi
import vanguard.ev_engine as ev1
import vanguard.ev_engine_v2 as ev2


def test_gex_wall_warnings_no_longer_scale_execution_size():
    source = inspect.getsource(eg)
    for warning in ("WARN_LOW_RUNWAY", "WARN_ABOVE_GAMMA", "WARN_TARGET_EXCEEDS_RUNWAY"):
        block = source[source.index(f'"{warning}"'):source.index(f'"{warning}"') + 400]
        assert "penalty *=" not in block, warning
        assert warning in block  # the label itself is kept - display only, not silently dropped


def test_options_score_no_longer_penalises_transitional_regime():
    source = inspect.getsource(oi)
    block = source[source.index("regime == 'TRANSITIONAL'"):source.index("regime == 'TRANSITIONAL'") + 300]
    assert "score -= 3" not in block
    assert "not scored" in block.lower() or "display-only" in block.lower()


def test_ev_regime_multiplier_is_neutral():
    for module in (ev1, ev2):
        engine = module.EVEngineV2()
        for regime, drift in (("RISK_OFF", "Flipped"), ("BULLISH", "Stable"), ("UNKNOWN_REGIME", "Undocumented")):
            row = type("Row", (), {"regime_state": regime, "regime_drift_status": drift})()
            assert engine._regime_mult(row) == 1.00, (module.__name__, regime, drift)
