"""Direction is labelled UNVALIDATED wherever the Lab shows a side (ACK 7 Oct 2026: "label direction unvalidated").

Evidence: four survivorship-free studies (Enhancements/direction_evidence/*_RESULTS_20261007.md) found no measured
direction edge - not in the pipeline's setups, side rules, a top-down trend read, momentum or compression.

Business rules:
- One owner: the validation state and its basis come from versioned config (direction_validation), display only.
- The book carries the state and basis for every row; the trade card, the trade summary and the Lab's direction
  badge show it next to the side. A "confirmed" governance path never reads as a validated direction.
- Missing is never neutral: a row without the state says the validation is not recorded.
- The label never changes the side, a gate, a score or a rank.
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


def test_the_validation_state_is_governed_config_and_display_only():
    cfg = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))
    block = cfg["direction_validation"]
    assert block["state"] == "TESTED_NO_EDGE" and block["authority"] == "DISPLAY_ONLY"   # ACK 9 Oct: precise wording
    assert block["basis"] and block["evidence"]


def test_the_book_carries_the_state_and_basis_on_every_row_without_changing_the_side():
    assert "direction_validation_state" in FINAL_BOOK_FIELDS and "direction_validation_basis" in FINAL_BOOK_FIELDS
    row = opportunity_book_row({"ticker": "MSFT", "direction": "CALL"}, "RUN", 1)
    assert row["direction_validation_state"] == "TESTED_NO_EDGE"
    assert "no measured direction edge" in row["direction_validation_basis"]
    assert row["direction"] == "CALL"


def test_the_trade_card_labels_the_side_unvalidated_and_states_a_missing_label():
    script = (STATIC / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const base = {ticker:'MSFT', direction:'CALL'};
const a = renderTradeCard({...base, direction_validation_state:'TESTED_NO_EDGE',
                           direction_validation_basis:'no measured direction edge (7 Oct 2026 studies)'});
const b = renderTradeCard(base);
console.log(JSON.stringify({labelled: a.includes('CALL · tested: no edge found'), basis: a.includes('no measured direction edge'),
                            missing: b.includes('direction validation not recorded')}));
"""
    assert _node(probe) == {"labelled": True, "basis": True, "missing": True}


def test_the_trade_summary_side_column_says_unvalidated():
    script = (STATIC / "trade-summary.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeSummaryTable([{ticker:'MSFT', direction:'CALL', trade_lane:'A',
                                       direction_validation_state:'TESTED_NO_EDGE'}]);
console.log(JSON.stringify({side: html.includes('<td>CALL · tested: no edge found</td>')}));
"""
    assert _node(probe) == {"side": True}


def test_a_confirmed_governance_path_never_reads_as_a_validated_direction():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    fn = re.search(r"function directionResolutionBadge\(s\) \{.*?\n\}", html, re.S).group(0)
    labels = re.search(r"const DIRECTION_EDGE_LABELS = \{.*?\};", html, re.S).group(0)
    probe = labels + """
function directionResolutionPath(s) { return s._path; }
""" + fn + """
const confirmed = directionResolutionBadge({_path:'DIRECTION_CONFIRMED', direction_validation_state:'TESTED_NO_EDGE',
                                            direction_validation_basis:'no measured direction edge'});
const missing = directionResolutionBadge({_path:'DIRECTION_CONFIRMED'});
console.log(JSON.stringify({label: confirmed.label, cls: confirmed.cls,
                            keepsPath: confirmed.title.includes('record consistent'),
                            basis: confirmed.title.includes('no measured direction edge'),
                            missing: missing.label}));
"""
    assert _node(probe) == {"label": "tested: no edge found", "cls": "a", "keepsPath": True, "basis": True,
                            "missing": "validation not recorded"}
