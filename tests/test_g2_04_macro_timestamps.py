"""G2-04 (verification of run 20261008_220129; ACK 9 Oct 2026: fix before the Morning).

Business rules:
- A macro timestamp in the future (beyond a small clock-skew allowance) is labelled FUTURE_TIMESTAMP, never FRESH:
  a negative age is a timestamp-meaning defect, not freshness. Age is disclosed, never a gate.
- The market-intelligence producer states its timestamp in UTC with the offset, so the macro build cannot read
  local time as UTC.

Live run: the producer wrote a naive local 22:38 (file mtime 21:38Z); the macro packet published as_of_utc 22:38Z,
one hour in the future, and its negative age was classified FRESH.
"""
from pathlib import Path

from scripts.macro_quant_packet import _freshness_status

ROOT = Path(__file__).resolve().parents[1]


def test_a_timestamp_an_hour_in_the_future_is_not_fresh():
    assert _freshness_status(-1.0) == "FUTURE_TIMESTAMP"


def test_clock_skew_within_the_allowance_is_still_fresh():
    assert _freshness_status(-0.1) == "FRESH"
    assert _freshness_status(0.5) == "FRESH"


def test_the_market_intelligence_producer_writes_a_utc_timestamp():
    src = (ROOT / "Enhancements" / "colab" / "avshunter_market_intelligence_v5_4_3.py").read_text(encoding="utf-8")
    assert "'timestamp': datetime.now().isoformat()" not in src
    assert "'timestamp': datetime.now(timezone.utc).isoformat()" in src


def test_the_interpreter_does_not_treat_a_future_timestamp_as_clean_context():
    # Both owners of the Interpreter macro context rule treat a timestamp that cannot be trusted like a stale one
    # (the regime is not passed through as current); the freshness label itself still says FUTURE_TIMESTAMP.
    for path in ("contracts/interpreter_macro_context.py", "pipeline_interpreter/macro_context.py"):
        src = (ROOT / path).read_text(encoding="utf-8")
        assert '{"STALE", "MISSING", "INVALID", "FUTURE_TIMESTAMP"}' in src, path
