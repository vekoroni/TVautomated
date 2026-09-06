"""Track A8 - Worker 3 behavioural engine boundary tests. Read-only import of
the staging package; nothing is written to it and no network call is made."""
import sys, pathlib, unittest
W3 = pathlib.Path(r"C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation")
sys.path.insert(0, str(W3))
from worker3.behaviour import analyse_behaviour, DailyBar, DailyEvidence

RESULTS = []
def rec(cid, expected, actual):
    RESULTS.append((cid, str(expected), str(actual), "Y" if expected == actual else "N"))

def bars(n=12, up=True, span=1.0, start=100.0, step=1.0):
    """Monotone staircase so lows/highs strictly rise (or fall) window over window."""
    out = []
    for i in range(n):
        base = start + (step * i if up else -step * i)
        o, c = (base, base + span) if up else (base, base - span)
        lo, hi = min(o, c), max(o, c)
        out.append(DailyBar(session=f"2026-0{(i//28)+1}-{(i%28)+1:02d}", open=o, high=hi,
                            low=lo, close=c, volume=1000.0,
                            available_at=f"2026-0{(i//28)+1}-{(i%28)+1:02d}T21:00:00Z"))
    return tuple(out)

def ev(bs):
    return DailyEvidence(ticker="TST", source_id="S", source_hash="a1"*32,
                         adjustment_basis="SPLIT", bars=bs,
                         expected_sessions=tuple(b.session for b in bs),
                         cutoff="2026-02-01T21:00:00Z", price_currency="USD",
                         volume_unit="shares")

class A8(unittest.TestCase):
    def test_W3_01_buyer_control(self):
        r = analyse_behaviour(ev(bars(12, up=True, step=2.0, span=1.0)))
        print(f"  rising: control={r['control']} disp={r['metrics'].get('range_normalized_displacement'):.4f}")
        rec("W3-01", "BUYER_CONTROL_PROXY", r["control"])
        self.assertEqual(r["control"], "BUYER_CONTROL_PROXY")

    def test_W3_02_seller_mirror(self):
        r = analyse_behaviour(ev(bars(12, up=False, step=2.0, span=1.0)))
        print(f"  falling: control={r['control']} disp={r['metrics'].get('range_normalized_displacement'):.4f}")
        rec("W3-02", "SELLER_CONTROL_PROXY", r["control"])
        self.assertEqual(r["control"], "SELLER_CONTROL_PROXY")

    def test_W3_03_displacement_boundary(self):
        """displacement >= 0.25 qualifies; just under does not."""
        got = {}
        for step, span in ((2.0, 1.0), (0.30, 8.0)):
            r = analyse_behaviour(ev(bars(12, up=True, step=step, span=span)))
            got[(step, span)] = (round(r["metrics"]["range_normalized_displacement"], 4), r["control"])
        for k, v in got.items(): print(f"  step/span {k}: disp={v[0]} control={v[1]}")
        hi = [v for v in got.values() if v[0] >= 0.25]
        lo = [v for v in got.values() if v[0] < 0.25]
        ok = all(v[1] == "BUYER_CONTROL_PROXY" for v in hi) and all(v[1] == "CONTESTED" for v in lo)
        rec("W3-03", True, ok); self.assertTrue(ok)

    def test_W3_06_insufficient_data_not_a_score(self):
        r = analyse_behaviour(ev(bars(11, up=True, step=2.0)))
        got = (r["status"], r["control"], r["phase"])
        print(f"  11 bars -> status={got[0]} control={got[1]} phase={got[2]}")
        rec("W3-06", ("INSUFFICIENT_DATA", "UNDETERMINED", "NOT_ASSIGNED"), got)
        self.assertEqual(got, ("INSUFFICIENT_DATA", "UNDETERMINED", "NOT_ASSIGNED"))

    def test_W3_authority_is_advisory_and_uncalibrated(self):
        r = analyse_behaviour(ev(bars(12, up=True, step=2.0)))
        got = (r["authority"], r["calibrated"], r["phase"])
        print(f"  authority={got[0]} calibrated={got[1]} phase={got[2]}")
        rec("W3-authority", ("ADVISORY_ONLY", False, "NOT_ASSIGNED"), got)
        self.assertEqual(r["authority"], "ADVISORY_ONLY")
        self.assertFalse(r["calibrated"])
        self.assertEqual(r["phase"], "NOT_ASSIGNED")   # never asserts a Wyckoff phase

    def test_W3_07_invalid_geometry_rejected(self):
        with self.assertRaises(Exception):
            DailyBar(session="2026-01-01", open=100.0, high=99.0, low=101.0,
                     close=100.0, volume=1.0, available_at="2026-01-01T21:00:00Z")
        rec("W3-07-geometry", "ContractError", "ContractError")

if __name__ == "__main__":
    unittest.main(exit=False, verbosity=2)
    print("\n==== A8 PRE-REGISTERED RESULTS ====")
    for cid, e, a, ok in RESULTS:
        print(f"{cid:18s} agrees={ok}  expected={e}  actual={a}")
