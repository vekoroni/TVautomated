#!/usr/bin/env python3
"""Render the HTML card from its record by one fixed template (render_card_v1, 21 Nov 2026).

AVS-ARCH-LB-001 D1 / D2 (ACK accepted 21 Nov 2026). It reads a record and writes one HTML file. It changes no record,
no decision file, no board and no ledger, and it never writes over a card that already exists.

Why (verified 21 Nov): each card was free-form HTML written by a chat. 24 cards showed at least three tab markups, and
the thesis sentence, notes switch, exit ladder, lifecycle and market-player read were each missing on some. With one
template the frame cannot drift: two cards differ only in what their records say.

The template is card_template_v1.html: the head, styles and script of GILD_deep_dive_2026-11-20.html, the base card
chosen on 21 Nov (status strip, three tabs, "For the trade" notes switch, dark text on white).

Rules:
- Every part of the card standard has its section on every card. A part the record does not carry is shown as
  "Not on the record"; it is never left out and never filled in.
- The record check's verdict and what it found are shown at the top of the card.
- All text from the record is escaped, so a record cannot change the page's structure.
- The same record always renders the same page.

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\render_card.py --record data\\scratch\\workaround\\handoff\\lab_2026-11-20\\decisions\\GILD.json --out-folder %TEMP%\\cards
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import card_record

VERSION = "render_card_v1"
TEMPLATE = Path(__file__).resolve().with_name("card_template_v1.html")
MISSING = '<span class="pill">Not on the record</span>'
SESSION = re.compile(r"(\d{4}-\d{2}-\d{2})")


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def show(value) -> str:
    """One value as escaped text. Lists and objects are written out plainly; an empty value is said to be missing."""
    if value in (None, "", [], {}):
        return MISSING
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return "; ".join(f"{esc(k)}: {show(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(show(v) for v in value)
    return esc(value)


def table(rows) -> str:
    body = "".join(f"<tr><th>{esc(label)}</th><td>{value}</td></tr>" for label, value in rows)
    return f'<div class="tbl"><table>{body}</table></div>'


def note(record: dict, key: str) -> str:
    notes = record.get("notes_for_the_trade")
    text = notes.get(key) if isinstance(notes, dict) else None
    return f'<p class="ft">For the trade: {esc(text)}</p>' if text else ""


def thesis_sentence(record: dict) -> str:
    thesis = record.get("thesis")
    if not isinstance(thesis, dict) or any(thesis.get(part) in (None, "") for part in card_record.THESIS_PARTS):
        return ""
    return (f"Because {thesis['macro']}, {thesis['sector']}, and {thesis['ticker']}, so this option should "
            f"{thesis['move']} by {thesis['by']}, unless {thesis['unless']}.")


def _branches(record: dict) -> str:
    branches = record.get("branches")
    if not isinstance(branches, list) or not branches:
        return f"<p>{MISSING}</p>"
    head = "<tr><th>Side</th><th>Trigger</th><th>Contract</th><th>Max pay</th><th>Stop</th><th>Targets</th><th>Exit steps (GTC)</th></tr>"
    rows = ""
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        rows += ("<tr>" + "".join(f"<td>{show(branch.get(key))}</td>" for key in
                                  ("side", "trigger", "contract", "max_pay", "stop", "targets", "gtc")) + "</tr>")
    return f'<div class="tbl"><table>{head}{rows}</table></div>'


def render(record: dict) -> str:
    """The whole card as one HTML page. Deterministic: the page depends on the record and the template only."""
    check = card_record.check_record(record)
    ticker = esc(str(record.get("ticker") or "").upper())
    day = (SESSION.search(str(record.get("ledger_id") or "")) or SESSION.search(str(record.get("created_utc") or "")))
    day_text = day.group(1) if day else "date not on the record"
    found = [f"{i['rule']} ({i['field']})" for i in check["errors"]] + [f"missing {g['field']}" for g in check["standard_gaps"]]
    banner = f"Record check: {check['verdict']}." + (" " + "; ".join(esc(f) for f in found) + "." if found else "")
    sentence = thesis_sentence(record)
    thesis_html = f'<p class="lead">{esc(sentence)}</p>' if sentence else f"<p>{MISSING}</p>"
    exit_plan = record.get("one_contract_exit") if isinstance(record.get("one_contract_exit"), dict) else {}
    liquidity = record.get("liquidity") if isinstance(record.get("liquidity"), dict) else {}
    kill = (record.get("macro_dependency") or {}).get("kill_switch") if isinstance(record.get("macro_dependency"), dict) else None

    status = [("Decision", f"{show(record.get('decision'))} · {show(record.get('final_action'))}"),
              ("States", show(record.get("states"))),
              ("Contract", f"{show(record.get('contract'))} · size {show(record.get('size'))} · limit {show(record.get('limit'))} · max pay {show(record.get('max_pay'))}"),
              ("Open criteria", show(record.get("entry_type"))),
              ("Liquidity tier", show(liquidity)),
              ("Lifecycle / players", f"Stage {show(record.get('lifecycle_stage'))} · {show(record.get('player_read'))}"),
              ("Macro kill switch", show(kill)),
              ("Stop / time stop", f"{show(record.get('stop'))} · {show(record.get('time_stop'))}"),
              ("Data clocks", f"card written {show(record.get('created_utc'))} · run {show(record.get('run_id'))}")]
    status_html = '<dl class="status" aria-label="Card state">' + "".join(
        f"<div><dt>{esc(label)}</dt><dd>{value}</dd></div>" for label, value in status) + "</dl>"

    card_panel = "".join([
        '<nav class="chips">' + "".join(f'<a class="chip" href="#{anchor}">{esc(label)}</a>' for anchor, label in (
            ("t-decision", "Decision"), ("t-trade", "Trades and criteria"), ("t-liq", "Liquidity"), ("t-pay", "Exits"),
            ("t-events", "Events"), ("t-checks", "What changes the plan"))) + "</nav>",
        '<h2 id="t-decision">Decision</h2>',
        table([("Final action", f"<b>{show(record.get('final_action'))}</b>"), ("Decision", show(record.get("decision"))),
               ("Reason", show(record.get("decision_reason"))), ("States", show(record.get("states"))),
               ("Card side", show(record.get("card_side"))), ("Hand-off side", show(record.get("handoff_side"))),
               ("Lab rank", show(record.get("lab_rank"))), ("Lane", show(record.get("lane")))]),
        note(record, "decision"),
        '<h2 id="t-trade">The trades and their criteria</h2>', _branches(record),
        table([("Entry", show(record.get("entry_type"))),
               ("Close zone", f"{show(record.get('close_zone_low'))} to {show(record.get('close_zone_high'))}"),
               ("Limit", show(record.get("limit"))), ("Max pay", show(record.get("max_pay"))), ("Size", show(record.get("size"))),
               ("Extra conditions", show(record.get("extra_conditions"))), ("Vetoes", show(record.get("vetoes")))]),
        note(record, "trade"),
        '<h2 id="t-liq">Liquidity</h2>', table([("Tier", show(liquidity.get("tier"))), ("Spread, % of mid", show(liquidity.get("spread_pct_mid"))),
                                               ("Open interest", show(liquidity.get("oi"))), ("Stock $M a day", show(liquidity.get("stock_dv_m")))]),
        note(record, "liquidity"),
        '<h2 id="t-pay">Price lines, payoff and exits</h2>',
        table([("One-contract exit", show(exit_plan)), ("Targets", show(record.get("targets"))), ("Stop", show(record.get("stop"))),
               ("Time stop", show(record.get("time_stop"))), ("Resting exit recorded", show(record.get("resting_exit"))),
               ("Order placed", show(record.get("order_placed"))), ("Fill", show(record.get("fill")))]),
        note(record, "exits"),
        '<h2 id="t-events">Events in the hold</h2>', f"<p>{show(record.get('events_in_hold'))}</p>",
        '<h2 id="t-checks">What changes the plan</h2>',
        table([("Discriminator", show(record.get("discriminator"))), ("Invalidation", show(record.get("invalidation")))]),
        note(record, "checks")])

    evidence_panel = "".join([
        '<nav class="chips">' + "".join(f'<a class="chip" href="#{anchor}">{esc(label)}</a>' for anchor, label in (
            ("e-thesis", "Thesis sentence"), ("e-life", "Lifecycle and players"), ("e-money", "Macro dependency"),
            ("e-levels", "52-week check"), ("e-challenge", "Challenge"), ("e-fresh", "Sources"))) + "</nav>",
        '<h2 id="e-thesis">Thesis sentence</h2>', thesis_html, note(record, "thesis"),
        '<h2 id="e-life">Narrative lifecycle and the market players</h2>',
        table([("Lifecycle stage (1 to 7)", show(record.get("lifecycle_stage"))), ("Market-player read", show(record.get("player_read")))]),
        '<h2 id="e-money">Macro dependency</h2>', table([("Kill switch", show(kill)), ("Dependency", show(record.get("macro_dependency")))]),
        '<h2 id="e-levels">52-week check</h2>', f"<p>{show(record.get('resistance_test'))}</p>",
        '<h2 id="e-challenge">Challenge</h2>',
        table([("Challenged by", show(record.get("challenge"))), ("Checked by", show(record.get("checked"))),
               ("Forecast", show(record.get("forecast")))]),
        '<h2 id="e-fresh">Sources</h2>', f"<p>{show(record.get('sources'))}</p>"])

    news = record.get("news")
    if isinstance(news, list) and news:
        rows = "".join("<tr>" + "".join(f"<td>{show(item.get(key) if isinstance(item, dict) else item)}</td>"
                                        for key in ("date", "headline", "source", "effect")) + "</tr>" for item in news)
        news_html = f'<div class="tbl"><table><tr><th>Date</th><th>Headline</th><th>Source</th><th>Effect on the trade</th></tr>{rows}</table></div>'
    else:
        news_html = "<p>No ticker news on the record.</p>"

    version = show(record.get("card_version"))
    supersedes = f" · supersedes {esc(record['supersedes'])}" if record.get("supersedes") else ""
    body = "".join([
        f'<header class="masthead"><h1>{ticker}: deep dive, {esc(day_text)}</h1>'
        f'<span class="id">{show(record.get("ledger_id"))} · card v{version}{supersedes} · run {show(record.get("run_id"))} · {VERSION}</span></header>',
        status_html, f'<div class="banner">{banner}</div>',
        '<div class="notesw"><label><input type="checkbox" id="ftsw" checked> Show "For the trade" notes</label></div>',
        '<nav class="tabs" role="tablist"><button class="tab" data-key="card" type="button">1 Trade card</button>'
        '<button class="tab" data-key="evidence" type="button">2 Evidence and challenge</button>'
        '<button class="tab" data-key="news" type="button">3 Ticker news</button></nav>',
        f'<section class="panel prose" data-key="card">{card_panel}</section>',
        f'<section class="panel prose" data-key="evidence">{evidence_panel}</section>',
        f'<section class="panel prose" data-key="news"><h2>Ticker news that might move the share price</h2>{news_html}</section>'])
    template = TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{{TITLE}}", f"{ticker} card {esc(day_text)} v{version}").replace("{{BODY}}", body)


def write_card(record: dict, out_folder: Path) -> Path:
    """Write <TICKER>_card_<date>_v<N>.html. A card that exists is never written over: a change is a new version."""
    out_folder = Path(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    day = SESSION.search(str(record.get("ledger_id") or "")) or SESSION.search(str(record.get("created_utc") or ""))
    name = f"{str(record.get('ticker') or 'UNKNOWN').upper()}_card_{day.group(1) if day else 'undated'}_v{record.get('card_version') or 0}.html"
    path = out_folder / name
    if path.exists():
        raise FileExistsError(f"{path} already exists: a changed card is a new card_version, never an overwrite")
    path.write_text(render(record), encoding="utf-8")
    return path


def render_file(record_path: Path, out_folder: Path) -> Path:
    """Render a record file or an older decision file. The source file is read and never changed."""
    raw = json.loads(Path(record_path).read_text(encoding="utf-8-sig"))
    return write_card(card_record.from_decision(raw), out_folder)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", required=True, help="a card record or decision file (JSON)")
    parser.add_argument("--out-folder", required=True)
    args = parser.parse_args(argv)
    print(f"{VERSION}: {render_file(Path(args.record), Path(args.out_folder))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
