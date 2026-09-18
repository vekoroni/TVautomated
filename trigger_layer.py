#!/usr/bin/env python3
"""
AVSHUNTER — Trigger Layer v2.2
==============================
Phase 8.6 — sits between Actuarial Enrichment (Phase 8.5) and EDE (Phase 9.5).

Architecture:
    Vanguard → Options Intelligence → EIL → Actuarial Enrichment
        → [THIS MODULE] Trigger Layer
        → EDE v4.1 (EV-primary)
        → Enhancement → Candidates

v2.2 changes (2026-08-28):
    Separate structural context from actual source-data freshness. FAR now means
    EARLY_FORMATION_ABSENT and days_in_range>15 means RANGE_EXTENDED; neither
    suppresses independent T1-T4 observations. Actual stale data is resolved
    only from governed source freshness/age fields, blocks GO eligibility, and
    is commuted alongside context through packages, sidecar, and EIL CSV.

v2.1 changes (2026-04-29):
    Fix 7: _compute_ev — replaced expected_value_10d (dollar EV, negative for most
            signals) with l3_expected_move_6_10d / 100 GARCH fallback chain.
            14/20 signals had wrong ev_sign in trigger block. Now matches EDE v4.1.1.
    Fix 8: _direction — STRANGLE correctly short-circuits to NONE (bidirectional).
            MIXED dominant_trend now falls back to vwap_bias as tiebreaker.
            Recovers direction for ~11% of universe previously returning NONE.
    Fix 9: _is_stale — days_in_range gate now guards against absent field.
            days_in_range only populated for 43% of universe (Crabel-scored signals).
            Absent field no longer treated as 0 (which was passing the >15 gate).
    Fix 10: _t4_trap — pcr_signal absent guard added. pcr only populated for 34%
            of universe. Empty string was being compared to BEARISH/BULLISH, always
            failing but risking silent wrong matches on whitespace edge cases.
    Fix 11: _t1_vol_compression — crabel_state absent handling. crabel_state only
            43% populated. When absent, requires BOTH ratio AND ATR to confirm T1
            (stricter dual gate). When present, original single-confirmation logic.
    Fix 12: enrich_csv() — new function writes trigger columns directly into the
            EIL CSV as flat columns (trigger_codes, trigger_count, trigger_primary,
            trigger_quality, trigger_score, trigger_go_eligible, trigger_stale,
            trigger_ev_10d, trigger_ev_sign). Fixes the pipeline wiring gap where
            EDE could not read trigger data because only package JSONs were patched.

v2.0 changes (2026-04-28):
    Fix 1: VWAP — event detection, not static state.
    Fix 2: RANGE_BREAK split into EARLY and CONFIRMED.
    Fix 3: TRAP requires structure confirmation.
    Fix 4: Trigger quality uses weighted scoring.
    Fix 5: Staleness gate — catalyst_proximity=FAR excluded.
    Fix 6: Primary quality filter — GO requires VOL_COMPRESSION or RANGE_BREAK.
"""

from __future__ import annotations
import json
import logging
import pathlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("trigger_layer")

# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER WEIGHTS — intensity scoring (Fix 4)
# ─────────────────────────────────────────────────────────────────────────────
TRIGGER_WEIGHTS: Dict[str, float] = {
    "VOL_COMPRESSION":      2.0,
    "RANGE_BREAK_EARLY":    1.5,   # ADX rising, momentum building
    "RANGE_BREAK":          2.0,   # confirmed breakout
    "VWAP_RECLAIM":         1.5,
    "VWAP_LOSS":            1.5,
    "TRAP":                 2.5,   # highest weight — hardest to fake
}

# Quality thresholds based on weighted score
QUALITY_STRONG_MIN  = 3.5   # e.g. TRAP alone (2.5) + VWAP (1.5) = 4.0 → STRONG
QUALITY_SINGLE_MIN  = 1.5   # any single trigger passes minimum bar

# GO-eligible primary triggers (Fix 6 — primary quality filter)
GO_ELIGIBLE_PRIMARIES = {"VOL_COMPRESSION", "RANGE_BREAK_EARLY", "RANGE_BREAK", "TRAP"}

# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

# T1 — Volatility Compression
T1_CRABEL_STATES      = {"COILING", "CRABEL_READY", "NR7"}
T1_COMPRESSION_MAX    = 0.45
T1_ATR_PERCENTILE_MAX = 30.0

# T2 — VWAP Reclaim / Rejection (event-based — Fix 1)
T2_VOLUME_RATIO_MIN   = 1.1    # slightly relaxed — event detection is stricter

# T3 — Range Break (split — Fix 2)
T3_EARLY_ADX_MIN      = 18.0   # ADX rising but not yet mature
T3_EARLY_ADX_MAX      = 28.0   # still early — above 28 is confirmed
T3_EARLY_PHASES       = {"C", "D"}   # Wyckoff spring/test → markup
T3_CONF_ADX_MIN       = 25.0   # confirmed breakout
T3_CONF_EMA           = "ALIGNED"
T3_CONF_PHASES        = {"MARKUP", "DISTRIBUTION"}

# T4 — Trap (structure-confirmed — Fix 3)
# Requires PCR contradiction + structure failure evidence

# Trigger context is not data freshness.  FAR means that Discovery did not find
# an early catalyst/compression formation; it does not mean the underlying bars
# are old.  Likewise, days_in_range is setup age, not source-data age.
TRIGGER_MAX_AGE_SESSIONS = 2
_EXPLICIT_STALE_STATES = {"STALE", "STALE_DATA", "EXPIRED", "INVALID_STALE"}
_EXPLICIT_FRESH_STATES = {"FRESH", "CURRENT", "VALID", "OK"}
_FRESHNESS_STATE_FIELDS = (
    "trigger_source_freshness",
    "equity_data_freshness",
    "price_data_freshness",
    "market_data_freshness",
    "data_freshness_status",
)
_FRESHNESS_AGE_FIELDS = (
    "trigger_source_age_sessions",
    "equity_data_age_sessions",
    "price_data_age_sessions",
    "market_data_age_sessions",
)
_FRESHNESS_ASOF_FIELDS = (
    "trigger_source_asof",
    "equity_data_asof",
    "price_data_asof",
    "market_data_asof",
    "source_max_date",
)

# EV threshold
EV_ZERO_THRESHOLD = 1e-8


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _flt(row: Dict, key: str, default: float = 0.0) -> float:
    v = row.get(key)
    if v is None:
        return default
    try:
        import math
        f = float(v)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default


def _volume_ratio(row: Dict) -> float:
    """Today's volume / 20-day average, from the canonical ``volume_ratio`` (Discovery owns it).

    ``volume_ratio_x`` is the name a suffixed Discovery/Vanguard merge once produced; it is read only when the
    canonical field is absent, so archived spines replay unchanged (ACK, 18 Sep 2026).
    """
    canonical = _flt(row, "volume_ratio", float("nan"))
    return canonical if canonical == canonical else _flt(row, "volume_ratio_x", 0.0)


def _str(row: Dict, key: str, default: str = "") -> str:
    v = row.get(key)
    if v is None:
        return default
    s = str(v).strip().upper()
    return default if s in ("", "NONE", "NULL", "NAN") else s


def _direction(row: Dict) -> str:
    """
    FIX-DIRECTION (2026-04-29): STRANGLE options_direction was falling through to NONE.
    STRANGLE = bidirectional, map to NONE intentionally (correct — no directional bias).
    TRANSITION precor_intent was also returning NONE — now falls through to dominant_trend.
    Added MIXED dominant_trend fallback via vwap_bias to recover direction for ~11% of universe.
    """
    for field in ("options_direction", "direction"):
        d = _str(row, field)
        if d in ("CALL", "PUT"):
            return d
        if d == "STRANGLE":
            return "NONE"   # bidirectional — intentionally non-directional

    intent = _str(row, "precor_intent")
    if "BUY" in intent:
        return "CALL"
    if "SELL" in intent:
        return "PUT"
    # TRANSITION intent — fall through to structural signals

    trend = _str(row, "dominant_trend")
    if trend == "BULLISH":
        return "CALL"
    if trend == "BEARISH":
        return "PUT"

    # MIXED trend — use VWAP bias as tiebreaker
    vwap = _str(row, "vwap_bias")
    if vwap == "ABOVE":
        return "CALL"
    if vwap == "BELOW":
        return "PUT"

    return "NONE"


def _parse_date(value: Any) -> Optional[date]:
    if value in (None, "", "nan", "None"):
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text).date()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None


def _business_sessions_between(start: date, end: date) -> int:
    """Weekday session distance; exchange holidays remain upstream governance."""
    if start >= end:
        return 0
    sessions = 0
    cursor = start
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            sessions += 1
    return sessions


def _trigger_context(row: Dict) -> Dict[str, str]:
    """Describe structural setup context without claiming that data is stale."""
    reasons: List[str] = []
    if _str(row, "catalyst_proximity") == "FAR":
        reasons.append("EARLY_FORMATION_ABSENT")
    days_in_range = row.get("days_in_range")
    if days_in_range not in (None, "", "nan", "None"):
        try:
            if float(days_in_range) > 15:
                reasons.append("RANGE_EXTENDED")
        except (TypeError, ValueError):
            reasons.append("RANGE_AGE_INVALID")
    return {
        "state": "|".join(reasons) if reasons else "ELIGIBLE",
        "reasons": "|".join(reasons) if reasons else "NONE",
    }


def _trigger_data_freshness(row: Dict) -> Dict[str, Any]:
    """Resolve actual data age only from explicit freshness evidence.

    `catalyst_proximity`, `days_in_range`, `asof_date`, and `score_date` are
    deliberately excluded as source-age evidence: they describe setup/run
    context.  When no governed source timestamp or status is supplied, UNKNOWN
    is safer and more truthful than fabricating either FRESH or STALE.
    """
    for field in _FRESHNESS_STATE_FIELDS:
        state = _str(row, field)
        if state in _EXPLICIT_STALE_STATES:
            return {"state": "STALE", "asof": "", "age_sessions": "", "reason": f"{field}={state}", "stale": True}
        if state in _EXPLICIT_FRESH_STATES:
            return {"state": "FRESH", "asof": "", "age_sessions": "", "reason": f"{field}={state}", "stale": False}

    for field in _FRESHNESS_AGE_FIELDS:
        value = row.get(field)
        if value not in (None, "", "nan", "None"):
            try:
                age = max(0, int(float(value)))
                stale = age > TRIGGER_MAX_AGE_SESSIONS
                return {
                    "state": "STALE" if stale else "FRESH",
                    "asof": "",
                    "age_sessions": age,
                    "reason": f"{field}={age}",
                    "stale": stale,
                }
            except (TypeError, ValueError):
                continue

    anchor = _parse_date(row.get("asof_date")) or _parse_date(row.get("score_date"))
    if anchor:
        for field in _FRESHNESS_ASOF_FIELDS:
            source_date = _parse_date(row.get(field))
            if source_date:
                age = _business_sessions_between(source_date, anchor)
                stale = age > TRIGGER_MAX_AGE_SESSIONS
                return {
                    "state": "STALE" if stale else "FRESH",
                    "asof": source_date.isoformat(),
                    "age_sessions": age,
                    "reason": f"{field}={source_date.isoformat()}",
                    "stale": stale,
                }

    return {"state": "UNKNOWN", "asof": "", "age_sessions": "", "reason": "NO_EXPLICIT_SOURCE_AGE", "stale": False}


def _is_stale(row: Dict) -> bool:
    """Backward-compatible alias: true only for actual stale source data."""
    return bool(_trigger_data_freshness(row)["stale"])


def _compute_ev(row: Dict) -> float:
    """
    Runtime EV — never stored in database.
    Priority: actuarial block → l3 GARCH forecasts → layer2 win_rate fallback.

    FIX-EV-GARCH (2026-04-29): layer2__expected_value_10d and expected_value_10d
    are DOLLAR EV figures (negative for most signals in bear/transitional regimes).
    They are NOT expected move percentages. Using them as em produced ev_sign=NEGATIVE
    for 14/20 signals that have genuine positive EV when computed correctly.

    Correct formula: EV = win_rate_10d × expected_move_10d (as decimal fraction).
    GARCH layer writes l3_expected_move_6_10d and l3_expected_move_1_5d in % terms
    (e.g. 3.44 = 3.44%) — divide by 100 to convert to decimal.

    Fallback chain:
        1. actuarial.win_rate_10d × actuarial.expected_move_10d  (package JSON path)
        2. win_rate_10d × l3_expected_move_6_10d / 100           (GARCH 6-10d, preferred)
        3. win_rate_10d × l3_expected_move_1_5d / 100            (GARCH 1-5d, fallback)
        4. 0.0 (no data)
    """
    # Path 1: authoritative EV from EIL/EVEngineV2. This is the current
    # field contract from execution_intelligence_runner.py; recompute only
    # when the sovereign EV fields are absent.
    for ev_key in ("ev2_ev_conf_adj", "fd_ev_used", "ev_conf_adj", "eil_ev_net", "ev_final"):
        if ev_key in row and row.get(ev_key) not in (None, "", "nan", "None"):
            try:
                return round(float(row.get(ev_key)), 8)
            except (TypeError, ValueError):
                pass

    # Path 2: nested actuarial block (package JSON mode)
    act = row.get("actuarial", {})
    if isinstance(act, dict) and act:
        wr = _flt(act, "win_rate_10d")
        em = _flt(act, "expected_move_10d")
        if wr and em:
            return round(wr * em, 8)

    # Path 2 & 3: flat CSV mode — use GARCH l3 forecasts (convert % → decimal)
    wr = _flt(row, "layer2__win_rate_10d") or _flt(row, "win_rate_10d")
    if not wr:
        return 0.0

    em_10_fraction = _flt(row, "expected_move_10d_fraction")
    if em_10_fraction:
        return round(wr * em_10_fraction, 8)

    em_6_10 = _flt(row, "l3_expected_move_6_10d")
    if em_6_10:
        return round(wr * (em_6_10 / 100.0), 8)

    em_1_5 = _flt(row, "l3_expected_move_1_5d")
    if em_1_5:
        return round(wr * (em_1_5 / 100.0), 8)

    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER EVALUATORS
# ─────────────────────────────────────────────────────────────────────────────

def _t1_vol_compression(row: Dict) -> Optional[str]:
    """
    T1: Volatility Compression → Expansion
    Energy stored, options cheap. Compression confirmed by Crabel + ATR.

    FIX-T1-CRABEL-MISSING (2026-04-29): crabel_state is only populated for 43%
    of the universe (Crabel-scored signals). When absent, the state_ok gate was
    always False, blocking T1 for 57% of signals regardless of compression ratio
    and ATR percentile rank.

    Resolution: crabel_state gates are applied only when the field is present.
    When absent, the ratio+ATR dual confirmation alone is sufficient for T1.
    This is conservative — both ratio AND ATR must pass when crabel_state is missing.
    When crabel_state IS present, a single confirmation (ratio OR ATR) suffices.
    """
    crabel_state = _str(row, "crabel_state")
    compression  = _flt(row, "crabel_compression", 1.0)
    atr_pct      = _flt(row, "atr_percentile_rank", 100.0)

    ratio_ok = compression < T1_COMPRESSION_MAX
    atr_ok   = atr_pct < T1_ATR_PERCENTILE_MAX

    # crabel_state present: single confirmation sufficient (original logic)
    if crabel_state and crabel_state not in ("NONE",):
        state_ok = crabel_state in T1_CRABEL_STATES
        if state_ok and (ratio_ok or atr_ok):
            return "VOL_COMPRESSION"
        if ratio_ok and atr_ok:
            return "VOL_COMPRESSION"
        return None

    # crabel_state absent: require both ratio AND ATR (stricter gate)
    if ratio_ok and atr_ok:
        return "VOL_COMPRESSION"
    return None


def _t2_vwap_reclaim(row: Dict) -> Optional[str]:
    """
    T2: VWAP Reclaim / Rejection (v2.0 — event detection, not static state)

    Fix 1: The original check (vwap_bias == "ABOVE") detects STATE.
    We now detect the EVENT of reclaim using control_state and layer1 fields.

    For CALL signals:
        vwap_bias=ABOVE (price is above VWAP)
        + control_state=SHIFTING (transition happening)
        + layer1__control__controller=BUYERS (buyers taking control)
        → reclaim event in progress

    For PUT signals:
        vwap_bias=BELOW (price below VWAP)
        + control_state=SHIFTING or SELLERS (control changing or lost)
        + layer1__control__controller=SELLERS (sellers in control)
        → rejection event confirmed

    Note: prev_vwap_bias is not available in EOD batch.
    control_state=SHIFTING + controller change is the EOD-available proxy
    for detecting the moment of crossover rather than just the static state.
    """
    vwap_bias    = _str(row, "vwap_bias")
    control_state = _str(row, "control_state")
    controller   = _str(row, "layer1__control__controller")
    volume_ratio = _volume_ratio(row)
    direction    = _direction(row)

    # CALL setup: reclaim — price crossed above VWAP with buyers taking control
    if (vwap_bias == "ABOVE"
            and control_state == "SHIFTING"
            and controller == "BUYERS"
            and volume_ratio >= T2_VOLUME_RATIO_MIN
            and direction in ("CALL", "NONE")):
        return "VWAP_RECLAIM"

    # PUT setup: rejection — price crossed below VWAP with sellers asserting
    if (vwap_bias == "BELOW"
            and control_state in ("SHIFTING", "SELLERS")
            and controller == "SELLERS"
            and volume_ratio >= T2_VOLUME_RATIO_MIN
            and direction in ("PUT", "NONE")):
        return "VWAP_LOSS"

    return None


def _t3_range_break(row: Dict) -> Optional[str]:
    """
    T3: Range Break (v2.0 — split into EARLY and CONFIRMED)

    Fix 2: The original MARKUP+ALIGNED+ADX>=25 definition detects a mature
    trend — entering AFTER the move. We now split into two triggers:

    RANGE_BREAK_EARLY:
        ADX in 18-28 range (rising, not yet mature) + Wyckoff Phase C or D
        (spring test or initial markup) + MARKUP phase bucket.
        This is the entry BEFORE full trend confirmation — higher risk, higher reward.
        Proxy for adx_14_prev < 20 and adx >= 20.

    RANGE_BREAK (confirmed):
        MARKUP phase + EMA ALIGNED + ADX >= 25.
        Mature trend, lower risk, already moving — institutional confirmation.

    Note: adx_14_prev not available in EOD batch. Phase C/D + ADX 18-28
    is the best available proxy for "ADX just crossed 20".
    """
    phase  = _str(row, "phase")
    bucket = _str(row, "wyckoff_phase_bucket")
    ema    = _str(row, "ema_stack")
    adx    = _flt(row, "adx_14", 0.0)
    vol    = _volume_ratio(row)

    # EARLY: ADX rising into trend threshold, Wyckoff spring/early markup
    if (phase in T3_EARLY_PHASES
            and bucket in ("MARKUP", "ACCUMULATION")
            and T3_EARLY_ADX_MIN <= adx <= T3_EARLY_ADX_MAX):
        return "RANGE_BREAK_EARLY"

    # CONFIRMED: established trend with EMA alignment
    if (bucket in T3_CONF_PHASES
            and ema == T3_CONF_EMA
            and adx >= T3_CONF_ADX_MIN):
        return "RANGE_BREAK"

    # Volume-confirmed breakout substitutes for EMA alignment
    if (bucket in T3_CONF_PHASES
            and adx >= T3_CONF_ADX_MIN
            and vol >= 1.2):
        return "RANGE_BREAK"

    return None


def _t4_trap(row: Dict) -> Optional[str]:
    """
    T4: Trap — failed move with structure confirmation (v2.0)

    Fix 3: PCR contradiction alone is NOT a trap. It is divergence.
    A trap requires the structural foundation to be failing as well.

    FIX-TRAP-PCR (2026-04-29): pcr_signal is only populated for 34% of the universe
    (options-scoped signals only). An empty pcr_signal must not be treated as NEUTRAL
    or matched against "BEARISH"/"BULLISH" checks. Gate returns None when pcr absent.

    Confirmation requires one of:
        - control_state=SELLERS or SHIFTING (structure losing/lost)
        - layer1__auction_state=TRANSITIONING (balance breaking)

    For CALL traps (bull trap):
        BUY_SETUP intent + PCR BEARISH + structure failing
        → institutional selling into retail buying = bull trap

    For PUT traps (bear trap):
        SELL_SETUP intent + PCR BULLISH + structure failing
        → institutional buying into retail selling = bear trap
    """
    pcr = _str(row, "pcr_signal")
    # Guard: pcr absent for 66% of universe — do not fire trap without PCR data
    if not pcr or pcr in ("NEUTRAL", "NONE"):
        return None

    direction     = _direction(row)
    control_state = _str(row, "control_state")
    auction_state = _str(row, "layer1__auction_state")
    intent        = _str(row, "precor_intent")
    controller    = _str(row, "layer1__control__controller")

    # Structure failure confirmation
    structure_failing = (
        control_state in ("SELLERS", "SHIFTING")
        or auction_state == "TRANSITIONING"
    )

    # Bull trap: bullish setup but bearish flow + structure failing
    if ("BUY" in intent
            and pcr == "BEARISH"
            and structure_failing
            and controller == "SELLERS"):
        return "TRAP"

    # Bear trap: bearish setup but bullish flow + structure failing
    if ("SELL" in intent
            and pcr == "BULLISH"
            and structure_failing
            and controller == "BUYERS"):
        return "TRAP"

    # Direction-based check when intent is ambiguous
    if direction == "CALL" and pcr == "BEARISH" and structure_failing and controller == "SELLERS":
        return "TRAP"
    if direction == "PUT" and pcr == "BULLISH" and structure_failing and controller == "BUYERS":
        return "TRAP"

    return None


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHTED QUALITY SCORING (Fix 4)
# ─────────────────────────────────────────────────────────────────────────────

def _trigger_score(triggers: List[str]) -> float:
    """Weighted trigger intensity score."""
    return sum(TRIGGER_WEIGHTS.get(t, 1.0) for t in triggers)


def trigger_quality(triggers: List[str]) -> str:
    """
    STRONG  — weighted score >= 3.5 (e.g. TRAP+VWAP, VOL_COMPRESSION+RANGE_BREAK)
    SINGLE  — weighted score >= 1.5 (any meaningful single trigger)
    NONE    — below threshold
    """
    score = _trigger_score(triggers)
    if score >= QUALITY_STRONG_MIN:
        return "STRONG"
    if score >= QUALITY_SINGLE_MIN:
        return "SINGLE"
    return "NONE"


def trigger_primary(triggers: List[str]) -> str:
    """
    Returns highest-weight trigger. Weighted priority:
    TRAP(2.5) > VOL_COMPRESSION(2.0) = RANGE_BREAK(2.0) > VWAP_RECLAIM/VWAP_LOSS(1.5) = RANGE_BREAK_EARLY(1.5)
    """
    if not triggers:
        return "NONE"
    return max(triggers, key=lambda t: TRIGGER_WEIGHTS.get(t, 1.0))


def is_go_eligible(triggers: List[str]) -> bool:
    """
    Fix 6: GO requires a primary trigger from the high-conviction set.
    VWAP_RECLAIM or VWAP_LOSS alone is not sufficient for GO — each is supportive.
    Primary must be VOL_COMPRESSION, RANGE_BREAK_EARLY, RANGE_BREAK, or TRAP.
    """
    if not triggers:
        return False
    primary = trigger_primary(triggers)
    return primary in GO_ELIGIBLE_PRIMARIES


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_triggers(row: Dict) -> List[str]:
    """
    Evaluate all triggers against a signal row.
    Trigger observations are retained even when source data is explicitly stale;
    capital eligibility is handled separately in build_trigger_block().
    """
    triggers = []

    t1 = _t1_vol_compression(row)
    if t1:
        triggers.append(t1)

    t2 = _t2_vwap_reclaim(row)
    if t2:
        triggers.append(t2)

    t3 = _t3_range_break(row)
    if t3:
        triggers.append(t3)

    t4 = _t4_trap(row)
    if t4:
        triggers.append(t4)

    return triggers


def trigger_summary(row: Dict) -> str:
    t = evaluate_triggers(row)
    return "|".join(t) if t else "NONE"


def build_trigger_block(row: Dict) -> Dict[str, Any]:
    """
    Build the complete trigger block for injection into package JSON.
    """
    triggers    = evaluate_triggers(row)
    ev          = _compute_ev(row)
    score       = _trigger_score(triggers)
    quality     = trigger_quality(triggers)
    primary     = trigger_primary(triggers)
    freshness   = _trigger_data_freshness(row)
    context     = _trigger_context(row)
    go_eligible = is_go_eligible(triggers) and not freshness["stale"]

    return {
        "codes":        "|".join(triggers) if triggers else "NONE",
        "count":        len(triggers),
        "quality":      quality,
        "primary":      primary,
        "score":        round(score, 2),
        "go_eligible":  go_eligible,
        "stale":        freshness["stale"],
        "freshness_state": freshness["state"],
        "data_asof":    freshness["asof"],
        "age_sessions": freshness["age_sessions"],
        "freshness_reason": freshness["reason"],
        "context_state": context["state"],
        "context_reasons": context["reasons"],
        "ev_10d":       ev,
        "ev_sign": (
            "POSITIVE" if ev > EV_ZERO_THRESHOLD
            else "NEGATIVE" if ev < -EV_ZERO_THRESHOLD
            else "ZERO"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CSV ENRICHMENT — writes trigger columns into EIL/superbrain flat CSV
# FIX-WIRING-GAP (2026-04-29): trigger_layer previously only patched package
# JSONs. EDE reads the EIL CSV — trigger columns were never present there,
# so ede_trigger_count=0 for every signal and sovereign gate fired WAIT for all.
# This function enriches the CSV in-place with trigger columns so EDE can read them.
# ─────────────────────────────────────────────────────────────────────────────

TRIGGER_CSV_COLUMNS = [
    "trigger_codes",
    "trigger_count",
    "trigger_primary",
    "trigger_quality",
    "trigger_score",
    "trigger_go_eligible",
    "trigger_stale",
    "trigger_freshness_state",
    "trigger_data_asof",
    "trigger_age_sessions",
    "trigger_freshness_reason",
    "trigger_context_state",
    "trigger_context_reasons",
    "trigger_ev_10d",
    "trigger_ev_sign",
]


def _load_package_trigger_map(input_path: pathlib.Path) -> Dict[str, Dict[str, Any]]:
    """
    Best-effort bridge from Phase 8.6 package mode to Phase 8.6b CSV mode.

    The EIL CSV is intentionally narrow and may not carry every raw field used
    by trigger evaluators. Package JSONs are patched first and already contain
    the canonical trigger block, so CSV enrichment should reuse it when present
    and only recompute triggers from flat fields as a fallback.
    """
    try:
        parts = list(input_path.parts)
        run_idx = next((i for i, part in enumerate(parts) if part == "runs" and i + 1 < len(parts)), None)
        if run_idx is None:
            return {}
        run_dir = pathlib.Path(*parts[: run_idx + 2])
        sidecar = run_dir / f"trigger_layer_summary_{run_dir.name}.csv"
        if not sidecar.exists():
            return {}
        import csv as _csv
        out: Dict[str, Dict[str, Any]] = {}
        with open(sidecar, newline="", encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                ticker = str(row.get("ticker", "")).strip().upper()
                if not ticker:
                    continue
                out[ticker] = {
                    "codes": row.get("trigger_codes", "NONE"),
                    "count": row.get("trigger_count", 0),
                    "quality": row.get("trigger_quality", "NONE"),
                    "primary": row.get("trigger_primary", "NONE"),
                    "score": row.get("trigger_score", 0),
                    "go_eligible": row.get("trigger_go_eligible", False),
                    "stale": row.get("trigger_stale", False),
                    "freshness_state": row.get("trigger_freshness_state", "UNKNOWN"),
                    "data_asof": row.get("trigger_data_asof", ""),
                    "age_sessions": row.get("trigger_age_sessions", ""),
                    "freshness_reason": row.get("trigger_freshness_reason", "NO_EXPLICIT_SOURCE_AGE"),
                    "context_state": row.get("trigger_context_state", "ELIGIBLE"),
                    "context_reasons": row.get("trigger_context_reasons", "NONE"),
                }
        return out
    except Exception:
        return {}


def _trigger_block_from_package(row: Dict[str, Any], pkg_trigger: Dict[str, Any]) -> Dict[str, Any]:
    """Reuse package trigger classification but refresh EV from the EIL row."""
    ev = _compute_ev(row)
    codes = str(pkg_trigger.get("codes") or "NONE")
    count = int(_flt(pkg_trigger, "count", 0.0))
    quality = str(pkg_trigger.get("quality") or "NONE")
    primary = str(pkg_trigger.get("primary") or "NONE")
    if codes in ("", "NONE"):
        trigger_list: List[str] = []
    else:
        trigger_list = [c for c in codes.split("|") if c and c != "NONE"]
    if count <= 0:
        count = len(trigger_list)
    if quality in ("", "NONE") and trigger_list:
        quality = trigger_quality(trigger_list)
    if primary in ("", "NONE") and trigger_list:
        primary = trigger_primary(trigger_list)
    go_raw = pkg_trigger.get("go_eligible", False)
    go_eligible = go_raw if isinstance(go_raw, bool) else str(go_raw).strip().upper() in {"TRUE", "1", "YES"}
    stale_raw = pkg_trigger.get("stale", False)
    stale = stale_raw if isinstance(stale_raw, bool) else str(stale_raw).strip().upper() in {"TRUE", "1", "YES"}
    freshness_state = str(pkg_trigger.get("freshness_state") or ("STALE" if stale else "UNKNOWN")).strip().upper()
    stale = bool(stale) or freshness_state == "STALE"
    return {
        "codes": codes,
        "count": count,
        "quality": quality or "NONE",
        "primary": primary or "NONE",
        "score": round(_flt(pkg_trigger, "score", _trigger_score(trigger_list)), 2),
        "go_eligible": bool(go_eligible) and not bool(stale),
        "stale": bool(stale),
        "freshness_state": freshness_state,
        "data_asof": pkg_trigger.get("data_asof", ""),
        "age_sessions": pkg_trigger.get("age_sessions", ""),
        "freshness_reason": str(pkg_trigger.get("freshness_reason") or "NO_EXPLICIT_SOURCE_AGE"),
        "context_state": str(pkg_trigger.get("context_state") or "ELIGIBLE"),
        "context_reasons": str(pkg_trigger.get("context_reasons") or "NONE"),
        "ev_10d": ev,
        "ev_sign": (
            "POSITIVE" if ev > EV_ZERO_THRESHOLD
            else "NEGATIVE" if ev < -EV_ZERO_THRESHOLD
            else "ZERO"
        ),
    }


def enrich_csv(
    input_csv_path,
    output_csv_path=None,
    inplace: bool = True,
) -> Dict[str, int]:
    """
    Enrich a flat EIL/superbrain CSV with trigger block columns.

    Reads the CSV, evaluates triggers for every row, appends trigger_* columns,
    and writes back. If inplace=True (default) overwrites the input file.
    If output_csv_path is provided, writes to that path regardless of inplace.

    Returns stats dict matching patch_run_packages format for orchestrator compatibility.

    Usage in orchestrator (Phase 8.6, before EDE Phase 9.5):

        from trigger_layer import enrich_csv
        stats = enrich_csv(
            input_csv_path = sb_dir / f"eil_enriched_{run_id}.csv",
            inplace        = True,
        )
        log.info("Trigger Layer: %d GO eligible | %d strong | %d stale filtered",
                 stats['go_eligible'], stats['trigger_strong'], stats['stale_filtered'])
    """
    import csv as _csv

    input_path  = pathlib.Path(input_csv_path)
    output_path = pathlib.Path(output_csv_path) if output_csv_path else input_path

    if not input_path.exists():
        log.warning("enrich_csv: input not found — %s", input_path)
        return {"patched": 0, "error": "FILE_NOT_FOUND"}

    # Read
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        original_fieldnames = reader.fieldnames or []
        rows = [dict(r) for r in reader]
    package_triggers = _load_package_trigger_map(input_path)

    if not rows:
        log.warning("enrich_csv: empty CSV — %s", input_path)
        return {"patched": 0, "error": "EMPTY_CSV"}

    # Build output fieldnames — append trigger columns (skip any already present)
    new_cols = [c for c in TRIGGER_CSV_COLUMNS if c not in original_fieldnames]
    out_fieldnames = list(original_fieldnames) + new_cols

    stats = {
        "patched": 0,
        "trigger_none": 0,
        "trigger_single": 0,
        "trigger_strong": 0,
        "go_eligible": 0,
        "stale_filtered": 0,
        "context_flagged": 0,
        "ev_positive": 0,
        "ev_negative": 0,
        "ev_zero": 0,
    }

    # Enrich each row
    enriched = []
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        pkg_trigger = package_triggers.get(ticker)
        tb = _trigger_block_from_package(row, pkg_trigger) if pkg_trigger else build_trigger_block(row)
        row["trigger_codes"]      = tb["codes"]
        row["trigger_count"]      = tb["count"]
        row["trigger_primary"]    = tb["primary"]
        row["trigger_quality"]    = tb["quality"]
        row["trigger_score"]      = round(tb["score"], 2)
        row["trigger_go_eligible"]= tb["go_eligible"]
        row["trigger_stale"]      = tb["stale"]
        row["trigger_freshness_state"] = tb["freshness_state"]
        row["trigger_data_asof"] = tb["data_asof"]
        row["trigger_age_sessions"] = tb["age_sessions"]
        row["trigger_freshness_reason"] = tb["freshness_reason"]
        row["trigger_context_state"] = tb["context_state"]
        row["trigger_context_reasons"] = tb["context_reasons"]
        row["trigger_ev_10d"]     = round(tb["ev_10d"], 8)
        row["trigger_ev_sign"]    = tb["ev_sign"]
        enriched.append(row)

        stats["patched"] += 1
        if tb.get("stale"):
            stats["stale_filtered"] += 1
        if tb.get("context_state") != "ELIGIBLE":
            stats["context_flagged"] += 1
        q = tb["quality"]
        if q == "STRONG":
            stats["trigger_strong"] += 1
        elif q == "SINGLE":
            stats["trigger_single"] += 1
        else:
            stats["trigger_none"] += 1
        if tb.get("go_eligible"):
            stats["go_eligible"] += 1
        ev_sign = tb["ev_sign"]
        if ev_sign == "POSITIVE":
            stats["ev_positive"] += 1
        elif ev_sign == "NEGATIVE":
            stats["ev_negative"] += 1
        else:
            stats["ev_zero"] += 1

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    log.info(
        "Trigger Layer enrich_csv — %d rows enriched | "
        "STRONG=%d SINGLE=%d NONE=%d | GO=%d | data_stale=%d | context=%d | EV+=%d EV-=%d → %s",
        stats["patched"],
        stats["trigger_strong"],
        stats["trigger_single"],
        stats["trigger_none"],
        stats["go_eligible"],
        stats["stale_filtered"],
        stats["context_flagged"],
        stats["ev_positive"],
        stats["ev_negative"],
        output_path.name,
    )
    return stats

def patch_package(pkg: Dict, vanguard_row: Optional[Dict] = None) -> Dict:
    if vanguard_row is not None:
        src = vanguard_row
    elif "vanguard" in pkg and isinstance(pkg["vanguard"], dict):
        src = pkg["vanguard"]
    else:
        src = pkg
    pkg["triggers"] = build_trigger_block(src)
    return pkg


def patch_run_packages(
    run_id: str,
    base_dir,
    vanguard_csv_path=None,
) -> Dict[str, int]:
    """
    Batch-patch all package JSONs in a run directory with trigger blocks.
    """
    base_dir = pathlib.Path(base_dir)
    pkg_dir  = base_dir / "data" / "output" / "runs" / run_id / "packages"

    if not pkg_dir.exists():
        log.warning("Trigger Layer: package directory not found — %s", pkg_dir)
        return {"patched": 0}

    vanguard_map: Dict[str, Dict] = {}
    if vanguard_csv_path:
        try:
            import csv
            vp = pathlib.Path(vanguard_csv_path)
            if vp.exists():
                with open(vp, encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        t = str(row.get("ticker", "")).strip().upper()
                        if t:
                            vanguard_map[t] = row
                log.info("Trigger Layer: loaded %d vanguard rows", len(vanguard_map))
        except Exception as e:
            log.warning("Trigger Layer: could not load vanguard CSV — %s", e)

    stats = {
        "patched": 0,
        "trigger_none": 0,
        "trigger_single": 0,
        "trigger_strong": 0,
        "go_eligible": 0,
        "stale_filtered": 0,
        "context_flagged": 0,
        "ev_positive": 0,
        "ev_negative": 0,
        "ev_zero": 0,
    }

    sidecar_rows: List[Dict[str, Any]] = []

    for pkg_path in sorted(pkg_dir.glob("*.package.json")):
        try:
            with open(pkg_path, encoding="utf-8") as f:
                pkg = json.load(f)
            ticker       = str(pkg.get("ticker", "")).strip().upper()
            vanguard_row = vanguard_map.get(ticker)
            patch_package(pkg, vanguard_row)
            with open(pkg_path, "w", encoding="utf-8") as f:
                json.dump(pkg, f, indent=2)

            stats["patched"] += 1
            trig = pkg["triggers"]
            if trig.get("stale"):
                stats["stale_filtered"] += 1
            if trig.get("context_state") != "ELIGIBLE":
                stats["context_flagged"] += 1
            q = trig["quality"]
            if q == "STRONG":
                stats["trigger_strong"] += 1
            elif q == "SINGLE":
                stats["trigger_single"] += 1
            else:
                stats["trigger_none"] += 1
            if trig.get("go_eligible"):
                stats["go_eligible"] += 1
            ev_sign = trig["ev_sign"]
            if ev_sign == "POSITIVE":
                stats["ev_positive"] += 1
            elif ev_sign == "NEGATIVE":
                stats["ev_negative"] += 1
            else:
                stats["ev_zero"] += 1

            sidecar_rows.append({
                "ticker": ticker,
                "trigger_codes": trig.get("codes", "NONE"),
                "trigger_count": trig.get("count", 0),
                "trigger_primary": trig.get("primary", "NONE"),
                "trigger_quality": trig.get("quality", "NONE"),
                "trigger_score": trig.get("score", 0),
                "trigger_go_eligible": trig.get("go_eligible", False),
                "trigger_stale": trig.get("stale", False),
                "trigger_freshness_state": trig.get("freshness_state", "UNKNOWN"),
                "trigger_data_asof": trig.get("data_asof", ""),
                "trigger_age_sessions": trig.get("age_sessions", ""),
                "trigger_freshness_reason": trig.get("freshness_reason", "NO_EXPLICIT_SOURCE_AGE"),
                "trigger_context_state": trig.get("context_state", "ELIGIBLE"),
                "trigger_context_reasons": trig.get("context_reasons", "NONE"),
            })

        except Exception as e:
            log.warning("Trigger Layer: failed to patch %s — %s", pkg_path.name, e)

    log.info(
        "Trigger Layer v2.2 complete — %d patched | "
        "STRONG=%d SINGLE=%d NONE=%d | GO_ELIGIBLE=%d | "
        "data_stale=%d | context=%d | EV+=%d EV-=%d",
        stats["patched"],
        stats["trigger_strong"],
        stats["trigger_single"],
        stats["trigger_none"],
        stats["go_eligible"],
        stats["stale_filtered"],
        stats["context_flagged"],
        stats["ev_positive"],
        stats["ev_negative"],
    )
    if sidecar_rows:
        try:
            import csv as _csv
            sidecar_path = pkg_dir.parent / f"trigger_layer_summary_{run_id}.csv"
            with open(sidecar_path, "w", newline="", encoding="utf-8") as f:
                fieldnames = [
                    "ticker", "trigger_codes", "trigger_count", "trigger_primary",
                    "trigger_quality", "trigger_score", "trigger_go_eligible",
                    "trigger_stale",
                    "trigger_freshness_state", "trigger_data_asof",
                    "trigger_age_sessions", "trigger_freshness_reason",
                    "trigger_context_state", "trigger_context_reasons",
                ]
                writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(sidecar_rows)
            log.info("Trigger Layer sidecar written -> %s", sidecar_path)
        except Exception as e:
            log.warning("Trigger Layer: failed to write sidecar CSV - %s", e)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE RUNNER
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser(description="AVSHUNTER Trigger Layer v2.2")
    subparsers = parser.add_subparsers(dest="command")

    # patch: original package JSON patching mode
    p_patch = subparsers.add_parser("patch", help="Patch package JSONs in a run directory")
    p_patch.add_argument("--run_id",       required=True)
    p_patch.add_argument("--base_dir",     default=".")
    p_patch.add_argument("--vanguard_csv", default=None)

    # enrich: new CSV enrichment mode (primary mode for EDE pipeline)
    p_enrich = subparsers.add_parser("enrich", help="Enrich EIL/superbrain CSV with trigger columns")
    p_enrich.add_argument("--input_csv",  required=True, help="Path to EIL enriched CSV")
    p_enrich.add_argument("--output_csv", default=None,  help="Output path (default: overwrite input)")

    # Legacy: bare args default to patch mode for backward compat
    parser.add_argument("--run_id",       default=None)
    parser.add_argument("--base_dir",     default=".")
    parser.add_argument("--vanguard_csv", default=None)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRIGGER] %(message)s", datefmt="%H:%M:%S")

    # Determine mode
    if args.command == "enrich" or (args.command is None and not args.run_id and hasattr(args, 'input_csv')):
        stats = enrich_csv(
            input_csv_path  = args.input_csv,
            output_csv_path = args.output_csv,
            inplace         = True,
        )
    else:
        run_id = args.run_id if args.command is None else getattr(args, 'run_id', None)
        if not run_id:
            parser.print_help()
            sys.exit(1)
        base_dir     = args.base_dir if args.command is None else getattr(args, 'base_dir', '.')
        vanguard_csv = args.vanguard_csv if args.command is None else getattr(args, 'vanguard_csv', None)
        stats = patch_run_packages(run_id, base_dir, vanguard_csv)

    total = max(stats.get("patched", 1), 1)
    print("\nTRIGGER LAYER v2.2 RESULTS")
    print(f"  Rows/packages     : {stats.get('patched', 0)}")
    print(f"  Data stale        : {stats.get('stale_filtered', 0)} ({stats.get('stale_filtered',0)/total*100:.1f}%)")
    print(f"  Context flagged   : {stats.get('context_flagged', 0)}")
    print(f"  STRONG (weighted) : {stats.get('trigger_strong', 0)}")
    print(f"  SINGLE            : {stats.get('trigger_single', 0)}")
    print(f"  NONE              : {stats.get('trigger_none', 0)}")
    print(f"  GO eligible       : {stats.get('go_eligible', 0)}")
    print(f"  EV positive       : {stats.get('ev_positive', 0)} ({stats.get('ev_positive',0)/total*100:.1f}%)")
    sys.exit(0)
