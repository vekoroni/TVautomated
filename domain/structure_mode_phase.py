"""Versioned Wyckoff mode/phase identity for structural replay.

This is deliberately distinct from the legacy broad actuarial phase bucket.
Unknown evidence remains unknown rather than acquiring a bullish default.
"""

_MODES = {"ACCUMULATION", "DISTRIBUTION", "REACCUMULATION", "REDISTRIBUTION"}
_PHASES = {"A", "B", "C", "D", "E"}


def mode_phase_key(mode: object, phase: object) -> str:
    """Return a stable mode:phase key without inferring either missing component."""
    clean_mode = str(mode or "").strip().upper()
    clean_phase = str(phase or "").strip().upper()
    if clean_mode not in _MODES:
        clean_mode = "UNKNOWN"
    if clean_phase not in _PHASES:
        clean_phase = "UNCONFIRMED"
    return f"{clean_mode}:{clean_phase}"


def resolve_mode_phase_identity(
    precore_mode: object, precore_phase: object, engine_phase: object
) -> tuple[str, str]:
    """Keep a mode tied to its own engine's phase, with explicit provenance."""
    if str(precore_phase or "").strip().upper() in _PHASES:
        return mode_phase_key(precore_mode, precore_phase), "PRECORE_MODE_PHASE"
    return mode_phase_key("UNKNOWN", engine_phase), "ENGINE_PHASE_ONLY"
