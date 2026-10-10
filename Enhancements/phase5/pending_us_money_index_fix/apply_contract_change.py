"""Apply the US Money Index text-flag fix to contracts/us_money_index_contract.py (run AFTER the Evening finishes).

Run from the repo root:  venv\\Scripts\\python.exe Enhancements\\phase5\\pending_us_money_index_fix\\apply_contract_change.py
Idempotency: refuses to run twice (anchors must match exactly once).
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
p = ROOT / "contracts" / "us_money_index_contract.py"
b = p.read_bytes()
crlf = b"\r\n" in b
s = b.decode("utf-8").replace("\r\n", "\n")


def rep(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, (old[:70], s.count(old))
    s = s.replace(old, new)


rep('''def _validate_v2(state: Mapping[str, Any]) -> tuple[datetime, datetime, list[str]]:''',
    '''V2_STATE_FLAGS = ("regime_change_since_monday", "monetisation_change_since_monday", "risk_off_transition")
# ACK 8 Oct 2026: the LLM producer writes some flags as text. Text is read only through this explicit vocabulary on
# its leading clause; anything else is refused (never assumed neutral).
_FLAG_TRUE_PREFIXES = ("CONFIRMED",)
_FLAG_FALSE_PREFIXES = ("UNCONFIRMED", "NOT_CONFIRMED", "NONE")
_FLAG_EXACT = {"TRUE": True, "YES": True, "FALSE": False, "NO": False}


def _state_flag(value: Any, field: str) -> tuple[bool, str]:
    """(value, basis) for a current_state flag: a boolean, or producer text read through the explicit vocabulary."""
    if isinstance(value, bool):
        return value, "BOOLEAN"
    if isinstance(value, str) and value.strip():
        lead = value.split(";", 1)[0].strip().upper()
        if lead in _FLAG_EXACT:
            return _FLAG_EXACT[lead], "PARSED_FROM_PRODUCER_TEXT"
        if lead.startswith(_FLAG_FALSE_PREFIXES):          # checked first: UNCONFIRMED also contains CONFIRMED
            return False, "PARSED_FROM_PRODUCER_TEXT"
        if lead.startswith(_FLAG_TRUE_PREFIXES):
            return True, "PARSED_FROM_PRODUCER_TEXT"
    raise USMoneyIndexValidationError(
        f"current_state.{field} must be boolean or producer text starting CONFIRMED/UNCONFIRMED/NOT_CONFIRMED/NONE/"
        f"TRUE/FALSE/YES/NO; got {str(value)[:60]!r}")


def _validate_v2(state: Mapping[str, Any]) -> tuple[datetime, datetime, list[str]]:''')

rep('''    for field in ("regime_change_since_monday", "monetisation_change_since_monday", "risk_off_transition"):
        if not isinstance(current.get(field), bool):
            raise USMoneyIndexValidationError(f"current_state.{field} must be boolean")
''', '''    for field in V2_STATE_FLAGS:
        _state_flag(current.get(field), field)                 # refuses unknown values, naming the field
''')

rep('''    raw = deepcopy(dict(state))
    content_hash = _canonical_hash(raw)
    state_block = state.get("current_state") if is_v2 else state.get("final_pipeline_state") if isinstance(state.get("final_pipeline_state"), Mapping) else {}
    if not state_block and isinstance(state.get("state"), Mapping):
        state_block = state.get("state")''',
    '''    raw = deepcopy(dict(state))
    content_hash = _canonical_hash(raw)
    state_block = state.get("current_state") if is_v2 else state.get("final_pipeline_state") if isinstance(state.get("final_pipeline_state"), Mapping) else {}
    if not state_block and isinstance(state.get("state"), Mapping):
        state_block = state.get("state")
    state_block = dict(state_block)
    if is_v2:
        # ACK 8 Oct 2026: publish each flag as a boolean with how it was read; producer text is kept as detail.
        for field in V2_STATE_FLAGS:
            value, basis = _state_flag(state_block.get(field), field)
            if basis != "BOOLEAN":
                state_block[f"{field}_detail"] = state_block.get(field)
                quality_issues.append(f"current_state.{field} read from producer text as {value}")
            state_block[field], state_block[f"{field}_basis"] = value, basis''')

if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode("utf-8"))
print("applied", p)
