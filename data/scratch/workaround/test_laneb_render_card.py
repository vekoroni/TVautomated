"""AVS-ARCH-LB-001 D1 / D2 (ACK accepted 21 Nov 2026): the HTML card is rendered from the record by one fixed template.

Business rules:
- One template for every card: the status strip, the three tabs (1 Trade card, 2 Evidence and challenge, 3 Ticker news),
  the "For the trade" notes switch, dark text on white. Two cards differ only in what their records say.
- The thesis sentence is assembled from its six parts, in the card standard's wording.
- Every branch on the record is a ticket on the card, with its own contract, max pay, trigger, stop and exit.
- Missing is never neutral: a part the record does not carry is shown as "Not on the record", and the card says at the
  top what the record check found.
- Nothing from the record can change the page's structure: all text is escaped.
- The same record always renders the same page. A rendered card is never written over.

Legacy behaviour replaced: each card was free-form HTML written by a chat; 24 cards showed at least three tab markups,
and the thesis sentence, notes switch, exit ladder, lifecycle and market-player read were each missing on some.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_render_card.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_rc
Isolated: in-memory records and temporary files only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_card as rc  # noqa: E402
from test_laneb_card_record import record  # noqa: E402


def panel(html: str, key: str) -> str:
    return re.search(rf'<section class="panel prose" data-key="{key}">(.*?)</section>', html, re.S).group(1)


def test_every_card_has_the_same_frame():
    html = rc.render(record())
    assert html.count('class="tab"') == 3
    assert [m for m in re.findall(r'data-key="(\w+)" type="button">([^<]+)<', html)] == [
        ("card", "1 Trade card"), ("evidence", "2 Evidence and challenge"), ("news", "3 Ticker news")]
    assert '<dl class="status"' in html and '<header class="masthead">' in html
    assert 'id="ftsw"' in html and "For the trade" in html                     # the notes switch
    assert "--ink:#151a1f" in html and "--surface:#fff" in html                # dark text on white, from the template
    assert html.count("<script") == 1 and html.rstrip().endswith("</html>")


def test_two_cards_differ_only_in_what_their_records_say():
    a = rc.render(record())
    b = rc.render(record(ticker="SE", ledger_id="2026-11-20_SE_PUT", contract="SE270115P00090000",
                         branches=[{"side": "PUT", "trigger": "t", "contract": "SE270115P00090000", "max_pay": 2.0},
                                   {"side": "CALL", "trigger": "t", "contract": "SE270115C00095000", "max_pay": 1.5}]))
    # the page title names the card, so it is content; everything else in the head is the frame
    frame = lambda html: (re.sub(r"<title>.*?</title>", "", html[:html.index("<body")]),   # noqa: E731
                          re.search(r"<script.*?</script>", html, re.S).group(0),
                          re.findall(r"<h2 id=\"([a-z\-]+)\"", html))
    assert frame(a) == frame(b)


def test_the_thesis_sentence_is_assembled_from_its_parts():
    html = rc.render(record())
    assert ("Because credit is tightening, SE-Asia internet is offered, and GRAB failed at 3.07, so this option should "
            "gain 70% at 2.75 by 2026-12-04, unless a 15:50 ET price above 3.26.") in html


def test_every_branch_is_a_ticket_with_its_own_contract_and_max_pay():
    trade = panel(rc.render(record()), "card")
    assert "GRAB270115C00003000" in trade and "GRAB270115P00003000" in trade
    assert "0.16" in trade and "0.19" in trade and "15:50 ET price 2.75-2.85" in trade
    assert trade.index("CALL") < trade.index("session high")                    # branches in the record's order


def test_a_part_the_record_does_not_carry_is_shown_as_missing_never_left_out():
    thin = record()
    for field in ("thesis", "lifecycle_stage", "player_read", "liquidity", "macro_dependency", "resistance_test", "sources"):
        thin.pop(field)
    html = rc.render(thin)
    assert html.count("Not on the record") >= 6
    assert "ACCEPTED_WITH_GAPS" in html and "thesis" in re.search(r'<div class="banner">(.*?)</div>', html, re.S).group(1)
    for heading in ("Thesis sentence", "Narrative lifecycle and the market players", "Liquidity", "Macro dependency", "52-week check", "Sources"):
        assert heading in html                                                  # the section is still there


def test_a_rejected_record_says_so_at_the_top():
    html = rc.render(record(contract="not a contract"))
    banner = re.search(r'<div class="banner">(.*?)</div>', html, re.S).group(1)
    assert "REJECTED" in banner and "CONTRACT_NOT_AN_OPTION_SYMBOL" in banner


def test_text_from_the_record_cannot_change_the_page():
    html = rc.render(record(decision_reason='<script>alert(1)</script> & "quotes"', player_read="<b>bold</b>"))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>bold</b>" not in html and html.count("<script") == 1


def test_for_the_trade_notes_use_the_switchable_block():
    html = rc.render(record(notes_for_the_trade={"decision": "GRAB is in a box; wait for it to break."}))
    assert '<p class="ft">For the trade: GRAB is in a box; wait for it to break.</p>' in html


def test_ticker_news_is_listed_or_said_to_be_absent():
    with_news = panel(rc.render(record(news=[{"date": "2026-11-19", "headline": "Buyback extended", "source": "company release",
                                              "effect": "supports the floor"}])), "news")
    assert "Buyback extended" in with_news and "company release" in with_news
    assert "No ticker news on the record" in panel(rc.render(record()), "news")


def test_the_same_record_always_renders_the_same_page():
    assert rc.render(record()) == rc.render(json.loads(json.dumps(record())))


def test_a_rendered_card_is_named_by_version_and_never_written_over(tmp_path):
    path = rc.write_card(record(), tmp_path)
    assert path.name == "GRAB_card_2026-11-20_v1.html" and "<html" in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        rc.write_card(record(), tmp_path)
    assert rc.write_card(record(card_version=2, supersedes="2026-11-20_GRAB_CALL"), tmp_path).name == "GRAB_card_2026-11-20_v2.html"


def test_an_older_decision_file_renders_without_being_changed(tmp_path):
    old = record()
    for field in ("record_version", "thesis", "sources", "lab_rank"):
        old.pop(field)
    source = tmp_path / "GRAB.json"
    source.write_text(json.dumps(old), encoding="utf-8")
    before = source.read_bytes()

    path = rc.render_file(source, tmp_path / "out")

    assert "Not on the record" in path.read_text(encoding="utf-8") and source.read_bytes() == before
