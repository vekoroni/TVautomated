"""p14_EH_h2_trade_journal: read-only field census of trade_journal.db COPY.
For each closed_trades row report presence of symbol/price/quantity/time/source
fields; list distinct journal_entry_source values; count trades rows; and dump the
legacy calibration_reports rows (report_id, generated_at, trades_analysed).
Output: p14_EH_h2_trade_journal_out.json
"""
import sqlite3, json, os, collections
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "trade_journal.db"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); con.row_factory = sqlite3.Row
cols = [r[1] for r in con.execute("PRAGMA table_info(closed_trades)")]
FIELDS = {
    "symbol_underlying": ["ticker"], "symbol_occ": ["occ_symbol", "contract_symbol"],
    "strike": ["strike"], "expiry": ["expiry"], "price_entry": ["entry_premium"],
    "price_exit": ["exit_premium"], "quantity": ["contracts"], "time_entry_date": ["entry_date"],
    "time_entry_time": ["entry_time"], "time_exit": ["exit_date", "exit_time"],
    "source": ["journal_entry_source"], "fill_source": ["fill_source", "source"],
    "user_confirmed_live_validation": ["user_confirmed_live_validation"],
}
rows = con.execute("SELECT * FROM closed_trades ORDER BY trade_id").fetchall()
per = []; missing_tot = collections.Counter(); dir_split = collections.Counter(); src = collections.Counter()
for r in rows:
    d = dict(r); rec = {"trade_id": d.get("trade_id"), "ticker": d.get("ticker"), "run_id": d.get("run_id"),
                        "options_direction": d.get("options_direction"), "journal_entry_source": d.get("journal_entry_source")}
    missing = []
    for label, cands in FIELDS.items():
        present = [c for c in cands if c in cols and d.get(c) not in (None, "")]
        rec[label] = present[0] + "=" + str(d.get(present[0]))[:30] if present else "MISSING"
        if not present: missing.append(label)
    rec["missing"] = missing; per.append(rec)
    for m in missing: missing_tot[m] += 1
    dd = str(d.get("options_direction") or "").upper(); dir_split[dd if dd in ("CALL", "PUT") else "OTHER"] += 1
    src[str(d.get("journal_entry_source"))] += 1
cal = [dict(r) for r in con.execute("SELECT report_id,generated_at,trades_analysed,predicted_win_rate,realised_win_rate FROM calibration_reports ORDER BY generated_at")]
out = {
    "closed_trades_rows": len(rows), "trades_rows": con.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
    "closed_trades_has_occ_symbol_column": any(c in cols for c in ("occ_symbol", "contract_symbol")),
    "closed_trades_has_fill_source_column": any(c in cols for c in ("fill_source",)),
    "journal_entry_source_values": dict(src), "direction_split": dict(dir_split),
    "missing_field_totals": dict(missing_tot), "per_record": per,
    "legacy_calibration_reports": cal,
}
json.dump(out, open(os.path.join(ROOT, "p14_EH_h2_trade_journal_out.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "per_record"}, indent=1, default=str))
print("per_record missing:", [(p["trade_id"], p["missing"]) for p in per])
