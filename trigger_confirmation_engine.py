from __future__ import annotations

"""
AVSHUNTER — Trigger Confirmation Engine v1.0
===========================================

Purpose
-------
This module answers one sovereign question only:

    "Has the move actually started?"

It is the missing event-confirmation layer between:
    1. EOD structural setup selection, and
    2. Morning live tradeability / options economics validation.

Why this exists
---------------
The current AVSHUNTER stack is strong at:
- finding structurally primed setups,
- validating live execution quality,
- pricing options and sizing positions.

But those layers can still monetise anticipation rather than confirmation.
This engine is designed to reduce early-entry errors by requiring explicit
price/volume behaviour that proves control of the tape has shifted.

Design principles
-----------------
1. Event-based, not proxy-based.
2. Trigger logic is separate from setup logic.
3. Tradeability is separate from confirmation.
4. Harder to get EXECUTE than PROBE.
5. Unknown data degrades score; it does not hallucinate certainty.
6. Output must be audit-friendly and easy to journal.

Typical placement
-----------------
morning_validation_engine.py should call this AFTER it has:
- loaded the EOD candidate manifest,
- fetched live stock/option data,
- built or loaded recent 1m/5m/15m bars.

Recommended flow:
    EOD Setup Score (SCS)
        -> Morning Validation Score (MVS)
        -> Trigger Confirmation Score (TCS)   <-- this module
        -> EV / PSE / Kelly / Trade Book

Suggested decision fusion
-------------------------
- EXECUTE:  MVS strong AND TCS confirmed
- PROBE:    MVS acceptable AND TCS partial
- WATCH:    setup valid but TCS not yet live
- REJECT:   execution poor OR trigger failed OR thesis invalidated

This module is intentionally ticker-agnostic and direction-aware.
Long calls and long puts are both supported, although PUT logic is the primary
focus for the current AVSHUNTER use case.
"""

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Iterable, Optional


# =============================================================================
# ENUMS / CONSTANTS
# =============================================================================

class TriggerState(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    NOT_READY = "NOT_READY"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"
    DATA_WEAK = "DATA_WEAK"


class EntryType(str, Enum):
    BREAKDOWN = "BREAKDOWN"
    BREAK_RETEST = "BREAK_RETEST"
    EARLY_PROBE = "EARLY_PROBE"
    MOMENTUM_CONTINUATION = "MOMENTUM_CONTINUATION"
    NONE = "NONE"


class TradeBias(str, Enum):
    PUT = "PUT"
    CALL = "CALL"


DEFAULT_WEIGHTS = {
    "support_or_resistance_break": 24.0,
    "two_bar_hold": 18.0,
    "failed_reclaim_or_failed_pullback": 18.0,
    "lower_high_or_higher_low_after_break": 12.0,
    "vwap_confirmation": 10.0,
    "volume_expansion": 10.0,
    "opening_range_confirmation": 8.0,
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TriggerComponent:
    name: str
    passed: Optional[bool]
    score_awarded: float
    max_score: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TriggerInput:
    ticker: str
    direction: str  # PUT / CALL

    # EOD / manifest inputs
    signal_price: Optional[float] = None
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    structural_tier: str = ""
    scs_score: Optional[float] = None

    # Live spot context
    current_price: Optional[float] = None
    live_vwap: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None

    # Live bars — newest bar last
    bars_1m: list[dict[str, Any]] = field(default_factory=list)
    bars_5m: list[dict[str, Any]] = field(default_factory=list)
    bars_15m: list[dict[str, Any]] = field(default_factory=list)

    # Volume context
    rvol: Optional[float] = None
    avg_bar_volume_5m: Optional[float] = None

    # Execution context hooks
    live_spread_pct: Optional[float] = None
    live_option_mid: Optional[float] = None
    live_iv: Optional[float] = None

    # Optional diagnostic fields
    session_minutes_elapsed: Optional[int] = None


@dataclass
class TriggerResult:
    ticker: str
    direction: str
    trigger_state: str
    trigger_score: float
    entry_type: str
    confirmed_components: int
    possible_components: int
    data_quality_score: float
    key_level: Optional[float]
    invalidation_level: Optional[float]
    trigger_reason: str
    summary_line: str
    components: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# =============================================================================
# HELPERS
# =============================================================================

def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        f = float(value)
        if f != f:  # NaN guard
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _bar_get(bar: dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    return _safe_float(bar.get(key), default)


def _bar_close(bar: dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("close") or bar.get("c"))


def _bar_open(bar: dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("open") or bar.get("o"))


def _bar_high(bar: dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("high") or bar.get("h"))


def _bar_low(bar: dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("low") or bar.get("l"))


def _bar_volume(bar: dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("volume") or bar.get("v"))


def _take_last(items: Iterable[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    seq = list(items)
    if n <= 0:
        return []
    return seq[-n:]


def _median(values: list[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    m = len(vals)
    mid = m // 2
    if m % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


# =============================================================================
# ENGINE
# =============================================================================

class TriggerConfirmationEngine:
    """
    Event-confirmation engine for AVSHUNTER.

    Primary focus:
      - PUT setups: breakdown, hold, reclaim failure, downside volume
      - CALL setups: mirrored logic for upside confirmation

    Trigger logic is intentionally conservative:
      - EXECUTE-grade confirmation should be rare and earned.
      - PARTIAL confirmation should be common for stalk candidates.
      - NOT_READY should be acceptable when the structural idea remains valid.
    """

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        min_confirmed_for_partial: int = 2,
        min_confirmed_for_confirmed: int = 4,
        volume_expansion_threshold: float = 1.30,
        vwap_proximity_pct: float = 0.005,
        reclaim_tolerance_pct: float = 0.0015,
        break_tolerance_pct: float = 0.0010,
    ):
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.min_confirmed_for_partial = min_confirmed_for_partial
        self.min_confirmed_for_confirmed = min_confirmed_for_confirmed
        self.volume_expansion_threshold = float(volume_expansion_threshold)
        self.vwap_proximity_pct = float(vwap_proximity_pct)
        self.reclaim_tolerance_pct = float(reclaim_tolerance_pct)
        self.break_tolerance_pct = float(break_tolerance_pct)

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def evaluate(self, ti: TriggerInput) -> TriggerResult:
        direction = str(ti.direction or "").upper().strip()
        if direction not in (TradeBias.PUT.value, TradeBias.CALL.value):
            direction = TradeBias.PUT.value

        components: list[TriggerComponent] = []

        bars_5m = list(ti.bars_5m or [])
        bars_1m = list(ti.bars_1m or [])
        bars_15m = list(ti.bars_15m or [])

        level = ti.support_level if direction == TradeBias.PUT.value else ti.resistance_level
        opposite_level = ti.resistance_level if direction == TradeBias.PUT.value else ti.support_level

        data_quality = self._data_quality_score(ti)

        if ti.current_price is None and bars_5m:
            ti.current_price = _bar_close(bars_5m[-1])

        # 1. Core break condition
        components.append(
            self._support_or_resistance_break(
                direction=direction,
                level=level,
                current_price=ti.current_price,
                bars_5m=bars_5m,
            )
        )

        # 2. Hold beyond broken level (2 bars)
        components.append(
            self._two_bar_hold(
                direction=direction,
                level=level,
                bars_5m=bars_5m,
            )
        )

        # 3. Failed reclaim / failed pullback
        components.append(
            self._failed_reclaim_or_failed_pullback(
                direction=direction,
                level=level,
                bars_1m=bars_1m,
                bars_5m=bars_5m,
            )
        )

        # 4. Lower high / higher low after break
        components.append(
            self._lower_high_or_higher_low_after_break(
                direction=direction,
                level=level,
                bars_1m=bars_1m,
                bars_5m=bars_5m,
            )
        )

        # 5. VWAP confirmation
        components.append(
            self._vwap_confirmation(
                direction=direction,
                current_price=ti.current_price,
                live_vwap=ti.live_vwap,
            )
        )

        # 6. Volume expansion
        components.append(
            self._volume_expansion(
                direction=direction,
                bars_5m=bars_5m,
                avg_bar_volume_5m=ti.avg_bar_volume_5m,
                rvol=ti.rvol,
            )
        )

        # 7. Opening range confirmation
        components.append(
            self._opening_range_confirmation(
                direction=direction,
                current_price=ti.current_price,
                opening_range_high=ti.opening_range_high,
                opening_range_low=ti.opening_range_low,
                premarket_high=ti.premarket_high,
                premarket_low=ti.premarket_low,
            )
        )

        confirmed_count = sum(1 for c in components if c.passed is True)
        possible_count = sum(1 for c in components if c.passed is not None)
        raw_score = sum(c.score_awarded for c in components)

        # Data weakness tax
        adjusted_score = raw_score * max(0.45, data_quality / 100.0)
        adjusted_score = round(min(100.0, max(0.0, adjusted_score)), 1)

        invalidated = self._is_invalidated(ti, direction, opposite_level)

        if invalidated:
            state = TriggerState.INVALIDATED.value
            entry_type = EntryType.NONE.value
            reason = "Price action has invalidated the setup against the directional thesis."
        elif data_quality < 45 and confirmed_count < self.min_confirmed_for_partial:
            state = TriggerState.DATA_WEAK.value
            entry_type = EntryType.NONE.value
            reason = "Data quality is too weak to confirm the event with confidence."
        else:
            state = self._classify_state(
                trigger_score=adjusted_score,
                confirmed_count=confirmed_count,
                has_core_break=(components[0].passed is True),
                has_hold=(components[1].passed is True),
                has_reclaim_fail=(components[2].passed is True),
            )
            entry_type = self._classify_entry_type(state, components)
            reason = self._build_reason(state, components, direction)

        summary_line = self._build_summary_line(
            ticker=ti.ticker,
            direction=direction,
            state=state,
            score=adjusted_score,
            entry_type=entry_type,
            confirmed_count=confirmed_count,
        )

        return TriggerResult(
            ticker=ti.ticker,
            direction=direction,
            trigger_state=state,
            trigger_score=adjusted_score,
            entry_type=entry_type,
            confirmed_components=confirmed_count,
            possible_components=possible_count,
            data_quality_score=round(data_quality, 1),
            key_level=level,
            invalidation_level=ti.invalidation_level,
            trigger_reason=reason,
            summary_line=summary_line,
            components=[c.to_dict() for c in components],
        )

    # -------------------------------------------------------------------------
    # CORE COMPONENTS
    # -------------------------------------------------------------------------

    def _support_or_resistance_break(
        self,
        direction: str,
        level: Optional[float],
        current_price: Optional[float],
        bars_5m: list[dict[str, Any]],
    ) -> TriggerComponent:
        max_score = self.weights["support_or_resistance_break"]
        if level is None:
            return TriggerComponent(
                name="support_or_resistance_break",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="No structural level supplied from EOD manifest.",
            )

        recent = _take_last(bars_5m, 2)
        closes = [_bar_close(b) for b in recent]
        highs = [_bar_high(b) for b in recent]
        lows = [_bar_low(b) for b in recent]

        if direction == TradeBias.PUT.value:
            broke = (
                (current_price is not None and current_price < level * (1 - self.break_tolerance_pct))
                or any(c is not None and c < level * (1 - self.break_tolerance_pct) for c in closes)
                or any(l is not None and l < level * (1 - self.break_tolerance_pct) for l in lows)
            )
            note = f"Need downside break below support {level:.2f}."
        else:
            broke = (
                (current_price is not None and current_price > level * (1 + self.break_tolerance_pct))
                or any(c is not None and c > level * (1 + self.break_tolerance_pct) for c in closes)
                or any(h is not None and h > level * (1 + self.break_tolerance_pct) for h in highs)
            )
            note = f"Need upside break above resistance {level:.2f}."

        return TriggerComponent(
            name="support_or_resistance_break",
            passed=broke,
            score_awarded=max_score if broke else 0.0,
            max_score=max_score,
            note=note,
        )

    def _two_bar_hold(
        self,
        direction: str,
        level: Optional[float],
        bars_5m: list[dict[str, Any]],
    ) -> TriggerComponent:
        max_score = self.weights["two_bar_hold"]
        recent = _take_last(bars_5m, 2)
        if level is None or len(recent) < 2:
            return TriggerComponent(
                name="two_bar_hold",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Insufficient 5m bars to test a two-bar hold.",
            )

        closes = [_bar_close(b) for b in recent]
        if any(c is None for c in closes):
            return TriggerComponent(
                name="two_bar_hold",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Missing bar close data.",
            )

        if direction == TradeBias.PUT.value:
            held = all(c < level * (1 - self.break_tolerance_pct) for c in closes)
            note = f"Need two 5m closes below support {level:.2f}."
        else:
            held = all(c > level * (1 + self.break_tolerance_pct) for c in closes)
            note = f"Need two 5m closes above resistance {level:.2f}."

        score = max_score if held else 0.0
        return TriggerComponent("two_bar_hold", held, score, max_score, note)

    def _failed_reclaim_or_failed_pullback(
        self,
        direction: str,
        level: Optional[float],
        bars_1m: list[dict[str, Any]],
        bars_5m: list[dict[str, Any]],
    ) -> TriggerComponent:
        max_score = self.weights["failed_reclaim_or_failed_pullback"]
        bars = _take_last(bars_1m, 6) or _take_last(bars_5m, 3)
        if level is None or len(bars) < 2:
            return TriggerComponent(
                name="failed_reclaim_or_failed_pullback",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Insufficient bars to assess reclaim or pullback failure.",
            )

        last = bars[-1]
        prev = bars[-2]
        last_close = _bar_close(last)
        last_high = _bar_high(last)
        last_low = _bar_low(last)
        prev_close = _bar_close(prev)

        if None in (last_close, prev_close):
            return TriggerComponent(
                name="failed_reclaim_or_failed_pullback",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Missing close data for reclaim test.",
            )

        tol_low = level * (1 - self.reclaim_tolerance_pct)
        tol_high = level * (1 + self.reclaim_tolerance_pct)

        if direction == TradeBias.PUT.value:
            # Price tried to reclaim broken support but closed back under it.
            failed = (
                last_high is not None and last_high >= tol_low and last_close < tol_low and prev_close <= tol_low
            )
            note = f"Need failed reclaim under broken support {level:.2f}."
        else:
            # Price pulled back toward broken resistance but failed lower.
            failed = (
                last_low is not None and last_low <= tol_high and last_close > tol_high and prev_close >= tol_high
            )
            note = f"Need failed pullback above broken resistance {level:.2f}."

        return TriggerComponent(
            name="failed_reclaim_or_failed_pullback",
            passed=failed,
            score_awarded=max_score if failed else 0.0,
            max_score=max_score,
            note=note,
        )

    def _lower_high_or_higher_low_after_break(
        self,
        direction: str,
        level: Optional[float],
        bars_1m: list[dict[str, Any]],
        bars_5m: list[dict[str, Any]],
    ) -> TriggerComponent:
        max_score = self.weights["lower_high_or_higher_low_after_break"]
        bars = _take_last(bars_1m, 5) or _take_last(bars_5m, 4)
        if len(bars) < 3:
            return TriggerComponent(
                name="lower_high_or_higher_low_after_break",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Insufficient bars to assess post-break pivot quality.",
            )

        highs = [_bar_high(b) for b in bars if _bar_high(b) is not None]
        lows = [_bar_low(b) for b in bars if _bar_low(b) is not None]

        passed: Optional[bool]
        note: str

        if direction == TradeBias.PUT.value:
            if len(highs) < 3:
                passed = None
                note = "Missing high data for lower-high test."
            else:
                passed = highs[-1] < highs[-2] < highs[-3] or highs[-1] < highs[-2]
                note = "Need a lower-high sequence after the break."
        else:
            if len(lows) < 3:
                passed = None
                note = "Missing low data for higher-low test."
            else:
                passed = lows[-1] > lows[-2] > lows[-3] or lows[-1] > lows[-2]
                note = "Need a higher-low sequence after the break."

        return TriggerComponent(
            name="lower_high_or_higher_low_after_break",
            passed=passed,
            score_awarded=max_score if passed else 0.0,
            max_score=max_score,
            note=note,
        )

    def _vwap_confirmation(
        self,
        direction: str,
        current_price: Optional[float],
        live_vwap: Optional[float],
    ) -> TriggerComponent:
        max_score = self.weights["vwap_confirmation"]
        if current_price is None or live_vwap is None or live_vwap == 0:
            return TriggerComponent(
                name="vwap_confirmation",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Live VWAP or current price unavailable.",
            )

        pct = (current_price - live_vwap) / live_vwap
        if direction == TradeBias.PUT.value:
            passed = pct <= 0 or abs(pct) <= self.vwap_proximity_pct
            note = f"Need price below or at VWAP for bearish confirmation (diff={pct:.3%})."
        else:
            passed = pct >= 0 or abs(pct) <= self.vwap_proximity_pct
            note = f"Need price above or at VWAP for bullish confirmation (diff={pct:.3%})."

        score = max_score if passed else 0.0
        return TriggerComponent("vwap_confirmation", passed, score, max_score, note)

    def _volume_expansion(
        self,
        direction: str,
        bars_5m: list[dict[str, Any]],
        avg_bar_volume_5m: Optional[float],
        rvol: Optional[float],
    ) -> TriggerComponent:
        max_score = self.weights["volume_expansion"]
        recent = _take_last(bars_5m, 4)
        vols = [_bar_volume(b) for b in recent if _bar_volume(b) is not None]
        if not recent or not vols:
            return TriggerComponent(
                name="volume_expansion",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="No live bar volume data available.",
            )

        last_bar = recent[-1]
        last_vol = _bar_volume(last_bar)
        last_open = _bar_open(last_bar)
        last_close = _bar_close(last_bar)

        if last_vol is None or last_open is None or last_close is None:
            return TriggerComponent(
                name="volume_expansion",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Incomplete latest bar data for volume expansion test.",
            )

        median_recent = _median(vols[:-1]) if len(vols) > 1 else None
        baseline = avg_bar_volume_5m or median_recent

        if baseline is None or baseline <= 0:
            if rvol is None:
                return TriggerComponent(
                    name="volume_expansion",
                    passed=None,
                    score_awarded=0.0,
                    max_score=max_score,
                    note="No baseline volume or RVOL available.",
                )
            if direction == TradeBias.PUT.value:
                directional_bar = last_close < last_open
            else:
                directional_bar = last_close > last_open
            passed = directional_bar and rvol >= max(1.05, self.volume_expansion_threshold - 0.15)
            note = f"Fallback RVOL test used (rvol={rvol:.2f})."
            return TriggerComponent(
                name="volume_expansion",
                passed=passed,
                score_awarded=max_score if passed else 0.0,
                max_score=max_score,
                note=note,
            )

        ratio = last_vol / baseline
        if direction == TradeBias.PUT.value:
            directional_bar = last_close < last_open
        else:
            directional_bar = last_close > last_open

        passed = directional_bar and ratio >= self.volume_expansion_threshold
        note = f"Need directional bar with volume ratio >= {self.volume_expansion_threshold:.2f}; got {ratio:.2f}."
        return TriggerComponent(
            name="volume_expansion",
            passed=passed,
            score_awarded=max_score if passed else 0.0,
            max_score=max_score,
            note=note,
        )

    def _opening_range_confirmation(
        self,
        direction: str,
        current_price: Optional[float],
        opening_range_high: Optional[float],
        opening_range_low: Optional[float],
        premarket_high: Optional[float],
        premarket_low: Optional[float],
    ) -> TriggerComponent:
        max_score = self.weights["opening_range_confirmation"]
        if current_price is None:
            return TriggerComponent(
                name="opening_range_confirmation",
                passed=None,
                score_awarded=0.0,
                max_score=max_score,
                note="Current price unavailable.",
            )

        if direction == TradeBias.PUT.value:
            candidates = [v for v in (opening_range_low, premarket_low) if v is not None]
            if not candidates:
                return TriggerComponent(
                    name="opening_range_confirmation",
                    passed=None,
                    score_awarded=0.0,
                    max_score=max_score,
                    note="No OR low or premarket low available.",
                )
            ref = min(candidates)
            passed = current_price < ref * (1 - self.break_tolerance_pct)
            note = f"Need price below OR/premarket low {ref:.2f}."
        else:
            candidates = [v for v in (opening_range_high, premarket_high) if v is not None]
            if not candidates:
                return TriggerComponent(
                    name="opening_range_confirmation",
                    passed=None,
                    score_awarded=0.0,
                    max_score=max_score,
                    note="No OR high or premarket high available.",
                )
            ref = max(candidates)
            passed = current_price > ref * (1 + self.break_tolerance_pct)
            note = f"Need price above OR/premarket high {ref:.2f}."

        return TriggerComponent(
            name="opening_range_confirmation",
            passed=passed,
            score_awarded=max_score if passed else 0.0,
            max_score=max_score,
            note=note,
        )

    # -------------------------------------------------------------------------
    # STATE CLASSIFICATION
    # -------------------------------------------------------------------------

    def _classify_state(
        self,
        trigger_score: float,
        confirmed_count: int,
        has_core_break: bool,
        has_hold: bool,
        has_reclaim_fail: bool,
    ) -> str:
        # Confirmed requires actual break evidence, not just good microstructure.
        if (
            trigger_score >= 75
            and confirmed_count >= self.min_confirmed_for_confirmed
            and has_core_break
            and (has_hold or has_reclaim_fail)
        ):
            return TriggerState.CONFIRMED.value

        if (
            trigger_score >= 50
            and confirmed_count >= self.min_confirmed_for_partial
            and (has_core_break or has_reclaim_fail)
        ):
            return TriggerState.PARTIAL.value

        if trigger_score >= 25:
            return TriggerState.NOT_READY.value

        return TriggerState.FAILED.value

    def _classify_entry_type(
        self,
        state: str,
        components: list[TriggerComponent],
    ) -> str:
        if state not in (TriggerState.CONFIRMED.value, TriggerState.PARTIAL.value):
            return EntryType.NONE.value

        c_break = components[0].passed is True
        c_hold = components[1].passed is True
        c_reclaim = components[2].passed is True
        c_vwap = components[4].passed is True
        c_volume = components[5].passed is True

        if c_break and c_hold and c_volume:
            return EntryType.BREAKDOWN.value
        if c_break and c_reclaim:
            return EntryType.BREAK_RETEST.value
        if c_break and c_vwap:
            return EntryType.MOMENTUM_CONTINUATION.value
        return EntryType.EARLY_PROBE.value

    def _build_reason(
        self,
        state: str,
        components: list[TriggerComponent],
        direction: str,
    ) -> str:
        passed = [c.name for c in components if c.passed is True]
        failed = [c.name for c in components if c.passed is False]
        missing = [c.name for c in components if c.passed is None]

        bias_word = "bearish" if direction == TradeBias.PUT.value else "bullish"

        if state == TriggerState.CONFIRMED.value:
            return (
                f"{bias_word.title()} event confirmed. Passed: {', '.join(passed)}. "
                f"The move has moved beyond anticipation into active confirmation."
            )
        if state == TriggerState.PARTIAL.value:
            return (
                f"{bias_word.title()} trigger partially confirmed. Passed: {', '.join(passed)}. "
                f"Still incomplete: {', '.join(failed[:3]) if failed else 'none'}"
            )
        if state == TriggerState.NOT_READY.value:
            return (
                f"Structural idea may still be valid, but trigger is not live. "
                f"Missing/failed components: {', '.join((failed + missing)[:4])}"
            )
        if state == TriggerState.DATA_WEAK.value:
            return "Trigger cannot be confirmed confidently because key live data is missing or weak."
        if state == TriggerState.INVALIDATED.value:
            return "Price action has invalidated the directional setup."
        return "Trigger failed. The event-based conditions required for confirmation were not present."

    def _build_summary_line(
        self,
        ticker: str,
        direction: str,
        state: str,
        score: float,
        entry_type: str,
        confirmed_count: int,
    ) -> str:
        return (
            f"[TCE] {ticker:<6} {direction:<4} {state:<11} "
            f"score={score:>5.1f} confirmed={confirmed_count}/7 entry={entry_type}"
        )

    # -------------------------------------------------------------------------
    # DATA QUALITY / INVALIDATION
    # -------------------------------------------------------------------------

    def _data_quality_score(self, ti: TriggerInput) -> float:
        score = 100.0

        if not ti.bars_5m:
            score -= 30.0
        if ti.current_price is None:
            score -= 20.0
        if ti.live_vwap is None:
            score -= 12.0
        if ti.support_level is None and str(ti.direction).upper() == TradeBias.PUT.value:
            score -= 15.0
        if ti.resistance_level is None and str(ti.direction).upper() == TradeBias.CALL.value:
            score -= 15.0
        if ti.opening_range_high is None and ti.opening_range_low is None:
            score -= 8.0
        if ti.rvol is None and ti.avg_bar_volume_5m is None:
            score -= 10.0

        return max(0.0, score)

    def _is_invalidated(
        self,
        ti: TriggerInput,
        direction: str,
        opposite_level: Optional[float],
    ) -> bool:
        cp = ti.current_price
        inval = ti.invalidation_level
        if cp is None:
            return False

        if direction == TradeBias.PUT.value:
            if inval is not None and cp > inval:
                return True
            if opposite_level is not None and cp > opposite_level * (1 + 0.002):
                return True
            return False

        if inval is not None and cp < inval:
            return True
        if opposite_level is not None and cp < opposite_level * (1 - 0.002):
            return True
        return False


# =============================================================================
# CONVENIENCE FUNCTIONS FOR INTEGRATION
# =============================================================================

def build_trigger_input_from_candidate(
    candidate: dict[str, Any],
    live_stock: Optional[dict[str, Any]] = None,
    bars_1m: Optional[list[dict[str, Any]]] = None,
    bars_5m: Optional[list[dict[str, Any]]] = None,
    bars_15m: Optional[list[dict[str, Any]]] = None,
) -> TriggerInput:
    """
    Convenience adapter for morning_validation_engine integration.

    Expected candidate fields (best effort / optional fallback chain):
      ticker, direction, signal_price, support_level, resistance_level,
      invalidation_level, structural_tier, scs_score,
      opening_range_high, opening_range_low, premarket_high, premarket_low,
      avg_bar_volume_5m, rvol

    Expected live_stock fields (best effort / optional fallback chain):
      price, vwap, change_pct, volume
    """
    live_stock = live_stock or {}

    return TriggerInput(
        ticker=str(candidate.get("ticker", "UNKNOWN")),
        direction=str(candidate.get("direction") or candidate.get("options_direction") or "PUT").upper(),
        signal_price=_safe_float(candidate.get("signal_price")),
        support_level=_safe_float(candidate.get("support_level") or candidate.get("range_low") or candidate.get("key_support")),
        resistance_level=_safe_float(candidate.get("resistance_level") or candidate.get("range_high") or candidate.get("key_resistance")),
        invalidation_level=_safe_float(candidate.get("invalidation_level")),
        structural_tier=str(candidate.get("structural_tier") or ""),
        scs_score=_safe_float(candidate.get("scs_score")),
        current_price=_safe_float(live_stock.get("price") or candidate.get("current_price")),
        live_vwap=_safe_float(live_stock.get("vwap") or candidate.get("live_vwap")),
        premarket_high=_safe_float(candidate.get("premarket_high")),
        premarket_low=_safe_float(candidate.get("premarket_low")),
        opening_range_high=_safe_float(candidate.get("opening_range_high")),
        opening_range_low=_safe_float(candidate.get("opening_range_low")),
        bars_1m=list(bars_1m or []),
        bars_5m=list(bars_5m or []),
        bars_15m=list(bars_15m or []),
        rvol=_safe_float(candidate.get("rvol") or candidate.get("live_rvol")),
        avg_bar_volume_5m=_safe_float(candidate.get("avg_bar_volume_5m")),
        live_spread_pct=_safe_float(candidate.get("spread_pct_live") or candidate.get("live_spread_pct")),
        live_option_mid=_safe_float(candidate.get("option_mid_live") or candidate.get("live_option_mid")),
        live_iv=_safe_float(candidate.get("iv_live") or candidate.get("live_iv")),
        session_minutes_elapsed=_safe_int(candidate.get("session_minutes_elapsed")),
    )


def trigger_result_to_row(result: TriggerResult) -> dict[str, Any]:
    """Flat row helper for CSV enrichment."""
    return {
        "tce_trigger_state": result.trigger_state,
        "tce_trigger_score": result.trigger_score,
        "tce_entry_type": result.entry_type,
        "tce_confirmed_components": result.confirmed_components,
        "tce_possible_components": result.possible_components,
        "tce_data_quality_score": result.data_quality_score,
        "tce_key_level": result.key_level,
        "tce_invalidation_level": result.invalidation_level,
        "tce_trigger_reason": result.trigger_reason,
        "tce_summary_line": result.summary_line,
        "tce_components_json": str(result.components),
    }


# =============================================================================
# EXAMPLE USAGE (safe no-op if imported)
# =============================================================================

if __name__ == "__main__":
    # Minimal smoke example for quick local testing.
    sample_candidate = {
        "ticker": "KEY",
        "direction": "PUT",
        "signal_price": 22.04,
        "support_level": 21.80,
        "resistance_level": 22.60,
        "invalidation_level": 22.60,
        "structural_tier": "A",
        "scs_score": 74.0,
        "opening_range_low": 21.92,
        "opening_range_high": 22.18,
        "premarket_low": 21.95,
        "premarket_high": 22.22,
        "avg_bar_volume_5m": 180000,
        "rvol": 1.35,
    }

    sample_live = {
        "price": 21.74,
        "vwap": 21.87,
    }

    sample_5m = [
        {"open": 22.02, "high": 22.04, "low": 21.86, "close": 21.90, "volume": 160000},
        {"open": 21.90, "high": 21.93, "low": 21.76, "close": 21.79, "volume": 210000},
        {"open": 21.79, "high": 21.82, "low": 21.70, "close": 21.74, "volume": 255000},
    ]

    sample_1m = [
        {"open": 21.80, "high": 21.83, "low": 21.76, "close": 21.78, "volume": 62000},
        {"open": 21.78, "high": 21.81, "low": 21.73, "close": 21.75, "volume": 74000},
        {"open": 21.75, "high": 21.79, "low": 21.71, "close": 21.74, "volume": 69000},
    ]

    ti = build_trigger_input_from_candidate(
        sample_candidate,
        live_stock=sample_live,
        bars_1m=sample_1m,
        bars_5m=sample_5m,
        bars_15m=[],
    )

    engine = TriggerConfirmationEngine()
    result = engine.evaluate(ti)
    print(result.summary_line)
    print(result.to_dict())
