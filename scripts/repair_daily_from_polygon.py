# scripts/repair_daily_from_polygon.py
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from polygon_data_fetcher import PolygonDataFetcher

BASE = Path(__file__).resolve().parents[1]
DAILY_DIR = BASE / "data" / "daily"

MIN_BARS = 120
START_DATE = "2022-01-01"   # wide window so you always exceed MIN_BARS
END_DATE   = "2026-02-11"   # set to today in real runs (or pass via CLI)

# If your universe CSV lives here, we'll auto-detect it
DEFAULT_UNIVERSE = BASE / "data" / "universe" / "hybrid_universe_enhanced.csv"
FALLBACK_TICKERS = BASE / "data" / "tickers.csv"

TICKER_COL_CANDIDATES = ("ticker", "symbol", "Ticker", "Symbol")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_local_daily(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"])
        return df
    except Exception:
        return None


def write_local_daily(path: Path, df: pd.DataFrame) -> None:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def detect_ticker_column(df: pd.DataFrame) -> str:
    for c in TICKER_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise SystemExit(
        f"Tickers file must contain one of these columns: {list(TICKER_COL_CANDIDATES)}. "
        f"Found: {df.columns.tolist()}"
    )


def load_tickers(tickers_path: Path) -> list[str]:
    if not tickers_path.exists():
        raise SystemExit(f"Missing tickers list: {tickers_path}")

    df = pd.read_csv(tickers_path)
    col = detect_ticker_column(df)

    tickers = (
        df[col]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )

    if not tickers:
        raise SystemExit(f"No tickers found in {tickers_path} (column: {col})")

    return tickers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Repair / backfill daily CSVs in data/daily using Polygon when local bars are insufficient."
    )
    p.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Path to tickers CSV (must contain ticker/symbol column). "
             "If omitted, uses data/universe/hybrid_universe_enhanced.csv if present, else data/tickers.csv.",
    )
    p.add_argument("--min-bars", type=int, default=MIN_BARS, help="Minimum bars required for a ticker to be OK.")
    p.add_argument("--start", type=str, default=START_DATE, help="Start date YYYY-MM-DD for Polygon fetch.")
    p.add_argument("--end", type=str, default=END_DATE, help="End date YYYY-MM-DD for Polygon fetch.")
    p.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite even if local file already has >= min-bars (normally skipped).",
    )
    p.add_argument(
        "--report",
        type=str,
        default="",
        help="Optional report path (json). Defaults to data/output/repair_daily_report.json",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    tickers_path = Path(args.tickers) if args.tickers else (DEFAULT_UNIVERSE if DEFAULT_UNIVERSE.exists() else FALLBACK_TICKERS)
    min_bars = int(args.min_bars)
    start = args.start
    end = args.end
    force = bool(args.force)

    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    # Initialise Polygon fetcher (expects key to be handled inside PolygonDataFetcher)
    f = PolygonDataFetcher()

    tickers = load_tickers(tickers_path)

    upgraded = 0
    skipped_ok = 0
    failed = 0

    failures_sample: list[dict] = []
    sources_used: dict[str, int] = {"LOCAL_OK": 0, "POLYGON_OK": 0}

    for i, t in enumerate(tickers, 1):
        out_path = DAILY_DIR / f"{t}.csv"
        local = read_local_daily(out_path)
        local_n = 0 if local is None else len(local)

        # If local already sufficient and not forcing, skip
        if (not force) and local_n >= min_bars:
            skipped_ok += 1
            sources_used["LOCAL_OK"] += 1
            continue

        try:
            poly = f.fetch_daily_bars(t, start, end)

            poly_n = 0 if poly is None else len(poly)
            if poly is None or poly_n < min_bars:
                key = f"INSUFFICIENT_BARS({poly_n}<{min_bars})"
                sources_used[key] = sources_used.get(key, 0) + 1
                failed += 1
                if len(failures_sample) < 50:
                    failures_sample.append(
                        {
                            "i": i,
                            "ticker": t,
                            "path": str(out_path),
                            "error": key,
                            "local_bars": local_n,
                            "polygon_bars": poly_n,
                            "tickers_source": str(tickers_path),
                        }
                    )
                print(f"[{i}/{len(tickers)}] FAIL {t}: polygon returned {poly_n} bars (need {min_bars})")
                continue

            # Overwrite (cleanest) — avoids merging partial ranges into a franken-series
            write_local_daily(out_path, poly)
            upgraded += 1
            sources_used["POLYGON_OK"] += 1
            print(f"[{i}/{len(tickers)}] UPGRADED {t}: {local_n} -> {poly_n} bars")

        except Exception as e:
            failed += 1
            err = f"{type(e).__name__}: {e}"
            if len(failures_sample) < 50:
                failures_sample.append(
                    {
                        "i": i,
                        "ticker": t,
                        "path": str(out_path),
                        "error": err,
                        "local_bars": local_n,
                        "tickers_source": str(tickers_path),
                    }
                )
            print(f"[{i}/{len(tickers)}] FAIL {t}: {err}")

    report = {
        "created_utc": utc_now_iso(),
        "tickers_source": str(tickers_path),
        "daily_dir": str(DAILY_DIR),
        "min_bars": min_bars,
        "start": start,
        "end": end,
        "force": force,
        "processed": len(tickers),
        "upgraded": upgraded,
        "skipped_ok": skipped_ok,
        "failed": failed,
        "sources_used": sources_used,
        "failures_sample": failures_sample,
    }

    report_path = Path(args.report) if args.report else (BASE / "data" / "output" / "repair_daily_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nDONE")
    print(f"Tickers source: {tickers_path}")
    print(f"Upgraded: {upgraded}")
    print(f"Skipped (already OK): {skipped_ok}")
    print(f"Failed: {failed}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
