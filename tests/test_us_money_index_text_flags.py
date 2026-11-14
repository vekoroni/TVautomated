"""US Money Index flags written as producer text (ACK 8 Oct 2026: fix the rejected packet; apply after the Evening).

Business rules:
- The three current_state flags (regime_change_since_monday, monetisation_change_since_monday, risk_off_transition)
  stay true/false facts. Since 7 Oct the LLM producer writes some as text, e.g. risk_off_transition =
  "CONFIRMED_WITH_AI_SOX_...; NO_BROAD_SYSTEMIC_UPGRADE"; the contract rejected the whole packet (G2-03).
- Text is read only through an explicit vocabulary on its leading clause: CONFIRMED.../TRUE/YES -> true;
  UNCONFIRMED.../NOT_CONFIRMED.../NONE/FALSE/NO -> false. Anything else is still refused, naming the field
  (missing or unknown is never neutral).
- The published state keeps the original text (<field>_detail) and says how the value was read (<field>_basis);
  a quality issue records it. A real boolean is unchanged (basis BOOLEAN).
- A validator script reports the same verdict at production time, so drift is caught before the Evening.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from contracts.us_money_index_contract import USMoneyIndexValidationError, normalise_us_money_index_sidecar

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "us_money_index_v2_text_flags_20261008.json"


def _packet(**flags):
    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state["current_state"].update(flags)
    return state


def test_confirmed_text_is_read_as_true_and_the_text_is_kept():
    out = normalise_us_money_index_sidecar(_packet())
    s = out["state"]
    assert s["risk_off_transition"] is True
    assert s["risk_off_transition_detail"].startswith("CONFIRMED_WITH_AI_SOX")
    assert s["risk_off_transition_basis"] == "PARSED_FROM_PRODUCER_TEXT"
    assert any("risk_off_transition" in issue for issue in out["quality_issues"])


def test_unconfirmed_text_is_false():
    out = normalise_us_money_index_sidecar(_packet(risk_off_transition="UNCONFIRMED_VIX_BELOW_18; CONCENTRATED"))
    assert out["state"]["risk_off_transition"] is False


def test_a_real_boolean_is_unchanged():
    out = normalise_us_money_index_sidecar(_packet(risk_off_transition=False))
    assert out["state"]["risk_off_transition"] is False
    assert out["state"]["risk_off_transition_basis"] == "BOOLEAN"


@pytest.mark.parametrize("value", ["MAYBE_LATER", "", None, 1])
def test_unknown_text_is_still_refused_naming_the_field(value):
    with pytest.raises(USMoneyIndexValidationError, match="risk_off_transition"):
        normalise_us_money_index_sidecar(_packet(risk_off_transition=value))


def test_the_validator_reports_the_verdict(tmp_path):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_packet()), encoding="utf-8")
    bad.write_text(json.dumps(_packet(risk_off_transition="MAYBE_LATER")), encoding="utf-8")
    script = ROOT / "scripts" / "validate_us_money_index.py"
    ok = subprocess.run([sys.executable, str(script), str(good)], capture_output=True, text=True)
    no = subprocess.run([sys.executable, str(script), str(bad)], capture_output=True, text=True)
    assert ok.returncode == 0 and "risk_off_transition=True (PARSED_FROM_PRODUCER_TEXT)" in ok.stdout
    assert no.returncode == 1 and "risk_off_transition" in (no.stdout + no.stderr)


REV43='REV43_MATERIAL_PRICE_AND_SPX_IMPLIED_VOLATILITY_TRANSMISSION_AFTER_VIX_CLEARS_18_AND20_WHILE_OIL_EXTENDS_ABOVE107'


def test_rev43_exact_alias_preserves_detail_authority_and_source():
    detail=REV43+'; POSITIVE_LAGGED_WEEKLY_FLOWS_DO_NOT_CANCEL_INTRADAY_RISK_OFF; NO_PROOF_SYSTEMIC_FUNDING_SEIZURE'
    raw=_packet(risk_off_transition=detail)
    original=copy.deepcopy(raw)
    out=normalise_us_money_index_sidecar(raw)
    assert out['state']['risk_off_transition'] is True
    assert out['state']['risk_off_transition_basis']=='EXPLICIT_REV43_PRODUCER_ALIAS'
    assert out['state']['risk_off_transition_detail']==detail
    assert out['source_payload']==original and raw==original
    assert out['authority']=='ADVISORY_ONLY'
    assert out['execution_permission']=='NONE_INTELLIGENCE_ONLY'


@pytest.mark.parametrize('flags',[
    {'risk_off_transition':REV43.replace('REV43','REV44')},
    {'risk_off_transition':REV43+'_UNCONFIRMED'},
    {'regime_change_since_monday':REV43},
    {'risk_off_transition':'MATERIAL_RISK_OFF'},
])
def test_revision_alias_does_not_accept_unknown_or_other_fields(flags):
    with pytest.raises(USMoneyIndexValidationError):
        normalise_us_money_index_sidecar(_packet(**flags))
