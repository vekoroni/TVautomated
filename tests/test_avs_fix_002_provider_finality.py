from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from domain.provider_finality import (
    ProviderFinalityState,
    ProviderRequestMode,
    assess_provider_session_finality,
    assess_run_provider_completeness,
    timestamp_distribution,
)
from canonical_data.contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetType,
)
from canonical_data.historical_prices import HistoricalPriceDatabase
from canonical_data.feature_flags import CanonicalFeatureFlags
from canonical_data.market_observation_resolver import (
    CanonicalMarketObservationResolver,
    ObservationResult,
)
from canonical_data.provider_finality import (
    GOVERNED_CONSTANTS_PATH,
    assess_completed_option_worklist,
    load_provider_finality_policy,
)
from canonical_data.registry import CanonicalRegistry


SESSION = date(2026, 9, 11)
CLOSE = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)


def distribution(*, observed: int = 8, expected: int = 10):
    return timestamp_distribution(
        [CLOSE - timedelta(minutes=index) for index in range(observed)],
        expected_count=expected,
        late_watermark_utc=CLOSE - timedelta(minutes=15),
    )


def assess(**overrides):
    values = {
        "requested_session": SESSION,
        "last_completed_session": SESSION,
        "request_mode": ProviderRequestMode.HISTORICAL_COMPLETED,
        "assessed_at_utc": CLOSE + timedelta(minutes=20),
        "session_close_utc": CLOSE,
        "provider_settlement_delay": timedelta(minutes=15),
        "underlying_close_dataset_id": "close-dataset",
        "session_date_coverage": 0.80,
        "timestamps": distribution(),
    }
    values.update(overrides)
    return assess_provider_session_finality(**values)


def test_complete_requires_every_governed_basis() -> None:
    result = assess()
    assert result.state is ProviderFinalityState.COMPLETE
    assert result.normal_completed_session_eligible is True
    assert len(result.completion_basis) == 8
    assert result.reasons == ()


def test_alg15_thresholds_are_loaded_from_governed_constants() -> None:
    policy = load_provider_finality_policy()
    assert GOVERNED_CONSTANTS_PATH.is_file()
    assert policy.minimum_normal_chain_fraction == pytest.approx(0.95)
    assert policy.minimum_official_close_fraction == pytest.approx(0.99)
    assert policy.minimum_session_coverage == pytest.approx(0.80)
    assert policy.minimum_timestamp_coverage == pytest.approx(0.80)
    assert policy.minimum_late_watermark_coverage == pytest.approx(0.10)
    assert len(policy.governed_constants_sha256) == 64


@pytest.mark.parametrize(
    ("overrides", "expected_state", "expected_reason"),
    [
        (
            {"requested_session": date(2026, 9, 10)},
            ProviderFinalityState.DATE_MISMATCH,
            "REQUESTED_SESSION_IS_NOT_LAST_COMPLETED_XNYS_SESSION",
        ),
        (
            {"request_mode": ProviderRequestMode.LIVE_LATEST},
            ProviderFinalityState.EVIDENCE_INSUFFICIENT,
            "REQUEST_MODE_IS_NOT_HISTORICAL_COMPLETED",
        ),
        (
            {"assessed_at_utc": CLOSE + timedelta(minutes=14)},
            ProviderFinalityState.NOT_SETTLED,
            "PROVIDER_SETTLEMENT_DELAY_NOT_ELAPSED",
        ),
        (
            {"underlying_close_dataset_id": None},
            ProviderFinalityState.EVIDENCE_INSUFFICIENT,
            "OFFICIAL_UNDERLYING_CLOSE_MISSING",
        ),
        (
            {"session_date_coverage": 0.79},
            ProviderFinalityState.PARTIAL,
            "SESSION_DATE_COVERAGE_BELOW_THRESHOLD",
        ),
        (
            {"timestamps": distribution(observed=7)},
            ProviderFinalityState.PARTIAL,
            "PROVIDER_TIMESTAMP_COVERAGE_BELOW_THRESHOLD",
        ),
    ],
)
def test_failure_precedence_is_named(overrides, expected_state, expected_reason) -> None:
    result = assess(**overrides)
    assert result.state is expected_state
    assert expected_reason in result.reasons
    assert result.normal_completed_session_eligible is False


def test_one_late_quote_does_not_prove_whole_chain_complete() -> None:
    result = assess(timestamps=distribution(observed=1, expected=100))
    assert result.timestamp_distribution.maximum_utc == CLOSE
    assert result.state is ProviderFinalityState.PARTIAL
    assert result.normal_completed_session_eligible is False


def test_earlier_quotes_without_late_watermark_coverage_are_partial() -> None:
    timestamps = timestamp_distribution(
        [CLOSE - timedelta(minutes=90 + index) for index in range(8)],
        expected_count=10,
        late_watermark_utc=CLOSE - timedelta(minutes=15),
    )
    result = assess(timestamps=timestamps)
    assert result.timestamp_distribution.late_watermark_coverage == 0.0
    assert result.state is ProviderFinalityState.PARTIAL
    assert "LATE_SESSION_WATERMARK_COVERAGE_BELOW_THRESHOLD" in result.reasons


def test_run_thresholds_keep_residual_ticker_exception_visible() -> None:
    completed = [assess(ticker=f"T{index:03d}") for index in range(95)]
    partial = [
        assess(
            ticker=f"X{index:03d}",
            timestamps=distribution(observed=1, expected=100),
        )
        for index in range(5)
    ]
    run = assess_run_provider_completeness(
        completed + partial,
        chains_expected=100,
        underlying_tickers_expected=100,
        checked_at_utc=CLOSE + timedelta(minutes=20),
    )
    assert run.normal_completed_session_eligible is True
    assert run.normal_chain_fraction == pytest.approx(0.95)
    assert len(run.ticker_exceptions) == 5


def test_run_below_chain_threshold_is_not_normal() -> None:
    values = [assess(ticker=f"T{index}") for index in range(94)] + [
        assess(
            ticker=f"X{index}",
            timestamps=distribution(observed=1, expected=100),
        )
        for index in range(6)
    ]
    run = assess_run_provider_completeness(
        values,
        chains_expected=100,
        underlying_tickers_expected=100,
        checked_at_utc=CLOSE + timedelta(minutes=20),
    )
    assert run.normal_completed_session_eligible is False


def _registered_chain(
    root: Path,
    registry: CanonicalRegistry,
    *,
    ticker: str,
    timestamps: list[datetime],
) -> str:
    payload = [
        {"symbol": f"{ticker}{index}", "quote_timestamp_utc": value.isoformat()}
        for index, value in enumerate(timestamps)
    ]
    path = root / f"{ticker}.json"
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    record = DatasetRecord(
        dataset_id=f"chain-{ticker}",
        dataset_type=DatasetType.OPTION_CHAIN,
        instrument_id=ticker,
        session_date=SESSION,
        scope=DataScope(start_date=SESSION, end_date=SESSION),
        provider="MARKETDATA",
        content_hash=digest,
        completeness_status=CompletenessStatus.COMPLETE,
        storage_uri=str(path),
        observed_at=CLOSE + timedelta(minutes=20),
        as_of=max(timestamps),
        adjustment_convention="RAW_OPTION_CONTRACT",
        schema_version="option_chain_v2",
    )
    registry.register_dataset(record)
    return record.dataset_id


def test_canonical_adapter_joins_close_and_uses_xnys_dst(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    history = HistoricalPriceDatabase(tmp_path / "history.sqlite")
    history.initialise()
    history.ingest(
        "AAPL",
        [{"date": SESSION, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}],
        provider="TEST",
        source_kind="RECORDED_FIXTURE",
    )
    dataset_id = _registered_chain(
        tmp_path,
        registry,
        ticker="AAPL",
        timestamps=[CLOSE - timedelta(minutes=index) for index in range(10)],
    )
    result = assess_completed_option_worklist(
        registry=registry,
        expected_tickers=("AAPL",),
        chain_dataset_ids={"AAPL": dataset_id},
        requested_session=SESSION,
        last_completed_session=SESSION,
        assessed_at_utc=CLOSE + timedelta(minutes=20),
        historical_price_database_path=history.database_path,
    )
    assessment = result.assessments[0]
    assert assessment.state is ProviderFinalityState.COMPLETE
    assert assessment.session_close_utc == CLOSE
    assert assessment.underlying_close_dataset_id.startswith("historical_close_v1:")
    assert result.aggregate.normal_completed_session_eligible is True
    assert len(result.aggregate.governed_constants_sha256) == 64


def test_missing_chain_is_named_exception_not_run_abort(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    history = HistoricalPriceDatabase(tmp_path / "history.sqlite")
    history.initialise()
    result = assess_completed_option_worklist(
        registry=registry,
        expected_tickers=("MISSING",),
        chain_dataset_ids={},
        requested_session=SESSION,
        last_completed_session=SESSION,
        assessed_at_utc=CLOSE + timedelta(minutes=20),
        historical_price_database_path=history.database_path,
    )
    assert result.aggregate.normal_completed_session_eligible is False
    assert result.aggregate.ticker_exceptions[0]["ticker"] == "MISSING"
    assert result.assessments[0].state is ProviderFinalityState.EVIDENCE_INSUFFICIENT


def test_november_dst_close_is_resolved_from_exchange_calendar(tmp_path: Path) -> None:
    from canonical_data.provider_finality import assess_canonical_option_chain

    session = date(2026, 11, 2)
    close = datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)
    assessment = assess_canonical_option_chain(
        ticker="AAPL",
        requested_session=session,
        last_completed_session=session,
        request_mode=ProviderRequestMode.HISTORICAL_COMPLETED,
        assessed_at_utc=close + timedelta(minutes=20),
        chain_record=None,
        historical_price_database_path=tmp_path / "missing.sqlite",
    )
    assert assessment.session_close_utc == close


def test_v2_resolver_refreshes_partial_last_session_cache(
    tmp_path: Path, monkeypatch
) -> None:
    import canonical_data.market_observation_resolver as resolver_module

    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    history = HistoricalPriceDatabase(tmp_path / "historical_prices.sqlite")
    history.initialise()
    history.ingest(
        "AAPL",
        [{"date": SESSION, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}],
        provider="TEST", source_kind="RECORDED_FIXTURE",
    )
    old_id = _registered_chain(
        tmp_path, registry, ticker="AAPL",
        timestamps=[CLOSE - timedelta(hours=2, minutes=index) for index in range(10)],
    )
    resolver = CanonicalMarketObservationResolver(
        registry_path=registry.database_path,
        payload_root=tmp_path / "payloads",
        run_id="R1",
        flags=CanonicalFeatureFlags(
            enabled=True, write_through=True, stage_gating_enforced=True,
            offline_replay=False, ohlcv_mode="ACTIVE",
        ),
    )
    monkeypatch.setattr(
        resolver_module,
        "session_snapshot",
        lambda *_args, **_kwargs: type("Snapshot", (), {"last_completed_session": SESSION})(),
    )
    monkeypatch.setattr(
        resolver,
        "_resolve",
        lambda *_args, **_kwargs: ObservationResult(
            json.loads((tmp_path / "AAPL.json").read_text()),
            "EXACT_HIT", old_id, "MARKETDATA",
        ),
    )
    monkeypatch.setattr(resolver.ledger, "start", lambda *_args, **_kwargs: "ledger-1")
    monkeypatch.setattr(resolver.ledger, "finish", lambda *_args, **_kwargs: None)
    calls: list[str] = []
    symbol = "AAPL261016C00100000"
    payload = {
        "s": "ok",
        "optionSymbol": [symbol] * 10,
        "updated": [(CLOSE - timedelta(minutes=index)).isoformat() for index in range(10)],
        "bid": [1.0] * 10,
        "ask": [1.2] * 10,
        "bidSize": [1] * 10,
        "askSize": [1] * 10,
        "contractMultiplier": [100] * 10,
    }

    result = resolver.option_chain(
        ticker="AAPL", session_date=SESSION, dte_max=90, min_open_interest=0,
        fetch=lambda ticker: calls.append(ticker) or payload,
    )

    assert calls == ["AAPL"]
    assert result.resolution == "PROVIDER_FETCH", json.dumps(
        result.provider_finality, indent=2, default=str
    )
    assert result.provider_finality["finality_state"] == "PROVIDER_SESSION_COMPLETE"


def test_timestamp_inputs_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        timestamp_distribution(
            [datetime(2026, 9, 11, 20, 0)],
            expected_count=1,
            late_watermark_utc=CLOSE,
        )
