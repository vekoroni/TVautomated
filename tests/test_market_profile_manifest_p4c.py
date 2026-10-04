"""AVS-PKG-002 P4c — completed market profiles in a package-free Evening (finding PKG-F5).

Live proving (Evening 20260927_205123, Morning 28 Sep 2026) showed two losses in manifest mode:
the profile builder took its worklist and ATR from the package files (none → 0 profiles → the
run-level fatal COMPLETED_MARKET_PROFILE_MISSING_OR_UNUSABLE → every Lab row blocked → the Morning
handoff refused), and Vanguard reads the completed-profile evidence FROM the package, which the thin
package never carried (Layer-1 auction NOT_EVALUATED on all 1,616 rows).

Business rules:
- Without a package index the builder's worklist is the run manifest's tickers and its ATR14 comes
  from canonical daily bars; it publishes exactly what it used to patch into the package as a
  per-run `market_profile` enrichment ledger (P3 pattern). Nothing here grants authority.
- The thin package carries the run's market-profile facts (ledger first; the canonical profile
  store for the evidence session as fallback), so Vanguard's input is identical in both modes.
- The completed profile is a PRE-Vanguard input, not a post-Vanguard patch: parity must cover it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from canonical_data import CanonicalRegistry, DatasetType, LifecycleManager, LifecycleState, session_bounds  # noqa: E402
from contracts.enrichment_ledger import ledger_path, read_enrichment_ledger  # noqa: E402
from scripts.build_completed_market_profiles import build_completed_profiles  # noqa: E402
from tests.test_package_free_evening_p4 import RUN, SESSION, package_free_run  # noqa: E402,F401


def _authorise(base: Path, tickers: tuple[str, ...]) -> None:
    """Register the run and its tickers in the control plane, as the Evening's earlier stages do."""
    registry = CanonicalRegistry(base / "data" / "canonical" / "control_plane.sqlite")
    registry.initialise()
    registry.register_run(RUN, "BUILD_THESIS", SESSION)
    lifecycle = LifecycleManager(registry)
    for ticker in tickers:
        event = lifecycle.register(RUN, ticker, allowed_capabilities=(DatasetType.DAILY_OHLCV,))
        lifecycle.transition(
            RUN, ticker, LifecycleState.ACTIVE_CORE, stage="MANIFEST", reason_code="TEST",
            expected_version=event.version, allowed_capabilities=(DatasetType.DAILY_OHLCV,),
        )


def _intraday_frame(interval: int = 5) -> pd.DataFrame:
    """A complete regular session of five-minute bars for the fixture's evidence session."""
    open_utc, close_utc = session_bounds(SESSION)
    timestamps = pd.date_range(open_utc, close_utc, freq=f"{interval}min")
    index = pd.Series(range(len(timestamps)), dtype=float)
    center = 100.0 + (index % 12) * 0.05
    return pd.DataFrame({
        "timestamp_utc": timestamps, "open": center, "high": center + 0.20, "low": center - 0.20,
        "close": center + 0.05, "volume": 1_000.0 + index * 10, "interval_minutes": interval,
        "session_segment": "REGULAR", "provider_observed_at_utc": timestamps, "observed_at": timestamps,
        "provider_http_status": 203,
    })


def _factory(_session, _interval):
    def fetch(_ticker, _start, _end):
        return _intraday_frame(5)
    return fetch


@pytest.fixture
def profiled_run(package_free_run):
    _authorise(package_free_run["base"], ("AAA", "BBB"))
    summary = build_completed_profiles(
        run_id=RUN, session_date=SESSION, base_dir=package_free_run["base"], fetch_factory=_factory,
    )
    return {**package_free_run, "summary": summary}


def test_builder_worklist_is_the_manifest_and_it_publishes_a_market_profile_ledger(profiled_run):
    summary = profiled_run["summary"]
    assert summary["input_count"] == 2, summary
    assert summary["completed"] == 2, summary["exceptions"]
    assert summary["stage_status"] == "PASS"
    assert not (profiled_run["run_dir"] / "packages").exists()
    ledger = read_enrichment_ledger(profiled_run["run_dir"], "market_profile", expected_run_id=RUN)
    assert ledger["status"] == "PRESENT" and set(ledger["by_ticker"]) == {"AAA", "BBB"}
    facts = ledger["by_ticker"]["AAA"]
    assert facts["market_profile_contract_required"] is True
    assert facts["market_profile_evidence_state"] == "COMPLETED_SESSION" and facts["market_profile_exception"] == ""
    assert facts["market_profile_evidence"]["ticker"] == "AAA" and facts["market_profile_evidence"]["poc"] > 0
    assert facts["market_profile_dataset_id"]


def test_thin_package_carries_the_profile_facts_ledger_first(profiled_run):
    from avshunter.c0_run.thin_package import ThinPackageFactory, load_run_reference
    facts = read_enrichment_ledger(profiled_run["run_dir"], "market_profile")["by_ticker"]["AAA"]
    pkg = ThinPackageFactory(load_run_reference(profiled_run["run_dir"])).build("AAA")
    assert pkg["market_profile_contract_required"] is True
    assert pkg["market_profile_evidence"] == facts["market_profile_evidence"]
    assert pkg["market_profile_dataset_id"] == facts["market_profile_dataset_id"]
    assert pkg["market_profile_evidence_state"] == "COMPLETED_SESSION"


def test_thin_package_falls_back_to_the_canonical_profile_store_for_the_evidence_session(profiled_run):
    from avshunter.c0_run.thin_package import ThinPackageFactory, load_run_reference
    facts = read_enrichment_ledger(profiled_run["run_dir"], "market_profile")["by_ticker"]["BBB"]
    ledger_path(profiled_run["run_dir"], "market_profile").unlink()   # a run profiled before P4c has no ledger
    pkg = ThinPackageFactory(load_run_reference(profiled_run["run_dir"])).build("BBB")
    assert pkg["market_profile_evidence"] == facts["market_profile_evidence"]
    assert pkg["market_profile_dataset_id"] == facts["market_profile_dataset_id"]
    assert pkg["market_profile_evidence_state"] == "COMPLETED_SESSION"


def test_a_ticker_without_a_profile_is_typed_not_evaluated_never_fabricated(package_free_run):
    from avshunter.c0_run.thin_package import ThinPackageFactory, load_run_reference
    pkg = ThinPackageFactory(load_run_reference(package_free_run["run_dir"])).build("AAA")
    assert pkg["market_profile_contract_required"] is True
    assert pkg["market_profile_evidence"] is None
    assert pkg["market_profile_evidence_state"] == "NOT_EVALUATED"


def test_completed_profile_is_a_pre_vanguard_input_not_a_post_vanguard_patch():
    from avshunter.c0_run.thin_package import DECLARED_STAMP_KEYS, POST_VANGUARD_PATCH_PREFIXES
    assert not any(prefix.startswith("market_profile") for prefix in POST_VANGUARD_PATCH_PREFIXES)
    assert "market_profile_quality" in DECLARED_STAMP_KEYS   # per-fetch diagnostics, not a Vanguard input


def test_ledger_stage_is_declared():
    from contracts.enrichment_ledger import STAGES
    assert "market_profile" in STAGES
