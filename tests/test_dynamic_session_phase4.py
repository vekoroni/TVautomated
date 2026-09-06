from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from canonical_data import (
    CanonicalRegistry,
    DatasetType,
    LifecycleManager,
    LifecycleState,
    session_bounds,
)
from canonical_data.run_plan import RequestedAction, resolve_run_plan
from contracts.market_profile_evidence import MarketProfileEvidence
from market_structure.completed_profile import build_profile_evidence
from market_structure.profile import build_market_profile
from orchestrator.dynamic_thesis import (
    BUILD_THESIS_STAGES,
    ThesisStageResult,
    build_thesis,
    record_completed_thesis,
)
from scripts.build_completed_market_profiles import build_completed_profiles
from vanguard.layer1_auction.auction_synthesizer import AuctionStateSynthesizer
from vanguard.schemas.input_schema import (
    CalendarData,
    MacroData,
    MicrostructureData,
    OptionsData,
    TechnicalData,
    VanguardInput,
)


SESSION = date(2026, 8, 31)


def intraday_frame(interval: int = 5, count: int | None = None) -> pd.DataFrame:
    open_utc, close_utc = session_bounds(SESSION)
    timestamps = pd.date_range(open_utc, close_utc, freq=f"{interval}min")
    if count is not None:
        timestamps = timestamps[:count]
    index = pd.Series(range(len(timestamps)), dtype=float)
    center = 100.0 + (index % 12) * 0.05
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "open": center,
            "high": center + 0.20,
            "low": center - 0.20,
            "close": center + 0.05,
            "volume": 1_000.0 + index * 10,
            "interval_minutes": interval,
            "session_segment": "REGULAR",
            "provider_observed_at_utc": timestamps,
            "observed_at": timestamps,
            "provider_http_status": 203,
        }
    )


def vanguard_input(evidence=None, *, required=True) -> VanguardInput:
    return VanguardInput(
        ticker="AAPL",
        analysis_timestamp=datetime(2026, 8, 31, 21, tzinfo=timezone.utc),
        current_price=100.25,
        calendar=CalendarData(),
        options=OptionsData(),
        technical=TechnicalData(ohlcv=pd.DataFrame()),
        microstructure=MicrostructureData(),
        macro=MacroData(),
        market_profile_evidence=evidence,
        market_profile_contract_required=required,
    )


def valid_evidence() -> MarketProfileEvidence:
    open_utc, close_utc = session_bounds(SESSION)
    return build_profile_evidence(
        ticker="AAPL",
        session_date=SESSION,
        evidence_state="COMPLETED_SESSION",
        bars=intraday_frame(),
        exchange_tick=0.01,
        atr14=2.0,
        regular_open_utc=open_utc,
        input_dataset_ids=("bars-1",),
        input_hashes=("hash-1",),
        completeness_status="COMPLETE",
        calculated_at_utc=close_utc,
    )


def test_profile_cadence_is_truthful_and_deterministic() -> None:
    open_utc, _ = session_bounds(SESSION)
    fifteen = build_market_profile(
        intraday_frame(15), exchange_tick=0.01, atr14=2.0,
        regular_open_utc=open_utc,
    )
    five_a = build_market_profile(
        intraday_frame(5), exchange_tick=0.01, atr14=2.0,
        regular_open_utc=open_utc,
    )
    five_b = build_market_profile(
        intraday_frame(5).sample(frac=1, random_state=7),
        exchange_tick=0.01, atr14=2.0, regular_open_utc=open_utc,
    )
    assert fifteen.data_quality == "COARSE_15_MINUTE"
    assert five_a.data_quality == "FIVE_MINUTE_ESTIMATED"
    assert (five_a.poc, five_a.value_area_low, five_a.value_area_high) == (
        five_b.poc, five_b.value_area_low, five_b.value_area_high
    )


def test_governed_short_frame_is_null_not_zero() -> None:
    open_utc, _ = session_bounds(SESSION)
    profile = build_market_profile(
        intraday_frame(5, 12), exchange_tick=0.01, atr14=2.0,
        regular_open_utc=open_utc,
    )
    assert profile.data_quality == "INSUFFICIENT_DATA"
    assert profile.poc is None
    assert profile.value_area_low is None
    assert profile.value_area_high is None


def test_profile_evidence_is_advisory_and_restart_deterministic() -> None:
    first = valid_evidence()
    second = valid_evidence()
    assert first.usable
    assert first == second
    assert first.can_grant_capital is False
    assert first.can_reverse_direction is False
    assert first.authority == "ADVISORY_ONLY"


def test_profile_authority_is_pinned_against_hostile_payload() -> None:
    payload = valid_evidence().to_dict()
    payload.update(
        authority="CAPITAL",
        can_grant_capital=True,
        can_reverse_direction=True,
    )
    rebuilt = MarketProfileEvidence.from_mapping(payload)
    assert rebuilt.authority == "ADVISORY_ONLY"
    assert rebuilt.can_grant_capital is False
    assert rebuilt.can_reverse_direction is False


def test_incomplete_evidence_is_not_usable() -> None:
    payload = valid_evidence().to_dict()
    payload["completeness_status"] = "PARTIAL_GAPS"
    assert not MarketProfileEvidence.from_mapping(payload).usable


def test_vanguard_fails_safe_without_governed_profile() -> None:
    verdict = AuctionStateSynthesizer().synthesize(vanguard_input(None))
    assert verdict.ready_to_trade is False
    assert verdict.auction_state == "NOT_EVALUATED"
    assert verdict.profile.poc is None
    assert verdict.profile.value_area_low is None
    assert verdict.profile.value_area_high is None


def test_vanguard_consumes_governed_profile_without_granting_readiness() -> None:
    evidence = valid_evidence()
    verdict = AuctionStateSynthesizer().synthesize(
        vanguard_input(evidence.to_dict())
    )
    assert verdict.auction_state == "PROFILE_CONTEXT_ONLY"
    assert verdict.ready_to_trade is False
    assert verdict.profile.poc == evidence.poc
    assert verdict.profile.value_area_low == evidence.value_area_low
    assert verdict.profile.value_area_high == evidence.value_area_high
    assert verdict.acceptance.classification == "PROFILE_CONTEXT_ONLY"


def _create_profile_run(root: Path, tickers=("AAPL",)) -> str:
    run_id = "PHASE4"
    registry = CanonicalRegistry(root / "data" / "canonical" / "control_plane.sqlite")
    registry.initialise()
    registry.register_run(run_id, "BUILD_THESIS", SESSION)
    lifecycle = LifecycleManager(registry)
    packages = root / "data" / "output" / "runs" / run_id / "packages"
    packages.mkdir(parents=True)
    indexed = []
    for ticker in tickers:
        event = lifecycle.register(
            run_id, ticker, allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            run_id, ticker, LifecycleState.ACTIVE_CORE, stage="PACKAGES",
            reason_code="TEST", expected_version=event.version,
            allowed_capabilities=(DatasetType.DAILY_OHLCV,),
        )
        path = packages / f"{ticker}.package.json"
        daily = [
            {"high": 101 + index / 10, "low": 99 + index / 10, "close": 100 + index / 10}
            for index in range(20)
        ]
        path.write_text(json.dumps({"ticker": ticker, "daily_df": daily}), encoding="utf-8")
        indexed.append({"ticker": ticker, "status": "BUILT", "package_path": str(path)})
    (packages / "index.json").write_text(json.dumps({"packages": indexed}), encoding="utf-8")
    return run_id


def test_completed_profile_stage_persists_and_reuses_cache() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        run_id = _create_profile_run(root)
        calls: list[str] = []

        def factory(_session, _interval):
            def fetch(ticker, start, end):
                calls.append(ticker)
                return intraday_frame(5)
            return fetch

        first = build_completed_profiles(
            run_id=run_id, session_date=SESSION, base_dir=root,
            fetch_factory=factory,
        )
        second = build_completed_profiles(
            run_id=run_id, session_date=SESSION, base_dir=root,
            fetch_factory=factory,
        )
        package = json.loads(
            (root / "data" / "output" / "runs" / run_id / "packages" / "AAPL.package.json").read_text()
        )
        assert first["completed"] == 1 and first["systemic_failure"] is False
        assert second["physical_provider_requests"] == 0
        assert calls == ["AAPL"]
        assert package["market_profile_evidence"]["usable"] is True
        assert package["market_profile_contract_required"] is True


def test_completed_profile_stage_isolates_ticker_and_flags_systemic_failure() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        run_id = _create_profile_run(root, ("AAPL", "FAIL"))

        def factory(_session, _interval):
            def fetch(ticker, start, end):
                if ticker == "FAIL":
                    raise RuntimeError("provider unavailable")
                return intraday_frame(5)
            return fetch

        summary = build_completed_profiles(
            run_id=run_id, session_date=SESSION, base_dir=root,
            fetch_factory=factory, max_failure_ratio=0.25,
        )
        assert summary["completed"] == 1
        assert summary["deferred"] == 0
        assert summary["exception_count"] == 1
        assert summary["reconciled"] is True
        assert summary["systemic_failure"] is True


def test_completed_profile_stage_fails_closed_on_systemic_partial_coverage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        run_id = _create_profile_run(root, ("AAPL", "PARTIAL"))

        def factory(_session, _interval):
            def fetch(ticker, start, end):
                return intraday_frame(5) if ticker == "AAPL" else intraday_frame(5, 20)
            return fetch

        summary = build_completed_profiles(
            run_id=run_id, session_date=SESSION, base_dir=root,
            fetch_factory=factory, max_failure_ratio=1.0, min_usable_ratio=0.75,
        )
        assert summary["provider_systemic_failure"] is False
        assert summary["usable_ratio"] == 0.5
        assert summary["coverage_failure"] is True
        assert summary["systemic_failure"] is True


def test_build_thesis_orders_stages_and_restart_reuses_receipt() -> None:
    plan = resolve_run_plan(
        requested_action=RequestedAction.BUILD_THESIS,
        as_of_utc=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 1, 20, tzinfo=timezone.utc),
        authorised_tickers=("AAPL", "MSFT"),
        pipeline_run_id="PHASE4-PLAN",
    )
    calls: list[str] = []

    def handler(stage):
        def execute(_plan, prior):
            assert tuple(prior) == tuple(BUILD_THESIS_STAGES[: len(prior)])
            calls.append(stage)
            return ThesisStageResult(stage, "COMPLETED", 2, 2)
        return execute

    handlers = {stage: handler(stage) for stage in BUILD_THESIS_STAGES}
    with tempfile.TemporaryDirectory() as directory:
        first = build_thesis(plan, handlers=handlers, receipt_root=Path(directory))
        second = build_thesis(plan, handlers=handlers, receipt_root=Path(directory))
    assert first == second
    assert calls == list(BUILD_THESIS_STAGES)
    assert first.authority_ceiling == "EOD_PREPARED"


def test_record_completed_thesis_is_idempotent_and_plan_bound() -> None:
    plan = resolve_run_plan(
        requested_action=RequestedAction.BUILD_THESIS,
        as_of_utc=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 1, 20, tzinfo=timezone.utc),
        authorised_tickers=("AAPL",),
        pipeline_run_id="PHASE4-RECORDED",
    )
    results = {
        stage: ThesisStageResult(stage, "COMPLETED", 1, 1)
        for stage in BUILD_THESIS_STAGES
    }
    with tempfile.TemporaryDirectory() as directory:
        first = record_completed_thesis(
            plan, stage_results=results, receipt_root=Path(directory)
        )
        second = record_completed_thesis(
            plan, stage_results=results, receipt_root=Path(directory)
        )
    assert first == second
    assert first.pipeline_run_id == "PHASE4-RECORDED"


def test_build_thesis_rejects_population_gain_and_loss() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        ThesisStageResult("DISCOVERY", "COMPLETED", 1, 2)
    with pytest.raises(ValueError, match="does not reconcile"):
        ThesisStageResult("DISCOVERY", "COMPLETED", 10, 3)
    reconciled = ThesisStageResult(
        "DISCOVERY", "COMPLETED", 10, 3,
        excluded_count=2, deferred_count=4, exception_count=1,
    )
    assert reconciled.input_count == 10


def test_build_thesis_rejects_non_build_plan() -> None:
    plan = resolve_run_plan(
        requested_action=RequestedAction.VALIDATE,
        as_of_utc=datetime(2026, 9, 1, 13, tzinfo=timezone.utc),
        authorised_tickers=("AAPL",),
        existing_thesis_id="thesis-1",
        existing_thesis_session=SESSION,
    )
    with pytest.raises(ValueError, match="BUILD_THESIS"):
        build_thesis(plan, handlers={}, receipt_root=Path("unused"))
