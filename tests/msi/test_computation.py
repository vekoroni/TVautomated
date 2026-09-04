"""MSI v1.1 independent computation tests (design doc §8.2, §8.4, §8.6, §8.8, §10.1,
§10.2, §10.3, §5.2, §20(8), §23).

Independent test engineer pack. Production code is READ-ONLY; this file only
imports and calls it. Every test's docstring starts with its test ID and the
exact design section it verifies. Hand-computed expected values are shown in
comments alongside the arithmetic that produced them; the assertion then
compares the actual return value against that hand-computed number.

Design document:
  audit/solution_design/MARKET_STRUCTURE_INTERPRETER_DATA_ENHANCEMENT_SOLUTION_DESIGN_20260830.md

Interpreter used to author and execute this file (record for every run):
  .codex_python313_runtime/python.exe  with PYTHONPATH=venv/Lib/site-packages
  (per audit/msi/00_preflight.md "Test runtime" — matches the interpreter the
  implementer used, not venv/Scripts/python.exe).

Run with:
  PYTHONPATH=venv/Lib/site-packages .codex_python313_runtime/python.exe -m pytest tests/msi/test_computation.py -v
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import math
import unittest
from datetime import date, datetime, timezone

import pandas as pd

from canonical_data.marketdata_response import (
    CHAIN_V2_COLUMNS,
    _quote,
    parse_exact_option_quote,
    parse_marketdata_option_response,
)
from canonical_data.intraday_bars import normalise_minute_bars
from market_structure.lifecycle import transition_lifecycle
from market_structure.params import MS_PARAMS_V1
from market_structure.profile import (
    MarketProfile,
    build_market_profile,
    profile_bin_width,
    round_to_tick,
)
from market_structure.service import ALGORITHM_VERSION, _metrics, calculate_market_structure_evidence


# ---------------------------------------------------------------------------
# C-01  (design §8.2 "Quote arithmetic is owned by one shared helper")
# ---------------------------------------------------------------------------
class C01_QuoteArithmetic(unittest.TestCase):
    """C-01 / design §8.2.

    mid = (bid+ask)/2 when both positive; bid=0,ask>0 -> mid=ask/2;
    spread_value = ask-bid; spread_pct = spread_value/mid when mid>0 else null;
    one shared helper used by chain, exact-quote and quote-change code.
    """

    def test_both_sides_positive_mid_and_spread_pct(self):
        # Hand computation: bid=2.00, ask=3.00
        #   mid       = (2.00 + 3.00) / 2      = 2.50
        #   spread_value (design) = 3.00 - 2.00 = 1.00
        #   spread_pct = spread_value / mid     = 1.00 / 2.50 = 0.40
        bid, ask, mid, spread_pct, quality, flags = _quote(2.0, 3.0, None)
        self.assertEqual((bid, ask), (2.0, 3.0))
        self.assertEqual(mid, 2.5)
        self.assertEqual(quality, "TWO_SIDED")
        self.assertAlmostEqual(spread_pct, 1.0 / 2.5)
        self.assertEqual(spread_pct, 0.4)

    def test_zero_bid_positive_ask_is_one_sided_half_ask_mid(self):
        # Hand computation: bid=0, ask=4.00 -> mid = ask/2 = 2.00
        #   spread_value (design) = 4.00 - 0.00 = 4.00
        #   spread_pct = 4.00 / 2.00 = 2.00
        bid, ask, mid, spread_pct, quality, flags = _quote(0.0, 4.0, None)
        self.assertEqual(mid, 2.0)
        self.assertEqual(quality, "ONE_SIDED")
        self.assertIn("ZERO_BID", flags)
        self.assertEqual(spread_pct, 2.0)
        # design: "the quote is not executable" for the ONE_SIDED case ->
        # verify through the exact-quote entry point, which is the field the
        # rest of the system reads to decide executability.
        payload = {
            "s": "ok", "optionSymbol": ["AAPL260918C00150000"], "side": ["call"],
            "strike": [150.0], "expiration": [1758153600], "dte": [10],
            "bid": [0.0], "ask": [4.0], "mid": [None], "bidSize": [1], "askSize": [1],
            "last": [2.0], "openInterest": [10], "volume": [5], "iv": [0.3],
            "delta": [0.5], "gamma": [0.01], "theta": [-0.02], "vega": [0.05],
            "underlyingPrice": [150.0], "contractMultiplier": [100], "multiplier": [100],
            "updated": [1758100000],
        }
        record = parse_exact_option_quote(payload, ticker="AAPL", symbol="AAPL260918C00150000")
        self.assertFalse(record["executable_now"])

    def test_mid_null_when_bid_and_ask_both_absent(self):
        # Neither side priced -> no mid can be formed, spread_pct is null.
        bid, ask, mid, spread_pct, quality, flags = _quote(None, None, None)
        self.assertIsNone(mid)
        self.assertIsNone(spread_pct)
        self.assertEqual(quality, "INCOMPLETE")

    def test_spread_value_field_is_absent_from_the_schema_FINDING(self):
        """Design §8.2 requires a persisted `spread_value = ask - bid` field.

        `_quote()` (canonical_data/marketdata_response.py:72-90) computes and
        returns only `spread_pct`; it never computes or returns spread_value,
        and `CHAIN_V2_COLUMNS` (same file, lines 14-21) has no `spread_value`
        column. A whole-repo grep for `spread_value` outside backups/docs
        found zero matches in any active module. This is a confirmed defect
        against §8.2, not a vacuous absence-of-evidence claim: the function
        signature was read and the return tuple has no spread_value slot.
        """
        bid, ask, mid, spread_pct, quality, flags = _quote(2.0, 3.0, None)
        returned_fields = {"bid", "ask", "mid", "spread_pct", "quality", "flags"}
        self.assertNotIn("spread_value", CHAIN_V2_COLUMNS)
        self.assertNotIn("spread_value", returned_fields)

    def test_shared_helper_used_by_chain_and_exact_quote_paths(self):
        """`_quote` is the single function both chain parsing and exact-quote
        parsing route through (source evidence:
        canonical_data/marketdata_response.py:118-120 `parse_marketdata_option_response`
        calls `_quote(...)`; :148-158 `parse_exact_option_quote` calls
        `parse_marketdata_option_response`, i.e. transitively the same
        function object, not a duplicated formula).
        """
        source = inspect.getsource(parse_marketdata_option_response)
        self.assertIn("_quote(", source)
        exact_source = inspect.getsource(parse_exact_option_quote)
        self.assertIn("parse_marketdata_option_response(", exact_source)
        # Behavioural cross-check: calling _quote directly and calling it via
        # the chain parser for the same raw bid/ask must produce identical
        # bid/ask/mid/spread_pct/quality — proving one code path, not two.
        direct = _quote(2.0, 3.0, None)
        payload = {
            "s": "ok", "optionSymbol": ["AAPL260918C00150000"], "side": ["call"],
            "strike": [150.0], "expiration": [1758153600], "dte": [10],
            "bid": [2.0], "ask": [3.0], "mid": [None], "bidSize": [1], "askSize": [1],
            "last": [2.5], "openInterest": [10], "volume": [5], "iv": [0.3],
            "delta": [0.5], "gamma": [0.01], "theta": [-0.02], "vega": [0.05],
            "underlyingPrice": [150.0], "contractMultiplier": [100], "multiplier": [100],
            "updated": [1758100000],
        }
        via_chain = parse_marketdata_option_response(payload, ticker="AAPL").iloc[0]
        self.assertEqual((via_chain.bid, via_chain.ask, via_chain.mid, via_chain.spread_pct), direct[:4])

    def test_quote_change_code_does_not_exist_FINDING(self):
        """Design §8.2 says the shared helper is "used by chain, exact-quote
        AND quote-change code". A whole-repo grep (excluding backups/
        _cleanup_holding/Archive/decommissioned) for `contract_bid_change`,
        `contract_mid_change`, `contract_spread_change_pp`, `BASELINE_ZERO`,
        `CONTRACT_CHANGED` (as an exact quote-change enum, not the unrelated
        EV3 economics string `MORNING_CONTRACT_CHANGED_RECOMPUTE_REQUIRED`
        found in morning_gate.py) found no computation anywhere in the
        codebase: contracts/interpreter_handoff_materializer.py:208-224 and
        contracts/lab_evidence_overlay.py:15-21 only declare/pass through the
        field NAMES; nothing computes them. See C-02 for the full test of
        this gap. Recorded here because it means the "one shared helper used
        by...quote-change code" requirement is UNVERIFIABLE by construction:
        there is no quote-change code to check.
        """
        import contracts.interpreter_handoff_materializer as materializer

        materializer_src = inspect.getsource(materializer._bundle)
        # The materializer's quote_change_evidence block is a dict comprehension
        # that copies existing row keys; it contains no arithmetic operators
        # computing a change (no '-', no subtraction helper call).
        self.assertIn("quote_change_evidence", materializer_src)
        self.assertNotIn("_quote(", materializer_src)


# ---------------------------------------------------------------------------
# C-02  (design §8.8 quote_change_evidence_v1)
# ---------------------------------------------------------------------------
class C02_QuoteChangeEvidence(unittest.TestCase):
    """C-02 / design §8.8.

    Absolute and percentage changes for bid, ask, mid between two snapshots
    of the same contract; spread change in percentage points; size changes
    only when both snapshots carry sizes.
    """

    def test_quote_change_computation_is_not_implemented_anywhere_NOT_IMPLEMENTED(self):
        """Exhaustive search for the §8.8 arithmetic.

        Searched (Grep, *.py, whole repo, this session):
          - `contract_bid_change`, `contract_mid_change`,
            `contract_spread_change_pp` -> matches ONLY in
            contracts/lab_evidence_overlay.py (an allow-listed field-name
            set, CURRENT_QUOTE_FIELDS, lines 15-21) and
            contracts/interpreter_handoff_materializer.py (a dict
            comprehension that copies whatever value is already present on
            `row`, lines 208-224). Neither file subtracts, divides, or
            otherwise derives these values from `morning_*` and
            `current_*` quote fields.
          - `BASELINE_ZERO`, `CONTRACT_CHANGED`, `BASELINE_MISSING`,
            `CURRENT_MISSING` (the design's §24 `Comparison` enum) -> the
            only non-backup hits are in morning_gate.py, and inspection
            shows they belong to an unrelated pre-existing EV3
            monetisability-recompute code path
            (`NOT_EVALUATED_CONTRACT_CHANGED` /
            `MORNING_CONTRACT_CHANGED_RECOMPUTE_REQUIRED`), not the MSI
            quote-change comparison_status enum. `BASELINE_ZERO`,
            `BASELINE_MISSING`, `CURRENT_MISSING` do not appear in
            morning_gate.py at all.
          - No module named anywhere in §22 (evidence_resolver.py,
            interpreter_handoff.py, interpreter_handoff_materializer.py,
            lab_evidence_overlay.py, morning_gate.py) contains a function
            that takes two quote snapshots and returns a change record.

        Per rule 5 (no vacuous passes) and rule 6 (two-level closure), this
        cannot be marked PASS on the strength of the allow-listed field
        names alone — that is a schema declaration, not a calculation.
        Verdict recorded in the test-card report: NOT_IMPLEMENTED.
        """
        import contracts.interpreter_handoff_materializer as materializer
        import contracts.lab_evidence_overlay as overlay

        # The declared field names exist (schema is present)...
        for field in (
            "contract_bid_change", "contract_ask_change", "contract_mid_change",
            "contract_spread_change_pp", "comparison_status",
        ):
            self.assertIn(field, overlay.CURRENT_QUOTE_FIELDS)

        # ...but no function in either module performs the subtraction/division
        # arithmetic the design requires. This is verified by source
        # inspection: the only place these names appear in
        # interpreter_handoff_materializer.py is a passthrough dict
        # comprehension `{key: row.get(key) for key in (...)}` with no
        # arithmetic operators over morning_/current_ pairs.
        bundle_source = inspect.getsource(materializer._bundle)
        self.assertIn(
            '"quote_change_evidence": {', bundle_source,
            "expected the passthrough block whose presence is the finding",
        )
        # `current_contract_bid` appears exactly once in the whole module:
        # as the field-name string literal inside the quote_change_evidence
        # tuple. If any code computed a change from it (e.g.
        # `row["current_contract_bid"] - row["morning_contract_bid"]`), the
        # field name would necessarily appear a second time as an operand.
        module_source = inspect.getsource(materializer)
        self.assertEqual(module_source.count("current_contract_bid"), 1)
        self.assertFalse(hasattr(materializer, "compute_quote_change"))


# ---------------------------------------------------------------------------
# C-03  (design §8.4 underlying_intraday_bar_v1 / vwap_canonical)
# ---------------------------------------------------------------------------
class C03_VwapCanonical(unittest.TestCase):
    """C-03 / design §8.4.

    vwap_canonical = cumulative sum(((h+l+c)/3)*v) / sum(v) over
    regular-session bars, reset at regular-session open; premarket bars
    excluded; vwap_provider stored separately and never substituted.

    Source: canonical_data/intraday_bars.py:35-61 `normalise_minute_bars`.
    Note: the function computes vwap for ONE session_segment per call
    (session_segment is a call-level parameter, not a per-row column), so
    the premarket/regular split is exercised here via two separate calls
    concatenated afterward — this is exactly how the only current caller,
    CanonicalMinuteBarResolver.resolve() (same file, line ~154), invokes it.
    """

    def test_premarket_excluded_and_regular_session_cumulative_vwap(self):
        start = pd.Timestamp("2026-01-02T09:00:00Z")
        premarket = pd.DataFrame([
            {"timestamp_utc": start, "open": 99, "high": 99.5, "low": 98.5, "close": 99.0, "volume": 1000},
        ])
        regular = pd.DataFrame([
            {"timestamp_utc": start + pd.Timedelta(minutes=1), "open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 200},
            {"timestamp_utc": start + pd.Timedelta(minutes=2), "open": 100, "high": 102, "low": 100, "close": 101.0, "volume": 300},
        ])
        pre_bars = normalise_minute_bars(premarket, ticker="AAPL", session_segment="PREMARKET")
        reg_bars = normalise_minute_bars(regular, ticker="AAPL", session_segment="REGULAR")

        # Premarket: regular==False everywhere -> numerator/denominator stay
        # 0 -> 0/0 -> NaN. This IS "excluded", not zero.
        self.assertTrue(pd.isna(pre_bars["vwap_canonical"].iloc[0]))

        # Hand computation (regular session only, reset at its own open):
        #   typical1 = (101 + 99 + 100.0) / 3   = 100.0   ; vol1 = 200
        #   typical2 = (102 + 100 + 101.0) / 3  = 101.0   ; vol2 = 300
        #   vwap_bar1 = (100.0*200) / 200                 = 100.0
        #   vwap_bar2 = (100.0*200 + 101.0*300) / (200+300)
        #             = (20000 + 30300) / 500 = 50300/500 = 100.6
        typical1 = (101 + 99 + 100.0) / 3.0
        typical2 = (102 + 100 + 101.0) / 3.0
        expected_bar1 = (typical1 * 200) / 200
        expected_bar2 = (typical1 * 200 + typical2 * 300) / (200 + 300)
        self.assertAlmostEqual(reg_bars["vwap_canonical"].iloc[0], expected_bar1)
        self.assertAlmostEqual(reg_bars["vwap_canonical"].iloc[1], expected_bar2)
        self.assertEqual(expected_bar1, 100.0)
        self.assertEqual(expected_bar2, 100.6)

    def test_vwap_provider_stored_separately_never_substitutes_canonical(self):
        start = pd.Timestamp("2026-01-02T09:31:00Z")
        rows = pd.DataFrame([
            {"timestamp_utc": start, "open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 200, "vw": 999.0},
        ])
        bars = normalise_minute_bars(rows, ticker="AAPL", session_segment="REGULAR")
        # Hand computation: typical = (101+99+100)/3 = 100.0; vwap_canonical = 100.0*200/200 = 100.0
        self.assertEqual(bars["vwap_canonical"].iloc[0], 100.0)
        # Provider VWAP of 999.0 must survive untouched, in a separate column.
        self.assertEqual(bars["vwap_provider"].iloc[0], 999.0)
        self.assertNotEqual(bars["vwap_provider"].iloc[0], bars["vwap_canonical"].iloc[0])


# ---------------------------------------------------------------------------
# C-04  (design §10.1 bin width)
# ---------------------------------------------------------------------------
class C04_BinWidth(unittest.TestCase):
    """C-04 / design §10.1.

    Bin width = round_to_tick(max(exchange_tick, ATR14/40)) with ATR(14) from
    completed daily sessions; verify with a hand-computed ATR and two tick
    sizes. SEED_VALUE: the "40" is `MS_PARAMS_V1.bin_divisor`, a proposed
    calibration seed (design §10.2); this test reads it from configuration
    rather than typing 40 into the assertion, per rule 4.
    """

    def test_hand_computed_atr14_two_tick_sizes(self):
        params = MS_PARAMS_V1
        # Hand-computed ATR14: 14 completed daily sessions, each with
        # True Range = high-low = 2.00 and no overnight gap (previous close
        # inside the day's range), so TR_i = 2.00 for all i=1..14 and
        #   ATR14 = sum(TR_i)/14 = (14*2.00)/14 = 2.00
        # atr14 is deliberately expressed as 0.05 * bin_divisor so the
        # "ATR-driven" case below (tick=0.01) always lands on ATR14/divisor
        # = 0.05 regardless of the configured divisor value (25-60 range).
        atr14 = 0.05 * params.bin_divisor
        self.assertEqual(atr14, 2.0)  # true for the currently configured divisor of 40

        # Case A - ATR-driven (small tick): exchange_tick=0.01
        #   raw   = max(0.01, atr14/divisor) = max(0.01, 0.05) = 0.05
        #   width = round_to_tick(0.05, 0.01) = 0.05
        width_small_tick = profile_bin_width(exchange_tick=0.01, atr14=atr14, params=params)
        self.assertAlmostEqual(width_small_tick, 0.05)

        # Case B - tick-driven (large tick): exchange_tick=5.00
        #   raw   = max(5.00, atr14/divisor) = max(5.00, 0.05) = 5.00
        #   width = round_to_tick(5.00, 5.00) = 5.00
        width_large_tick = profile_bin_width(exchange_tick=5.0, atr14=atr14, params=params)
        self.assertAlmostEqual(width_large_tick, 5.0)

    def test_round_to_tick_rounds_to_nearest_not_floor(self):
        # Hand computation: value=0.074, tick=0.05 -> value/tick=1.48 ->
        # round(1.48)=1 -> 1*0.05=0.05 (rounds down since 1.48 rounds to 1)
        self.assertAlmostEqual(round_to_tick(0.074, 0.05), 0.05)
        # value=0.076, tick=0.05 -> value/tick=1.52 -> round(1.52)=2 -> 0.10
        self.assertAlmostEqual(round_to_tick(0.076, 0.05), 0.10)


# ---------------------------------------------------------------------------
# C-05 / C-07  (design §10.1 TPO participation and one-minute volume allocation)
# ---------------------------------------------------------------------------
class C05C07_TpoAndVolumeAllocation(unittest.TestCase):
    """C-05 / design §10.1 "calculate TPO from bar-range participation" and
    C-06 / design §10.1 value-area expansion and
    C-07 / design §10.1 "allocate each one-minute bar's volume uniformly
    across every intersected price bin and label it ONE_MINUTE_ESTIMATED".

    One shared fixture is used for C-05, C-06 and C-07 because
    `build_market_profile` (market_structure/profile.py:44-67) computes TPO
    counts, value area and volume allocation from the same bins DataFrame in
    a single pass; hand-computing them together keeps the arithmetic
    traceable to one worked example.
    """

    @staticmethod
    def _profile() -> MarketProfile:
        params = MS_PARAMS_V1
        tick = 1.0
        # atr14 chosen so bin width == 1.0 exactly regardless of the
        # configured bin_divisor: atr14/divisor == tick == 1.0.
        atr14 = tick * params.bin_divisor
        open_ts = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
        bars = pd.DataFrame([
            # Bar 1: period 0 (t=+0min), spans bins [100,101,102] (3 bins), vol=300
            {"timestamp_utc": open_ts, "high": 102.0, "low": 100.0, "close": 101.0,
             "volume": 300.0, "session_segment": "REGULAR"},
            # Bar 2: period 0 (t=+5min, same 30-min TPO period), spans
            # bins [101,102,103] (3 bins), vol=300
            {"timestamp_utc": open_ts + pd.Timedelta(minutes=5), "high": 103.0, "low": 101.0,
             "close": 102.0, "volume": 300.0, "session_segment": "REGULAR"},
            # Bar 3: period 1 (t=+31min -> floor(31/30)=1), spans bin [102] only, vol=100
            {"timestamp_utc": open_ts + pd.Timedelta(minutes=31), "high": 102.0, "low": 102.0,
             "close": 102.0, "volume": 100.0, "session_segment": "REGULAR"},
        ])
        return build_market_profile(bars, exchange_tick=tick, atr14=atr14, regular_open_utc=open_ts, params=params)

    def test_c05_tpo_participation_counts_one_per_period_per_bin(self):
        """C-05: a bar spanning N bins increments each of those N bins once
        per period (not once per bar).

        Hand computation of the price-level ladder: bottom=floor(100/1)*1=100,
        top=ceil(103/1)*1=103 -> levels = [100,101,102,103].

        Period participation sets per bin (bar1,bar2 both fall in period 0;
        bar3 falls in period 1):
          bin 100: {bar1(P0)}                          -> periods={0}    -> tpo=1
          bin 101: {bar1(P0), bar2(P0)}                 -> periods={0}    -> tpo=1 (P0 counted once, not twice)
          bin 102: {bar1(P0), bar2(P0), bar3(P1)}       -> periods={0,1}  -> tpo=2
          bin 103: {bar2(P0)}                           -> periods={0}    -> tpo=1
        """
        profile = self._profile()
        bins = profile.bins.set_index("price")
        self.assertEqual(int(bins.loc[100.0, "tpo_count"]), 1)
        self.assertEqual(int(bins.loc[101.0, "tpo_count"]), 1)
        self.assertEqual(int(bins.loc[102.0, "tpo_count"]), 2)
        self.assertEqual(int(bins.loc[103.0, "tpo_count"]), 1)
        self.assertEqual(profile.total_tpo, 1 + 1 + 2 + 1)  # = 5
        # POC is the bin with the max TPO count -> bin 102.
        self.assertEqual(profile.poc, 102.0)

    def test_c06_value_area_expands_from_poc_to_next_higher_adjacent_count(self):
        """C-06: value area = value_area_share (params.value_area_share,
        seed 0.70) of regular-session TPO count, expanding from POC toward
        the next higher adjacent count.

        counts=[1,1,2,1] (indices 0..3), poc_index=2, total=5.
        target = 5 * value_area_share; with the current seed 0.70 -> target=3.5
        Expansion trace (poc_index=2, accumulated=counts[2]=2):
          step1: below=counts[1]=1, above=counts[3]=1 -> above>=below -> take
                 high (tie goes to the higher side per the code's `>=`) ->
                 high=3, accumulated=2+1=3 (< target 3.5, continue)
          step2: below=counts[1]=1, above=n/a (high already at top index 3)
                 -> above=-1 < below -> take low -> low=1,
                 accumulated=3+counts[1]=3+1=4 (>= target 3.5, stop)
        Result: va_low_index=1 (price 101.0), va_high_index=3 (price 103.0)
        """
        params = MS_PARAMS_V1
        profile = self._profile()
        counts = profile.bins["tpo_count"].to_numpy()
        target = counts.sum() * params.value_area_share
        self.assertEqual(list(counts), [1, 1, 2, 1])
        self.assertAlmostEqual(target, 5 * params.value_area_share)
        self.assertEqual(profile.value_area_low, 101.0)
        self.assertEqual(profile.value_area_high, 103.0)

    def test_c07_one_minute_volume_uniformly_allocated_and_labelled(self):
        """C-07: each bar's volume is split evenly across every bin it
        intersects; label ONE_MINUTE_ESTIMATED; total allocated volume ==
        sum of bar volumes.

        Hand computation:
          bar1 vol=300 over 3 bins [100,101,102] -> 100 each
          bar2 vol=300 over 3 bins [101,102,103] -> 100 each
          bar3 vol=100 over 1 bin  [102]          -> 100

          bin100 = 100                              = 100
          bin101 = 100(bar1) + 100(bar2)            = 200
          bin102 = 100(bar1) + 100(bar2) + 100(bar3)= 300
          bin103 = 100(bar2)                        = 100
          total  = 100+200+300+100 = 700 == 300+300+100 (sum of bar volumes)
        """
        profile = self._profile()
        bins = profile.bins.set_index("price")
        self.assertAlmostEqual(bins.loc[100.0, "volume_estimated"], 100.0)
        self.assertAlmostEqual(bins.loc[101.0, "volume_estimated"], 200.0)
        self.assertAlmostEqual(bins.loc[102.0, "volume_estimated"], 300.0)
        self.assertAlmostEqual(bins.loc[103.0, "volume_estimated"], 100.0)
        self.assertAlmostEqual(profile.bins["volume_estimated"].sum(), 700.0)
        self.assertAlmostEqual(profile.regular_volume, 300.0 + 300.0 + 100.0)
        self.assertEqual(profile.data_quality, "ONE_MINUTE_ESTIMATED")


# ---------------------------------------------------------------------------
# C-08 / C-09  (design §10.3 acceptance and repair)
# ---------------------------------------------------------------------------
class C08C09_AcceptanceAndRepair(unittest.TestCase):
    """C-08 / design §10.3 `ms_repair_pct` = width-weighted fraction of
    separation-zone bins recovered to >= 50% of the weaker regional peak (all
    profile bins share one width, so the width-weighted fraction reduces to
    a simple mean, which is what `_metrics` computes) and
    C-09 / design §10.3 acceptance counters, each threshold read from
    `ms_params_v1` (MS_PARAMS_V1), not hard-coded here.

    Source: market_structure/service.py:23-46 `_metrics`. `_metrics` is a
    module-private helper (leading underscore) but is directly imported and
    exercised here since it is the only place the four acceptance thresholds
    and the repair-percentage formula are implemented; the public
    `calculate_market_structure_evidence` only wraps it.
    """

    @staticmethod
    def _bars(inside_minutes: int, outside_minutes: int = 10) -> pd.DataFrame:
        # start minute-aligned to a 5-minute boundary so the 5-min resample
        # bucket edges used below are exactly reproducible by hand.
        start = pd.Timestamp("2026-01-02T13:30:00Z")
        rows = []
        for i in range(outside_minutes):
            rows.append({"timestamp_utc": start + pd.Timedelta(minutes=i), "close": 95.0, "volume": 9.0})
        for i in range(inside_minutes):
            rows.append({"timestamp_utc": start + pd.Timedelta(minutes=outside_minutes + i), "close": 111.0, "volume": 10.0})
        return pd.DataFrame(rows)

    @staticmethod
    def _structure() -> dict:
        return {
            "detected": True, "second_direction": "ABOVE",
            "second_low": 110.0, "second_high": 112.0,
            "separation_low": 105.0, "separation_high": 107.0,
            "separation_indexes": (0, 1), "weaker_peak": 10.0,
            "first_low": 90.0, "first_high": 92.0,
        }

    @staticmethod
    def _profile(regular_volume: float) -> MarketProfile:
        bins = pd.DataFrame({"price": [104.0, 105.0], "tpo_count": [1, 1]})
        return MarketProfile(
            bins=bins, bin_width=1.0, poc=111.0, value_area_low=110.0, value_area_high=112.0,
            data_quality="ONE_MINUTE_ESTIMATED", total_tpo=10, regular_volume=regular_volume,
        )

    def test_c09_all_four_thresholds_pass_and_accepted_is_true(self):
        """Hand computation with N = params.acceptance_minutes bars inside the
        second distribution, preceded by M=10 bars outside it:

          minutes: entry = first "inside" bar (index M). Bars are consecutive
            1-minute bars, so (last_ts - entry_ts) = (N-1) minutes and
            `minutes = int(seconds//60) + 1 = (N-1) + 1 = N`
            -> minutes == params.acceptance_minutes (exactly meets "at least")

          5-min closes beyond boundary(107.0, direction=ABOVE): the frame
            starts on a 5-min-aligned timestamp; the first M/5 = 2 buckets are
            all "outside" (close=95, not >107); the remaining N/5 buckets are
            all "inside" (close=111>107) -> acceptance_closes = N/5.
            With N=30 (current config) -> 30/5 = 6 buckets.

          volume_share = (N*10) / (M*9 + N*10)
            with N=30, M=10 -> (30*10) / (10*9 + 30*10) = 300/390 = 0.769231

          repair_pct: separation bins tpo_count=[1,1], weaker_peak=10.0 ->
            threshold = 10.0*0.50 = 5.0; 1>=5.0 is False for both bins ->
            repaired.mean() = 0/2 = 0.0

          accepted = (minutes>=params.acceptance_minutes)
                 and (acceptance_closes>=params.acceptance_five_minute_closes)
                 and (volume_share>=params.acceptance_volume_share)
                 and (repair_pct<=params.intact_repair)
                 and not invalidated
                 = True and True and True and True and True = True
        """
        params = MS_PARAMS_V1
        N = params.acceptance_minutes
        M = 10
        bars = self._bars(inside_minutes=N, outside_minutes=M)
        structure = self._structure()
        profile = self._profile(regular_volume=float(bars["volume"].sum()))

        metrics = _metrics(bars, structure, profile, params)

        self.assertEqual(metrics["acceptance_minutes"], N)
        self.assertGreaterEqual(metrics["acceptance_minutes"], params.acceptance_minutes)

        expected_closes = N // 5
        self.assertEqual(metrics["acceptance_closes"], expected_closes)
        self.assertGreaterEqual(metrics["acceptance_closes"], params.acceptance_five_minute_closes)

        expected_volume_share = (N * 10) / (M * 9 + N * 10)
        self.assertAlmostEqual(metrics["volume_share"], round(expected_volume_share, 6))
        self.assertGreaterEqual(metrics["volume_share"], params.acceptance_volume_share)

        self.assertAlmostEqual(metrics["repair_pct"], 0.0)
        self.assertLessEqual(metrics["repair_pct"], params.intact_repair)

        self.assertTrue(metrics["accepted"])

    def test_c09_one_threshold_failing_blocks_acceptance(self):
        """Same fixture as above but with N = params.acceptance_minutes - 1
        elapsed minutes inside the second distribution -> minutes fails the
        >=params.acceptance_minutes rule (29 < 30 for the current config)
        while acceptance_closes, volume_share and repair_pct still pass ->
        proves acceptance is a strict AND of all four conditions, not an
        OR/majority vote.

        Hand computation: minutes = N = params.acceptance_minutes - 1.
        """
        params = MS_PARAMS_V1
        N = params.acceptance_minutes - 1
        M = 10
        bars = self._bars(inside_minutes=N, outside_minutes=M)
        structure = self._structure()
        profile = self._profile(regular_volume=float(bars["volume"].sum()))

        metrics = _metrics(bars, structure, profile, params)

        self.assertEqual(metrics["acceptance_minutes"], N)
        self.assertLess(metrics["acceptance_minutes"], params.acceptance_minutes)
        # the other three thresholds still individually pass
        self.assertGreaterEqual(metrics["acceptance_closes"], params.acceptance_five_minute_closes)
        self.assertGreaterEqual(metrics["volume_share"], params.acceptance_volume_share)
        self.assertLessEqual(metrics["repair_pct"], params.intact_repair)
        # yet overall acceptance is False because minutes alone fails
        self.assertFalse(metrics["accepted"])

    def test_c08_repair_pct_bands_intact_repairing_failed(self):
        """C-08 repair-percentage bands (design §10.3): <0.20 intact,
        0.20-0.60 repairing, >0.60 failed. `params.intact_repair`=seed 0.20,
        `params.failed_repair`=seed 0.60 read from configuration.

        Band 1 (intact): counts=[1,1], weaker_peak=10.07 -> threshold=5.035;
          1>=5.035 False, False -> mean=0/2=0.0 (< params.intact_repair)
        Band 2 (repairing): counts=[4,6,3,2], weaker_peak=10.0 -> threshold=5.0
          -> [4>=5 F, 6>=5 T, 3>=5 F, 2>=5 F] -> mean=1/4=0.25
          (params.intact_repair <= 0.25 <= params.failed_repair)
        Band 3 (failed): counts=[9,8,7,10], weaker_peak=10.0 -> threshold=5.0
          -> all four >=5.0 True -> mean=4/4=1.0 (> params.failed_repair)
        """
        params = MS_PARAMS_V1
        bars = self._bars(inside_minutes=5, outside_minutes=0)
        structure_template = self._structure()

        cases = [
            ("intact", [1, 1], 10.07, 0.0),
            ("repairing", [4, 6, 3, 2], 10.0, 0.25),
            ("failed", [9, 8, 7, 10], 10.0, 1.0),
        ]
        for label, counts, weaker_peak, expected_repair_pct in cases:
            with self.subTest(band=label):
                bins = pd.DataFrame({"price": list(range(len(counts))), "tpo_count": counts})
                structure = dict(structure_template)
                structure["separation_indexes"] = tuple(range(len(counts)))
                structure["weaker_peak"] = weaker_peak
                profile = MarketProfile(
                    bins=bins, bin_width=1.0, poc=111.0, value_area_low=110.0, value_area_high=112.0,
                    data_quality="ONE_MINUTE_ESTIMATED", total_tpo=10, regular_volume=float(bars["volume"].sum()),
                )
                metrics = _metrics(bars, structure, profile, params)
                self.assertAlmostEqual(metrics["repair_pct"], expected_repair_pct)

        # Cross-check the same three repair_pct values against the lifecycle
        # transition table (design §10.3) to close the loop between the
        # repair-percentage number and its named band, using
        # market_structure/lifecycle.py:transition_lifecycle (also
        # imported/keyed off MS_PARAMS_V1, not re-typed thresholds).
        self.assertEqual(
            transition_lifecycle(prior="MS_ACCEPTED", detected=True, accepted=True, repair_pct=0.0, params=params),
            "MS_CONTINUING",  # intact band -> stays/continues accepted
        )
        self.assertEqual(
            transition_lifecycle(prior="MS_ACCEPTED", detected=True, accepted=False, repair_pct=0.25, params=params),
            "MS_REPAIRING",  # repairing band
        )
        self.assertEqual(
            transition_lifecycle(prior="MS_CONTINUING", detected=True, accepted=True, repair_pct=0.65, params=params),
            "MS_FAILED",  # failed band -> terminal MS_FAILED regardless of `accepted`
        )


# ---------------------------------------------------------------------------
# C-10  (design §8.6, §23 ms_evidence_id)
# ---------------------------------------------------------------------------
class C10_EvidenceId(unittest.TestCase):
    """C-10 / design §8.6, §23.

    `ms_evidence_id` = SHA-256 over ticker, session, algorithm version,
    parameter-set version and ordered input dataset IDs; identical inputs
    reproduce the same ID; a changed parameter-set version changes it.

    Source: market_structure/service.py
      lineage = "|".join([ticker, session, ALGORITHM_VERSION,
                           params.version, *input_dataset_ids])
      evidence_id = sha256(lineage)
    """

    @staticmethod
    def _bars() -> pd.DataFrame:
        start = pd.Timestamp("2026-01-02T14:30:00Z")
        return pd.DataFrame([
            {"timestamp_utc": start + pd.Timedelta(minutes=i), "high": 100 + i, "low": 99 + i,
             "close": 99.5 + i, "volume": 100.0, "session_segment": "REGULAR"}
            for i in range(3)
        ])

    def _evidence(self, params=MS_PARAMS_V1, dataset_ids=("D1", "D2")):
        return calculate_market_structure_evidence(
            ticker="AAPL", session_date=date(2026, 1, 2), run_id="R1", bars=self._bars(),
            exchange_tick=1.0, atr14=40.0, regular_open_utc=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=dataset_ids, input_hashes=("H1", "H2"), params=params,
        )

    def test_algorithm_matches_literal_sha256_design(self):
        """Design §23: "SHA-256 of ticker, session, algorithm version,
        parameter version and ordered input dataset IDs".

        Hand-computed value per the literal design formula (ticker, session,
        algorithm version, parameter version, ordered dataset IDs joined
        with '|', then SHA-256 hex-digested):
        """
        evidence = self._evidence()
        design_lineage = "|".join([
            "AAPL", "2026-01-02", ALGORITHM_VERSION, MS_PARAMS_V1.version, "D1", "D2",
        ])
        expected_sha256_hex = hashlib.sha256(design_lineage.encode()).hexdigest()
        self.assertEqual(evidence["ms_evidence_id"], expected_sha256_hex)
        self.assertEqual(len(evidence["ms_evidence_id"]), 64)

    def test_identical_inputs_reproduce_the_same_id(self):
        first = self._evidence()
        second = self._evidence()
        self.assertEqual(first["ms_evidence_id"], second["ms_evidence_id"])

    def test_changed_parameter_set_version_changes_the_id(self):
        base = self._evidence()
        different_params = dataclasses.replace(MS_PARAMS_V1, version="ms_params_v2")
        changed = self._evidence(params=different_params)
        self.assertNotEqual(base["ms_evidence_id"], changed["ms_evidence_id"])

    def test_dataset_id_order_matters_ordered_not_sorted(self):
        # Design says "ordered input dataset IDs" -- swapping the order of
        # otherwise-identical dataset IDs must change the ID if the
        # implementation genuinely orders rather than sorts/sets them.
        forward = self._evidence(dataset_ids=("D1", "D2"))
        reversed_ids = self._evidence(dataset_ids=("D2", "D1"))
        self.assertNotEqual(forward["ms_evidence_id"], reversed_ids["ms_evidence_id"])


# ---------------------------------------------------------------------------
# C-11  (design §5.2, §20(8) determinism)
# ---------------------------------------------------------------------------
class C11_Determinism(unittest.TestCase):
    """C-11 / design §5.2 "A deterministic pipeline service..." and §20
    acceptance criterion 8: "Structure evidence is deterministic, versioned,
    quality-labelled and non-authoritative."

    Running `calculate_market_structure_evidence` twice on the same fixture
    bars must yield byte-identical evidence records excluding the
    calculation timestamp (`ms_calculated_utc`, which is `datetime.now()` by
    construction and is explicitly excluded from the design's own
    determinism claim).
    """

    def test_two_runs_are_identical_except_calculated_timestamp(self):
        start = pd.Timestamp("2026-01-02T14:30:00Z")
        bars = pd.DataFrame([
            {"timestamp_utc": start + pd.Timedelta(minutes=i), "high": 100 + i, "low": 99 + i,
             "close": 99.5 + i, "volume": 100.0, "session_segment": "REGULAR"}
            for i in range(3)
        ])
        kwargs = dict(
            ticker="AAPL", session_date=date(2026, 1, 2), run_id="R1", bars=bars,
            exchange_tick=1.0, atr14=40.0, regular_open_utc=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1", "D2"), input_hashes=("H1", "H2"),
        )
        first = calculate_market_structure_evidence(**kwargs)
        second = calculate_market_structure_evidence(**kwargs)

        self.assertEqual(set(first) - {"ms_calculated_utc"}, set(second) - {"ms_calculated_utc"})
        diffs = {
            key for key in first
            if key != "ms_calculated_utc" and first[key] != second.get(key)
        }
        self.assertEqual(diffs, set(), f"non-deterministic fields: {diffs}")
        # sanity: the excluded field is in fact allowed to differ in general
        # (it is wall-clock-derived), even though in this fast unit test it
        # will usually coincide to the second.
        self.assertIn("ms_calculated_utc", first)
        self.assertIn("ms_calculated_utc", second)


# ---------------------------------------------------------------------------
# C-12  (design §10.2 ms_params_v1 calibration ranges)
# ---------------------------------------------------------------------------
class C12_ParamsWithinCalibrationRange(unittest.TestCase):
    """C-12 / design §10.2.

    Every `ms_params_v1` value lies within its permitted calibration range
    (bin divisor 25-60; region share 15-30%; peak percentile 55-75%; valley
    ratio 35-65%; separation 0.20-0.50 ATR; acceptance 20-60 minutes), and
    the parameter set is versioned.

    All bounds below are the design's own §10.2 permitted RANGES (not the
    seed values themselves) -- these are the closure test, not calibration
    inputs, so they are the one place literal numbers from the design text
    are legitimately written into the test. The values under test are read
    from MS_PARAMS_V1, never re-typed.
    """

    def test_bin_divisor_within_25_to_60(self):
        self.assertTrue(25 <= MS_PARAMS_V1.bin_divisor <= 60, MS_PARAMS_V1.bin_divisor)

    def test_region_share_within_15_to_30_percent(self):
        self.assertTrue(0.15 <= MS_PARAMS_V1.region_share <= 0.30, MS_PARAMS_V1.region_share)

    def test_peak_percentile_within_55_to_75_percent(self):
        self.assertTrue(0.55 <= MS_PARAMS_V1.peak_percentile <= 0.75, MS_PARAMS_V1.peak_percentile)

    def test_valley_ratio_within_35_to_65_percent(self):
        self.assertTrue(0.35 <= MS_PARAMS_V1.valley_ratio <= 0.65, MS_PARAMS_V1.valley_ratio)

    def test_separation_within_020_to_050_atr(self):
        self.assertTrue(0.20 <= MS_PARAMS_V1.separation_atr <= 0.50, MS_PARAMS_V1.separation_atr)

    def test_acceptance_minutes_within_20_to_60(self):
        self.assertTrue(20 <= MS_PARAMS_V1.acceptance_minutes <= 60, MS_PARAMS_V1.acceptance_minutes)

    def test_parameter_set_is_versioned(self):
        self.assertEqual(MS_PARAMS_V1.version, "ms_params_v1")
        self.assertTrue(MS_PARAMS_V1.version)
        # design §10.2: "MSI-4 calibration/UAT either accepts the seed or
        # records a signed versioned replacement before activation" -- the
        # calibration_status field records which state we are in; assert it
        # is one of the two documented states rather than assuming PASS.
        self.assertIn(
            MS_PARAMS_V1.calibration_status,
            {"PROPOSED_NOT_CALIBRATED", "ACCEPTED"},
        )
        if MS_PARAMS_V1.calibration_status != "ACCEPTED":
            # Recorded as a SEED_VALUE condition, not a failure: the design
            # explicitly permits production to run on the proposed seed
            # pending MSI-4 sign-off (design §10.2, §19 MSI-4).
            pass


if __name__ == "__main__":
    unittest.main()
