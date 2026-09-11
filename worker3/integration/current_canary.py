"""Current governed evidence canary. Offline by default; no production writes.

Run from the repository with ``python -B -m worker3.integration.current_canary``.
The explicit live mode has a persistent attempt latch and never retries.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from anthropic_runtime_config import workspace_id as configured_workspace_id
from unittest.mock import patch

from ..adapters.claude_v2 import ClaudeV2Adapter
from ..adapters.jobs import JobStore
from ..adapters.lab_reports import AnalystReports
from ..domain import ContractError, Section, canonical, digest
from ..v2.assessment import SCHEMA
from .activation import ControlledProviderRuntime
from .avshunter_source import AvshunterSourceBridge
from .coordinator import Worker3Coordinator
from .lab_mount import install_worker3_lab_projection

MODEL = "claude-sonnet-4-6"
CEILING = 500_000
INPUT_BYTES = 500_000
OUTPUT_TOKENS = 8192
GENERATION_TIMEOUT_SECONDS = 300
PRICING_SOURCE = "https://platform.claude.com/docs/en/models/sonnet-4-6/overview"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def count_frozen_request(request, connection_factory=http.client.HTTPSConnection, receipt=None):
    """One free preflight HTTP request. No redirects, retries or error-body logging."""
    if request.get("model") != MODEL:
        raise ContractError("counted model differs from approved model")
    if receipt is None:
        receipt = {}
    receipt.update(model=MODEL, frozen_request_hash=digest(request), http_status=None)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or any(character in key for character in "\r\n"):
        raise ContractError("environment credential unavailable or invalid")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    try:
        headers["anthropic-workspace-id"] = configured_workspace_id()
    except RuntimeError as exc:
        raise ContractError(str(exc)) from None
    packet = {name: request[name] for name in ("model", "system", "messages")}
    if "output_config" in request:
        packet["output_config"] = request["output_config"]
    connection = connection_factory("api.anthropic.com", timeout=60)
    try:
        connection.request("POST", "/v1/messages/count_tokens", body=canonical(packet).encode(), headers=headers)
        response = connection.getresponse()
        receipt["http_status"] = response.status
        if response.status != 200:
            raise ContractError(f"token-count HTTP {response.status}; no retry")
        raw = response.read(8193)
        if len(raw) > 8192:
            raise ContractError("oversized token-count response")
        value = json.loads(raw)
        tokens = value.get("input_tokens")
        if type(tokens) is not int or tokens <= 0 or value.get("model", MODEL) != MODEL:
            raise ContractError("token count unavailable or model differs")
        receipt.update({"http_status": 200, "input_tokens": tokens, "model": MODEL,
                "count_packet_hash": digest(packet), "frozen_request_hash": digest(request),
                "credential_source": "os.environ",
                "credential_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:8]})
        return receipt
    except ContractError:
        raise
    except Exception:
        raise ContractError("token-count request failed; details withheld; no retry") from None
    finally:
        connection.close()


def counted_cost_ceiling(request, receipt):
    if receipt["frozen_request_hash"] != digest(request) or request["model"] != MODEL:
        raise ContractError("request changed after token count")
    # Anthropic documents token counts as estimates with small possible drift.
    # Reserve a further 4096 input tokens in addition to the complete output cap.
    total = (receipt["input_tokens"] + 4096) * 3 + request["max_tokens"] * 15
    if total > CEILING:
        raise ContractError("counted worst-case cost exceeds paid canary ceiling")
    return total


def latest_completed(bridge):
    """Resolve dated directories, never an ungoverned 'latest' alias.

    A newer completed run that fails governance blocks resolution rather than
    silently falling back to old evidence. Incomplete runs are recorded.
    """
    skipped = []
    for directory in sorted(bridge.runs_root.iterdir(), reverse=True):
        if not directory.is_dir() or not re.fullmatch(r"\d{8}_\d{6}", directory.name):
            continue
        meta = json.loads((directory / "run_meta.json").read_text(encoding="utf-8"))
        if meta.get("run_status") != "COMPLETED":
            skipped.append({"run_id": directory.name, "status": meta.get("run_status")})
            continue
        bridge.load_context(directory.name)
        return directory.name, skipped
    raise ContractError("no completed governed run available")


def select_candidate(prepared, ticker=None, direction=None):
    entries = [entry for entry in prepared.entries if entry.bundle is not None]
    if ticker is not None:
        entries = [entry for entry in entries if entry.ticker == ticker]
    if direction is not None:
        entries = [entry for entry in entries if entry.bundle.identity.direction.value == direction]
    if not entries:
        raise ContractError("requested canary has no prepared evidence; no ticker fallback")
    return sorted(entries, key=lambda entry: entry.ticker)[0]


class DeterministicTransport:
    def __init__(self, context, mode="valid"):
        self.context, self.mode = context, mode
        self.calls, self.receipts = [], []

    def create(self, request, *, timeout_seconds):
        self.calls.append(digest(request))
        self.receipts.append({"request_hash": digest(request), "http_status": 200,
                              "input_tokens": 100, "output_tokens": 50,
                              "credential_source": "deterministic_fake",
                              "credential_fingerprint": None, "elapsed_ms": 0})
        if self.mode == "envelope":
            return {"id": "invalid-envelope"}
        job = self.context.job
        payload = {"schema_version": SCHEMA, "job_key": job.job_key,
                   "identity": asdict(job.bundle.identity),
                   "evidence_hash": job.bundle.evidence_hash,
                   "context_hash": self.context.context_hash,
                   "authority": "BUY_NOW" if self.mode == "authority" else "ADVISORY_ONLY",
                   "claims": [], "numeric_facts": [],
                   "sections": [{"section": section.value,
                                 "summary": "Evidence review pending.", "claim_ids": []}
                                for section in Section]}
        return {"id": "fake-" + digest(request), "model": job.model,
                "stop_reason": "end_turn", "content": [{"type": "text", "text": canonical(payload)}]}


class NoTransport:
    def create(self, *args, **kwargs):
        raise AssertionError("replay attempted a second provider call")


def release_copy(repository, target, **overrides):
    value = json.loads((repository / "contracts/worker3_provider_release_v1.json").read_text())
    value.update(release_id="WORKER3-DISPOSABLE-CANARY", enabled=True,
                 status="CONTROLLED_ACTIVE", allowed_models=[MODEL],
                 max_jobs_per_activation=1, max_calls_per_process=1,
                 max_total_microusd=CEILING, max_call_microusd=CEILING,
                 input_microusd_per_million_tokens=3_000_000,
                 output_microusd_per_million_tokens=15_000_000,
                 max_input_bytes=INPUT_BYTES, max_output_tokens=OUTPUT_TOKENS,
                 timeout_seconds=GENERATION_TIMEOUT_SECONDS, lab_projection_enabled=True)
    value.update(overrides)
    target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return target


def open_runtime(stack, repository, directory, release):
    store = JobStore(directory / "jobs.sqlite", budget_microusd=CEILING)
    stack.callback(store.close)
    reports = AnalystReports(directory / "data/worker3/analyst_reports.sqlite")
    stack.callback(reports.close)
    coordinator = Worker3Coordinator(AvshunterSourceBridge(repository), store,
                                    repository / "contracts/worker3_integration_v1.json")
    runtime = ControlledProviderRuntime(coordinator, store, reports, release)
    return store, reports, coordinator, runtime


def route_checks(directory, release, identity, assessment_id):
    from flask import Flask
    app = Flask("worker3_canary")
    reports = install_worker3_lab_projection(app, directory, release)
    try:
        client = app.test_client()
        suffix = f"{identity.run_id}/{identity.ticker}/{assessment_id}"
        response = client.get("/api/worker3/report/" + suffix)
        view = response.get_json()
        assert response.status_code == 200 and view["execution_permission"] is False
        assert view["authority"] == "ADVISORY_ONLY" and view["human_review_required"] is True
        assert view["identity"] == json.loads(canonical(asdict(identity)))
        assert client.get("/worker3/report/" + suffix).status_code == 200
        wrong = [("wrong", identity.ticker, assessment_id),
                 (identity.run_id, "WRONG", assessment_id),
                 (identity.run_id, identity.ticker, "0" * 64)]
        for parts in wrong:
            for prefix in ("/api/worker3/report/", "/worker3/report/"):
                assert client.get(prefix + "/".join(parts)).status_code == 404
        return {"exact_json": 200, "exact_html": 200, "wrong_identity_404s": 6,
                "route": "/api/worker3/report/" + suffix, "view": view}
    finally:
        reports.close()


def restore_process(repository, directory, release, job_id):
    # A genuinely new interpreter reopens the stores, with no provider transport.
    command = [sys.executable, "-B", "-m", "worker3.integration.current_canary", "--repository", str(repository),
               "--restore", str(directory), "--release", str(release), "--job-id", job_id, "--max-cost-microusd", str(CEILING)]
    return json.loads(subprocess.check_output(command, cwd=Path(__file__).resolve().parents[2], text=True))


def expect_blocked(action, phrase):
    try:
        action()
    except ContractError as exc:
        if phrase not in str(exc):
            raise AssertionError(f"wrong rejection: {exc}") from exc
        return str(exc)
    raise AssertionError("operation unexpectedly accepted")


def activation_controls(repository, run_id, tickers):
    """Use real current identities to check release and durable batch ceilings."""
    with tempfile.TemporaryDirectory(prefix="worker3-controls-") as temporary, ExitStack() as stack:
        directory = Path(temporary)
        (directory / "data/worker3").mkdir(parents=True)
        release = release_copy(repository, directory / "release.json")
        store, reports, coordinator, runtime = open_runtime(stack, repository, directory, release)
        prepared = coordinator.prepare_run(run_id, provider="ANTHROPIC", model=MODEL,
                                           tickers=tuple(tickers), now=time.time(),
                                           call_ceiling_microusd=CEILING)
        ids = tuple(entry.job_id for entry in prepared.entries)
        disabled_release = release_copy(repository, directory / "disabled.json",
                                        enabled=False, status="INSTALLED_DISABLED")
        disabled = ControlledProviderRuntime(coordinator, store, reports, disabled_release)
        result = {"disabled": expect_blocked(lambda: disabled.activate(
            (ids[0],), operator_approval_id="offline", now=time.time()), "disabled")}
        wrong_release = release_copy(repository, directory / "wrong.json", allowed_models=["not-approved"])
        wrong = ControlledProviderRuntime(coordinator, store, reports, wrong_release)
        result["model_allowlist"] = expect_blocked(lambda: wrong.activate(
            (ids[0],), operator_approval_id="offline", now=time.time()), "not release-approved")
        runtime.activate((ids[0],), operator_approval_id="offline", now=time.time())
        if len(ids) > 1:
            result["job_count"] = expect_blocked(lambda: runtime.activate(
                ids, operator_approval_id="offline", now=time.time()), "job count")
            stack.close()
            store, reports, coordinator, runtime = open_runtime(stack, repository, directory, release)
            result["cumulative_after_reopen"] = expect_blocked(lambda: runtime.activate(
                (ids[1],), operator_approval_id="offline", now=time.time()), "cumulative activation")
            assert store.job_record(ids[1])["status"] == "PREPARED"
        result["provider_attempts"] = 0
        return result


def exercise(repository, run_id, ticker, *, mode="valid", live=False):
    with tempfile.TemporaryDirectory(prefix="worker3-canary-") as temporary, ExitStack() as stack:
        directory = Path(temporary)
        (directory / "data/worker3").mkdir(parents=True)
        release = release_copy(repository, directory / "release.json")
        store, reports, coordinator, runtime = open_runtime(stack, repository, directory, release)
        prepared = coordinator.prepare_run(run_id, provider="ANTHROPIC", model=MODEL,
                    tickers=(ticker,), now=time.time(), call_ceiling_microusd=CEILING,
                    max_input_bytes=INPUT_BYTES, max_output_tokens=OUTPUT_TOKENS,
                    timeout_seconds=GENERATION_TIMEOUT_SECONDS)
        assert len(prepared.entries) == 1 and prepared.entries[0].job_id
        job_id = prepared.entries[0].job_id
        context = coordinator.restore_context(job_id)
        request = ClaudeV2Adapter(NoTransport(), OUTPUT_TOKENS, INPUT_BYTES,
                                 GENERATION_TIMEOUT_SECONDS, context).request_for(context.job)
        request_bytes = len(canonical(request).encode())
        # Conservatively reserve one input token per serialized UTF-8 byte plus
        # protocol margin; output tokens have an API-enforced hard maximum.
        estimated_ceiling = (request_bytes + 4096) * 3 + OUTPUT_TOKENS * 15
        details = {"identity": asdict(context.job.bundle.identity), "job_id": job_id,
                   "job_key": context.job.job_key, "context_hash": context.context_hash,
                   "evidence_hash": context.job.bundle.evidence_hash,
                   "request_fingerprint": store.job_record(job_id)["payload"]["request_fingerprint"],
                   "request_hash": digest(request), "request_bytes": request_bytes,
                   "byte_based_cost_bound_microusd": estimated_ceiling,
                   "release_hash": sha(release), "release": json.loads(release.read_text()),
                   "prepared_count": len(prepared.entries), "mode": mode, "live": live}
        if live:
            details.update(count_request_attempts=1, generation_request_attempts=0, retries=0, count_receipt={})
            try:
                count_frozen_request(request, receipt=details["count_receipt"])
                details["counted_cost_ceiling_microusd"] = counted_cost_ceiling(request, details["count_receipt"])
            except ContractError as exc:
                details.update(accepted=False, error=str(exc), state="PREPARED")
                return details
        details["approval_rejection"] = expect_blocked(
            lambda: runtime.activate((job_id,), operator_approval_id="", now=time.time()), "operator approval")
        runtime.activate((job_id,), operator_approval_id="user-one-call-canary" if live else "offline-canary", now=time.time())
        details["activation"] = store.activation_record(job_id)
        if live:
            from ..adapters.anthropic_http import AnthropicHTTP
            transport = AnthropicHTTP(enabled=True, max_calls=1, max_input_bytes=INPUT_BYTES,
                                      max_output_tokens=OUTPUT_TOKENS)
        else:
            transport = DeterministicTransport(context, mode)
        provider_envelopes = []
        original_create = transport.create

        def capture_response(request, *, timeout_seconds):
            if live:
                counted_cost_ceiling(request, details["count_receipt"])
                details["generation_request_attempts"] += 1
                if details["generation_request_attempts"] != 1:
                    raise ContractError("canary generation already attempted")
            response = original_create(request, timeout_seconds=timeout_seconds)
            provider_envelopes.append(response)
            return response

        transport.create = capture_response
        try:
            if mode == "projection_failure":
                with patch.object(reports, "save_draft", side_effect=RuntimeError("injected projection failure")):
                    try:
                        runtime.execute(job_id, transport=transport, clock=time.time)
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("projection failure not exercised")
                assert store.job_record(job_id)["status"] == "REVIEW_REQUIRED"
                result = runtime.execute(job_id, transport=NoTransport(), clock=time.time)
            else:
                result = runtime.execute(job_id, transport=transport, clock=time.time)
            details["result"] = result
            replay = runtime.execute(job_id, transport=NoTransport(), clock=time.time)
            assert replay["provider_called"] is False
            assert replay["assessment_id"] == result["assessment_id"]
            details["replay"] = replay
            details["routes"] = route_checks(directory, release, context.job.bundle.identity, result["assessment_id"])
            # Close before a new process restores the durable state.
            stack.close()
            details["restart_replay"] = restore_process(repository, directory, release, job_id)
            store, reports, coordinator, runtime = open_runtime(stack, repository, directory, release)
        except ContractError as exc:
            details["error"] = str(exc)
            if mode not in ("envelope", "authority") and not live:
                raise
            assert store.job_record(job_id)["status"] == "UNCERTAIN"
            details["uncertain_replay_rejection"] = expect_blocked(
                lambda: runtime.execute(job_id, transport=NoTransport(), clock=time.time()), "call limit")
        details["provider_attempts"] = len(transport.receipts)
        assert details["provider_attempts"] == 1
        # Strict allow-list: never retain provider error prose, headers or keys.
        allowed = ("request_hash", "model", "http_status", "input_tokens", "output_tokens",
                   "elapsed_ms", "credential_source", "credential_fingerprint", "status",
                   "error_type", "failure_stage", "timeout_seconds")
        details["receipts"] = [{key: receipt.get(key) for key in allowed} for receipt in transport.receipts]
        details["state"] = store.job_record(job_id)["status"]
        if live:
            details["provider_envelopes"] = provider_envelopes
        details["accounting"] = store.accounting()
        details["durable_response"] = store.completed_result(job_id)
        details["events"] = [dict(row) for row in store.db.execute("SELECT * FROM events ORDER BY seq")]
        details["charges"] = [dict(row) for row in store.db.execute("SELECT * FROM charges")]
        release.write_text(release.read_text() + "\n")
        details["tamper_rejection"] = expect_blocked(
            lambda: runtime.execute(job_id, transport=NoTransport(), clock=time.time()), "changed after")
        details["accepted"] = details["state"] == "REVIEW_REQUIRED" and bool(details.get("restart_replay"))
        if live:
            receipt = details["receipts"][0]
            details["accepted"] = details["accepted"] and receipt["http_status"] == 200 and (
                receipt["model"] == MODEL and type(receipt["input_tokens"]) is int
                and type(receipt["output_tokens"]) is int
                and details["accounting"]["unknown_calls"] == 0
                and 0 <= details["accounting"]["reported_cost_microusd"] <= CEILING)
        return details


def offline_audit(repository, checkpoint=None):
    bridge = AvshunterSourceBridge(repository)
    run_id, skipped = latest_completed(bridge)
    with patch.object(socket.socket, "connect", side_effect=AssertionError("offline canary attempted network")):
        with tempfile.TemporaryDirectory(prefix="worker3-intake-") as temporary:
            store = JobStore(Path(temporary) / "intake.sqlite", budget_microusd=CEILING)
            try:
                coordinator = Worker3Coordinator(bridge, store, repository / "contracts/worker3_integration_v1.json")
                prepared = coordinator.prepare_run(run_id, provider="ANTHROPIC", model=MODEL, now=time.time())
                intake = store.intake_progress(run_id)
            finally:
                store.close()
        source = prepared.source
        directions = Counter(entry.bundle.identity.direction.value for entry in source.entries if entry.bundle)
        if checkpoint is not None:
            checkpoint.write_text(json.dumps({"run": asdict(source.context),
                "summary": prepared.summary(), "intakes": intake,
                "directions": dict(directions)}, indent=2, default=str), encoding="utf-8")
        selected = [select_candidate(source, direction=direction).ticker for direction in ("CALL", "PUT") if directions[direction]]
        cases = [exercise(repository, run_id, ticker) for ticker in selected]
        controls = activation_controls(repository, run_id, selected) if selected else {}
        if selected:
            cases += [exercise(repository, run_id, selected[0], mode=mode)
                      for mode in ("envelope", "authority", "projection_failure")]
        return {"schema_version": "worker3_current_state_canary_v1", "run": asdict(source.context),
                "skipped_runs": skipped, "summary": prepared.summary(), "directions": dict(directions),
                "intakes": intake, "cases": cases, "activation_controls": controls, "offline_network_calls": 0,
                "production_release_hash": sha(repository / "contracts/worker3_provider_release_v1.json")}


def main(argv=None):
    global CEILING
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ticker")
    parser.add_argument("--live-one-call", action="store_true")
    parser.add_argument("--restore", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--release", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--job-id", help=argparse.SUPPRESS)
    parser.add_argument('--max-cost-microusd', type=int, choices=(500_000, 1_000_000), default=500_000)
    args = parser.parse_args(argv)
    CEILING = args.max_cost_microusd
    repository = args.repository.resolve(strict=True)
    if args.restore:
        with ExitStack() as stack:
            store, reports, coordinator, runtime = open_runtime(stack, repository, args.restore, args.release)
            result = runtime.execute(args.job_id, transport=NoTransport(), clock=time.time)
            assert result["provider_called"] is False
            print(canonical(result))
        return 0
    if args.output is None:
        args.output = repository / "audit/worker3_current_state_canary" / ("live.json" if args.live_one_call else "offline.json")
    output = args.output.resolve()
    approved = (repository / "audit/worker3_current_state_canary").resolve()
    if not output.is_relative_to(approved):
        raise ContractError("canary output must remain in its dedicated audit directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.live_one_call:
        if not args.ticker:
            raise ContractError("live canary requires an explicit exact ticker")
        bridge = AvshunterSourceBridge(repository)
        run_id, _ = latest_completed(bridge)
        select_candidate(bridge.prepare_run(run_id, tickers=(args.ticker,)), ticker=args.ticker)
        # Across reruns, a prior started attempt always requires manual reconciliation.
        with (approved / "LIVE_ATTEMPT_LATCH.json").open("x", encoding="utf-8") as handle:
            json.dump({"run_id": run_id, "ticker": args.ticker, "model": MODEL,
                       "ceiling_microusd": CEILING, "started_at": time.time()}, handle)
        result = exercise(repository, run_id, args.ticker, live=True)
    else:
        result = offline_audit(repository, approved / "intake.json")
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(output), "accepted": result.get("accepted"), "summary": result.get("summary")}))
    return 0 if not args.live_one_call or result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
