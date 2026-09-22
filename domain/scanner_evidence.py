"""Scanner evidence classifications; no thesis or execution authority.

Aggregate call/put volume can describe concentration, but cannot identify an
exchange sweep or which side initiated a trade without transaction prints.
"""

from __future__ import annotations


def volume_concentration_side(call_volume: int, put_volume: int) -> str:
    """Classify observed chain volume, preserving the no-volume state."""
    if call_volume <= 0 and put_volume <= 0:
        return "NO_VOLUME"
    if put_volume <= 0 or call_volume >= 2 * put_volume:
        return "CALL"
    if call_volume <= 0 or put_volume >= 2 * call_volume:
        return "PUT"
    return "BALANCED"


def lead_route(score: float, missing_evidence: tuple[str, ...]) -> tuple[str, str]:
    """Rank complete leads; an incomplete/weak score never excludes a ticker."""
    if missing_evidence:
        return "LEAD_INCOMPLETE", "WATCHLIST_ONLY"
    if score >= 75:
        return "LEAD_GO", "FULL_PIPELINE"
    if score >= 60:
        return "LEAD_PROBE", "DISCOVERY_ONLY"
    return "LEAD_WATCH", "WATCHLIST_ONLY"
