"""wyckoff_crabel_precor_logic_v2.py

AVSHUNTER â€” Wyckoff Ã— Crabel Pre-CORE Logic (Rebuilt) â€” v2.1
=============================================================
ROLE (revised 2026-03): AUDIT ENRICHMENT ONLY.

This module now serves as a secondary data source for discovery.
It provides supporting evidence and alternative phase readings.
It does NOT decide direction or intent â€” that is swing_fusion.py's job.

Fixes applied:
  FIX-PRECOR-1 â€” Event index coordinate bug corrected.
    Events were detected in a window slice (rw, 40 bars) but idx was stored
    as a position within rw. _estimate_move_start_and_duration() then used
    that idx against r=df.tail(140), producing off-by-~100-bar errors.
    Fix: store idx as an absolute offset from end of df, so age calculations
    are frame-independent.

  FIX-PRECOR-2 â€” process_precore_signal() demoted.
    It still runs but its 'intent' field is labelled 'precor_intent_raw'.
    swing_fusion.fuse_wyckoff_crabel() is the single authority for intent.
    Downstream: _reconcile_intent() in discovery still handles raw intent
    for the precor_intent display column (unchanged behaviour).

Original design principles preserved:
- Never require Phase A/B as prerequisites to label C/D/E.
- Always a phase â€” if evidence is weak, tag confidence + missing_evidence.
- Output is for discovery/audit, not execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b is None or b == 0 or (isinstance(b, float) and np.isnan(b)):
        return default
    return a / b


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return _true_range(df).rolling(n).mean()


def _poc(df: pd.DataFrame) -> pd.Series:
    # Position of close within bar: 0=low, 1=high
    rng = (df['high'] - df['low']).replace(0, np.nan)
    out = (df['close'] - df['low']) / rng
    return out.fillna(0.5).clip(0.0, 1.0)


def _slope(series: pd.Series, lookback: int = 20) -> float:
    # Simple linear slope proxy (normalised)
    if len(series) < lookback:
        return 0.0
    y = series.tail(lookback).values
    x = np.arange(len(y))
    if np.std(y) == 0:
        return 0.0
    m = np.polyfit(x, y, 1)[0]
    return float(m / np.mean(y))


def _fractal_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[List[int], List[int]]:
    """Return indices (integer positions) of swing highs and lows."""
    highs, lows = [], []
    h = df['high'].values
    l = df['low'].values
    n = len(df)
    for i in range(left, n - right):
        if h[i] == max(h[i-left:i+right+1]):
            highs.append(i)
        if l[i] == min(l[i-left:i+right+1]):
            lows.append(i)
    return highs, lows


# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------

@dataclass
class DetectedEvent:
    name: str
    idx: int
    confidence: float
    evidence: List[str]


@dataclass
class WyckoffState:
    phase: str  # A/B/C/D/E
    mode: str   # ACCUMULATION/DISTRIBUTION
    control: str  # BUYERS/SELLERS/EQUILIBRIUM/SHIFTING
    primary_event: str
    phase_conf: float
    event_conf: float
    transition_to: Optional[str]
    transition_conf: float
    intent: str
    notes: List[str]


# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------

class WyckoffCrabelStateMachine:
    """Deterministic phase+event+compression inference from OHLCV bars."""

    def __init__(self, lookback: int = 180):
        self.lookback = lookback

        # Event thresholds (tuned for discovery, not execution)
        self.climax_vol_mult = 1.8
        self.climax_tr_mult = 1.4

        # Boundary sweep thresholds
        self.sweep_pct = 0.6 / 100  # 0.6%
        self.reclaim_within = 5

        # Breakout thresholds
        self.breakout_pct = 0.7 / 100
        self.followthrough_bars = 3

        # Compression thresholds
        self.nr_window = 7
        self.atr_contract_pct = 0.25  # ATR percentile < 25% => compressed

    # ----------------------- public API --------------------------------------

    def analyse(self, df: pd.DataFrame) -> Dict:
        dfp = self._prepare(df)
        notes: List[str] = []

        if dfp is None or len(dfp) < 50:
            return self._output_insufficient(df)

        # Core components
        control, control_conf, control_notes = self._infer_control(dfp)
        notes.extend(control_notes)

        comp_state, comp_conf, comp_notes, crabel_score_norm = self._infer_crabel_compression(dfp)
        notes.extend(comp_notes)

        events = self._detect_events(dfp)
        primary_event = events[0] if events else None

        phase, phase_conf, phase_notes = self._infer_phase(dfp, primary_event, control)
        notes.extend(phase_notes)

        mode, mode_conf, mode_notes = self._infer_mode(dfp, primary_event, phase, control)
        notes.extend(mode_notes)

        # Phaseâ†’intent mapping (Gap 3)
        intent, intent_conf, intent_notes = self._map_phase_to_intent(phase, mode, primary_event, control, comp_state)
        notes.extend(intent_notes)

        # Transition logic (what it is creeping towards)
        transition_to, transition_conf, transition_notes = self._infer_transition(dfp, phase, mode, primary_event, control)
        notes.extend(transition_notes)

        # Move start & duration
        move_start_idx, move_age_bars, move_notes = self._estimate_move_start_and_duration(dfp, phase, mode, primary_event)
        notes.extend(move_notes)

        # Event confidence
        event_name = primary_event.name if primary_event else "NONE"
        event_conf = primary_event.confidence if primary_event else 0.0

        state = WyckoffState(
            phase=phase,
            mode=mode,
            control=control,
            primary_event=event_name,
            phase_conf=phase_conf,
            event_conf=event_conf,
            transition_to=transition_to,
            transition_conf=transition_conf,
            intent=intent,
            notes=notes,
        )

        return {
            # Audit enrichment fields â€” all prefixed for clarity
            "wyckoff_phase": state.phase,
            "wyckoff_phase_conf": round(state.phase_conf, 1),
            "wyckoff_mode": state.mode,
            "wyckoff_mode_conf": round(mode_conf, 1),
            "control_state": state.control,
            "control_conf": round(control_conf, 1),
            "primary_event": state.primary_event,
            "event_conf": round(state.event_conf, 1),
            "crabel_compression_state": comp_state,
            "crabel_compression_conf": round(comp_conf, 1),
            "crabel_score": crabel_score_norm,   # FIX-CRABEL-SCORE: numeric 0-100
            # FIX-PRECOR-2: labelled as precor_intent (raw) â€” swing_fusion decides final intent
            "intent": state.intent,           # kept for _reconcile_intent() compatibility
            "precor_intent_raw": state.intent, # explicit audit label
            "intent_conf": round(intent_conf, 1),
            "transition_to": state.transition_to or "NONE",
            "transition_conf": round(state.transition_conf, 1),
            "move_start_idx": int(move_start_idx) if move_start_idx is not None else None,
            "move_age_bars": int(move_age_bars) if move_age_bars is not None else None,
            "notes_top5": state.notes[:5],
            "notes_all": state.notes,
            # Audit marker â€” downstream code can check this
            "_precor_role": "AUDIT_ENRICHMENT",  # not decision-making
        }


# -----------------------------------------------------------------------------
# Preparation
# -----------------------------------------------------------------------------

    def _prepare(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        if df is None or len(df) == 0:
            return None

        d = df.copy()
        # Ensure standard columns
        needed = {"open", "high", "low", "close", "volume"}
        if not needed.issubset(set(map(str.lower, d.columns))):
            # Try case-insensitive mapping
            colmap = {c: c.lower() for c in d.columns}
            d = d.rename(columns=colmap)

        if not needed.issubset(set(d.columns)):
            return None

        d = d.tail(self.lookback).copy()

        d['tr'] = _true_range(d)
        d['atr14'] = _atr(d, 14)
        d['poc'] = _poc(d)

        d['vol20'] = d['volume'].rolling(20).mean()
        d['tr20'] = d['tr'].rolling(20).mean()
        d['vol_ratio'] = (d['volume'] / d['vol20']).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        d['tr_ratio'] = (d['tr'] / d['tr20']).replace([np.inf, -np.inf], np.nan).fillna(1.0)

        d['ema21'] = _ema(d['close'], 21)
        d['ema50'] = _ema(d['close'], 50)

        # Return & direction
        d['ret1'] = d['close'].pct_change().fillna(0.0)
        d['dir'] = np.where(d['close'] > d['close'].shift(1), 1, np.where(d['close'] < d['close'].shift(1), -1, 0))

        return d


    def _output_insufficient(self, df: pd.DataFrame) -> Dict:
        return {
            "wyckoff_phase": "UNKNOWN",
            "wyckoff_phase_conf": 0.0,
            "wyckoff_mode": "ACCUMULATION",
            "wyckoff_mode_conf": 0.0,
            "control_state": "EQUILIBRIUM",
            "control_conf": 0.0,
            "primary_event": "NONE",
            "event_conf": 0.0,
            "crabel_compression_state": "NONE",
            "crabel_compression_conf": 0.0,
            "crabel_score": 0.0,
            "intent": "WAIT",
            "intent_conf": 0.0,
            "transition_to": "NONE",
            "transition_conf": 0.0,
            "move_start_idx": None,
            "move_age_bars": None,
            "notes_top5": ["INSUFFICIENT_DATA"],
            "notes_all": ["INSUFFICIENT_DATA"],
        }


# -----------------------------------------------------------------------------
# Control inference (who controls the tape)
# -----------------------------------------------------------------------------

    def _infer_control(self, df: pd.DataFrame) -> Tuple[str, float, List[str]]:
        notes: List[str] = []
        r = df.tail(30)

        # Trend proxy
        slope21 = _slope(r['ema21'], 20)
        slope50 = _slope(r['ema50'], 20)

        # Effort vs result: high vol + small range, and close location
        evr_buy = ((r['vol_ratio'] > 1.4) & (r['tr_ratio'] < 0.85) & (r['poc'] > 0.65)).sum()
        evr_sell = ((r['vol_ratio'] > 1.4) & (r['tr_ratio'] < 0.85) & (r['poc'] < 0.35)).sum()

        # Follow-through failures
        fail_breakdown = 0
        fail_breakout = 0
        for i in range(2, len(r) - 1):
            prev = r.iloc[i-1]
            cur = r.iloc[i]
            nxt = r.iloc[i+1]

            # breakdown attempt then immediate reclaim
            if cur['close'] < prev['low'] and nxt['close'] > cur['close']:
                fail_breakdown += 1
            # breakout attempt then immediate fade
            if cur['close'] > prev['high'] and nxt['close'] < cur['close']:
                fail_breakout += 1

        buyer_points = 0.0
        seller_points = 0.0

        # Trend slope gives baseline
        if slope21 > 0 and slope50 > 0:
            buyer_points += 2
            notes.append("EMA slopes rising")
        if slope21 < 0 and slope50 < 0:
            seller_points += 2
            notes.append("EMA slopes falling")

        buyer_points += evr_buy * 0.8
        seller_points += evr_sell * 0.8
        if evr_buy:
            notes.append(f"EVR absorption by buyers (count={int(evr_buy)})")
        if evr_sell:
            notes.append(f"EVR absorption by sellers (count={int(evr_sell)})")

        buyer_points += fail_breakdown * 0.7
        seller_points += fail_breakout * 0.7
        if fail_breakdown:
            notes.append(f"Failed breakdowns (count={int(fail_breakdown)})")
        if fail_breakout:
            notes.append(f"Failed breakouts (count={int(fail_breakout)})")

        diff = buyer_points - seller_points

        if diff >= 2.5:
            return "BUYERS", min(90.0, 70.0 + diff * 6.0), notes
        if diff <= -2.5:
            return "SELLERS", min(90.0, 70.0 + abs(diff) * 6.0), notes
        if abs(diff) <= 1.0:
            return "EQUILIBRIUM", 55.0, notes or ["Balanced tape"]
        return "SHIFTING", 50.0, notes or ["Control unclear"]


# -----------------------------------------------------------------------------
# Crabel compression inference
# -----------------------------------------------------------------------------

    def _infer_crabel_compression(self, df: pd.DataFrame) -> Tuple[str, float, List[str]]:
        notes: List[str] = []
        r = df.tail(40)

        # NR7 / NR4
        tr = r['tr']
        if len(tr) >= self.nr_window:
            last_tr = tr.iloc[-1]
            nr7 = last_tr == tr.tail(self.nr_window).min()
            nr4 = last_tr == tr.tail(4).min()
        else:
            nr7 = nr4 = False

        # ATR contraction percentile
        atr = r['atr14'].dropna()
        if len(atr) > 20:
            atr_pct = (atr.rank(pct=True).iloc[-1])
        else:
            atr_pct = 0.5

        # Inside day sequence
        inside = 0
        for i in range(1, min(6, len(r))):
            cur = r.iloc[-i]
            prev = r.iloc[-i-1]
            if cur['high'] <= prev['high'] and cur['low'] >= prev['low']:
                inside += 1
            else:
                break

        score = 0
        if nr7:
            score += 2
            notes.append("NR7")
        if nr4:
            score += 1
            notes.append("NR4")
        if atr_pct < self.atr_contract_pct:
            score += 2
            notes.append(f"ATR compressed (pct={atr_pct:.2f})")
        if inside >= 2:
            score += 2
            notes.append(f"Inside-bars run (n={inside})")

        # FIX-CRABEL-SCORE (2026-04-21): normalise raw score (0-7) to 0-100
        # and return as 4th element so callers can write crabel_score column.
        crabel_score_norm = round(min(100.0, (score / 7) * 100), 1)

        if score >= 4:
            return "CRABEL_READY", 80.0, notes, crabel_score_norm
        if score >= 2:
            return "COILING", 72.0, notes, crabel_score_norm
        return "NONE", 50.0, notes or ["No compression"], crabel_score_norm


# -----------------------------------------------------------------------------
# Event detection (Wyckoff)
# -----------------------------------------------------------------------------

    def _detect_events(self, df: pd.DataFrame) -> List[DetectedEvent]:
        """Return events ordered by recency and confidence (discovery oriented)."""
        r = df.tail(120)
        notes: List[DetectedEvent] = []

        # Define local range boundaries (20â€“60 bar windows)
        win = 40 if len(r) >= 40 else len(r)
        rw = r.tail(win)
        rng_high = float(rw['high'].max())
        rng_low = float(rw['low'].min())
        rng_mid = (rng_high + rng_low) / 2
        rng_size = max(1e-9, rng_high - rng_low)

        # Climax candidates (SC/BC)
        for i in range(len(rw) - 20, len(rw)):
            if i < 0:
                continue
            row = rw.iloc[i]
            if row['vol_ratio'] >= self.climax_vol_mult and row['tr_ratio'] >= self.climax_tr_mult:
                if row['dir'] < 0 and row['poc'] >= 0.45:
                    notes.append(DetectedEvent(
                        name="SC",
                        idx=int(rw.index.get_loc(row.name)),
                        confidence=78.0,
                        evidence=["High vol+range", "Down bar closes off lows"],
                    ))
                if row['dir'] > 0 and row['poc'] <= 0.55:
                    notes.append(DetectedEvent(
                        name="BC",
                        idx=int(rw.index.get_loc(row.name)),
                        confidence=78.0,
                        evidence=["High vol+range", "Up bar closes off highs"],
                    ))

        # Spring / Upthrust detection using boundary sweeps
        # We use a *small sweep* and a reclaim signal.
        closes = rw['close'].values
        highs = rw['high'].values
        lows = rw['low'].values

        # Recent boundary levels based on rolling mins/maxs
        roll_low = rw['low'].rolling(20).min().shift(1)
        roll_high = rw['high'].rolling(20).max().shift(1)

        for i in range(25, len(rw) - 1):
            sup = roll_low.iloc[i]
            res = roll_high.iloc[i]
            if np.isnan(sup) or np.isnan(res):
                continue

            # Spring: sweeps below support then reclaims support within N bars
            if lows[i] < sup * (1 - self.sweep_pct):
                depth = (sup - lows[i]) / max(1e-9, sup)
                for j in range(1, self.reclaim_within + 1):
                    if i + j >= len(rw):
                        break
                    if closes[i + j] > sup:
                        conf = 82.0
                        if rw.iloc[i]['vol_ratio'] < 1.0:
                            conf = 76.0  # "quiet" spring
                        notes.append(DetectedEvent(
                            name="Spring",
                            idx=i,
                            confidence=conf,
                            evidence=[f"Sweep below support ({depth*100:.1f}%)", f"Reclaim within {j} bars"],
                        ))
                        break

            # UT/UTAD: sweeps above resistance then falls back below within N bars
            if highs[i] > res * (1 + self.sweep_pct):
                ext = (highs[i] - res) / max(1e-9, res)
                for j in range(1, self.reclaim_within + 1):
                    if i + j >= len(rw):
                        break
                    if closes[i + j] < res:
                        conf = 82.0
                        if rw.iloc[i]['vol_ratio'] < 1.0:
                            conf = 76.0
                        notes.append(DetectedEvent(
                            name="UTAD",
                            idx=i,
                            confidence=conf,
                            evidence=[f"Sweep above resistance ({ext*100:.1f}%)", f"Fail back within {j} bars"],
                        ))
                        break

        # SOS/SOW: breakout beyond range with follow-through
        # We measure vs rolling boundary rather than absolute range.
        for i in range(25, len(rw) - self.followthrough_bars):
            sup = roll_low.iloc[i]
            res = roll_high.iloc[i]
            if np.isnan(sup) or np.isnan(res):
                continue
            # SOS
            if closes[i] > res * (1 + self.breakout_pct) and rw.iloc[i]['poc'] > 0.65:
                # follow-through check
                ft = (closes[i+1:i+1+self.followthrough_bars] >= closes[i]).sum()
                if ft >= 1:
                    notes.append(DetectedEvent(
                        name="SOS",
                        idx=i,
                        confidence=80.0,
                        evidence=["Breakout above resistance", f"Follow-through bars={int(ft)}"],
                    ))
            # SOW
            if closes[i] < sup * (1 - self.breakout_pct) and rw.iloc[i]['poc'] < 0.35:
                ft = (closes[i+1:i+1+self.followthrough_bars] <= closes[i]).sum()
                if ft >= 1:
                    notes.append(DetectedEvent(
                        name="SOW",
                        idx=i,
                        confidence=80.0,
                        evidence=["Breakdown below support", f"Follow-through bars={int(ft)}"],
                    ))

        # Sort: most recent first, then confidence
        notes.sort(key=lambda e: (e.idx, e.confidence), reverse=True)
        return notes[:5]


# -----------------------------------------------------------------------------
# Phase inference â€” ALWAYS A PHASE (Gap 5)
# -----------------------------------------------------------------------------

    def _infer_phase(self, df: pd.DataFrame, primary_event: Optional[DetectedEvent], control: str) -> Tuple[str, float, List[str]]:
        """Infer A/B/C/D/E from *observable structure* (not rigid prerequisites)."""
        notes: List[str] = []
        r = df.tail(120)

        # Structure: range vs trend
        slope = _slope(r['ema21'], 30)
        ema_sep = _safe_div((r['ema21'].iloc[-1] - r['ema50'].iloc[-1]), r['close'].iloc[-1], 0.0)

        # Range-ness metric: frequent direction changes
        dirs = r['dir'].tail(40).values
        flips = np.sum(np.sign(dirs[1:]) != np.sign(dirs[:-1]))

        # Boundary interaction metric
        w = r.tail(50)
        hi = float(w['high'].max())
        lo = float(w['low'].min())
        size = max(1e-9, hi - lo)
        # how many closes in middle 40% of range
        mid_lo = lo + 0.30 * size
        mid_hi = hi - 0.30 * size
        mid_closes = ((w['close'] >= mid_lo) & (w['close'] <= mid_hi)).sum()

        # Detect if currently far from range (trend extension)
        dist_from_mid = abs(w['close'].iloc[-1] - (hi + lo) / 2) / size

        # Phase overrides via explicit events (they are high-information)
        if primary_event:
            if primary_event.name in {"Spring", "UTAD"}:
                notes.append(f"Primary event implies Phase C: {primary_event.name}")
                return "C", max(75.0, primary_event.confidence), notes
            if primary_event.name in {"SOS", "SOW"}:
                notes.append(f"Primary event implies Phase D: {primary_event.name}")
                return "D", 80.0, notes
            if primary_event.name in {"SC", "BC"}:
                notes.append(f"Climax-like event implies Phase A: {primary_event.name}")
                return "A", 75.0, notes

        # If strong trend + away from range â†’ E (trend continuation)
        # FIX: Lowered thresholds â€” original 0.0025/0.003/0.55 missed strong extended
        # trends (e.g. ADX>40 stocks like AROC). New: 0.0015/0.0015/0.40 are more
        # sensitive to established markup/markdown phases.
        if abs(slope) > 0.0015 and abs(ema_sep) > 0.0015 and dist_from_mid > 0.40:
            notes.append("Sustained trend away from value")
            return "E", 78.0, notes

        # If breakout emerging but not extended yet â†’ D
        if abs(slope) > 0.0010 and abs(ema_sep) > 0.0010:
            notes.append("Trend emerging / leaving range")
            return "D", 74.0, notes

        # If it looks like a range (many flips + many mid closes) â†’ B
        if flips >= 18 and mid_closes >= 18:
            notes.append("Range-building behaviour (oscillation)")
            return "B", 76.0, notes

        # Phase A (stopping) â€” weakening thrust after trend
        tr_now = r['tr'].tail(10).mean()
        tr_prev = r['tr'].tail(30).head(20).mean()
        if tr_now < tr_prev * 0.8 and flips >= 12:
            notes.append("Momentum shortening + uncertainty (possible stopping action)")
            return "A", 72.0, notes

        # Default fallback: choose most plausible between B and D based on control & slope
        if control == "BUYERS" and slope >= 0:
            notes.append("Default to Phase D (buyers + mild slope)")
            return "D", 70.0, notes
        if control == "SELLERS" and slope <= 0:
            notes.append("Default to Phase D (sellers + mild slope)")
            return "D", 70.0, notes

        notes.append("Default to Phase B (insufficient distinct structure)")
        return "B", 45.0, notes


# -----------------------------------------------------------------------------
# Mode inference (Accumulation vs Distribution)
# -----------------------------------------------------------------------------

    def _infer_mode(self, df: pd.DataFrame, primary_event: Optional[DetectedEvent], phase: str, control: str) -> Tuple[str, float, List[str]]:
        notes: List[str] = []

        if primary_event:
            if primary_event.name in {"Spring", "SC", "SOS"}:
                return "ACCUMULATION", 80.0, [f"Event implies accumulation: {primary_event.name}"]
            if primary_event.name in {"UTAD", "BC", "SOW"}:
                return "DISTRIBUTION", 80.0, [f"Event implies distribution: {primary_event.name}"]

        # Otherwise infer from control + phase context
        if phase in {"D", "E"}:
            if control == "BUYERS":
                return "ACCUMULATION", 74.0, ["Buyers controlling emerging/active trend"]
            if control == "SELLERS":
                return "DISTRIBUTION", 74.0, ["Sellers controlling emerging/active trend"]

        # Range-like phases fall back to last swing direction
        r = df.tail(60)
        recent_ret = r['close'].iloc[-1] / r['close'].iloc[0] - 1
        if recent_ret >= 0:
            return "ACCUMULATION", 70.0, ["Net drift up in range"]
        return "DISTRIBUTION", 70.0, ["Net drift down in range"]


# -----------------------------------------------------------------------------
# Phase â†’ intent mapping (Gap 3)
# -----------------------------------------------------------------------------

    def _map_phase_to_intent(
        self,
        phase: str,
        mode: str,
        primary_event: Optional[DetectedEvent],
        control: str,
        compression_state: str,
    ) -> Tuple[str, float, List[str]]:
        notes: List[str] = []

        # Intent is what we pass to Light CORE as a *candidate label*.
        # It is not an execution command.
        event = primary_event.name if primary_event else "NONE"

        if phase == "A":
            notes.append("Stopping action / early turn")
            return "WAIT", 75.0, notes

        if phase == "B":
            # In B, we prefer compression readiness and boundary pressure.
            if compression_state in {"COILING", "CRABEL_READY"}:
                notes.append("Cause-building + compression")
                return "TRANSITION", 75.0, notes
            return "WAIT", 72.0, ["Range-building without clear compression"]

        if phase == "C":
            # Phase C is where events matter the most.
            if event == "Spring" and mode == "ACCUMULATION":
                return "BUY_SETUP", 80.0, ["Spring detected â†’ long candidate"]
            if event == "UTAD" and mode == "DISTRIBUTION":
                return "SELL_SETUP", 80.0, ["UTAD detected â†’ short candidate"]
            # FIX: If event unclear, use control â€” but require mode agreement for SELL_SETUP.
            # Prevents SELL_SETUP firing when BUYERS are in control.
            if control == "BUYERS":
                return "BUY_SETUP", 72.0, ["Phase C-like turn with buyer control"]
            if control == "SELLERS" and mode == "DISTRIBUTION":
                return "SELL_SETUP", 72.0, ["Phase C-like turn with seller control + distribution mode"]
            if control == "SELLERS":
                return "TRANSITION", 70.0, ["Seller control but mode unclear â€” waiting for confirmation"]
            # FIX-PRECOR-C-EQUIL (2026-04-21): EQUILIBRIUM control in Phase C was
            # falling through to WAIT, then being misread as SELL_SETUP downstream.
            # 300/515 Phase C SELL_SETUP signals had EQUILIBRIUM control â€” structurally
            # neutral, not short. ACCUMULATION mode + EQUILIBRIUM = TRANSITION (coiling),
            # not a directional short signal. This eliminates the V4_UNCLEAR_STATE veto
            # on ~300 signals per run.
            if control == "EQUILIBRIUM" and mode == "ACCUMULATION":
                return "TRANSITION", 68.0, ["Phase C coiling â€” EQUILIBRIUM in accumulation, awaiting Spring/LPS"]
            if control == "EQUILIBRIUM":
                return "TRANSITION", 65.0, ["Phase C EQUILIBRIUM â€” direction unresolved, watch for event"]
            # SHIFTING control â€” may be transitioning either way
            if control == "SHIFTING" and mode == "ACCUMULATION":
                return "TRANSITION", 62.0, ["Phase C SHIFTING in accumulation - direction unresolved, monitor for event confirmation"]
            if control == "SHIFTING":
                return "TRANSITION", 62.0, ["Phase C SHIFTING â€” monitor for event confirmation"]
            return "WAIT", 60.0, ["Phase C inferred but event and control unclear"]

        if phase == "D":
            # D = emerging trend; use SOS/SOW or control.
            if event == "SOS" or (mode == "ACCUMULATION" and control == "BUYERS"):
                return "BUY_SETUP", 78.0, ["Markup emergence (SOS/control)"]
            if event == "SOW" or (mode == "DISTRIBUTION" and control == "SELLERS"):
                return "SELL_SETUP", 78.0, ["Markdown emergence (SOW/control)"]
            return "TRANSITION", 72.0, ["Phase D emerging but mixed control"]

        # phase == E
        if phase == "E":
            # E = trend continuation; pre-core should surface pullback entries.
            # FIX: Mode must agree with control for SELL_SETUP to fire.
            # Prevents SELL_SETUP being assigned when BUYERS are in control.
            if mode == "ACCUMULATION":
                return "BUY_SETUP", 74.0, ["Trend continuation (seek LPS pullback)"]
            if mode == "DISTRIBUTION" and control in {"SELLERS", "EQUILIBRIUM"}:
                return "SELL_SETUP", 74.0, ["Trend continuation (seek LPSY pullback)"]
            # Mode says DISTRIBUTION but BUYERS in control â€” trust control
            return "BUY_SETUP", 70.0, ["Trend continuation â€” mode/control conflict, control wins"]


# -----------------------------------------------------------------------------
# Transition inference ("creeping to next phase")
# -----------------------------------------------------------------------------

    def _infer_transition(
        self,
        df: pd.DataFrame,
        phase: str,
        mode: str,
        primary_event: Optional[DetectedEvent],
        control: str,
    ) -> Tuple[Optional[str], float, List[str]]:
        notes: List[str] = []
        r = df.tail(60)

        # Transition is a second-order judgement: what is most likely next.
        # We base it on (1) compression, (2) boundary pressure, (3) follow-through.

        # Boundary pressure: closes clustering near extremes
        hi = float(r['high'].rolling(40).max().iloc[-1])
        lo = float(r['low'].rolling(40).min().iloc[-1])
        size = max(1e-9, hi - lo)
        last = float(r['close'].iloc[-1])

        near_high = (hi - last) / size < 0.20
        near_low = (last - lo) / size < 0.20

        # Micro follow-through: last 5 bars net direction
        net_dir = r['dir'].tail(5).sum()

        if phase == "B":
            if near_high and control == "BUYERS":
                return "C", 75.0, ["Range pressing near resistance (buyers) â†’ likely Spring/UTAD setup next"]
            if near_low and control == "SELLERS":
                return "C", 75.0, ["Range pressing near support (sellers) â†’ likely sweep/test next"]
            return "C", 70.0, ["Range likely to resolve into Phase C event"]

        if phase == "C":
            # After spring/utad, next is D if follow-through exists
            if net_dir >= 2 and control in {"BUYERS", "SELLERS"}:
                return "D", 78.0, ["Post-event follow-through building â†’ Phase D"]
            return "D", 70.0, ["Phase C often transitions to D with confirmation"]

        if phase == "D":
            # D moves to E if trend extends and pullbacks hold
            slope = _slope(r['ema21'], 25)
            if abs(slope) > 0.0025:
                return "E", 75.0, ["Trend strengthening â†’ Phase E"]
            return "E", 70.0, ["Likely continuation into E if trend persists"]

        if phase == "A":
            return "B", 75.0, ["Stopping action tends to form B (cause-building)"]

        # phase E
        return None, 0.0, ["No higher phase than E"]


# -----------------------------------------------------------------------------
# Start-of-move and duration inference
# -----------------------------------------------------------------------------

    def _estimate_move_start_and_duration(
        self,
        df: pd.DataFrame,
        phase: str,
        mode: str,
        primary_event: Optional[DetectedEvent],
    ) -> Tuple[Optional[int], Optional[int], List[str]]:
        notes: List[str] = []
        r = df.tail(140)
        total_len = len(r)

        # FIX-PRECOR-1: Event idx was stored as rw-relative (window of 40 bars)
        # but age was computed against r (140 bars), giving off-by-~100 bar errors.
        # Fix: primary_event.idx is the position within rw (df.tail(40)).
        # We must convert to an offset from the END of r so age is frame-independent.
        #
        # rw = r.tail(40), so rw position i maps to r position (total_len - 40 + i).
        # age = total_len - 1 - r_position = total_len - 1 - (total_len - 40 + i) = 39 - i
        # i.e. age = (len(rw) - 1) - rw_relative_idx

        if primary_event:
            rw_len = min(40, total_len)   # matches the window used in _detect_events
            rw_relative_idx = primary_event.idx

            # Guard against stale/out-of-bounds idx
            if 0 <= rw_relative_idx < rw_len:
                age = (rw_len - 1) - rw_relative_idx
                # abs_idx is position within r (useful for price lookups)
                abs_idx = total_len - rw_len + rw_relative_idx
                notes.append(
                    f"Move-start anchored to event {primary_event.name} "
                    f"(rw_idx={rw_relative_idx}, age={age} bars)"
                )
                return abs_idx, age, notes
            else:
                notes.append(
                    f"Event idx {rw_relative_idx} out of bounds for rw_len={rw_len} â€” "
                    f"falling back to swing pivot"
                )

        # Otherwise use last major swing pivot as anchor.
        highs, lows = _fractal_swings(r)
        if phase in {"D", "E"}:
            if mode == "ACCUMULATION" and lows:
                anchor = lows[-1]
                age = len(r) - 1 - anchor
                notes.append(f"Move-start anchored to last swing low (age={age} bars)")
                return anchor, age, notes
            if mode == "DISTRIBUTION" and highs:
                anchor = highs[-1]
                age = len(r) - 1 - anchor
                notes.append(f"Move-start anchored to last swing high (age={age} bars)")
                return anchor, age, notes

        # Range phases: no clear start
        notes.append("No dominant move-start; likely rotational")
        return None, None, notes


# -----------------------------------------------------------------------------
# Backwards-compatible wrapper functions
# -----------------------------------------------------------------------------

_STATE_MACHINE = WyckoffCrabelStateMachine()


def classify_wyckoff_state(bars: pd.DataFrame) -> Dict:
    """Replacement for the prior naive classifier.

    Always returns a phase and event mapping suitable for AVSHUNTER.
    """
    return _STATE_MACHINE.analyse(bars)


def determine_direction_intent(bars: pd.DataFrame) -> Dict:
    """Convenience wrapper when only direction/intent fields are needed."""
    out = _STATE_MACHINE.analyse(bars)
    return {
        "wyckoff_phase": out["wyckoff_phase"],
        "wyckoff_mode": out["wyckoff_mode"],
        "control_state": out["control_state"],
        "primary_event": out["primary_event"],
        "intent": out["intent"],
        "transition_to": out["transition_to"],
        "notes_top5": out["notes_top5"],
    }


def process_precore_signal(ticker: str, bars: pd.DataFrame) -> Dict:
    """Main entry point used by AVSHUNTER discovery scripts.

    Returns a ticker-tagged payload that downstream code can log and rank.
    """
    out = _STATE_MACHINE.analyse(bars)
    out["ticker"] = ticker
    return out
