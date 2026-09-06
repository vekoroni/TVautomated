"""
build_premarket_candidates.py
Combines News Terminal catalyst CSV + MA Cockpit candidate CSV into a single
pre-market candidate file at dropbox/inputs/.

Called automatically at the end of the news terminal run.
Output feeds AVSHUNTER pipeline as supplementary universe input.
execution_permission and capital_grade are LOCKED -- source values discarded.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

BASE  = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
TODAY = datetime.now().strftime("%Y%m%d")

NEWS_TERMINAL_OUTPUT = BASE / "news_terminal" / "outputs"
MA_COCKPIT_OUTPUT    = BASE / "ma_cockpit" / "outputs"

DROPBOX_INPUTS = BASE / "dropbox" / "inputs"

OUTPUT_COLS = [
    "ticker", "catalyst_type", "catalyst_status", "catalyst_date",
    "event_window_start", "event_window_end", "catalyst_direction_bias",
    "catalyst_source_confidence", "catalyst_binary_score", "source_tier",
    "source_url", "ticker_role", "event_status", "tradability_route",
    "failure_risk", "missing_data", "execution_permission", "capital_grade",
    "date_quality", "source_count", "already_priced_risk",
    "needs_manual_confirmation", "company", "sector", "key_catalyst",
    "transmission_channel", "expected_impact", "confirmation_signals",
    "invalidation_signals", "anis_score", "fips_score", "manual_validation_notes"
]

LOCKED_FIELDS = {
    "execution_permission": "NONE_NEWS_TERMINAL_ONLY",
    "capital_grade":        "NO",
}


def load_latest(directory: Path, pattern: str, label: str) -> pd.DataFrame:
    files = sorted(
        directory.glob(pattern),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        print(f"  [WARN] {label}: no files matching '{pattern}' in {directory}")
        return pd.DataFrame()
    latest = files[0]
    print(f"  [LOAD] {label}: {latest.name} ({latest.stat().st_size:,} bytes)")
    try:
        df = pd.read_csv(latest, low_memory=False)
        print(f"         {len(df)} rows")
        return df
    except Exception as e:
        print(f"  [ERROR] {label}: {e}")
        return pd.DataFrame()


def build_tickers_file(combined: pd.DataFrame):
    tickers = combined["ticker"].dropna().unique().tolist()
    outfile = DROPBOX_INPUTS / f"news_terminal_tickers_{TODAY}.txt"
    with open(outfile, "w") as f:
        f.write("\n".join(sorted(str(t) for t in tickers if t)))
    print(f"  [TICKERS] {len(tickers)} tickers -> {outfile.name}")


def build_combined():
    DROPBOX_INPUTS.mkdir(parents=True, exist_ok=True)

    print(f"\n[BUILD] build_premarket_candidates.py â€” {TODAY}")

    nt_df = load_latest(
        NEWS_TERMINAL_OUTPUT,
        f"avshunter_catalyst_csv_{TODAY}.csv",
        "News Terminal"
    )
    if nt_df.empty:
        nt_df = load_latest(
            NEWS_TERMINAL_OUTPUT,
            "avshunter_catalyst_csv_*.csv",
            "News Terminal (latest)"
        )

    ma_df = load_latest(
        MA_COCKPIT_OUTPUT,
        f"ma_candidates_{TODAY}.csv",
        "MA Cockpit"
    )
    if ma_df.empty:
        ma_df = load_latest(
            MA_COCKPIT_OUTPUT,
            "ma_candidates_*.csv",
            "MA Cockpit (latest)"
        )

    frames = [df for df in [nt_df, ma_df] if not df.empty]
    if not frames:
        print("[ERROR] No source data found. Aborting.")
        print("        Ensure news terminal and MA cockpit have run first.")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    print(f"\n[BUILD] Raw combined: {len(combined)} rows")

    for field, value in LOCKED_FIELDS.items():
        combined[field] = value

    for col in OUTPUT_COLS:
        if col not in combined.columns:
            combined[col] = ""

    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["ticker", "catalyst_date", "catalyst_type"],
        keep="first"
    )
    if before > len(combined):
        print(f"  [DEDUP] {before - len(combined)} duplicate rows removed")

    combined["catalyst_binary_score"] = pd.to_numeric(
        combined["catalyst_binary_score"], errors="coerce"
    ).fillna(0)
    combined["anis_score"] = pd.to_numeric(
        combined["anis_score"], errors="coerce"
    ).fillna(0)
    combined = combined.sort_values(
        ["catalyst_binary_score", "anis_score"],
        ascending=[False, False]
    )

    outfile = DROPBOX_INPUTS / f"premarket_candidates_{TODAY}.csv"
    combined[OUTPUT_COLS].to_csv(outfile, index=False)
    print(f"\n[BUILD] premarket_candidates_{TODAY}.csv")
    print(f"        {len(combined)} rows | {len(OUTPUT_COLS)} cols")
    print(f"        execution_permission: NONE_NEWS_TERMINAL_ONLY (locked)")
    print(f"        capital_grade: NO (locked)")

    build_tickers_file(combined)

    return combined


if __name__ == "__main__":
    build_combined()

