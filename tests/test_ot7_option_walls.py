"""Output-trust item 7 (D5-2 / D5-3 enhanced by ACK's call-wall review, 10 Oct 2026).

Design: Enhancements/phase7/ITEM7_WALLS_DESIGN_20261010.md. Root cause confirmed on data: SMCI 8 Oct put wall 3.0 was
SMCI270115P00003000 (largest raw OI, gamma 0.0001) - the highest open interest anywhere in a 1-110 day chain.

Business rules (three separate conclusions; concentration never establishes support, resistance or direction):
- Instrument: only the ticker's own root; other roots excluded and counted; a missing multiplier is stated.
- Expiry baskets by actual dates: TODAY, THROUGH_EXIT (to the planned exit), AFTER_EXIT (to the longer cutoff).
- Measure: gamma x OI x multiplier (x S^2 x 0.01), unsigned, per side; zones, materiality, relevance band; never forced.
- Dealer influence is separate: gamma flip with confidence state; the dealer sign is a labelled assumption.
- Observed price response from completed daily bars: untested / observed support or resistance / breached /
  continuation / failed break; absorption flag.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from domain.option_walls import WALL_FIELDS, assess_option_walls, price_response_status

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
SPOT = 42.77


@pytest.fixture(scope="module")
def smci_chain():
    return pd.DataFrame(json.loads((FIX / "smci_option_chain_20261008.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def smci_bars():
    return pd.read_csv(FIX / "smci_daily_20261008.csv", parse_dates=["date"])


def _assess(chain, bars=None, **kw):
    base = dict(ticker="SMCI", spot=SPOT, trade_session=date(2026, 10, 9), hold_sessions=21, atm_iv=None, bars=bars,
                chain_asof_utc="2026-10-08T20:00:00Z")
    base.update(kw)
    return assess_option_walls(chain, **base)


def test_smci_no_longer_reports_a_3_dollar_put_wall(smci_chain):
    out = _assess(smci_chain)
    assert out["wall_hold_put_peak"] != 3.0 and out["wall_post_put_peak"] != 3.0
    assert 38.0 <= out["wall_hold_put_peak"] < SPOT and SPOT < out["wall_hold_call_peak"] <= 47.0
    assert out["wall_hold_put_low"] <= out["wall_hold_put_peak"] <= out["wall_hold_put_high"]
    assert out["wall_hold_put_state"] == "QUALIFIED" and out["wall_hold_put_share"] >= 0.10
    assert out["wall_exit_date"] == "2026-11-09"                        # 21 XNYS sessions after 9 Oct
    assert out["wall_method"] == "GAMMA_OI_CONCENTRATION_V1"
    assert out["wall_multiplier_basis"] == "MULTIPLIER_ASSUMED_100_NOT_PROVIDED"
    assert out["wall_dealer_sign"] == "NOT_ESTIMATED_CONCENTRATION_IS_UNSIGNED"
    assert set(WALL_FIELDS) <= set(out)


def test_expiries_are_separated_by_actual_dates(smci_chain):
    out = _assess(smci_chain)
    baskets = json.loads(out["wall_map_json"])["baskets"]
    assert baskets["TODAY"]["expiries"] == ["2026-10-09"]
    assert baskets["THROUGH_EXIT"]["expiries"][-1] <= "2026-11-09" < baskets["AFTER_EXIT"]["expiries"][0]
    assert "2027-01-15" in baskets["AFTER_EXIT"]["expiries"]


def test_other_roots_are_excluded_and_counted(smci_chain):
    adjusted = smci_chain.head(3).assign(underlying="SMCI1", symbol=lambda d: d["symbol"].str.replace("SMCI", "SMCI1"))
    out = _assess(pd.concat([smci_chain, adjusted], ignore_index=True))
    assert out["wall_excluded_contracts"] == 3


def test_nothing_material_is_never_forced(smci_chain):
    out = _assess(smci_chain, policy_overrides={"materiality_share_min": 0.95})
    assert out["wall_hold_call_state"] == "NO_QUALIFIED_WALL" and out["wall_hold_call_peak"] is None


def test_a_call_concentration_below_spot_is_never_overhead(smci_chain):
    out = _assess(smci_chain)
    assert out["wall_hold_call_peak"] is None or out["wall_hold_call_peak"] > SPOT
    zones = json.loads(out["wall_map_json"])["baskets"]["THROUGH_EXIT"]["call_zones"]
    assert all(z["peak"] > SPOT for z in zones)


def test_without_a_hold_the_exit_basket_is_stated_unavailable(smci_chain):
    out = _assess(smci_chain, hold_sessions=None)
    assert out["wall_hold_call_state"] == "NO_PLANNED_EXIT" and out["wall_exit_date"] is None


# ------------------------------------------------------------------ observed price response
def _bars(closes, highs=None, lows=None, volume=1_000_000):
    n = len(closes)
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    return pd.DataFrame({"date": pd.bdate_range("2026-07-01", periods=n), "open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": [volume] * n})


def test_price_response_statuses():
    flat = [40.0] * 30
    assert price_response_status(_bars(flat), low=50, high=51)["status"] == "UNTESTED_CONCENTRATION"
    # two touches of 50-51 from below, both closing back below -> observed resistance
    closes = [45.0] * 10 + [49.0] * 5 + [46.0] * 5 + [49.0] * 5 + [46.0] * 5
    highs = [c + 0.5 for c in closes]
    highs[12] = 50.6
    highs[22] = 50.4
    res = price_response_status(_bars(closes, highs=highs), low=50, high=51)
    assert res["status"] == "OBSERVED_RESISTANCE" and res["rejections"] == 2
    # closes above the zone, then back below and failing to recover -> failed break
    fb = [45.0] * 10 + [52.0] * 3 + [47.0] * 10
    assert price_response_status(_bars(fb), low=50, high=51)["status"] == "FAILED_BREAK_ASSESSING"
    # came from below, now above, no retest yet -> breached, acceptance being assessed
    br = [45.0] * 10 + [53.0] * 3
    assert price_response_status(_bars(br, lows=[c - 0.5 for c in br]), low=50, high=51)["status"] == \
        "BREACHED_ACCEPTANCE_ASSESSING"
    # came from below, broke above, retested the zone and held -> continuation supported
    ct = [45.0] * 10 + [53.0] * 5 + [52.0] * 3 + [55.0] * 3
    lows = [c - 0.5 for c in ct]
    lows[16] = 50.8
    assert price_response_status(_bars(ct, lows=lows), low=50, high=51)["status"] == "CONTINUATION_SUPPORTED"


def test_smci_walls_carry_a_price_status(smci_chain, smci_bars):
    out = _assess(smci_chain, bars=smci_bars)
    assert out["wall_hold_put_price_status"] in {"UNTESTED_CONCENTRATION", "OBSERVED_SUPPORT", "SINGLE_REJECTION",
                                                 "BREACHED_ACCEPTANCE_ASSESSING", "CONTINUATION_SUPPORTED",
                                                 "FAILED_BREAK_ASSESSING", "AT_LEVEL", "CONTESTED_LEVEL"}
    assert out["wall_price_basis"].startswith("DAILY_BARS:")


def test_the_gamma_flip_states_its_confidence():
    from domain.option_walls import gamma_flip_confidence_state
    assert gamma_flip_confidence_state(37.3, 0.067) == "LOW_CONFIDENCE"
    assert gamma_flip_confidence_state(37.3, 0.9) == "CONFIDENT"
    assert gamma_flip_confidence_state(None, 0.0) == "NO_FLIP"


def test_oi_clearing_date_is_the_session_before_the_chain_and_zones_rank_by_share(smci_chain):
    out = _assess(smci_chain)
    assert out["wall_oi_clearing_date"] == "2026-10-07"                 # an 8 Oct close chain carries 7 Oct OI
    for basket in json.loads(out["wall_map_json"])["baskets"].values():
        for side in ("call", "put"):
            shares = [z["share"] for z in basket[f"{side}_zones"]]
            assert shares == sorted(shares, reverse=True)


def test_the_book_carries_the_walls_and_the_card_shows_the_display_chain(smci_chain, smci_bars):
    import re
    import subprocess
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    walls = _assess(smci_chain, bars=smci_bars)
    assert set(WALL_FIELDS) <= set(FINAL_BOOK_FIELDS)
    row = opportunity_book_row({"ticker": "SMCI", "direction": "CALL", "put_wall": 3.0, "call_wall": 50.0,
                                "gamma_flip": 37.297, "gamma_flip_conf": 0.067,
                                **{f"opt__{k}": v for k, v in walls.items()}, "gamma_flip_confidence_state": "LOW_CONFIDENCE"},
                               "RUN", 1)
    assert row["wall_hold_put_peak"] == walls["wall_hold_put_peak"]
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    out = subprocess.run(["node"], input=card + f"\nconst h = renderTradeCard({json.dumps(row, default=str)});\n"
                         "console.log(JSON.stringify({put: h.includes('SMCI · put zone 41.00') && h.includes('through 2026-11-09'),"
                         " method: h.includes('gamma x OI') && h.includes('14% of basket'),"
                         " stamps: h.includes('chain 2026-10-08') && h.includes('OI 2026-10-07'),"
                         " sign: h.includes('dealer sign not estimated'),"
                         " status: h.includes('continuation supported'),"
                         " flip: h.includes('indicative only (confidence 0.07'),"
                         " noThree: !h.includes('3.00')}));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"put": True, "method": True, "stamps": True,
                                                               "sign": True, "status": True, "flip": True,
                                                               "noThree": True}
    legacy = re.search(r"const TC_LEGACY = (/.*?/i);", card).group(1)
    # readers build (ACK 10 Oct 2026): call_wall / put_wall now carry the governed wall; only the raw-OI values are legacy
    probe = subprocess.run(["node"], input=f"const re = {legacy};\nconsole.log(JSON.stringify(['legacy_oi_call_wall',"
                           "'legacy_oi_put_wall','oi_max_put_strike','call_wall','put_wall'].map(f => re.test(f))));",
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert json.loads(probe.stdout.strip().splitlines()[-1]) == [True, True, True, False, False]


def test_repeated_crossings_are_contested_and_a_retest_needs_follow_through():
    chop = [45.0] * 5 + [53.0] * 3 + [47.0] * 3 + [53.0] * 3 + [47.0] * 3
    assert price_response_status(_bars(chop), low=50, high=51)["status"] == "CONTESTED_LEVEL"
    # crossed above, retest held, but no follow-through beyond the retest close yet
    nf = [45.0] * 10 + [53.0] * 5 + [52.0] * 3
    lows = [c - 0.5 for c in nf]
    lows[16] = 50.8
    out = price_response_status(_bars(nf, lows=lows), low=50, high=51)
    assert out["status"] == "BREACHED_ACCEPTANCE_ASSESSING" and "follow-through pending" in out["note"]


# ------------------------------------------------------------------ readers (ACK approved 10 Oct 2026, design section 8)
def test_readers_get_the_hold_zone_and_the_legacy_raw_oi_stays_by_name(smci_chain, smci_bars):
    from domain.option_walls import governed_walls
    w = _assess(smci_chain, bars=smci_bars)
    legacy = {"call_wall": 50.0, "put_wall": 3.0, "call_wall_state": "OI_MAX_ABOVE_SPOT",
              "put_wall_state": "OI_MAX_BELOW_SPOT", "max_pain": 40.0, "oi_max_call_strike": 50.0, "oi_max_put_strike": 3.0}
    g = governed_walls(w, legacy)
    assert (g["call_wall"], g["put_wall"]) == (w["wall_hold_call_peak"], w["wall_hold_put_peak"])
    assert g["call_wall_state"] == "QUALIFIED" and g["max_pain"] == 40.0
    assert (g["legacy_oi_call_wall"], g["legacy_oi_put_wall"]) == (50.0, 3.0)
    assert g["wall_basis"] == "GAMMA_OI_CONCENTRATION_V1:THROUGH_EXIT"
    assert g["call_wall_level_confirmed"] is True                       # 45: observed resistance
    assert g["put_wall_level_confirmed"] is True                        # 41: continuation supported


def test_a_wall_is_a_price_level_only_when_price_confirmed_it():
    from domain.option_walls import level_wall
    row = {"wall_method": "GAMMA_OI_CONCENTRATION_V1", "call_wall": 45.0, "call_wall_level_confirmed": True,
           "put_wall": 41.0, "put_wall_level_confirmed": False}
    assert level_wall(row, "call") == 45.0 and level_wall(row, "put") is None
    assert level_wall({"call_wall": 50.0}, "call") == 50.0             # a pre-item-7 row keeps its legacy reading


def test_the_exit_plan_and_the_runway_veto_use_only_confirmed_levels():
    import inspect
    import eod_candidate_engine
    from scripts import avshunter_superbrain_layer as sb
    src = inspect.getsource(eod_candidate_engine)
    assert 'call_wall=level_wall(row, "call"), put_wall=level_wall(row, "put")' in src
    signal = {"direction": "CALL", "underlying_price": 44.0, "spot": 44.0, "breakeven_pct": 5.0,
              "wall_method": "GAMMA_OI_CONCENTRATION_V1", "call_wall": 44.0, "call_wall_level_confirmed": False}
    assert not any(v.startswith("V2_AT_WALL") for v in sb.apply_behavioural_vetoes(signal, {})[0])
    confirmed = {**signal, "call_wall_level_confirmed": True}
    assert any(v.startswith("V2_AT_WALL") for v in sb.apply_behavioural_vetoes(confirmed, {})[0])


def test_no_confirmed_wall_means_the_runway_is_not_limited_not_that_there_is_none():
    from scripts import avshunter_superbrain_layer as sb
    signal = {"direction": "CALL", "underlying_price": 44.0, "spot": 44.0, "breakeven_pct": 5.0, "ivp": 0.95,
              "iv_percentile": 0.95, "wall_method": "GAMMA_OI_CONCENTRATION_V1", "call_wall": 45.0,
              "call_wall_level_confirmed": False}
    vetoes = sb.apply_behavioural_vetoes(signal, {})[0]
    assert not any(v.startswith("V3_HIGH_IV_NO_EDGE") for v in vetoes)
    near = {**signal, "call_wall_level_confirmed": True}                # a confirmed wall 2.3% away still fires V3
    assert any(v.startswith("V3_HIGH_IV_NO_EDGE") for v in sb.apply_behavioural_vetoes(near, {})[0])
