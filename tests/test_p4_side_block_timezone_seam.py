"""Phase 4 / RC01: Vanguard side-evidence blocks survive the real adapter timestamp.

Business rule: the same evidence session gives the same point-in-time cut, whether it arrives as a date string, a
naive datetime or the UTC-aware midnight that orchestrator_adapter actually sends
(datetime.fromisoformat(session).replace(tzinfo=timezone.utc)). Phase 0: every one of 1,702 Vanguard rows failed
with SIDE_BLOCK_ERROR:TypeError because the existing tests only used naive or missing cuts.
"""
from datetime import datetime, timezone

import pandas as pd

from vanguard.layer2_statistical.actuarial_query import load_side_block_policy, side_evidence_blocks


def _sample(n=60):
    dates = pd.bdate_range("2025-01-02", periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({"label_asof_date": dates,
                         **{f"outcome_{h}d_return": [0.02 if i % 3 else -0.01 for i in range(n)]
                            for h in (1, 5, 10, 20, 60)},
                         "outcome_max_gain_20d": 0.05, "outcome_max_drawdown_20d": -0.03})


def _run(as_of):
    policy = load_side_block_policy()
    return side_evidence_blocks(_sample(), as_of=as_of, match_attrs={}, policy=policy)


def test_adapter_utc_midnight_does_not_raise_and_matches_the_date_form():
    adapter_form = datetime.fromisoformat("2026-10-05").replace(tzinfo=timezone.utc)
    a, b, c = _run(adapter_form), _run("2026-10-05"), _run(datetime(2026, 10, 5))
    keys = [k for k in a if k.startswith("side_") or k in ("side_block_status", "side_block_sample_size")]
    assert a["side_block_status"] != "NOT_EVALUATED" or a["side_block_reason"] in ("THIN_SAMPLE", "NO_MATCH")
    assert {k: a[k] for k in keys} == {k: b[k] for k in keys} == {k: c[k] for k in keys}


def test_label_dates_with_timezones_are_compared_as_dates():
    s = _sample()
    s["label_asof_date"] = pd.to_datetime(s["label_asof_date"]).dt.tz_localize("UTC").astype(str)
    policy = load_side_block_policy()
    out = side_evidence_blocks(s, as_of=datetime(2026, 10, 5, tzinfo=timezone.utc), match_attrs={}, policy=policy)
    assert out["side_block_sample_size"] == len(s)
