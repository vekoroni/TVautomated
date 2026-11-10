"""Keep publication ownership and the existing PostClose timing guard explicit."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_publication_policy_stays_full():
    policy = json.loads((ROOT / "config/macro_delivery_v1.json").read_bytes())
    assert policy["publication_mode"] == "FULL"


def test_postclose_timing_formula_is_preserved_verbatim():
    runner = (ROOT / "Run-MacroInputs.ps1").read_text(encoding="utf-8-sig")
    assert "$waitsPastGuard = (-not $forced) -and ($startAt.TimeOfDay -ge $RegularGuard) -and ($etNow -lt $startAt)" in runner
    assert "if ($inRegularHours -and -not $AllowIntraday -and -not $offSession -and -not $waitsPastGuard) {" in runner
