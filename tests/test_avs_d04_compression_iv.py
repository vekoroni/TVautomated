"""XLU-D04 (ACK 2 Oct 2026): VOL_COMPRESSION claims "energy stored, options cheap" but checked
only realised range. Business rules:
- Realised compression still fires; the options-cheap half of the premise is checked on the
  pipeline's own implied-vol classification (ivp_label vs the ticker's own history).
- CHEAP/FAIR -> VOL_COMPRESSION (GO-eligible, weight 2.0).
- EXPENSIVE -> VOL_COMPRESSION_IV_RICH; missing label -> VOL_COMPRESSION_IV_UNVERIFIED.
  ACK decision 2 Oct 2026: flag only. The variants stay GO-eligible at the same weight, so GO
  eligibility, primary and quality are unchanged; the trader sees the flag and decides.
- IV/HV is not the test: during compression realised vol is low, so IV/HV is high mechanically.
Evidence (run 20261001_211641): 546 fires; 138 EXPENSIVE, 59 without a label. XLU IVP 0.716.
"""
import trigger_layer as tl

BASE = {"crabel_state": "COILING", "crabel_compression": 0.94, "atr_percentile_rank": 8.3}


def test_cheap_or_fair_options_keep_the_go_eligible_trigger():
    assert tl._t1_vol_compression({**BASE, "ivp_label": "CHEAP"}) == "VOL_COMPRESSION"
    assert tl._t1_vol_compression({**BASE, "ivp_label": "FAIR"}) == "VOL_COMPRESSION"


def test_expensive_options_mark_the_compression_iv_rich():
    assert tl._t1_vol_compression({**BASE, "ivp_label": "EXPENSIVE", "iv_vs_hv": 1.37}) == "VOL_COMPRESSION_IV_RICH"


def test_missing_iv_classification_is_unverified_not_neutral():
    assert tl._t1_vol_compression({**BASE}) == "VOL_COMPRESSION_IV_UNVERIFIED"


def test_iv_variants_are_flags_only_go_eligibility_and_weight_unchanged():
    for name in ("VOL_COMPRESSION_IV_RICH", "VOL_COMPRESSION_IV_UNVERIFIED"):
        assert name in tl.GO_ELIGIBLE_PRIMARIES
        assert tl.TRIGGER_WEIGHTS[name] == tl.TRIGGER_WEIGHTS["VOL_COMPRESSION"]
    from execution_decision_engine import GO_ELIGIBLE_PRIMARIES as edge
    assert {"VOL_COMPRESSION_IV_RICH", "VOL_COMPRESSION_IV_UNVERIFIED"} <= edge


def test_no_compression_still_returns_nothing():
    assert tl._t1_vol_compression({"crabel_state": "EXPANDING", "crabel_compression": 0.95,
                                   "atr_percentile_rank": 80.0, "ivp_label": "CHEAP"}) is None
