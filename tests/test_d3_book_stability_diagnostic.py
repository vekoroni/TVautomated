"""D3 — book stability as a manifest diagnostic, split by cause, morning to morning (ACK, 25 Sep 2026).

Design: Enhancements/research/rca/D3_BOOK_STABILITY_DIAGNOSTIC_RCA_AND_DESIGN_20260925.md

Business rules (ACK, reviewer amendment "D3 as a diagnostic, not a run-health failure"):
- Compare like with like: this morning's actionable set (routed GO / GO_LIMIT) with the previous morning-mode
  run's, skipping EOD folders in between.
- Every dropped row is attributed to one cause: absent from the book, geometry missing, quote not executable
  (by viability state), or routed out (by route).
- Diagnostic only: no stale flag, no health penalty, no change to the label or permissions.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from contracts.lab_control import build_final_run_manifest

PREV, EOD_BETWEEN, CUR = "20990105_000000", "20990106_000000", "20990107_000000"


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _v(ticker, route="GO_LIMIT", viability="EXECUTABLE_QUOTE", target="110", invalidation="95"):
    return {"ticker": ticker, "morning_execution_route": route, "execution_viability_state": viability,
            "target_price": target, "invalidation_spot": invalidation, "live_data_mode": "LIVE"}


def _make_run(root: Path, run_id: str, mode: str, session: str, validated: list[dict] | None) -> None:
    d = root / run_id
    tickers = [{"ticker": r["ticker"]} for r in (validated or [])] or [{"ticker": "NONE"}]
    _write_csv(d / "discovery" / f"discovery_candidates_{run_id}.csv", tickers)
    _write_csv(d / "options" / f"vanguard_signals_enriched_{run_id}.csv",
               [{**t, "physics_state_id": "PHYS|TEST", "state_transition_label": "CONTINUATION_UP"} for t in tickers])
    _write_csv(d / "options" / f"options_intelligence_{run_id}.csv", [{**t, "options_verdict": "EXECUTE"} for t in tickers])
    _write_csv(d / "execution" / f"execution_v3_5_{run_id}.csv", [{**t, "execution_verdict": "BUY_NOW"} for t in tickers])
    _write_csv(d / "morning_validation" / f"morning_candidates_{run_id}.csv",
               [{**t, "governed_direction": "CALL", "target_price": "110", "invalidation_spot": "95",
                 "candidate_status": "MORNING_VALIDATION_REQUIRED"} for t in tickers])
    if validated is not None:
        _write_csv(d / "morning_validation" / f"morning_validated_trades_{run_id}.csv", validated)
    _write_csv(d / "superbrain" / f"eil_enriched_{run_id}.csv",
               [{**t, "eil_v3_verdict": "EXECUTE", "macro_regime_label": "RISK_ON", "macro_freshness_status": "FRESH"} for t in tickers])
    (d / "run_meta.json").write_text(json.dumps({"pipeline_mode": mode, "session_date": session}), encoding="utf-8")


PREV_ROWS = [_v("KEEP"), _v("KEEP2"), _v("GONE"), _v("NOGEO"), _v("WIDE"), _v("ROUTED"), _v("WATCH", route="MONITOR_CONTRACT_LIQUIDITY")]
CUR_ROWS = [
    _v("KEEP"), _v("KEEP2"),                                                     # retained
    _v("NOGEO", route="STAND_DOWN_UPSTREAM_AUTHORITY", invalidation=""),        # geometry lost overnight (attributed before route)
    _v("WIDE", route="MONITOR_CONTRACT_LIQUIDITY", viability="BLOCKED_WIDE_SPREAD"),  # quote not executable
    _v("ROUTED", route="STAND_DOWN_DIRECTION"),                                 # executable but routed out
    _v("NEW1"), _v("NEW2"),                                                     # new entrants
    _v("WATCH", route="MONITOR_CONTRACT_LIQUIDITY"),                            # never actionable
]                                                                               # GONE: absent from the book


def _two_morning_runs(root: Path, eod_between: bool = False) -> None:
    _make_run(root, PREV, "MORNING_VALIDATION", "2099-01-05", PREV_ROWS)
    if eod_between:
        _make_run(root, EOD_BETWEEN, "EOD", "2099-01-06", None)
    _make_run(root, CUR, "MORNING_VALIDATION", "2099-01-07", CUR_ROWS)


# ── Characterisation: no prior morning book leaves everything as before ─────────────────────────────────────
def test_characterisation_without_a_prior_morning_book_nothing_else_changes(tmp_path):
    _make_run(tmp_path, CUR, "MORNING_VALIDATION", "2099-01-07", CUR_ROWS)
    m = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")
    assert m["book_stability"]["state"] == "NO_PRIOR_MORNING_BOOK"
    assert m["book_stability"]["authority"] == "DIAGNOSTIC_ONLY"
    assert m["run_tradeable"] is True and m["run_tradeable_label"] == "EXECUTION_READY"
    assert not any("STABILITY" in f for f in m["stale_flags"])


# ── Business rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_retained_new_and_dropped_are_counted_with_the_cause_split(tmp_path):
    _two_morning_runs(tmp_path)
    b = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")["book_stability"]
    assert b["state"] == "COMPUTED" and b["basis"] == "MORNING_VALIDATION_TO_MORNING_VALIDATION"
    assert b["previous_run_id"] == PREV
    assert b["previous_actionable"] == 6 and b["current_actionable"] == 4
    assert b["retained"] == 2 and b["retained_share"] == 0.333
    assert b["new_entrants"] == 2 and b["dropped"] == 4
    assert b["dropped_by_cause"] == {
        "ABSENT_FROM_BOOK": 1,
        "GEOMETRY_MISSING": 1,
        "QUOTE_NOT_EXECUTABLE": {"BLOCKED_WIDE_SPREAD": 1},
        "ROUTED_OUT": {"STAND_DOWN_DIRECTION": 1},
    }
    assert b["previous_session_date"] == "2099-01-05" and b["current_session_date"] == "2099-01-07"
    assert b["sessions_between"] == 2


def test_an_eod_folder_between_two_morning_runs_is_skipped(tmp_path):
    _two_morning_runs(tmp_path, eod_between=True)
    b = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")["book_stability"]
    assert b["state"] == "COMPUTED" and b["previous_run_id"] == PREV


def test_an_eod_run_is_not_applicable(tmp_path):
    _make_run(tmp_path, PREV, "MORNING_VALIDATION", "2099-01-05", PREV_ROWS)
    _make_run(tmp_path, CUR, "EOD", "2099-01-07", None)
    b = build_final_run_manifest(CUR, tmp_path, pipeline_mode="EOD")["book_stability"]
    assert b["state"] == "NOT_APPLICABLE_EOD"


def test_the_diagnostic_never_touches_flags_health_label_or_permissions(tmp_path):
    _make_run(tmp_path, CUR, "MORNING_VALIDATION", "2099-01-07", CUR_ROWS)
    alone = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")
    _make_run(tmp_path, PREV, "MORNING_VALIDATION", "2099-01-05", PREV_ROWS)
    compared = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")
    assert compared["book_stability"]["state"] == "COMPUTED"
    for key in ("stale_flags", "run_health_score", "run_tradeable", "run_tradeable_label",
                "run_execution_permission", "run_prep_permission", "next_action"):
        assert compared[key] == alone[key], key


def test_the_block_survives_a_json_round_trip(tmp_path):
    _two_morning_runs(tmp_path)
    m = build_final_run_manifest(CUR, tmp_path, pipeline_mode="MORNING_VALIDATION")
    assert json.loads(json.dumps(m))["book_stability"] == m["book_stability"]
