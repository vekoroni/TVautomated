"""P0-8 service: ingest, scoring idempotency, provenance and report on synthetic books and prices."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3

import pytest

from avshunter.c12_outcome import service
from avshunter.c12_outcome.adapters import storage
from avshunter.c12_outcome.records import provenance_class, resolve_evidence_session
from avshunter.config import ConfigRegistry
from avshunter.config.adapters import load_documents, load_lock
from avshunter.shared.xnys_calendar import is_xnys_session

NOW = datetime(2026, 9, 17, 7, 0, tzinfo=timezone.utc)


def snapshot(**overrides):
    documents = load_documents()
    if overrides:
        for document in documents:
            for entry in document["entries"]:
                if entry["config_key"] in overrides:
                    entry["value"] = overrides[entry["config_key"]]
        return ConfigRegistry.from_documents(documents).resolve(date(2026, 9, 17))
    return ConfigRegistry.from_documents(documents, load_lock()).resolve(date(2026, 9, 17))


def sessions_from(start: date, count: int) -> list[date]:
    out, day = [], start
    while len(out) < count:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


@pytest.fixture()
def world(tmp_path: Path):
    runs = tmp_path / "runs"
    run = runs / "20260902_232526" / "intelligence_lab"
    run.mkdir(parents=True)
    (run.parent / "run_meta.json").write_text(json.dumps({"pipeline_mode": "EOD", "run_status": "COMPLETED"}), encoding="utf-8")
    (run.parent / "macro_snapshot.json").write_text(json.dumps({"report_date": "2026-09-01", "regime_label": "RISK_ON",
                                                               "risk_on_off_switch": "RISK_ON"}), encoding="utf-8")
    book = run / "final_opportunity_book_20260902_232526.csv"
    book.write_text(
        "ticker,direction,thesis_id,underlying_price,invalidation_price,target_price,contract_symbol,contract_bid,contract_ask,tier,lab_verdict\n"
        "UPCO,CALL,UPCO:CALL:2026-09-02:OLM2,100,95,110,UPCO261016C00105000,1.0,1.2,A,MANUAL_REVIEW\n"
        "DNCO,CALL,DNCO:CALL:2026-09-02:OLM2,100,95,110,,,,B,MANUAL_REVIEW\n"
        "NEGT,PUT,NEGT:PUT:2026-09-02:OLM2,9.54,15.61,-8.67,NEGT261016P00010000,1.45,1.75,C,MANUAL_REVIEW\n"
        "BADS,CALL,BADS:CALL:2026-09-02:OLM2,100,105,110,,,,C,MANUAL_REVIEW\n",
        encoding="utf-8",
    )
    recorded = datetime(2026, 9, 2, 23, 30, tzinfo=timezone.utc).timestamp()
    os.utime(book, (recorded, recorded))

    prices_db = tmp_path / "prices.sqlite"
    con = sqlite3.connect(prices_db)
    con.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, open REAL, high REAL, low REAL, close REAL, bar_status TEXT)")
    days = sessions_from(date(2026, 9, 3), 10)
    rows = []
    history = [d for d in sessions_from(date(2026, 7, 1), 60) if d <= date(2026, 9, 2)][-15:]
    for d in history:
        for ticker, price in (("UPCO", 100), ("DNCO", 100), ("NEGT", 9.5), ("BADS", 100)):
            rows.append((ticker, d.isoformat(), price, price * 1.02, price * 0.98, price, "COMPLETE"))
    for i, d in enumerate(days):
        rows.append(("UPCO", d.isoformat(), 100, 111 if i == 2 else 102, 99, 101, "COMPLETE"))
        rows.append(("DNCO", d.isoformat(), 100, 101, 94 if i == 1 else 99, 100, "COMPLETE"))
        rows.append(("NEGT", d.isoformat(), 9.5, 9.8, 9.2, 9.5, "COMPLETE"))
        rows.append(("BADS", d.isoformat(), 100, 101, 99, 100, "COMPLETE"))
    con.executemany("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    chain_db = tmp_path / "chains.sqlite"
    con = sqlite3.connect(chain_db)
    con.execute("CREATE TABLE chain_snapshots (ticker TEXT, quote_date TEXT, option_symbol TEXT, bid REAL, ask REAL, "
                "PRIMARY KEY (ticker, quote_date, option_symbol))")
    con.execute("INSERT INTO chain_snapshots VALUES ('UPCO', ?, 'UPCO261016C00105000', 3.0, 3.2)", (days[2].isoformat(),))
    con.execute("INSERT INTO chain_snapshots VALUES ('UPCO', '2026-09-02', 'UPCO261016C00105000', 1.0, 1.2)")
    con.commit()
    con.close()
    store = storage.connect(tmp_path / "scoring.sqlite")
    return runs, prices_db, store, days


def test_ingest_classifies_and_is_idempotent(world):
    runs, _, store, _ = world
    first = service.ingest(store, runs, NOW)
    again = service.ingest(store, runs, NOW)
    assert (first["new_predictions"], again["new_predictions"], again["new_sightings"]) == (4, 0, 0)
    states = dict(store.execute("SELECT ticker, target_state || '/' || invalidation_state || '/' || provenance_class FROM prediction_records"))
    assert states["NEGT"] == "INVALID_LEGACY/VALID/RECORDED_AT_RUN"
    assert states["BADS"].split("/")[1] == "WRONG_SIDE"


def test_score_as_of_is_point_in_time_and_idempotent(world):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    early = service.score(store, days[1], snapshot(), NOW, prices_db)   # two sessions observed
    assert early["states"] == {"OPEN_CENSORED": 2, "STOP_FIRST": 1, "NOT_SCORABLE": 1}
    repeat = service.score(store, days[1], snapshot(), NOW, prices_db)
    assert repeat["written"] == 0
    later = service.score(store, days[4], snapshot(), NOW, prices_db)
    # DNCO and BADS already terminal; UPCO resolves on session 3; NEGT stays open (target invalid)
    assert later["states"] == {"TARGET_FIRST": 1, "OPEN_CENSORED": 1}
    latest = dict(store.execute("SELECT prediction_id, state FROM latest_underlying_outcomes").fetchall())
    assert sorted(latest.values()) == ["NOT_SCORABLE", "OPEN_CENSORED", "STOP_FIRST", "TARGET_FIRST"]


def test_unsupported_policy_in_configuration_fails_loudly(world):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    with pytest.raises(ValueError, match="does not implement"):
        service.score(store, days[1], snapshot(**{"outcome.stop_fill_policy": "LEVEL_ONLY"}), NOW, prices_db)


def test_base_rates_are_matched_idempotent_and_skip_unscorable(world):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    first = service.score_base_rates(store, days[4], snapshot(), NOW, prices_db)
    assert first["states"] == {"OK": 3, "NOT_SCORABLE": 1}
    assert service.score_base_rates(store, days[4], snapshot(), NOW, prices_db)["written"] == 0
    upco = store.execute("SELECT universe, observed_sessions, stop_atr, target_atr FROM latest_base_rate_outcomes b "
                         "JOIN prediction_records p USING (prediction_id) WHERE p.ticker = 'UPCO'").fetchone()
    assert upco[0] == 4 and upco[1] == 5
    assert upco[2] == pytest.approx(5 / 4) and upco[3] == pytest.approx(10 / 4)   # ATR = 4% of 100
    negt = store.execute("SELECT target_atr FROM latest_base_rate_outcomes b JOIN prediction_records p "
                         "USING (prediction_id) WHERE p.ticker = 'NEGT'").fetchone()
    assert negt[0] is None   # INVALID_LEGACY target: stop / timeout only


def test_conditions_use_the_runs_own_snapshot(world):
    runs, prices_db, store, _ = world
    service.ingest(store, runs, NOW)
    result = service.record_conditions(store, runs, snapshot(), NOW, prices_db)
    assert result["written"] == 4
    row = store.execute("SELECT macro_source, macro_freshness, macro_lag_sessions, regime_label, market_trend_state, "
                        "sector_alignment FROM condition_records LIMIT 1").fetchone()
    assert row == ("RUN_SNAPSHOT", "STALE", 1, "RISK_ON", "INSUFFICIENT_HISTORY", "MISSING_TICKER_SECTOR")
    assert service.record_conditions(store, runs, snapshot(), NOW, prices_db)["written"] == 0


def test_distance_unit_must_match_atr_period(world):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    with pytest.raises(ValueError, match="base_rate_distance_unit"):
        service.score_base_rates(store, days[4], snapshot(**{"outcome.atr_period": 20}), NOW, prices_db)


def test_report_written_with_insufficient_sessions_label(world, tmp_path):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    service.score(store, days[4], snapshot(), NOW, prices_db)
    service.record_conditions(store, runs, snapshot(), NOW, prices_db)
    service.score_base_rates(store, days[4], snapshot(), NOW, prices_db)
    path = service.build_report(store, days[4], snapshot(), tmp_path / "report")
    text = path.read_text(encoding="utf-8")
    assert "INSUFFICIENT_SESSIONS" in text and "headline" in text
    assert "Excess target" in text and "## Conditions vs matched base rate" in text and "regime_label=RISK_ON" in text
    payload = json.loads((tmp_path / "report" / "outcome_report.json").read_text(encoding="utf-8"))
    assert payload["coverage"]["target_state"]["INVALID_LEGACY"] == 1


def test_evidence_session_resolution_order():
    assert resolve_evidence_session("X:CALL:2026-09-02:OLM2", {"session_date": "2026-09-01"}, "20260902_232526").source == "THESIS_ID"
    assert resolve_evidence_session(None, {"session_date": "2026-09-01"}, "20260902_232526").source == "RUN_META"
    derived = resolve_evidence_session(None, {}, "20260804_114554")   # Tue 4 Aug 11:45 UTC = 07:45 ET, before the open
    assert (derived.source, derived.session) == ("DERIVED_FROM_RUN_ID", date(2026, 8, 3))


def test_provenance_after_first_session_close_is_retrospective():
    evidence, first = date(2026, 9, 2), date(2026, 9, 3)
    assert provenance_class(datetime(2026, 9, 3, 19, 0, tzinfo=timezone.utc), evidence, first) == "RECORDED_AT_RUN"
    assert provenance_class(datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc), evidence, first) == "RETROSPECTIVE_UNVERIFIED"


def test_expressions_mark_resolved_contracts_and_wait_for_open_ones(world):
    runs, prices_db, store, days = world
    service.ingest(store, runs, NOW)
    service.score(store, days[4], snapshot(), NOW, prices_db)
    result = service.score_expressions(store, days[4], snapshot(), NOW, prices_db.parent / "chains.sqlite")
    assert result["states"] == {"MARKED": 1, "PENDING": 1}
    row = store.execute("SELECT state, exit_reason, entry_ask, exit_bid, pnl_per_contract, return_on_premium, "
                        "evidence_session_chain_ask, underlying_state FROM expression_outcomes").fetchone()
    assert row[:5] == ("MARKED", "RESOLUTION", 1.2, 3.0, pytest.approx(180.0))
    assert row[5] == pytest.approx(1.5) and row[6] == 1.2 and row[7] == "TARGET_FIRST"
    assert service.score_expressions(store, days[4], snapshot(), NOW, prices_db.parent / "chains.sqlite")["written"] == 0
    path = service.build_report(store, days[4], snapshot(), prices_db.parent / "report")
    assert "## Expressions" in path.read_text(encoding="utf-8")
