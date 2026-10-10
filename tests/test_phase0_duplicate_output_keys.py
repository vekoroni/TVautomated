"""Single source of truth for output fields (Phase 1, P0-06).

Business rule: a decision-path output record never writes the same field twice. A second write silently
discards the first value (Phase 0 found the published crabel_score was not the score that set the tier, and the
EOD record overwrote quote_as_of). Phase 0 pinned the duplicates; Phase 1 removes them and this test now guards
against their return.
"""
import ast
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ["avshunter_discovery_ULTIMATE.py", "eod_candidate_engine.py", "morning_gate.py",
                 "contracts/lab_control.py", "scripts/avshunter_options_intelligence.py", "trigger_layer.py",
                 "vanguard/main.py", "execution_decision_engine.py"]


def _dupes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    found = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            ks = [k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            dup = sorted(k for k, c in collections.Counter(ks).items() if c > 1)
            if dup:
                found[n.lineno] = dup
    return found


def test_no_decision_path_record_writes_a_field_twice():
    offenders = {f: _dupes(ROOT / f) for f in DECISION_PATH if (ROOT / f).exists()}
    offenders = {f: d for f, d in offenders.items() if d}
    assert offenders == {}


def _keys_of_dict_at(path: Path, containing: str):
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            ks = {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if containing in ks:
                yield ks


def test_discovery_publishes_the_tier_deciding_crabel_score_explicitly():
    records = list(_keys_of_dict_at(ROOT / "avshunter_discovery_ULTIMATE.py", "composite_adjusted"))
    assert records and all({"discovery_crabel_score", "crabel_score"} <= ks for ks in records)
