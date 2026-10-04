"""Gap 1 follow-up (ACK, 25 Sep 2026) — atomic persistence of a supplemental
broker observation: reopen-after-save parity and never overwriting an
existing file at the same path (historical snapshot or a prior supplemental
read).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contracts.supplemental_broker_observation_writer import (
    SupplementalObservationAlreadyExistsError,
    persist_supplemental_broker_observation_atomically,
    read_persisted_supplemental_broker_observation,
)
from domain.exact_contract_quote_join import SupplementalBrokerObservationRecord

RECORD = SupplementalBrokerObservationRecord(
    exact_contract_quote_join_ref="BULL:20260925_061649:BULL261120C00007500",
    fetched_at_utc="20260925T063000Z",
    provider="TASTYTRADE",
    provider_observed_at_utc="2026-09-25T06:29:55Z",
    bid="0.62", ask="0.65",
    persisted_as="market_observations/exact_option_quote_live_supplement/BULL/20260925_061649/20260925T063000Z.json",
    overwrites_historical_snapshot=False,
)


def test_persist_then_reopen_round_trips_without_any_provider_call(tmp_path):
    target = persist_supplemental_broker_observation_atomically(RECORD, root_dir=tmp_path)
    assert target.exists()
    reopened = read_persisted_supplemental_broker_observation(target)
    assert reopened["exact_contract_quote_join_ref"] == RECORD.exact_contract_quote_join_ref
    assert reopened["bid"] == "0.62"
    assert reopened["overwrites_historical_snapshot"] is False


def test_a_second_write_to_the_same_path_never_overwrites():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        persist_supplemental_broker_observation_atomically(RECORD, root_dir=root)
        different_record = SupplementalBrokerObservationRecord(
            exact_contract_quote_join_ref=RECORD.exact_contract_quote_join_ref,
            fetched_at_utc=RECORD.fetched_at_utc, provider="TASTYTRADE",
            provider_observed_at_utc="2026-09-25T06:29:59Z",
            bid="9.99", ask="9.99",  # deliberately different -- would clobber if allowed
            persisted_as=RECORD.persisted_as, overwrites_historical_snapshot=False,
        )
        with pytest.raises(SupplementalObservationAlreadyExistsError):
            persist_supplemental_broker_observation_atomically(different_record, root_dir=root)
        # The original content must be untouched.
        reopened = read_persisted_supplemental_broker_observation(root / RECORD.persisted_as)
        assert reopened["bid"] == "0.62"


def test_persisting_never_touches_the_historical_exact_option_quote_path(tmp_path):
    historical_dir = tmp_path / "market_observations" / "exact_option_quote" / "2026-09-25" / "BULL"
    historical_dir.mkdir(parents=True)
    historical_file = historical_dir / "e87aff2d2b6a28e790cdd4e5b718f25c88ec9a442401ebf873508984be9335de.json"
    historical_file.write_text('{"symbol": "BULL261120C00007500"}', encoding="utf-8")
    original_bytes = historical_file.read_bytes()

    persist_supplemental_broker_observation_atomically(RECORD, root_dir=tmp_path)

    assert historical_file.read_bytes() == original_bytes


def test_temp_file_is_not_left_behind_on_success(tmp_path):
    persist_supplemental_broker_observation_atomically(RECORD, root_dir=tmp_path)
    leftovers = [p for p in (tmp_path / "market_observations" / "exact_option_quote_live_supplement"
                              / "BULL" / "20260925_061649").iterdir()
                 if p.name.startswith(".tmp_supplemental_")]
    assert leftovers == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
