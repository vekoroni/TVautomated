"""D2 — the run manifest reports thesis geometry completeness at the right grain (ACK, 25 Sep 2026).

Root cause (Enhancements/research/rca/D2_MANIFEST_GEOMETRY_GRAIN_RCA_AND_DESIGN_20260925.md): the manifest carries
one count (missing invalidation) with no denominator, counts no missing targets, never looks at the actionable
rows, and decides run_tradeable without semantic health, so EXECUTION_READY sits beside DEGRADED.

Business rules (ACK, reviewer amendment "grain-correct D2"):
- Distinct counts for missing target, missing invalidation and both, each beside its denominator.
- The actionable rows (routed GO / GO_LIMIT) are counted separately.
- The label says so only when an actionable row lacks geometry; run_tradeable and the permissions never change.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from contracts.lab_control import build_final_run_manifest

RUN = "20990102_000000"


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _row(ticker, *, target="110", invalidation="95", route="MONITOR_CONTRACT_LIQUIDITY", direction="CALL"):
    """Production shape: the candidates file carries geometry (target_price / invalidation_spot) and no route;
    the validated-trades file carries the route. `_make_run` splits the two."""
    return {"ticker": ticker, "governed_direction": direction, "target_price": target,
            "invalidation_spot": invalidation, "invalidation_state": "AVAILABLE" if invalidation else "MISSING",
            "morning_execution_route": route, "candidate_status": "MORNING_VALIDATION_REQUIRED"}


def _make_run(root: Path, candidates: list[dict]) -> None:
    d = root / RUN
    tickers = [{"ticker": r["ticker"]} for r in candidates] or [{"ticker": "NONE"}]
    _write_csv(d / "discovery" / f"discovery_candidates_{RUN}.csv", tickers)
    _write_csv(d / "options" / f"vanguard_signals_enriched_{RUN}.csv",
               [{**t, "physics_state_id": "PHYS|TEST", "state_transition_label": "CONTINUATION_UP"} for t in tickers])
    _write_csv(d / "options" / f"options_intelligence_{RUN}.csv", [{**t, "options_verdict": "EXECUTE"} for t in tickers])
    _write_csv(d / "execution" / f"execution_v3_5_{RUN}.csv", [{**t, "execution_verdict": "BUY_NOW"} for t in tickers])
    _write_csv(d / "morning_validation" / f"morning_candidates_{RUN}.csv",
               [{k: v for k, v in r.items() if k != "morning_execution_route"} for r in candidates] or [{"ticker": "NONE"}])
    _write_csv(d / "morning_validation" / f"morning_validated_trades_{RUN}.csv",
               [{"ticker": r["ticker"], "morning_execution_route": r["morning_execution_route"], "live_data_mode": "LIVE"}
                for r in candidates] or [{"ticker": "NONE", "live_data_mode": "LIVE"}])
    _write_csv(d / "superbrain" / f"eil_enriched_{RUN}.csv",
               [{**t, "eil_v3_verdict": "EXECUTE", "macro_regime_label": "RISK_ON", "macro_freshness_status": "FRESH"} for t in tickers])


MODE = "MORNING_VALIDATION"


COMPLETE = [_row("AAA"), _row("BBB", route="GO_LIMIT"), _row("CCC", route="GO")]
MIXED = [
    _row("AAA"),                                             # complete, monitored
    _row("BBB", route="GO_LIMIT"),                           # complete, actionable
    _row("CCC", target=""),                                  # target missing, monitored
    _row("DDD", invalidation=""),                            # invalidation missing, monitored
    _row("EEE", target="", invalidation=""),                 # both missing, monitored
    _row("FFF", direction="", target="", invalidation=""),   # no direction: not a thesis, not in the population
]
ACTIONABLE_DEFECT = MIXED + [_row("GGG", route="GO", invalidation="")]   # invalidation missing on a GO row


# ── Characterisation: complete geometry leaves everything as today ────────────────────────────────────────
def test_characterisation_complete_geometry_is_execution_ready_as_today(tmp_path):
    _make_run(tmp_path, COMPLETE)
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)
    assert m["run_tradeable"] is True
    assert m["run_tradeable_label"] == "EXECUTION_READY"
    assert m["missing_selected_handoff"] == {"invalidation_spot": 0}
    assert m["pipeline_semantic_health"] == "PASS"


# ── Business rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_counts_are_reported_by_grain_with_denominators(tmp_path):
    _make_run(tmp_path, MIXED)
    g = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)["thesis_geometry_completeness"]
    assert g["population"] == 5                     # FFF has no direction
    assert g["missing_target"] == 2                 # CCC, EEE
    assert g["missing_invalidation"] == 2           # DDD, EEE
    assert g["missing_both"] == 1                   # EEE
    assert g["complete"] == 2                       # AAA, BBB
    assert g["actionable_population"] == 1          # BBB
    assert g["actionable_missing_target"] == 0
    assert g["actionable_missing_invalidation"] == 0
    assert g["actionable_missing_both"] == 0


def test_the_legacy_count_is_unchanged_and_the_label_stays_when_no_actionable_row_is_affected(tmp_path):
    _make_run(tmp_path, MIXED)
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)
    assert m["missing_selected_handoff"]["invalidation_spot"] == 2      # as today: DDD, EEE
    assert m["run_tradeable"] is True
    assert m["run_tradeable_label"] == "EXECUTION_READY"
    assert not any(f.startswith("ACTIONABLE_GEOMETRY_DEFECTS") for f in m["stale_flags"])


def test_the_label_says_so_when_an_actionable_row_lacks_geometry_and_nothing_else_changes(tmp_path):
    _make_run(tmp_path, ACTIONABLE_DEFECT)
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)
    g = m["thesis_geometry_completeness"]
    assert g["actionable_population"] == 2 and g["actionable_missing_invalidation"] == 1
    assert m["run_tradeable_label"] == "EXECUTION_READY_ACTIONABLE_GEOMETRY_DEFECTS"
    assert "ACTIONABLE_GEOMETRY_DEFECTS:1" in m["stale_flags"]
    # routing preserved
    assert m["run_tradeable"] is True
    assert m["run_execution_permission"] == "READY_FOR_LAB"
    assert m["run_prep_permission"] == "NONE"
    assert m["next_action"] == "READY_FOR_LAB"


def test_the_block_is_present_and_zero_when_there_are_no_candidates(tmp_path):
    _make_run(tmp_path, [])
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)
    g = m["thesis_geometry_completeness"]
    assert g["population"] == 0 and g["actionable_population"] == 0
    assert m["run_tradeable_label"] != "EXECUTION_READY_ACTIONABLE_GEOMETRY_DEFECTS"


def test_the_block_survives_a_json_round_trip(tmp_path):
    _make_run(tmp_path, MIXED)
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode=MODE)
    assert json.loads(json.dumps(m))["thesis_geometry_completeness"] == m["thesis_geometry_completeness"]
