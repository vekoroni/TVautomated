from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avshunter_trade_journal import get_open_positions, log_entry, log_exit
from contracts.lab_control import write_final_opportunity_book


def _route_signal(permission: str, route: str | None = None, ticker: str = "TST") -> dict:
    return {
        "ticker": ticker,
        "direction": "CALL",
        "strike": "100",
        "expiry": "2099-01-19",
        "dte": "30",
        "premium_mid": "1.25",
        "target_price": "108",
        "invalidation_price": "95",
        "mv__morning_execution_permission": permission,
        "mv__execution_permission": permission,
        "mv__morning_execution_route": route or permission,
        "mv__live_validation_state": "CONFIRMED" if permission != "BLOCKED" else "REJECTED",
    }


def _wire_entry_route(lab, tmp_path: Path, signal: dict) -> None:
    lab._JOURNAL_DB = tmp_path / "trade_journal.db"
    lab.RUNS_DIR = tmp_path / "runs"
    lab.RUNS_DIR.mkdir(exist_ok=True)
    lab._list_runs = lambda: ["run_001"]
    lab._load_run = lambda run_id: {
        "signals": [signal],
        "final_run_manifest": {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    }

    import vanguard.trade_contract as trade_contract

    trade_contract.find_open_contract = lambda ticker: None
    trade_contract.create_contract = lambda **kwargs: {"ok": True, **kwargs}


def _entry_payload(ticker: str = "TST") -> dict:
    return {
        "ticker": ticker,
        "run_id": "run_001",
        "entry_premium": 1.25,
        "contracts": 1,
        "invalidation_price": 95,
        "underlying_entry_price": 100,
        "declared_R": 125,
    }


def _write_csv(path: Path, columns: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [str(row.get(col, "")) for col in columns]
    path.write_text(",".join(columns) + "\n" + ",".join(values) + "\n", encoding="utf-8")


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_for_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lab_trade_entry_captures_clean_handoff_fields_and_carries_to_close():
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "trade_journal.db"
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        lab._JOURNAL_DB = db_path

        trade_id = log_entry(
            db_path=db_path,
            runs_dir=runs_dir,
            ticker="TST",
            run_id="run_001",
            entry_premium=1.25,
            contracts=2,
            options_direction="CALL",
            strike=100,
            expiry="2099-01-19",
            dte_at_entry=30,
            rr_predicted=2.5,
            ev_predicted=0.12,
            structural_target=108,
            sb_verdict="GO",
            underlying_price_at_entry=99.5,
        )

        sig = {
            "ticker": "TST",
            "trade_idea_id": "run_001:TST:CALL:100:2099-01-19",
            "display_final_verdict": "GO",
            "lab_verdict": "GO",
            "lab_tradeable": True,
            "display_execution_category": "GO_LIMIT",
            "display_campaign": "READY_LIMIT",
            "display_execution_mode": "LIMIT_ENTRY",
            "display_eod_candidate_status": "EOD_EXECUTE_CANDIDATE",
            "display_morning_execution_permission": "GO_LIMIT",
            "display_morning_execution_route": "GO_LIMIT",
            "display_options_research_route": "OPTIONS_GO_REVIEW",
            "options_research_permission": "NONE_OPTIONS_RESEARCH_ONLY",
            "options_research_score": "84.5",
            "hard_vetoes": "",
            "eod_candidate_reason": "QA handoff",
            "mv__live_validation_state": "CONFIRMED",
            "mv__validation_score": "91",
            "horizon_bucket": "6_10D",
            "hold_label": "14 days",
            "hold_urgency": "NORMAL",
            "horizon_action": "GO_SELECTIVE",
            "horizon_pressure": "NEUTRAL",
            "horizon_source": "QA",
            "trigger_primary": "TRIGGER_CONFIRMED",
            "trigger_quality": "CONFIRMED",
            "trigger_score": "88",
            "trigger_codes": "QA_TRIGGER",
            "direction": "CALL",
            "sb_instrument_now": "LONG_CALL",
            "strike": "100",
            "expiry": "2099-01-19",
            "dte": "30",
            "premium_mid": "1.25",
            "spread_pct": "0.04",
            "rr": "2.5",
            "ev": "0.12",
            "invalidation_price": "95",
            "target_price": "108",
            "priority_rank": "3",
            "priority_score": "94",
            "conflict_state": "NONE",
            "execution_lock_reason": "",
        }

        lab._update_lab_journal_row(
            trade_id,
            sig,
            {"declared_R": 250, "user_confirmed_live_validation": True},
            250.0,
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        open_row = dict(conn.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,)).fetchone())
        conn.close()

        assert open_row["lab_action_category"] == "GO_LIMIT"
        assert open_row["eod_candidate_status"] == "EOD_EXECUTE_CANDIDATE"
        assert open_row["morning_execution_permission"] == "GO_LIMIT"
        assert open_row["morning_execution_route"] == "GO_LIMIT"
        assert open_row["options_research_permission"] == "NONE_OPTIONS_RESEARCH_ONLY"
        assert open_row["options_research_route"] == "OPTIONS_GO_REVIEW"
        assert open_row["journal_open_status"] == "OPEN_MANUAL"
        assert "LONG_CALL" in open_row["contract_snapshot_json"]

        snapshot = get_open_positions(db_path)[0]
        log_exit(db_path=db_path, trade_id=trade_id, exit_premium=1.50, exit_reason="QA_CLOSE")
        lab._carry_lab_closed_metadata(trade_id, snapshot)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        closed_row = dict(conn.execute("SELECT * FROM closed_trades WHERE trade_id=?", (trade_id,)).fetchone())
        conn.close()

        assert closed_row["lab_action_category"] == "GO_LIMIT"
        assert closed_row["morning_execution_permission"] == "GO_LIMIT"
        assert closed_row["options_research_route"] == "OPTIONS_GO_REVIEW"
        assert closed_row["outcome_class"] == "PROCESS_WIN"


def test_api_enter_trade_allows_go_limit_and_probe_only_when_lab_tradeable():
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        client = lab.app.test_client()

        for idx, permission in enumerate(("GO_LIMIT", "PROBE"), 1):
            ticker = f"TS{idx}"
            _wire_entry_route(lab, tmp_path, _route_signal(permission, ticker=ticker))
            response = client.post("/api/enter_trade", json=_entry_payload(ticker))
            assert response.status_code == 200, response.get_json()
            payload = response.get_json()
            assert payload["ok"] is True
            assert payload["contract_summary"]["ticker"] == ticker

        _wire_entry_route(lab, tmp_path, _route_signal("WAIT", ticker="TSW"))
        response = client.post("/api/enter_trade", json=_entry_payload("TSW"))
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["lab_verdict"] == "WAIT"
        assert payload["lab_tradeable"] is False

        _wire_entry_route(lab, tmp_path, _route_signal("CONTRACT_REPAIR", ticker="TSR"))
        response = client.post("/api/enter_trade", json=_entry_payload("TSR"))
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["lab_verdict"] == "CONTRACT_REPAIR"
        assert payload["lab_tradeable"] is False


def test_lab_reload_detects_fresh_morning_validator_output_without_manual_cache_clear():
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_id = "20990101_093000"
        lab.RUNS_DIR = tmp_path / "runs"
        lab._JOURNAL_DB = tmp_path / "trade_journal.db"
        lab._run_cache.clear()
        # This regression exercises file-change detection, not run-health
        # adjudication. Keep the production fail-closed manifest guard intact
        # and supply a healthy manifest for the deliberately minimal fixture.
        lab.write_final_run_manifest = lambda *args, **kwargs: {
            "pipeline_mode": "MORNING_VALIDATION",
            "fatal_flags": [],
            "stale_flags": [],
        }

        run_dir = lab.RUNS_DIR / run_id
        _write_csv(
            run_dir / "superbrain" / f"eil_enriched_{run_id}.csv",
            ["ticker", "direction", "strike", "expiry", "premium_mid", "target_price", "invalidation_price", "lab_verdict"],
            {
                "ticker": "AAA",
                "direction": "CALL",
                "strike": "100",
                "expiry": "2099-01-19",
                "premium_mid": "1.0",
                "target_price": "110",
                "invalidation_price": "95",
                "lab_verdict": "GO",
            },
        )
        mv_path = run_dir / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
        mv_columns = [
            "ticker",
            "morning_execution_permission",
            "morning_execution_route",
            "execution_permission",
            "live_validation_state",
        ]
        _write_csv(
            mv_path,
            mv_columns,
            {
                "ticker": "AAA",
                "morning_execution_permission": "WAIT",
                "morning_execution_route": "WAIT",
                "execution_permission": "WAIT",
                "live_validation_state": "WAIT_RETEST",
            },
        )
        governed_signal = {
            "ticker": "AAA", "direction": "CALL", "strike": "100",
            "expiry": "2099-01-19", "premium_mid": "1.0",
            "target_price": "110", "invalidation_price": "95",
            "lab_verdict": "GO", "lab_tradeable": False,
            "morning_execution_permission": "WAIT",
            "morning_execution_route": "WAIT",
            "live_validation_state": "WAIT_RETEST",
        }
        governed_manifest = {
            "pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []
        }
        write_final_opportunity_book(
            run_id, [governed_signal], governed_manifest, lab.RUNS_DIR,
            sync_interpreter=False,
        )

        first = lab._load_run(run_id, force_reload=True)
        first_sig = first["signals"][0]
        assert first_sig["morning_execution_permission"] == "WAIT"
        assert first_sig["lab_verdict"] == "MANUAL_REVIEW"

        time.sleep(0.02)
        _write_csv(
            mv_path,
            mv_columns,
            {
                "ticker": "AAA",
                "morning_execution_permission": "GO_LIMIT",
                "morning_execution_route": "GO_LIMIT",
                "execution_permission": "GO_LIMIT",
                "live_validation_state": "CONFIRMED",
            },
        )
        governed_signal.update(
            morning_execution_permission="GO_LIMIT",
            morning_execution_route="GO_LIMIT",
            live_validation_state="CONFIRMED",
        )
        write_final_opportunity_book(
            run_id, [governed_signal], governed_manifest, lab.RUNS_DIR,
            sync_interpreter=False,
        )

        second = lab._load_run(run_id)
        second_sig = second["signals"][0]
        assert second is not first
        assert second_sig["morning_execution_permission"] == "GO_LIMIT"
        # This fixture has no governed direction lineage, so GO_LIMIT cannot
        # independently upgrade the Lab row above manual review.
        assert second_sig["lab_verdict"] == "MANUAL_REVIEW"
