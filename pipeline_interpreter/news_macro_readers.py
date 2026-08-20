"""
news_macro_readers.py
Macro, enrichment delta, and news terminal reader functions — appended to engine.

Three sources:
  1. macro_intelligence_latest.json  — full macro contract (main authority)
  2. avshunter_macro_enrichment_delta.json — session narrative overlay and theme deltas
  3. News terminal output — CSV rows or pasted plain text brief
"""
import json, csv, os
from pathlib import Path
from datetime import datetime

# ── Standard paths ────────────────────────────────────────────────────────────
_DROPBOX_MACRO   = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro")
_MACRO_LATEST    = _DROPBOX_MACRO / "macro_intelligence_latest.json"
_ENRICHMENT_DELTA = _DROPBOX_MACRO / "avshunter_macro_enrichment_delta.json"

# Pasted newsroom brief is written here by /brief command
_BRIEF_PASTE_FILE = Path(__file__).resolve().parent / "MA_Inputs" / "news_terminal" / "newsroom_brief_latest.txt"


# ── 1. Main macro contract ────────────────────────────────────────────────────
def read_macro_context(path: str = None, ma_macro_dir: Path = None) -> str:
    """
    Read macro_intelligence_latest.json and return a compact summary string
    suitable for injection into the interpreter prompt.

    Priority order:
      1. Explicit path argument
      2. Latest file matching 'macro_intelligence_latest' in MA_Inputs/macro/
      3. Standard dropbox path (hardcoded fallback — always present)
    """
    resolved = _resolve_path(
        explicit=path,
        search_dir=ma_macro_dir,
        extensions=[".json", ".txt"],
        hardcoded=_MACRO_LATEST,
        filename_hint="macro_intelligence_latest",
    )
    if not resolved:
        return ""

    try:
        p = Path(resolved)
        print(f"  ✅ Macro context: {p.name}")
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            # Actual macro_contract_v1_0 field names used by the pipeline.
            # Extras fields are also walked for display purposes.
            key_fields = [
                "contract_version",
                "regime_state",
                "dir_bias",
                "vol_mode",
                "risk_on_off_switch",
                "macro_conviction",
                "macro_filter",
                "liquidity_pulse",
                "regime_drift_status",
                "vix_spot",
                "sector_tilt",
                "size_multiplier",
                "trigger_required",
                "trend_energy",
                "usd_state",
                "rates_impulse",
                "notes",
                "report_date",
                "as_of_utc",
                "rotation_override",
            ]
            extras = data.get("extras", {})
            extra_fields = [
                "execution_bias",
                "macro_notes",
                "predictability_score",
                "vix_contango",
                "vix_term_regime",
            ]
            lines = ["MACRO INTELLIGENCE CONTEXT:"]
            for f in key_fields:
                if f in data:
                    val = data[f]
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val, separators=(",", ":"))
                    lines.append(f"{f}: {str(val)[:300]}")
            # Append selected extras fields
            if isinstance(extras, dict):
                for f in extra_fields:
                    if f in extras:
                        val = extras[f]
                        if isinstance(val, (dict, list)):
                            val = json.dumps(val, separators=(",", ":"))
                        lines.append(f"extras.{f}: {str(val)[:300]}")
            return "\n".join(lines)
        return f"MACRO CONTEXT:\n{p.read_text(encoding='utf-8')[:2000]}"
    except Exception as e:
        print(f"  ⚠ Macro read error: {e}")
        return ""


# ── 2. Enrichment delta ───────────────────────────────────────────────────────
def read_enrichment_delta(path: str = None, ma_macro_dir: Path = None) -> str:
    """
    Read avshunter_macro_enrichment_delta.json and return a compact summary.

    The delta contains:
      - narrative_overlay: session summary and base macro alignment
      - theme_deltas: 8 active themes with tickers and bias
      - macro_json_merge_block: session-specific field overrides
      - macro_exposure_index_build: ticker-level exposure index

    This is the newsroom session layer — it sits ON TOP of the main macro
    contract and provides the intraday/session-specific colour.
    """
    resolved = _resolve_path(
        explicit=path,
        search_dir=ma_macro_dir,
        extensions=[".json"],
        hardcoded=_ENRICHMENT_DELTA,
        filename_hint="enrichment_delta",
    )
    if not resolved:
        return ""

    try:
        p = Path(resolved)
        print(f"  ✅ Enrichment delta: {p.name}")
        data = json.loads(p.read_text(encoding="utf-8"))

        lines = ["MACRO ENRICHMENT DELTA (session overlay):"]

        # Batch metadata
        lines.append(f"batch_id: {data.get('batch_id', 'UNKNOWN')}")
        lines.append(f"report_date: {data.get('report_date', 'UNKNOWN')}")
        lines.append(f"source: {data.get('source', 'UNKNOWN')}")

        # Narrative overlay
        no = data.get("narrative_overlay", {})
        if no.get("overlay_summary"):
            lines.append(f"session_narrative: {str(no['overlay_summary'])[:400]}")
        if no.get("base_macro_alignment"):
            alignment = no["base_macro_alignment"]
            if isinstance(alignment, list):
                alignment = " | ".join(str(a)[:100] for a in alignment[:3])
            lines.append(f"base_macro_alignment: {str(alignment)[:300]}")

        # Macro merge block — session field overrides
        mb = data.get("macro_json_merge_block", {})
        merge_keys = [
            "asia_risk_tone", "global_us_equity_bias", "global_us_options_bias",
            "usd_transmission", "rates_transmission", "commodity_transmission",
            "volatility_transmission", "sector_rotation_map", "index_bias_map",
        ]
        for k in merge_keys:
            if k in mb:
                val = mb[k]
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, separators=(",", ":"))
                lines.append(f"{k}: {str(val)[:200]}")

        # Theme deltas — the active session themes
        themes = data.get("theme_deltas", [])
        if themes:
            lines.append(f"\nACTIVE SESSION THEMES ({len(themes)}):")
            for t in themes[:8]:
                tid   = t.get("theme_id", "?")
                tname = t.get("theme_name", "")
                # schema v1.2 uses directional_pressure; older schemas used options_bias/macro_bias
                bias  = t.get("directional_pressure", t.get("options_bias", t.get("macro_bias", "")))
                # schema v1.2 uses beneficiary_universe; older schemas used primary_tickers/tickers
                ticks = t.get("beneficiary_universe", t.get("primary_tickers", t.get("tickers", [])))
                if isinstance(ticks, list):
                    ticks = ", ".join(ticks[:8])
                lines.append(f"  [{tid}] {tname} | bias={bias} | tickers={ticks}")

        # Event guards
        eg = data.get("event_guard_deltas", [])
        if eg:
            lines.append(f"\nEVENT GUARDS ({len(eg)}):")
            for g in eg[:4]:
                # schema v1.2 uses event_id/event_name; older schemas used guard_id/description
                gid   = g.get("event_id", g.get("guard_id", "?"))
                gdesc = g.get("event_name", g.get("description", ""))[:120]
                lines.append(f"  [{gid}] {gdesc}")

        return "\n".join(lines)

    except Exception as e:
        print(f"  ⚠ Enrichment delta read error: {e}")
        return ""


# ── 3. News terminal output ───────────────────────────────────────────────────
def read_news_terminal_output(
    path: str = None,
    ticker: str = None,
    ma_news_dir: Path = None,
) -> str:
    """
    Read news terminal output — accepts three formats:
      1. CSV file (standard news terminal export)
      2. Plain text brief (pasted via /brief command, saved as .txt)
      3. JSON narrative file

    When ticker is supplied, CSV rows are filtered for that ticker.
    The plain text brief is always returned in full (it already contains
    the full session narrative).
    """
    # Check for pasted brief first — most recent and most complete
    if _BRIEF_PASTE_FILE.exists():
        try:
            brief_text = _BRIEF_PASTE_FILE.read_text(encoding="utf-8").strip()
            if brief_text:
                print(f"  ✅ Newsroom brief (pasted): {_BRIEF_PASTE_FILE.name}")
                # Filter for ticker if requested — scan for ticker mentions
                if ticker:
                    ticker_upper = ticker.upper()
                    lines = brief_text.split("\n")
                    relevant = [
                        l for l in lines
                        if ticker_upper in l.upper()
                        or any(
                            ticker_upper in str(v).upper()
                            for v in [l]
                        )
                    ]
                    if relevant:
                        header = f"NEWS BRIEF — {ticker} MENTIONS:\n"
                        return header + "\n".join(relevant[:20])
                return f"NEWSROOM BRIEF (session):\n{brief_text[:3000]}"
        except Exception as e:
            print(f"  ⚠ Brief paste read: {e}")

    resolved = _resolve_path(
        explicit=path,
        search_dir=ma_news_dir,
        extensions=[".csv", ".json", ".txt"],
        hardcoded=None,
    )
    if not resolved:
        return ""

    try:
        p = Path(resolved)
        print(f"  ✅ News Terminal: {p.name}")

        if p.suffix.lower() == ".csv":
            with open(p, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            if not rows:
                return ""
            if ticker:
                t = ticker.upper()
                filtered = [
                    r for r in rows
                    if t in str(r.get("ticker", "")).upper()
                    or t in str(r.get("narrative", "")).upper()
                ]
                rows = filtered if filtered else rows[:5]
                if filtered:
                    print(f"  ✅ News rows for {ticker}: {len(filtered)}")

            key_cols = [
                "ticker", "narrative", "event_category", "event_status",
                "directional_bias", "anis_total_score", "fips_score",
                "confidence_score", "upload_priority",
                "forward_impact_thesis", "key_catalyst", "key_risk",
                "confirmed_data", "assumptions", "missing_data",
            ]
            avail = [c for c in key_cols if rows and c in rows[0]]
            lines = [f"NEWS TERMINAL ({p.name}):"]
            for row in rows[:6]:
                parts = [
                    f"{c}={str(row.get(c, ''))[:80]}"
                    for c in avail
                    if str(row.get(c, "")).strip() not in ("", "nan", "None")
                ]
                lines.append(" | ".join(parts))
            return "\n".join(lines)

        # Plain text or JSON
        return f"NEWS TERMINAL:\n{p.read_text(encoding='utf-8')[:2000]}"

    except Exception as e:
        print(f"  ⚠ News terminal read error: {e}")
        return ""


# ── 4. Combined context builder ───────────────────────────────────────────────
def read_all_news_macro_context(ticker: str = None, ma_macro_dir: Path = None, ma_news_dir: Path = None) -> str:
    """
    Build the complete macro + enrichment delta + news context block
    for injection into a single prompt.

    Called by build_single_ticker_prompt and build_triage_prompt in the engine.
    """
    parts = []

    macro = read_macro_context(ma_macro_dir=ma_macro_dir)
    if macro:
        parts.append(macro)

    delta = read_enrichment_delta(ma_macro_dir=ma_macro_dir)
    if delta:
        parts.append(delta)

    news = read_news_terminal_output(ticker=ticker, ma_news_dir=ma_news_dir)
    if news:
        parts.append(news)

    if not parts:
        return "MACRO_DATA_MISSING | NEWS_DATA_MISSING — no context files found."

    return "\n\n".join(parts)


# ── Internal helper ───────────────────────────────────────────────────────────
def _resolve_path(
    explicit: str,
    search_dir: Path,
    extensions: list,
    hardcoded: Path,
    filename_hint: str = None,
) -> str:
    """Resolve a file path from explicit arg → search_dir → hardcoded fallback."""
    if explicit and Path(explicit).exists():
        return explicit

    if search_dir and Path(search_dir).exists():
        candidates = []
        for ext in extensions:
            candidates.extend(Path(search_dir).glob(f"*{ext}"))
        if filename_hint:
            candidates = [c for c in candidates if filename_hint in c.name.lower()] or candidates
        if candidates:
            return str(max(candidates, key=lambda f: f.stat().st_mtime))

    if hardcoded and Path(hardcoded).exists():
        return str(hardcoded)

    return None


# ── Brief paste writer — called by /brief command ─────────────────────────────
def save_pasted_brief(text: str) -> Path:
    """
    Save a pasted newsroom brief to the standard location so the interpreter
    can read it automatically on the next /triage or /ticker call.
    """
    _BRIEF_PASTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Prepend timestamp so the interpreter knows when it was pasted
    stamped = f"[Pasted: {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n{text.strip()}"
    _BRIEF_PASTE_FILE.write_text(stamped, encoding="utf-8")
    print(f"  ✅ Brief saved → {_BRIEF_PASTE_FILE}")
    return _BRIEF_PASTE_FILE
