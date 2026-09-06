"""Run-scoped compatibility artifacts with atomic shadow publication."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .market_structure import MARKET_STRUCTURE_FIELDS
from .models import TickerRunResult
from .schemas import TRADE_BRIEF_FIELDS, TradeBrief


HtmlRenderer = Callable[[TickerRunResult, dict[str, Any]], str]


def _default_html(result: TickerRunResult, row: dict[str, Any]) -> str:
    narrative = result.analysis.narrative if result.analysis else ""
    sections = result.analysis.junior_briefing if result.analysis else {}
    cards = "".join(
        f"<section><h2>{html.escape(str(tag))}</h2>"
        f"<pre>{html.escape(str(content))}</pre></section>"
        for tag, content in sections.items()
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(result.ticker)} Shadow Interpreter</title></head>"
        "<body data-mode='SHADOW'>"
        f"<h1>{html.escape(result.ticker)} â€” SHADOW</h1>"
        f"<p>Verdict: {html.escape(result.effective_verdict)}</p>"
        f"<p>EIL: {html.escape(result.eil_action)}</p>"
        f"<p>Execution: {html.escape(result.execution_permission)}</p>"
        f"<p>Capital: {html.escape(result.capital_permission)}</p>"
        f"<pre>{html.escape(narrative)}</pre>{cards}</body></html>"
    )


def _enhanced_html(result: TickerRunResult, row: dict[str, Any]) -> str:
    """Render the legacy-style report with deterministic execution intelligence."""
    narrative = result.analysis.narrative if result.analysis else ""
    sections = result.analysis.junior_briefing if result.analysis else {}

    def value(name: str) -> str:
        raw = row.get(name, "")
        return html.escape(str(raw)) if str(raw).strip() else "NOT AVAILABLE"

    def pairs(items: tuple[tuple[str, str], ...]) -> str:
        return "".join(
            f"<span>{html.escape(label)}</span><span>{value(field)}</span>"
            for label, field in items
        )

    cards = "".join(
        f"<section class='brief-card' id='{html.escape(str(tag))}'>"
        f"<h2>{html.escape(str(tag).replace('_', ' ').title())}</h2>"
        f"<div class='copy'>{html.escape(str(content))}</div></section>"
        for tag, content in sections.items()
    )
    vetoes = " | ".join(result.veto_codes) or "NONE"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(result.ticker)} Pipeline Interpreter</title>"
        "<style>:root{--bg:#050811;--panel:#0b1220;--line:#1b2a3d;"
        "--text:#dce6f2;--muted:#7890a8;--cyan:#00d9ff;--green:#00e6a8;"
        "--amber:#f5a623;--red:#ff4069;font-family:Inter,Segoe UI,sans-serif}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text)}"
        ".wrap{max-width:1280px;margin:auto;padding:28px}.top{display:flex;gap:18px;"
        "align-items:center;border-bottom:1px solid var(--line);padding-bottom:20px}"
        "h1{font:700 42px ui-monospace;margin:0;color:var(--cyan)}"
        ".badges{display:flex;gap:8px;flex-wrap:wrap}.badge{padding:6px 10px;"
        "border:1px solid var(--line);font:700 12px ui-monospace}.stop{color:var(--red);"
        "border-color:var(--red)}.safe{color:var(--green)}.sovereign{margin:20px 0;"
        "padding:16px;border:2px solid var(--red);background:#210712;"
        "font:700 13px ui-monospace;color:#ff8aa4}.grid{display:grid;"
        "grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}"
        ".panel,.brief-card{background:linear-gradient(180deg,#0c1524,#08101b);"
        "border:1px solid var(--line);border-radius:7px;padding:16px}"
        ".panel h3,.brief-card h2{margin:0 0 12px;color:var(--cyan);"
        "font:700 12px ui-monospace;letter-spacing:1.4px}.kv{display:grid;"
        "grid-template-columns:1fr auto;gap:7px;font:12px ui-monospace}"
        ".kv span:nth-child(odd){color:var(--muted)}.kv span:nth-child(even){color:var(--text)}"
        ".narrative,.copy{white-space:pre-wrap;line-height:1.7;color:#b8c7d8}"
        ".brief-card{margin-top:12px}.section-title{margin:30px 0 12px;"
        "font:700 14px ui-monospace;letter-spacing:2px;color:var(--amber)}"
        "@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}}"
        "@media(max-width:560px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;"
        "flex-direction:column}}</style></head><body data-mode='SHADOW'><main class='wrap'>"
        f"<header class='top'><h1>{html.escape(result.ticker)}</h1><div class='badges'>"
        f"<span class='badge stop'>VERDICT {html.escape(result.effective_verdict)}</span>"
        f"<span class='badge stop'>EIL {html.escape(result.eil_action)}</span>"
        "<span class='badge safe'>SHADOW / READ ONLY</span></div></header>"
        f"<div class='sovereign'>EXECUTION: {html.escape(result.execution_permission)}"
        f" &nbsp;|&nbsp; CAPITAL: {html.escape(result.capital_permission)}"
        f" &nbsp;|&nbsp; VETOES: {html.escape(vetoes)}</div>"
        "<h2 class='section-title'>MARKET STRUCTURE &amp; EXECUTION INTELLIGENCE</h2>"
        "<div class='grid'><section class='panel'><h3>GEX &amp; WALLS</h3><div class='kv'>"
        + pairs((("Call wall", "call_wall"), ("Put wall", "put_wall"),
                 ("Gamma flip", "gamma_flip"), ("Max pain", "max_pain"),
                 ("Regime", "gex_regime"), ("GEX score", "gex_score")))
        + "</div></section><section class='panel'><h3>WALL BREAK SCORE</h3><div class='kv'>"
        + pairs((("Grade", "wbs_grade"), ("Score", "wbs_score"),
                 ("Nearest wall", "wbs_wall_price"), ("Distance", "wbs_wall_distance_pct"),
                 ("Entry", "wbs_entry_guidance"), ("Stop", "wbs_stop_guidance")))
        + "</div></section><section class='panel'><h3>TRIGGER INTELLIGENCE</h3><div class='kv'>"
        + pairs((("Primary", "trigger_primary"), ("State", "trigger_confirmation_state"),
                 ("Quality", "trigger_quality"), ("Score", "trigger_score"),
                 ("Codes", "trigger_codes"), ("GO eligible", "trigger_go_eligible")))
        + "</div></section><section class='panel'><h3>TRADE CONTROL</h3><div class='kv'>"
        + pairs((("Direction", "direction"), ("R:R", "rr"),
                 ("Trigger level", "trigger_level"), ("Kill switch", "kill_switch_level"),
                 ("Trade state", "trade_state"), ("EIL action", "eil_action")))
        + "</div></section></div><h2 class='section-title'>LATEST TICKER NARRATIVE</h2>"
        f"<section class='panel narrative'>{html.escape(narrative)}</section>"
        f"<h2 class='section-title'>JUNIOR TRADER BRIEFING</h2>{cards}"
        "</main></body></html>"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, row: dict[str, Any]) -> None:
    fields = (*TRADE_BRIEF_FIELDS, "sovereign_vetoes", "eil_action")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)


def publish_complete_shadow_artifacts(
    result: TickerRunResult,
    shadow_root: str | Path,
    *,
    html_renderer: HtmlRenderer | None = None,
) -> Path:
    """Publish a complete artifact set or leave no final invocation directory."""
    if not result.shadow:
        raise ValueError("compatibility publisher is shadow-only")
    if result.analysis is None:
        raise ValueError("complete artifacts require validated analysis")

    root = Path(shadow_root).resolve()
    final_dir = root / result.run_id / result.ticker / result.invocation_id
    if final_dir.exists():
        raise FileExistsError(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{result.invocation_id}.", dir=final_dir.parent)
    )
    try:
        ticker_lower = result.ticker.lower()
        invocation = result.invocation_id
        raw_path = stage / f"raw_response_{ticker_lower}_{invocation}.txt"
        story_path = stage / f"raw_story_{ticker_lower}_{invocation}.txt"
        csv_path = stage / f"ticker_{ticker_lower}_trade_brief_{invocation}.csv"
        html_path = stage / f"ticker_{ticker_lower}_interpreter_{invocation}.html"
        sidecar_path = stage / f"{result.run_id}_{result.ticker}_interpreter.json"

        raw_path.write_text(result.analysis.raw_response, encoding="utf-8")
        story_path.write_text(result.analysis.raw_story, encoding="utf-8")
        brief = TradeBrief.from_row(result.analysis.trade_brief, result.ticker)
        row = brief.sovereign_row(
            effective_verdict=result.effective_verdict,
            veto_codes=result.veto_codes,
            eil_action=result.eil_action,
        )
        _write_csv(csv_path, row)
        renderer = html_renderer or _enhanced_html
        html_path.write_text(renderer(result, row), encoding="utf-8")
        sidecar_path.write_text(
            json.dumps(
                {
                    "schema_version": "automation_v2.sidecar.1",
                    "ticker": result.ticker,
                    "run_id": result.run_id,
                    "invocation_id": result.invocation_id,
                    "status": result.status.value,
                    "proposed_verdict": result.proposed_verdict,
                    "effective_verdict": result.effective_verdict,
                    "veto_codes": list(result.veto_codes),
                    "execution_permission": result.execution_permission,
                    "capital_permission": result.capital_permission,
                    "eil_action": result.eil_action,
                    "market_structure": {
                        field: row.get(field, "") for field in MARKET_STRUCTURE_FIELDS
                    },
                    "trade_brief": row,
                    "narrative": result.analysis.narrative,
                    "shadow": True,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        artifacts = sorted(
            path for path in stage.iterdir() if path.name != "artifact_manifest.json"
        )
        manifest_path = stage / "artifact_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "automation_v2.artifacts.1",
                    "complete": True,
                    "ticker": result.ticker,
                    "run_id": result.run_id,
                    "invocation_id": result.invocation_id,
                    "shadow": True,
                    "artifacts": [
                        {
                            "name": path.name,
                            "size_bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                        for path in artifacts
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(stage, final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

