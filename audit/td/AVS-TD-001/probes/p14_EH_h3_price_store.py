"""p14_EH_h3_price_store: read-only coverage of historical_prices.sqlite COPY
against the governed universe of the primary run (final_opportunity_book tickers).
Outputs p14_EH_h3_price_store_out.json and p14_EH_h3_price_store_per_ticker.csv.
"""
import sqlite3, json, os, csv, collections
import pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "historical_prices.sqlite"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
run = "20260911_115904"
book = pd.read_csv(os.path.join(REPO, "data", "output", "runs", run, "intelligence_lab", f"final_opportunity_book_{run}.csv"),
                   usecols=["ticker", "governed_direction"], low_memory=False)
universe = sorted(set(book["ticker"].astype(str).str.upper()))
per = con.execute(
    "SELECT ticker, COUNT(*), MIN(trading_date), MAX(trading_date), "
    "SUM(CASE WHEN bar_status='COMPLETE' THEN 1 ELSE 0 END), COUNT(DISTINCT adjustment_convention) "
    "FROM ohlcv_daily GROUP BY ticker").fetchall()
stats = {r[0]: r for r in per}
bar_status = dict(con.execute("SELECT bar_status, COUNT(*) FROM ohlcv_daily GROUP BY bar_status").fetchall())
adj = dict(con.execute("SELECT adjustment_convention, COUNT(*) FROM ohlcv_daily GROUP BY adjustment_convention").fetchall())
prov = dict(con.execute("SELECT provider, COUNT(*) FROM ohlcv_daily GROUP BY provider").fetchall())
meta = con.execute("SELECT * FROM price_schema_metadata").fetchall()
glob_range = con.execute("SELECT MIN(trading_date), MAX(trading_date), COUNT(*), COUNT(DISTINCT ticker) FROM ohlcv_daily").fetchone()
covered = [t for t in universe if t in stats]
missing = [t for t in universe if t not in stats]
rows_cov = [stats[t][1] for t in covered]
maxd = collections.Counter(stats[t][3] for t in covered)
recent = sum(1 for t in covered if stats[t][3] >= "2026-09-10")
with open(os.path.join(ROOT, "p14_EH_h3_price_store_per_ticker.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["ticker", "in_primary_book", "rows", "min_date", "max_date", "completed_rows", "n_adjustment_conventions"])
    for t in sorted(stats):
        r = stats[t]; w.writerow([t, t in set(universe), r[1], r[2], r[3], r[4], r[5]])
dir_cov = collections.defaultdict(lambda: [0, 0])
for t, d in zip(book["ticker"].astype(str).str.upper(), book["governed_direction"].astype(str).str.upper()):
    k = d if d in ("CALL", "PUT") else "OTHER"; dir_cov[k][1] += 1; dir_cov[k][0] += int(t in stats)
out = {
    "db_path": DB, "schema_metadata": meta, "global_min_date": glob_range[0], "global_max_date": glob_range[1],
    "total_rows": glob_range[2], "distinct_tickers_in_store": glob_range[3],
    "bar_status_counts": bar_status, "adjustment_conventions": adj, "providers": prov,
    "primary_book_tickers": len(universe), "primary_book_tickers_covered": len(covered), "primary_book_tickers_missing": len(missing),
    "missing_ticker_sample": missing[:20],
    "rows_per_covered_ticker": {"min": min(rows_cov) if rows_cov else None, "median": sorted(rows_cov)[len(rows_cov)//2] if rows_cov else None, "max": max(rows_cov) if rows_cov else None},
    "covered_tickers_with_max_date_ge_2026-09-10": recent,
    "max_date_distribution_top": maxd.most_common(6),
    "coverage_by_book_direction_rows": {k: {"covered": v[0], "rows": v[1]} for k, v in dir_cov.items()},
}
json.dump(out, open(os.path.join(ROOT, "p14_EH_h3_price_store_out.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
