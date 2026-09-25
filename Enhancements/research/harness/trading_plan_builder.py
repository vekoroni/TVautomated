#!/usr/bin/env python
"""Trading plan for an evening run: every candidate trade with valuation, break-even probability, macro overlay
and a morning checklist. Read-only against the completed run. Writes only under Enhancements/research/output/.

Selection (research rule, EXPLORATORY_NO_AUTHORITY):
  Tier A  spread <= 15% of mid, reachable payoff >= 2 x |FLAT| loss, break-even p* <= 0.40
  Tier B  spread <= 15%, reachable >= 2 x |FLAT|, p* > 0.40
  Tier C  probability-free grid EV > 0 but outside A/B
Macro is a displayed overlay (spec §14: display-only, never a gate). Sizing is HUMAN DETERMINED; the packet's
size modifiers are shown as advisory text only.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merged_5_7_8_scenario_harness import value_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260925_061649"
R = "payoff_favourable_reachable_base_net_return_fraction"
F = "payoff_flat_base_net_return_fraction"
I = "payoff_adverse_invalidation_base_net_return_fraction"
G = "ev_grid_net_return_fraction"
SECTOR_ETF = {"Energy": "XLE", "Information Technology": "XLK", "Communication Services": "XLC", "Utilities": "XLU",
              "Real Estate": "XLRE", "Financials": "XLF", "Materials": "XLB", "Consumer Staples": "XLP",
              "Consumer Discretionary": "XLY", "Industrials": "XLI", "Health Care": "XLV"}


def first(row, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "null"):
            return v
    return None


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def macro_overlay(row, side, sector, packet, snap):
    preferred = set(packet.get("preferred_sectors") or [])
    avoid = set(packet.get("avoid_sectors") or [])
    ticker = str(row.get("ticker") or "").upper()
    if ticker in {"SPY", "QQQ", "IWM", "DIA", "RSP"}:
        if side == "CALL":
            return "AGAINST", "Broad index call: packet rule 'NO broad QQQ/SPY/IWM calls without rate gate reversal (10Y below 5.05%)'"
        return ("ALIGNED" if ticker == "IWM" else "NEUTRAL"), ("IWM puts armed on relative-weakness confirmation" if ticker == "IWM" else "SPY/QQQ puts need VIX 16-18 confirmation plus breadth failure")
    etf_sector = {v: k for k, v in SECTOR_ETF.items()}.get(ticker)
    if etf_sector:
        sector = etf_sector  # a sector ETF is judged by its sector
    if side == "CALL":
        align = "ALIGNED" if sector in preferred else "AGAINST" if sector in avoid else "NEUTRAL"
        note = ("Calls: selective only, trigger confirmation and individual RS required (breadth Z -2.31); "
                "no broad index calls until 10Y < 5.05%")
        if sector in avoid:
            note = "Call in a macro-avoid sector (rate-sensitive / cyclical pressure): " + note
    else:
        align = "ALIGNED" if sector in avoid else "AGAINST" if sector in preferred else "NEUTRAL"
        note = ("Puts: gate ARMED_PRIORITY_WATCH, not activated; full activation needs VIX > 16 on CBOE close "
                "and breadth Z < -2.50; rate-sensitive sectors (XLU/XLRE/XLP/XLF) are the armed set")
        if sector in preferred:
            note = "Put against the macro-preferred (tech-led) leadership: " + note
    return align, note


def main() -> int:
    base = ROOT / "data/output/runs" / RUN
    d = json.loads((base / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("rows") or d.get("opportunities") or d.get("items") or d.get("book"))
    packet = json.loads((base / "macro_quant_packet.json").read_text(encoding="utf-8"))
    snap = json.loads((base / "macro_snapshot.json").read_text(encoding="utf-8"))
    routing = (snap.get("extras") or {}).get("horizon_routing") or snap.get("horizon_routing") or {}
    session = date(int(RUN[:4]), int(RUN[4:6]), int(RUN[6:8]))

    plan = []
    for r in rows:
        v = value_row(r, 0.04, "horizon")
        if v["applicability"] != "OK":
            continue
        reach, flat, inval, ev = v[R], v[F], v[I], v[G]
        p_star = (-inval / (reach - inval)) if reach > inval else 1.0
        asym = reach / abs(flat) if flat else None
        spread = v["spread_fraction_mid"]
        if spread <= 0.15 and asym is not None and asym >= 2.0:
            tier = "A" if p_star <= 0.40 else "B"
        elif ev > 0:
            tier = "C"
        else:
            continue
        side = v["direction"]
        sector = str(first(r, "gics_sector_norm", "gics_sector", "sector") or "")
        bucket = str(r.get("time_horizon") or "").lower()
        align, mnote = macro_overlay(r, side, sector, packet, snap)
        hr = routing.get(bucket, {})
        expiry = str(first(r, "expiry", "contract_expiry") or "")
        dte = fnum(first(r, "contract_dte", "dte"))
        exit_buffer_sessions = 5
        last_exit = None
        try:
            exp_d = datetime.strptime(expiry[:10], "%Y-%m-%d").date()
            last_exit = min(session + timedelta(days=28), exp_d - timedelta(days=7)).isoformat()
        except ValueError:
            pass
        cat = first(r, "catalyst_type")
        review = []
        _spot, _tgt, _inv = fnum(r.get("underlying_price")), fnum(first(r, "structural_target", "target_price")), fnum(r.get("invalidation_price"))
        if _spot and _tgt is not None and _inv is not None and (abs(_tgt / _spot - 1) < 0.01 or abs(_inv / _spot - 1) < 0.01):
            review.append("DEGENERATE_GEOMETRY: target or invalidation within 1% of spot; p* not meaningful")
        if flat > 0:
            review.append("STOCK_LIKE: positive at flat, deep ITM; compare with shares")
        if reach > 3.0:
            review.append("OUTLIER: reachable > 300%, verify forecast vol vs IV before trusting")
        if v["iv_minus_forecast_vol"] < -0.15:
            review.append("FORECAST_ABOVE_IV: > 15 pts, reachable payoff is forecast-driven (ALG-10 unvalidated)")
        if str(cat or "").upper() == "EARNINGS" and str(first(r, "catalyst_inside_dte") or "").lower() in ("true", "1", "yes"):
            review.append("EARNINGS_INSIDE_DTE: event variance not separated (note 04 §4)")
        plan.append({
            "review_flag": "; ".join(review),
            "tier": tier, "ticker": r["ticker"], "direction": side, "sector": sector, "sector_etf": SECTOR_ETF.get(sector, ""),
            "horizon_bucket": bucket, "hold_sessions": v["hold_sessions"],
            "contract": first(r, "selected_contract_symbol"), "strike": fnum(r.get("strike")), "expiry": expiry, "dte": dte,
            "spot_eod": fnum(r.get("underlying_price")), "target": fnum(first(r, "structural_target", "target_price")),
            "invalidation": fnum(r.get("invalidation_price")), "invalidation_source": first(r, "invalidation_source"),
            "trigger_primary": first(r, "trigger_primary"), "trigger_price": fnum(r.get("trigger_price")),
            "eod_bid": fnum(r.get("contract_bid")), "eod_ask": fnum(r.get("contract_ask")), "spread_pct_of_mid": round(spread * 100, 1),
            "contract_iv": fnum(r.get("contract_iv")), "forecast_vol": fnum(r.get("garch_forecast_vol")),
            "iv_minus_forecast_pts": round(v["iv_minus_forecast_vol"] * 100, 1),
            "reachable_move_pct": round(v["vol_budget_move_fraction"] * 100, 1),
            "payoff_reachable_pct": round(reach * 100, 1), "payoff_flat_pct": round(flat * 100, 1),
            "payoff_invalidation_pct": round(inval * 100, 1), "payoff_structural_pct": round(v["payoff_favourable_structural_base_net_return_fraction"] * 100, 1),
            "asymmetry_reach_over_flat": round(asym, 2) if asym else None, "breakeven_p_target": round(p_star, 2),
            "grid_ev_pct": round(ev * 100, 1), "p_positive_exit_grid": round(v["p_positive_net_exit_grid"], 2),
            "legacy_p_target": fnum(r.get("layer2__adjusted_prob_target_hit")),
            "legacy_clears_breakeven": (fnum(r.get("layer2__adjusted_prob_target_hit")) or 0) >= p_star,
            "eil_verdict": first(r, "eil_v3_verdict"), "lab_verdict": r.get("lab_verdict"),
            "execution_viability": first(r, "execution_viability_state"), "hidden_state": first(r, "hidden_state_label"),
            "phase": first(r, "phase"), "catalyst": cat, "catalyst_date": first(r, "catalyst_date"),
            "catalyst_inside_dte": first(r, "catalyst_inside_dte"),
            "macro_regime": packet.get("macro_regime_sub_state"), "macro_alignment": align, "macro_note": mnote,
            "macro_horizon_action": hr.get("action"), "macro_size_modifier_advisory": hr.get("size_multiplier"),
            "macro_row_pressure": first(r, "macro_directional_pressure"), "macro_row_themes": first(r, "macro_active_themes"),
            "last_exit_session_max": last_exit, "planned_exit_policy": f"time-stop Day {v['hold_sessions']} if unresolved; target / invalidation first",
            "morning_checklist": ("1 requote: two-sided, spread <= 15% of mid, provider timestamp present; "
                                  "2 spot vs trigger: " + ("above" if side == "CALL" else "below") + " trigger_price; "
                                  "3 invalidation still on the correct side; 4 macro overlay read; 5 size HUMAN DETERMINED"),
            "sizing": "HUMAN DETERMINED", "state": "EXPLORATORY_NO_AUTHORITY",
        })

    order = {"A": 0, "B": 1, "C": 2}
    plan.sort(key=lambda x: (order[x["tier"]], x["breakeven_p_target"], -(x["grid_ev_pct"])))
    od = ROOT / "Enhancements/research/output" / RUN
    od.mkdir(parents=True, exist_ok=True)
    csv_path = od / f"trading_plan_{RUN}_v2.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)

    # markdown plan
    tiers = Counter(p["tier"] for p in plan)
    L = []
    L.append(f"# Trading plan — evening run {RUN} (for the morning session of {session.isoformat()} US)")
    L.append("")
    L.append("**State:** EXPLORATORY_NO_AUTHORITY · research plan built read-only from the completed evening book · sizing HUMAN DETERMINED · nothing here alters the pipeline or the run book")
    L.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')} · **CSV:** `{csv_path.name}`")
    L.append("")
    L.append("## 1. Macro overlay (display-only, spec §14)")
    L.append("")
    L.append(f"- Regime **{packet.get('macro_regime_sub_state')}** (drift {packet.get('regime_drift_status')}); conviction {packet.get('macro_conviction_score')}; risk-on/off score {packet.get('risk_on_off_score')}; filter **{snap.get('macro_filter')}** (size modifier only, direction does not abstain)")
    L.append(f"- Rates {packet.get('rates_impulse')}, USD {packet.get('usd_state')}, credit {packet.get('credit_state')}, liquidity {packet.get('liquidity_pulse')}, VIX {packet.get('vix_level')} ({packet.get('vix_regime_label')}), dealer gamma {packet.get('dealer_gamma_state')} (GEX source unavailable in the packet)")
    L.append(f"- Preferred sectors: {', '.join(packet.get('preferred_sectors') or [])}. Avoid: {', '.join(packet.get('avoid_sectors') or [])}. Rotation: {packet.get('sector_rotation_state')}")
    for b in ("1_5d", "6_10d", "11_20d"):
        h = routing.get(b, {})
        L.append(f"- {b}: {h.get('action')} · bias {h.get('bias')} · advisory size modifier {h.get('size_multiplier')}")
    L.append(f"- Calls rule: {(snap.get('extras') or {}).get('execution_rules', {}).get('calls', '')}")
    L.append(f"- Puts rule: {(snap.get('extras') or {}).get('execution_rules', {}).get('puts', '')}")
    L.append(f"- Macro notes: {str((snap.get('extras') or {}).get('macro_notes', ''))}")
    L.append("")
    L.append("## 2. Candidate trades")
    L.append("")
    L.append(f"Tier A (asymmetric, executable, break-even p ≤ 0.40): **{tiers['A']}** · Tier B (asymmetric, executable, p* > 0.40): **{tiers['B']}** · Tier C (grid EV > 0 outside A/B): **{tiers['C']}**")
    L.append("")
    L.append("Every row is MANUAL_REVIEW with REQUOTE_REQUIRED in the evening book; GO/GO_LIMIT can only arise from the morning validation. EOD quotes are wide; the morning requote decides executability.")
    L.append("")
    for t in ("A", "B", "C"):
        sub = [p for p in plan if p["tier"] == t]
        if not sub:
            continue
        L.append(f"### Tier {t}")
        L.append("")
        L.append("| Ticker | Dir | Sector | Contract | DTE | Spot | Target | Invalidation | Spread | Reach % | Flat % | Inval % | p* | Grid EV % | Legacy p clears p* | EIL | Macro | Catalyst | Review |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p in sub:
            L.append(f"| {p['ticker']} | {p['direction']} | {p['sector'] or '—'} | {p['contract']} | {p['dte']:.0f} | {p['spot_eod']:.2f} | {p['target']:.2f} | {p['invalidation']:.2f} | {p['spread_pct_of_mid']}% | {p['payoff_reachable_pct']:+.0f} | {p['payoff_flat_pct']:+.0f} | {p['payoff_invalidation_pct']:+.0f} | {p['breakeven_p_target']:.2f} | {p['grid_ev_pct']:+.1f} | {'yes' if p['legacy_clears_breakeven'] else 'no'} | {p['eil_verdict'] or '—'} | {p['macro_alignment']} | {p['catalyst'] or '—'} | {p['review_flag'] or '—'} |")
        L.append("")
    L.append("## 3. How to read a row")
    L.append("")
    L.append("- **Reach / Flat / Inval**: net return on premium at the exit session if spot reaches the vol-budget target (1.5σ), stays flat, or hits the invalidation; entry at ask, exit at modelled bid (ALG-04, friction_model_v1). Scenario values, not forecasts.")
    L.append("- **p\\***: the probability of target-before-invalidation you must believe for the trade to break even. Below 0.40 is Tier A. The pipeline's legacy probability is shown beside it; it is uncalibrated.")
    L.append("- **Macro**: ALIGNED / NEUTRAL / AGAINST by sector versus the packet's preferred and avoid lists, plus the calls/puts rule. It is an overlay for the reviewer, never a kill.")
    L.append("- **Morning checklist** (in the CSV): requote two-sided and ≤ 15% of mid with a provider timestamp; spot on the right side of the trigger; invalidation intact; macro overlay read; size human determined.")
    L.append("- **Exit policy**: target or invalidation first; otherwise time-stop at the horizon hold (Day 5 or Day 10); hard last exit at Day 20 or expiry minus the exit buffer, whichever is earlier.")
    L.append("")
    L.append("## 4. What this plan is not")
    L.append("")
    L.append("Not a pipeline output, not a capital allocation, not a validated probability. The vol forecast is unvalidated (ALG-10 pending) and the reachable payoff scales with it; a 15% forecast error moves the Tier A count by roughly a factor of two.")
    (od / f"TRADING_PLAN_{RUN}.md").write_text("\n".join(L), encoding="utf-8")
    print(json.dumps({"run": RUN, "rows_valued_in_plan": len(plan), "tiers": dict(tiers),
                      "by_direction": dict(Counter(p["direction"] for p in plan)),
                      "macro_alignment": dict(Counter(f"{p['tier']}:{p['macro_alignment']}" for p in plan)),
                      "csv": str(csv_path), "md": str(od / f"TRADING_PLAN_{RUN}.md")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
