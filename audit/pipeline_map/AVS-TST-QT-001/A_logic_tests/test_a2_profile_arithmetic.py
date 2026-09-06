"""Track A2 - Market Profile arithmetic on REAL bars, plus the truncation-error
analysis A1 asks for. Read-only: parquet payloads are opened, never written."""
import sys, pathlib, sqlite3, unittest, math
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from datetime import datetime, timezone
from market_structure.profile import build_market_profile, profile_bin_width, round_to_tick
from market_structure.params import MS_PARAMS_V1 as P

CON = sqlite3.connect(f"file:{ROOT}/data/canonical/control_plane.sqlite?mode=ro", uri=True)
def load(tkr):
    u = list(CON.execute(
        "select storage_uri from dataset_registry where dataset_type='INTRADAY_BAR' and instrument_id=?",
        (tkr,)))[0][0]
    df = pd.read_parquet(u)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.sort_values("timestamp_utc").reset_index(drop=True)

OPEN_UTC = datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc)
ATR = 3.0
RESULTS = []
def rec(cid, expected, actual):
    RESULTS.append((cid, str(expected), str(actual), "Y" if expected == actual else "N"))

def independent_profile(df, tick, atr):
    """My own TPO implementation, written from AVS-SD-002 s9.1-9.5."""
    width = round_to_tick(max(tick, atr / P.bin_divisor), tick)
    lo = math.floor(df["low"].min() / width) * width
    hi = math.ceil(df["high"].max() / width) * width
    n = int(round((hi - lo) / width)) + 1
    levels = np.array([round(lo + i * width, 10) for i in range(n)])
    counts = np.zeros(n, dtype=int)
    open_ts = pd.Timestamp(OPEN_UTC)
    seen = [set() for _ in range(n)]
    for row in df.itertuples():
        period = max(0, int((pd.Timestamp(row.timestamp_utc) - open_ts).total_seconds()
                            // (P.tpo_period_minutes * 60)))
        i0 = int(round((math.floor(row.low / width) * width - lo) / width))
        i1 = int(round((math.ceil(row.high / width) * width - lo) / width))
        for i in range(max(0, i0), min(n - 1, i1) + 1):
            if period not in seen[i]:
                seen[i].add(period); counts[i] += 1
    poc_i = int(np.flatnonzero(counts == counts.max())[-1])
    target = counts.sum() * P.value_area_share
    low = high = poc_i; acc = counts[poc_i]
    while acc < target and (low > 0 or high < n - 1):
        below = counts[low - 1] if low > 0 else -1
        above = counts[high + 1] if high < n - 1 else -1
        if above >= below: high += 1; acc += counts[high]
        else: low -= 1; acc += counts[low]
    return float(levels[poc_i]), float(levels[high]), float(levels[low]), width, int(counts.sum())

class A2(unittest.TestCase):
    def test_PROF_BIN_01_nominal(self):
        w = profile_bin_width(exchange_tick=0.01, atr14=2.0)
        rec("PROF-BIN-01", 0.05, round(w, 10)); self.assertAlmostEqual(w, 0.05)

    def test_PROF_BIN_02_tick_floor(self):
        w = profile_bin_width(exchange_tick=0.01, atr14=0.2)
        rec("PROF-BIN-02", 0.01, round(w, 10)); self.assertAlmostEqual(w, 0.01)

    def test_PROF_BIN_03_atr_null_or_zero(self):
        got = []
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            try:
                profile_bin_width(exchange_tick=0.01, atr14=bad); got.append(("NO_RAISE", bad))
            except ValueError: got.append("ValueError")
        rec("PROF-BIN-03", ["ValueError"] * 4, got)
        self.assertEqual(got, ["ValueError"] * 4)

    def test_PROF_VA_01_and_POC_vs_independent(self):
        df = load("AAPL")
        prod = build_market_profile(df, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
        mine = independent_profile(df, 0.01, ATR)
        print(f"\n  production POC={prod.poc} VAH={prod.value_area_high} VAL={prod.value_area_low} "
              f"width={prod.bin_width} tpo={prod.total_tpo}")
        print(f"  independent POC={mine[0]} VAH={mine[1]} VAL={mine[2]} width={mine[3]} tpo={mine[4]}")
        rec("PROF-VA-01-independent",
            (prod.poc, prod.value_area_high, prod.value_area_low),
            (mine[0], mine[1], mine[2]))
        self.assertLessEqual(prod.value_area_low, prod.poc)
        self.assertLessEqual(prod.poc, prod.value_area_high)

    def test_PROF_VA_01_share_band(self):
        df = load("AAPL")
        p = build_market_profile(df, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
        b = p.bins
        inside = b[(b["price"] >= p.value_area_low) & (b["price"] <= p.value_area_high)]
        share = inside["tpo_count"].sum() / p.total_tpo
        one_bin = b["tpo_count"].max() / p.total_tpo
        print(f"  value-area TPO share={share:.4f} (target 0.70, one bin={one_bin:.4f})")
        rec("PROF-VA-01-share", "0.70 <= share <= 0.70+one_bin",
            f"{share:.4f} within [{0.70:.2f},{0.70+one_bin:.4f}]")
        self.assertGreaterEqual(share, 0.70)
        self.assertLessEqual(share, 0.70 + one_bin + 1e-9)

    def test_PROF_POC_03_determinism_under_shuffle(self):
        df = load("AAPL")
        a = build_market_profile(df, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
        sh = df.sample(frac=1.0, random_state=7).reset_index(drop=True)
        b = build_market_profile(sh, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
        got = (a.poc == b.poc, a.value_area_high == b.value_area_high,
               a.value_area_low == b.value_area_low, a.total_tpo == b.total_tpo)
        rec("PROF-POC-03", (True, True, True, True), got)
        self.assertEqual(got, (True, True, True, True))

    def test_A1_truncation_error_on_real_bars(self):
        """What a 70-77 bar profile does to POC/VAH/VAL versus the full frame."""
        df = load("AAPL")
        base = build_market_profile(df, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
        print(f"\n  reference {len(df)} bars: POC={base.poc} VAH={base.value_area_high} VAL={base.value_area_low}")
        print(f"  {'bars':>5s} {'cov':>7s} {'dPOC':>8s} {'dVAH':>8s} {'dVAL':>8s}")
        rows = []
        for drop in range(0, 8):
            sub = df.iloc[: len(df) - drop] if drop else df
            p = build_market_profile(sub, exchange_tick=0.01, atr14=ATR, regular_open_utc=OPEN_UTC)
            cov = len(sub) / 78.0
            d = (abs(p.poc - base.poc), abs(p.value_area_high - base.value_area_high),
                 abs(p.value_area_low - base.value_area_low))
            rows.append((len(sub), cov, *d))
            print(f"  {len(sub):5d} {cov:7.4f} {d[0]:8.2f} {d[1]:8.2f} {d[2]:8.2f}")
        atr_units = [(n, c, dp / ATR, dh / ATR, dl / ATR) for n, c, dp, dh, dl in rows]
        print("  (same, in ATR units)")
        for n, c, dp, dh, dl in atr_units:
            print(f"  {n:5d} {c:7.4f} {dp:8.3f} {dh:8.3f} {dl:8.3f}")
        RESULTS.append(("A1-TRUNCATION-ERROR", "measured", str(rows), "-"))

if __name__ == "__main__":
    unittest.main(exit=False, verbosity=2)
    print("\n==== A2 PRE-REGISTERED RESULTS ====")
    for cid, e, a, ok in RESULTS:
        print(f"{cid:26s} agrees={ok}\n    expected={e}\n    actual  ={a}")
