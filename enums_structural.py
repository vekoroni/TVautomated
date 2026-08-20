"""
enums_structural.py
===================
Canonical string constants for the Structural Signal Layer.

ALL modules that emit or consume control_state, direction, intent,
crabel_state, or wyckoff_phase MUST import from here.

This eliminates the BUYERS_IN_CONTROL vs BUYERS enum drift that caused
silent control-check failures throughout the fusion pipeline.

Usage:
    from enums_structural import ControlState, Direction, Intent, CrabelState

DO NOT define these strings in any other file.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Control state — single canonical set used by WyckoffEngine, precor, fusion
# ---------------------------------------------------------------------------
class ControlState:
    BUYERS      = "BUYERS"
    SELLERS     = "SELLERS"
    EQUILIBRIUM = "EQUILIBRIUM"
    SHIFTING    = "SHIFTING"
    UNKNOWN     = "UNKNOWN"

    ALL = {BUYERS, SELLERS, EQUILIBRIUM, SHIFTING, UNKNOWN}

    # Legacy aliases — map old strings to canonical (used by normalise())
    _LEGACY_MAP = {
        "BUYERS_IN_CONTROL":  BUYERS,
        "SELLERS_IN_CONTROL": SELLERS,
        "CONTROL_SHIFTING":   SHIFTING,
        "BUYER":              BUYERS,
        "SELLER":             SELLERS,
    }

    @classmethod
    def normalise(cls, raw: str) -> str:
        """Convert any legacy or variant string to canonical form."""
        s = str(raw).strip().upper()
        if s in cls.ALL:
            return s
        return cls._LEGACY_MAP.get(s, cls.UNKNOWN)


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------
class Direction:
    LONG  = "LONG"
    SHORT = "SHORT"
    NONE  = "NONE"

    ALL = {LONG, SHORT, NONE}


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------
class Intent:
    BUY_SETUP    = "BUY_SETUP"
    SELL_SETUP   = "SELL_SETUP"
    TRANSITION   = "TRANSITION"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    WAIT         = "WAIT"

    ALL = {BUY_SETUP, SELL_SETUP, TRANSITION, OBSERVE_ONLY, WAIT}

    # Intents that represent actionable go-signals
    GO_INTENTS = {BUY_SETUP, SELL_SETUP}


# ---------------------------------------------------------------------------
# Crabel compression state
# ---------------------------------------------------------------------------
class CrabelState:
    COILING       = "COILING"
    READY         = "READY"          # canonical (was CRABEL_READY in precor)
    CRABEL_READY  = "CRABEL_READY"   # legacy alias — normalise() maps → READY
    NONE          = "NONE"

    COMPRESSED_STATES = {COILING, READY, CRABEL_READY}

    @classmethod
    def normalise(cls, raw: str) -> str:
        s = str(raw).strip().upper()
        if s == cls.CRABEL_READY:
            return cls.READY
        if s in {cls.COILING, cls.READY, cls.NONE}:
            return s
        return cls.NONE


# ---------------------------------------------------------------------------
# Wyckoff phase
# ---------------------------------------------------------------------------
class WyckoffPhase:
    A       = "A"
    B       = "B"
    C       = "C"
    D       = "D"
    E       = "E"
    UNKNOWN = "UNKNOWN"

    ALL = {A, B, C, D, E, UNKNOWN}

    RANGE_PHASES  = {A, B, C}
    TREND_PHASES  = {D, E}


# ---------------------------------------------------------------------------
# Wyckoff operator (mode)
# ---------------------------------------------------------------------------
class Operator:
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    MARKUP       = "MARKUP"
    MARKDOWN     = "MARKDOWN"
    UNCLEAR      = "UNCLEAR"

    ALL = {ACCUMULATION, DISTRIBUTION, MARKUP, MARKDOWN, UNCLEAR}

    # Operators compatible with LONG direction
    LONG_OPERATORS  = {ACCUMULATION, MARKUP}
    # Operators compatible with SHORT direction
    SHORT_OPERATORS = {DISTRIBUTION, MARKDOWN}
