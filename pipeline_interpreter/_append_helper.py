"""Append new functions to pipeline_interpreter_outputs.py"""

NEW_CODE = '''

def write_all_outputs_with_junior(
    main_response: str,
    story_response: str,
    session,
    run_dir,
    ts: str,
    ticker: str,
    pre_trade_prob_block: str = "",
) -> dict:
    """
    Writes a single unified HTML containing:
      1. The full Dr. Magnus Vale deep dive (from main_response)
      2. PRE-TRADE PROBABILITY ASSESSMENT card (if pre_trade_prob_block provided)
      3. The Junior Trader eight-section briefing (from story_response)
    Falls back gracefully if story sections cannot be parsed.
    """
    from pathlib import Path as _Path
    results = {}
    run_dir = _Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / f"raw_response_{ts}.txt").write_text(main_response, encoding="utf-8")
    (run_dir / f"raw_story_{ts}.txt").write_text(story_response, encoding="utf-8")

    brief_raw  = _extract_section(main_response, "TRADE_BRIEF_CSV")
    brief_rows = _parse_csv(brief_raw) if brief_raw else []
    for _row in brief_rows:
        _t  = _row.get("ticker", "")
        _v  = _row.get("final_verdict", "WAIT")
        _st = _row.get("trade_state", "WATCH")
        if _t and hasattr(session, "add_verdict"):
            session.add_verdict(_t, _v, _st)
    session.last_ticker_csv = brief_rows

    _BRIEF_FIELDS = [
        "ticker", "direction", "final_verdict", "trade_state", "horizon", "dte",
        "trigger_level", "kill_switch_level", "preferred_contract", "premium", "rr",
        "iv_context", "ivp", "earnings_in_window", "earnings_action",
        "max_pain_risk", "sector_confirmation_required", "first_hour_rule",
        "probe_permitted", "initial_adverse_tolerance", "capital_permission",
        "narrative_summary", "execution_permission",
    ]
    _bp = run_dir / f"ticker_{ticker.lower()}_trade_brief_{ts}.csv"
    _write_csv(brief_rows, _bp, _BRIEF_FIELDS)
    results["brief_csv"] = {"path": _bp, "rows": len(brief_rows)}

    main_html = build_html(main_response, session, ts, tickers=[ticker])

    # PRE-TRADE PROBABILITY ASSESSMENT card
    ete_block_html = ""
    if pre_trade_prob_block:
        _ete_esc = (
            pre_trade_prob_block
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        ete_block_html = (
            "<div style=\\"max-width:1280px;margin:0 auto;padding:0 40px 0\\">"
            "<div style=\\"background:#0b0d16;border:2px solid #00d4aa44;"
            "border-radius:8px;margin-top:24px;overflow:hidden\\">"
            "<div style=\\"background:#060f0c;border-bottom:1px solid #00d4aa44;"
            "padding:14px 20px;display:flex;justify-content:space-between;align-items:center\\">"
            "<div style=\\"font-family:monospace;font-size:13px;"
            "color:#00d4aa;font-weight:700;letter-spacing:2px\\">"
            "PRE-TRADE PROBABILITY ASSESSMENT</div>"
            "<div style=\\"font-size:10px;color:#4a5568;font-family:monospace\\">"
            "INFORMATIONAL ONLY &#8212; NEVER BLOCKS VERDICT</div>"
            "</div>"
            "<div style=\\"padding:20px 24px\\">"
            "<pre style=\\"font-family:monospace;font-size:13px;color:#dde4f0;"
            "background:#060810;border:1px solid #1c2235;border-radius:6px;"
            "padding:16px 18px;overflow-x:auto;white-space:pre;line-height:1.6;margin:0\\">"
            + _ete_esc +
            "</pre></div></div></div>"
        )

    try:
        junior_html = _build_junior_section_cards(story_response, ticker, ts)
    except Exception:
        junior_html = "<p style=\\"color:#4a5568;font-family:monospace\\">Junior briefing unavailable.</p>"

    junior_block = (
        "<div style=\\"max-width:1280px;margin:0 auto;padding:0 40px 40px\\">"
        "<div style=\\"background:#0b0d16;border:2px solid #00d4aa44;"
        "border-radius:8px;margin-top:24px;overflow:hidden\\">"
        "<div style=\\"background:#060f0c;border-bottom:1px solid #00d4aa44;"
        "padding:14px 20px;display:flex;justify-content:space-between;align-items:center\\">"
        "<div style=\\"font-family:monospace;font-size:13px;"
        "color:#00d4aa;font-weight:700;letter-spacing:2px\\">JUNIOR TRADER BRIEFING</div>"
        "<div style=\\"font-size:10px;color:#4a5568;font-family:monospace\\">"
        "EXECUTION PERMISSION: NONE &#8212; READ ONLY</div>"
        "</div>"
        "<div style=\\"padding:20px 24px\\">"
        + junior_html +
        "</div></div></div>"
    )

    unified_html = main_html.replace("</body>", ete_block_html + junior_block + "\\n</body>")

    hp = run_dir / f"ticker_{ticker.lower()}_interpreter_{ts}.html"
    hp.write_text(unified_html, encoding="utf-8")
    results["html"] = {"path": hp}
    print(f"  \\u2705 Unified HTML: {hp.name}")

    return results


def _build_junior_section_cards(story_response: str, ticker: str, ts: str) -> str:
    """
    Extract and render the eight Junior Briefing section cards as inner HTML.
    No full-page wrapper. Designed to be embedded in write_all_outputs_with_junior.
    """
    cards_html = ""

    pill_bar = "<div style=\\"display:flex;gap:6px;flex-wrap:wrap;margin:0 0 20px 0\\">"
    for tag, num, label in _SECTION_LABELS:
        short = label.split("\\u2014")[0].strip() if "\\u2014" in label else label.split("&")[0].strip()
        pill_bar += (
            f"<a href=\\"#{tag}_jr\\" style=\\"text-decoration:none;padding:5px 12px;"
            f"border-radius:20px;background:#101420;border:1px solid #1c2235;"
            f"font-size:11px;color:#8895b0;font-family:monospace\\">{num} {short}</a>"
        )
    pill_bar += "</div>"

    for tag, num, label in _SECTION_LABELS:
        content = _extract_junior_section(story_response, tag, ticker)
        if not content:
            content = "Section not generated."

        status = _extract_status(content)
        badge  = _story_badge_html(status)

        import re as _re
        interdep_match = _re.search(r"INTERDEP:\\s*(.+?)(?:\\n|$)", content, _re.IGNORECASE | _re.DOTALL)
        interdep_html  = ""
        if interdep_match:
            interdep_text = interdep_match.group(1).strip()
            content = content[:interdep_match.start()].strip()
            interdep_html = (
                f"<div style=\\"border-top:1px solid #1c2235;margin-top:16px;"
                f"padding-top:10px;font-size:11px;color:#4a5568;font-family:monospace\\">"
                f"INTERDEP: {interdep_text}</div>"
            )

        cards_html += (
            f"<div id=\\"{tag}_jr\\" style=\\"background:#060810;border:1px solid #1c2235;"
            f"border-radius:8px;margin-bottom:14px;overflow:hidden\\">"
            f"<div style=\\"padding:12px 16px;border-bottom:1px solid #1c2235;"
            f"display:flex;justify-content:space-between;align-items:center\\">"
            f"<div style=\\"font-family:monospace;font-size:12px;"
            f"color:#dde4f0;font-weight:600\\">{num}. {label}</div>"
            f"{badge}</div>"
            f"<div style=\\"padding:14px 16px\\" class=\\"narrative-content\\">"
            f"{_md_to_html(content)}"
            f"{interdep_html}"
            f"</div></div>"
        )

    return pill_bar + cards_html
'''

# This approach is too complex with escaping - use a cleaner method
import textwrap

# The actual new code as a clean Python string (no triple-quote confusion)
new_functions = textwrap.dedent("""

def write_all_outputs_with_junior(
    main_response: str,
    story_response: str,
    session,
    run_dir,
    ts: str,
    ticker: str,
    pre_trade_prob_block: str = "",
) -> dict:
    from pathlib import Path as _Path
    results = {}
    run_dir = _Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / f"raw_response_{ts}.txt").write_text(main_response, encoding="utf-8")
    (run_dir / f"raw_story_{ts}.txt").write_text(story_response, encoding="utf-8")

    brief_raw  = _extract_section(main_response, "TRADE_BRIEF_CSV")
    brief_rows = _parse_csv(brief_raw) if brief_raw else []
    for _row in brief_rows:
        _t  = _row.get("ticker", "")
        _v  = _row.get("final_verdict", "WAIT")
        _st = _row.get("trade_state", "WATCH")
        if _t and hasattr(session, "add_verdict"):
            session.add_verdict(_t, _v, _st)
    session.last_ticker_csv = brief_rows

    _BRIEF_FIELDS = [
        "ticker", "direction", "final_verdict", "trade_state", "horizon", "dte",
        "trigger_level", "kill_switch_level", "preferred_contract", "premium", "rr",
        "iv_context", "ivp", "earnings_in_window", "earnings_action",
        "max_pain_risk", "sector_confirmation_required", "first_hour_rule",
        "probe_permitted", "initial_adverse_tolerance", "capital_permission",
        "narrative_summary", "execution_permission",
    ]
    _bp = run_dir / f"ticker_{ticker.lower()}_trade_brief_{ts}.csv"
    _write_csv(brief_rows, _bp, _BRIEF_FIELDS)
    results["brief_csv"] = {"path": _bp, "rows": len(brief_rows)}

    main_html = build_html(main_response, session, ts, tickers=[ticker])

    ete_block_html = ""
    if pre_trade_prob_block:
        _ete_esc = (
            pre_trade_prob_block
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        ete_block_html = (
            "<div style=\\"max-width:1280px;margin:0 auto;padding:0 40px 0\\">"
            "<div style=\\"background:#0b0d16;border:2px solid #00d4aa44;"
            "border-radius:8px;margin-top:24px;overflow:hidden\\">"
            "<div style=\\"background:#060f0c;border-bottom:1px solid #00d4aa44;"
            "padding:14px 20px;display:flex;justify-content:space-between;"
            "align-items:center\\">"
            "<div style=\\"font-family:monospace;font-size:13px;"
            "color:#00d4aa;font-weight:700;letter-spacing:2px\\">"
            "PRE-TRADE PROBABILITY ASSESSMENT</div>"
            "<div style=\\"font-size:10px;color:#4a5568;font-family:monospace\\">"
            "INFORMATIONAL ONLY &#8212; NEVER BLOCKS VERDICT</div>"
            "</div>"
            "<div style=\\"padding:20px 24px\\">"
            "<pre style=\\"font-family:monospace;font-size:13px;color:#dde4f0;"
            "background:#060810;border:1px solid #1c2235;border-radius:6px;"
            "padding:16px 18px;overflow-x:auto;white-space:pre;line-height:1.6;"
            "margin:0\\">"
            + _ete_esc
            + "</pre></div></div></div>"
        )

    try:
        junior_html = _build_junior_section_cards(story_response, ticker, ts)
    except Exception:
        junior_html = (
            "<p style=\\"color:#4a5568;font-family:monospace\\">"
            "Junior briefing unavailable.</p>"
        )

    junior_block = (
        "<div style=\\"max-width:1280px;margin:0 auto;padding:0 40px 40px\\">"
        "<div style=\\"background:#0b0d16;border:2px solid #00d4aa44;"
        "border-radius:8px;margin-top:24px;overflow:hidden\\">"
        "<div style=\\"background:#060f0c;border-bottom:1px solid #00d4aa44;"
        "padding:14px 20px;display:flex;justify-content:space-between;"
        "align-items:center\\">"
        "<div style=\\"font-family:monospace;font-size:13px;"
        "color:#00d4aa;font-weight:700;letter-spacing:2px\\">JUNIOR TRADER BRIEFING</div>"
        "<div style=\\"font-size:10px;color:#4a5568;font-family:monospace\\">"
        "EXECUTION PERMISSION: NONE &#8212; READ ONLY</div>"
        "</div>"
        "<div style=\\"padding:20px 24px\\">"
        + junior_html
        + "</div></div></div>"
    )

    unified_html = main_html.replace("</body>", ete_block_html + junior_block + "\\n</body>")

    hp = run_dir / f"ticker_{ticker.lower()}_interpreter_{ts}.html"
    hp.write_text(unified_html, encoding="utf-8")
    results["html"] = {"path": hp}
    print(f"  \\u2705 Unified HTML: {hp.name}")
    return results


def _build_junior_section_cards(story_response: str, ticker: str, ts: str) -> str:
    pill_bar = "<div style=\\"display:flex;gap:6px;flex-wrap:wrap;margin:0 0 20px 0\\">"
    for tag, num, label in _SECTION_LABELS:
        em_dash = "\\u2014"
        short = label.split(em_dash)[0].strip() if em_dash in label else label.split("&")[0].strip()
        pill_bar += (
            f"<a href=\\"#{tag}_jr\\" style=\\"text-decoration:none;padding:5px 12px;"
            f"border-radius:20px;background:#101420;border:1px solid #1c2235;"
            f"font-size:11px;color:#8895b0;font-family:monospace\\">{num} {short}</a>"
        )
    pill_bar += "</div>"

    cards_html = ""
    for tag, num, label in _SECTION_LABELS:
        content = _extract_junior_section(story_response, tag, ticker)
        if not content:
            content = "Section not generated."
        status = _extract_status(content)
        badge  = _story_badge_html(status)
        interdep_match = re.search(r"INTERDEP:\\s*(.+?)(?:\\n|$)", content, re.IGNORECASE | re.DOTALL)
        interdep_html  = ""
        if interdep_match:
            interdep_text = interdep_match.group(1).strip()
            content = content[:interdep_match.start()].strip()
            interdep_html = (
                f"<div style=\\"border-top:1px solid #1c2235;margin-top:16px;"
                f"padding-top:10px;font-size:11px;color:#4a5568;font-family:monospace\\">"
                f"INTERDEP: {interdep_text}</div>"
            )
        cards_html += (
            f"<div id=\\"{tag}_jr\\" style=\\"background:#060810;border:1px solid #1c2235;"
            f"border-radius:8px;margin-bottom:14px;overflow:hidden\\">"
            f"<div style=\\"padding:12px 16px;border-bottom:1px solid #1c2235;"
            f"display:flex;justify-content:space-between;align-items:center\\">"
            f"<div style=\\"font-family:monospace;font-size:12px;"
            f"color:#dde4f0;font-weight:600\\">{num}. {label}</div>"
            f"{badge}</div>"
            f"<div style=\\"padding:14px 16px\\" class=\\"narrative-content\\">"
            f"{_md_to_html(content)}"
            f"{interdep_html}"
            f"</div></div>"
        )
    return pill_bar + cards_html
""")

# Write to a temp py file, then run it to test
with open("_new_functions_content.py", "w", encoding="utf-8") as f:
    f.write(new_functions)

print("Wrote new_functions_content.py")
print(f"Length: {len(new_functions)} chars")

