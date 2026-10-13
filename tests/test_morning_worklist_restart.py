"""Morning restart after a ticker-identity fix (live run 20261012_212523, 13 Oct 2026).

Business rule: a same-run Morning restart may ADD a ticker the earlier attempt wrongly left out (NAN was read as a
missing value and dropped from the published quote worklist), but may never remove or replace an authorised ticker.
The Morning gate's quote / NBBO worklist therefore uses the publisher's one-way expansion, as the Morning
market-structure worklist already does.
"""
import inspect
from datetime import date
from pathlib import Path

import pytest

import morning_gate as gate
from canonical_data import CanonicalRegistry, DatasetType, publish_observation_worklist
from tests.test_msi_stage_worklist import _active_options


def test_the_morning_gate_worklist_call_allows_one_way_expansion():
    source = inspect.getsource(gate.run_morning_gate)
    call = source.split("publication = publish_observation_worklist(", 1)[1].split("\n        )\n", 1)[0]
    assert 'stage="MORNING_GATE"' in call
    assert "allow_monotonic_expansion=True" in call


def test_restart_adds_the_missing_ticker_but_never_drops_one(tmp_path: Path):
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    registry.register_run("R1", "MORNING", date(2026, 10, 13))
    for t in ("AAA", "NAN"):
        _active_options(registry, "R1", t)
    kinds = (DatasetType.EXACT_OPTION_QUOTE, DatasetType.UNDERLYING_NBBO)
    publish_observation_worklist(registry, run_id="R1", stage="MORNING_GATE", tickers=("AAA",),
                                 dataset_types=kinds, allow_monotonic_expansion=True)
    grown = publish_observation_worklist(registry, run_id="R1", stage="MORNING_GATE", tickers=("AAA", "NAN"),
                                         dataset_types=kinds, allow_monotonic_expansion=True)
    assert grown.reconciled
    with pytest.raises(ValueError, match="worklist changed"):
        publish_observation_worklist(registry, run_id="R1", stage="MORNING_GATE", tickers=("NAN",),
                                     dataset_types=kinds, allow_monotonic_expansion=True)
