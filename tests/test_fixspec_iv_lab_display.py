"""Fix Spec Fix 2 ripple: the Lab and the book show the governed IV fields, and write none of them.

Rules:
- The book carries `iv_percentile`, `iv_rank`, `ivp_label`, `ivp_source`, `iv_rank_definition`
  and `iv_rank_window_sessions` from the options owner, under their own names.
- The Lab server does not rewrite `iv_rank` / `ivp_label` from the Morning live IV level.
- The page shows IV Rank (range) and IV Percentile as two labelled numbers with the source,
  and never invents a label from a number.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from contracts.lab_control import FINAL_BOOK_FIELDS, write_final_opportunity_book  # noqa: E402
from test_ila_release_coverage_gate import OCC, RUN_ID, _base_signal  # noqa: E402

LAB = ROOT / "intelligence-lab" / "intelligence_lab.py"
PAGE = ROOT / "intelligence-lab" / "static" / "index.html"
GOVERNED_IV_FIELDS = ("iv_percentile", "iv_rank", "ivp_label", "ivp_source", "iv_rank_definition", "iv_rank_window_sessions")


def test_book_contract_carries_the_governed_iv_fields_under_their_own_names(tmp_path):
    assert set(GOVERNED_IV_FIELDS) <= set(FINAL_BOOK_FIELDS)
    book = write_final_opportunity_book(RUN_ID, [_base_signal(
        contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30,
        iv_percentile=0.525, iv_rank=51.3, ivp_label="FAIR", ivp_source="IV_HISTORY_252D",
        iv_rank_definition="RANGE_IV_HISTORY", iv_rank_window_sessions=40,
        iv_alignment="CHEAP", ivp=99.0,                       # stale aliases must not win
    )], {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []}, tmp_path, sync_interpreter=False)
    row = book["rows"][0]
    assert row["iv_percentile"] == 0.525 and row["iv_rank"] == 51.3 and row["ivp_label"] == "FAIR"
    assert row["ivp_source"] == "IV_HISTORY_252D" and row["iv_rank_definition"] == "RANGE_IV_HISTORY"
    assert row["iv_rank_window_sessions"] == 40


def test_book_reads_the_options_owner_prefix_but_no_other_alias(tmp_path):
    book = write_final_opportunity_book(RUN_ID, [_base_signal(
        contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30,
        opt__iv_percentile=0.30, opt__iv_rank=12.0, opt__ivp_label="CHEAP", opt__ivp_source="IV_HISTORY_252D",
        iv_alignment="EXPENSIVE", ivp=88.0,
    )], {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []}, tmp_path, sync_interpreter=False)
    row = book["rows"][0]
    assert (row["iv_percentile"], row["iv_rank"], row["ivp_label"], row["ivp_source"]) == (0.30, 12.0, "CHEAP", "IV_HISTORY_252D")


def test_lab_server_no_longer_rewrites_iv_fields_from_live_iv():
    source = LAB.read_text(encoding="utf-8")
    assert 'sig["opt__ivp_label"] = "CHEAP" if _iv_pct < 20' not in source
    assert 'sig["iv_rank"]        = round(_iv_pct, 1)' not in source
    assert re.search(r'sig\[\s*["\'](iv_rank|ivp_label|opt__iv_rank|opt__ivp_label)["\']\s*\]\s*=', source) is None


def test_page_shows_rank_and_percentile_separately_with_source_and_invents_no_label():
    html = PAGE.read_text(encoding="utf-8")
    assert "ivr < 20 ? 'CHEAP' : ivr < 50 ? 'FAIR' : 'RICH'" not in html
    assert "IV Rank" in html and "IV Percentile" in html
    assert "getIvRankDisplay" in html and "getIvPercentileDisplay" in html and "ivp_source" in html
    assert "mv__iv_pct" not in html.split("function getIvRankDisplay")[1].split("}")[0]
