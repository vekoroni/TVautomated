"""DIR-002 §4.6.3 V-A / VNG-03, VNG-05, VNG-17: side-correct descriptive blocks.

Business rules:
- Vanguard publishes BULL and BEAR blocks from one side-parameterised rule over
  the same matched cohort; reflecting the cohort's forward paths swaps them.
- Only labels observable before the evidence session (minus a 20-session
  embargo) enter; a missing as-of cut is NOT_EVALUATED, never "all history".
- An empty or thin cohort is NOT_EVALUATED(NO_MATCH), never measured zeros.
- Every V-A field is SHADOW_DESCRIPTIVE_ONLY with an explicit metric basis.
"""
import math

import numpy as np
import pandas as pd
import pytest

from vanguard.layer2_statistical.actuarial_query import (
    load_side_block_policy,
    side_evidence_blocks,
)

POLICY = load_side_block_policy()


def cohort(n=200, seed=3, start="2024-01-02"):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "ticker": "X", "date": pd.bdate_range(start, periods=n),
    })
    frame["label_asof_date"] = frame["date"] + pd.offsets.BDay(20)
    for h in (5, 10, 20):
        log_ret = rng.normal(0.003 * h ** 0.5, 0.02 * h ** 0.5, n)
        up = np.abs(rng.normal(0, 0.02 * h ** 0.5, n)) + np.maximum(log_ret, 0)
        down = -np.abs(rng.normal(0, 0.02 * h ** 0.5, n)) + np.minimum(log_ret, 0)
        frame[f"outcome_{h}d_return"] = np.expm1(log_ret)
        frame[f"outcome_max_gain_{h}d"] = np.expm1(up)
        frame[f"outcome_max_drawdown_{h}d"] = np.expm1(down)
    return frame


def reflect(frame):
    out = frame.copy()
    for h in (5, 10, 20):
        out[f"outcome_{h}d_return"] = 1.0 / (1.0 + frame[f"outcome_{h}d_return"]) - 1.0
        out[f"outcome_max_gain_{h}d"] = 1.0 / (1.0 + frame[f"outcome_max_drawdown_{h}d"]) - 1.0
        out[f"outcome_max_drawdown_{h}d"] = 1.0 / (1.0 + frame[f"outcome_max_gain_{h}d"]) - 1.0
    return out


ATTRS = {"state_match_method": "EXACT", "state_match_is_exact": True, "state_match_dimensions": "a|b"}
AS_OF = pd.Timestamp("2026-09-25")


def test_reflected_cohort_swaps_bull_and_bear_blocks():
    original = side_evidence_blocks(cohort(), as_of=AS_OF, match_attrs=ATTRS, policy=POLICY)
    mirrored = side_evidence_blocks(reflect(cohort()), as_of=AS_OF, match_attrs=ATTRS, policy=POLICY)
    assert original["side_block_status"] == "SHADOW_DESCRIPTIVE_ONLY"
    for key, value in original.items():
        if not key.startswith("side_bull__"):
            continue
        twin = key.replace("side_bull__", "side_bear__")
        if "signed_mean_return_close" in key:
            continue  # arithmetic returns transform nonlinearly (design §4.6.3)
        if isinstance(value, float):
            assert math.isclose(value, mirrored[twin], rel_tol=1e-9, abs_tol=1e-12), key
        else:
            assert value == mirrored[twin], key


def test_log_mean_is_exactly_antisymmetric_and_bases_are_labelled():
    blocks = side_evidence_blocks(cohort(), as_of=AS_OF, match_attrs=ATTRS, policy=POLICY)
    for h in (5, 10, 20):
        bull = blocks[f"side_bull__signed_mean_log_return_close_{h}d"]
        bear = blocks[f"side_bear__signed_mean_log_return_close_{h}d"]
        assert math.isclose(bull, -bear, rel_tol=1e-12)
        assert blocks[f"side_bull__p_close_favourable_{h}d_basis"] == "CLOSE_TO_CLOSE"
    assert blocks["side_bull__p_touch_favourable_k0_basis"] == "TOUCH_ONLY_UNORDERED"


def test_labels_not_observable_before_the_cut_are_excluded():
    frame = cohort(start="2026-08-03", n=60)
    blocks = side_evidence_blocks(frame, as_of=pd.Timestamp("2026-09-25"), match_attrs=ATTRS, policy=POLICY)
    assert blocks["side_block_sample_size"] < 60
    assert blocks["side_block_excluded_not_observable"] > 0


def test_missing_as_of_is_not_evaluated_not_all_history():
    blocks = side_evidence_blocks(cohort(), as_of=None, match_attrs=ATTRS, policy=POLICY)
    assert blocks["side_block_status"] == "NOT_EVALUATED"
    assert blocks["side_block_reason"] == "AS_OF_MISSING"
    assert blocks["side_bull__p_close_favourable_20d"] is None


@pytest.mark.parametrize("frame", [pd.DataFrame(), cohort(n=5)])
def test_empty_or_thin_cohort_is_not_a_measured_zero(frame):
    blocks = side_evidence_blocks(frame, as_of=AS_OF, match_attrs=ATTRS, policy=POLICY)
    assert blocks["side_block_status"] == "NOT_EVALUATED"
    assert blocks["side_block_reason"] in {"NO_MATCH", "THIN_SAMPLE"}
    assert blocks["side_bear__p_close_favourable_20d"] is None
    assert blocks["side_bull__signed_mean_log_return_close_20d"] is None


def test_dropped_match_dimensions_are_not_exact():
    attrs = {"state_match_method": "RELAXED", "state_match_is_exact": False,
             "state_match_dimensions": "a"}
    blocks = side_evidence_blocks(cohort(), as_of=AS_OF, match_attrs=attrs, policy=POLICY)
    assert blocks["side_block_is_exact"] is False
    assert blocks["side_block_match_method"] == "RELAXED"
