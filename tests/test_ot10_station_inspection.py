"""Output-trust item 10, part 10.3 (C-2; ACK approved 9-10 Oct 2026): station inspections stop the line on integrity.

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. Today every integrity artefact only
reports; the line runs on with duplicated, invented or unaccounted rows.

Business rules:
- After each station (Discovery, Options, EOD candidates, Lab book, Morning gate) a defect report is written.
- STOP checks are integrity invariants: unique and non-blank tickers, no ticker invented by a later stage, every lost
  ticker accounted for by the drop-off audit, positive prices, sane quotes (bid <= ask, none negative), a directed row's
  side equals its governed direction, target and invalidation on the correct sides, no timestamp in the future. A STOP
  defect raises with the station, check and rows. Each was zero on the healthy 8 Oct run before being made STOP.
- REPORT checks (fill rates) never stop the line. Enforcement is governed config (a stated switch, default on).
- Integrity only: a row-level trade judgement is never a station defect.
"""
from __future__ import annotations

import pandas as pd
import pytest

from domain.station_inspection import StationDefect, enforce, inspect_station

CLEAN = pd.DataFrame({"ticker": ["AAA", "BBB", "NAN"], "direction": ["CALL", "PUT", "UNRESOLVED"],
                      "governed_direction": ["CALL", "PUT", "UNRESOLVED"], "signal_price": ["10", "20", "5"],
                      "contract_bid": ["1.0", "2.0", ""], "contract_ask": ["1.1", "2.2", ""],
                      "target_price": ["12", "18", ""], "invalidation_price": ["9", "21", ""],
                      "selected_quote_timestamp_utc": ["2026-10-08T20:00:00Z"] * 3})
NOW = "2026-10-08T22:30:00Z"


def _inspect(frame, **kw):
    base = dict(run_id="R1", previous_tickers=None, accounted_tickers=None, now_utc=NOW)
    base.update(kw)
    return inspect_station("eod", frame, **base)


def test_a_clean_station_passes_and_nan_is_a_ticker():
    report = _inspect(CLEAN)
    assert report["stop_defects"] == [] and report["rows"] == 3
    enforce(report)                                                      # does not raise


@pytest.mark.parametrize("mutate,check", [
    (lambda d: pd.concat([d, d.iloc[[0]]]), "unique_tickers"),
    (lambda d: d.assign(ticker=["AAA", "", "NAN"]), "nonblank_tickers"),
    (lambda d: d.assign(signal_price=["10", "-1", "5"]), "positive_prices"),
    (lambda d: d.assign(contract_bid=["1.3", "2.0", ""]), "sane_quotes"),
    (lambda d: d.assign(governed_direction=["PUT", "PUT", "UNRESOLVED"]), "side_matches_governed_direction"),
    (lambda d: d.assign(target_price=["8", "18", ""]), "levels_on_correct_sides"),
    (lambda d: d.assign(selected_quote_timestamp_utc=["2026-10-09T20:00:00Z"] * 3), "no_future_timestamps"),
])
def test_each_integrity_defect_stops_the_line(mutate, check):
    report = _inspect(mutate(CLEAN.copy()))
    assert check in {d["check"] for d in report["stop_defects"]}
    with pytest.raises(StationDefect) as err:
        enforce(report)
    assert "eod" in str(err.value) and check in str(err.value)


def test_invented_and_unaccounted_tickers_stop_the_line():
    invented = _inspect(CLEAN, previous_tickers={"AAA", "BBB"})
    assert {"NAN"} == set(next(d for d in invented["stop_defects"] if d["check"] == "no_invented_tickers")["tickers"])
    lost = _inspect(CLEAN, previous_tickers={"AAA", "BBB", "NAN", "CCC", "DDD"}, accounted_tickers={"CCC"})
    defect = next(d for d in lost["stop_defects"] if d["check"] == "losses_accounted")
    assert defect["tickers"] == ["DDD"]
    accounted = _inspect(CLEAN, previous_tickers={"AAA", "BBB", "NAN", "CCC"}, accounted_tickers={"CCC"})
    assert accounted["stop_defects"] == []


def test_report_checks_and_disabled_enforcement_never_stop():
    report = _inspect(CLEAN.assign(contract_bid=["", "", ""]))
    assert report["report"]["fill_rates"]["contract_bid"] == 0.0 and report["stop_defects"] == []
    broken = _inspect(pd.concat([CLEAN, CLEAN.iloc[[0]]]))
    enforce(broken, policy={"enforce": False})                          # stated switch: report only


def test_every_station_is_inspected_in_the_run():
    import inspect
    import intelligent_orchestrator
    src = inspect.getsource(intelligent_orchestrator)
    for station in ("discovery", "options", "eod", "book"):
        assert f'_run_station_inspection(canonical_run_id, "{station}"' in src or \
               f'_run_station_inspection(run_id, "{station}"' in src, station
    import morning_gate
    assert '"morning"' in inspect.getsource(morning_gate.run_morning_gate) and "inspect_station(" in \
        inspect.getsource(morning_gate)


def test_the_morning_hook_runs_with_morning_gate_names():
    # the hook's own code, executed with morning_gate's module globals (the first version used an undefined pd)
    import inspect
    import morning_gate
    src = inspect.getsource(morning_gate.run_morning_gate)
    start = src.index("    import pandas as _pd_station")
    end = src.index("    enforce(_station)") + len("    enforce(_station)")
    block = chr(10).join(line[4:] for line in src[start:end].splitlines())
    scope = dict(vars(morning_gate), results=[{"ticker": "AAA", "direction": "CALL", "signal_price": "10"}],
                 candidates=[{"ticker": "AAA"}], run_id="R_TEST", log=morning_gate.log)
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        scope["ROOT"] = pathlib.Path(tmp)
        exec(block, scope)
    assert scope["_station"]["stop_defects"] == []
