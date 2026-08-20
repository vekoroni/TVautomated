import pandas as pd
from pathlib import Path

# === CHANGE THIS PATH TO YOUR FINAL EXECUTION CSV ===
csv_path = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\LATEST_RUN\execution\final_execution_list.csv")

if not csv_path.exists():
    raise FileNotFoundError(f"CSV not found: {csv_path}")

df = pd.read_csv(csv_path)

print("=" * 80)
print("AVSHUNTER MACRO SECTOR PROPAGATION TEST")
print("=" * 80)
print(f"Rows loaded: {len(df)}")
print(f"File: {csv_path}")
print()

lead = [
    "XLK",
    "QQQ",
    "Information Technology",
    "Industrials",
    "Consumer Discretionary",
]

avoid = [
    "XLE",
    "XLV",
    "XLU",
    "Energy",
    "Health Care",
    "Utilities",
]

# Try to find a usable sector column
possible_sector_cols = [
    "sector",
    "sector_name",
    "gics_sector",
    "macro_sector",
    "sector_etf",
]

sector_col = None
for col in possible_sector_cols:
    if col in df.columns:
        sector_col = col
        break

if sector_col is None:
    print("FAIL: No sector column found.")
    print("Available columns:")
    for c in df.columns:
        print(" -", c)
    raise SystemExit(1)

print(f"Using sector column: {sector_col}")
print()

def classify_sector(x):
    x = str(x).strip()

    if x in lead:
        return "TAILWIND"

    if x in avoid:
        return "HEADWIND"

    return "NEUTRAL"

df["macro_sector_expected"] = df[sector_col].apply(classify_sector)

# Try to find verdict column
possible_verdict_cols = [
    "final_verdict",
    "verdict",
    "execution_verdict",
    "pse_execution_mode",
    "final_decision",
    "decision",
]

verdict_col = None
for col in possible_verdict_cols:
    if col in df.columns:
        verdict_col = col
        break

if verdict_col is None:
    print("FAIL: No verdict column found.")
    print("Available columns:")
    for c in df.columns:
        print(" -", c)
    raise SystemExit(1)

print(f"Using verdict column: {verdict_col}")
print()

print("Macro Sector x Final Verdict:")
print(pd.crosstab(df["macro_sector_expected"], df[verdict_col], dropna=False))
print()

# Try score column
possible_score_cols = [
    "final_score",
    "composite_score",
    "execution_score",
    "eil_composite_score",
    "pse_score",
    "truth_score",
]

score_col = None
for col in possible_score_cols:
    if col in df.columns:
        score_col = col
        break

if score_col:
    print(f"Using score column: {score_col}")
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce")
    print()
    print("Average score by macro sector expectation:")
    print(df.groupby("macro_sector_expected")[score_col].mean().sort_values(ascending=False))
else:
    print("WARNING: No score column found. Skipping score test.")

print()
print("Top 30 candidates by available score/verdict context:")
cols_to_show = ["ticker", sector_col, "macro_sector_expected", verdict_col]

if score_col:
    cols_to_show.append(score_col)

existing_cols = [c for c in cols_to_show if c in df.columns]

if score_col:
    print(df.sort_values(score_col, ascending=False)[existing_cols].head(30).to_string(index=False))
else:
    print(df[existing_cols].head(30).to_string(index=False))

print()
print("=" * 80)
print("TEST INTERPRETATION")
print("=" * 80)
print("PASS expectation:")
print("- TAILWIND sectors should have better verdict distribution than NEUTRAL.")
print("- HEADWIND sectors should not dominate the executable list.")
print("- If HEADWIND names are high-ranked, they need exceptional Vanguard/options evidence.")
print("- If all sectors behave the same, macro sector rotation is not being used effectively.")
