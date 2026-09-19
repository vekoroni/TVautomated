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


CHAIN_SELECT = """SELECT ticker,quote_date,option_symbol,side,strike,dte,bid,mid,ask,
               open_interest,volume,underlying_price,iv,delta,gamma,theta,vega FROM chain_snapshots"""


def _surface_and_atm(frame: pd.DataFrame, quote_date: str, built_at: str):
    """The IV surface rows (ticker x DTE bucket x side) and each ticker's ATM IV for one session's chains."""
    frame = frame.copy()
    frame["dte_bucket"] = frame["dte"].map(dte_bucket)
    frame["spread_pct"] = (
        (pd.to_numeric(frame["ask"], errors="coerce") - pd.to_numeric(frame["bid"], errors="coerce"))
        / pd.to_numeric(frame["mid"], errors="coerce").replace(0, pd.NA)
    )
    surface_rows = []
    grouped = frame.groupby(["ticker", "dte_bucket", "side"], dropna=False)
    medians = grouped["iv"].median().to_dict()
    iv25 = {key: nearest_iv(group, 0.25) for key, group in grouped}
    for (ticker, bucket, side), group in grouped:
        own_med = medians.get((ticker, bucket, side))
        put_med = medians.get((ticker, bucket, "put"))
        call_med = medians.get((ticker, bucket, "call"))
        put25 = iv25.get((ticker, bucket, "put"))
        call25 = iv25.get((ticker, bucket, "call"))
        surface_rows.append((
            ticker, quote_date, bucket, str(side).lower(), int(len(group)),
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
    valid_iv = valid_iv.sort_values(["ticker", "rank_dte", "rank_delta", "rank_strike", "side"], kind="mergesort")
    atm = valid_iv.groupby("ticker", as_index=False).first()[["ticker", "iv"]]
    return surface_rows, atm


def derive_iv_history(phantom_path: Path, iv_cache_path: Path, quote_date: str, tickers, *, execute: bool) -> dict:
    """Derive IV surface history and the IV cache for one session from the chains stored in Phantom.

    ACK 19 Sep 2026: the chains for 31 Aug - 17 Sep were stored but never derived (IV history stopped on 4 Sep),
    because derivation ran only in the manual weekly step. Rows are selected by (ticker, quote_date) - the
    indexed path - and only the tickers derived here are rewritten for that date. ``execute=False`` reports only.
    """
    built_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(phantom_path), timeout=120)
    conn.row_factory = sqlite3.Row
    try:
        records = []
        for ticker in sorted({str(t).upper() for t in tickers if t}):
            records.extend(dict(r) for r in conn.execute(
                CHAIN_SELECT + " WHERE ticker = ? AND quote_date = ?", (ticker, quote_date)))
        frame = pd.DataFrame(records)
        report = {"quote_date": quote_date, "tickers_requested": len(set(tickers)), "executed": bool(execute),
                  "built_at_utc": built_at}
        if frame.empty:
            return {**report, "status": "NO_CHAINS_FOR_SESSION", "tickers_derived": 0, "chain_rows": 0,
                    "surface_rows": 0, "iv_cache_rows": 0}
        surface_rows, atm = _surface_and_atm(frame, quote_date, built_at)
        derived = sorted(frame["ticker"].unique().tolist())
        report.update({"status": "PASS" if frame["iv"].notna().any() else "FAIL", "tickers_derived": len(derived),
                       "chain_rows": int(len(frame)), "surface_rows": len(surface_rows),
                       "iv_cache_rows": int(len(atm))})
        if execute:
            conn.execute("BEGIN")
            conn.executemany("DELETE FROM iv_surface_history WHERE quote_date = ? AND ticker = ?",
                             [(quote_date, t) for t in derived])
            conn.executemany(
                """INSERT INTO iv_surface_history
                (ticker,quote_date,dte_bucket,side,contract_count,atm_iv,median_iv,iv_entropy,
                 skew_25d,put_call_iv_spread,median_spread_pct,total_open_interest,total_volume,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", surface_rows)
            conn.commit()
            _write_iv_cache(iv_cache_path, quote_date, atm, built_at)
        return report
    finally:
        conn.close()


def _write_iv_cache(iv_cache_path: Path, quote_date: str, atm: pd.DataFrame, built_at: str) -> None:
    cache = sqlite3.connect(str(iv_cache_path), timeout=60)
    try:
        cache.execute("PRAGMA journal_mode=WAL")
        cache.execute("BEGIN")
        cache.executemany(
            """INSERT OR REPLACE INTO iv_history(ticker,sample_date,atm_iv,source,updated_at)
               VALUES(?,?,?,'phantom_history',?)""",
            [(row.ticker, quote_date, float(row.iv), built_at) for row in atm.itertuples(index=False)],
        )
        cache.executemany(
            """INSERT INTO iv_cache_meta(ticker,last_full_build,last_refresh) VALUES(?,NULL,?)
               ON CONFLICT(ticker) DO UPDATE SET last_refresh=excluded.last_refresh""",
            [(str(ticker), quote_date) for ticker in atm["ticker"]],
        )
        cache.commit()
    finally:
        cache.close()


def catch_up(phantom_path: Path, iv_cache_path: Path, start: str, end: str, tickers, *, execute: bool) -> list:
    """Derive every XNYS session from ``start`` to ``end`` (inclusive) that has stored chains."""
    import sys
    from datetime import date as _date, timedelta
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)                  # run as a script: the repo root holds the shared calendar
    from avshunter.shared.xnys_calendar import is_xnys_session
    day, last, reports = _date.fromisoformat(start), _date.fromisoformat(end), []
    while day <= last:
        if is_xnys_session(day):
            report = derive_iv_history(phantom_path, iv_cache_path, day.isoformat(), tickers, execute=execute)
            print(json.dumps({k: report[k] for k in ("quote_date", "status", "tickers_derived", "chain_rows",
                                                      "surface_rows", "iv_cache_rows", "executed")}), flush=True)
            reports.append(report)
        day += timedelta(days=1)
    return reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--iv-cache-path", type=Path, required=True)
    parser.add_argument("--quote-date")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    # Catch-up mode (ACK 19 Sep 2026): derive a range of sessions from chains already in Phantom.
    parser.add_argument("--catch-up-from")
    parser.add_argument("--catch-up-to")
    args = parser.parse_args()

    if args.catch_up_from:
        cache = sqlite3.connect(f"file:{Path(args.iv_cache_path).as_posix()}?mode=ro", uri=True)
        tickers = [r[0] for r in cache.execute("SELECT DISTINCT ticker FROM iv_history")]
        cache.close()
        reports = catch_up(args.db_path, args.iv_cache_path, args.catch_up_from, args.catch_up_to or
                           args.catch_up_from, tickers, execute=args.execute)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        return 0
    if not args.quote_date or args.expected_rows is None:
        parser.error("--quote-date and --expected-rows are required outside catch-up mode")

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
