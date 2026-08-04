# Pipeline Interpreter Automation v2

This package is the isolated, stateless foundation for automating the complete
ticker interpretation workflow.

## Safety boundary

- It is not imported by the production command router.
- It does not modify `SESSION`, `_loaded_pipeline`, `_loaded_options`, or other
  Interpreter globals.
- It cannot enable execution. `TickerRunRequest(execution_enabled=True)` is
  rejected.
- Every result retains:
  - `EXECUTION_PERMISSION = NONE_PIPELINE_INTERPRETER_ONLY`
  - `CAPITAL_PERMISSION = CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION`
  - `eil_action = STOP`
- Shadow artifacts are written only beneath an explicitly supplied shadow root.
- Attended shadow Webull capture is composed through `capture_v1`; navigation
  and all twelve required captures are automated while exact ticker/screen
  transcription remains an operator safety check.

## Current phase

The first vertical slice supplies:

1. immutable request, evidence, analysis, and result contracts;
2. exact ticker-token asset discovery;
3. hashed chart evidence manifests;
4. deterministic sovereign veto evaluation;
5. `NEGATIVE_RR -> STOP`, blocking GO/EXEC;
6. injected analysis-provider boundary;
7. provider-failure degradation to STOP;
8. unique run/ticker/invocation shadow publication;
9. regression tests for identity, vetoes, state isolation, and failure handling.

Phase 2 additionally supplies:

1. an explicit-path adapter for legacy pipeline, Lab, option, macro, and chart
   evidence;
2. exact-row lookup with missing and duplicate tickers failing closed;
3. run-ID, freshness, file-size, modification-time, and SHA-256 provenance;
4. stable JSON request serialization for deterministic replay;
5. observed legacy artifact baselines for F and NFLX;
6. a compatibility profiler that distinguishes historical output from the
   intended complete output contract.

Phase 3 additionally supplies:

1. validated trade-brief and eight-section junior-briefing schemas;
2. strict parsing of the current tagged narrative/CSV response format;
3. malformed-response degradation to STOP;
4. an injected adapter for the existing Claude API call signature;
5. a concrete legacy prompt adapter that uses the comprehensive ticker path for
   both image and no-image analysis;
6. identical immutable Lab, macro, sector, note, live-validation, and evidence
   context in both main and story stages;
7. sovereign post-parse overlay on the emitted trade brief;
8. atomic publication of raw response, raw story, trade CSV, HTML, sidecar, and
   a hashed artifact manifest.

Phase 4 additionally supplies:

1. narrowly classified retries for timeout, connection, HTTP 429, and HTTP 5xx
   failures only;
2. bounded multi-ticker coordination with one provider instance per request;
3. unique run/ticker/invocation enforcement before batch work starts;
4. per-ticker artifacts plus an atomic batch manifest;
5. representative clean, upstream-denied, and negative-R:R replay fixtures;
6. machine-readable legacy-versus-shadow comparison reports;
7. an explicit-input, fixture-backed shadow CLI that cannot enable execution or
   perform implicit production discovery.

Phase 5 additionally supplies:

1. a lazy live-provider adapter around the existing Claude prompt/API functions;
2. Windows UTF-8 isolation inside the shadow CLI;
3. per-trial latency, attempt, schema, artifact, evidence, status, and sovereign
   metrics;
4. field-level trade-brief comparison excluding fields intentionally tightened
   by sovereign policy;
5. a fail-closed acceptance evaluator;
6. rollout modes limited to `OFF` and non-authoritative `SHADOW`;
7. guaranteed legacy return behavior if a shadow observer fails.

## Core API

```python
result = interpret_ticker(request, provider)
```

The core performs no filesystem reads or writes. Discovery and artifact
publication are adapters around it.

## End-to-end attended shadow run

The batch launcher prefers the newest `avshunter_signals_*.csv` in
`pipeline_interpreter/MA_Inputs/lab_export`, requires `Verdict=GO`, `EV>0`, and
`RR>0`, then orders candidates by `Priority_Rank`.

```powershell
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
python -m pipeline_interpreter.automation_v2.lab_batch_cli `
  --pipeline-outputs pipeline_interpreter\MA_Inputs\pipeline_outputs `
  --staging-root pipeline_interpreter\MA_Inputs\capture_staging `
  --output-directory "pipeline_interpreter\automation_v2\deployments\shadow-$runId" `
  --invocation-id "shadow-$runId" `
  --max-candidates 1 `
  --execute-shadow-batch `
  --capture-webull `
  --confirm-attended-shadow-capture `
  --run-live-interpreter `
  --confirm-shadow-live-provider
```

This remains shadow-only: production publication, execution permission, and
capital permission remain disabled. Live interpretation makes billable
provider calls. Start with one candidate before increasing the batch size.

## Verification

```powershell
python -m unittest tests.test_pipeline_interpreter_automation_v2 -v
python -m unittest tests.test_pipeline_interpreter_automation_v2_adapter -v
python -m unittest tests.test_pipeline_interpreter_automation_v2_phase3 -v
python -m unittest tests.test_pipeline_interpreter_automation_v2_phase4 -v
python -m unittest tests.test_pipeline_interpreter_automation_v2_phase5 -v
python -m compileall -q pipeline_interpreter\automation_v2
```

Offline CLI example:

```powershell
python -m pipeline_interpreter.automation_v2.cli run-fixture `
  --request tests\fixtures\pipeline_interpreter_automation_v2\request_negative_rr.json `
  --main-response <captured-main-response.txt> `
  --story-response <captured-story-response.txt> `
  --shadow-root <isolated-shadow-output>
```

## Next gates

Before production routing is changed:

1. run live-provider shadow comparisons over representative tickers;
2. compare structured output and legacy HTML at field/section level;
3. add production-observability metrics without changing routing;
4. define the disabled-by-default feature flag and rollback contract;
5. require explicit acceptance before placing `/ticker` behind that flag.

Current live-shadow status on 2026-07-25: **NOT ACCEPTED**. Explicit repository
`.env` precedence was added for the isolated shadow process and a minimal Sonnet
probe authenticated successfully. Full Opus two-stage trials exceeded the
bounded command timeout and did not publish a complete result. Sovereign STOP
was preserved on all recorded failures.
