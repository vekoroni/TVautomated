# === ENHANCED Fung-Hsieh Weekly Factor Dashboard ML v1.4 ===
# CHANGES over v1.1 (v1.2):
# ✅ OUTPUT_DIR config cell — saves direct to dropbox\market_data
# ✅ HYG added to tickers — credit spread factor (BD_HYG) now in model
# ✅ BD_HYG factor: weekly HYG return as credit risk proxy
# ✅ No files.download() calls
#
# v1.3 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab: keys from Colab
# Secrets, else environment / repo .env; charts only with matplotlib; 30 s timeout on Polygon
# requests; UTF-8 console; --output-dir (or AVSH_FH_OUTPUT_DIR) for testing; exit 1 if the CSV
# fails.
#
# v1.4 (7 Oct 2026, ACK approved) — factors, model, thresholds and CSV schema unchanged:
# ✅ FIX: chronological split. v1.3 used train_test_split(random_state=42, stratify=y), which
#    SHUFFLES the weekly series, so future weeks trained the model that was then "tested" on
#    the past; Accuracy — and GO/NO-GO, which gates on Accuracy >= 0.70 — was optimistic. The
#    test set is now the most recent 20% of weeks, after the weeks the model learned from.
# ✅ FIX: only finished weeks. Polygon's current weekly bar is in progress; v1.3 resampled it to
#    a FUTURE Friday (6 Oct run: "Week of 2026-10-09"). Weeks whose Friday is after today are
#    dropped; run after Friday's close to include that week.
# ✅ FIX: no fabricated outcome. (NaN > 0).astype(int) gave the newest week a Target of 0
#    ("SPY fell") that never happened; a week without a following week now has no Target and
#    is left out of training and testing.
# ✅ Importing this file does nothing; work happens in main() (tests import the functions).
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_fung_hsieh_filter_v1_4.py

import argparse
import datetime as dt
import os
import pathlib
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUTPUT_NAME = "avshunter_macro_filter_summary.csv"
TEST_FRACTION = 0.2
GO_ACCURACY = 0.7
PROB_THRESHOLD = 0.65
POLYGON_API_KEY = None     # set by main()

tickers = {
    "SPY":"SPY","IWM":"IWM","UUP":"UUP",
    "TLT":"TLT","IEF":"IEF","GLD":"GLD","USO":"USO",
    "HYG":"HYG",   # FIX v1.2: credit proxy added
}


# ══════════════════════════════════════════════════════════════
# Data preparation (pure; unit-tested)
# ══════════════════════════════════════════════════════════════

def complete_weekly_returns(data, today):
    """Weekly (Friday-labelled) returns from finished weeks only. A week whose Friday label is
    after `today` is still in progress and is dropped (v1.3 kept it under a future date)."""
    weekly_data = data.resample('W-FRI').last()
    weekly_data = weekly_data[weekly_data.index <= pd.Timestamp(today)]
    return weekly_data.pct_change().dropna()


def build_factors(weekly_returns):
    """Fung-Hsieh factors and their 12-week transforms (unchanged from v1.2)."""
    factors = pd.DataFrame(index=weekly_returns.index)
    risk_free_weekly = 0.05 / 52
    factors["SNPMRF"]   = weekly_returns["SPY"] - risk_free_weekly
    factors["SCMLC"]    = weekly_returns["IWM"] - weekly_returns["SPY"]
    factors["BD10RET"]  = weekly_returns["TLT"] - weekly_returns["IEF"]
    factors["PTFSCOM"]  = (weekly_returns["USO"] + weekly_returns["GLD"]) / 2
    factors["PTFSFX"]   = weekly_returns["UUP"]
    factors["PTFSBD"]   = weekly_returns["TLT"]
    if "HYG" in weekly_returns.columns:
        factors["BD_HYG"] = weekly_returns["HYG"]   # credit spread proxy (HY bond returns)
    for col in list(factors.columns):
        factors[f'{col}_sharpe'] = factors[col].rolling(12).mean() / factors[col].rolling(12).std()
        factors[f'{col}_roc']    = factors[col].pct_change(periods=12)
        factors[f'{col}_z']      = (factors[col] - factors[col].rolling(12).mean()) / factors[col].rolling(12).std()
    return factors


def build_dataset(weekly_returns):
    """(X, y): y is whether SPY rose the FOLLOWING week. FIX v1.4: a week whose following week
    has not happened has no outcome (NaN, dropped), never a fabricated 0."""
    factors = build_factors(weekly_returns)
    nxt = weekly_returns['SPY'].shift(-1)
    factors['Target'] = (nxt > 0).astype(float).where(nxt.notna())
    factors = factors.dropna()
    X = factors[[c for c in factors.columns if '_sharpe' in c or '_roc' in c or '_z' in c]]
    X = X.replace([np.inf,-np.inf], np.nan).dropna()
    y = factors['Target'].loc[X.index].astype(int)
    return X, y


def chronological_split(X_scaled, y, test_size=TEST_FRACTION):
    """FIX v1.4: train on earlier weeks, test on the most recent ones (no shuffle)."""
    return train_test_split(X_scaled, y, test_size=test_size, shuffle=False)


# ══════════════════════════════════════════════════════════════
# Fetching
# ══════════════════════════════════════════════════════════════

def fetch_polygon_weekly(ticker, start_date, end_date):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/week/{start_date}/{end_date}"
    params = {"adjusted":"true","sort":"asc","apiKey":POLYGON_API_KEY}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200: print(f"Failed: {ticker}: {r.status_code}"); return None
    results = r.json().get("results", [])
    if not results: return None
    df = pd.DataFrame(results)
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("t", inplace=True)
    return df["c"]


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main(argv=None):
    global POLYGON_API_KEY
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="AVSHUNTER Fung-Hsieh weekly macro filter")
    parser.add_argument("--output-dir", default=os.environ.get("AVSH_FH_OUTPUT_DIR"),
                        help="write here instead of dropbox\\market_data (for testing)")
    args, _ = parser.parse_known_args(argv)   # Colab passes its own kernel arguments
    if args.output_dir:
        output_dir = pathlib.Path(args.output_dir)
    else:
        output_dir = REPO_ROOT / "dropbox" / "market_data"
        if not output_dir.exists():
            output_dir = pathlib.Path("/content")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 OUTPUT_DIR: {output_dir}")

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        plt = None

    if IN_COLAB:
        from google.colab import userdata
        try:
            POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
            print("✅ API key loaded from Colab Secrets")
        except Exception as e:
            print("❌ ERROR: Could not load POLYGON_API_KEY"); raise
    else:
        try:
            from dotenv import load_dotenv
            if (REPO_ROOT / ".env").exists():
                load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
        except ImportError:
            pass
        POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "").strip() or None
        print(f"ℹ️  Polygon key from environment / repo .env: {'found' if POLYGON_API_KEY else 'MISSING'}")
        if not POLYGON_API_KEY:
            raise SystemExit("❌ POLYGON_API_KEY is required — cannot proceed")

    today = dt.date.today()
    end_date   = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')

    price_data = {}
    for name, ticker in tickers.items():
        series = fetch_polygon_weekly(ticker, start_date, end_date)
        if series is not None and not series.empty:
            price_data[name] = series; print(f"✅ {name}")
        else:
            print(f"⚠️ Failed: {name}")

    weekly_returns = complete_weekly_returns(pd.DataFrame(price_data), today)
    if "HYG" in weekly_returns.columns:
        print(f"\n💳 BD_HYG factor active — HYG latest return: {weekly_returns['HYG'].iloc[-1]*100:.2f}%")
    else:
        print("\n⚠️  HYG MISSING — BD_HYG credit factor absent, credit risk neutral")

    X, y = build_dataset(weekly_returns)
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = chronological_split(X_scaled, y)
    print(f"\n📅 Train weeks {y_train.index.min().date()} → {y_train.index.max().date()} ({len(y_train)})"
          f" | test weeks {y_test.index.min().date()} → {y_test.index.max().date()} ({len(y_test)})")

    voter = VotingClassifier(estimators=[
        ('gbc',   GradientBoostingClassifier(n_estimators=150, random_state=42)),
        ('rf',    RandomForestClassifier(n_estimators=100, random_state=42)),
        ('logit', LogisticRegression(max_iter=500, random_state=42))
    ], voting='soft')

    voter.fit(X_train, y_train)
    model = CalibratedClassifierCV(voter, method='isotonic', cv=5)
    model.fit(X_train, y_train)

    probs  = model.predict_proba(X_test)[:, 1]
    y_pred = (probs >= PROB_THRESHOLD).astype(int)
    acc    = accuracy_score(y_test, y_pred)
    print(f"\n✅ Adjusted Accuracy: {acc:.2%}  (chronological hold-out, {len(y_test)} weeks)")

    report    = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    report_df = pd.DataFrame(report).T
    print(report_df)

    gbc = voter.named_estimators_['gbc']
    importance = pd.Series(gbc.feature_importances_, index=X.columns)
    if plt is not None and IN_COLAB:
        importance.sort_values(ascending=False).plot(
            kind='bar', figsize=(10,5), title='Weekly Feature Importance (v1.4)')
        plt.tight_layout(); plt.show()

    macro_bias    = 'Bullish' if acc >= GO_ACCURACY else 'Cautious / Tier 2'
    macro_go_flag = 'GO'      if acc >= GO_ACCURACY else 'NO-GO'
    top_drivers   = importance.sort_values(ascending=False).head(3).index.tolist()
    credit_active = "HYG" in weekly_returns.columns
    week_label    = weekly_returns.index[-1].strftime('%Y-%m-%d')   # last FINISHED week

    print(f"""
🧠 AVSHUNTER MACRO FILTER v1.4
Week of: {week_label}  (last finished week)
Adjusted Accuracy: {acc:.2%}
Bias: {macro_bias}
GO/NO-GO: {macro_go_flag}
Top Macro Drivers: {top_drivers}
Credit Factor (BD_HYG): {'ACTIVE' if credit_active else 'MISSING — neutral'}

📋 PIPELINE NOTE: macro_filter_summary.csv feeds into macro_intelligence_latest.json
   Path: extras.macro_filter_summary
   GO/NO-GO gate: accuracy >= 0.70 → GO | < 0.70 → NO-GO
""")

    macro_summary = pd.DataFrame([{
        'Week':          week_label,
        'Accuracy':      acc,
        'Bias':          macro_bias,
        'GO_NO_GO':      macro_go_flag,
        'Top1':          top_drivers[0],
        'Top2':          top_drivers[1],
        'Top3':          top_drivers[2],
        'Credit_Active': credit_active,   # FIX v1.2
    }])

    try:
        macro_summary.to_csv(output_dir / OUTPUT_NAME, index=False)
    except OSError as e:
        print(f"\n❌ CSV save failed: {e}")
        if not IN_COLAB:
            return 1
        raise
    print(f"📁 {output_dir / OUTPUT_NAME}")
    print(f"\n✅ v1.4 COMPLETE — outputs → {output_dir}")
    return 0


if __name__ == "__main__":
    _code = main()
    if not IN_COLAB:          # in a notebook cell SystemExit would print a traceback
        sys.exit(_code)
