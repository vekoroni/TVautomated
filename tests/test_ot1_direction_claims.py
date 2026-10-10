"""Output-trust item 1 (D2-2; ACK approved 9 Oct 2026): the Lab states three separate direction claims.

Business rules:
- Structural bias (the thesis side and the timeframe that set it), trigger (the thesis readiness) and predictive edge
  are three different claims; the card shows each with what supports it.
- Predictive edge says exactly what was found: TESTED_NO_EDGE (the 7 Oct studies), distinct from NOT_TESTED and
  INSUFFICIENT_EVIDENCE. One owner: versioned config, display only.
- "DIRECTION_CONFIRMED" only means the governed direction record is consistent; it is shown as "record consistent",
  never as a confirmed direction.
- Display only: no side, gate, score or rank changes.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "intelligence-lab" / "static"


def _node(js: str) -> dict:
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_predictive_edge_states_what_was_found():
    block = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))["direction_validation"]
    assert block["state"] == "TESTED_NO_EDGE" and block["authority"] == "DISPLAY_ONLY" and block["evidence"]


def test_the_book_publishes_the_record_status_not_a_confirmed_direction():
    row = opportunity_book_row({"ticker": "SMCI", "direction": "CALL", "direction_resolution_path": "DIRECTION_CONFIRMED",
                                "direction_governance_status": "CONFIRMED"}, "RUN", 1)
    assert row["direction_record_status"] == "RECORD_CONSISTENT"
    assert "direction_record_status" in FINAL_BOOK_FIELDS
    assert row["direction"] == "CALL"


def test_the_card_shows_three_separate_claims():
    script = (STATIC / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeCard({ticker:'SMCI', direction:'CALL', thesis__side:'BULL', thesis__top_timeframe:'1mo',
  thesis__readiness:'WAIT_TRIGGER', direction_validation_state:'TESTED_NO_EDGE',
  direction_validation_basis:'no measured direction edge (7 Oct 2026 studies)'});
console.log(JSON.stringify({bias: html.includes('Structural bias') && html.includes('BULL') && html.includes('set on 1mo'),
  trigger: html.includes('Trigger state') && html.includes('waiting for the trigger to be accepted'),
  edge: html.includes('Predictive edge') && html.includes('tested: no edge found'),
  noConfirmed: !/confirmed/i.test(html.replace(/not confirmed|unconfirmed/gi, ''))}));
"""
    assert _node(probe) == {"bias": True, "trigger": True, "edge": True, "noConfirmed": True}


def test_the_badge_and_export_say_record_consistent():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Direction confirmed by governed structural authority" not in html
    fn = re.search(r"function directionResolutionBadge\(s\) \{.*?\n\}", html, re.S).group(0)
    labels = re.search(r"const DIRECTION_EDGE_LABELS = \{.*?\};", html, re.S).group(0)
    probe = labels + """
function directionResolutionPath(s) { return s._path; }
""" + fn + """
const b = directionResolutionBadge({_path:'DIRECTION_CONFIRMED', direction_validation_state:'TESTED_NO_EDGE',
                                    direction_validation_basis:'no measured direction edge'});
console.log(JSON.stringify({label: b.label, record: b.title.includes('record consistent')}));
"""
    assert _node(probe) == {"label": "tested: no edge found", "record": True}
    assert "['Direction_Record', s => directionRecordStatus(s)]" in html
