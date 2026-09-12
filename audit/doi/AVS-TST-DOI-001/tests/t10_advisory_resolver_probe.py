"""AVS-TST-DOI-001 / T10 - advisory resolver rejection probe (read-only).

Design claim under test (AVS-SD-DOI-001):
    "A separate advisory resolver exposes non-actionable rows only for EOD
     review and trajectory use and explicitly rejects executable-session
     requests."

Resolver under test:
    pipeline_interpreter/evidence_resolver.py::resolve_interpreter_opportunity
    (rejection at lines 294-295)

SAFETY / EXECUTION PROOF
------------------------
1.  A network guard is installed *before* the resolver module is imported.
    socket.socket.connect, socket.socket.connect_ex and socket.create_connection
    are replaced with functions that raise.  Any attempt to reach MarketData /
    Polygon / FRED / Tastytrade / Anthropic - at import time or inside the
    exercised code path - fails loudly instead of touching the network.
2.  The resolver's own import graph is provider-free:
      evidence_resolver -> contracts.interpreter_handoff  (stdlib only)
                        -> canonical_data.bundle_freshness -> .session_clock
                        -> pipeline_interpreter.macro_context
                           -> contracts.interpreter_macro_context
    canonical_data/__init__.py loads provider transports lazily through
    module __getattr__ (_LAZY_PROVIDER_EXPORTS, lines 484-556), so importing a
    CDS contract does not pull marketdata_stock_candles into the process.
    test_no_provider_module_imported asserts this at runtime.
3.  resolve_interpreter_opportunity only json.loads a file on disk.  It never
    writes.  The real-run assertions read the frozen reference-run artefact
    read-only; every mutation happens inside pytest's tmp_path.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
REFERENCE_RUN = "20260909_071646"
REAL_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"


# --------------------------------------------------------------------------
# 1. Network guard - installed at module import, before the resolver import.
# --------------------------------------------------------------------------
class NetworkAccessAttempted(AssertionError):
    """A guarded probe tried to open a socket."""


_NETWORK_CALLS: list[str] = []


def _blocked(name):
    def _raise(*args, **kwargs):
        _NETWORK_CALLS.append(f"{name}{args!r}")
        raise NetworkAccessAttempted(f"BLOCKED_NETWORK_CALL:{name}:{args!r}")

    return _raise


socket.socket.connect = _blocked("socket.socket.connect")  # type: ignore[method-assign]
socket.socket.connect_ex = _blocked("socket.socket.connect_ex")  # type: ignore[method-assign]
socket.create_connection = _blocked("socket.create_connection")  # type: ignore[assignment]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline_interpreter.evidence_resolver import (  # noqa: E402
    EvidenceResolutionError,
    IntendedUse,
    ResolvedOpportunityEvidence,
    resolve_interpreter_opportunity,
)


# --------------------------------------------------------------------------
# 2. Synthetic fixture - a minimal governed full opportunity book.
# --------------------------------------------------------------------------
SYNTHETIC_RUN = "29990101_000000"


@pytest.fixture()
def synthetic_runs_dir(tmp_path: Path) -> Path:
    lab = tmp_path / SYNTHETIC_RUN / "intelligence_lab"
    lab.mkdir(parents=True)
    rows = [
        {
            "run_id": SYNTHETIC_RUN,
            "ticker": "AAA",
            "governed_direction": "CALL",
            "final_action": "MANUAL_REVIEW",
            "thesis_id": f"AAA:CALL:2999-01-01:OLM2",
        },
        {
            "run_id": SYNTHETIC_RUN,
            "ticker": "BBB",
            "governed_direction": "PUT",
            "final_action": "CONTRACT_REPAIR",
            "thesis_id": f"BBB:PUT:2999-01-01:OLM2",
        },
    ]
    payload = {
        "run_id": SYNTHETIC_RUN,
        "lab_schema_version": "lab_signal_book_v2",
        "candidate_count": len(rows),
        "rows": rows,
    }
    (lab / f"final_opportunity_book_{SYNTHETIC_RUN}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return tmp_path


# --------------------------------------------------------------------------
# 3. Import-graph proof.
# --------------------------------------------------------------------------
def test_no_provider_module_imported():
    """The resolver import must not pull a live provider transport in."""
    forbidden = [
        name
        for name in sys.modules
        if name.endswith("marketdata_stock_candles")
        or name.endswith("marketdata_response")
        or name.endswith("market_observation_resolver")
        or name.endswith("polygon_client")
        or name.endswith("tastytrade_client")
        or name.split(".")[0] in {"requests", "httpx", "anthropic"}
    ]
    assert forbidden == [], f"provider/transport modules imported: {forbidden}"


def test_network_guard_is_armed():
    with pytest.raises(NetworkAccessAttempted):
        socket.create_connection(("127.0.0.1", 9))


# --------------------------------------------------------------------------
# 4. THE CLAIM - executable-session requests are rejected.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "use",
    [
        IntendedUse.EXECUTABLE_SESSION,
        IntendedUse.INTRADAY_ADVISORY,
        "EXECUTABLE_SESSION",
        "executable_session",
    ],
)
def test_rejects_executable_session(synthetic_runs_dir: Path, use):
    with pytest.raises(EvidenceResolutionError) as caught:
        resolve_interpreter_opportunity(
            "AAA", run_id=SYNTHETIC_RUN, intended_use=use,
            runs_dir=synthetic_runs_dir,
        )
    assert caught.value.code == "FULL_BOOK_USE_NOT_ADVISORY"
    assert caught.value.detail in {"EXECUTABLE_SESSION", "INTRADAY_ADVISORY"}


def test_rejection_happens_before_any_file_is_opened(tmp_path: Path):
    """Refusal is a real guard, not a post-hoc label on a produced row."""
    empty = tmp_path / "no_runs"
    empty.mkdir()
    with pytest.raises(EvidenceResolutionError) as caught:
        resolve_interpreter_opportunity(
            "AAA", run_id=SYNTHETIC_RUN,
            intended_use=IntendedUse.EXECUTABLE_SESSION, runs_dir=empty,
        )
    # If the guard ran first we get the authority code, not a missing-book code.
    assert caught.value.code == "FULL_BOOK_USE_NOT_ADVISORY"


def test_unknown_intended_use_is_rejected(synthetic_runs_dir: Path):
    with pytest.raises(ValueError):
        resolve_interpreter_opportunity(
            "AAA", run_id=SYNTHETIC_RUN, intended_use="LIVE",
            runs_dir=synthetic_runs_dir,
        )


# --------------------------------------------------------------------------
# 5. The permitted advisory uses are accepted.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "use", [IntendedUse.EOD_REVIEW, IntendedUse.TRAJECTORY, "EOD_REVIEW", "TRAJECTORY"]
)
def test_accepts_eod_review_and_trajectory(synthetic_runs_dir: Path, use):
    result = resolve_interpreter_opportunity(
        "AAA", run_id=SYNTHETIC_RUN, intended_use=use, runs_dir=synthetic_runs_dir
    )
    assert isinstance(result, ResolvedOpportunityEvidence)
    assert result.ticker == "AAA"
    assert result.run_id == SYNTHETIC_RUN
    assert result.authority == "ADVISORY_ONLY"
    assert result.provider_calls == 0
    assert result.book_row["governed_direction"] == "CALL"


def test_default_intended_use_is_eod_review(synthetic_runs_dir: Path):
    result = resolve_interpreter_opportunity(
        "BBB", run_id=SYNTHETIC_RUN, runs_dir=synthetic_runs_dir
    )
    assert result.intended_use is IntendedUse.EOD_REVIEW
    assert result.book_row["governed_direction"] == "PUT"


# --------------------------------------------------------------------------
# 6. Same behaviour on the frozen reference run (read-only).
# --------------------------------------------------------------------------
REAL_BOOK = (
    REAL_RUNS_DIR / REFERENCE_RUN / "intelligence_lab"
    / f"final_opportunity_book_{REFERENCE_RUN}.json"
)


@pytest.mark.skipif(not REAL_BOOK.is_file(), reason="reference run book absent")
@pytest.mark.parametrize("ticker", ["VIPS", "ZYME", "AAOI", "CAPR", "MATW", "GDS", "CVNA"])
def test_reference_run_rejects_executable_session(ticker):
    with pytest.raises(EvidenceResolutionError) as caught:
        resolve_interpreter_opportunity(
            ticker, run_id=REFERENCE_RUN,
            intended_use=IntendedUse.EXECUTABLE_SESSION, runs_dir=REAL_RUNS_DIR,
        )
    assert caught.value.code == "FULL_BOOK_USE_NOT_ADVISORY"


@pytest.mark.skipif(not REAL_BOOK.is_file(), reason="reference run book absent")
@pytest.mark.parametrize("ticker", ["VIPS", "ZYME", "AAOI", "CAPR", "MATW", "GDS", "CVNA"])
def test_reference_run_accepts_eod_review(ticker):
    result = resolve_interpreter_opportunity(
        ticker, run_id=REFERENCE_RUN, intended_use=IntendedUse.EOD_REVIEW,
        runs_dir=REAL_RUNS_DIR,
    )
    assert result.authority == "ADVISORY_ONLY"
    assert result.provider_calls == 0
    assert result.run_id == REFERENCE_RUN
    assert str(result.book_row.get("governed_direction") or "").upper() in {"CALL", "PUT"}


@pytest.mark.skipif(not REAL_BOOK.is_file(), reason="reference run book absent")
def test_reference_run_direction_split_call_put_other():
    """Report the advisory population split - never one undifferentiated total."""
    payload = json.loads(REAL_BOOK.read_text(encoding="utf-8-sig"))
    counts = {"CALL": 0, "PUT": 0, "OTHER": 0}
    for row in payload["rows"]:
        value = str(row.get("governed_direction") or "").strip().upper()
        counts[value if value in ("CALL", "PUT") else "OTHER"] += 1
    print(f"\nADVISORY BOOK SPLIT  CALL={counts['CALL']} PUT={counts['PUT']} OTHER={counts['OTHER']}")
    assert sum(counts.values()) == payload["candidate_count"] == 235
    assert counts == {"CALL": 151, "PUT": 84, "OTHER": 0}


def test_no_network_call_was_attempted():
    """Only this file's own deliberate arming probe may appear in the log."""
    unexpected = [
        call for call in _NETWORK_CALLS if "'127.0.0.1', 9" not in call
    ]
    assert unexpected == [], f"unexpected network attempts: {unexpected}"
