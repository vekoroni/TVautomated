"""MSI v1.1 independent FUNCTIONALITY tests (design doc §3.2, §8, §18, §23, §24 — unit level).

Independent test engineer pack. Production code is READ-ONLY; this file only
imports and calls it. Every test's docstring starts with its test ID (F-xx)
and the exact design section it verifies, per the assignment brief.

Design document:
  audit/solution_design/MARKET_STRUCTURE_INTERPRETER_DATA_ENHANCEMENT_SOLUTION_DESIGN_20260830.md
Preflight:
  audit/msi/00_preflight.md

Interpreter used to author and execute this file (record for every run):
  .codex_python313_runtime/python.exe  with PYTHONPATH=<repo>/venv/Lib/site-packages
  (matches the interpreter the implementer used for its own regression evidence,
  per audit/msi/00_preflight.md "Test runtime" — NOT venv/Scripts/python.exe).

Run with (from repo root, POSIX shell):
  PYTHONPATH="$(pwd)/venv/Lib/site-packages" .codex_python313_runtime/python.exe -m pytest tests/msi/test_functionality.py -v

No live provider calls are made anywhere in this file. Every provider-shaped
payload used below is either one of the five recorded fixtures at
tests/fixtures/marketdata/, or (only where explicitly labelled BLOCKED) omitted
entirely per the assignment's instruction not to fabricate a substitute fixture.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from canonical_data.contracts import DatasetType
from canonical_data.errors import FetchNotAuthorised
from canonical_data.feature_flags import CanonicalFeatureFlags
from canonical_data.lifecycle import LifecycleManager, LifecycleState
from canonical_data.marketdata_response import (
    parse_exact_option_quote,
    parse_marketdata_option_response,
)
from canonical_data.market_observation_resolver import (
    CanonicalMarketObservationResolver,
    normalise_underlying_nbbo,
)
from canonical_data.option_identity import (
    build_occ_symbol,
    normalise_occ_symbol,
    parse_occ_symbol,
)
from canonical_data.registry import CanonicalRegistry
from canonical_data.request_ledger import RequestLedger, RequestResolution
from canonical_data.session_clock import (
    FreshnessState,
    SessionState,
    evaluate_freshness,
    is_early_close,
    is_xnys_session,
    session_bounds,
    session_snapshot,
    xnys_holidays,
)

import contracts.selected_contract_economics as sce
import canonical_data.contract_reference as cref

from contracts.interpreter_handoff import RunKind, RunStatus, HandoffStatus
from pipeline_interpreter.assessment_contract import AssessmentStatus

from market_structure.lifecycle import transition_lifecycle
from market_structure.service import calculate_market_structure_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "marketdata"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# F-01  design §3.2, §8.1, §18
# ---------------------------------------------------------------------------

class F01ChainParserSizes(unittest.TestCase):
    """F-01 (design §3.2, §8.1, §18): chain parser retains bidSize/askSize as
    bid_size/ask_size from the MarketData chain fixture; compatible parallel
    arrays parse; incompatible lengths are rejected.

    Evidence: canonical_data/marketdata_response.py:_values (line 24),
    parse_marketdata_option_response (line 93).
    """

    def test_bid_ask_size_retained_from_chain_fixture(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertEqual(list(frame["bid_size"]), [12, 0])
        # Fixture's second askSize element is JSON null. The underlying Python
        # value returned by _size() is (None, "MISSING"); once placed in a
        # pandas column alongside a real int (9), pandas upcasts the whole
        # column to float64 and represents the missing entry as NaN rather
        # than None/pd.NA. Checked with pd.isna() here (see F-15 for the
        # "sizes are integers" precision consequence of this coercion).
        self.assertEqual(frame.iloc[0]["ask_size"], 9)
        self.assertTrue(pd.isna(frame.iloc[1]["ask_size"]))
        self.assertIn("bid_size", frame.columns)
        self.assertIn("ask_size", frame.columns)

    def test_compatible_parallel_arrays_parse(self):
        # 2 optionSymbols, all parallel arrays length 2 (or scalar-broadcastable).
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertEqual(len(frame), 2)

    def test_incompatible_parallel_array_length_is_rejected(self):
        bad = fixture("option_chain_list_sizes.json")
        bad["bidSize"] = [1, 2, 3]  # 3 values for 2 optionSymbols -> incompatible
        with self.assertRaisesRegex(ValueError, "incompatible MarketData parallel-array length"):
            parse_marketdata_option_response(bad, ticker="AAPL")


# ---------------------------------------------------------------------------
# F-02  design §3.2, §8.2
# ---------------------------------------------------------------------------

class F02ExactQuoteParserSizes(unittest.TestCase):
    """F-02 (design §3.2, §8.2): exact-contract quote parser retains
    bid_size/ask_size from the exact-quote fixture.

    Evidence: canonical_data/marketdata_response.py:parse_exact_option_quote
    (line 148), fed by the scalar-shaped fixture option_quote_scalar_ok.json.
    """

    def test_exact_quote_retains_sizes(self):
        record = parse_exact_option_quote(
            fixture("option_quote_scalar_ok.json"),
            ticker="AAPL",
            symbol="AAPL260918C00200000",
        )
        self.assertEqual(record["bid_size"], 12)
        self.assertEqual(record["ask_size"], 9)


# ---------------------------------------------------------------------------
# F-03  design §16.1, §18
# ---------------------------------------------------------------------------

class F03ProviderFixtureCategories(unittest.TestCase):
    """F-03 (design §16.1, §18): provider adapters handle ok, no_data, error,
    scalar, parallel-array and missing-field fixture responses without raising
    unhandled exceptions and with the stated status outcome.

    Content verification of the 5 recorded fixtures (per preflight instruction
    to open each file and map it to the 6 required categories by content,
    not filename):
      option_chain_list_sizes.json  -> s="ok", 2 optionSymbols       => OK + PARALLEL-ARRAY
                                        (askSize[1] is JSON null)    => also covers MISSING-FIELD
      option_quote_scalar_ok.json   -> s="ok", all scalar fields     => SCALAR (+ OK)
      option_quote_no_data.json     -> {"s":"no_data"}               => NO_DATA
      option_quote_crossed.json     -> s="ok", bid>ask (not a required category, extra fixture for F-05)
      option_quote_negative_size.json -> s="ok", bidSize=-1 (not a required category, extra fixture for F-04)
      ERROR category: no fixture among the 5 files has any error/failure shape
        (e.g. s="error", s="invalid", or an HTTP-error envelope). This matches
        preflight's finding. Per the assignment's explicit instruction, this
        is recorded as a finding against MSI-0 and the sub-test below is
        marked BLOCKED (skipped), not silently omitted or faked with a
        fabricated fixture.
    """

    def test_ok_and_parallel_array_category(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertFalse(frame.empty)
        self.assertEqual(len(frame), 2)

    def test_no_data_category(self):
        frame = parse_marketdata_option_response(
            fixture("option_quote_no_data.json"), ticker="AAPL"
        )
        self.assertTrue(frame.empty)  # stated outcome: empty v2 frame, no exception

    def test_scalar_category(self):
        frame = parse_marketdata_option_response(
            fixture("option_quote_scalar_ok.json"), ticker="AAPL"
        )
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["symbol"], "AAPL260918C00200000")

    def test_missing_field_category_null_within_array(self):
        # option_chain_list_sizes.json row index 1 has askSize=null: a present
        # key with a missing per-contract value, which is the shape the size
        # parser is built to classify (canonical_data/marketdata_response.py:_size).
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertTrue(pd.isna(frame.iloc[1]["ask_size"]))
        self.assertEqual(frame.iloc[1]["ask_size_quality"], "MISSING")

    def test_error_category_BLOCKED(self):
        pytest.skip(
            "BLOCKED - MSI-0 fixture missing: none of the 5 recorded fixtures "
            "under tests/fixtures/marketdata/ represents a provider ERROR "
            "response shape (e.g. s='error'). Per design §16.1 this category "
            "is required before provider-adapter activation. Reported as a "
            "finding against MSI-0, not faked with a fabricated fixture."
        )

    def test_missing_field_category_key_entirely_absent(self):
        # A stronger reading of "missing-field": the key itself is entirely
        # absent from the payload (not merely null within an existing array).
        # No fixture exercises this shape either, but the code path exists
        # (canonical_data/marketdata_response.py:_values falls back to
        # [None]*count when payload.get(key) is None). Demonstrated here via
        # a locally *removed* key from the recorded ok/parallel-array fixture
        # content, not a new fabricated provider fixture file.
        payload = fixture("option_chain_list_sizes.json")
        del payload["askSize"]
        frame = parse_marketdata_option_response(payload, ticker="AAPL")
        self.assertTrue(all(v is None for v in frame["ask_size"]))
        self.assertTrue(all(q == "MISSING" for q in frame["ask_size_quality"]))


# ---------------------------------------------------------------------------
# F-04  design §8.2
# ---------------------------------------------------------------------------

class F04SizeQuality(unittest.TestCase):
    """F-04 (design §8.2): size quality: absent/null -> MISSING; numeric 0 ->
    OBSERVED_ZERO; negative -> INVALID_SIZE and the observation is rejected.

    Design §24 enum table: Size quality = OBSERVED, OBSERVED_ZERO, MISSING,
    INVALID_SIZE. This test asserts the DESIGN's literal values; where the
    code emits a different literal, the assertion fails for real and the
    mismatch is reported (see F-13 for the systematic enum audit).
    """

    def test_null_size_is_missing(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertEqual(frame.iloc[1]["ask_size_quality"], "MISSING")
        self.assertTrue(pd.isna(frame.iloc[1]["ask_size"]))

    def test_zero_size_is_observed_zero(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertEqual(frame.iloc[1]["bid_size_quality"], "OBSERVED_ZERO")
        self.assertEqual(frame.iloc[1]["bid_size"], 0)

    def test_positive_size_label_matches_design_enum_OBSERVED(self):
        """Design §24 defines the positive-size enum value as literally
        'OBSERVED'. The actual code (canonical_data/marketdata_response.py:51
        and canonical_data/market_observation_resolver.py:75) emits
        'OBSERVED_POSITIVE' instead, in every call site repo-wide (also
        scripts/avshunter_options_intelligence.py:1492,1501,2530,2531). This
        assertion is written against the design's literal value and is
        expected to fail for real, which is itself the evidence."""
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        self.assertEqual(frame.iloc[0]["bid_size_quality"], "OBSERVED")

    def test_negative_size_rejects_the_observation(self):
        # "rejects the observation" half of the requirement: code raises.
        with self.assertRaises(ValueError):
            parse_marketdata_option_response(
                fixture("option_quote_negative_size.json"), ticker="AAPL"
            )

    def test_negative_size_never_surfaces_INVALID_SIZE_label(self):
        """The design also names the label INVALID_SIZE for this case. The
        actual implementation only raises a generic ValueError
        ('invalid displayed size: ...') and never attaches the literal string
        'INVALID_SIZE' to any field, because the row is never constructed.
        This test documents that the label half of the requirement is not
        met even though the rejection half is."""
        try:
            parse_marketdata_option_response(
                fixture("option_quote_negative_size.json"), ticker="AAPL"
            )
            self.fail("expected ValueError for negative size")
        except ValueError as error:
            self.assertNotIn("INVALID_SIZE", str(error))


# ---------------------------------------------------------------------------
# F-05  design §8.1, §8.2, §18
# ---------------------------------------------------------------------------

class F05CrossedAndZeroBidQuotes(unittest.TestCase):
    """F-05 (design §8.1, §8.2, §18): crossed quote (bid > ask) is not
    accepted as a normal quote unless flagged; quote_quality = CROSSED
    (per design §24 enum and the assignment's own wording). Zero bid with
    positive ask -> quote_quality = ONE_SIDED, non-executable.
    """

    def test_crossed_quote_is_flagged_not_accepted_as_normal(self):
        frame = parse_marketdata_option_response(
            fixture("option_quote_crossed.json"), ticker="AAPL"
        )
        self.assertIn("CROSSED_QUOTE", frame.iloc[0]["quality_flags"])
        # exact-contract path additionally REJECTS a crossed quote outright:
        with self.assertRaisesRegex(ValueError, "crossed"):
            parse_exact_option_quote(
                fixture("option_quote_crossed.json"),
                ticker="AAPL",
                symbol="AAPL260918C00200000",
            )

    def test_crossed_quote_quality_label_matches_design_enum_CROSSED(self):
        """Design §24 Quote-quality enum names CROSSED as the value for this
        case (and the assignment's own F-05 instruction states this
        literally). The actual code
        (canonical_data/marketdata_response.py:_quote, line 79) sets
        quality = 'INVALID' for bid > ask, never 'CROSSED'. The implementer's
        own regression suite codifies 'INVALID' as the expected value
        (tests/test_msi_agent1_data_foundation.py:52), corroborating that
        this is a real, intentional deviation from the design's literal enum
        value, not a copy/paste slip. This assertion is written against the
        design and is expected to fail for real."""
        frame = parse_marketdata_option_response(
            fixture("option_quote_crossed.json"), ticker="AAPL"
        )
        self.assertEqual(frame.iloc[0]["quote_quality"], "CROSSED")

    def test_zero_bid_positive_ask_is_one_sided_and_non_executable(self):
        # option_chain_list_sizes.json row 1 (put) has bid=0, ask=3.0.
        record = parse_exact_option_quote(
            fixture("option_chain_list_sizes.json"),
            ticker="AAPL",
            symbol="AAPL260918P00200000",
        )
        self.assertEqual(record["quote_quality"], "ONE_SIDED")  # matches design §8.2
        self.assertFalse(record["executable_now"])  # matches "non-executable"
        self.assertIn("ZERO_BID", record["quality_flags"])  # matches design §18 wording
        self.assertEqual(record["mid"], 1.5)  # mid = ask / 2

    def test_design_sections_8_2_and_18_are_not_actually_contradictory(self):
        """Documented finding, not a functional bug: §8.2 states
        quote_quality=ONE_SIDED for the zero-bid case; §18 separately says
        'observed zero-bid preservation as ZERO_BID/non-executable'. The code
        realises both in different fields of the SAME record simultaneously
        (quote_quality='ONE_SIDED' AND a 'ZERO_BID' entry in quality_flags),
        so the two design passages describe two different fields of one
        record rather than contradicting each other. Recorded here so the
        consolidated design-inconsistency list does not double-count this."""
        record = parse_exact_option_quote(
            fixture("option_chain_list_sizes.json"),
            ticker="AAPL",
            symbol="AAPL260918P00200000",
        )
        self.assertEqual(record["quote_quality"], "ONE_SIDED")
        self.assertIn("ZERO_BID", record["quality_flags"])


# ---------------------------------------------------------------------------
# F-06  design §23
# ---------------------------------------------------------------------------

VECTORS = [
    "AAPL260918C00150000",
    "AAPL260918P00150500",
    "AAPL1260918C00150000",
    "BRK.B260918P00500000",
    "SPY260918C00600000",
    "TSLA260918P00250500",
    "IWM260918C00200000",
    "X260918P00025000",
    "F260918C00015000",
    "GOOGL260918P00200000",
]


class F06OccNormaliser(unittest.TestCase):
    """F-06 (design §23): OCC normaliser returns the canonical compact identity
    for every listed vector; provider-prefixed and space-padded inputs of the
    same contracts return the same identity; AAPL1... and AAPL... remain
    distinct.

    Evidence: canonical_data/option_identity.py:normalise_occ_symbol (line 40).
    """

    def test_all_vectors_normalise_to_themselves(self):
        for vector in VECTORS:
            with self.subTest(vector=vector):
                self.assertEqual(normalise_occ_symbol(vector), vector)
                identity = parse_occ_symbol(vector)
                self.assertEqual(identity.symbol, vector)

    def test_provider_prefixed_and_space_padded_match(self):
        for vector in VECTORS:
            with self.subTest(vector=vector):
                prefixed = f"O:{vector}"
                padded = f"  {vector}  "
                prefixed_and_padded = f"  O:{vector}  "
                self.assertEqual(normalise_occ_symbol(prefixed), vector)
                self.assertEqual(normalise_occ_symbol(padded), vector)
                self.assertEqual(normalise_occ_symbol(prefixed_and_padded), vector)

    def test_adjusted_root_remains_distinct(self):
        adjusted = parse_occ_symbol("AAPL1260918C00150000")
        standard = parse_occ_symbol("AAPL260918C00150000")
        self.assertNotEqual(adjusted.root, standard.root)
        self.assertNotEqual(adjusted.symbol, standard.symbol)
        self.assertEqual(adjusted.root, "AAPL1")
        self.assertEqual(standard.root, "AAPL")


# ---------------------------------------------------------------------------
# F-07  design §22, §23
# ---------------------------------------------------------------------------

class F07SingleOccNormaliserOwner(unittest.TestCase):
    """F-07 (design §22, §23): exactly one OCC normaliser is active
    (canonical_data/option_identity.py); the older functions in
    contracts/selected_contract_economics.py and
    canonical_data/contract_reference.py import/alias it rather than
    reimplementing.
    """

    def test_contract_reference_aliases_option_identity(self):
        # canonical_data/contract_reference.py:16 imports these names directly
        # from option_identity rather than redefining them -> same function object.
        import canonical_data.option_identity as identity_module

        self.assertIs(cref.normalise_occ_symbol, identity_module.normalise_occ_symbol)
        self.assertIs(cref.parse_occ_symbol, identity_module.parse_occ_symbol)
        self.assertIs(cref.build_occ_symbol, identity_module.build_occ_symbol)

    def test_selected_contract_economics_REIMPLEMENTS_rather_than_aliases(self):
        """Design requirement: 'old functions become imports/aliases'.
        contracts/selected_contract_economics.py:24-28 (_OCC_RE),
        46-48 (normalise_occ_symbol) and 73-86 (parse_occ_symbol) define an
        entirely independent regex and implementation, not an import from
        canonical_data.option_identity. This assertion documents that fact
        directly (is-not-the-same-function) and is expected to fail the
        'exactly one normaliser is active' requirement for real."""
        import canonical_data.option_identity as identity_module

        self.assertIsNot(sce.normalise_occ_symbol, identity_module.normalise_occ_symbol)
        self.assertIsNot(sce.parse_occ_symbol, identity_module.parse_occ_symbol)

    def test_two_normalisers_can_behave_differently_on_the_same_input(self):
        """Demonstrates the practical risk of two independent normalisers:
        canonical_data.option_identity.normalise_occ_symbol fullmatch-validates
        against the OCC shape and raises ValueError for anything that is not a
        real option symbol (option_identity.py:44-46). By contrast,
        contracts.selected_contract_economics.normalise_occ_symbol
        (selected_contract_economics.py:46-48) performs NO shape validation at
        all -- it only strips an 'O:' prefix and whitespace -- so it silently
        accepts arbitrary garbage that the canonical owner would reject."""
        garbage = "NOT_AN_OPTION_SYMBOL_AT_ALL"
        with self.assertRaises(ValueError):
            normalise_occ_symbol(garbage)  # canonical_data.option_identity: rejects
        # contracts.selected_contract_economics: does NOT reject the same input.
        accepted = sce.normalise_occ_symbol(garbage)
        self.assertEqual(accepted, garbage)


# ---------------------------------------------------------------------------
# F-08  design §3.1, §8.3, §11
# ---------------------------------------------------------------------------

class F08UnderlyingNbboSizeFields(unittest.TestCase):
    """F-08 (design §3.1, §8.3, §11): underlying_nbbo_bid_size /
    underlying_nbbo_ask_size are emitted together with underlying_nbbo_bid,
    underlying_nbbo_ask, timestamp, source, freshness and
    depth_level=NBBO_ONLY; l2_bid_size/l2_ask_size remain readable as aliases
    and resolve to the same values.
    """

    def test_resolver_normaliser_computes_sizes_but_under_generic_names(self):
        """canonical_data/market_observation_resolver.py:normalise_underlying_nbbo
        (line 78) DOES compute bid_size/ask_size/depth_level=NBBO_ONLY, but
        under the generic keys 'bid_size'/'ask_size', not the canonical
        design names 'underlying_nbbo_bid_size'/'underlying_nbbo_ask_size'."""
        payload = {
            "bid": [100.0], "ask": [100.2],
            "bidSize": [5], "askSize": [7],
            "updated": [datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)],
        }
        result = normalise_underlying_nbbo(payload, ticker="AAPL", provider="POLYGON")
        self.assertEqual(result["bid_size"], 5)
        self.assertEqual(result["ask_size"], 7)
        self.assertEqual(result["depth_level"], "NBBO_ONLY")
        self.assertNotIn("underlying_nbbo_bid_size", result)
        self.assertNotIn("underlying_nbbo_ask_size", result)

    def test_resolver_normaliser_rejects_raw_epoch_seconds_updated_field(self):
        """Incidental finding while exercising the above: unlike
        marketdata_response.py's _timestamp() (which magnitude-sniffs raw
        unix seconds/ms/ns), market_observation_resolver._utc (line 58-62)
        calls bare pd.Timestamp(value) and requires the result to already be
        tzinfo-aware. A raw unix-seconds integer such as the 'updated' value
        MarketData actually returns (e.g. 1788120000, as used throughout the
        recorded fixtures) is parsed as tz-naive and rejected outright."""
        payload = {"bid": [100.0], "ask": [100.2], "updated": [1788120000]}
        with self.assertRaises(ValueError):
            normalise_underlying_nbbo(payload, ticker="AAPL", provider="POLYGON")

    def test_no_producer_anywhere_writes_the_canonical_field_names(self):
        """Repo-wide check: 'underlying_nbbo_bid_size'/'underlying_nbbo_ask_size'
        (and even 'underlying_nbbo_bid'/'underlying_nbbo_ask' without size)
        appear in exactly one place in the entire non-backup .py tree: the
        ALLOW-LIST in contracts/lab_evidence_overlay.py (lines 22-27) which
        only declares the name as a field an overlay COULD legally carry.
        No producer anywhere actually sets that key on any dict, row or
        overlay. This walks every non-backup .py file directly (no shell
        grep) so the result is reproducible in-process."""
        needle_size = "underlying_nbbo_bid_size"
        needle_bid = "underlying_nbbo_bid"
        hits = []
        for path in REPO_ROOT.rglob("*.py"):
            text_parts = path.parts
            if "backups" in text_parts or "venv" in text_parts or "__pycache__" in text_parts:
                continue
            if "_cleanup_holding" in text_parts:
                continue
            if "tests" in text_parts:
                # This is a PRODUCTION-code check. Test files (this one
                # included, and sibling MSI test packs written by other
                # agents in the same audit) legitimately discuss the
                # canonical field name in prose/docstrings and assertions;
                # they are not producers.
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if needle_size in content or needle_bid in content:
                hits.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
        self.assertEqual(
            hits,
            ["contracts/lab_evidence_overlay.py"],
            f"expected the canonical underlying_nbbo_bid[_size] name to appear "
            f"only in the overlay allow-list; found in: {hits}",
        )

    def test_morning_gate_extraction_drops_the_computed_sizes(self):
        """Reproduces morning_gate.py:918-931's own extraction pattern against
        a real (non-live, locally-supplied) resolver call: the resolver DOES
        compute bid_size/ask_size/bid/ask inside observation.payload, but the
        one production caller of resolver.underlying_nbbo() only reads
        payload['mid'] and payload['depth_level'] out of the result -- bid,
        ask, bid_size and ask_size are read from the observation and then
        discarded. This is executed against the real resolver + real
        marketdata_response/session_clock code (no live provider call: fetch
        is a local lambda returning fixed content), so this is genuine
        execution evidence, not a source-only claim."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = CanonicalRegistry(root / "control.sqlite")
            registry.initialise()
            session = date(2026, 8, 30)
            registry.register_run("R1", "MORNING", session)
            lifecycle = LifecycleManager(registry)
            event = lifecycle.register(
                "R1", "AAPL", allowed_capabilities=(DatasetType.UNDERLYING_NBBO,)
            )
            event = lifecycle.transition(
                "R1", "AAPL", LifecycleState.ACTIVE_CORE, stage="PACKAGES",
                reason_code="TEST", expected_version=event.version,
                allowed_capabilities=(DatasetType.UNDERLYING_NBBO,),
            )
            lifecycle.transition(
                "R1", "AAPL", LifecycleState.ACTIVE_MORNING, stage="MORNING_GATE",
                reason_code="TEST", expected_version=event.version,
                allowed_capabilities=(DatasetType.UNDERLYING_NBBO,),
            )
            lifecycle.create_worklist("R1", "MORNING_GATE", DatasetType.UNDERLYING_NBBO, ("AAPL",))
            flags = CanonicalFeatureFlags(
                enabled=True, write_through=True, stage_gating_enforced=True,
                offline_replay=False, ohlcv_mode="ACTIVE",
            )
            resolver = CanonicalMarketObservationResolver(
                registry_path=root / "control.sqlite", payload_root=root / "payloads",
                run_id="R1", flags=flags,
            )
            raw_underlying = {
                "bid": 100.0, "ask": 100.2, "bidSize": 5, "askSize": 7,
                "updated": datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc),
            }
            observation = resolver.underlying_nbbo(
                ticker="AAPL", session_date=session, freshness_seconds=30,
                fetch=lambda _t: raw_underlying, provider="POLYGON",
            )
            self.assertIn("bid_size", observation.payload)
            self.assertIn("ask_size", observation.payload)
            self.assertEqual(observation.payload["bid_size"], 5)
            self.assertEqual(observation.payload["ask_size"], 7)

            # Reproduce morning_gate.py's own extraction (lines 927-929):
            live: dict = {}
            live["underlying_mid"] = observation.payload.get("mid")
            live["underlying_depth_level"] = observation.payload.get("depth_level")
            self.assertNotIn("underlying_nbbo_bid_size", live)
            self.assertNotIn("underlying_nbbo_ask_size", live)
            self.assertNotIn("bid_size", live)
            self.assertNotIn("ask_size", live)


# ---------------------------------------------------------------------------
# F-09  design §16.3
# ---------------------------------------------------------------------------

class F09SessionClock(unittest.TestCase):
    """F-09 (design §16.3): canonical_data/session_clock.py returns premarket
    for 04:00-09:29 ET, regular for 09:30 ET to calendar close, after_hours to
    20:00 ET; handles a known NYSE holiday, an early-close day (13:00 ET) and
    a DST transition; all outputs are UTC; 'last completed session' is correct
    on a weekend and on a holiday.
    """

    def test_premarket_regular_after_hours_boundaries(self):
        # Monday 2026-08-31 is a regular XNYS session (not a holiday).
        day = date(2026, 8, 31)
        self.assertTrue(is_xnys_session(day))
        premarket = session_snapshot(datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc))  # 05:00 ET
        self.assertEqual(premarket.state, SessionState.PREMARKET)
        regular = session_snapshot(datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc))  # 11:00 ET
        self.assertEqual(regular.state, SessionState.REGULAR)
        after_hours = session_snapshot(datetime(2026, 8, 31, 21, 0, tzinfo=timezone.utc))  # 17:00 ET
        self.assertEqual(after_hours.state, SessionState.AFTER_HOURS)
        closed_predawn = session_snapshot(datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc))  # 02:00 ET
        self.assertEqual(closed_predawn.state, SessionState.CLOSED)
        closed_late = session_snapshot(datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc))  # 21:00 ET
        self.assertEqual(closed_late.state, SessionState.CLOSED)

    def test_known_nyse_holiday(self):
        # 2026-09-07 is Labor Day (1st Monday of September).
        labor_day = date(2026, 9, 7)
        self.assertIn(labor_day, xnys_holidays(2026))
        self.assertFalse(is_xnys_session(labor_day))
        snapshot = session_snapshot(datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(snapshot.state, SessionState.CLOSED)

    def test_early_close_day_1300_et(self):
        # Day after Thanksgiving 2026 (2026-11-26 is Thanksgiving Thursday).
        early_close_day = date(2026, 11, 27)
        self.assertTrue(is_early_close(early_close_day))
        _, close_utc = session_bounds(early_close_day)
        close_et = close_utc.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
        self.assertEqual(close_et.hour, 13)
        self.assertEqual(close_et.minute, 0)

    def test_dst_transition_shifts_utc_open_by_one_hour(self):
        # 2026-03-08 is the US spring-forward Sunday; Monday 2026-03-09 is the
        # first EDT (UTC-4) session, Monday 2026-03-02 is the last EST (UTC-5)
        # session before it.
        pre_dst_open, _ = session_bounds(date(2026, 3, 2))
        post_dst_open, _ = session_bounds(date(2026, 3, 9))
        self.assertEqual(pre_dst_open.hour, 14)  # 09:30 EST -> 14:30 UTC
        self.assertEqual(post_dst_open.hour, 13)  # 09:30 EDT -> 13:30 UTC
        self.assertEqual(pre_dst_open.tzinfo, timezone.utc)
        self.assertEqual(post_dst_open.tzinfo, timezone.utc)

    def test_all_outputs_are_utc(self):
        snapshot = session_snapshot(datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(snapshot.regular_open_utc.tzinfo, timezone.utc)
        self.assertEqual(snapshot.regular_close_utc.tzinfo, timezone.utc)

    def test_last_completed_session_on_weekend(self):
        # Saturday 2026-09-05.
        snapshot = session_snapshot(datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(snapshot.state, SessionState.CLOSED)
        self.assertEqual(snapshot.last_completed_session, date(2026, 9, 4))  # Friday

    def test_last_completed_session_on_holiday(self):
        # Labor Day Monday 2026-09-07 -> last completed session is Friday 2026-09-04.
        snapshot = session_snapshot(datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(snapshot.state, SessionState.CLOSED)
        self.assertEqual(snapshot.last_completed_session, date(2026, 9, 4))


# ---------------------------------------------------------------------------
# F-10  design §7.1-7.4, §18
# ---------------------------------------------------------------------------

class F10FreshnessBySessionState(unittest.TestCase):
    """F-10 (design §7.1-7.4, §18): freshness by session state: an observation
    covering the last completed session is EOD_CURRENT when the market is
    closed and not refetched; the same observation during market hours beyond
    the configured TTL is STALE; a missing observation is MISSING.

    NOTE on the 60-second TTL: canonical_data/session_clock.py:evaluate_freshness
    line 162 hard-codes `live_ttl_seconds: int = 60` as a Python default
    parameter. Per design §7.4 this is a 'calibration/UAT seed... Approved
    values must be configuration, not embedded separately'; no TTL key exists
    anywhere in config/msi_runtime.json. This test uses the design's own
    proposed seed (60s) and is marked SEED_VALUE for that reason, and the
    fact that it is a Python default rather than a read configuration value
    is itself recorded as a finding.
    """

    def test_eod_current_when_market_closed_covers_last_completed_session(self):
        # Monday 2026-08-31 08:00 UTC = 04:00 ET premarket-ish edge; use a
        # clearly-closed instant instead: Sunday 2026-08-30 12:00 UTC.
        now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)  # Sunday, CLOSED
        last_session = session_snapshot(now).last_completed_session
        self.assertEqual(last_session, date(2026, 8, 28))  # Friday
        state = evaluate_freshness(
            as_of=datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc),
            dataset_session=last_session,
            domain="OPTION_CHAIN",
            now=now,
        )
        self.assertEqual(state, FreshnessState.EOD_CURRENT)

    def test_live_domain_becomes_stale_beyond_seed_ttl_during_market_hours(self):
        """SEED_VALUE: live_ttl_seconds default = 60 (design §7.4 proposed seed)."""
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)  # Monday regular session
        as_of = datetime(2026, 8, 31, 14, 57, tzinfo=timezone.utc)  # 180s old
        state = evaluate_freshness(
            as_of=as_of, dataset_session=date(2026, 8, 31), domain="UNDERLYING_NBBO",
            now=now, live_ttl_seconds=60,
        )
        self.assertEqual(state, FreshnessState.STALE)

    def test_live_domain_is_fresh_within_seed_ttl(self):
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
        as_of = datetime(2026, 8, 31, 14, 59, 30, tzinfo=timezone.utc)  # 30s old
        state = evaluate_freshness(
            as_of=as_of, dataset_session=date(2026, 8, 31), domain="UNDERLYING_NBBO",
            now=now, live_ttl_seconds=60,
        )
        self.assertEqual(state, FreshnessState.FRESH)

    def test_missing_observation_is_missing(self):
        state = evaluate_freshness(as_of=None, dataset_session=None, domain="UNDERLYING_NBBO")
        self.assertEqual(state, FreshnessState.MISSING)

    def test_evaluate_freshness_has_zero_production_callers(self):
        """Integration-gap finding, verified by direct in-process file scan
        (not shell grep): evaluate_freshness is only referenced by its own
        definition, canonical_data/__init__.py's re-export, and the
        implementer's own test file. No production consumer
        (morning_gate.py, pipeline_interpreter/evidence_resolver.py,
        contracts/interpreter_handoff_materializer.py, etc.) calls it, and no
        production code anywhere assigns a 'freshness_map' key (the field
        design §8.7 requires on every bundle) -- evidence_resolver.py only
        ever READS bundle.get('freshness_map'). This means §7's session-aware
        freshness policy exists as a correct, independently-testable
        function (see the three tests above) but is not wired into the
        pipeline that actually produces bundles."""
        callers = []
        for path in REPO_ROOT.rglob("*.py"):
            parts = path.parts
            if "backups" in parts or "venv" in parts or "__pycache__" in parts or "_cleanup_holding" in parts:
                continue
            if path.name in {"session_clock.py", "__init__.py"} and path.parent.name == "canonical_data":
                continue
            if path.parts[-2:] == ("tests", "test_msi_agent1_data_foundation.py")[:1] + (path.name,):
                pass
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "evaluate_freshness(" in content:
                callers.append(str(path.relative_to(REPO_ROOT)))
        self_path = Path(__file__).resolve()
        non_test_callers = [
            c for c in callers
            if not c.replace("\\", "/").startswith("tests/")
            and (REPO_ROOT / c).resolve() != self_path
        ]
        self.assertEqual(
            non_test_callers, [],
            f"expected zero production callers of evaluate_freshness(); found: {non_test_callers}",
        )
        # NOTE (not a failing assertion -- documented separately): a
        # 'freshness_map' key IS assigned in production, by
        # contracts/interpreter_handoff_materializer.py:_freshness_map
        # (line 151). That function builds the map from ad hoc ROW fields
        # (quote_freshness, underlying_quote_freshness, ms_freshness,
        # macro_freshness_status) rather than by calling evaluate_freshness()
        # itself. canonical_data/marketdata_response.py hardcodes
        # quote_freshness="UNASSESSED" as a literal (line 141) rather than
        # computing it via the shared session-aware service. So the
        # freshness_map FIELD exists structurally, but the design's central
        # 'consumers cannot recreate these rules locally' requirement
        # (design §16.3) is not demonstrated to be honoured end-to-end --
        # this is flagged as a design-inconsistency / integration-gap
        # finding rather than asserted as a pass/fail here, since fully
        # tracing every upstream writer of quote_freshness/ms_freshness is
        # outside this unit-level test's scope.


# ---------------------------------------------------------------------------
# F-11  design §4(6), §23, §14
# ---------------------------------------------------------------------------

def _make_resolver(tmp_root: Path, run_id: str, dataset_types, stage: str, ticker: str = "AAPL"):
    registry = CanonicalRegistry(tmp_root / f"{run_id}.sqlite")
    registry.initialise()
    session = date(2026, 8, 30)
    registry.register_run(run_id, "MORNING", session)
    lifecycle = LifecycleManager(registry)
    event = lifecycle.register(run_id, ticker, allowed_capabilities=dataset_types)
    # ACTIVE_DISCOVERY cannot transition directly to ACTIVE_OPTIONS/ACTIVE_MORNING
    # (canonical_data/lifecycle.py:LEGAL_TRANSITIONS) -- ACTIVE_CORE is a
    # mandatory intermediate step.
    event = lifecycle.transition(
        run_id, ticker, LifecycleState.ACTIVE_CORE, stage="PACKAGES",
        reason_code="TEST", expected_version=event.version,
        allowed_capabilities=dataset_types,
    )
    final_state = LifecycleState.ACTIVE_MORNING if stage == "MORNING_GATE" else LifecycleState.ACTIVE_OPTIONS
    lifecycle.transition(
        run_id, ticker, final_state, stage=stage,
        reason_code="TEST", expected_version=event.version,
        allowed_capabilities=dataset_types,
    )
    for dataset_type in dataset_types:
        lifecycle.create_worklist(run_id, stage, dataset_type, (ticker,))
    flags = CanonicalFeatureFlags(
        enabled=True, write_through=True, stage_gating_enforced=True,
        offline_replay=False, ohlcv_mode="ACTIVE",
    )
    resolver = CanonicalMarketObservationResolver(
        registry_path=tmp_root / f"{run_id}.sqlite",
        payload_root=tmp_root / f"{run_id}_payloads",
        run_id=run_id, flags=flags,
    )
    return resolver, session


class F11IdempotentRegistration(unittest.TestCase):
    """F-11 (design §4(6), §23, §14): idempotent registration: registering
    identical content twice returns the same dataset_id; the content hash
    excludes registry IDs, request ID, run ID and registration time and
    includes provider timestamps; changed content creates a new immutable
    revision and never overwrites.
    """

    def test_chain_registration_is_idempotent_for_identical_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolver, session = _make_resolver(
                root, "RCHAIN", (DatasetType.OPTION_CHAIN,), "OPTIONS"
            )
            calls = []
            def fetch(_ticker):
                calls.append(1)
                return fixture("option_chain_list_sizes.json")
            first = resolver.option_chain(
                ticker="AAPL", session_date=session, dte_max=110,
                min_open_interest=0, fetch=fetch,
            )
            second = resolver.option_chain(
                ticker="AAPL", session_date=session, dte_max=110,
                min_open_interest=0, fetch=fetch,
            )
            self.assertEqual(first.resolution, "PROVIDER_FETCH")
            self.assertIn(second.resolution, {"EXACT_HIT", "SUPERSET_HIT"})
            self.assertEqual(first.dataset_id, second.dataset_id)
            self.assertEqual(len(calls), 1)  # provider fetched exactly once

    def test_exact_quote_content_hash_embeds_run_id_breaking_cross_run_idempotency(self):
        """Design §23: 'content hash is SHA-256 of canonical sorted JSON
        excluding registry-generated IDs, request ID, run ID and registration
        time; economically meaningful provider timestamps remain included.'

        Evidence: canonical_data/market_observation_resolver.py:199-204
        (exact_option_quote's `normalise` closure) does
        `quote.update({'run_id': self.run_id, ...})` BEFORE the dict is
        handed to `_persist_json`, which hashes the payload verbatim
        (line 126-127). run_id is therefore INSIDE the hashed content,
        directly contradicting the design's explicit exclusion list. This
        test proves it behaviourally: identical exact-quote content observed
        under two different run_ids produces two different dataset_ids
        instead of the same idempotent one, using two independent resolver
        instances against the same fixture content (no live provider call)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolver_a, session = _make_resolver(
                root, "RUN_A", (DatasetType.EXACT_OPTION_QUOTE,), "MORNING_GATE"
            )
            resolver_b, _ = _make_resolver(
                root, "RUN_B", (DatasetType.EXACT_OPTION_QUOTE,), "MORNING_GATE"
            )
            symbol = "AAPL260918C00200000"

            def fetch(_ticker, _occ):
                return fixture("option_quote_scalar_ok.json")

            result_a = resolver_a.exact_option_quote(
                ticker="AAPL", symbol=symbol, session_date=session,
                freshness_seconds=10 ** 9, fetch=fetch,
            )
            result_b = resolver_b.exact_option_quote(
                ticker="AAPL", symbol=symbol, session_date=session,
                freshness_seconds=10 ** 9, fetch=fetch,
            )
            self.assertEqual(result_a.resolution, "PROVIDER_FETCH")
            self.assertEqual(result_b.resolution, "PROVIDER_FETCH")
            # Design intent: identical observed content -> same dataset_id
            # regardless of which run observed it. Actual behaviour: they
            # differ solely because run_id is baked into the hashed payload.
            self.assertNotEqual(
                result_a.dataset_id, result_b.dataset_id,
                "if this ever starts passing (equal ids), the run_id-in-hash "
                "defect described above has been fixed",
            )

    def test_changed_content_creates_new_id_and_does_not_overwrite(self):
        """Exercised directly at the registry level (canonical_data/registry.py:
        register_dataset, line 224) rather than through the resolver's
        request-scoped cache: a same-scope resolver.option_chain() call
        returns an EXACT_HIT from its own cache and never even invokes the
        fetch callback a second time (a separate, correctly-behaving 'reuse;
        do not refetch' result in itself -- design §6 requires exactly this
        for completed-session chains), so it cannot exercise the
        changed-content path. The registry's own immutability rule is what
        design §4(6)/§14 actually describes, so it is tested here directly."""
        from canonical_data.contracts import (
            CompletenessStatus, DataScope, DatasetRecord, DatasetType as DT,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = CanonicalRegistry(root / "control.sqlite")
            registry.initialise()
            registry.register_run("RREG", "MORNING", date(2026, 8, 30))
            as_of = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
            scope = DataScope(start_date=date(2026, 8, 30), end_date=date(2026, 8, 30))

            def record(content_hash: str, dataset_id: str) -> "DatasetRecord":
                return DatasetRecord(
                    dataset_id=dataset_id, dataset_type=DT.OPTION_CHAIN,
                    instrument_id="AAPL", session_date=date(2026, 8, 30), scope=scope,
                    provider="MARKETDATA", content_hash=content_hash,
                    completeness_status=CompletenessStatus.COMPLETE,
                    storage_uri=f"/tmp/{dataset_id}.json", observed_at=as_of, as_of=as_of,
                    source_run_id="RREG",
                )

            first_hash = "a" * 64
            second_hash = "b" * 64  # different content -> different hash
            first_id = "id_" + first_hash
            second_id = "id_" + second_hash
            registry.register_dataset(record(first_hash, first_id))
            registry.register_dataset(record(second_hash, second_id))
            self.assertNotEqual(first_id, second_id)
            record_first = registry.get_dataset(first_id)
            record_second = registry.get_dataset(second_id)
            self.assertIsNotNone(record_first)
            self.assertIsNotNone(record_second)
            self.assertEqual(record_first.content_hash, first_hash)
            self.assertEqual(record_second.content_hash, second_hash)

            # Attempting to register DIFFERENT content under the SAME
            # dataset_id (the actual "never overwrite" case) is rejected:
            with self.assertRaises(Exception):
                registry.register_dataset(record("c" * 64, first_id))
            # ... and the original is provably untouched:
            self.assertEqual(registry.get_dataset(first_id).content_hash, first_hash)

    def test_resolver_reuses_chain_without_refetch_for_same_scope(self):
        """Documents the resolver-level behaviour observed above as its own
        assertion (design §6: completed option chain -> 'Reuse; do not
        refetch'): a second resolver.option_chain() call with an identical
        scope never invokes fetch again, even when the fetch callback would
        have returned different content."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolver, session = _make_resolver(
                root, "RREUSE", (DatasetType.OPTION_CHAIN,), "OPTIONS"
            )
            first = resolver.option_chain(
                ticker="AAPL", session_date=session, dte_max=110,
                min_open_interest=0, fetch=lambda _t: fixture("option_chain_list_sizes.json"),
            )
            changed_payload = fixture("option_chain_list_sizes.json")
            changed_payload["bid"] = [4.5, 0]
            calls = []
            second = resolver.option_chain(
                ticker="AAPL", session_date=session, dte_max=110,
                min_open_interest=0,
                fetch=lambda _t: (calls.append(1) or changed_payload),
            )
            self.assertEqual(calls, [])  # fetch never invoked: reused from cache
            self.assertEqual(first.dataset_id, second.dataset_id)


# ---------------------------------------------------------------------------
# F-12  design §4(3), §9.1, §14, §18
# ---------------------------------------------------------------------------

class F12WorklistBlocking(unittest.TestCase):
    """F-12 (design §4(3), §9.1, §14, §18): a request for a ticker not in the
    active worklist is refused and a worklist rejection is recorded in the
    ledger; no provider adapter is invoked.

    Evidence: canonical_data/gateway.py:resolve (line 33) calls
    lifecycle.authorise_worklist before any fetch; on refusal it calls
    ledger.record_blocked (line 50) and raises FetchNotAuthorised BEFORE the
    resolver's fetch callback is ever invoked
    (canonical_data/market_observation_resolver.py:_resolve, line 146).
    """

    def test_unregistered_ticker_is_blocked_ledger_records_it_no_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = CanonicalRegistry(root / "control.sqlite")
            registry.initialise()
            session = date(2026, 8, 30)
            registry.register_run("R1", "OPTIONS", session)
            # deliberately do NOT register/worklist "DROP"
            flags = CanonicalFeatureFlags(
                enabled=True, write_through=True, stage_gating_enforced=True,
                offline_replay=False, ohlcv_mode="ACTIVE",
            )
            resolver = CanonicalMarketObservationResolver(
                registry_path=root / "control.sqlite", payload_root=root / "payloads",
                run_id="R1", flags=flags,
            )
            fetch_calls = []
            with self.assertRaises(FetchNotAuthorised):
                resolver.option_chain(
                    ticker="DROP", session_date=session, dte_max=110,
                    min_open_interest=0,
                    fetch=lambda _t: (fetch_calls.append(1) or fixture("option_chain_list_sizes.json")),
                )
            self.assertEqual(fetch_calls, [])  # provider adapter never invoked

            ledger = RequestLedger(registry)
            entries = ledger.entries("R1")
            blocked = [e for e in entries if e["resolution"] == RequestResolution.BLOCKED_NOT_AUTHORISED.value]
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked[0]["ticker"], "DROP")
            self.assertEqual(blocked[0]["physical_request_count"], 0)
            self.assertIn("NOT_REGISTERED", blocked[0]["reason"])

    def test_worklisted_ticker_not_in_stage_worklist_table_is_blocked(self):
        """Ticker registered/active but never added to stage_worklist (the
        persisted worklist membership table) is still blocked -- i.e. active
        lifecycle state alone is not sufficient; explicit worklist membership
        is separately required (canonical_data/lifecycle.py:authorise_worklist,
        line 438)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = CanonicalRegistry(root / "control.sqlite")
            registry.initialise()
            session = date(2026, 8, 30)
            registry.register_run("R1", "OPTIONS", session)
            lifecycle = LifecycleManager(registry)
            event = lifecycle.register(
                "R1", "AAPL", allowed_capabilities=(DatasetType.OPTION_CHAIN,)
            )
            event = lifecycle.transition(
                "R1", "AAPL", LifecycleState.ACTIVE_CORE, stage="PACKAGES",
                reason_code="TEST", expected_version=event.version,
                allowed_capabilities=(DatasetType.OPTION_CHAIN,),
            )
            lifecycle.transition(
                "R1", "AAPL", LifecycleState.ACTIVE_OPTIONS, stage="OPTIONS",
                reason_code="TEST", expected_version=event.version,
                allowed_capabilities=(DatasetType.OPTION_CHAIN,),
            )
            # NOTE: no lifecycle.create_worklist() call for AAPL/OPTIONS.
            flags = CanonicalFeatureFlags(
                enabled=True, write_through=True, stage_gating_enforced=True,
                offline_replay=False, ohlcv_mode="ACTIVE",
            )
            resolver = CanonicalMarketObservationResolver(
                registry_path=root / "control.sqlite", payload_root=root / "payloads",
                run_id="R1", flags=flags,
            )
            with self.assertRaises(FetchNotAuthorised) as ctx:
                resolver.option_chain(
                    ticker="AAPL", session_date=session, dte_max=110,
                    min_open_interest=0,
                    fetch=lambda _t: fixture("option_chain_list_sizes.json"),
                )
            self.assertIn("WORKLIST", str(ctx.exception))


# ---------------------------------------------------------------------------
# F-13  design §24
# ---------------------------------------------------------------------------

class F13EnumAudit(unittest.TestCase):
    """F-13 (design §24): every enum in §24 exists in its owning contract
    module with exactly the listed values; grep the repo for local string
    sets that redeclare any of these values outside the owning module."""

    def test_run_kind_matches_exactly(self):
        self.assertEqual(
            {member.value for member in RunKind},
            {"PRODUCTION", "TEST", "REPLAY", "REPAIR", "RESEARCH"},
        )

    def test_run_status_matches_exactly(self):
        self.assertEqual(
            {member.value for member in RunStatus},
            {"IN_PROGRESS", "COMPLETED", "ABORTED", "ACCEPTED"},
        )

    def test_handoff_matches_exactly(self):
        self.assertEqual(
            {member.value for member in HandoffStatus},
            {"READY", "BLOCKED_MISSING_STAGE", "BLOCKED_IDENTITY", "BLOCKED_HASH", "BLOCKED_RECONCILIATION"},
        )

    def test_assessment_matches_exactly(self):
        self.assertEqual(
            {member.value for member in AssessmentStatus},
            {"VALID", "REJECTED_SCHEMA", "REJECTED_GOVERNANCE_CONFLICT", "REJECTED_STALE_BUNDLE"},
        )

    def test_freshness_matches_exactly(self):
        self.assertEqual(
            {member.value for member in FreshnessState},
            {"FRESH", "EOD_CURRENT", "STALE", "MISSING", "INVALID"},
        )

    def test_size_quality_has_NO_owning_enum_module(self):
        """§24: 'Enums live in their owning contract module and are imported,
        never redeclared as local string sets.' No SizeQuality Enum class
        exists anywhere in the repo (confirmed by direct source scan below);
        'OBSERVED_ZERO'/'OBSERVED_POSITIVE'/'MISSING' are inline string
        literals independently duplicated in at least 4 places:
        canonical_data/marketdata_response.py:51,
        canonical_data/market_observation_resolver.py:75,
        scripts/avshunter_options_intelligence.py:1492,1501 and :2530,2531.
        This fails both halves of the §24 requirement: no owning module, and
        the literal value used ('OBSERVED_POSITIVE') does not match the
        design's own enum value ('OBSERVED') -- see F-04."""
        found_class = False
        for path in REPO_ROOT.rglob("*.py"):
            parts = path.parts
            if "backups" in parts or "venv" in parts or "__pycache__" in parts or "_cleanup_holding" in parts:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"class\s+SizeQuality\b", content):
                found_class = True
        self.assertFalse(found_class, "expected no owning SizeQuality enum module to exist")

    def test_quote_quality_values_deviate_from_design_enum(self):
        """§24 Quote quality = TWO_SIDED, ONE_SIDED, CROSSED, MISSING,
        INVALID. canonical_data/marketdata_response.py:_quote (line 72-90)
        never emits 'CROSSED' (uses 'INVALID' for bid>ask, see F-05) and
        never emits 'MISSING' for the incomplete case (uses 'INCOMPLETE',
        an extraneous value not in the design's enum at all)."""
        frame = parse_marketdata_option_response(
            fixture("option_quote_crossed.json"), ticker="AAPL"
        )
        emitted_for_crossed = frame.iloc[0]["quote_quality"]
        self.assertNotIn(emitted_for_crossed, {"TWO_SIDED", "ONE_SIDED", "CROSSED", "MISSING", "INVALID"} - {"INVALID"})
        self.assertEqual(emitted_for_crossed, "INVALID")  # actual (not a §24 CROSSED value)

    def test_structure_lifecycle_introduces_undeclared_MS_NONE_value(self):
        """§24 Structure lifecycle = MS_DEVELOPING, MS_ACCEPTED, MS_CONTINUING,
        MS_REPAIRING, MS_FAILED (5 values). market_structure/lifecycle.py:11
        `transition_lifecycle` can additionally return 'MS_NONE' (when no
        distribution is detected and there is no prior lifecycle), which is
        NOT one of the 5 declared values, and this value flows directly into
        the persisted evidence's ms_lifecycle field via
        market_structure/service.py:56."""
        result = transition_lifecycle(
            prior=None, detected=False, accepted=False, repair_pct=0.0, invalidated=False
        )
        self.assertEqual(result, "MS_NONE")
        self.assertNotIn(
            result,
            {"MS_DEVELOPING", "MS_ACCEPTED", "MS_CONTINUING", "MS_REPAIRING", "MS_FAILED"},
        )

    def test_structure_lifecycle_and_relationship_have_no_owning_enum_class(self):
        found = False
        for path in REPO_ROOT.rglob("*.py"):
            parts = path.parts
            if "backups" in parts or "venv" in parts or "__pycache__" in parts or "_cleanup_holding" in parts:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"class\s+(MSLifecycle|StructureLifecycle|MSDirectionRelationship|StructureRelationship)\b", content):
                found = True
        self.assertFalse(found, "expected no owning Structure-lifecycle/relationship enum module")


# ---------------------------------------------------------------------------
# F-14  design §8.6
# ---------------------------------------------------------------------------

class F14MsPrefixDiscipline(unittest.TestCase):
    """F-14 (design §8.6): every field emitted by the Market Structure service
    carries the ms_ prefix; no unqualified lifecycle_state, quality, direction
    or status field is introduced by MSI modules.

    Design §8.6 explicitly carves out identity/lineage fields (ticker,
    session, run ID, calculation timestamp) as unqualified by definition, so
    those are excluded from the ms_-prefix requirement itself.
    """

    @staticmethod
    def _bars() -> pd.DataFrame:
        start = pd.Timestamp("2026-08-28T13:30:00Z")
        rows = []
        for index in range(120):
            base = 100.0 if index < 60 else 103.0
            rows.append({
                "timestamp_utc": start + pd.Timedelta(minutes=index),
                "open": base, "high": base + 0.05, "low": base - 0.05,
                "close": base + 0.02, "volume": 1000, "session_segment": "REGULAR",
            })
        from canonical_data.intraday_bars import normalise_minute_bars
        return normalise_minute_bars(pd.DataFrame(rows), ticker="TEST")

    def test_every_field_is_ms_prefixed_or_identity_lineage(self):
        evidence = calculate_market_structure_evidence(
            ticker="TEST", session_date=date(2026, 8, 28), run_id="R1", bars=self._bars(),
            exchange_tick=0.01, atr14=2.0,
            regular_open_utc=datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
        )
        identity_lineage = {"ticker", "session_date", "run_id"}
        offenders = [
            key for key in evidence
            if not key.startswith("ms_") and key not in identity_lineage
        ]
        self.assertEqual(offenders, [])

    def test_no_unqualified_forbidden_field_names(self):
        evidence = calculate_market_structure_evidence(
            ticker="TEST", session_date=date(2026, 8, 28), run_id="R1", bars=self._bars(),
            exchange_tick=0.01, atr14=2.0,
            regular_open_utc=datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
        )
        for forbidden in ("lifecycle_state", "quality", "direction", "status"):
            self.assertNotIn(forbidden, evidence)


# ---------------------------------------------------------------------------
# F-15  design §8.2
# ---------------------------------------------------------------------------

class F15PersistedPrecision(unittest.TestCase):
    """F-15 (design §8.2): persisted prices have four decimal places, sizes
    are integers, ratios are 0-1 decimals, timestamps are ISO-8601 UTC to the
    second."""

    def test_sizes_are_python_int(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        for value in frame["bid_size"]:
            if value is not None:
                self.assertIsInstance(value, int)

    def test_timestamps_are_iso8601_utc_to_the_second(self):
        frame = parse_marketdata_option_response(
            fixture("option_chain_list_sizes.json"), ticker="AAPL"
        )
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        for value in frame["quote_timestamp_utc"]:
            self.assertIsNotNone(value)
            self.assertRegex(value, pattern)

    def test_mid_price_is_NOT_rounded_to_four_decimal_places(self):
        """Design §8.2: 'persisted prices use four decimal places.' The
        option-chain/exact-quote arithmetic helper
        (canonical_data/marketdata_response.py:_quote, line 72-90) never
        calls round()/format on bid/ask/mid/spread_pct -- it stores the raw
        float division result as-is (contrast with
        market_observation_resolver.normalise_underlying_nbbo, which
        explicitly calls round(..., 4), see the passing test below).
        Demonstrated with a bid/ask pair whose true mathematical midpoint
        needs 5 decimal places (1.00001 + 1.00003) / 2 = 1.00002; a genuine
        4-decimal-place persistence rule would round this to 1.0."""
        payload = {
            "s": "ok", "optionSymbol": ["AAPL260918C00200000"], "side": ["call"],
            "bid": [1.00001], "ask": [1.00003], "bidSize": [1], "askSize": [1],
            "updated": [1788120000],
        }
        frame = parse_marketdata_option_response(payload, ticker="AAPL")
        mid = frame.iloc[0]["mid"]
        self.assertAlmostEqual(mid, 1.00002, places=6)  # raw, un-rounded value
        self.assertNotEqual(
            round(mid, 4), mid,
            "expected mid to retain more than 4 decimal places (i.e. NOT be "
            "pre-rounded by the code), demonstrating the design's 4-dp "
            "persistence requirement is not enforced at this layer",
        )

    def test_underlying_nbbo_normaliser_DOES_round_to_four_decimals(self):
        """By contrast, canonical_data/market_observation_resolver.py:
        normalise_underlying_nbbo (line 94) explicitly calls round(bid, 4)/
        round(ask, 4)/round(mid, 4) -- the 4-decimal-place requirement IS met
        for the underlying-NBBO path even though it is not met for the
        option-chain/exact-quote path above."""
        payload = {
            "bid": [1.111111], "ask": [2.222222],
            "updated": [datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)],
        }
        result = normalise_underlying_nbbo(payload, ticker="AAPL", provider="POLYGON")
        self.assertEqual(result["bid"], round(1.111111, 4))
        self.assertEqual(result["mid"], round((1.111111 + 2.222222) / 2.0, 4))

    def test_repair_pct_ratio_is_bounded_0_to_1(self):
        bars = F14MsPrefixDiscipline._bars()
        evidence = calculate_market_structure_evidence(
            ticker="TEST", session_date=date(2026, 8, 28), run_id="R1", bars=bars,
            exchange_tick=0.01, atr14=2.0,
            regular_open_utc=datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
        )
        self.assertGreaterEqual(evidence["ms_repair_pct"], 0.0)
        self.assertLessEqual(evidence["ms_repair_pct"], 1.0)


if __name__ == "__main__":
    unittest.main()
