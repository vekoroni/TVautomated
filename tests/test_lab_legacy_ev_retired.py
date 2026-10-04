"""AVS options analytics slice 1d (ACK 30 Sep 2026: "retire EV v2") — the Lab book carries no legacy EV v2.

EV v2 (the v2.1.0 heuristic) is not an expected value (CLAUDE.md rule 5) and is wrong for puts. The book's
`ev_predicted` comes from EV3 only (advisory, and only when EV3 valued the selected contract); a row with only legacy
values publishes no EV, and the LEGACY_EV_* advisory flags are retired. Lab permission never depended on them
(tests/test_big_bang_phase_6_7.py test_manifest_and_resolver: a WEAK legacy hint still resolves GO, now without a
legacy flag).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from contracts.lab_control import opportunity_book_row  # noqa: E402
from test_ila_release_coverage_gate import OCC, RUN_ID, _base_signal  # noqa: E402

LEGACY = {"ev2_ev_conf_adj": 0.31, "eil_ev_net": 0.2, "ev": 0.31, "ev_final": 0.31, "ev2_decision_hint": "WEAK",
          "ev2_status": "NEGATIVE_EV"}
ALIGNED_CONTRACT = dict(lab_verdict="GO_LIMIT", lab_tradeable=True, contract_symbol=OCC, instrument="LONG_CALL",
                        strike=100, expiry="2099-01-19", dte=30, premium_mid=1.05, contract_bid=1.0, contract_ask=1.1,
                        rr_premium_expected=1.8, monetisability_status="COMPLETE",
                        monetisability_state="MONETISABLE", monetisability_contract_symbol=OCC)


def test_a_row_with_only_legacy_ev_publishes_no_ev():
    row = opportunity_book_row(_base_signal(**ALIGNED_CONTRACT, **LEGACY), RUN_ID, 1)
    assert row["ev_predicted"] in ("", None)


def test_an_ev3_valued_selected_contract_still_publishes_its_advisory_ev():
    row = opportunity_book_row(_base_signal(**ALIGNED_CONTRACT, **LEGACY, ev3_status="EVALUATED_SHADOW",
                                            ev3_structure="LONG_SINGLE", ev3_contract_symbol=OCC,
                                            ev3_ev_conservative_return=0.12), RUN_ID, 1)
    assert row["economics_comparable"] is True
    assert row["ev_predicted"] == 0.12
