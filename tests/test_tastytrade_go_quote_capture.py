"""GO paper-mark capture preserves time, identity and advisory authority."""

from bridge.tastytrade_go_quote_capture import build_go_quote_report


class FakeBroker:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def quote(self, symbols, instrument_type):
        self.calls.append((symbols, instrument_type))
        return self.response


def row(symbol="QBTS261120C00018000"):
    return {"ticker": "QBTS", "morning_gate_verdict": "GO",
            "morning_selected_contract_symbol": symbol,
            "morning_contract_ask": "2.00",
            "quote_provider_timestamp_utc": "2026-09-21T13:36:00Z",
            "contract_multiplier": "100"}


def quote(symbol="QBTS  261120C00018000", timestamp="2026-09-21T19:59:00Z"):
    return {"symbol": symbol, "instrument-type": "Equity Option",
            "bid": "3.00", "ask": "3.10", "bid-size": "5", "ask-size": "6",
            "updated-at": timestamp}


def test_exact_close_window_yields_day_zero_paper_mark_not_realised_trade():
    broker = FakeBroker({"items": [quote()]})
    report = build_go_quote_report(
        [row()], broker, run_id="20260920_203115",
        fetched_at_utc="2026-09-21T20:05:00Z",
        close_window_start_utc="2026-09-21T19:45:00Z",
        close_window_end_utc="2026-09-21T20:00:00Z",
    )
    assert broker.calls == [(["QBTS261120C00018000"], "Equity Option")]
    item = report["observations"][0]
    assert item["exact_occ_symbol"] == "QBTS261120C00018000"
    assert item["broker_provider_updated_at_utc"] == "2026-09-21T19:59:00Z"
    assert item["mark_state"] == "CLOSE_WINDOW_PAPER_MARK"
    assert item["day_zero_paper_return_pct"] == "50.0"
    assert item["realised_trade_return_pct"] is None
    assert item["authority"] == "ADVISORY_ONLY"


def test_stale_quote_cannot_become_today_outcome():
    broker = FakeBroker({"items": [quote(timestamp="2026-09-18T19:59:00Z")]})
    item = build_go_quote_report(
        [row()], broker, run_id="run", fetched_at_utc="2026-09-21T20:05:00Z",
        close_window_start_utc="2026-09-21T19:45:00Z",
        close_window_end_utc="2026-09-21T20:00:00Z",
    )["observations"][0]
    assert item["mark_state"] == "NO_CLOSE_WINDOW_MARK"
    assert item["day_zero_paper_return_pct"] is None


def test_missing_exact_contract_stays_missing_not_a_loss():
    broker = FakeBroker({"items": [quote(symbol="OTHER 261120C00018000")]})
    item = build_go_quote_report(
        [row()], broker, run_id="run", fetched_at_utc="2026-09-21T20:05:00Z",
        close_window_start_utc="2026-09-21T19:45:00Z",
        close_window_end_utc="2026-09-21T20:00:00Z",
    )["observations"][0]
    assert item["broker_identity_state"] == "NOT_RETURNED"
    assert item["mark_state"] == "NO_CLOSE_WINDOW_MARK"
    assert item["day_zero_paper_return_pct"] is None


def test_only_go_rows_and_no_silent_duplicate_identity():
    broker = FakeBroker({"items": [quote()]})
    flag = dict(row(), morning_gate_verdict="FLAG")
    report = build_go_quote_report([row(), flag], broker, run_id="run",
        fetched_at_utc="2026-09-21T20:05:00Z")
    assert report["requested_contract_count"] == 1
    assert report["observations"][0]["mark_state"] == "SNAPSHOT_ONLY"
    assert report["observations"][0]["day_zero_paper_return_pct"] is None


def test_large_go_cohort_batches_without_inventing_missing_outcomes():
    broker = FakeBroker({"items": []})
    rows = [dict(row(symbol=f"Q{i:03d}261120C00018000"), ticker=f"Q{i:03d}")
            for i in range(205)]
    report = build_go_quote_report(rows, broker, run_id="run",
        fetched_at_utc="2026-09-21T20:05:00Z",
        close_window_start_utc="2026-09-21T19:45:00Z",
        close_window_end_utc="2026-09-21T20:00:00Z")
    assert [len(symbols) for symbols, _ in broker.calls] == [100, 100, 5]
    assert report["requested_contract_count"] == 205
    assert report["close_window_paper_mark_count"] == 0
    assert all(item["day_zero_paper_return_pct"] is None for item in report["observations"])
