"""Quote age is flagged, never a reason to stamp a Morning run DO_NOT_TRADE.

Business rule (ACK): re-value at the current premium; flag quote age, never gate on it.
ACK, 14 Nov 2026: the Morning gate runs at any time during market hours. ACK, 21 Nov 2026:
the verifier's quote-freshness rule "should have changed in previous enhancements; it is no
longer applicable", and Lane B fetches and analyses prices before entry.

Legacy behaviour replaced: when at least half the tradeable rows were on quotes older than the
limit by the pipeline's own clock, R19_QUOTE_FRESH became a book-level P0 and the Morning
verdict was DO_NOT_TRADE (runs 20261114_155308 and 20261119_234734). A stale row also carried a
row-level P0, so it was not counted as a clean row.

Still true after the change: the age is measured and reported on every stale row and in the
book check, with the instruction to re-quote before entry. Other P0 rules keep their verdicts.

Isolated: in-memory rows only; no run folder, no provider, no network.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.avs_verify import avs_verify as verify

RULES = Path(verify.__file__).with_name("avs_verify_rules.json")
VERDICT_TIME = datetime(2026, 11, 20, 15, 58, tzinfo=timezone.utc)
STALE_ROW = {"stamp": "2026-11-20T14:44:00Z", "age": 74 * 60}   # 74 minutes old on both clocks
FRESH_ROW = {"stamp": "2026-11-20T15:55:00Z", "age": 3 * 60}


def _cfg() -> dict:
    return json.loads(RULES.read_text(encoding="utf-8-sig"))


def _check(rows, cfg):
    column_map = {key: None for key in cfg["columns"]}
    column_map["quote_ts"], column_map["quote_age_s"] = "stamp", "age"
    findings = verify.F({})
    tradeable = list(range(len(rows)))
    verify.r_rows(rows, tradeable, column_map, cfg, "morning", VERDICT_TIME, findings)
    # These rows carry only the two quote columns, so every other rule reports missing evidence.
    # Keep the quote rule alone: the verdict below then shows what quote age by itself does.
    findings.book = [item for item in findings.book if item["rule"] == "R19_QUOTE_FRESH"]
    findings.row = {i: [item for item in items if item[0] == "R19_QUOTE_FRESH"]
                    for i, items in findings.row.items()}
    book = next(item for item in findings.book if item["rule"] == "R19_QUOTE_FRESH")
    return findings, tradeable, book


def test_the_governed_policy_says_quote_age_is_a_flag():
    assert _cfg()["timing"]["quote_age_policy"] == "FLAG"


def test_a_morning_on_old_quotes_is_flagged_and_still_usable():
    findings, tradeable, book = _check([dict(STALE_ROW), dict(STALE_ROW)], _cfg())

    assert book["status"] == "FAIL" and book["severity"] == "P1"
    assert "2/2 tradeable rows" in book["message"] and "Re-quote before entry" in book["message"]

    verdict, clean, reason = verify.decide(findings, tradeable)

    assert verdict == "TRUST_WITH_CAVEATS"
    assert clean == tradeable                       # an old quote does not make a row unusable
    assert "caveat" in reason


def test_every_stale_row_still_carries_its_measured_age():
    findings, _, _ = _check([dict(STALE_ROW), dict(FRESH_ROW)], _cfg())

    stale = [item for item in findings.row.get(0, []) if item[0] == "R19_QUOTE_FRESH"]
    assert stale and stale[0][1] == "P1" and "74 min" in stale[0][2]
    assert not [item for item in findings.row.get(1, []) if item[0] == "R19_QUOTE_FRESH"]


def test_fresh_quotes_pass_as_before():
    findings, tradeable, book = _check([dict(FRESH_ROW)], _cfg())

    assert book["status"] == "PASS"
    assert verify.decide(findings, tradeable)[0] != "DO_NOT_TRADE"


def test_other_p0_rules_still_stop_the_verdict():
    findings, tradeable, _ = _check([dict(STALE_ROW)], _cfg())
    findings.b("R16_SPREAD_UNITS", "P0", "FAIL", "another rule's defect")

    assert verify.decide(findings, tradeable)[0] == "DO_NOT_TRADE"


def test_the_policy_is_governed_and_an_unknown_value_is_refused():
    cfg = copy.deepcopy(_cfg())
    cfg["timing"]["quote_age_policy"] = "GATE"
    _, _, book = _check([dict(STALE_ROW)], cfg)
    assert book["severity"] == "P0"                 # the legacy behaviour, reachable only by configuration

    cfg["timing"]["quote_age_policy"] = "IGNORE"
    with pytest.raises(ValueError, match="quote_age_policy"):
        _check([dict(STALE_ROW)], cfg)
