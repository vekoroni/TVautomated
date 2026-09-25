#!/usr/bin/env python
"""Render the trading-plan CSV as a readable Markdown document (compact tables). Read-only."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260925_061649"
SUFFIX = ("_" + sys.argv[2]) if len(sys.argv) > 2 else ""
od = ROOT / "Enhancements/research/output" / RUN
rows = list(csv.DictReader((od / f"trading_plan_{RUN}_v2.csv").open(encoding="utf-8")))
base = ROOT / "data/output/runs" / RUN
packet = json.loads((base / "macro_quant_packet.json").read_text(encoding="utf-8"))
snap = json.loads((base / "macro_snapshot.json").read_text(encoding="utf-8"))
ex = snap.get("extras") or {}
routing = ex.get("horizon_routing") or {}
rules = ex.get("execution_rules") or {}
session = f"{RUN[:4]}-{RUN[4:6]}-{RUN[6:8]}"


def f(v, d=1, sign=False):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def short_flag(s: str) -> str:
    return "; ".join(p.split(":")[0] for p in s.split("; ") if p) if s else "—"


L = []
L.append(f"# Trading plan — run {RUN}{SUFFIX.replace(chr(95), chr(32))} · US session of {session}")
L.append("")
L.append("Research plan built read-only from the completed evening book. State EXPLORATORY_NO_AUTHORITY. Sizing HUMAN DETERMINED. Nothing here alters the pipeline or the run book.")
L.append(f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')} · source CSV `trading_plan_{RUN}_v2.csv`")
L.append("")
tiers = Counter(r["tier"] for r in rows)
L.append("## 1. Summary")
L.append("")
L.append("| Item | Value |")
L.append("|---|---|")
L.append(f"| Rows in the evening book | 1,549 (all MANUAL_REVIEW or BLOCKED; GO verdicts arise only at morning validation) |")
L.append(f"| Candidate trades listed | {len(rows)} ({Counter(r['direction'] for r in rows)['CALL']} CALL, {Counter(r['direction'] for r in rows)['PUT']} PUT) |")
L.append(f"| Tier A — asymmetric, executable, break-even p ≤ 0.40 | **{tiers['A']}** |")
L.append(f"| Tier B — asymmetric, executable, break-even p > 0.40 | {tiers['B']} |")
L.append(f"| Tier C — positive grid EV outside A/B | {tiers['C']} |")
L.append(f"| Tier A macro alignment | {Counter(r['macro_alignment'] for r in rows if r['tier']=='A')['ALIGNED']} aligned · {Counter(r['macro_alignment'] for r in rows if r['tier']=='A')['NEUTRAL']} neutral · {Counter(r['macro_alignment'] for r in rows if r['tier']=='A')['AGAINST']} against |")
L.append(f"| Tier A rows with a review flag | {sum(1 for r in rows if r['tier']=='A' and r['review_flag'])} |")
L.append("")
L.append("## 2. Macro overlay (display-only; never a gate)")
L.append("")
L.append("| Factor | Tonight's reading | What it means for the plan |")
L.append("|---|---|---|")
L.append(f"| Regime | {packet.get('macro_regime_sub_state')} · drift {packet.get('regime_drift_status')} · conviction {packet.get('macro_conviction_score')} | Selective, trigger-confirmed entries only |")
L.append(f"| Filter | {snap.get('macro_filter')} (Fung-Hsieh, accuracy 55.6%) | Size modifier 0.70× on all positions; direction does not abstain; no ticker is blocked |")
L.append(f"| Rates | 10Y 5.11%, 30Y 5.40%, both above deterioration gates; impulse {packet.get('rates_impulse')} | No broad QQQ/SPY/IWM calls until 10Y < 5.05%; rate-sensitive puts armed |")
L.append(f"| Breadth | RSP−SPY −5.63%, Z −2.31, narrowing | Individual relative-strength confirmation required before any call |")
L.append(f"| Volatility | VIX {round(float(packet.get('vix_level') or 0),2)} ({packet.get('vix_regime_label')}), contango, CBOE/yfinance conflict, VVIX escalating | Treat as ELEVATED_CAUTION; puts activate only on VIX > 16 CBOE close |")
L.append(f"| Credit / liquidity | HY OAS 2.73 benign · liquidity {packet.get('liquidity_pulse')} (RRP exhausted, TGA building) | No systemic stress; medium-term exposure reduced |")
L.append(f"| Dealer gamma | {packet.get('dealer_gamma_state')} · GEX source unavailable | No dealer-flow confirmation available tonight |")
L.append(f"| Sectors | Preferred: {', '.join(packet.get('preferred_sectors') or [])} · Avoid: {', '.join(packet.get('avoid_sectors') or [])} · rotation {packet.get('sector_rotation_state')} | Drives the ALIGNED / NEUTRAL / AGAINST column below |")
for b in ("1_5d", "6_10d", "11_20d"):
    h = routing.get(b, {})
    L.append(f"| Horizon {b} | {h.get('action')} · bias {h.get('bias')} | Advisory size modifier {h.get('size_multiplier')} |")
L.append(f"| Calls rule | {rules.get('calls','')} | |")
L.append(f"| Puts rule | {rules.get('puts','')} | |")
L.append("")
L.append("## 3. Candidate trades")
L.append("")
L.append("Columns: **Contract (DTE)** is the pipeline's selected contract · **Spot → Target / Inval** are end-of-day spot, structural target and invalidation · **Spread** is the EOD spread as % of mid · **Reach / Flat / Inval** are net returns on premium at the exit session if spot reaches the vol-budget target, stays flat, or hits the invalidation (entry at ask, exit at modelled bid) · **p\\*** is the probability of target-before-invalidation you must believe to break even · **Legacy p** is the pipeline's uncalibrated probability and whether it clears p\\* · **Macro** is the overlay · **EIL** is the pipeline's edge verdict · **Flag** is a review flag explained in section 4.")
L.append("")
for t, title in (("A", "Tier A — asymmetric, executable, break-even p ≤ 0.40"), ("B", "Tier B — asymmetric, executable, break-even p > 0.40"), ("C", "Tier C — positive grid EV, outside A/B")):
    sub = [r for r in rows if r["tier"] == t]
    if not sub:
        continue
    L.append(f"### {title} ({len(sub)})")
    L.append("")
    L.append("| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\\* | Legacy p | Macro | EIL | Flag |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(sub, 1):
        legacy = f"{f(r['legacy_p_target'],2)} {'✓' if r['legacy_clears_breakeven']=='True' else '✗'}"
        L.append(f"| {i} | **{r['ticker']}** | {r['direction']} | {r['sector'] or '—'} | {r['contract']} ({f(r['dte'],0)}) | {f(r['spot_eod'],2)} → {f(r['target'],2)} / {f(r['invalidation'],2)} | {r['spread_pct_of_mid']}% | {f(r['payoff_reachable_pct'],0,True)} / {f(r['payoff_flat_pct'],0,True)} / {f(r['payoff_invalidation_pct'],0,True)} | {f(r['breakeven_p_target'],2)} | {legacy} | {r['macro_alignment']} | {(r['eil_verdict'] or '—').replace('EXECUTE_WITH_CAUTION','EXEC_CAUTION')} | {short_flag(r['review_flag'])} |")
    L.append("")
flagged = [r for r in rows if r["review_flag"]]
L.append("## 4. Review flags")
L.append("")
L.append("| Flag | Meaning | What to check | Rows |")
L.append("|---|---|---|---|")
defs = {
    "DEGENERATE_GEOMETRY": ("Target or invalidation within 1% of spot", "The thesis geometry is not a trade; p* and the invalidation payoff are not meaningful until the Thesis owner publishes a real level"),
    "OUTLIER": ("Reachable payoff above 300%", "Forecast vol versus contract IV; the number is forecast-driven and ALG-10 is unvalidated"),
    "STOCK_LIKE": ("Positive return even if spot stays flat: deep in the money", "Compare with holding the shares; the option is a stock substitute, not convexity"),
    "FORECAST_ABOVE_IV": ("Forecast vol more than 15 points above IV", "If the forecast is biased high, the reachable payoff shrinks first"),
    "EARNINGS_INSIDE_DTE": ("Earnings date inside the contract's life", "Event variance is not separated from the IV (method note 04 §4)"),
}
for key, (meaning, check) in defs.items():
    names = [r["ticker"] for r in flagged if key in r["review_flag"]]
    if names:
        L.append(f"| {key} | {meaning} | {check} | {', '.join(names)} |")
L.append("")
L.append("## 5. Macro alignment of the Tier A list")
L.append("")
L.append("| Alignment | Tickers | Reading |")
L.append("|---|---|---|")
for al, reading in (("ALIGNED", "Sector on the preferred list for a call, or on the avoid list for a put"),
                    ("NEUTRAL", "Sector on neither list; the calls/puts rule still applies"),
                    ("AGAINST", "Call in an avoid sector, put against tech leadership, or a broad index call the packet forbids")):
    names = [f"{r['ticker']} {r['direction'][0]}" for r in rows if r["tier"] == "A" and r["macro_alignment"] == al]
    L.append(f"| {al} | {', '.join(names) or '—'} | {reading} |")
L.append("")
L.append("## 6. Morning checklist (every row, before any order)")
L.append("")
L.append("| Step | Check | Pass condition |")
L.append("|---|---|---|")
L.append("| 1 | Requote the selected contract | Two-sided, provider timestamp present, spread ≤ 15% of mid |")
L.append("| 2 | Spot versus trigger | CALL: spot above trigger_price · PUT: spot below trigger_price (trigger_primary in the CSV) |")
L.append("| 3 | Invalidation | Still on the correct side of spot; if crossed overnight the thesis is INVALIDATED, not re-entered |")
L.append("| 4 | Macro overlay | Read the alignment and rule; AGAINST is information for the reviewer, not a kill |")
L.append("| 5 | Review flag | Resolve any flag in section 4 before sizing |")
L.append("| 6 | Exit policy | Target or invalidation first; time-stop at the horizon hold (Day 5 or Day 10); hard last exit at Day 20 or expiry minus buffer |")
L.append("| 7 | Size | HUMAN DETERMINED; the packet's 0.63 / 0.56 / 0.49 modifiers are advisory text only |")
L.append("")
L.append("## 7. What this plan is not")
L.append("")
L.append("| Limit | Why it matters |")
L.append("|---|---|")
L.append("| Not a pipeline output | Built from the book by a research harness; the pipeline's own morning validation still runs unchanged |")
L.append("| Not a validated probability | p\\* is what you must believe; the legacy probability shown beside it is uncalibrated |")
L.append("| Not a validated forecast | Reachable payoffs scale with the unvalidated vol forecast; a 15% error moves the Tier A count by roughly 2× |")
L.append("| Not a fill | EOD quotes are wide; the morning requote decides executability |")
L.append("| Not a size | Capital and Kelly are outside AVSHUNTER by design |")
(od / f"TRADING_PLAN_{RUN}{SUFFIX}_tables.md").write_text("\n".join(L), encoding="utf-8")
print("written", od / f"TRADING_PLAN_{RUN}{SUFFIX}_tables.md", "rows", len(rows))
