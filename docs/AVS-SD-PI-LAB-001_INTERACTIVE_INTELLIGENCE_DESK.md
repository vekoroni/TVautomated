# AVS-SD-PI-LAB-001 — Interactive Intelligence Desk

**Status:** Integrated offline build complete; live GPT provider canary and next completed-session EOD acceptance pending. Not yet production-signed-off.
**Date:** 22 September 2026
**Scope:** Intelligence Lab selection of at most five tickers, governed Pipeline Interpreter reports, and interactive GPT questions.
**Non-goals:** changing Discovery/Vanguard/Options/Morning decisions, trading authority, broker orders, capital allocation, screenshots, or activating Worker 3.

## 1. Business outcome and decision

The completed-session Evening pipeline must give the trader a defensible thesis and focused list before the next session. The trader selects up to five Lab tickers for deep, sourced reports. Morning validation compares new evidence with the frozen Evening thesis; it does not create a new thesis merely because a quote has aged. The trader can then interrogate each report in the Lab. The Interpreter explains and challenges evidence; it cannot promote a blocked opportunity, change the selected direction or contract, or grant execution permission.

This is a **new Lab-to-Interpreter read model and report workflow**, reusing the working governed resolver and reporting capability. It does not revive screenshot capture, independent `/triage`, the legacy contract-repair brief, or the shadow `automation_v2` route.

## 2. Verified current state and design consequences

| Current implementation | Consequence for this design |
|---|---|
| `pipeline_interpreter/evidence_resolver.py` binds a Morning handoff to run, ticker, direction, contract, quote snapshot and bundle identity. | Reuse its identity and hash checks for Morning reports; do not reconstruct a ticker from loose CSVs. |
| `contracts/interpreter_handoff_materializer.py` requires an exact option contract; `morning_handoff_finalizer.py` creates the accepted handoff after Morning. | Add a separate immutable EOD review bundle that can represent a formed share thesis even when no option contract is selected. Do not weaken the Morning contract. |
| The governed `_msi_cmd_ticker` in `pipeline_interpreter/pipeline_interpreter_commands.py` makes one model call and stores a generic assessment with a short narrative excerpt. | Preserve the governed route, but add a versioned, multi-section report contract and separate report persistence. |
| The legacy Interpreter produced a main narrative plus eight junior sections, but could independently recommend a different contract or position size. | Restore analytical depth, not legacy authority. Any alternative is explicitly hypothetical and cannot replace the governed selection. |
| `build_single_ticker_prompt` includes nearly every nonempty Lab field; a current PFE row has 634 columns and roughly 112k characters. The system prompt is roughly 63k characters. | Compile a bounded evidence digest by domain with explicit omission accounting. Never silently truncate a required fact or send five full rows in one request. |
| `contracts/lab_evidence_overlay.py` keeps the latest compatible overlay per run/ticker/bundle. | Put reports and conversations in their own read model/API. A report must not supersede the existing assessment overlay or mutate Lab authority fields. |
| The Lab already has a maximum-five selection pattern for Worker 3. | Reuse the interaction pattern, not Worker 3's job queue/provider contract. |
| The current run has an accepted Morning Interpreter handoff for 249 rows, while the Lab has 1,543 total rows (249 GO, 583 FLAG, 711 BLOCK). | A five-ticker selection is a human review subset, not a claim that 249 are executable. Reconcile each selected row with its source manifest and state. |
| `final_run_manifest.json` for a run is refreshed after Morning and changes `pipeline_mode` to `MORNING_VALIDATION`. | The EOD review bundle needs a frozen Evening completion receipt/hash captured at Evening publication; the mutable final manifest cannot serve as its sole parent. |

## 3. Domain-driven boundaries

### Governed Thesis context

Owns ticker, direction, target, invalidation, horizon, option family/selection and lifecycle state. Existing pipeline authority remains here. The Evening thesis is immutable after publication; Morning produces a linked validation event. No report or chat message writes this context.

### Evidence context

Owns source identity, observed/as-of/fetched timestamps, data quality and hashes. Completed-session profile, price structure, VWAP/volume, options chain, macro packet and externally sourced news are separately identified. A later live quote is valid *later evidence*, not automatically a mismatch with an earlier Evening session.

### Interpreter Report context

Owns `ReportRequest`, `EvidenceDigest`, `Report`, `ReportSection`, `Claim`, `Contradiction` and `ReportRevision`. A report binds to one `run_id`, ticker, thesis version, phase and evidence cutoff. Its assertions are classified as `OBSERVED`, `DERIVED`, `INFERRED` or `UNKNOWN`, each with evidence references and freshness. It may expose tensions between authorities; it cannot resolve them by quietly rewriting the thesis.

### Conversation context

Owns `Question`, `Answer`, referenced report revision, cited evidence, provider metadata, cost and latency. One conversation is scoped to one ticker/report revision; a new Morning revision can be explicitly added as context. Platform persistence, not provider-side conversation state, is the durable record. No cross-ticker leakage.

### Lab Presentation context

Owns five-ticker selection, progress, report rendering and questions. It displays Evening thesis, Morning delta, quote/execution context and uncertainty as distinct concepts. It does not turn advisory report text into a trading action.

## 4. Workflow and contracts

1. The Lab shows candidates from one terminal, reconciled pipeline run. The human selects one to five distinct tickers. The UI shows each ticker's current thesis/contract state and an estimated maximum cost before explicit launch.
2. The service verifies run completion, source hashes, row identity, permissions and a per-ticker idempotency key. A failed ticker is isolated from the other four. It rejects mixed-run or unreconciled inputs.
3. For EOD review, the service reads a new immutable EOD evidence bundle: frozen thesis, signal sequence, profile/levels, options alternatives if present, macro advisory packet and provenance. Missing contract or current quote is represented explicitly and does not erase the share thesis.
4. For Morning review, it reads the accepted governed handoff plus its EOD parent. It emits a **delta**: validated, developed, unresolved or invalidated, with exact changed evidence and cause. It does not overwrite the EOD report.
5. A deterministic digest compiler selects high-value fields by domain, deduplicates values, caps size, records included/omitted field counts and required-field failures, and checks token budget before any provider call. It never disguises missing information as zero.
6. The narrative provider receives the digest and a versioned schema. The report is validated, reconciled to canonical numbers, and stored only on success. An unknown provider outcome is not automatically retried. Each ticker has bounded calls, timeout and cost accounting.
7. The Lab displays the complete report and an interactive GPT question pane. Questions use the frozen report, claims and evidence references; optional fresh news is a separately timestamped addendum requiring explicit refresh. Read-only deterministic functions may answer arithmetic/level questions. No broker writes or autonomous evidence acquisition.

### Report depth

Preserve the useful breadth of the historical Interpreter: executive thesis, macro/sector setting, market and trader profile, price structure and chart soul, gamma/options positioning, liquidity and activity, catalyst/news timeline, competing scenarios, risks/invalidation, and a final human review brief. The eight historical junior lenses (Macro, Gamma, Liquidity, Thesis, Chart, Options Flow, Risk, Verdict) may be represented as sections or specialist analyses; they do not get independent execution authority. If one call cannot fit the whole structured report, use bounded section calls and deterministic assembly rather than reducing analytical coverage.

### Crowd and hidden-liquidity questions

“Is the crowd near the wall?” requires a defined wall (strike/OI or profile level), current spot distance, activity/volume, expiry and timestamp. “Where are buyers/sellers hiding?” must separate **observed** trade/quote-depth evidence from **inference** using absorption, repeated rejection, volume, VWAP and profile behavior. Open interest and put/call ratios do not prove initiation or hidden orders. If order-book depth or prints are unavailable, the answer must say so and give a qualified inference with counter-evidence; it must not invent a location.

### Safety invariants

- One request is one ticker and one explicit run. Maximum five distinct tickers per human-launched batch; no automatic full-universe triage.
- Report and chat never mutate governed direction, contract, invalidation, lifecycle or capital permission.
- A 1–20-session thesis is not invalidated merely by an old execution quote. Quote usability remains a separate execution-context field.
- Every numeric and event claim cites a dataset/packet and as-of time. News/earnings assertions need source URL, event time and retrieval time; unavailable sources are disclosed.
- EOD and Morning revisions remain individually addressable and hash-bound. New evidence produces a revision/addendum, not a silent rewrite.
- Provider input/output, model/prompt/schema versions, token/cost accounting and validation outcome are durable. Raw sensitive credentials are never stored.
- A report is advisory even if it uses the words “buy”, “sell”, “GO” or “Verdict”; the Lab never maps those words into execution authority.

## 5. Test-driven acceptance contract

Write failing tests against these contracts **before** implementing each slice. Preserve existing governed resolver, Morning handoff, assessment and Lab tests. The tests below are acceptance criteria, not claims that the current code passes.

| ID | Test-first case | Acceptance evidence |
|---|---|---|
| T01 | Select 0, 1, 5 and 6 distinct tickers; duplicates and mixed runs | Only 1–5 unique, same-run selections launch; deterministic errors otherwise. |
| T02 | Select an EOD share thesis with no contract or current quote | Report remains possible, states option-expression gap; no invented contract. |
| T03 | Select a Morning ticker with altered bundle hash, direction or contract identity | Fail closed before model call; no report published. |
| T04 | Same request repeated after success and after unknown provider outcome | Idempotent retrieval after success; unknown outcome is held for reconciliation, not blindly retried. |
| T05 | EOD report then Morning validation with overnight gap | EOD stays frozen; Morning delta names actual spot/level/trigger changes and does not alter original thesis. |
| T06 | Later live quote than EOD date, or stale quote with valid swing thesis | Later quote is retained as later evidence; stale quote is execution context only, not automatic thesis invalidation. |
| T07 | Large PFE-like row and five-ticker batch | Per-ticker digest fits configured token/cost ceiling, preserves required facts, records omissions and never concatenates five full rows. |
| T08 | Missing critical numeric field, non-finite value, or contradictory source values | No fake zero; explicit `UNKNOWN`/contradiction and validation failure where required. |
| T09 | Report covers every required narrative section | Machine-readable sections and human-readable depth; no empty generic excerpt substituted for a section. |
| T10 | Model proposes changed CALL/PUT, strike, target or capital size | Validator labels proposal non-authoritative or rejects it; canonical row and action unchanged. |
| T11 | “Crowd near wall?” with and without OI/spot/profile evidence | Exact level, distance, time and provenance if available; otherwise qualified unknown. |
| T12 | “Where are buyers/sellers hiding?” without depth/trade prints | Explicitly says hidden orders are unobservable and limits inference to available proxies. |
| T13 | Earnings/news with old, future or unsourced events | Only point-in-time sourced events included; old/future/unsourced claims disclosed or rejected. |
| T14 | Ask a question in ticker A, then switch to B | No report/evidence/conversation leakage across ticker or run. |
| T15 | Source quote changes after report and user asks a follow-up | Answer cites frozen report; an explicit refresh creates a timestamped addendum, not a retroactive rewrite. |
| T16 | Publish report beside an existing Lab assessment overlay | Existing overlay status and authority fields remain byte-equivalent; report renders separately. |
| T17 | Provider 400, timeout, invalid JSON, partial batch failure | Durable per-ticker error; other tickers continue; no fabricated report or uncontrolled retry. |
| T18 | Web search or tool result tries to instruct model to change action/order | Treat source content as data; deny broker/order/capital tools; no authority change. |
| T19 | Replay frozen EOD and Morning fixtures | Stable structural/numeric claims and identical identities; language variability tolerated within schema. |
| T20 | Lab human review of representative CALL, PUT, invalidated, watch and missing-option cases | Trader can see what is observed, inferred, unresolved and execution-only without confusing report with permission. |

Required integration evidence: accepted Morning handoff and manifest reconciliation; EOD bundle completeness; one-to-five batch success/failure isolation; report/assessment coexistence; current Lab UI rendering; no screenshot dependency; no change to existing execution gate or broker boundary. Use fake provider responses for CI and a bounded, operator-approved live-provider canary only after deterministic tests pass.

## 6. Build sequence and release gates

1. **Contract and failing tests:** publish versioned EOD bundle, digest, report, claim, revision and conversation schemas; write T01–T20 fixtures including adversarial authority and chronology cases.
2. **EOD evidence/read model:** materialize hash-bound completed-session evidence without weakening the existing Morning contract. Test shares and long CALL/PUT routes, missing contract and source reconciliation.
3. **Compact report engine:** digest compiler, token/cost preflight, structured report generation, section validation, claim provenance and durable per-ticker state. Reuse the governed Interpreter resolver and report-writing capability; do not call legacy `/triage` or screenshot automation.
4. **Morning delta:** link accepted Morning handoff to its frozen EOD parent, preserve quote-versus-thesis distinction, and test gap/continuation/invalidation scenarios.
5. **Lab selection and display:** explicit maximum-five selection, progress and report pane, no overlay replacement, role labels and human review warnings. Prove parity of Lab row/bundle identities.
6. **GPT conversation:** scoped, durable questions/answers over the report and evidence; read-only arithmetic and sourced-event tools; adversarial isolation, injection and temporal tests.
7. **Verification and activation:** focused tests, existing Interpreter/Lab/Morning regression suites, stored-run replay, bounded provider canary, cost/latency measurements and human inspection of representative reports. Feature activation only after evidence and rollback manifest. No implicit Worker 3 or broker activation.

Release is **not** approved merely because an API produces prose. It requires complete sections, numeric provenance, identity reconciliation, no authority drift, successful Morning delta, no loss of existing Lab fields and usable manual-trading presentation. An isolated domain slice does not authorize provider or live workflow activation; implementation and activation require their respective test and release gates.

### First-slice verification — 22 September 2026

`tests/test_pi_lab_interactive_contract.py` was added before `domain/interpreter_review_selection.py`. The selection tests first failed because the module did not exist, then passed after the pure domain function was implemented. It preserves human order and source action (including BLOCK) without retriage; rejects zero/six/duplicate choices, missing ticker, mixed run and ambiguous Lab rows. EOD bundle tests remain strict expected failures pending the next slice. Focused run with the existing pretrade-focus and governed Interpreter handoff suites: **24 passed, 2 expected failures**. The run used an isolated writable pytest base directory because the default user temp directory was inaccessible in this sandbox. No provider, Lab server, broker, database or pipeline run was invoked.

### Second-slice verification — 22 September 2026

The two EOD bundle expected failures were made ordinary tests, and four more provenance/authority cases were added. All six failed before `contracts/interpreter_eod_review.py` existed. The pure builder now creates a deterministic advisory bundle with a full source-row hash, frozen-manifest hash reference, governed evidence references and optional selected contract; it rejects cross-run rows, malformed hashes and non-finite content. It never carries `capital_permission` into the report contract. Focused regression including pretrade focus, governed Interpreter handoff and handoff materializer: **38 passed**. This is not yet a published EOD snapshot: the completion receipt and immutable writer must be added at the actual successful EOD terminal boundary. The mutable `final_run_manifest.json` cannot be used as the sole frozen parent, and this contract must not be wired to Morning's contract-required materializer.

### Integrated offline build — 22 September 2026

The production EOD workflow now calls `pipeline_interpreter/interactive_snapshot.py` after closing EOD `run_meta`, before same-run Morning files can be rewritten. It freezes and hashes the EOD final manifest, run metadata and a gzip copy of the governed Lab book. The package is advisory and additive; failure is logged without changing the existing Evening execution decision. `load_eod_snapshot` verifies the package hashes and population. Nonfatal `DEGRADED` technical health is disclosed rather than silently discarding a reviewable thesis; `FAILED`/fatal sources are rejected.

`pipeline_interpreter/interactive_desk.py` adds localhost-only Lab APIs for one-to-five human-selected preview, per-ticker reports, persisted report retrieval and ticker/report-scoped questions. It uses the frozen EOD parent and accepted Morning handoff when available. Eight analytical lenses are required; oversized/invalid output, unverified or future news, mixed identity and cross-ticker questions fail controlled validation. Report and questions persist separately from the Lab overlay. `pipeline_interpreter/openai_desk_provider.py` uses the OpenAI Responses API with structured JSON and read-only web search. It is disabled until local key, model, verified model/tool prices and a per-ticker ceiling are configured. The Lab UI adds a separate Interpreter selection/report/question pane, leaving Worker 3 unchanged. Each report and follow-up question requires separate human confirmation. The report preview shows a deliberately conservative configured batch-cost bound, not a provider billing guarantee.

TDD: snapshot and service tests failed before their implementations. The integrated focused regression covering new contracts plus existing Evening focus, Lab authority and Morning handoff passed **109 tests and 3 subtests**. No external provider call was made. The current run cannot be retroactively treated as an EOD snapshot because its mutable same-run manifest and book were already advanced by Morning. Acceptance requires the next completed-session run to publish a frozen package, a real provider canary with an operator-selected model/key and verified pricing, and Lab browser review. These are release gates, not reasons to alter the governed trading authority. Current implementation does not yet prove claim-by-claim numeric reconciliation of free-form provider prose or a production-scale five-ticker latency bound; those must be assessed in the canary rather than assumed from schema validation.

## 7. Open decisions to settle before implementation

- Which current EOD file/manifest is the canonical parent for the new review bundle, and what terminal completion check binds it? Resolve with a stored-run fixture before coding the materializer.
- Which provider/model and maximum per-ticker cost/latency are operator-approved? Keep configuration explicit; do not infer pricing from old Worker 3 values.
- What event/news provider is authorised for current sourced catalysts? Until defined, the report must state that external catalysts were not verified rather than inventing them.
- Which legacy eight-section headings should be visible verbatim? Preserve analytical coverage regardless of naming.

## 8. References

Local implementation: `pipeline_interpreter/evidence_resolver.py`, `pipeline_interpreter/pipeline_interpreter_commands.py`, `pipeline_interpreter/pipeline_interpreter_engine.py`, `contracts/interpreter_handoff_materializer.py`, `contracts/lab_evidence_overlay.py`, `intelligence-lab/intelligence_lab.py`.

OpenAI API design references: [conversation state](https://developers.openai.com/api/docs/guides/conversation-state), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [function calling](https://developers.openai.com/api/docs/guides/function-calling), and [web search](https://developers.openai.com/api/docs/guides/tools-web-search). These describe mechanisms, not permission for a model to own AVSHUNTER trading authority.
