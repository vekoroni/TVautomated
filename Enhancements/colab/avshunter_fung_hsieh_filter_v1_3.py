# === ENHANCED Fung-Hsieh Weekly Factor Dashboard ML v1.2 ===
# CHANGES over v1.1:
# ✅ OUTPUT_DIR config cell — saves direct to dropbox\market_data
# ✅ HYG added to tickers — credit spread factor (BD_HYG) now in model
# ✅ BD_HYG factor: weekly HYG return as credit risk proxy
# ✅ No files.download() calls
#
# v1.3 (7 Oct 2026) — Colab notebook "AVSHUNTER_Macro_Model_Rebuild_and_Loader" ported to run
# unattended on the AVSHUNTER PC as well as in Colab. Model, factors, thresholds and the
# avshunter_macro_filter_summary.csv schema are unchanged from v1.2; only how it runs:
# ✅ Keys from Colab Secrets, else environment / repo .env (override=False).
# ✅ Charts only when matplotlib is installed (display-only; not in the venv).
# ✅ Polygon requests get a 30 s timeout (v1.2 had none: a scheduled run could hang).
# ✅ UTF-8 console; --output-dir (or AVSH_FH_OUTPUT_DIR) for testing; exit 1 if the CSV fails.
# ⚠️ KNOWN, NOT FIXED HERE (awaiting ACK):
#    • train_test_split(random_state=42, stratify=y) SHUFFLES a weekly time series, so future
#      weeks train the model that is then "tested" on the past; Accuracy (and GO/NO-GO, which
#      gates on Accuracy >= 0.70) is optimistic. 6 Oct: 50% on 18 test weeks.
#    • The current, unfinished week is resampled to a FUTURE Friday label (6 Oct run: "Week
#      of 2026-10-09") and its Target is a fabricated 0: (NaN > 0).astype(int) == 0.
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_fung_hsieh_filter_v1_3.py

# ════════════════════════════════════════════════════════════
# ── CONFIG ──────────────────────────────────────────────────
import argparse
import os
import pathlib
import sys

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
_parser = argparse.ArgumentParser(description="AVSHUNTER Fung-Hsieh weekly macro filter")
_parser.add_argument("--output-dir", default=os.environ.get("AVSH_FH_OUTPUT_DIR"),
                     help="write here instead of dropbox\\market_data (for testing)")
_args, _ = _parser.parse_known_args()   # Colab passes its own kernel arguments
if _args.output_dir:
    OUTPUT_DIR = pathlib.Path(_args.output_dir)
else:
    OUTPUT_DIR = REPO_ROOT / "dropbox" / "market_data"
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR = pathlib.Path("/content")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
print(f"📁 OUTPUT_DIR: {OUTPUT_DIR}")
# ════════════════════════════════════════════════════════════

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV

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

tickers = {
    "SPY":"SPY","IWM":"IWM","UUP":"UUP",
    "TLT":"TLT","IEF":"IEF","GLD":"GLD","USO":"USO",
    "HYG":"HYG",   # FIX v1.2: credit proxy added
}

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

end_date   = datetime.today().strftime('%Y-%m-%d')
start_date = (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')

price_data = {}
for name, ticker in tickers.items():
    series = fetch_polygon_weekly(ticker, start_date, end_date)
    if series is not None and not series.empty:
        price_data[name] = series; print(f"✅ {name}")
    else:
        print(f"⚠️ Failed: {name}")

data           = pd.DataFrame(price_data)
weekly_data    = data.resample('W-FRI').last()
weekly_returns = weekly_data.pct_change().dropna()

# ── Fung-Hsieh factors ────────────────────────────────────────────────────────
factors = pd.DataFrame(index=weekly_returns.index)
risk_free_weekly = 0.05 / 52
factors["SNPMRF"]   = weekly_returns["SPY"] - risk_free_weekly
factors["SCMLC"]    = weekly_returns["IWM"] - weekly_returns["SPY"]
factors["BD10RET"]  = weekly_returns["TLT"] - weekly_returns["IEF"]
factors["PTFSCOM"]  = (weekly_returns["USO"] + weekly_returns["GLD"]) / 2
factors["PTFSFX"]   = weekly_returns["UUP"]
factors["PTFSBD"]   = weekly_returns["TLT"]

# FIX v1.2: credit factor
if "HYG" in weekly_returns.columns:
    factors["BD_HYG"] = weekly_returns["HYG"]   # credit spread proxy (HY bond returns)
    print(f"\n💳 BD_HYG factor active — HYG latest return: {weekly_returns['HYG'].iloc[-1]*100:.2f}%")
else:
    print("\n⚠️  HYG MISSING — BD_HYG credit factor absent, credit risk neutral")

for col in factors.columns:
    factors[f'{col}_sharpe'] = factors[col].rolling(12).mean() / factors[col].rolling(12).std()
    factors[f'{col}_roc']    = factors[col].pct_change(periods=12)
    factors[f'{col}_z']      = (factors[col] - factors[col].rolling(12).mean()) / factors[col].rolling(12).std()

factors['Target'] = (weekly_returns['SPY'].shift(-1) > 0).astype(int)
factors = factors.dropna()

X = factors[[c for c in factors.columns if '_sharpe' in c or '_roc' in c or '_z' in c]]
y = factors['Target']
X = X.replace([np.inf,-np.inf], np.nan).dropna()
y = y.loc[X.index]

scaler   = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42, stratify=y)

voter = VotingClassifier(estimators=[
    ('gbc',   GradientBoostingClassifier(n_estimators=150, random_state=42)),
    ('rf',    RandomForestClassifier(n_estimators=100, random_state=42)),
    ('logit', LogisticRegression(max_iter=500, random_state=42))
], voting='soft')

voter.fit(X_train, y_train)
model = CalibratedClassifierCV(voter, method='isotonic', cv=5)
model.fit(X_train, y_train)

probs  = model.predict_proba(X_test)[:, 1]
y_pred = (probs >= 0.65).astype(int)
acc    = accuracy_score(y_test, y_pred)
print(f"\n✅ Adjusted Accuracy: {acc:.2%}")

report    = classification_report(y_test, y_pred, output_dict=True)
report_df = pd.DataFrame(report).T
print(report_df)

gbc = voter.named_estimators_['gbc']
importance = pd.Series(gbc.feature_importances_, index=X.columns)
if plt is not None:
    importance.sort_values(ascending=False).plot(
        kind='bar', figsize=(10,5), title='Weekly Feature Importance (v1.2 — HYG added)')
    plt.tight_layout(); plt.show()

    factors.drop(columns='Target').cumsum().plot(
        figsize=(12,6), title='Cumulative Weekly Returns — Fung-Hsieh Factors (v1.2)')
    plt.grid(True); plt.tight_layout(); plt.show()

macro_bias    = 'Bullish' if acc >= 0.7 else 'Cautious / Tier 2'
macro_go_flag = 'GO'      if acc >= 0.7 else 'NO-GO'
top_drivers   = importance.sort_values(ascending=False).head(3).index.tolist()
credit_active = "HYG" in weekly_returns.columns

print(f"""
🧠 AVSHUNTER MACRO FILTER v1.2
Week of: {weekly_returns.index[-1].strftime('%Y-%m-%d')}
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
    'Week':          weekly_returns.index[-1].strftime('%Y-%m-%d'),
    'Accuracy':      acc,
    'Bias':          macro_bias,
    'GO_NO_GO':      macro_go_flag,
    'Top1':          top_drivers[0],
    'Top2':          top_drivers[1],
    'Top3':          top_drivers[2],
    'Credit_Active': credit_active,   # FIX v1.2
}])

# FIX v1.2: OUTPUT_DIR
try:
    macro_summary.to_csv(OUTPUT_DIR / "avshunter_macro_filter_summary.csv", index=False)
except OSError as e:
    print(f"\n❌ CSV save failed: {e}")
    if not IN_COLAB:
        sys.exit(1)
    raise
print(f"📁 {OUTPUT_DIR / 'avshunter_macro_filter_summary.csv'}")

print(f"\n✅ v1.3 COMPLETE — outputs → {OUTPUT_DIR}")
print("   • HYG credit factor (BD_HYG) added to feature set")
print("   • Credit_Active column in summary CSV")
