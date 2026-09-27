"""AVS-PKG-002 P1 — the run input manifest (`runs/<run>/canonical_manifest.json`).

Business rules (canonical data design v1 §3.1, §3.8, §4.1 item 5; design rules R1, R2, R7):
- A run cites every input it consumed by path and hash: discovery rows, the run-scoped macro
  snapshot and quant packet, the canonical price history, the actuarial database. A later change
  to any cited file is detectable; nothing is copied.
- Every discovery ticker is listed with its history coverage and a typed data-contract verdict
  computed from the canonical bars, judged against the run's evidence session. Missing or short
  history is a typed rejection on the row, never a dropped row and never a zero.
- The manifest is deterministic for the same inputs, written atomically, and makes no provider call.
- Written beside the packages in P1; consumers still read packages. No authority is granted.
"""
from __future__ import annotations

import csv
import hashlib
import json
import socket
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.historical_prices import HistoricalPriceDatabase  # noqa: E402
from avshunter.c0_run.canonical_manifest import (  # noqa: E402
    CONTRACT_VERSION,
    build_canonical_manifest,
    collect_canonical_inputs,
    validate_canonical_manifest,
    write_canonical_manifest,
)

RUN = "20260925_230000"
SESSION = date(2026, 9, 25)


def _bars(n: int, last: date) -> pd.DataFrame:
    days, d = [], last
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return pd.DataFrame({
        "date": [x.isoformat() for x in days],
        "open": [50.0 + i * 0.01 for i in range(n)],
        "high": [50.5 + i * 0.01 for i in range(n)],
        "low": [49.5 + i * 0.01 for i in range(n)],
        "close": [50.2 + i * 0.01 for i in range(n)],
        "volume": [1_000_000 + i for i in range(n)],
    })


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fixture_run(tmp_path, monkeypatch):
    repo = tmp_path
    run_dir = repo / "data" / "output" / "runs" / RUN
    (run_dir / "discovery").mkdir(parents=True)
    rows = [{"ticker": "FRESH", "signal_price": "50.2"},
            {"ticker": "SHORT", "signal_price": "12.0"},
            {"ticker": "ABSENT", "signal_price": "7.5"},
            {"ticker": "STALE", "signal_price": "80.0"}]
    discovery = run_dir / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv"
    with discovery.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "signal_price"]); w.writeheader(); w.writerows(rows)
    (run_dir / "macro_snapshot.json").write_text(json.dumps({
        "contract_version": "macro_contract_v1_0", "macro_authority": "ADVISORY_ONLY",
        "as_of_utc": "2026-09-25T05:39:11Z", "regime_state": "TRANSITIONAL_BEARISH"}), encoding="utf-8")
    (run_dir / "macro_quant_packet.json").write_text(json.dumps({"macro_regime_label": "TRANSITIONAL"}), encoding="utf-8")
    (run_dir / "run_meta.json").write_text(json.dumps({
        "dynamic_plan": {"last_completed_session": SESSION.isoformat(),
                         "evidence_cutoff_utc": "2026-09-25T23:00:00Z", "run_condition": "TEST"}}), encoding="utf-8")
    db_path = repo / "data" / "canonical" / "historical_prices.sqlite"
    db_path.parent.mkdir(parents=True)
    db = HistoricalPriceDatabase(db_path); db.initialise()
    db.ingest("FRESH", _bars(260, SESSION), provider="TEST", source_kind="DAILY_BACKFILL", source_run_id=RUN)
    db.ingest("SHORT", _bars(30, SESSION), provider="TEST", source_kind="DAILY_BACKFILL", source_run_id=RUN)
    db.ingest("STALE", _bars(260, SESSION - timedelta(days=12)), provider="TEST", source_kind="DAILY_BACKFILL", source_run_id=RUN)
    actuarial = repo / "actuarial_v7.parquet"
    actuarial.write_bytes(b"PAR1-fixture")
    monkeypatch.setenv("AVSHUNTER_HISTORICAL_PRICE_DB", str(db_path))

    def no_network(*_a, **_k):
        raise AssertionError("manifest build attempted a network connection")
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    return {"repo": repo, "run_dir": run_dir, "discovery": discovery, "db_path": db_path, "actuarial": actuarial}


def _build(fx, **overrides):
    kwargs = {"actuarial_path": fx["actuarial"], **overrides}
    inputs = collect_canonical_inputs(run_dir=fx["run_dir"], repo_root=fx["repo"], **kwargs)
    return build_canonical_manifest(inputs, created_at_utc=datetime(2026, 9, 25, 23, 5, tzinfo=timezone.utc))


# ------------------------------------------------------------------ R7: cite by hash, detect tampering
def test_manifest_cites_every_source_by_hash_and_detects_a_later_change(fixture_run):
    fx = fixture_run
    manifest = _build(fx)
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["authority"] == "INPUT_CITATION_ONLY"
    assert manifest["run_id"] == RUN and manifest["evidence_session"] == SESSION.isoformat()
    sources = manifest["sources"]
    assert sources["discovery"]["sha256"] == _sha(fx["discovery"]) and sources["discovery"]["row_count"] == 4
    assert sources["macro_snapshot"]["sha256"] == _sha(fx["run_dir"] / "macro_snapshot.json")
    assert sources["macro_snapshot"]["as_of_utc"] == "2026-09-25T05:39:11Z"
    assert sources["macro_quant_packet"]["sha256"] == _sha(fx["run_dir"] / "macro_quant_packet.json")
    assert sources["actuarial_database"]["sha256"] == _sha(fx["actuarial"])
    hist = sources["historical_prices"]
    assert hist["path"].endswith("historical_prices.sqlite") and hist["status"] == "PRESENT"
    assert hist["dataset_fingerprint"] and hist["fingerprint_basis"]
    for name in ("discovery", "macro_snapshot", "macro_quant_packet", "actuarial_database", "historical_prices"):
        assert sources[name]["status"] == "PRESENT"

    path = write_canonical_manifest(fx["run_dir"], manifest)
    assert path.name == "canonical_manifest.json" and not list(fx["run_dir"].glob("*.tmp*"))
    assert validate_canonical_manifest(path)["valid"] is True

    edited = json.loads((fx["run_dir"] / "macro_snapshot.json").read_text(encoding="utf-8"))
    edited["regime_state"] = "RISK_ON_BULLISH"
    (fx["run_dir"] / "macro_snapshot.json").write_text(json.dumps(edited), encoding="utf-8")
    result = validate_canonical_manifest(path)
    assert result["valid"] is False
    assert result["mismatches"] == ["macro_snapshot"]


# ------------------------------------------------------------------ R1: typed verdicts, nothing dropped
def test_every_discovery_ticker_is_listed_with_a_typed_history_verdict(fixture_run):
    manifest = _build(fixture_run)
    by = {row["ticker"]: row for row in manifest["tickers"]}
    assert list(by) == ["ABSENT", "FRESH", "SHORT", "STALE"]  # sorted, complete
    assert by["FRESH"]["dcv_verdict"] is True and by["FRESH"]["dcv_reason"] == "VALID"
    assert by["FRESH"]["bar_count"] == 260 and by["FRESH"]["last_session"] == SESSION.isoformat()
    assert by["FRESH"]["dcv_confidence"] == "HIGH"
    assert by["SHORT"]["dcv_verdict"] is False and by["SHORT"]["dcv_reason"].startswith("INSUFFICIENT_HISTORY")
    assert by["SHORT"]["bar_count"] == 30
    assert by["ABSENT"]["dcv_verdict"] is False and by["ABSENT"]["dcv_reason"] == "NO_OHLCV"
    assert by["ABSENT"]["bar_count"] == 0 and by["ABSENT"]["last_session"] is None
    assert by["STALE"]["dcv_verdict"] is False and by["STALE"]["dcv_reason"].startswith("STALE_DATA")
    stale_last = date.fromisoformat(by["STALE"]["last_session"])
    assert by["STALE"]["staleness_days"] == (SESSION - stale_last).days > 5
    for row in manifest["tickers"]:
        assert row["regime_present"] is True
        assert len(row["discovery_row_sha256"]) == 64
    coverage = manifest["coverage"]
    assert coverage["tickers"] == 4 and coverage["valid"] == 1 and coverage["rejected"] == 3
    assert coverage["rejected_by_reason"]["NO_OHLCV"] == 1
    assert coverage["valid_ratio"] == pytest.approx(0.25)


def test_staleness_is_judged_against_the_evidence_session_not_the_wall_clock(fixture_run):
    # The same bars are fresh when the run's evidence session is their last bar ...
    manifest = _build(fixture_run)
    assert {r["ticker"]: r["dcv_reason"] for r in manifest["tickers"]}["FRESH"] == "VALID"
    # ... and stale when a later run cites them, regardless of today's date.
    later = dict(json.loads((fixture_run["run_dir"] / "run_meta.json").read_text(encoding="utf-8")))
    later["dynamic_plan"]["last_completed_session"] = (SESSION + timedelta(days=10)).isoformat()
    (fixture_run["run_dir"] / "run_meta.json").write_text(json.dumps(later), encoding="utf-8")
    manifest2 = _build(fixture_run)
    fresh = {r["ticker"]: r for r in manifest2["tickers"]}["FRESH"]
    assert fresh["dcv_verdict"] is False and fresh["dcv_reason"].startswith("STALE_DATA")
    assert manifest2["history_policy"]["reference_session"] == (SESSION + timedelta(days=10)).isoformat()
    assert manifest2["history_policy"]["max_staleness_days"] == 5 and manifest2["history_policy"]["min_bars"] == 50


# ------------------------------------------------------------------ deterministic, governed ticker set
def test_manifest_is_deterministic_for_the_same_inputs(fixture_run):
    a, b = _build(fixture_run), _build(fixture_run)
    assert a["manifest_sha256"] == b["manifest_sha256"]
    assert len(a["manifest_sha256"]) == 64
    body = {k: v for k, v in a.items() if k not in {"manifest_sha256", "created_at_utc"}}
    assert a["manifest_sha256"] == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_ticker_set_follows_deduped_discovery_or_the_governed_worklist(fixture_run):
    fx = fixture_run
    with fx["discovery"].open("a", encoding="utf-8", newline="") as fh:
        fh.write("fresh,50.3\n")  # duplicate, different case
    manifest = _build(fx)
    assert [r["ticker"] for r in manifest["tickers"]] == ["ABSENT", "FRESH", "SHORT", "STALE"]
    assert manifest["sources"]["discovery"]["row_count"] == 5
    assert manifest["sources"]["discovery"]["duplicate_tickers"] == ["FRESH"]

    governed = _build(fx, worklist=("FRESH", "SHORT", "NEWCO"))
    assert [r["ticker"] for r in governed["tickers"]] == ["FRESH", "NEWCO", "SHORT"]
    newco = {r["ticker"]: r for r in governed["tickers"]}["NEWCO"]
    assert newco["dcv_verdict"] is False and newco["dcv_reason"] == "WORKLIST_TICKER_MISSING_FROM_DISCOVERY"
    assert newco["discovery_row_sha256"] is None
    assert governed["ticker_set_source"] == "GOVERNED_WORKLIST"
    assert manifest["ticker_set_source"] == "DISCOVERY_DEDUPED"


def test_missing_optional_source_is_typed_not_fabricated(fixture_run):
    fx = fixture_run
    (fx["run_dir"] / "macro_quant_packet.json").unlink()
    manifest = _build(fx, actuarial_path=fx["repo"] / "nope.parquet")
    quant = manifest["sources"]["macro_quant_packet"]
    assert quant["status"] == "MISSING" and quant["sha256"] is None
    assert quant["path"].endswith("macro_quant_packet.json")  # says where it looked
    assert manifest["sources"]["actuarial_database"]["status"] == "MISSING"
    assert manifest["sources"]["actuarial_database"]["sha256"] is None
    # A missing macro snapshot is a hard failure: the run has no cited macro evidence.
    (fx["run_dir"] / "macro_snapshot.json").unlink()
    with pytest.raises(FileNotFoundError, match="macro_snapshot.json"):
        _build(fx)


# ------------------------------------------------------------------ P1 gate on the retained real run (read-only)
REAL_RUN = "20260926_173730"
REAL_DIR = ROOT / "data" / "output" / "runs" / REAL_RUN


@pytest.mark.skipif(not (REAL_DIR / "packages").is_dir(), reason="retained package run not present")
def test_p1_gate_manifest_verdicts_equal_dcv_over_the_packages_actual_bars(tmp_path):
    """Parity: for every retained package, the manifest's verdict from canonical history equals the
    data-contract validator applied to the bars the package actually carries. The package's own
    stored dcv_* annotation is NOT the reference: it was stamped before backfill (finding PKG-F1)."""
    from scripts.data_contract_validator import DataContractValidator as DCV

    before = hashlib.sha256((REAL_DIR / "run_meta.json").read_bytes()).hexdigest()
    inputs = collect_canonical_inputs(run_dir=REAL_DIR, repo_root=ROOT)
    manifest = build_canonical_manifest(inputs, created_at_utc=datetime.now(timezone.utc))
    write_canonical_manifest(tmp_path, manifest)  # never into the real run in P1 tests
    assert hashlib.sha256((REAL_DIR / "run_meta.json").read_bytes()).hexdigest() == before
    assert manifest["evidence_session"] == "2026-09-25"
    by = {row["ticker"]: row for row in manifest["tickers"]}

    packages = sorted((REAL_DIR / "packages").glob("*.package.json"))
    assert set(by) == {p.name[:-13].upper() for p in packages}
    disagreements, stale_annotations, withheld_as_stale, barless, checked = [], 0, 0, 0, 0
    for path in packages:
        pkg = json.loads(path.read_text(encoding="utf-8-sig"))
        ticker = path.name[:-13].upper()
        bars = pkg.get("ohlcv_daily") or []
        ok, reason = DCV.validate_price_history({"ohlcv": bars}) if bars else (False, "NO_OHLCV")
        row = by[ticker]
        manifest_reason = row["dcv_reason"].split(" ")[0]
        package_reason = reason.split(" ")[0]
        if bool(row["dcv_verdict"]) != ok:
            disagreements.append((ticker, "verdict", row["dcv_reason"], reason))
        elif ok and row["bar_count"] != len(bars):
            disagreements.append((ticker, "bar_count", row["bar_count"], len(bars)))
        elif manifest_reason != package_reason:
            # The backfill withholds stale canonical bars, so the package cannot tell "no history"
            # from "history too old"; the manifest can and must say so (R1). Any other difference
            # is a real disagreement.
            if package_reason == "NO_OHLCV" and manifest_reason == "STALE_DATA":
                withheld_as_stale += 1
            else:
                disagreements.append((ticker, row["dcv_reason"], reason))
        if not bars:
            barless += 1
        if bars and not (pkg.get("data_contract") or {}).get("dcv_valid"):
            stale_annotations += 1
        checked += 1
    assert checked == len(packages)
    assert disagreements == [], disagreements[:10]
    assert withheld_as_stale <= barless
    assert manifest["coverage"]["valid"] >= int(0.95 * checked)
    assert manifest["coverage"]["valid"] == checked - barless  # every bar-carrying package is VALID
    # Finding PKG-F1 is recorded, not hidden: the packages' own annotation disagrees with their bars.
    assert stale_annotations > 0


# ------------------------------------------------------------------ orchestrator hook (non-critical, beside the packages)
def test_evening_writes_the_manifest_after_backfill_without_making_it_critical():
    import inspect
    import intelligent_orchestrator as orch

    assert orch.cfg.BUILD_CANONICAL_MANIFEST.name == "build_canonical_manifest.py"
    assert orch.cfg.BUILD_CANONICAL_MANIFEST.is_file()
    # P4: the package phases (build, inject, backfill) live in the rollback-only helper; the
    # pipeline runs that helper only in packages mode, then builds the manifest, then Vanguard.
    helper = inspect.getsource(orch._run_package_input_phases)
    assert "BACKFILL_TIMESERIES" in helper and "BUILD_PACKAGES" in helper and "INJECT_MACRO" in helper
    source = inspect.getsource(orch.run_vanguard_pipeline)
    phases = source.index("_run_package_input_phases(")
    hook = source.index("BUILD_CANONICAL_MANIFEST")
    vanguard = source.index("RUN_VANGUARD")
    assert phases < hook < vanguard, "manifest is built after any package phases and before Vanguard reads"
    hook_call = source[hook - 200: hook + 300]
    # P1 kept the hook non-critical beside the packages; P4 makes it the input in manifest mode.
    assert 'critical=(_input_mode == "manifest")' in hook_call
