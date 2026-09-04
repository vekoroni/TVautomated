# AVSHUNTER Pipeline Interpreter — GPT Agent Automation Options Paper

**Document status:** Solution options and impact assessment only  
**Date:** 29 August 2026  
**Scope:** Candidate extraction from the Intelligence Lab, evidence capture from the Intelligence Lab and Webull, and automated submission to the existing Pipeline Interpreter.  
**Out of scope:** Broker order entry, autonomous capital permission, changes to upstream signal generation, and replacement of the Intelligence Lab.

## 1. Executive decision

AVSHUNTER should not create a free-roaming GPT agent that decides which tickers are tradable and then operates Webull without controls. The recommended solution is a **hybrid deterministic workflow with a GPT interpretation agent**:

1. Deterministic code reads the governed Intelligence Lab output for one explicit pipeline `run_id`.
2. Deterministic rules select the eligible tickers and freeze the batch in a signed or hashed manifest.
3. A controlled evidence agent captures the required Intelligence Lab and Webull screens in read-only workspaces.
4. A GPT vision agent interprets the structured data and screenshots and returns a strict JSON result.
5. A deterministic reconciler checks identity, completeness and contradictions before publishing an Interpreter brief for human review.

This preserves the Intelligence Lab as the user-facing source of truth while using GPT where it adds value: visual interpretation, evidence synthesis, contradiction explanation and preparation of a consistent trade-review brief.

The existing repository already contains approximately two-thirds of this capability: batch discovery, Webull capture, evidence hashing, resumable state, structured Interpreter contracts and shadow publication. The principal gaps are source-of-truth alignment, Intelligence Lab screen capture, a GPT provider, fully automated screen verification, and production acceptance testing.

## 2. Current-state findings

### 2.1 What already exists

The existing Pipeline Interpreter automation provides:

- a resumable multi-ticker batch workflow;
- Webull ticker and timeframe navigation;
- capture of five chart timeframes and seven market-data views;
- ticker/screen verification hooks;
- privacy cropping and evidence hashing;
- structured request, evidence, analysis and result contracts;
- sovereign veto preservation and fail-closed validation;
- shadow-only output publication.

The current Webull evidence set is:

- 5-minute, 15-minute, 1-hour, 4-hour and daily charts;
- options chain and Greeks;
- tape and order book;
- opening and closing NOII/cross screens;
- short-interest screen.

### 2.2 Material gaps

1. **The candidate selector is using an obsolete contract.** It searches legacy `avshunter_signals_*.csv` before the governed `final_opportunity_book`/`lab_triage_view`, and it still requires `Verdict=GO`, positive EV and positive R:R. The current pipeline policy no longer gives EV or R:R capital authority.
2. **GO_LIMIT is omitted.** The latest governed opportunity book contains 35 `GO` and 40 `GO_LIMIT` rows marked tradeable. A GO-only selector sees 35 candidates; a governed execution-review lane should recognise all 75 while preserving their different permissions.
3. **There is no Intelligence Lab visual evidence adapter.** The package contains structured Lab JSON but not the Lab screenshots requested for human and GPT reconciliation.
4. **The live provider is Anthropic-specific.** A new GPT provider is needed for the OpenAI Responses API.
5. **Webull verification is not fully unattended.** Ticker acceptance can be automated, but screen-type confirmation still relies on attended callbacks.
6. **The automation is intentionally shadow-only.** It does not yet have production publication authority or the required acceptance history.
7. **Newest-file discovery is unsafe for governance.** A batch must bind to one explicit `run_id`, source path and SHA-256, not whichever file has the newest modification time.
8. **Capturing every screen for every tradeable ticker is inefficient.** Seventy-five candidates multiplied by twelve Webull screens would create 900 Webull images before Lab screenshots. A staged funnel is needed.

## 3. Source-of-truth and eligibility contract

The selector must be ordinary deterministic code, not an LLM prompt.

### 3.1 Authoritative input

Use the successfully published `final_opportunity_book_<run_id>.csv` for the selected pipeline run. `lab_triage_view_<run_id>.csv` may be used as a compatible read projection, but it must carry the same `run_id` and reconcile to the opportunity book.

The batch manifest must record:

- pipeline `run_id` and mode;
- source file path, size and SHA-256;
- pipeline completion/health manifest path and hash;
- selection-policy version;
- selected ticker, direction and selected contract symbol;
- Lab verdict, tradeable flag, rank and reason;
- creation timestamp and evidence expiry policy.

### 3.2 Recommended lanes

| Lane | Deterministic condition | Automation treatment |
|---|---|---|
| Primary | `lab_tradeable=true` and `lab_verdict=GO` | Eligible for full evidence capture, ranked and capped |
| Limited | `lab_tradeable=true` and `lab_verdict=GO_LIMIT` | Eligible, but retain limited/manual-review label |
| Probe | Explicit governed probe status | Disabled by default; separate opt-in batch |
| Excluded | BLOCKED, CONTRACT_REPAIR, MANUAL_REVIEW or non-tradeable | Do not navigate Webull; record exclusion reason |

EV, R:R and macro are context fields only. They may be displayed and interpreted, but they must not silently remove a candidate that the governed Lab contract marks tradeable. Conversely, GPT must not promote an excluded ticker.

Additional deterministic prerequisites should include:

- successful required pipeline stages for the same `run_id`;
- no fatal data-health flag;
- resolved direction;
- selected contract present and internally consistent;
- contract data state available;
- no known ticker/contract identity mismatch.

## 4. Solution options

### Option A — Minimal extension of the existing shadow workflow

Patch the existing Lab batch selector, add one Intelligence Lab screenshot, and replace the current provider with GPT.

**Advantages:** Fastest and lowest code change; reuses capture, hashing, retry and Interpreter contracts.  
**Limitations:** Retains legacy file-discovery assumptions, a heavy twelve-screen capture set and partially attended verification.  
**Use:** Short shadow trial or proof of concept.  
**Assessment:** Viable, but not the preferred production endpoint.

### Option B — Governed deterministic orchestrator plus GPT analyst — recommended

Create a versioned selection contract and batch manifest, add dedicated Lab/browser and Webull/desktop capture adapters, use GPT only for multimodal interpretation, and validate all outputs deterministically.

**Advantages:** Strong lineage, resumability, auditable failures, exact run/ticker/contract binding, controlled cost and low hallucination exposure.  
**Limitations:** Requires several new adapters and an acceptance phase.  
**Use:** Production target.

### Option C — GPT computer-use agent controls both applications

A GPT computer-use agent visually navigates the Intelligence Lab and Webull, captures screens and submits the package.

**Advantages:** Flexible against screens with no API or stable DOM.  
**Limitations:** UI drift, focus errors, higher latency/cost, weaker reproducibility and unacceptable proximity to Webull order-entry controls unless heavily sandboxed.  
**Use:** Shadow experimentation only; not recommended for production capture.

### Option D — Structured-data-first Interpreter with no visual capture

Send only the governed Lab contract and directly acquired market data to GPT.

**Advantages:** Cheapest, fastest and most reproducible.  
**Limitations:** Does not meet the requested screenshot/audit workflow and loses visual chart/order-flow context.  
**Use:** Possible long-term efficiency lane, not the immediate solution.

## 5. Recommended target architecture

```text
Completed morning pipeline
        |
        v
Final opportunity book + run health manifest
        |
        v
Deterministic Selector Agent
  - validates run_id and health
  - applies governed GO/GO_LIMIT policy
  - ranks and caps the batch
  - writes immutable candidate manifest
        |
        v
Evidence Orchestrator
  +------------------------+-------------------------+
  |                                                  |
  v                                                  v
Lab Browser Capture                              Webull Desktop Capture
  - exact run_id/ticker                            - read-only workspace
  - summary/overview                               - exact ticker/contract
  - trade setup/options                            - charts/options/flow
  - structured JSON                                - privacy crop
  +------------------------+-------------------------+
                           |
                           v
Evidence Validator
  - hashes, freshness, completeness, identity and schema
                           |
                           v
GPT Interpretation Agent
  - structured data + images
  - strict JSON schema
  - evidence-linked observations
                           |
                           v
Deterministic Reconciler / QA Agent
  - no permission escalation
  - contradiction and missing-data checks
  - REVIEW_READY / HUMAN_REVIEW / DATA_DEFECT
                           |
                           v
Pipeline Interpreter output + Intelligence Lab backlink
                           |
                           v
Human trade decision
```

The OpenAI Responses API can accept text and image inputs and return structured JSON, which fits the interpretation stage. JSON Schema Structured Outputs should be used rather than free-form prose so the existing Interpreter can validate every response. See the official [Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create) and [model/vision capabilities](https://developers.openai.com/api/docs/models).

## 6. Agent responsibilities and hard boundaries

### Selector agent — deterministic

- Reads one explicit, healthy run.
- Chooses governed GO/GO_LIMIT rows.
- Applies rank/cap policy.
- Never infers permission from screenshots.
- Prevents API/UI work for tickers already excluded upstream.

### Evidence agent — deterministic automation with visual verification

- Opens exact Lab ticker and Webull symbol.
- Confirms displayed ticker, contract and screen type.
- Captures and hashes evidence.
- Has no broker trading permissions.
- Fails the ticker, not the entire batch, on mismatch.

### GPT interpretation agent

- Receives the frozen structured candidate record and approved images.
- Describes chart structure, contract fit, wall/trigger context, liquidity observations and contradictions.
- References evidence IDs for every material claim.
- Cannot change direction, contract, Lab verdict, position permission or capital permission.
- Returns `INDETERMINATE` when evidence is missing or contradictory.

### Reconciler agent — deterministic

- Confirms output schema and evidence references.
- Detects direction, contract, trigger and WBS contradictions.
- Preserves sovereign upstream flags.
- Publishes only review states; never places an order.

## 7. Evidence design

### 7.1 Intelligence Lab capture

Use browser automation with stable DOM selectors and a fixed viewport. The URL or application state must bind to `run_id` and ticker. Capture at minimum:

1. **Lab overview:** verdict, campaign, direction, selected contract, trigger, WBS, position permission and data-health/provenance status.
2. **Trade setup/options:** contract symbol, strike, expiry, premium, Greeks, IV/HV, liquidity and trigger levels.
3. **Optional provenance view:** required stage completion, timestamps and source lineage if the UI exposes it.

The screenshot is visual evidence; the structured record remains the computational source of truth. OCR must not be used to recreate values already present in the CSV/JSON.

### 7.2 Webull capture

Use a dedicated read-only Webull layout with order ticket panels closed or inaccessible. Validate ticker and selected contract before every capture. Retain the existing full evidence set for finalists, but use progressive capture:

- **Pass 1:** daily and 4-hour chart plus Lab overview for the top-ranked candidates.
- **Pass 2:** 1-hour, 15-minute and 5-minute charts for candidates that remain coherent.
- **Pass 3:** options, Greeks, tape, order book, cross/NOII and short-interest evidence only for the final shortlist.

Recommended operational cap: shortlist the top 5–10 candidates per run, with full capture for approximately 3–5. The cap must be configuration, not a hidden prompt rule.

## 8. GPT output contract

The GPT result should be a versioned JSON object containing:

- `run_id`, `ticker`, `direction`, `contract_symbol`;
- `evidence_snapshot_hash` and referenced evidence IDs;
- `interpretation_status`: `REVIEW_READY`, `HUMAN_REVIEW`, `DATA_DEFECT`, `INDETERMINATE`;
- thesis confirmation/contradiction observations;
- trigger-primary and trigger-quality observations;
- WBS/wall proximity and break-state observations;
- contract/liquidity observations;
- timeframe alignment summary;
- missing or stale evidence list;
- contradiction list;
- concise human review checklist;
- model ID, prompt version, schema version and response ID.

The model must not emit `BUY`, `SELL`, position size or capital permission as authoritative fields. If those words appear in narrative evidence, the reconciler must treat them as commentary only.

## 9. Safety, operational and governance controls

- Run Webull capture under an operating-system account with no order-entry capability where feasible.
- Use an allowlist of Webull screens and block order, modify and cancel controls.
- Bind every artifact to `run_id + ticker + contract_symbol + evidence_snapshot_hash`.
- Continue after a per-ticker failure; do not publish partial evidence as complete.
- Keep API keys in environment/secrets storage and redact account data before upload.
- Set OpenAI data-retention configuration according to the organisation's policy.
- Pin a model snapshot/configuration during acceptance testing.
- Maintain full request/response audit logs without storing unnecessary personal/account information.
- Require a visible human confirmation before any downstream brokerage action.

Computer-use models exist for the Responses API, but their direct use for Webull navigation is not the recommended production path because deterministic navigation and verification are easier to test and constrain. See the official [computer-use model documentation](https://developers.openai.com/api/docs/models/computer-use-preview).

## 10. Implementation plan

### Phase PI-GPT-0 — Contract alignment

- Make `final_opportunity_book` the first and authoritative source.
- Define GO, GO_LIMIT, probe and excluded lanes.
- Remove EV/R:R as selector gates.
- Define batch and GPT output schemas.
- Produce a read-only reconciliation report against the latest run.

**Exit:** candidate counts and exclusions reconcile exactly to the governed book.

### Phase PI-GPT-1 — Deterministic selector and immutable batch

- Implement explicit `run_id` input.
- Validate run-health manifest and source hash.
- Rank/cap candidates and persist resumable state.
- Prove dropped tickers cause no later capture/API work.

**Exit:** repeated runs produce the same candidate manifest and no cross-run mixing.

### Phase PI-GPT-2 — Intelligence Lab capture adapter

- Add stable ticker/run navigation and DOM assertions.
- Capture overview and options/trade-setup evidence.
- Add screenshots to evidence-package schema v2.

**Exit:** 100% exact ticker/run match across representative Lab trials.

### Phase PI-GPT-3 — Webull capture hardening

- Replace attended screen checks with deterministic UI assertions plus visual fallback.
- Enforce a read-only workspace and order-control denylist.
- Add progressive capture and per-ticker recovery.

**Exit:** no ticker/screen mismatches and no interaction with trading controls in trial logs.

### Phase PI-GPT-4 — GPT provider and Interpreter integration

- Implement an OpenAI Responses API provider.
- Submit structured Lab data and selected images.
- Enforce JSON Schema output and evidence citations.
- Add retries for transport/schema failures without changing the frozen evidence snapshot.

**Exit:** schema-valid, reproducible Interpreter artifacts with no permission escalation.

### Phase PI-GPT-5 — Shadow acceptance

- Run at least five representative pipeline batches, including GO, GO_LIMIT, missing evidence, stale evidence, contract mismatch and UI failure cases.
- Compare GPT conclusions with a human-reviewed gold set.
- Measure completeness, false assertions, contradiction detection, capture failures, duration and cost.

**Minimum acceptance:** at least 95% complete/schema-valid packages, 100% identity and sovereign-field preservation, zero brokerage-control interactions, and explicit failure status for every incomplete case.

### Phase PI-GPT-6 — Attended production activation

- Publish review-ready Interpreter packages to a production output area.
- Add a backlink/status indicator in the Intelligence Lab.
- Keep execution manual and retain a one-switch rollback to shadow mode.

**Exit:** the trader can start in the Lab, open one coherent evidence package, and make the decision without searching multiple folders.

## 11. Impact assessment

### Positive impact

- One governed source for candidate selection.
- Visual and structured evidence reconciled to the same ticker, contract and run.
- Faster human review of a small, ranked shortlist.
- Clear separation between signal authority, visual interpretation and execution authority.
- Auditable reasons for exclusions, capture failures and contradictions.
- Reuses substantial existing Interpreter and capture functionality.

### Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| UI layout changes | Capture failure or wrong screen | Stable selectors, screen allowlist, visual assertion, fail closed |
| Cross-run file mixing | Incorrect evidence | Explicit run manifest and SHA-256 binding |
| GPT hallucination | False interpretation | Structured source values, evidence IDs, schema, deterministic reconciler |
| Excessive screenshots | Slow/costly run | Progressive capture, rank cap, full evidence only for finalists |
| Webull order interaction | Capital risk | Read-only workspace, denylist, human-only execution |
| Stale contract/image | Invalid comparison | One evidence snapshot timestamp and identity/freshness checks |
| Legacy selector policy | Missing valid candidates | Final-book authority; GO and GO_LIMIT lanes; EV/R:R advisory only |

## 12. Final recommendation

Approve **Option B** and deliver it by extending the current `pipeline_interpreter/automation_v2` and `capture_v1` components, not by starting a separate system.

The first build should be PI-GPT-0 and PI-GPT-1 only: align the selector to the governed Intelligence Lab book and create an immutable batch manifest. Until that is correct, screenshot or GPT automation would efficiently process the wrong candidate set.

After contract alignment, add Lab capture, harden Webull read-only verification, integrate GPT through the Responses API and complete shadow acceptance. Production activation should publish a human-review package back to the Intelligence Lab; it should not place trades or grant capital permission.

