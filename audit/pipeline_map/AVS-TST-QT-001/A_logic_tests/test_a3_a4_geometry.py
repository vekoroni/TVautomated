"""Track A3 (Layer-2 scoring) and A4 (geometry / null-target guard).
Three-direction discipline throughout. Read-only imports."""
import sys, pathlib, unittest, math
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import importlib.util as ilu
spec = ilu.spec_from_file_location("oi", ROOT / "scripts" / "avshunter_options_intelligence.py")
OI = ilu.module_from_spec(spec); spec.loader.exec_module(OI)

from vanguard.layer2_statistical.edge_detector import EdgeDetector
from vanguard.schemas.auction_schema import (AuctionVerdict, MarketProfile,
                                             AcceptanceState, ControlState, MigrationState)
import pandas as pd

RESULTS = []
def rec(cid, expected, actual):
    RESULTS.append((cid, str(expected), str(actual), "Y" if expected == actual else "N"))

def verdict(state, poc):
    return AuctionVerdict(
        ready_to_trade=False, confidence=1.0, auction_state=state,
        profile=MarketProfile(poc=poc, value_area_high=poc, value_area_low=poc,
                              profile_type="X", balance="U", tpo_distribution={},
                              timestamp=pd.Timestamp.now(tz="UTC"), timeframe="GOVERNED"),
        acceptance=AcceptanceState(level=100.0, score=0.0, classification="C",
                                   position_in_profile="INSIDE_VALUE"),
        control=ControlState(controller="BUYERS", confidence=1.0, interpretation=""),
        migration=MigrationState(direction="UNKNOWN", speed="UNKNOWN",
                                 consistency="UNKNOWN", magnitude=0.0, interpretation=""),
        scenarios={}, reasoning="")

class _S:  # minimal state/outcomes stubs
    confidence = 1.0; trend_direction = "UP"; intraday_rows = None; positional_strategy = True
    macro_regime = "TRANSITIONAL"; catalyst_proximity = "NONE"; volatility_regime = "NORMAL"
    def __getattr__(self, name): return "NONE"
class _O:
    confidence_level = 1.0; prob_up_10pct_20d = 0.5; prob_trend_continues_20d = 0.5
    n_observations = 100
    def __getattr__(self, name): return 0.0

class A3(unittest.TestCase):
    def setUp(self): self.d = EdgeDetector()

    def test_L2_01_no_profile_zeroes_alignment_and_conf(self):
        got = {}
        for state in ("ALIGNED", "TRANSITIONING", "SEARCHING"):
            s_none = self.d._calculate_right_side_score(_S(), _O(), verdict(state, None))
            s_zero = self.d._calculate_right_side_score(_S(), _O(), verdict(state, 0.0))
            s_real = self.d._calculate_right_side_score(_S(), _O(), verdict(state, 100.0))
            got[state] = (s_none, s_zero, s_real)
            print(f"  {state:14s} poc=None:{s_none:6.1f}  poc=0.0:{s_zero:6.1f}  poc=100:{s_real:6.1f}")
        # None and 0.0 must score identically; real POC must score strictly higher
        ok = all(g[0] == g[1] and g[2] > g[0] for g in got.values())
        rec("L2-01/L2-03", True, ok); self.assertTrue(ok)

    def test_L2_03_uplift_delta_is_the_designed_25_15_5(self):
        deltas = {}
        for state, exp in (("ALIGNED", 25), ("TRANSITIONING", 15), ("SEARCHING", 5)):
            hi = self.d._calculate_right_side_score(_S(), _O(), verdict(state, 100.0))
            lo = self.d._calculate_right_side_score(_S(), _O(), verdict(state, None))
            deltas[state] = round(hi - lo, 6)
        rec("L2-03-deltas", {"ALIGNED": 25, "TRANSITIONING": 15, "SEARCHING": 5}, deltas)
        print(f"  uplift deltas: {deltas}")
        self.assertEqual(deltas, {"ALIGNED": 25.0, "TRANSITIONING": 15.0, "SEARCHING": 5.0})

class A4(unittest.TestCase):
    IV = {"iv_percentile": 50, "ivp_label": "MID"}
    C = {"mark": 2.0, "strike": 100.0, "theta": -0.01, "vega": 0.05, "delta": 0.35, "dte": 30}

    def ctx(self, direction, target, entry=100.0, stop=95.0):
        return {"spot": 100.0, "entry": entry, "structural_target": target,
                "hold_days": 5, "direction": direction, "win_prob": 50.0, "stop": stop}

    def test_GEO_03_04_05_null_target_all_directions(self):
        got = {}
        for direction in ("CALL", "PUT"):
            for label, tgt in (("None", None), ("NaN", float("nan")),
                               ("inf", float("inf")), ("zero", 0.0), ("negative", -5.0)):
                r = OI.compute_trade_economics(self.C, self.ctx(direction, tgt), self.IV)
                got[(direction, label)] = (r.get("economics_state"), r.get("economics_reason"))
        for k, v in got.items(): print(f"  {k}: {v}")
        expected = ("NOT_EVALUATED", "STRUCTURAL_TARGET_UNRESOLVED")
        ok = all(v == expected for v in got.values())
        rec("GEO-03/04/05", True, ok)
        self.assertTrue(ok, f"a direction/value combination escaped the guard: {got}")

    def test_GEO_07_other_direction_not_applicable(self):
        got = {}
        for direction in ("STRANGLE", "UNRESOLVED", "", "NONE"):
            r = OI.compute_trade_economics(self.C, self.ctx(direction, 110.0), self.IV)
            got[direction] = (r.get("economics_state"), r.get("economics_reason"))
        for k, v in got.items(): print(f"  {k!r}: {v}")
        ok = all(v[0] == "NOT_EVALUATED" and "NON_DIRECTIONAL" in str(v[1]) for v in got.values())
        rec("GEO-07", True, ok); self.assertTrue(ok)

    def test_GEO_01_02_mirror_symmetry(self):
        call = OI.compute_trade_economics(
            {**self.C, "strike": 100.0}, self.ctx("CALL", 110.0, 100.0, 95.0), self.IV)
        put = OI.compute_trade_economics(
            {**self.C, "strike": 100.0}, self.ctx("PUT", 90.0, 100.0, 105.0), self.IV)
        pair = (call.get("target_gain_underlying"), put.get("target_gain_underlying"),
                call.get("option_value_at_target"), put.get("option_value_at_target"),
                call.get("rr_options"), put.get("rr_options"))
        print(f"  CALL gain={pair[0]} optval={pair[2]} rr={pair[4]}")
        print(f"  PUT  gain={pair[1]} optval={pair[3]} rr={pair[5]}")
        rec("GEO-01/02-mirror",
            "CALL and PUT mirror identical",
            f"gain {pair[0]}=={pair[1]}, optval {pair[2]}=={pair[3]}, rr {pair[4]}=={pair[5]}")
        self.assertEqual(pair[0], pair[1]); self.assertEqual(pair[2], pair[3])
        self.assertEqual(pair[4], pair[5])

    def test_GEO_06_wrong_side_stop(self):
        """CALL with a stop ABOVE entry is geometrically invalid."""
        r = OI.compute_trade_economics(self.C, self.ctx("CALL", 110.0, 100.0, 105.0), self.IV)
        print(f"  CALL entry=100 stop=105 (wrong side) -> state={r.get('economics_state')} "
              f"reason={r.get('economics_reason')}")
        rec("GEO-06", "rejected or flagged", f"{r.get('economics_state')}/{r.get('economics_reason')}")

if __name__ == "__main__":
    unittest.main(exit=False, verbosity=2)
    print("\n==== A3/A4 PRE-REGISTERED RESULTS ====")
    for cid, e, a, ok in RESULTS:
        print(f"{cid:20s} agrees={ok}  expected={e}  actual={a}")
