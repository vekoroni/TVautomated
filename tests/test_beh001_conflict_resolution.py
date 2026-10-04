"""BEH-001: resolving a two-sided daily reading by timeframe precedence.

Business rules (evidence: Enhancements/outcomes/beh001/eval_v3/two_sided_resolution.json;
positive in both halves of 2022-09..2026-09 and at +/-1, 2, 3 ATR; in-sample replay; switched off in production 3 Oct after the holdout, see last test):
- When daily live candidates point both ways, the highest timeframe above daily with live
  directed candidates sets the side if it is one-sided; the primary is the daily candidate
  on that side (its invalidation is the thesis invalidation).
- Otherwise the side stays UNASSIGNED with the reason stated; Spring and Upthrust/UTAD
  both live on daily is a genuine two-sided range.
- Activation and proximity are not tiebreaks (no evidence; proximity was slightly wrong).
- A one-sided daily reading is unchanged.
"""
from domain.structure_behaviour.engine import handoff_thesis

# The mechanism is tested with its own policy; production switched it off on 3 Oct (last test).
RULE = {"handoff": {"conflict_resolution": "HIGHER_TIMEFRAME_ONE_SIDED", "higher_timeframes": ["1mo", "1w"]}}


def c(tf, side, kind="SOS -> LPS continuation", state="DETECTED", label="2026-09-01"):
    return {"Candidate_ID": f"T|{tf}|CAMPAIGN|{kind}|{label}", "Timeframe": tf, "Direction": side,
            "Signal_State": state, "Signal_Type": kind}


def reading(*cands, status="EVALUATED"):
    return {"Status": status, "candidates": list(cands)}


TWO_SIDED_DAILY = reading(c("1d", "BULL"), c("1d", "BEAR", "SOW -> LPSY continuation", state="ACTIVATED"))


def test_higher_timeframe_one_sided_sets_the_side_with_a_daily_primary():
    h = handoff_thesis({"1mo": reading(), "1w": reading(c("1w", "BULL")), "1d": TWO_SIDED_DAILY}, RULE)
    assert h["thesis__side"] == "BULL"
    assert h["thesis__direction_status"].startswith("RESOLVED_BY_TIMEFRAME:1w")
    assert h["primary"]["Timeframe"] == "1d" and h["primary"]["Direction"] == "BULL"


def test_highest_timeframe_wins_over_a_lower_one():
    h = handoff_thesis({"1mo": reading(c("1mo", "BEAR")), "1w": reading(c("1w", "BULL")), "1d": TWO_SIDED_DAILY}, RULE)
    assert h["thesis__side"] == "BEAR"
    assert h["thesis__direction_status"].startswith("RESOLVED_BY_TIMEFRAME:1mo")


def test_activation_is_not_a_tiebreak():
    h = handoff_thesis({"1mo": reading(), "1w": reading(), "1d": TWO_SIDED_DAILY}, RULE)
    assert h["thesis__side"] == "UNASSIGNED"
    assert h["thesis__unassigned_reason"] == "CONFLICTING_DAILY_CANDIDATES"


def test_two_sided_higher_timeframe_does_not_resolve():
    h = handoff_thesis({"1w": reading(c("1w", "BULL"), c("1w", "BEAR")), "1d": TWO_SIDED_DAILY}, RULE)
    assert h["thesis__side"] == "UNASSIGNED"


def test_range_edges_are_a_stated_two_sided_range():
    daily = reading(c("1d", "BULL", "Spring Candidate"), c("1d", "BEAR", "Upthrust Candidate"))
    h = handoff_thesis({"1w": reading(), "1d": daily}, RULE)
    assert h["thesis__unassigned_reason"] == "RANGE_EDGES_TWO_SIDED"


def test_one_sided_daily_is_unchanged():
    h = handoff_thesis({"1w": reading(c("1w", "BEAR")), "1d": reading(c("1d", "BULL"))}, RULE)
    assert h["thesis__side"] == "BULL"
    assert h["thesis__direction_status"] == "DETECTED:SOS -> LPS continuation"


def test_production_policy_leaves_a_two_sided_daily_unassigned():
    """ACK 3 Oct 2026: the timeframe tiebreak did not replicate on a 500-ticker holdout
    (+0.5 pt vs drift, 95% [-1.0, +2.0]; eval_v4_holdout), so production does not use it.
    The conflict is stated for the trader; the mechanism stays available by configuration."""
    from domain.structure_behaviour.policy import load_policy
    policy = load_policy()
    assert policy["handoff"]["conflict_resolution"] == "NONE"
    h = handoff_thesis({"1mo": reading(), "1w": reading(c("1w", "BULL")), "1d": TWO_SIDED_DAILY}, policy)
    assert h["thesis__side"] == "UNASSIGNED"
    assert h["thesis__unassigned_reason"] == "CONFLICTING_DAILY_CANDIDATES"
