"""Output-trust item 6 (D5-5; ACK approved 9 Oct 2026): IV labels say what was measured.

Root cause: the IV owner (scripts/avshunter_options_intelligence.resolve_iv_ownership) names every history-based
reading IV_HISTORY_252D, while the window holds whatever the cache has (SMCI 8 Oct: 66 samples; the cache was restored
on 8 Sep). The card showed only CHEAP / FAIR / EXPENSIVE.

Business rules:
- The source names the method, not a window it may not have: IV_HISTORY, with the samples used and the first date.
- SHORT_HISTORY when fewer than the governed full window (252 samples); FULL_WINDOW at or above it.
- IV rank (position in the history's range) and IV percentile (share of the history below today) are shown
  separately, each with its definition and sample count.
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import avshunter_options_intelligence as oi  # noqa: E402

AS_OF = date(2026, 10, 8)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "iv_cache.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE iv_history (ticker TEXT, sample_date TEXT, atm_iv REAL, source TEXT, updated_at TEXT)")
    for i in range(1, 67):                                            # 66 samples, like SMCI on 8 Oct
        con.execute("INSERT INTO iv_history VALUES ('SMCI', ?, ?, 'x', 'x')",
                    ((AS_OF - timedelta(days=i)).isoformat(), 0.50 + (i % 30) * 0.01))
    for i in range(1, 300):                                           # a full year of daily samples
        con.execute("INSERT INTO iv_history VALUES ('KO', ?, ?, 'x', 'x')",
                    ((AS_OF - timedelta(days=i)).isoformat(), 0.15 + (i % 40) * 0.002))
    con.commit()
    monkeypatch.setattr(oi, "IV_CACHE_DB", path)
    oi._iv_history_samples.cache_clear()
    return path


def test_short_history_is_named_with_its_samples_and_first_date(cache):
    result = {}
    oi._apply_true_iv_percentile(result, "SMCI", 0.60, AS_OF)
    assert result["ivp_source"] == "IV_HISTORY" and result["iv_rank_window_sessions"] == 66
    assert result["iv_history_state"] == "SHORT_HISTORY"
    assert result["iv_history_first_date"] == (AS_OF - timedelta(days=66)).isoformat()


def test_a_full_year_is_full_window(cache):
    result = {}
    oi._apply_true_iv_percentile(result, "KO", 0.18, AS_OF)
    assert result["iv_history_state"] == "FULL_WINDOW" and result["iv_rank_window_sessions"] >= 252


def test_a_proxy_source_is_not_called_iv_history():
    out = oi.resolve_iv_ownership({"iv_vs_rv_range_primary": 0.9}, None)
    assert out["ivp_source"] == "RV_RANGE_PROXY" and out["iv_history_state"] == "NOT_IV_HISTORY"


def test_the_full_window_is_governed_config():
    cfg = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))
    assert cfg["iv_history"]["full_window_samples"] == 252


def test_the_book_carries_the_history_state():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    assert {"iv_history_state", "iv_history_first_date"} <= set(FINAL_BOOK_FIELDS)
    row = opportunity_book_row({"ticker": "SMCI", "direction": "CALL", "opt__iv_history_state": "SHORT_HISTORY",
                                "opt__iv_history_first_date": "2026-08-03"}, "RUN", 1)
    assert (row["iv_history_state"], row["iv_history_first_date"]) == ("SHORT_HISTORY", "2026-08-03")


def test_the_card_shows_rank_and_percentile_separately_with_samples():
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "SMCI", "direction": "CALL", "iv_percentile": 0.52, "iv_rank": 51.3, "ivp_label": "FAIR",
           "ivp_source": "IV_HISTORY", "iv_rank_window_sessions": 66, "iv_history_state": "SHORT_HISTORY",
           "iv_history_first_date": "2026-08-03"}
    out = subprocess.run(["node"], input=card + f"\nconst h = renderTradeCard({json.dumps(row)});\n"
                         "console.log(JSON.stringify({p: h.includes('percentile 52% (share of 66 samples below today)'),"
                         " r: h.includes('rank 51 (position in the range of 66 samples)'),"
                         " s: h.includes('short history: 66 samples since 2026-08-03')}));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"p": True, "r": True, "s": True}


def test_the_lab_iv_title_states_samples_and_short_history():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    fn = re.search(r"function getIvSourceTitle\(s\) \{.*?\n\}", html, re.S).group(0)
    probe = ("function getOpt(s, k) { return s[k]; }\n" + fn +
             "\nconsole.log(JSON.stringify(getIvSourceTitle({ivp_source:'IV_HISTORY', iv_rank_window_sessions:66,"
             " iv_history_state:'SHORT_HISTORY', iv_history_first_date:'2026-08-03'})));")
    out = subprocess.run(["node"], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=60)
    title = json.loads(out.stdout.strip().splitlines()[-1])
    assert "66 samples since 2026-08-03" in title and "SHORT_HISTORY" in title and "252D" not in title
