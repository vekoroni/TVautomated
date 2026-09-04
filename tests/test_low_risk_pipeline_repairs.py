from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import execution_intelligence as eil
from execution_schema import ExecutionContext, StrategyResult


ROOT = Path(__file__).resolve().parents[1]


def _load_functions(path: Path, names: set[str], globals_: dict[str, Any]) -> dict[str, Any]:
    """Load small pure helpers without importing pandas-dependent pipeline modules."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    namespace = dict(globals_)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _eod_helpers() -> dict[str, Any]:
    return _load_functions(
        ROOT / "eod_candidate_engine.py",
        {"_str", "_optional_flt", "_has_direction_conflict_lineage"},
        {"Optional": Optional},
    )


def test_missing_theta_ratio_stays_missing() -> None:
    optional_flt = _eod_helpers()["_optional_flt"]
    assert optional_flt({"move_theta_ratio": ""}, "move_theta_ratio") is None
    assert optional_flt({"move_theta_ratio": None}, "move_theta_ratio") is None
    assert optional_flt({"move_theta_ratio": "nan"}, "move_theta_ratio") is None
    assert optional_flt({"move_theta_ratio": "0.0"}, "move_theta_ratio") == 0.0


def test_resolved_direction_conflict_remains_visible_but_is_not_unresolved() -> None:
    has_conflict = _eod_helpers()["_has_direction_conflict_lineage"]
    row = {
        "direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS",
        "direction_conflict_status": "MITIGATED_REQUIRES_CONFIRMATION",
    }
    assert has_conflict(row) is True
    assert has_conflict({"direction_conflict_status": "NO_CONFLICT"}) is False


def _strategy(name: str, *, score: float = 100.0, passed: bool = True) -> StrategyResult:
    return StrategyResult(
        strategy_name=name,
        score=score,
        passed=passed,
        verdict="PASS" if passed else "NO_EXECUTABLE_MARKET",
        detail="test",
        size_multiplier=1.0,
        block=False,
    )


def test_eil_preserves_pre_hard_gate_raw_verdict(monkeypatch) -> None:
    liquidity = _strategy("liquidity", passed=False)
    monkeypatch.setattr(eil.liquidity_gate, "run", lambda ctx: liquidity)
    monkeypatch.setattr(eil.iv_distortion, "run", lambda ctx: _strategy("iv"))
    monkeypatch.setattr(eil.gex_flipper, "run", lambda ctx: _strategy("gex"))
    monkeypatch.setattr(eil.obi_predictor, "run", lambda ctx: _strategy("obi"))
    monkeypatch.setattr(eil.poc_timing, "run", lambda ctx: _strategy("poc"))

    now = datetime.now(timezone.utc)
    result = eil.evaluate(
        ExecutionContext(
            ticker="QA",
            signal_time=now,
            superbrain_verdict="GO",
            wbs_grade="A",
            wbs_score=90.0,
            signal_direction="CALL",
            current_price=100.0,
            check_time=now,
        )
    )

    assert result.eil_verdict == "BLOCKED"
    assert result.eil_raw_verdict == "EXECUTE_NOW"
    runner_source = (ROOT / "execution_intelligence_runner.py").read_text(encoding="utf-8-sig")
    assert "raw_eil_token = eil_result.eil_raw_verdict" in runner_source
    assert "_EIL_TOKEN_NORMALISE.get(final_eil_token" in runner_source


class _FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._rows


def test_contract_rejection_log_includes_selection_and_repair_failures() -> None:
    helpers = _load_functions(
        ROOT / "scripts" / "avshunter_options_intelligence.py",
        {"_build_contract_rejection_log_rows"},
        {
            "Any": Any,
            "Dict": Dict,
            "List": List,
            "DTE_CONFIG": {
                "1_5d": {"dte_min": 7, "dte_max": 30},
                "6_10d": {"dte_min": 14, "dte_max": 45},
            },
        },
    )
    build_rows = helpers["_build_contract_rejection_log_rows"]
    frame = _FakeFrame(
        [
            {
                "ticker": "AAA",
                "contract_rejection_reason": "NO_CONTRACT_PASSED_QUALITY_GATES",
                "contract_rejection_stage": "CONTRACT_SELECTION",
                "contract_rejection_horizon": "6_10d",
                "contract_rejection_dte_min": 14,
                "contract_rejection_dte_max": 45,
                "contract_rejection_chain_rows": 25,
                "final_route": "OPTIONS_PROBE_ONLY",
            },
            {
                "ticker": "BBB",
                "contract_repair_required": True,
                "contract_repair_reason": "SPREAD_TOO_WIDE",
                "recommended_contract": "BBB260918C00100000",
                "horizon_bucket": "1_5d",
                "final_route": "OPTIONS_GO_REVIEW",
            },
            {
                "ticker": "CCC",
                "contract_rejection_reason": float("nan"),
                "final_route": "OPTIONS_GO_REVIEW",
            },
        ]
    )

    rows = build_rows(frame)
    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert rows[0]["rejection_stage"] == "CONTRACT_SELECTION"
    assert rows[1]["rejection_reason"] == "SPREAD_TOO_WIDE"


def test_integrity_manifest_reports_retired_pse_and_governs_latest_pointer() -> None:
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    assert '"pse_active":                   False' in source
    assert '"pse_capital_authority":        "NONE"' in source
    assert '"run_pointer.json"' in source
    assert '"NOT_AVAILABLE_FOR_RUN"' in source
