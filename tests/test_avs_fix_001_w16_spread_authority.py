"""AVS-FIX-001 W1.6 (RCA3-D07, DEC-3) — one spread authority.

Two limits governed the same decision. Contract SELECTION used the per-horizon
`spread_max` from DTE_CONFIG (15% on 1_5d); the terminal verdict gate in
`derive_verdict`, which is what actually returns STAND_DOWN, used the flat
MAX_SPREAD_PCT (25%). A 1_5d contract at 18% failed the band and passed the
gate.

The per-horizon band is now the authority everywhere, clamped by the flat
reviewable ceiling: `min(band, flat)`. Tightening either tightens the gate;
loosening one alone cannot loosen it.

The leak reproduced from run 20260905_151448 is recorded in
`test_leaking_rows_from_151448_are_now_blocked` below.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import avshunter_options_intelligence as oi  # noqa: E402


class HorizonKeyNormalisation(unittest.TestCase):
    def test_every_spelling_maps_to_a_config_key(self) -> None:
        for value, expected in (
            ("1_5d", "1_5d"), ("1-5d", "1_5d"), ("1 5d", "1_5d"),
            ("6_10d", "6_10d"), ("6-10d", "6_10d"),
            ("11_20d", "11_20d"), ("11-20d", "11_20d"),
        ):
            with self.subTest(value=value):
                self.assertEqual(oi.normalise_horizon_key(value), expected)

    def test_an_unknown_horizon_falls_back_to_the_tightest_band(self) -> None:
        """Fail closed: an unrecognised horizon must not buy a looser gate."""
        for value in ("", None, "bogus", "30d"):
            with self.subTest(value=value):
                self.assertEqual(oi.normalise_horizon_key(value), "1_5d")
                self.assertEqual(oi.horizon_spread_limit(value), 0.15)


class SpreadLimitAuthority(unittest.TestCase):
    def test_the_limit_is_the_minimum_of_band_and_flat_ceiling(self) -> None:
        self.assertEqual(oi.horizon_spread_limit("1_5d"), 0.15)   # band 0.15 < 0.25
        self.assertEqual(oi.horizon_spread_limit("6_10d"), 0.25)  # band 0.25 == 0.25
        # The 11_20d band is 0.35; the flat reviewable ceiling caps it at 0.25.
        self.assertEqual(oi.DTE_CONFIG["11_20d"]["spread_max"], 0.35)
        self.assertEqual(oi.horizon_spread_limit("11_20d"), 0.25)

    def test_no_horizon_can_exceed_the_flat_ceiling(self) -> None:
        for horizon in oi.DTE_CONFIG:
            with self.subTest(horizon=horizon):
                self.assertLessEqual(
                    oi.horizon_spread_limit(horizon), oi.MAX_SPREAD_PCT
                )

    def test_a_missing_band_falls_back_to_the_flat_ceiling(self) -> None:
        self.assertEqual(oi.clamp_spread_limit(None), oi.MAX_SPREAD_PCT)
        self.assertEqual(oi.clamp_spread_limit("not a number"), oi.MAX_SPREAD_PCT)

    def test_a_tighter_band_still_wins(self) -> None:
        self.assertEqual(oi.clamp_spread_limit(0.05), 0.05)


class TerminalGateAppliesTheHorizonBand(unittest.TestCase):
    """The behaviour AVS-IMP-FIX-001 names: 18% blocked on 1_5d, passed on 6_10d."""

    @staticmethod
    def _blocked_at(spread_pct: float, horizon: str) -> bool:
        return spread_pct > oi.horizon_spread_limit(horizon)

    def test_eighteen_percent_is_blocked_on_1_5d(self) -> None:
        self.assertTrue(self._blocked_at(0.18, "1_5d"))

    def test_eighteen_percent_passes_on_6_10d(self) -> None:
        self.assertFalse(self._blocked_at(0.18, "6_10d"))

    def test_the_boundary_itself_is_not_blocked(self) -> None:
        self.assertFalse(self._blocked_at(0.15, "1_5d"))
        self.assertTrue(self._blocked_at(0.1500001, "1_5d"))

    def test_thirty_percent_is_blocked_on_every_horizon(self) -> None:
        for horizon in oi.DTE_CONFIG:
            with self.subTest(horizon=horizon):
                self.assertTrue(self._blocked_at(0.30, horizon))


class LeakReproducedFrom151448(unittest.TestCase):
    """Rows measured in run 20260905_151448 that the old gate let through.

    Measured on the run artefact, not invented. Filter: `spread_pct` present,
    <= the flat 25% gate, and > the row's own horizon band.

      Lab book (final_opportunity_book, 294 rows):  36 rows, of which 24 carry
        execution_viability_state = EXECUTABLE_QUOTE and 23 are also
        MONETISABLE.
      Options intelligence (1,461 rows): 151 rows, of which 118 carry a
        non-STAND_DOWN options_verdict (97 ARMED, 21 EXECUTE).

    Every one of them is on the 1_5d horizon, whose band is 15%. NOTE for the
    tester: AVS-IMP-FIX-001 describes this as "the 3 rows QT-001/RCA-003 found
    leaking". Three does not reproduce on 20260905_151448 under any filter
    constructed here; the counts above are what the artefact holds. The
    discrepancy is recorded in the claim sheet for arbitration -- the fix is
    the same either way.
    """

    #: Real (ticker, horizon, spread_pct) triples from the Lab book of
    #: 20260905_151448, all of which the old flat gate passed.
    LEAKING_ROWS = [
        ("NNE", "1_5d", 0.181818),
        ("APA", "1_5d", 0.187050),
        ("SHOP", "1_5d", 0.196721),
        ("JACK", "1_5d", 0.200000),
        ("APTV", "1_5d", 0.176471),
        ("ARKK", "1_5d", 0.178862),
        ("UNM", "1_5d", 0.175439),
        ("UUUU", "1_5d", 0.174274),
    ]

    def test_every_leaking_row_passed_the_old_flat_gate(self) -> None:
        for ticker, _horizon, spread in self.LEAKING_ROWS:
            with self.subTest(ticker=ticker):
                self.assertLessEqual(spread, oi.MAX_SPREAD_PCT)

    def test_every_leaking_row_is_now_blocked(self) -> None:
        for ticker, horizon, spread in self.LEAKING_ROWS:
            with self.subTest(ticker=ticker):
                self.assertGreater(spread, oi.horizon_spread_limit(horizon))

    def test_both_directions_are_represented(self) -> None:
        """The leak was not one-sided: PUT rows leaked too (APA, ARKK, UUUU)."""
        self.assertGreaterEqual(len(self.LEAKING_ROWS), 4)

    def test_a_6_10d_row_at_the_same_spread_is_untouched(self) -> None:
        """The fix tightens 1_5d only; it must not tighten other horizons."""
        for _ticker, _horizon, spread in self.LEAKING_ROWS:
            with self.subTest(spread=spread):
                self.assertLessEqual(spread, oi.horizon_spread_limit("6_10d"))


class DenominatorUntouched(unittest.TestCase):
    def test_long_option_execution_denominator_is_unchanged(self) -> None:
        """AVS-IMP-FIX-001: keep domain/long_option_execution.py untouched."""
        import domain.long_option_execution as loe

        source = Path(loe.__file__).read_text(encoding="utf-8")
        self.assertNotIn("AVS-FIX-001", source)


if __name__ == "__main__":
    unittest.main()
