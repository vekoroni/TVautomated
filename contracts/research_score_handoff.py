"""Research ranking input only; never grants execution or clears a veto."""
import math


def score_handoff(row):
    raw = row.get("options_research_score")
    present = raw is not None and str(raw).strip().lower() not in {"", "nan", "none"}
    if present:
        try:
            score = float(raw)
        except (ValueError, TypeError):
            score = float("nan")
        valid = math.isfinite(score) and 0 <= score <= 100
        return {
            "ranking_score_source": "OPTIONS_RESEARCH" if valid else "INVALID_OPTIONS_RESEARCH",
            "ranking_score_100": score if valid else None,
            # Existing EOD thresholds 15/25/35 and fit /2.5 use a 50-point scale.
            "ranking_score_eod_50": score / 2 if valid else 0.0,
            "ranking_score_authority": "RESEARCH_RANKING_ONLY",
        }
    try:
        legacy = float(row.get("options_score") or 0)
    except (ValueError, TypeError):
        legacy = 0.0
    if not math.isfinite(legacy) or legacy < 0:
        legacy = 0.0
    return {
        "ranking_score_source": "LEGACY_FALLBACK",
        "ranking_score_100": None,
        "ranking_score_eod_50": legacy,
        "ranking_score_authority": "RESEARCH_RANKING_ONLY",
    }


def eod_ranking_score(row):
    return score_handoff(row)["ranking_score_eod_50"]
