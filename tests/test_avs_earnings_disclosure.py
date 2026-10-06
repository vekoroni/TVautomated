"""Earnings disclosure (design AVS_ANTICIPATED_MOVE_DESIGN_20261003 §9 step 1; ACK 3 Oct 2026).

Business rules:
- Catalysts are bonuses; an earnings date is position-risk disclosure (gap, IV crush), never a gate or score.
- The date comes from MarketData (/v1/stocks/earnings/), the options vendor; the Polygon snapshot carries no
  earnings field (verified 3 Oct), so the former enricher never produced a date (every row UNKNOWN).
- Three explicit states: SCHEDULED, NONE_IN_LOOKAHEAD, UNKNOWN (with reason). Unknown is never "no catalyst".
- Disclosed against the trade: XNYS sessions to the report, inside the planned hold, inside the contract's life.
- The fields travel with the row to the book and the Morning recomputes the session count; one fetch per run.
No network: the provider response is injected.
"""
import json
from datetime import date

import pandas as pd

from canonical_data.marketdata_earnings import fetch_marketdata_earnings, parse_marketdata_earnings
from earnings_calendar_enricher import EARNINGS_DISCLOSURE_FIELDS, earnings_disclosure

AS_OF = date(2026, 10, 2)
SOFI = {"s": "ok", "symbol": ["SOFI"], "fiscalYear": [2026], "fiscalQuarter": [3], "date": [1790740800],
        "reportDate": [1793073600], "reportTime": ["before open"], "currency": [None], "reportedEPS": [None],
        "estimatedEPS": [0.17], "surpriseEPS": [None], "surpriseEPSpct": [None], "updated": [1790827200]}


def test_marketdata_payload_gives_the_next_report():
    e = parse_marketdata_earnings(SOFI, as_of=AS_OF)
    assert e["state"] == "SCHEDULED"
    assert e["date"] == "2026-10-27" and e["report_time"] == "BEFORE_OPEN"
    assert e["fiscal_quarter"] == "2026Q3"


def test_no_data_and_errors_are_stated():
    assert parse_marketdata_earnings({"s": "no_data"}, as_of=AS_OF)["state"] == "NONE_IN_LOOKAHEAD"
    bad = parse_marketdata_earnings({"s": "error", "errmsg": "boom"}, as_of=AS_OF)
    assert bad["state"] == "UNKNOWN" and "boom" in bad["reason"]


def test_disclosure_against_hold_and_expiry():
    e = parse_marketdata_earnings(SOFI, as_of=AS_OF)
    d = earnings_disclosure(e, as_of=AS_OF, hold_sessions=20, expiry="2026-12-18")
    assert set(EARNINGS_DISCLOSURE_FIELDS) <= set(d)
    assert d["earnings_state"] == "SCHEDULED" and d["earnings_sessions_to_event"] == 17
    assert d["earnings_inside_hold"] is True and d["earnings_inside_expiry"] is True
    assert "inside the 20-session hold" in d["earnings_disclosure"]
    assert d["earnings_authority"] == "DISCLOSURE_ONLY"


def test_unknown_is_never_called_no_catalyst():
    d = earnings_disclosure({"state": "UNKNOWN", "reason": "HTTP_503"}, as_of=AS_OF, hold_sessions=20,
                            expiry="2026-12-18")
    assert d["earnings_state"] == "UNKNOWN"
    assert d["earnings_inside_hold"] is None and d["earnings_inside_expiry"] is None
    assert "unknown" in d["earnings_disclosure"].lower() and "no catalyst" not in d["earnings_disclosure"].lower()


def test_unestimated_hold_leaves_inside_hold_unknown():
    e = parse_marketdata_earnings(SOFI, as_of=AS_OF)
    d = earnings_disclosure(e, as_of=AS_OF, hold_sessions=None, expiry="2026-12-18")
    assert d["earnings_inside_hold"] is None and d["earnings_inside_expiry"] is True


def test_fetch_uses_injected_transport_and_caches_per_session(tmp_path):
    calls = []

    def transport(symbol, start, end):
        calls.append(symbol)
        return 200, SOFI if symbol == "SOFI" else {"s": "no_data"}

    first = fetch_marketdata_earnings(["SOFI", "XLF"], as_of=AS_OF, cache_dir=tmp_path, transport=transport)
    again = fetch_marketdata_earnings(["SOFI", "XLF"], as_of=AS_OF, cache_dir=tmp_path, transport=transport)
    assert first["SOFI"]["date"] == "2026-10-27" and first["XLF"]["state"] == "NONE_IN_LOOKAHEAD"
    assert again == first and calls == ["SOFI", "XLF"]


def test_evening_patch_adds_the_fields_to_the_options_csv(tmp_path):
    import intelligent_orchestrator as io
    csv = tmp_path / "oi.csv"
    pd.DataFrame([{"ticker": "SOFI", "planned_hold_sessions": 20, "expiry": "2026-12-18"},
                  {"ticker": "XLF", "planned_hold_sessions": 20, "expiry": "2027-01-15"}]).to_csv(csv, index=False)
    fake = {"SOFI": parse_marketdata_earnings(SOFI, as_of=AS_OF), "XLF": {"state": "NONE_IN_LOOKAHEAD"}}
    assert io.patch_earnings_fields_into_csv("20261002_211641", csv, "test", fetcher=lambda tickers, as_of: fake)
    out = pd.read_csv(csv).set_index("ticker")
    assert out.loc["SOFI", "earnings_date"] == "2026-10-27"
    assert bool(out.loc["SOFI", "earnings_inside_hold"]) is True
    assert out.loc["XLF", "earnings_state"] == "NONE_IN_LOOKAHEAD"


def test_fields_travel_to_eod_and_the_book():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    for f in EARNINGS_DISCLOSURE_FIELDS:
        assert f in FINAL_BOOK_FIELDS, f
    row = opportunity_book_row({"ticker": "SOFI", "earnings_date": "2026-10-27", "earnings_state": "SCHEDULED"},
                               "RUN", 1)
    assert row["earnings_date"] == "2026-10-27" and row["earnings_state"] == "SCHEDULED"
    import inspect
    import eod_candidate_engine
    assert "EARNINGS_DISCLOSURE_FIELDS" in inspect.getsource(eod_candidate_engine)


def test_morning_recomputes_sessions_from_the_stored_date():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_morning_gate_authority import _gate, _row
    out = _gate(_row(earnings_state="SCHEDULED", earnings_date="2026-10-27", earnings_report_time="BEFORE_OPEN",
                     planned_hold_sessions=20, contract_expiry="2026-12-18"))
    assert out["earnings_state"] == "SCHEDULED" and out["earnings_date"] == "2026-10-27"
    assert isinstance(out["earnings_sessions_to_event"], int)
    assert out["verdict"] == "GO"                       # disclosure only: it never changes the verdict


# --- Fix C (ACK 5 Oct 2026): a provider's expected date is not a confirmed date. --------------------------------
# External review: MarketData gave DELL 27 Nov (Tastytrade confirmed 24 Nov), MRVL 1 Dec and PL 9 Dec (no next
# date published yet); the pipeline labelled all of them SCHEDULED. MarketData carries no confirmation field.

def test_marketdata_dates_are_marked_unconfirmed():
    from datetime import date as _d, datetime as _dt, timezone as _tz
    from canonical_data.marketdata_earnings import parse_marketdata_earnings
    stamp = _dt(2026, 11, 27, tzinfo=_tz.utc).timestamp()
    out = parse_marketdata_earnings({"s": "ok", "reportDate": [stamp], "fiscalYear": [2027], "fiscalQuarter": [3]},
                                    as_of=_d(2026, 10, 5))
    assert out["state"] == "SCHEDULED" and out["date_confirmation"] == "PROVIDER_DATE_UNCONFIRMED"


def test_disclosure_states_the_date_is_unconfirmed():
    from earnings_calendar_enricher import EARNINGS_DISCLOSURE_FIELDS, earnings_disclosure
    out = earnings_disclosure({"state": "SCHEDULED", "date": "2026-11-27", "report_time": "UNKNOWN",
                               "date_confirmation": "PROVIDER_DATE_UNCONFIRMED"},
                              as_of="2026-10-05", hold_sessions=21, expiry="2026-12-18")
    assert "earnings_date_confirmation" in EARNINGS_DISCLOSURE_FIELDS
    assert out["earnings_date_confirmation"] == "PROVIDER_DATE_UNCONFIRMED"
    assert "not confirmed" in out["earnings_disclosure"]
