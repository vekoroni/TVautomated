"""Phase 3b: intraday build-up of the move, on the thesis's own levels, in the Morning run (ACK 8 Oct 2026).

Business rules:
- Today's 5-minute bars are checked with the SAME event detector against the thesis's own trigger, invalidation and
  target, plus the session VWAP anchored at the open. The acceptance margin uses the DAILY ATR, so an intraday break
  must be decisive. The legacy Wall-Break trigger is never used.
- The build-up label is ALIGNED (moving the thesis's way), OPPOSED (pushing against it), NONE, or NOT_MEASURED
  (no bars). It is advisory display only: it never changes the Morning verdict, direction or contract.
"""
import numpy as np
import pandas as pd

from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.trigger_events import intraday_buildup

POLICY = load_policy()


def _bars(closes, start="2026-10-08 13:30", spread=0.05, volume=1e5):
    ts = pd.date_range(start, periods=len(closes), freq="5min", tz="UTC")
    c = np.asarray(closes, float)
    return pd.DataFrame({"timestamp_utc": ts, "open": c, "high": c + spread, "low": c - spread, "close": c,
                         "volume": volume})


def test_decisive_break_of_the_trigger_is_aligned_for_its_side():
    r = intraday_buildup(_bars([100.0, 100.2, 100.6, 101.2, 101.5, 101.7]), side="BULL", trigger=100.5,
                         invalidation=98.0, target=106.0, atr_daily=2.0, policy=POLICY)
    assert r["ib_state"] == "ALIGNED" and r["ib_last_event"] in {"BREAK_ACCEPTED_UP", "RETEST_HELD_UP", "VWAP_RECLAIM"}
    assert "BREAK_ACCEPTED_UP" in r["ib_events"]
    assert r["ib_interval"] == "5m" and r["ib_authority"] == "ADVISORY_ONLY"


def test_selling_through_session_vwap_is_opposed_for_a_bull_thesis():
    r = intraday_buildup(_bars([100.0, 100.4, 100.5, 99.8, 99.5]), side="BULL", trigger=None,
                         invalidation=97.0, target=106.0, atr_daily=2.0, policy=POLICY)
    assert r["ib_state"] == "OPPOSED" and r["ib_last_event"] == "VWAP_LOSS"


def test_no_bars_is_not_measured():
    r = intraday_buildup(pd.DataFrame(), side="BULL", trigger=100.5, invalidation=98.0, target=106.0,
                         atr_daily=2.0, policy=POLICY)
    assert r["ib_state"] == "NOT_MEASURED"


def test_no_events_is_none():
    r = intraday_buildup(_bars([100.0, 100.0, 100.0]), side="BEAR", trigger=95.0, invalidation=103.0,
                         target=90.0, atr_daily=2.0, policy=POLICY)
    assert r["ib_state"] == "NONE"


def test_morning_attaches_build_up_without_touching_the_decision():
    import morning_gate as mg
    row = {"ticker": "X", "governed_direction": "CALL", "thesis_trigger_level": 100.5, "invalidation_level": 98.0,
           "structural_target": 106.0, "atr14": 2.0, "morning_gate_verdict": "FLAG", "direction": "CALL",
           "contract_symbol": "X261120C00100000", "trigger_price": 250.0}
    before = {k: row[k] for k in ("morning_gate_verdict", "direction", "contract_symbol")}
    fields = mg._intraday_buildup_fields(row, _bars([100.0, 100.2, 100.6, 101.2, 101.5, 101.7]))
    assert fields["ib_state"] == "ALIGNED"
    assert fields["ib_trigger_source"] == "THESIS_TRIGGER_LEVEL"        # never the legacy trigger_price (250.0)
    assert {k: row[k] for k in before} == before
