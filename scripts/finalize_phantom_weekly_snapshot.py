"""Finalize one newly appended PHANTOM weekly snapshot without a full-table scan."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def entropy(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    clean = clean[(clean > 0) & clean.map(math.isfinite)]
    if len(clean) < 2:
        return 0.0
    probs = clean / clean.sum()
    return float(-(probs * probs.map(math.log)).sum())


def dte_bucket(value) -> str:
    try:
        dte = float(value)
    except Exception:
        return "UNKNOWN"
    if dte <= 7:
        return "0_7"
    if dte <= 30:
        return "8_30"
    if dte <= 60:
        return "31_60"
    return "61_PLUS"


def nearest_iv(group: pd.DataFrame, target_delta: float) -> float | None:
    valid = group[pd.to_numeric(group["iv"], errors="coerce").between(0.01, 5.0)].copy()
    if valid.empty:
        return None
    delta = pd.to_numeric(valid["delta"], errors="coerce").abs()
    if delta.notna().any():
        row = valid.loc[(delta - target_delta).abs().idxmin()]
    else:
        distance = (
            pd.to_numeric(valid["strike"], errors="coerce")
            - pd.to_numeric(valid["underlying_price"], errors="coerce")
        ).abs()
        row = valid.loc[distance.idxmin()]
    return float(row["iv"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--iv-cache-path", type=Path, required=True)
    parser.add_argument("--quote-date", required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    rows = conn.execute(
        """
        SELECT ticker,quote_date,option_symbol,side,strike,dte,bid,mid,ask,
               open_interest,volume,underlying_price,iv,delta,gamma,theta,vega,
               greeks_source,greeks_quality
        FROM chain_snapshots ORDER BY rowid DESC LIMIT ?
        """,
        (args.expected_rows,),
    ).fetchall()
    frame = pd.DataFrame([dict(row) for row in rows])
    if len(frame) != args.expected_rows:
        raise RuntimeError(f"Expected {args.expected_rows} tail rows, found {len(frame)}")
    dates = sorted(frame["quote_date"].astype(str).unique().tolist())
    if dates != [args.quote_date]:
        raise RuntimeError(f"Tail-slice date contract failed: {dates}")

    greek_cols = ["iv", "delta", "gamma", "theta", "vega"]
    coverage = {name: int(frame[name].notna().sum()) for name in greek_cols}
    frame["dte_bucket"] = frame["dte"].map(dte_bucket)
    frame["spread_pct"] = (
        (pd.to_numeric(frame["ask"], errors="coerce") - pd.to_numeric(frame["bid"], errors="coerce"))
        / pd.to_numeric(frame["mid"], errors="coerce").replace(0, pd.NA)
    )

    surface_rows = []
    grouped = frame.groupby(["ticker", "dte_bucket", "side"], dropna=False)
    medians = grouped["iv"].median().to_dict()
    iv25 = {key: nearest_iv(group, 0.25) for key, group in grouped}
    built_at = datetime.now(timezone.utc).isoformat()
    for (ticker, bucket, side), group in grouped:
        opposite = "put" if str(side).lower() == "call" else "call"
        own_med = medians.get((ticker, bucket, side))
        opp_med = medians.get((ticker, bucket, opposite))
        put_med = medians.get((ticker, bucket, "put"))
        call_med = medians.get((ticker, bucket, "call"))
        put25 = iv25.get((ticker, bucket, "put"))
        call25 = iv25.get((ticker, bucket, "call"))
        surface_rows.append((
            ticker, args.quote_date, bucket, str(side).lower(), int(len(group)),
            nearest_iv(group, 0.50), float(own_med) if pd.notna(own_med) else None,
            entropy(group["iv"]),
            (float(put25) - float(call25)) if put25 is not None and call25 is not None else None,
            (float(put_med) - float(call_med)) if pd.notna(put_med) and pd.notna(call_med) else None,
            float(group["spread_pct"].median()) if group["spread_pct"].notna().any() else None,
            int(pd.to_numeric(group["open_interest"], errors="coerce").fillna(0).sum()),
            int(pd.to_numeric(group["volume"], errors="coerce").fillna(0).sum()),
            built_at,
        ))

    valid_iv = frame[
        pd.to_numeric(frame["iv"], errors="coerce").between(0.01, 5.0)
        & pd.to_numeric(frame["underlying_price"], errors="coerce").gt(0)
        & pd.to_numeric(frame["strike"], errors="coerce").gt(0)
    ].copy()
    valid_iv["rank_dte"] = (pd.to_numeric(valid_iv["dte"], errors="coerce") - 30.0).abs()
    valid_iv["rank_delta"] = (pd.to_numeric(valid_iv["delta"], errors="coerce").abs() - 0.50).abs()
    valid_iv["rank_strike"] = (
        pd.to_numeric(valid_iv["strike"], errors="coerce")
        - pd.to_numeric(valid_iv["underlying_price"], errors="coerce")
    ).abs()
    valid_iv = valid_iv.sort_values(
        ["ticker", "rank_dte", "rank_delta", "rank_strike", "side"],
        kind="mergesort",
    )
    atm = valid_iv.groupby("ticker", as_index=False).first()[["ticker", "iv"]]

    report = {
        "status": "PASS" if coverage["iv"] > 0 else "FAIL",
        "quote_date": args.quote_date,
        "chain_rows": int(len(frame)),
        "tickers_with_chains": int(frame["ticker"].nunique()),
        "greek_coverage": coverage,
        "full_greek_rows": int(frame[greek_cols].notna().all(axis=1).sum()),
        "surface_rows": int(len(surface_rows)),
        "iv_cache_rows": int(len(atm)),
        "executed": bool(args.execute),
        "built_at_utc": built_at,
    }
    if args.execute:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM iv_surface_history WHERE quote_date=?", (args.quote_date,))
        conn.executemany(
            """
            INSERT INTO iv_surface_history
            (ticker,quote_date,dte_bucket,side,contract_count,atm_iv,median_iv,iv_entropy,
             skew_25d,put_call_iv_spread,median_spread_pct,total_open_interest,total_volume,created_at_utc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            surface_rows,
        )
        conn.commit()

        cache = sqlite3.connect(str(args.iv_cache_path), timeout=60)
        cache.execute("PRAGMA journal_mode=WAL")
        cache.execute("BEGIN")
        cache.executemany(
            """INSERT OR REPLACE INTO iv_history(ticker,sample_date,atm_iv,source,updated_at)
               VALUES(?,?,?,'phantom_history',?)""",
            [(row.ticker, args.quote_date, float(row.iv), built_at) for row in atm.itertuples(index=False)],
        )
        cache.executemany(
            """INSERT INTO iv_cache_meta(ticker,last_full_build,last_refresh) VALUES(?,NULL,?)
               ON CONFLICT(ticker) DO UPDATE SET last_refresh=excluded.last_refresh""",
            [(str(ticker), args.quote_date) for ticker in atm["ticker"]],
        )
        cache.commit()
        cache.close()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    conn.close()
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
