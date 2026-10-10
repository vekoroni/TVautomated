"""Phase 4: Vanguard's UNIVERSE_CONFIG price / volume / spread limits are retired and must never act as a gate.

Business rule (ACK 4 Oct 2026: no price gate; price is a label): vanguard/config.py still declares
UNIVERSE_CONFIG (min_price 10, max_price 500, max spread 2%). No code reads it today; this guard keeps it that way
until ACK approves its deletion in the cleanup phase.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ["vanguard", "scripts", "contracts", "domain", "avshunter", "canonical_data"]


def test_nothing_reads_vanguard_universe_config():
    readers = []
    files = [p for d in SCAN for p in (ROOT / d).rglob("*.py") if "Archive" not in p.parts]
    files += list(ROOT.glob("*.py"))
    for p in files:
        if p.as_posix().endswith("vanguard/config.py"):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8-sig", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and n.id == "UNIVERSE_CONFIG":
                readers.append(str(p.relative_to(ROOT)))
            if isinstance(n, ast.alias) and n.name == "UNIVERSE_CONFIG":
                readers.append(str(p.relative_to(ROOT)))
    assert readers == []


def test_universe_config_is_marked_retired():
    src = (ROOT / "vanguard" / "config.py").read_text(encoding="utf-8-sig")
    assert "RETIRED" in src.split("UNIVERSE_CONFIG = {")[0].splitlines()[-1]
