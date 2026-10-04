"""Regression gate for the Fix Spec's four dossier checks plus the flagged-state check.

Synthetic rows only; the CLI reads a stored run read-only and is exercised by the
release process, not here.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Enhancements.assessment.dossier_field_integrity_gate import (  # noqa: E402
    audit_rows, direction_of, gf_bad, ivp_bad, rr_bad, rr_state_inconsistent, wall_bad, wall_side_bad,
)


def test_rr_check_accepts_explained_losses_and_rejects_unexplained_or_implausible_values():
    assert not rr_bad({"rr_options": 2.5})
    assert not rr_bad({"rr_options": -0.4, "rr_options_state": "PRICED_TARGET_INSIDE_BREAKEVEN"})
    assert not rr_bad({"rr_options": -1.0, "rr_options_state": "STRIKE_BEYOND_TARGET"})
    assert rr_bad({"rr_options": -0.4, "rr_options_state": "PRICED_TARGET_ABOVE_BREAKEVEN"})
    assert rr_bad({"rr_options": 659.4})
    assert rr_bad({"rr_options": -1.5})
    assert not rr_bad({"rr_options": None})
    assert not rr_bad({"opt__rr_options": ""})


def test_flagged_state_check_only_applies_once_the_state_field_exists():
    assert not rr_state_inconsistent({"rr_options": None})            # pre-fix dossier
    assert not rr_state_inconsistent({"rr_options": None, "rr_options_state": "MARK_UNPRICED"})
    assert not rr_state_inconsistent({"rr_options": 1.2, "rr_options_state": "PRICED_TARGET_ABOVE_BREAKEVEN"})
    assert rr_state_inconsistent({"rr_options": None, "rr_options_state": None})          # silently dropped
    assert rr_state_inconsistent({"rr_options": 1.2, "rr_options_state": "MARK_UNPRICED"})  # contradictory
    assert rr_state_inconsistent({"rr_options": None, "rr_options_state": "STRIKE_BEYOND_TARGET"})


def test_ivp_label_must_match_the_single_threshold_convention():
    assert not ivp_bad({"iv_percentile": 0.40, "ivp_label": "CHEAP"})
    assert not ivp_bad({"iv_percentile": 0.65, "ivp_label": "FAIR"})
    assert not ivp_bad({"iv_percentile": 0.66, "ivp_label": "EXPENSIVE"})
    assert ivp_bad({"iv_percentile": 0.20, "ivp_label": "FAIR"})
    assert ivp_bad({"opt__iv_percentile": "0.90", "opt__ivp_label": "CHEAP"})
    assert not ivp_bad({"iv_percentile": None, "ivp_label": "CHEAP"})


def test_wall_side_check_flags_a_call_wall_below_spot_or_a_put_wall_above_it():
    assert wall_side_bad({"entry_spot": 17.13, "call_wall": 15.0, "put_wall": 12.0})
    assert wall_side_bad({"entry_spot": 17.13, "call_wall": 20.0, "put_wall": 20.0})
    assert not wall_side_bad({"entry_spot": 17.13, "call_wall": 20.0, "put_wall": 15.0})
    assert not wall_side_bad({"entry_spot": 17.13, "call_wall": None, "put_wall": 15.0})
    assert not wall_side_bad({"call_wall": 15.0, "put_wall": 12.0})            # no spot: cannot judge


def test_wall_and_gamma_flip_checks_use_prefixed_or_plain_names():
    assert wall_bad({"call_wall": 15.0, "put_wall": 15.0})
    assert not wall_bad({"call_wall": 15.0, "put_wall": 12.5})
    assert not wall_bad({"call_wall": None, "put_wall": 12.5})
    assert gf_bad({"gamma_flip": 400.0, "strike": 100.0})
    assert gf_bad({"opt__gamma_flip": 5.0, "opt__strike": 100.0})
    assert not gf_bad({"gamma_flip": 105.0, "contract_strike": 100.0})
    assert not gf_bad({"gamma_flip": 105.0})


def test_audit_splits_by_direction_and_reports_clean_rate():
    rows = [
        {"options_direction": "CALL", "rr_options": 1.0, "iv_percentile": 0.3, "ivp_label": "CHEAP",
         "call_wall": 10, "put_wall": 9, "gamma_flip": 10, "strike": 10},
        {"options_direction": "PUT", "rr_options": -0.5, "rr_options_state": "PRICED_TARGET_INSIDE_BREAKEVEN",
         "iv_percentile": 0.5, "ivp_label": "FAIR", "call_wall": 10, "put_wall": 10, "gamma_flip": 10, "strike": 10},
        {"governed_direction": "PUT", "rr_options": 30.0},
    ]
    report = audit_rows(rows)
    assert direction_of(rows[2]) == "PUT"
    assert report["CALL"] == {"rows": 1, "clean": 1, "clean_rate": 1.0, "rr_bad": 0, "rr_state_inconsistent": 0,
                              "ivp_bad": 0, "wall_bad": 0, "wall_side_bad": 0, "gf_bad": 0}
    assert report["PUT"]["rows"] == 2 and report["PUT"]["clean"] == 0
    assert report["PUT"]["wall_bad"] == 1 and report["PUT"]["rr_bad"] == 1
    assert report["ALL"]["clean_rate"] == round(1 / 3, 4)
