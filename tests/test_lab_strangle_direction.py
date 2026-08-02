"""
FIX-5 — the Lab must not collapse a non-directional STRANGLE setup into a
single-leg CALL/PUT label. See LAB_QA_REPORT.md F1/F2 and
CLAUDE_CODE_TASK_lab_fix_sprint.md Phase 2.

Root cause: _normalise_direction_value() (intelligence_lab.py) walks a
priority list of direction-indicating fields. options_direction correctly
resolves "STRANGLE" to "" via _side_from_value (not a side), but the loop
then falls through to options_strategy (a single leg Phase 7 chose for
display/execution, e.g. "LONG_PUT"), which _side_from_value happily reads as
"PUT" on a substring match. The fix must distinguish "explicitly
non-directional" (stop, do not fall through) from "field absent" (keep
falling through, unchanged behaviour).
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_for_strangle_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(c, "")) for c in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_EIL_COLUMNS = [
    "ticker", "options_direction", "options_strategy", "strike", "structural_target",
    "premium_mid", "expiry", "lab_verdict", "eil_v3_verdict",
]


def _make_run(tmp_path: Path, run_id: str, rows: list[dict], lab):
    # eil_v3_verdict and a morning_validated_trades file are here purely to
    # satisfy contracts/lab_control.py's independent run-health check
    # (PHASE_REQUIRED_COLUMNS / EOD_CANDIDATE_MANIFEST_MISSING) so it doesn't
    # blanket-BLOCK every row in this minimal fixture for reasons unrelated
    # to the STRANGLE fix under test.
    lab.RUNS_DIR = tmp_path / "runs"
    lab._run_cache.clear()
    run_dir = lab.RUNS_DIR / run_id
    rows = [dict(r, eil_v3_verdict=r.get("lab_verdict", "GO")) for r in rows]
    _write_csv(run_dir / "superbrain" / f"eil_enriched_{run_id}.csv", _EIL_COLUMNS, rows)
    mv_columns = ["ticker", "morning_execution_permission", "live_validation_state"]
    _write_csv(
        run_dir / "morning_validation" / f"morning_validated_trades_{run_id}.csv",
        mv_columns,
        [{"ticker": r["ticker"], "morning_execution_permission": "GO", "live_validation_state": "CONFIRMED"} for r in rows],
    )
    return run_dir


_FIXTURE_ROWS = [
    {
        # STRANGLE: options_direction explicitly non-directional. options_strategy
        # is a single leg (LONG_PUT) — this must NOT win. structural_target (110)
        # sits above strike (100), on the wrong side for a PUT — exactly the
        # shape of the 29 mismatched rows in LAB_QA_REPORT.md F2.
        "ticker": "STR1", "options_direction": "STRANGLE", "options_strategy": "LONG_PUT",
        "strike": "100", "structural_target": "110", "premium_mid": "2.0",
        "expiry": "2099-01-19", "lab_verdict": "GO",
    },
    {
        # Genuine single-leg PUT (mirrors ticker T in the audited export) —
        # options_direction is a real side, structural_target correctly below strike.
        "ticker": "T", "options_direction": "PUT", "options_strategy": "LONG_PUT",
        "strike": "23", "structural_target": "19.7", "premium_mid": "0.51",
        "expiry": "2099-01-19", "lab_verdict": "GO",
    },
    {
        # No direction signal anywhere — options_direction and options_strategy
        # both blank. Must behave exactly as before this fix (fall through,
        # resolve to "" since nothing in the candidate list has a side).
        "ticker": "ABS1", "options_direction": "", "options_strategy": "",
        "strike": "50", "structural_target": "55", "premium_mid": "1.0",
        "expiry": "2099-01-19", "lab_verdict": "GO",
    },
]


def test_strangle_row_does_not_receive_call_or_put_direction():
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120000", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120000", force_reload=True)
        by_ticker = {s["ticker"]: s for s in payload["signals"]}
        strangle = by_ticker["STR1"]
        assert strangle.get("direction") not in ("CALL", "PUT"), (
            f"STR1 is options_direction=STRANGLE and must not resolve to a side, got {strangle.get('direction')!r}"
        )


def test_genuine_put_row_still_resolves_to_put():
    """The regression that matters most: a real single-leg PUT (ticker T in
    the audited export) must be completely unaffected by this fix."""
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120100", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120100", force_reload=True)
        by_ticker = {s["ticker"]: s for s in payload["signals"]}
        assert by_ticker["T"].get("direction") == "PUT"


def test_absent_direction_row_behaves_as_before():
    """A row with no direction-indicating field anywhere must still resolve
    to no direction (unchanged, pre-existing behaviour) — not be affected by
    the new STRANGLE short-circuit."""
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120200", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120200", force_reload=True)
        by_ticker = {s["ticker"]: s for s in payload["signals"]}
        assert by_ticker["ABS1"].get("direction") not in ("CALL", "PUT")


def test_strangle_row_gets_options_direction_and_coherence_columns():
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120300", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120300", force_reload=True)
        by_ticker = {s["ticker"]: s for s in payload["signals"]}
        strangle = by_ticker["STR1"]
        assert strangle.get("options_direction") == "STRANGLE"
        assert strangle.get("lab_coherence_status") == "STRANGLE_NONDIRECTIONAL"

        put_row = by_ticker["T"]
        assert put_row.get("options_direction") == "PUT"
        assert put_row.get("lab_coherence_status") != "STRANGLE_NONDIRECTIONAL"


def test_strangle_policy_include_labelled_keeps_row_in_default_queue():
    lab = _load_lab_module()
    lab.LAB_STRANGLE_POLICY = "INCLUDE_LABELLED"
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120400", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120400", force_reload=True)
        tickers = {s["ticker"] for s in payload["signals"]}
        assert "STR1" in tickers
        strangle = next(s for s in payload["signals"] if s["ticker"] == "STR1")
        assert strangle.get("lab_hidden_by_default") is not True


def test_strangle_policy_flag_only_hides_row_from_default_queue_but_keeps_it():
    lab = _load_lab_module()
    lab.LAB_STRANGLE_POLICY = "FLAG_ONLY"
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120500", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120500", force_reload=True)
        tickers = {s["ticker"] for s in payload["signals"]}
        assert "STR1" in tickers, "FLAG_ONLY must keep the row in the dataset (recoverable via Show blocked)"
        strangle = next(s for s in payload["signals"] if s["ticker"] == "STR1")
        assert strangle.get("lab_hidden_by_default") is True


def test_strangle_policy_exclude_removes_row_entirely():
    lab = _load_lab_module()
    lab.LAB_STRANGLE_POLICY = "EXCLUDE"
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120600", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120600", force_reload=True)
        tickers = {s["ticker"] for s in payload["signals"]}
        assert "STR1" not in tickers, "EXCLUDE must remove the row from the signal set entirely"
        assert {"T", "ABS1"} <= tickers, "EXCLUDE must not touch non-strangle rows"


def test_strangle_direction_survives_conflicting_eod_candidate_manifest():
    """Regression for a second, independent source of the same defect found
    while verifying this fix against the real production run: eod_candidate_map
    (sourced from morning_candidates_*.csv, an upstream file this Lab does not
    produce) can carry its own single-leg "direction" for a STRANGLE ticker.
    Confirmed directly against run 20260731_083130: AVGO's morning_candidates
    row has direction=CALL in the same row as options_direction=STRANGLE. The
    Lab's EOD-candidate merge (intelligence_lab.py, the bare_key loop building
    eod__-prefixed + selected bare fields) must not let that stale upstream
    value overwrite a row this fix already correctly left non-directional.
    """
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        run_id = "20990101_120800"
        run_dir = _make_run(Path(tmp), run_id, _FIXTURE_ROWS, lab)
        _write_csv(
            run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv",
            ["ticker", "direction", "primary_direction"],
            [
                # Mirrors the real AVGO row: upstream already picked a single
                # leg for a ticker the Lab itself knows is a STRANGLE.
                {"ticker": "STR1", "direction": "CALL", "primary_direction": "CALL"},
                {"ticker": "T", "direction": "PUT", "primary_direction": "PUT"},
                {"ticker": "ABS1", "direction": "", "primary_direction": ""},
            ],
        )
        payload = lab._load_run(run_id, force_reload=True)
        by_ticker = {s["ticker"]: s for s in payload["signals"]}

        strangle = by_ticker["STR1"]
        assert strangle.get("direction") not in ("CALL", "PUT"), (
            f"eod_candidate_map's direction=CALL must not overwrite a row already "
            f"marked STRANGLE_NONDIRECTIONAL, got {strangle.get('direction')!r}"
        )
        assert strangle.get("lab_coherence_status") == "STRANGLE_NONDIRECTIONAL"

        # A genuine single-leg row must still pick up the eod_candidate_map
        # value normally -- the guard must be scoped to the strangle case only.
        assert by_ticker["T"].get("direction") == "PUT"


def test_property_directional_rows_have_target_on_profitable_side():
    """For every row where Direction resolved to CALL or PUT, Structural_Target
    must sit on the profitable side of Strike. This is the property the whole
    fix exists to restore — it must hold across the fixture regardless of
    policy."""
    lab = _load_lab_module()
    lab.LAB_STRANGLE_POLICY = "INCLUDE_LABELLED"
    with tempfile.TemporaryDirectory() as tmp:
        _make_run(Path(tmp), "20990101_120700", _FIXTURE_ROWS, lab)
        payload = lab._load_run("20990101_120700", force_reload=True)
        checked = 0
        for sig in payload["signals"]:
            direction = sig.get("direction")
            if direction not in ("CALL", "PUT"):
                continue
            strike = float(sig.get("strike") or sig.get("contract_strike") or 0)
            target = float(sig.get("structural_target") or sig.get("opt__structural_target") or 0)
            if not strike or not target:
                continue
            checked += 1
            if direction == "CALL":
                assert target > strike, f"{sig['ticker']}: CALL target {target} must be above strike {strike}"
            else:
                assert target < strike, f"{sig['ticker']}: PUT target {target} must be below strike {strike}"
        assert checked >= 1, "fixture must exercise at least one directional row"
