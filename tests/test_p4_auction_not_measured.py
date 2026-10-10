"""Phase 4 / RC02: unmeasured auction fields are NOT_MEASURED, never zero or NEUTRAL (R1).

Business rules:
- A completed market profile measures POC, value area and where price sits in it. It does NOT measure acceptance,
  control or migration: those read NOT_MEASURED (controller, migration direction) and NaN (scores), so no consumer
  can treat "unmeasured" as a weak/neutral reading. Phase 0: all 1,702 rows had control confidence 0 and NEUTRAL.
- The legacy auction-based structure score reads NOT_MEASURED when acceptance was not measured (it was WEAK on
  every row by construction).
"""
import math

import pandas as pd

from vanguard.layer1_auction.auction_synthesizer import AuctionStateSynthesizer
from vanguard.layer2_statistical.state_calculator import StateVectorCalculator
from vanguard.schemas.input_schema import TechnicalData
from test_dynamic_session_phase4 import valid_evidence, vanguard_input


def _unmeasured(v):
    assert math.isnan(v.acceptance.score)
    assert v.control.controller == "NOT_MEASURED" and math.isnan(v.control.confidence)
    assert v.migration.direction == "NOT_MEASURED" and math.isnan(v.migration.magnitude)


def test_governed_profile_keeps_what_it_measures_and_marks_the_rest():
    ev = valid_evidence()
    v = AuctionStateSynthesizer().synthesize(vanguard_input(ev.to_dict()))
    assert v.profile.poc == ev.poc and v.acceptance.position_in_profile in {"INSIDE_VALUE", "ABOVE_VALUE",
                                                                             "BELOW_VALUE"}
    _unmeasured(v)


def test_missing_profile_is_not_measured_too():
    _unmeasured(AuctionStateSynthesizer().synthesize(vanguard_input(None)))


def test_legacy_auction_structure_score_is_not_measured_not_weak():
    v = AuctionStateSynthesizer().synthesize(vanguard_input(valid_evidence().to_dict()))
    tech = TechnicalData(ohlcv=pd.DataFrame({"close": [100.0, 101.0], "volume": [1e6, 1e6]}), atr_current=1.0)
    out = StateVectorCalculator()._calculate_structure_quality(tech, v)
    assert out["quality"] == "NOT_MEASURED"
