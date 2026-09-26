"""A1 — thesis geometry labels say what was measured (ACK, 25 Sep 2026).

Design: Enhancements/research/rca/A1_THESIS_GEOMETRY_RECONCILIATION_RCA_AND_DESIGN_20260925.md

Business rules (ACK, reviewer amendments A1):
- A row whose only invalidation candidates lie on the wrong side of spot is DATA_DEFECT_WRONG_SIDE, not MISSING;
  the routing field invalidation_state is unchanged (additive field invalidation_candidate_state).
- A computed fallback target (target_spot) reaches the Lab book with its source label.
- The manifest counts missing geometry by source, degenerate levels relative to the expected move (never a
  fixed percent), unassessed rows, and targets beyond 3x the expected move; nothing routes on them.
"""

from __future__ import annotations

import csv
from pathlib import Path

from contracts.lab_control import (
    _enrich_lab_extract_rows_from_run_sources,
    _lab_extract_field_aliases,
    build_final_run_manifest,
)
from scripts.avshunter_options_intelligence import _ev3_handoff_fields

RUN = "20990110_000000"


def _ctx(direction="CALL", stop=None, stop_state="MISSING", stop_authoritative=None):
    return {"direction": direction, "entry": 100.0, "structural_target": 110.0 if direction == "CALL" else 90.0,
            "stop": stop, "stop_authoritative": stop is not None if stop_authoritative is None else stop_authoritative,
            "stop_source": "WYCKOFF_VALIDATION" if stop is not None else "MISSING_AUTHORITATIVE_STOP",
            "stop_state": stop_state, "horizon_bucket": "6_10d", "spot": 100.0}


# ── Handoff ────────────────────────────────────────────────────────────────────────────────────────────────
def test_characterisation_the_routing_state_is_still_missing_when_no_stop_is_on_side():
    fields = _ev3_handoff_fields(_ctx(stop=None, stop_state="DATA_DEFECT_WRONG_SIDE"))
    assert fields["invalidation_spot"] is None
    assert fields["invalidation_state"] == "MISSING"
    assert fields["invalidation_source"] == "MISSING_AUTHORITATIVE_STOP"


def test_a_wrong_side_candidate_is_named_beside_the_routing_state():
    fields = _ev3_handoff_fields(_ctx(stop=None, stop_state="DATA_DEFECT_WRONG_SIDE"))
    assert fields["invalidation_candidate_state"] == "DATA_DEFECT_WRONG_SIDE"


def test_no_numeric_candidate_at_all_is_missing():
    assert _ev3_handoff_fields(_ctx(stop=None, stop_state="MISSING"))["invalidation_candidate_state"] == "MISSING"


def test_an_available_stop_is_available():
    fields = _ev3_handoff_fields(_ctx(stop=95.0, stop_state="AVAILABLE"))
    assert fields["invalidation_state"] == "AVAILABLE" and fields["invalidation_candidate_state"] == "AVAILABLE"


def test_a_non_directional_thesis_is_not_applicable():
    assert _ev3_handoff_fields(_ctx(direction="STRANGLE", stop=None))["invalidation_candidate_state"] == "NOT_APPLICABLE_NON_DIRECTIONAL"


# ── Lab extract ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_lab_extract_reads_a_computed_fallback_target(tmp_path):
    aliases = _lab_extract_field_aliases()
    assert "target_spot" in aliases["structural_target"] and "target_spot" in aliases
    assert "invalidation_candidate_state" in aliases
    run_id = "20990110_000000"
    options = tmp_path / run_id / "options"
    options.mkdir(parents=True)
    with (options / f"options_intelligence_{run_id}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "trade_idea_id", "target_spot", "structural_target",
                                            "structural_target_state", "invalidation_candidate_state"])
        w.writeheader()
        w.writerow({"ticker": "NLST", "trade_idea_id": f"{run_id}:NLST:CALL:NA:NA", "target_spot": "15.64",
                    "structural_target": "", "structural_target_state": "TARGET_3R",
                    "invalidation_candidate_state": "AVAILABLE"})
    rows = [{"ticker": "NLST", "trade_idea_id": f"{run_id}:NLST:CALL:NA:NA"}]
    _enrich_lab_extract_rows_from_run_sources(rows, tmp_path, run_id)
    assert float(rows[0]["structural_target"]) == 15.64
    assert rows[0]["invalidation_candidate_state"] == "AVAILABLE"


# ── Manifest ───────────────────────────────────────────────────────────────────────────────────────────────
def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _cand(ticker, *, direction="CALL", spot="100", target="110", inval="95", route="MONITOR_CONTRACT_LIQUIDITY",
          tsrc="DISCOVERY_TARGET", isrc="WYCKOFF_VALIDATION", bucket="1_5d", em=("4.0", "2.0", "3.0")):
    return {"ticker": ticker, "governed_direction": direction, "signal_price": spot, "target_price": target,
            "invalidation_spot": inval, "invalidation_state": "AVAILABLE" if inval else "MISSING",
            "target_price_source": tsrc, "invalidation_source": isrc if inval else "MISSING_AUTHORITATIVE_STOP",
            "time_horizon": bucket, "garch_expected_move_1_5d": em[0], "garch_expected_move_6_10d": em[1],
            "garch_expected_move_11_20d": em[2], "morning_execution_route": route,
            "candidate_status": "MORNING_VALIDATION_REQUIRED"}


def _make_run(root: Path, candidates: list[dict]) -> None:
    d = root / RUN
    t = [{"ticker": r["ticker"]} for r in candidates]
    _write_csv(d / "discovery" / f"discovery_candidates_{RUN}.csv", t)
    _write_csv(d / "options" / f"vanguard_signals_enriched_{RUN}.csv",
               [{**x, "physics_state_id": "PHYS|TEST", "state_transition_label": "CONTINUATION_UP"} for x in t])
    _write_csv(d / "options" / f"options_intelligence_{RUN}.csv", [{**x, "options_verdict": "EXECUTE"} for x in t])
    _write_csv(d / "execution" / f"execution_v3_5_{RUN}.csv", [{**x, "execution_verdict": "BUY_NOW"} for x in t])
    _write_csv(d / "morning_validation" / f"morning_candidates_{RUN}.csv",
               [{k: v for k, v in r.items() if k != "morning_execution_route"} for r in candidates])
    _write_csv(d / "morning_validation" / f"morning_validated_trades_{RUN}.csv",
               [{"ticker": r["ticker"], "morning_execution_route": r["morning_execution_route"], "live_data_mode": "LIVE"} for r in candidates])
    _write_csv(d / "superbrain" / f"eil_enriched_{RUN}.csv",
               [{**x, "eil_v3_verdict": "EXECUTE", "macro_regime_label": "RISK_ON", "macro_freshness_status": "FRESH"} for x in t])


ROWS = [
    _cand("OK1", route="GO_LIMIT"),                                                   # complete, 1_5d move 4%: target 10% away, inval 5% away
    _cand("DEG", route="GO_LIMIT", target="100.5", inval="99.6"),                    # both inside 0.25 x 4% = 1%: degenerate
    _cand("FAR", bucket="6_10d", target="130", em=("4.0", "2.0", "3.0")),            # 6_10d cumulative move 6%; target 30% away > 3 x 6% = 18%
    _cand("NOINV", inval=""),                                                        # missing invalidation, source MISSING_AUTHORITATIVE_STOP
    _cand("NOTGT", target="", tsrc="TARGET_3R_NON_POSITIVE", direction="PUT", inval="140"),  # missing target by source
    _cand("NOEM", em=("", "", "")),                                                  # no move fields: unassessed
]


def test_geometry_counts_by_source_degenerate_and_reachability(tmp_path):
    _make_run(tmp_path, ROWS)
    m = build_final_run_manifest(RUN, tmp_path, pipeline_mode="MORNING_VALIDATION")
    g = m["thesis_geometry_completeness"]
    assert g["population"] == 6 and g["missing_invalidation"] == 1 and g["missing_target"] == 1
    assert g["missing_invalidation_by_source"] == {"MISSING_AUTHORITATIVE_STOP": 1}
    assert g["missing_target_by_source"] == {"TARGET_3R_NON_POSITIVE": 1}
    assert g["degenerate_vol_relative"] == 1                    # DEG
    assert g["actionable_degenerate_vol_relative"] == 1         # DEG is routed GO_LIMIT
    assert g["degenerate_unassessed"] == 1                      # NOEM
    assert g["target_beyond_3x_expected_move"] == 1             # FAR
    assert g["expected_move_basis"] == "CUMULATIVE_1SIGMA_CANONICAL_OR_COMPLETE_LEGACY_PCT"
    # nothing routes on these counts
    assert m["run_tradeable"] is True and m["run_tradeable_label"] == "REVIEW_REQUIRED_SEMANTIC_HANDOFF_DEFECTS"
    assert not any("DEGENERATE" in f for f in m["stale_flags"])
