"""Track A1 - completed-profile coverage and the 90/95 gate question.
Imports production modules read-only. Never writes to production paths."""
import sys, pathlib, unittest
from datetime import date, datetime, timezone, timedelta
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import pandas as pd
from canonical_data.session_clock import session_bounds
from scripts.build_completed_market_profiles import _quality_diagnostics as EVAL  # noqa

SESSION = date(2026, 9, 3)
OPEN_UTC, CLOSE_UTC = session_bounds(SESSION)

def frame(n_bars=78, drop_first=False, drop_last=False, drop_interior=0, interval=5):
    """RTH bar-open grid 09:30..15:55 inclusive."""
    stamps = [OPEN_UTC + timedelta(minutes=interval * i)
              for i in range(int((CLOSE_UTC - OPEN_UTC).total_seconds() // 60 // interval))]
    keep = list(stamps)
    if drop_last:  keep = keep[:-1]
    if drop_first: keep = keep[1:]
    if drop_interior:
        mid = len(keep) // 2
        del keep[mid:mid + drop_interior]
    keep = keep[:n_bars] if n_bars < len(keep) else keep
    return pd.DataFrame({
        "timestamp_utc": keep,
        "open": [100.0] * len(keep), "high": [101.0] * len(keep),
        "low": [99.0] * len(keep), "close": [100.5] * len(keep),
        "volume": [1000.0] * len(keep),
        "session_segment": ["REGULAR"] * len(keep),
        "provider_http_status": [200] * len(keep),
    })

def ev(df):
    return EVAL(frame=df, session_date=SESSION, open_utc=OPEN_UTC,
                close_utc=CLOSE_UTC, interval_minutes=5)

RESULTS = []
def rec(cid, expected, actual):
    RESULTS.append((cid, expected, actual, "Y" if expected == actual else "N"))

class A1(unittest.TestCase):
    def test_expected_grid_is_78(self):
        usable, d = ev(frame())
        self.assertEqual(d["expected_regular_bars"], 78)

    def test_PROF_COV_01_full(self):
        usable, d = ev(frame())
        rec("PROF-COV-01", (True, 1.0, True, True),
            (usable, d["coverage_ratio"], d["first_region_present"], d["last_region_present"]))
        self.assertTrue(usable); self.assertEqual(d["coverage_ratio"], 1.0)

    def test_PROF_COV_02_last_bar_missing(self):
        usable, d = ev(frame(drop_last=True))
        rec("PROF-COV-02", (False, False), (usable, d["last_region_present"]))
        self.assertFalse(usable); self.assertFalse(d["last_region_present"])
        self.assertGreater(d["coverage_ratio"], 0.95)   # coverage was never the constraint

    def test_PROF_COV_03_first_bar_missing(self):
        usable, d = ev(frame(drop_first=True))
        rec("PROF-COV-03", (False, False), (usable, d["first_region_present"]))
        self.assertFalse(usable); self.assertFalse(d["first_region_present"])

    def test_PROF_COV_04_closure_claim(self):
        """77/78 fails under BOTH a 0.95 and a 0.90 coverage gate."""
        usable, d = ev(frame(drop_last=True))
        cov = d["coverage_ratio"]
        would_pass_95 = cov >= 0.95 and d["first_region_present"] and d["last_region_present"]
        would_pass_90 = cov >= 0.90 and d["first_region_present"] and d["last_region_present"]
        rec("PROF-COV-04", (False, False), (would_pass_95, would_pass_90))
        self.assertFalse(would_pass_95); self.assertFalse(would_pass_90)
        self.assertAlmostEqual(cov, 77/78, places=6)

    def test_PROF_COV_05_75_of_78(self):
        usable, d = ev(frame(drop_interior=3))
        rec("PROF-COV-05", "coverage>=0.95", f"cov={d['coverage_ratio']:.6f} usable={usable}")
        self.assertGreaterEqual(d["coverage_ratio"], 0.95)

    def test_PROF_COV_06_71_of_78(self):
        usable, d = ev(frame(drop_interior=7))
        rec("PROF-COV-06", (False, "0.90<=cov<0.95"),
            (usable, f"{d['coverage_ratio']:.6f}"))
        self.assertFalse(usable)
        self.assertGreaterEqual(d["coverage_ratio"], 0.90)
        self.assertLess(d["coverage_ratio"], 0.95)

    def test_PROF_COV_07_70_of_78(self):
        usable, d = ev(frame(drop_interior=8))
        rec("PROF-COV-07", False, usable)
        self.assertFalse(usable)

if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2)
    print("\n==== A1 PRE-REGISTERED RESULTS ====")
    for cid, e, a, ok in RESULTS:
        print(f"{cid:14s} agrees={ok}  expected={e}  actual={a}")
