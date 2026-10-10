"""Phase 5.5: the Lab card renders the thesis (one candidate, one story) and Vanguard's context.

Business rules (design §10 Lab):
- "Why now" shows the thesis's OWN trigger level and its readiness from its own events (accepted break / held retest),
  with the governing candidate and the deciding event. The state category (trigger_primary) is shown only as a labelled
  state reading, never as the trigger.
- No thesis trigger is stated as missing, never filled from another source.
- The card names the top timeframe and counts conflicting theses; the Morning intraday build-up is advisory.
- Vanguard's context flags are shown as context only.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
THESIS = {"ticker": "AAA", "direction": "CALL", "thesis_trigger_level": 101.5,
          "thesis_trigger_candidate_id": "AAA|1w|SOS|2026-09-12", "thesis__top_timeframe": "1w",
          "thesis__conflicting_count": 1, "thesis__readiness": "READY_FOR_HUMAN_REVIEW",
          "thesis__readiness_event_date": "2026-10-05", "thesis__readiness_reason": "BREAK_ACCEPTED_UP@2026-10-05",
          "thesis__last_event": "VWAP_RECLAIM", "ib_state": "ALIGNED", "ib_last_event": "RETEST_HELD_UP",
          "vanguard_context_flags": "HISTORY_AGAINST_THESIS_SIDE", "trigger_primary": "VOL_COMPRESSION",
          "trigger_quality": "SINGLE"}


def _render(sig):
    probe = SCRIPT + f"\nconsole.log(JSON.stringify(renderTradeCard({json.dumps(sig)})));"
    out = subprocess.run(["node"], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_why_now_is_the_thesis_trigger_and_its_readiness():
    html = _render(THESIS)
    assert "Thesis trigger" in html and "101.5" in html
    assert "ready for your review" in html and "BREAK_ACCEPTED_UP@2026-10-05" in html
    assert "AAA|1w|SOS|2026-09-12" in html and "1w" in html and "1 conflicting" in html
    assert "state reading, not the trigger" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_missing_thesis_trigger_is_stated_not_filled():
    html = _render({**THESIS, "thesis_trigger_level": None, "thesis__readiness": "WAIT_TRIGGER",
                    "trigger_price": 97.0, "legacy_wbs_trigger_price": 97.0})
    assert "no thesis trigger" in html
    assert "waiting for the trigger to be accepted" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_intraday_build_up_and_vanguard_context_are_advisory():
    html = _render(THESIS)
    assert "Intraday build-up" in html and "RETEST_HELD_UP" in html and "advisory" in html
    assert "HISTORY_AGAINST_THESIS_SIDE" in html and "context only" in html


def test_the_card_fields_are_registered_so_they_are_not_listed_as_evidence():
    for field in ("thesis_trigger_level", "thesis__readiness", "thesis_trigger_candidate_id", "ib_state",
                  "vanguard_context_flags"):
        assert f"'{field}'" in SCRIPT.split("const TC_CARD_FIELDS", 1)[1].split("]);", 1)[0], field
