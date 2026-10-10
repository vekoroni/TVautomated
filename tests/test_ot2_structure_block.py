"""Output-trust item 2 (D2-1 Step A; ACK approved 9 Oct 2026, "old legacy should be made inactive").

Business rules:
- The card's structure comes from ONE engine, the thesis engine: scope (timeframe, scope, since), phase and event,
  event status (candidate / observed / failed / historical) with the last observation and its date and level, failure
  evidence, and other-timeframe conflicts. Nothing is forced to agree with the trade; conflicts are shown with scope.
- The legacy structure producers (Wyckoff engine labels, Wyckoff validation heuristics, the forecast structure stage,
  structure_evidence) are not shown as evidence: on the card they sit in the legacy tier; the Lab table and modal show
  the thesis engine's structure instead of forecast_structure_stage; the Discovery tab names its legacy score as legacy.
- Display only: no side, gate, score or rank changes in this step (Step B handles decisions, station by station).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "intelligence-lab" / "static"
CARD = (STATIC / "trade-card.js").read_text(encoding="utf-8")
SMCI = {"ticker": "SMCI", "direction": "CALL", "thesis_phase": "E", "thesis_event": "SOS -> LPS continuation",
        "thesis_event_state": "ACTIVATED", "thesis_event_timeframe": "1d", "thesis_event_scope": "CAMPAIGN",
        "thesis_event_candidate_id": "SMCI|1d|CAMPAIGN|SOS -> LPS continuation|2026-08-24",
        "thesis__last_event": "RETEST_HELD_UP", "thesis__last_event_date": "2026-10-07",
        "thesis__last_event_level": 42.31, "thesis__readiness": "READY_FOR_HUMAN_REVIEW",
        "thesis__conflicting_count": 0, "wyckoff_mode": "DISTRIBUTION", "wyckoff_phase_granular": "ACCUMULATION_SPRING"}


def _node(js: str):
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_card_structure_comes_from_the_thesis_engine():
    r = _node(CARD + f"\nconst h = renderTradeCard({json.dumps(SMCI)});\n"
              "console.log(JSON.stringify({scope: h.includes('1d · CAMPAIGN · since 2026-08-24'),"
              " phase: h.includes('Phase E') && h.includes('SOS -&gt; LPS continuation'),"
              " status: h.includes('observed (activated)'),"
              " last: h.includes('RETEST_HELD_UP') && h.includes('2026-10-07') && h.includes('42.31'),"
              " failure: h.includes('invalidation not reached'),"
              " others: h.includes('no conflicting thesis on another timeframe'),"
              " noLegacy: !h.includes('DISTRIBUTION') && !h.includes('ACCUMULATION_SPRING')}));")
    assert r == {"scope": True, "phase": True, "status": True, "last": True, "failure": True, "others": True,
                 "noLegacy": True}


def test_a_closed_thesis_shows_its_failure_evidence():
    row = {**SMCI, "thesis__readiness": "CLOSED_INVALIDATED", "thesis__readiness_reason": "INVALIDATED@2026-10-08"}
    r = _node(CARD + f"\nconst h = renderTradeCard({json.dumps(row)});\n"
              "console.log(JSON.stringify({failed: h.includes('failed') && h.includes('INVALIDATED@2026-10-08')}));")
    assert r == {"failed": True}


def test_legacy_structure_fields_are_in_the_legacy_tier():
    legacy = re.search(r"const TC_LEGACY = (/.*?/i);", CARD).group(1)
    r = _node(f"const re = {legacy};\nconsole.log(JSON.stringify(['wyckoff_mode','wyckoff_phase_granular',"
              "'wyckoff_validation_phase_probability','forecast_structure_stage','structure_evidence_state',"
              "'lab_v4_structure_evidence_state','phase','wyckoff_score'].map(f => re.test(f))));")
    assert r == [True] * 8


def test_the_lab_table_and_modal_show_the_thesis_structure():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "cell(s.forecast_structure_stage)" not in html
    assert "s.forecast_structure_stage||'UNRESOLVED'" not in html
    assert "Legacy Wyckoff" in html
