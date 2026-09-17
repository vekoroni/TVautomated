"""Expression loss diagnostic (read-only): why did the recorded option contracts lose money?

For every MARKED expression (c12-expression-v1.1.0) it decomposes the result into:
  - spread cost      entry at ask vs mid, exit at bid vs mid
  - delta move       entry delta x direction-signed underlying move (chain underlying prices)
  - residual         mid change not explained by delta (theta / vega / gamma / stale quotes)
and records liquidity at entry and exit (volume, open interest, quote age), contract shape
(DTE, delta, moneyness) and a selection counterfactual: every same-side contract of the
same ticker quoted on both the entry and exit sessions, bought at ask and sold at bid.

Writes a JSON + Markdown summary to Enhancements/expression_forensics/. No writes elsewhere.

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\expression_loss_diagnostic.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import statistics as st

REPO = Path(__file__).resolve().parents[2]
SCORING = REPO / "data" / "canonical" / "outcome_scoring.sqlite"
CHAINS = REPO / "data" / "phantom" / "phantom_history.db"
OUT = Path(__file__).resolve().parent
VERSION = "c12-expression-v1.1.0"

COLUMNS = ("option_symbol", "side", "strike", "expiration_ts", "dte", "bid", "ask", "mid", "volume",
           "open_interest", "iv", "delta", "theta", "underlying_price", "updated_ts", "greeks_quality")


def quote_rows(ph, ticker, day, side=None):
    sql = f"SELECT {', '.join(COLUMNS)} FROM chain_snapshots WHERE ticker = ? AND quote_date = ?"
    args = [ticker, day]
    if side:
        sql += " AND side = ?"
        args.append(side)
    return {r[0]: dict(zip(COLUMNS, r)) for r in ph.execute(sql, args)}


def mid(q):
    if q.get("bid") is not None and q.get("ask") is not None and q["ask"] > 0:
        return (q["bid"] + q["ask"]) / 2
    return q.get("mid")


def bucket(value, edges, labels):
    if value is None:
        return "MISSING"
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def pct(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(q * len(values)))]


def summarise(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": st.fmean(values), "median": st.median(values),
            "p10": pct(values, 0.10), "p90": pct(values, 0.90)}


def main() -> None:
    sc = sqlite3.connect(f"file:{SCORING.as_posix()}?mode=ro", uri=True)
    ph = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    rows = sc.execute(
        """SELECT e.prediction_id, p.ticker, p.direction, p.evidence_session, e.exit_session, e.contract_symbol,
                  e.entry_ask, e.entry_source, e.exit_bid, e.return_on_premium, e.underlying_state, e.exit_reason,
                  (SELECT labels_json FROM prediction_sightings s WHERE s.prediction_id = p.prediction_id
                   ORDER BY s.book_mtime_utc LIMIT 1)
           FROM expression_outcomes e JOIN prediction_records p USING (prediction_id)
           WHERE e.expression_version = ? AND e.state = 'MARKED' AND p.provenance_class = 'RECORDED_AT_RUN'""",
        (VERSION,)).fetchall()

    records = []
    chain_cache = {}
    for (pid, ticker, direction, evidence, exit_day, symbol, entry_ask, entry_source, exit_bid, rop,
         u_state, exit_reason, labels_json) in rows:
        side = "call" if symbol[-9] == "C" else "put"
        sign = 1 if direction == "BULL" else -1
        for day in (evidence, exit_day):
            key = (ticker, day, side)
            if key not in chain_cache:
                chain_cache[key] = quote_rows(ph, ticker, day, side)
        entry_chain, exit_chain = chain_cache[(ticker, evidence, side)], chain_cache[(ticker, exit_day, side)]
        eq, xq = entry_chain.get(symbol), exit_chain.get(symbol)
        rec = {"prediction_id": pid, "ticker": ticker, "direction": direction, "side": side,
               "entry_source": entry_source, "underlying_state": u_state, "exit_reason": exit_reason,
               "return_on_premium": rop, "tier": json.loads(labels_json or "{}").get("tier"),
               "entry_quote_found": eq is not None}
        if eq:
            m_in = mid(eq)
            rec.update({
                "entry_spread_pct_of_ask": (eq["ask"] - eq["bid"]) / eq["ask"] if eq["ask"] else None,
                "entry_volume": eq["volume"], "entry_open_interest": eq["open_interest"],
                "entry_dte": eq["dte"], "entry_abs_delta": abs(eq["delta"]) if eq["delta"] is not None else None,
                "entry_iv": eq["iv"], "greeks_quality": eq["greeks_quality"],
                "moneyness_pct": (sign * (eq["underlying_price"] - eq["strike"]) / eq["underlying_price"]
                                  if eq["underlying_price"] else None),
                "recorded_vs_chain_ask": entry_ask / eq["ask"] - 1 if eq["ask"] else None,
            })
            if xq and m_in:
                m_out = mid(xq)
                s_in, s_out = eq["underlying_price"], xq["underlying_price"]
                delta_move = (abs(eq["delta"]) * sign * (s_out - s_in)) if (eq["delta"] is not None and s_in and s_out) else None
                rec.update({
                    "exit_volume": xq["volume"], "exit_open_interest": xq["open_interest"],
                    "exit_spread_pct_of_ask": (xq["ask"] - xq["bid"]) / xq["ask"] if xq["ask"] else None,
                    "underlying_move_pct": sign * (s_out - s_in) / s_in if s_in and s_out else None,
                    # attribution in fractions of entry premium (entry_ask)
                    "attr_entry_spread": -(entry_ask - m_in) / entry_ask,
                    "attr_exit_spread": -(m_out - exit_bid) / entry_ask if m_out is not None else None,
                    "attr_delta": delta_move / entry_ask if delta_move is not None else None,
                    "attr_residual": ((m_out - m_in) - delta_move) / entry_ask if (m_out is not None and delta_move is not None) else None,
                    "holding_calendar_days": (datetime.fromisoformat(exit_day) - datetime.fromisoformat(evidence)).days,
                })
                # selection counterfactual: same-side contracts quoted on both days
                alternatives = []
                for alt_symbol, alt_in in entry_chain.items():
                    alt_out = exit_chain.get(alt_symbol)
                    if alt_out and alt_in["ask"] and alt_in["ask"] > 0 and alt_out["bid"] is not None:
                        alternatives.append((alt_symbol, alt_in, alt_out["bid"] / alt_in["ask"] - 1))
                if alternatives:
                    returns = sorted(r for _, _, r in alternatives)
                    chosen = xq["bid"] / eq["ask"] - 1 if eq["ask"] else None
                    rec["alt_count"] = len(alternatives)
                    rec["alt_median_return"] = st.median(returns)
                    rec["chosen_percentile"] = (sum(r < chosen for r in returns) / len(returns)) if chosen is not None else None
                    liquid = [r for _, a, r in alternatives
                              if a["delta"] is not None and 0.4 <= abs(a["delta"]) <= 0.6 and (a["dte"] or 0) >= 30
                              and (a["open_interest"] or 0) >= 100 and a["ask"] and (a["ask"] - a["bid"]) / a["ask"] <= 0.10]
                    rec["alt_atm_30dte_liquid_median_return"] = st.median(liquid) if liquid else None
        records.append(rec)

    def group_stats(key_fn):
        groups = defaultdict(list)
        for r in records:
            groups[key_fn(r)].append(r)
        out = {}
        for k, items in sorted(groups.items(), key=lambda kv: str(kv[0])):
            out[str(k)] = {
                "n": len(items),
                "return_on_premium": summarise([i["return_on_premium"] for i in items]),
                "underlying_move_pct": summarise([i.get("underlying_move_pct") for i in items]),
                "attr_entry_spread": summarise([i.get("attr_entry_spread") for i in items]),
                "attr_exit_spread": summarise([i.get("attr_exit_spread") for i in items]),
                "attr_delta": summarise([i.get("attr_delta") for i in items]),
                "attr_residual": summarise([i.get("attr_residual") for i in items]),
            }
        return out

    analysis = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expression_version": VERSION,
        "marked_headline": len(records),
        "entry_quote_found": sum(r["entry_quote_found"] for r in records),
        "liquidity": {
            "entry_volume_zero_share": st.fmean([1.0 if (r.get("entry_volume") in (0, None)) else 0.0 for r in records if r["entry_quote_found"]]),
            "exit_volume_zero_share": st.fmean([1.0 if (r.get("exit_volume") in (0, None)) else 0.0 for r in records if "exit_volume" in r]),
            "entry_open_interest": summarise([r.get("entry_open_interest") for r in records]),
            "entry_spread_pct_of_ask": summarise([r.get("entry_spread_pct_of_ask") for r in records]),
            "exit_spread_pct_of_ask": summarise([r.get("exit_spread_pct_of_ask") for r in records]),
        },
        "shape": {
            "entry_dte": summarise([r.get("entry_dte") for r in records]),
            "entry_abs_delta": summarise([r.get("entry_abs_delta") for r in records]),
            "moneyness_pct": summarise([r.get("moneyness_pct") for r in records]),
            "entry_iv": summarise([r.get("entry_iv") for r in records]),
            "greeks_quality": {k: sum(1 for r in records if r.get("greeks_quality") == k) for k in {r.get("greeks_quality") for r in records}},
            "recorded_vs_chain_ask": summarise([r.get("recorded_vs_chain_ask") for r in records]),
        },
        "attribution_all": group_stats(lambda r: "ALL"),
        "attribution_by_underlying_state": group_stats(lambda r: r["underlying_state"]),
        "by_delta_bucket": group_stats(lambda r: bucket(r.get("entry_abs_delta"), [0.15, 0.3, 0.45, 0.6], ["<0.15", "0.15-0.30", "0.30-0.45", "0.45-0.60", ">=0.60"])),
        "by_dte_bucket": group_stats(lambda r: bucket(r.get("entry_dte"), [14, 30, 45, 60], ["<14", "14-29", "30-44", "45-59", ">=60"])),
        "by_entry_spread_bucket": group_stats(lambda r: bucket(r.get("entry_spread_pct_of_ask"), [0.05, 0.10, 0.20, 0.35], ["<5%", "5-10%", "10-20%", "20-35%", ">=35%"])),
        "by_entry_volume": group_stats(lambda r: "MISSING" if r.get("entry_volume") is None else ("ZERO" if r["entry_volume"] == 0 else "TRADED")),
        "selection": {
            "with_alternatives": sum(1 for r in records if r.get("alt_count")),
            "chosen_percentile": summarise([r.get("chosen_percentile") for r in records]),
            "chosen_return": summarise([r["return_on_premium"] for r in records if r.get("alt_count")]),
            "alternatives_median_return": summarise([r.get("alt_median_return") for r in records]),
            "atm_30dte_liquid_alternative_median_return": summarise([r.get("alt_atm_30dte_liquid_median_return") for r in records]),
            "by_underlying_state": {
                state: {
                    "chosen": summarise([r["return_on_premium"] for r in records if r["underlying_state"] == state and r.get("alt_atm_30dte_liquid_median_return") is not None]),
                    "atm_30dte_liquid_alternative": summarise([r.get("alt_atm_30dte_liquid_median_return") for r in records if r["underlying_state"] == state]),
                } for state in sorted({r["underlying_state"] for r in records})
            },
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "expression_loss_diagnostic.json").write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    with (OUT / "expression_loss_records.jsonl").open("w", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, default=str) + "\n")
    print(json.dumps({k: analysis[k] for k in ("marked_headline", "entry_quote_found", "liquidity", "shape", "selection")}, indent=1, default=str))


if __name__ == "__main__":
    main()
