"""A1 (ACK 6 Oct 2026, "approve A1"): a valid share price is never thrown away for being old.

Run 20261006_060401: 17 rows had a valid MarketData SmartMid older than 300 s discarded (STALE_PROVIDER_PRICE); the
lifecycle then saw "no spot" and gave CONTRACT_REPRICE_REQUIRED / LIVE_PRICE_UNAVAILABLE - 6 lane A rows could not be
GO, labelled "unavailable" when the price was only old. Standing ACK rule: quote age is disclosed, never a gate.
Business rules:
- A valid provider price is kept whatever its age; its age and source time are published.
- live_price_state labels it CURRENT or AGED_REFERENCE (display only; boundary in config share_price_label).
- Invalid inputs are still rejected: missing or future-dated provider timestamp, wrong symbol, non-positive mid.
- The book carries the price age and the card shows it under "Can I trust the data".
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import morning_gate  # noqa: E402

NOW = datetime(2026, 10, 6, 14, 45, tzinfo=timezone.utc)


def _payload(age=timedelta(seconds=20), mid=55.63):
    return {"s": "ok", "symbol": ["BLDR"], "mid": [mid], "updated": [int((NOW - age).timestamp())]}


def test_an_old_valid_price_is_kept_and_its_age_disclosed():
    out = morning_gate._parse_marketdata_stock_price(_payload(age=timedelta(minutes=20)), "BLDR", now_utc=NOW)
    assert out["live_price"] == 55.63
    assert out["live_price_age_seconds"] == 1200.0
    assert out["live_price_state"] == "AGED_REFERENCE"
    assert "live_fetch_error" not in out


def test_a_recent_price_is_current():
    out = morning_gate._parse_marketdata_stock_price(_payload(), "BLDR", now_utc=NOW)
    assert out["live_price_state"] == "CURRENT" and out["live_price_age_seconds"] == 20.0


def test_invalid_inputs_are_still_rejected():
    future = morning_gate._parse_marketdata_stock_price(_payload(age=timedelta(minutes=-2)), "BLDR", now_utc=NOW)
    assert future["live_fetch_error"] == "FUTURE_PROVIDER_TIMESTAMP" and "live_price" not in future
    zero = morning_gate._parse_marketdata_stock_price(_payload(mid=0), "BLDR", now_utc=NOW)
    assert zero["live_fetch_error"] == "INVALID_MIDPOINT"


def test_no_age_threshold_gates_the_price():
    src = (ROOT / "morning_gate.py").read_text(encoding="utf-8")
    assert "LIVE_STOCK_PRICE_MAX_AGE_SECONDS" not in src and '"STALE_PROVIDER_PRICE"' not in src
    cfg = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))
    assert cfg["share_price_label"]["authority"] == "DISPLAY_ONLY"


def test_the_book_and_card_carry_the_price_age():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    row = opportunity_book_row({"ticker": "BLDR", "live_price": 55.63, "live_price_age_seconds": 1200.0,
                                "live_price_state": "AGED_REFERENCE"}, "RUN", 1)
    assert {"live_price_age_seconds", "live_price_state"} <= set(FINAL_BOOK_FIELDS)
    assert row["live_price_age_seconds"] == 1200.0 and row["live_price_state"] == "AGED_REFERENCE"
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeCard({ticker:'BLDR', direction:'PUT', live_price:55.63, live_price_age_seconds:1200,
  live_price_state:'AGED_REFERENCE'});
console.log(JSON.stringify({shown: html.includes('Share price') && html.includes('20 min old')}));
"""
    out = subprocess.run(["node"], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"shown": True}
