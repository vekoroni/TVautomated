"""Macro and News Terminal reader functions — appended to engine"""
import json, csv
from pathlib import Path

def read_macro_context(path:str=None, ma_macro_dir:Path=None) -> str:
    if not path and ma_macro_dir:
        candidates = list(ma_macro_dir.glob("*.json")) + list(ma_macro_dir.glob("*.txt"))
        std = Path("C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/dropbox/macro/macro_intelligence_latest.json")
        if std.exists(): candidates.append(std)
        if not candidates: return ""
        path = str(max(candidates, key=lambda f: f.stat().st_mtime))
        print(f"  ✅ Macro context: {Path(path).name}")
    if not path: return ""
    try:
        p = Path(path)
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            key_fields = ["global_session_date","final_desk_verdict","asia_risk_tone",
                "global_us_equity_bias","global_us_options_bias","usd_transmission",
                "rates_transmission","commodity_transmission","volatility_transmission",
                "sector_rotation_map","index_bias_map","macro_merge_summary",
                "confidence_score","theme_deltas","event_guards","missing_data"]
            lines = ["MACRO INTELLIGENCE CONTEXT:"]
            for f in key_fields:
                if f in data:
                    val = data[f]
                    if isinstance(val, (dict,list)): val = json.dumps(val, separators=(',',':'))
                    lines.append(f"{f}: {str(val)[:200]}")
            return "\n".join(lines)
        return f"MACRO CONTEXT:\n{p.read_text(encoding='utf-8')[:1500]}"
    except Exception as e:
        print(f"  ⚠ Macro read: {e}"); return ""

def read_news_terminal_output(path:str=None, ticker:str=None, ma_news_dir:Path=None) -> str:
    if not path and ma_news_dir:
        candidates = list(ma_news_dir.glob("*.csv")) + list(ma_news_dir.glob("*.json")) + list(ma_news_dir.glob("*.txt"))
        if not candidates: return ""
        path = str(max(candidates, key=lambda f: f.stat().st_mtime))
        print(f"  ✅ News Terminal: {Path(path).name}")
    if not path: return ""
    try:
        p = Path(path)
        if p.suffix.lower() == ".csv":
            with open(p,"r",encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            if not rows: return ""
            if ticker:
                t = ticker.upper()
                filtered = [r for r in rows if t in str(r.get("ticker","")).upper()
                            or t in str(r.get("narrative","")).upper()]
                rows = filtered if filtered else rows[:5]
                if filtered: print(f"  ✅ News rows for {ticker}: {len(filtered)}")
            key_cols = ["ticker","narrative","event_category","event_status","directional_bias",
                "anis_total_score","fips_score","confidence_score","upload_priority",
                "forward_impact_thesis","key_catalyst","key_risk","confirmed_data",
                "assumptions","missing_data"]
            avail = [c for c in key_cols if rows and c in rows[0]]
            lines = [f"NEWS TERMINAL ({Path(path).name}):"]
            for row in rows[:6]:
                parts = [f"{c}={str(row.get(c,''))[:80]}" for c in avail if str(row.get(c,'')).strip() not in ('','nan','None')]
                lines.append(" | ".join(parts))
            return "\n".join(lines)
        return f"NEWS TERMINAL:\n{p.read_text(encoding='utf-8')[:1500]}"
    except Exception as e:
        print(f"  ⚠ News read: {e}"); return ""
