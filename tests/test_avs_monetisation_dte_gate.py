"""Invented-values inventory F1 (ACK 3 Oct 2026, step 1): the monetisation policy's DTE gate.

Business rule: a contract about to expire (fewer than HARD_DTE_MIN sessions) cannot be
monetised and is blocked on economics; a contract with runway passes, and the event records
the DTE actually read. Missing DTE is never reported as an acceptable number.

Root cause: map_options_row_to_policy_input._int had no return path for a valid value (its
int(float(v)) sat unreachable inside _bool), so DTE, tier and contradictions were always None/0,
OPT_001 could never fire and every row logged "DTE acceptable". Both copies carried the defect;
production loads the root copy (execution_intelligence_runner imports it by name).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


COPIES = {
    "root": ROOT / "avshunter_monetisation_policy.py",
    "scripts": ROOT / "scripts" / "avshunter_monetisation_policy.py",
}


@pytest.fixture(params=sorted(COPIES))
def policy(request):
    return _load(COPIES[request.param], f"mp_{request.param}")


def _evaluate(policy, **row):
    base = {"ticker": "TEST", "direction": "CALL", "contract_mid": "1.50", "contract_bid": "1.45",
            "contract_ask": "1.55", "spread_pct": "0.03"}  # fraction, as the EIL runner passes it
    base.update(row)
    x = policy.map_options_row_to_policy_input(base)
    return x, policy.MonetisationPolicy().evaluate(x)


def _codes(out):
    return {e.rule_id: e for e in out.rule_events}


def test_integer_fields_are_read(policy):
    x, _ = _evaluate(policy, contract_dte="3.0", tier="2", contradictions_count="4")
    assert x.dte == 3 and x.tier == 2 and x.contradictions == 4


def test_contract_about_to_expire_is_blocked(policy):
    _, out = _evaluate(policy, contract_dte="3")
    assert "OPT_001" in _codes(out)
    assert out.hard_block_reason and "DTE" in out.hard_block_reason


def test_contract_with_runway_passes_and_records_its_dte(policy):
    _, out = _evaluate(policy, contract_dte="55")
    ev = _codes(out)
    assert "OPT_001" not in ev
    assert ev["OPT_000"].value == 55.0


def test_missing_dte_is_not_a_number(policy):
    x, _ = _evaluate(policy, contract_dte="nan", dte="")
    assert x.dte is None


def test_missing_dte_is_stated_not_called_acceptable(policy):
    _, out = _evaluate(policy, contract_dte="", dte="")
    ev = _codes(out)
    assert "OPT_001" not in ev
    assert ev["OPT_000"].value is None and "acceptable" not in ev["OPT_000"].note.lower()
