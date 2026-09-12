from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import (
    FINAL_BOOK_FIELDS,
    build_final_run_manifest,
    learning_feedback_from_closed_trades,
    resolve_lab_tradeability,
    write_final_opportunity_book,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_run(root: Path, run_id: str, include_eil: bool = True) -> Path:
    run_dir = root / run_id
    _write_csv(run_dir / "discovery" / f"discovery_candidates_{run_id}.csv", [{"ticker": "AAA"}])
    _write_csv(
        run_dir / "options" / f"vanguard_signals_enriched_{run_id}.csv",
        [{"ticker": "AAA", "physics_state_id": "PHYS|TEST", "state_transition_label": "CONTINUATION_UP"}],
    )
    _write_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv", [{"ticker": "AAA", "options_verdict": "EXECUTE"}])
    _write_csv(run_dir / "execution" / f"execution_v3_5_{run_id}.csv", [{"ticker": "AAA", "execution_verdict": "BUY_NOW"}])
    _write_csv(
        run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv",
        [{"ticker": "AAA", "candidate_status": "MORNING_VALIDATION_REQUIRED"}],
    )
    if include_eil:
        _write_csv(
            run_dir / "superbrain" / f"eil_enriched_{run_id}.csv",
            [{
                "ticker": "AAA",
                "eil_v3_verdict": "EXECUTE",
                "macro_regime_label": "RISK_ON",
                "macro_freshness_status": "FRESH",
            }],
        )
    return run_dir


def test_manifest_and_resolver() -> None:
    with tempfile.TemporaryDirectory() as td:
        runs = Path(td)
        run_id = "20990101_000000"
        run_dir = _make_run(runs, run_id, include_eil=True)
        manifest = build_final_run_manifest(run_id, runs, pipeline_mode="EOD")
        assert manifest["phase_status"]["eil"] == "PASS"
        assert manifest["phase_status"]["morning_validation"] == "PENDING"
        assert manifest["next_action"] == "NEEDS_MORNING_VALIDATION"
        assert manifest["v5_colab_decommissioned"] is True
        assert "v5" not in manifest["missing_columns"]
        assert "v5" not in manifest["required_columns_present"]
        assert manifest["worker3_market_environment"]["status"] == "MISSING"
        assert manifest["worker3_macro_ticker_context"]["status"] == "MISSING"
        assert manifest["fatal_flags"] == []
        assert manifest["next_action"] == "NEEDS_MORNING_VALIDATION"

        packet_path = run_dir / "interpreter" / "interpreter_macro_context.json"
        _write_json(packet_path, {
            "schema_version": "interpreter_macro_context_v1",
            "packet_id": "MACRO:fixture",
            "session_date": "2099-01-01",
            "authority_statement": "MACRO_ADVISORY_ONLY",
        })
        (run_dir / "run_meta.json").write_text(json.dumps({
            "dynamic_plan": {"last_completed_session": "2099-01-01"}
        }), encoding="utf-8")
        with_worker3 = build_final_run_manifest(run_id, runs, pipeline_mode="EOD")
        assert with_worker3["worker3_market_environment"]["status"] == "AVAILABLE"
        assert with_worker3["worker3_market_environment"]["packet_sha256"]
        assert with_worker3["worker3_market_environment"]["trading_authority"] is False

        packet_sha256 = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        lab_book_path = (
            run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
        )
        _write_json(lab_book_path, {
            "lab_schema_version": "lab_signal_book_v2",
            "run_id": run_id,
            "candidate_count": 1,
            "rows": [{"ticker": "AAA"}],
        })
        lab_book_sha256 = hashlib.sha256(lab_book_path.read_bytes()).hexdigest()
        context_path = run_dir / "interpreter" / "macro_ticker_context_manifest.json"
        _write_json(
            context_path,
            {
                "schema_version": "worker3_macro_ticker_context_manifest_v1",
                "context_contract": "macro_ticker_context_v1",
                "run_id": run_id,
                "session_date": "2099-01-01",
                "authority": "ADVISORY_ONLY",
                "trading_authority": False,
                "source_packet_sha256": packet_sha256,
                "lab_book_sha256": lab_book_sha256,
                "diagnostics": {
                    "macro_ticker_context_requested": 1,
                    "macro_ticker_context_available": 1,
                    "macro_ticker_context_partial": 0,
                    "macro_ticker_context_stale": 0,
                    "macro_ticker_context_conflicting": 0,
                    "macro_ticker_context_unmapped": 0,
                    "macro_ticker_context_invalid": 0,
                    "macro_ticker_context_bytes_total": 1024,
                    "macro_ticker_context_omitted_items_total": 0,
                    "macro_ticker_context_exact_ticker": 1,
                    "macro_ticker_context_sector_only": 0,
                    "macro_ticker_context_applicability_unmapped": 0,
                    "macro_ticker_context_reconciled": True,
                },
            },
        )
        with_context = build_final_run_manifest(run_id, runs, pipeline_mode="EOD")
        self_context = with_context["worker3_macro_ticker_context"]
        assert self_context["status"] == "AVAILABLE"
        assert self_context["contract_version"] == "macro_ticker_context_v1"
        assert self_context["diagnostics"]["macro_ticker_context_requested"] == 1
        assert self_context["trading_authority"] is False

        context_payload = json.loads(context_path.read_text(encoding="utf-8"))
        context_payload["lab_book_sha256"] = "0" * 64
        _write_json(context_path, context_payload)
        wrong_lab_hash = build_final_run_manifest(run_id, runs, pipeline_mode="EOD")
        assert wrong_lab_hash["worker3_macro_ticker_context"]["status"] == "INVALID"
        assert "Lab hash differs" in wrong_lab_hash["worker3_macro_ticker_context"]["error"]

        context_payload["lab_book_sha256"] = lab_book_sha256
        context_payload["diagnostics"].update({
            "macro_ticker_context_available": -1,
            "macro_ticker_context_partial": 2,
            "macro_ticker_context_bytes_total": -1,
        })
        _write_json(context_path, context_payload)
        negative_counts = build_final_run_manifest(run_id, runs, pipeline_mode="EOD")
        assert negative_counts["worker3_macro_ticker_context"]["status"] == "INVALID"
        assert "cannot be negative" in negative_counts["worker3_macro_ticker_context"]["error"]

        context_payload["diagnostics"].update({
            "macro_ticker_context_available": 1,
            "macro_ticker_context_partial": 0,
            "macro_ticker_context_bytes_total": 1024,
        })
        _write_json(context_path, context_payload)

        live_manifest = build_final_run_manifest(run_id, runs, pipeline_mode="LIVE")
        assert "LIVE_VALIDATION_MISSING" in live_manifest["fatal_flags"]

        missing_run = "20990101_000001"
        _make_run(runs, missing_run, include_eil=False)
        missing_manifest = build_final_run_manifest(missing_run, runs)
        assert "EIL_ADVISORY_OUTPUT_MISSING_OR_INVALID" in missing_manifest["stale_flags"]
        assert "EIL_OUTPUT_MISSING_OR_INVALID" not in missing_manifest["fatal_flags"]

        blocked = resolve_lab_tradeability(
            {"ticker": "AAA", "eil_v3_verdict": "BLOCKED", "thesis_decision": "GO"},
            manifest,
        )
        assert blocked["lab_verdict"] == "MORNING_VALIDATION_REQUIRED"
        assert blocked["conflict_state"] != "HARD_CONFLICT"
        assert "EIL_ADVISORY_BLOCKED" in blocked["advisory_flags"]

        sb_conflict = resolve_lab_tradeability(
            {"ticker": "AAA", "sb_final_verdict": "EXECUTE", "options_verdict": "STAND_DOWN"},
            manifest,
        )
        assert sb_conflict["lab_verdict"] == "BLOCKED"

        go = resolve_lab_tradeability(
            {
                "ticker": "AAA",
                "options_verdict": "EXECUTE",
                "campaign_verdict": "READY_EXECUTE",
                "execution_verdict": "BUY_NOW",
                "thesis_decision": "GO",
                "strike": 100,
                "expiry": "2099-02-01",
                "premium_mid": 1.25,
                "rr_options": 1.5,
                "ev2_decision_hint": "MODERATE",
                "spread_pct": 0.05,
                "mv_verdict": "VALID",
            },
            {**manifest, "stale_flags": [], "fatal_flags": [], "pipeline_mode": "LIVE"},
        )
        assert go["lab_verdict"] == "GO"
        assert go["lab_tradeable"] is True

        weak_ev = resolve_lab_tradeability(
            {
                "ticker": "AAA",
                "options_verdict": "EXECUTE",
                "campaign_verdict": "READY_EXECUTE",
                "execution_verdict": "BUY_NOW",
                "thesis_decision": "GO",
                "strike": 100,
                "expiry": "2099-02-01",
                "premium_mid": 1.25,
                "rr_options": 1.5,
                "ev2_decision_hint": "WEAK",
                "spread_pct": 0.05,
                "mv_verdict": "VALID",
            },
            {**manifest, "stale_flags": [], "fatal_flags": [], "pipeline_mode": "LIVE"},
        )
        assert weak_ev["lab_verdict"] == "GO"
        assert weak_ev["lab_tradeable"] is True
        assert "EV_WEAK" in weak_ev["advisory_flags"]

        legacy_negative_rr = resolve_lab_tradeability(
            {
                "ticker": "AAA",
                "options_verdict": "EXECUTE",
                "campaign_verdict": "READY_EXECUTE",
                "execution_verdict": "BUY_NOW",
                "thesis_decision": "GO",
                "rr_options": -0.25,
                "strike": 100,
                "expiry": "2099-02-01",
                "premium_mid": 1.25,
                "spread_pct": 0.05,
                "mv_verdict": "VALID",
            },
            {**manifest, "stale_flags": [], "fatal_flags": [], "pipeline_mode": "LIVE"},
        )
        assert legacy_negative_rr["lab_verdict"] == "GO"
        assert legacy_negative_rr["lab_tradeable"] is True
        assert "NEGATIVE_RR" not in legacy_negative_rr["veto_flags"]

        missing_contract = resolve_lab_tradeability(
            {"ticker": "AAA", "options_verdict": "EXECUTE", "campaign_verdict": "READY_EXECUTE"},
            manifest,
        )
        assert missing_contract["lab_verdict"] == "MORNING_VALIDATION_REQUIRED"
        assert missing_contract["lab_tradeable"] is False


def test_opportunity_book_and_learning_feedback() -> None:
    with tempfile.TemporaryDirectory() as td:
        runs = Path(td)
        run_id = "20990101_000002"
        _make_run(runs, run_id, include_eil=True)
        manifest = build_final_run_manifest(run_id, runs)
        signal = {
            "ticker": "AAA",
            "lab_verdict": "GO",
            "lab_tradeable": True,
            "conflict_state": "CLEAN",
            "direction": "CALL",
            "contract_strike": 100,
            "contract_expiry": "2099-02-01",
            "premium_mid": 1.25,
            "priority_score": 91,
            "physics_state_id": "PHYS|ENERGY_HIGH",
            "hidden_state_label": "TRENDING_BULLISH_INERTIA",
            "state_transition_label": "CONTINUATION_UP",
            "macro_regime_label": "RISK_ON",
            "legacy_column": "must_survive_in_payload",
        }
        book = write_final_opportunity_book(
            run_id, [signal], manifest, runs, sync_interpreter=False
        )
        assert Path(book["csv_path"]).exists()
        assert Path(book["json_path"]).exists()
        assert all(field in book["rows"][0] for field in FINAL_BOOK_FIELDS)
        payload = json.loads(book["rows"][0]["source_payload_json"])
        assert payload["legacy_column"] == "must_survive_in_payload"

        feedback = learning_feedback_from_closed_trades(
            [
                {"ticker": "AAA", "pnl_usd": 100, "rr_predicted": 2, "rr_realised": 1, "physics_state_id": "P1"},
                {"ticker": "BBB", "pnl_usd": -50, "rr_predicted": 1, "rr_realised": -0.5, "physics_state_id": "P2"},
            ]
        )
        assert feedback["n_trades"] == 2
        assert feedback["win_rate"] == 0.5
        assert feedback["win_rate_by_physics_state"]


def test_ui_contract_strings_and_journal_roundtrip() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    for token in [
        "Open Positions",
        "Exit Ticket",
        "Outcomes",
        "Learning Loop",
        "Run Health",
        "lab_verdict",
        "/monitor_positions",
        "/log_exit",
        "/learning_feedback",
        "/orchestrator/status",
    ]:
        assert token in html

    from avshunter_trade_journal import get_open_positions, log_entry, log_exit

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        db = base / "trade_journal.db"
        runs = base / "runs"
        trade_id = log_entry(db, runs, "ZZZ", "run_test", entry_premium=0.5, contracts=1)
        open_rows = get_open_positions(db)
        assert open_rows and "trade_id" in open_rows[0]
        outcome = log_exit(db, trade_id=trade_id, exit_premium=0.6, exit_reason="TEST")
        assert outcome["trade_id"] == trade_id


if __name__ == "__main__":
    test_manifest_and_resolver()
    test_opportunity_book_and_learning_feedback()
    test_ui_contract_strings_and_journal_roundtrip()
    print("big_bang_phase_6_7 tests passed: 3 groups")
