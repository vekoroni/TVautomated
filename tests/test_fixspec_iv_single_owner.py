"""Fix Spec (Data Integrity Remediation, 24 Sep 2026) — Fix 2: one owner for the IV fields.

Business rules:
- `iv_percentile` is the share of the ticker's own IV history below today's IV; `iv_rank`
  is the industry-standard range statistic (IV − low) / (high − low) over that same history,
  on the 0–100 scale its readers expect, with its definition and window disclosed. They are
  different numbers and are never collapsed (spec 2a).
- Exactly one function publishes `iv_percentile`, `iv_rank`, `ivp_label` and `ivp_source`,
  with the declared precedence IV history > realised-vol range proxy > MarketData contract
  ivRank > unavailable, one threshold pair, and the suppressed paths named (spec 2b).
- A value the pipeline cannot measure is None / UNKNOWN / UNAVAILABLE, never 50 / 0.50 / FAIR.

Characterisation (retired 24 Sep 2026 with the fix): `iv_rank` was the percentile × 100, the VRP
refinement rewrote `ivp_label` after the number (286 of 1,550 rows on run 20260922_223221), and
seven sites wrote the three fields.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402

AS_OF = date(2026, 9, 18)
SCRIPT = ROOT / "scripts" / "avshunter_options_intelligence.py"
FINAL_WRITE = re.compile(r"\[\s*['\"](iv_rank|iv_percentile|ivp_label)['\"]\s*\]\s*=")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "iv_cache.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE iv_history (ticker TEXT, sample_date TEXT, atm_iv REAL, source TEXT, updated_at TEXT)")
    for i in range(1, 41):                                            # 40 daily samples: 0.20 ... 0.59
        con.execute("INSERT INTO iv_history VALUES ('AAA', ?, ?, 'x', 'x')",
                    ((AS_OF - timedelta(days=i)).isoformat(), 0.60 - i * 0.01))
    for i in range(1, 31):                                            # flat history: rank undefined
        con.execute("INSERT INTO iv_history VALUES ('FLAT', ?, 0.30, 'x', 'x')", ((AS_OF - timedelta(days=i)).isoformat(),))
    con.execute("INSERT INTO iv_history VALUES ('BBB', ?, 0.30, 'x', 'x')", ((AS_OF - timedelta(days=1)).isoformat(),))
    con.commit()
    monkeypatch.setattr(oi, "IV_CACHE_DB", path)
    oi._iv_history_samples.cache_clear()
    return path


def _script_lines():
    return SCRIPT.read_text(encoding="utf-8").splitlines()


# ------------------------------------------------------------------ Fix 2a: rank is a range statistic
def test_iv_rank_from_history_is_the_range_statistic_and_declines_short_or_flat_history():
    history = [0.60 - i * 0.01 for i in range(1, 41)]            # 0.20 ... 0.59
    assert oi.iv_rank_from_history(0.40, history) == pytest.approx((0.40 - 0.20) / (0.59 - 0.20), abs=1e-9)
    assert oi.iv_rank_from_history(0.70, history) == pytest.approx(1.0)        # above the range clips to 1
    assert oi.iv_rank_from_history(0.10, history) == pytest.approx(0.0)
    assert oi.iv_rank_from_history(0.40, history[:10]) is None                 # below IV_PERCENTILE_MIN_SAMPLES
    assert oi.iv_rank_from_history(0.30, [0.30] * 30) is None                  # flat range: undefined
    assert oi.iv_rank_from_history(None, history) is None


def test_history_percentile_and_range_rank_are_published_as_different_disclosed_numbers(cache):
    result = {"iv_percentile": 0.90, "ivp_252d": 0.90, "ivp_30d": 0.80}
    oi._apply_true_iv_percentile(result, "AAA", 0.40, AS_OF)
    assert result["iv_percentile"] == 0.525                        # 21 of 40 samples below 0.40 (float rounding)
    assert result["iv_rank"] == pytest.approx(51.3, abs=0.05)      # (0.40 − 0.20) / (0.59 − 0.20) × 100
    assert result["iv_rank_definition"] == oi.IV_RANK_DEFINITION == "RANGE_IV_HISTORY"
    assert result["iv_rank_window_sessions"] == 40
    assert result["ivp_source"] == "IV_HISTORY_252D"
    assert result["ivp_label"] == "FAIR"
    assert result["iv_vs_rv_range_252d"] == 0.90                    # the proxy is kept under its own name


def test_flat_history_gives_a_percentile_but_no_rank(cache):
    result = {}
    oi._apply_true_iv_percentile(result, "FLAT", 0.35, AS_OF)
    assert result["iv_percentile"] == 1.0
    assert result["iv_rank"] is None
    assert result["iv_rank_definition"] == "RANGE_IV_HISTORY"


# ------------------------------------------------------------------ Fix 2b: one owner, declared precedence
def test_resolver_prefers_history_then_proxy_then_marketdata_and_names_what_it_suppressed():
    ctx = {"iv_percentile_history": 0.30, "iv_rank_history": 0.42, "iv_history_samples": 40,
           "iv_vs_rv_range_primary": 0.90, "iv_engine_proxy_pct": 0.55}
    contract = {"iv_percentile_marketdata": 0.80, "iv_rank_marketdata": 80.0, "iv_engine_vrp_signal": "SELL_EDGE"}
    out = oi.resolve_iv_ownership(ctx, contract)
    assert out["iv_percentile"] == 0.30 and out["iv_rank"] == 42.0 and out["ivp_label"] == "CHEAP"
    assert out["ivp_source"] == "IV_HISTORY_252D"
    assert set(out["ivp_suppressed_sources"]) == {"RV_RANGE_PROXY", "MARKETDATA_CONTRACT_IVRANK", "IV_ENGINE_PROXY"}

    proxy_only = oi.resolve_iv_ownership({"iv_vs_rv_range_primary": 0.90}, {"iv_percentile_marketdata": 0.10})
    assert proxy_only["iv_percentile"] == 0.90 and proxy_only["ivp_label"] == "EXPENSIVE"
    assert proxy_only["iv_rank"] is None                            # a realised-vol range is not an IV range rank
    assert proxy_only["ivp_source"] == "RV_RANGE_PROXY"
    assert proxy_only["ivp_suppressed_sources"] == ["MARKETDATA_CONTRACT_IVRANK"]

    md_only = oi.resolve_iv_ownership({}, {"iv_percentile_marketdata": 0.10, "iv_rank_marketdata": 12.0})
    assert md_only["iv_percentile"] == 0.10 and md_only["ivp_label"] == "CHEAP"
    assert md_only["iv_rank"] == 12.0 and md_only["iv_rank_definition"] == "MARKETDATA_CONTRACT_IVRANK"
    assert md_only["ivp_source"] == "MARKETDATA_CONTRACT_IVRANK"


def test_resolver_never_fabricates_a_neutral_value_and_ignores_the_vrp_signal():
    out = oi.resolve_iv_ownership({"iv_engine_proxy_pct": 0.55, "iv_level_bucket_pct": 0.60},
                                  {"iv_engine_vrp_signal": "BUY_EDGE"})
    assert out["iv_percentile"] is None and out["iv_rank"] is None
    assert out["ivp_label"] == "UNKNOWN" and out["ivp_source"] == "UNAVAILABLE"
    labelled = oi.resolve_iv_ownership({"iv_percentile_history": 0.50, "iv_rank_history": 0.5, "iv_history_samples": 30},
                                       {"iv_engine_vrp_signal": "BUY_EDGE"})
    assert labelled["ivp_label"] == "FAIR"                          # VRP does not rewrite the label


@pytest.mark.parametrize("ivp,label", [(0.40, "CHEAP"), (0.401, "FAIR"), (0.65, "FAIR"), (0.651, "EXPENSIVE")])
def test_one_threshold_pair_governs_the_label(ivp, label):
    out = oi.resolve_iv_ownership({"iv_percentile_history": ivp, "iv_rank_history": 0.5, "iv_history_samples": 30}, None)
    assert out["ivp_label"] == label
    assert (oi.IVP_CHEAP_MAX, oi.IVP_EXPENSIVE) == (0.40, 0.65)


def test_only_the_resolver_writes_the_three_governed_fields():
    lines = _script_lines()
    inside = False
    offenders = []
    for number, line in enumerate(lines, 1):
        if line.startswith("def "):
            inside = line.startswith("def resolve_iv_ownership(")
        if FINAL_WRITE.search(line) and not inside:
            offenders.append((number, line.strip()))
    assert offenders == [], offenders
    source = "\n".join(lines)
    assert "vrp_signal == 'BUY_EDGE' and iv_ctx.get('ivp_label') == 'FAIR'" not in source
    assert "result['iv_rank']       = 50" not in source
    assert "Polygon returns chains without IV data" not in source     # stale comment corrected
