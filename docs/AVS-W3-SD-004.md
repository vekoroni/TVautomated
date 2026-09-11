# AVS-W3-SD-004 — W3-ME3 governed macro ticker context

Document status: approved design; implementation recorded in Section 22
Design version: 1.0.0
Date: 2026-09-11
Bounded context: Worker 3 advisory analysis
Trading authority: none
Provider activation: unchanged

## 1. Executive decision

Implement a new immutable `macro_ticker_context_v1` evidence contract between
the run-frozen Interpreter macro packet and Worker 3. The contract will expose
only the macro evidence applicable to one exact ticker and its already-governed
direction. It will improve explanation and monitoring without changing the
ticker thesis, selected contract, lifecycle, execution permission, capital
permission, position size or pipeline population.

Worker 3 must not browse `dropbox/macro`, select a latest file, or ingest every
archived narrative. The production source remains the single run-frozen
`interpreter/interpreter_macro_context.json` packet created by W3-ME2. The new
projector converts that packet and the exact attested Intelligence Lab row into
small typed evidence for one ticker.

This design is compatible with the current pipeline. It is additive to
`market_environment_v1`, `trade_plan_snapshot_v1` and `analyst_evidence_v1`.

## 2. Business outcome

For every ticker presented to Worker 3, the analyst should be able to answer:

1. Which current macro themes actually apply to this ticker?
2. Does sector rotation provide a tailwind, headwind, mixed evidence or no
   mapping for the existing governed direction?
3. Which event guards or forward observations should a human monitor?
4. How do rates, oil, volatility, credit, breadth, GEX and capital
   concentration transmit to this ticker?
5. Which sources are stale, missing, conflicting or unverified?
6. What changed from the prior frozen assessment, when a valid prior exists?

The output is explanatory evidence. It cannot answer whether a trade is GO,
change CALL to PUT, reject a candidate, choose an option contract, or size a
position.

## 3. Scope

### 3.1 In scope

- A pure domain contract for ticker-conditioned macro evidence.
- Deterministic projection from a verified run-frozen macro packet.
- Exact ticker, sector, industry and governed-direction applicability.
- Ticker themes, event guards, sector rotation and macro transmission.
- Source timestamps, hashes, freshness, quality and conflicts.
- Explicit stale, missing and unverified states.
- Worker 3 evidence-bundle attachment.
- Typed evidence coverage in Worker 3 reports.
- Refresh comparison through the existing evidence-hash mechanism.
- Tests, release metadata and run-level observability.

### 3.2 Out of scope

- Direct reads from `dropbox/macro` by Worker 3.
- New macro-data collection or external API calls.
- Changes to Discovery, Vanguard, Options Intelligence, Morning Gate or the
  Execution Gate authority model.
- Macro-based ticker rejection or direction reversal.
- Macro-based option-contract selection.
- Feeding the derived human macro thesis back into the model.
- Model training, outcome calibration or autonomous execution.
- Provider release activation or a change to provider pricing limits.

## 4. Validated as-is position

### 4.1 Active macro sources

| Source | Current role | Design treatment |
|---|---|---|
| `macro_intelligence_latest.json` | Consolidated macro contract containing regime, rates, liquidity, volatility, GEX, sector information and embedded sidecars | Freeze once per run; primary packet source |
| `bond_macro_state.json` | Yield curve, Treasury, credit and bond context | Use embedded copy and preserve nested source date/stale flag |
| `avshunter_us_money_index.json` | Participation, leadership, cross-asset transmission, oil, risk appetite and forward triggers | Use normalized embedded copy with unverified-count disclosure |
| `avshunter_macro_enrichment_delta.json` | Themes, event guards, normalized catalyst records and ticker exposure | Use embedded ticker-advisory index; never treat narrative as authority |
| `auction_calendar.csv` | Auction events | Use only valid nonblank embedded rows; current blank row is unavailable |

The active macro file already embeds augmented bond and enrichment contracts
and a normalized US Money Index under `extras`. W3-ME2 freezes that consolidated
state in the run directory. Worker 3 therefore does not require a second file
read or a second source of truth.

### 4.2 Sources that must not enter current evidence directly

- `thesis/macro_thesis_*.md` is a derived human narrative. Supplying it beside
  its source JSON would double-count the same evidence and encourage circular
  confirmation.
- `avshunter_us_money_indexold*.json` is a legacy contract and is not eligible
  for current evidence.
- `Archive/*.json` contains historical enrichment snapshots. These may support
  a later deterministic change calculation, but they are never current
  per-run evidence and must not be bulk-injected into a model prompt.

### 4.3 Existing implementation seams

- `contracts/interpreter_macro_context.py` creates
  `interpreter_macro_context_v1`, strips prohibited authority fields and
  creates the existing exact-ticker advisory index.
- `contracts/lab_control.py` already carries macro ticker alignment, themes,
  event guards, directional pressure, bond context and USMI fields into
  `lab_signal_book_v2`.
- `worker3/market_environment.py` projects four global advisory domains:
  equity participation, rates, oil and risk appetite.
- `worker3/integration/avshunter_source.py` loads the frozen packet once and
  attaches `market_environment_v1`, but currently exposes only a small subset
  of ticker macro fields as independent typed observations.
- The entire selected Lab row is also attached as a native document. That is
  useful for qualitative traceability but is not a substitute for typed,
  separately citable facts.

### 4.4 Confirmed gap

Useful ticker-specific information exists in the frozen packet and Lab row but
is not consistently represented as a bounded typed Worker 3 observation. A
model may see it nested inside a large document, but numeric reconciliation,
coverage reporting, exact citations and change detection are weaker than they
are for normal `Observation` records.

## 5. Domain-driven design

### 5.1 Ubiquitous language

- **Macro source**: one source document embedded in the frozen macro packet.
- **Market environment**: global cross-asset state shared by every ticker in a
  run, represented by `market_environment_v1`.
- **Ticker macro context**: macro evidence deterministically mapped to one
  ticker and its pre-existing direction.
- **Applicability**: whether a theme or transmission channel is relevant to the
  ticker; it is not a trading verdict.
- **Alignment**: advisory relationship to the existing thesis, one of
  `TAILWIND`, `HEADWIND`, `MIXED`, `NEUTRAL` or `UNMAPPED`.
- **Event guard**: a future observable condition requiring reassessment; it is
  not an execution gate.
- **Evidence quality**: availability and reliability of a source at its own
  timestamp.
- **Governed direction**: direction already decided upstream; immutable within
  this bounded context.

### 5.2 Bounded contexts and ownership

| Bounded context | Owns | Must not own |
|---|---|---|
| Macro acquisition/build | Source retrieval, normalization and consolidated macro contract | Ticker direction or capital permission |
| Run evidence | Frozen packet, run/session identity, source hashes and cutoff | Reinterpretation of source data |
| Macro ticker applicability | Exact ticker/sector mapping and advisory transmission | Candidate filtering or contract selection |
| Worker 3 analysis | Evidence-bound explanation, contradictions and monitoring considerations | Trading authority or new market facts |
| Intelligence Lab | Human-facing display of governed and advisory evidence | Silent recomputation of macro logic |

The anti-corruption layer is the `macro_ticker_context_v1` projector. Raw
source vocabulary must not leak directly into Worker 3 authority or identity.

## 6. Target data flow

```text
dropbox/macro and dropbox/marketdata
  -> macro builder and governed sidecar normalizers
  -> macro_intelligence_latest.json
  -> dynamic orchestrator pins macro_snapshot.json once
  -> W3-ME2 materializes interpreter_macro_context_v1
       - source manifest and hashes
       - global market data
       - normalized USMI
       - ticker advisory index
       - forbidden authority fields removed
  -> exact lab_signal_book_v2 row
       - ticker, sector, industry
       - governed direction and thesis identity
  -> pure macro ticker projector
  -> macro_ticker_context_v1
  -> one TICKER-scoped analyst_evidence_v1 Observation
  -> Worker 3 provider request / report / refresh comparison
  -> Intelligence Lab advisory display
```

The projector performs no filesystem or network access. The source bridge owns
the single verified read and passes immutable Python mappings into the domain
function.

## 7. Source precedence and mapping

### 7.1 Source precedence

1. Run and session identity: `run_meta_v2.dynamic_plan`.
2. Macro evidence: the verified run-frozen
   `interpreter_macro_context_v1` packet only.
3. Ticker, sector, industry, thesis and direction: the exact attested
   `lab_signal_book_v2` row.
4. Ticker themes and guards: `ticker_advisories[ticker]` in the frozen packet.
5. Sector alignment: the packet's normalized sector map and USMI sector
   advisory, evaluated against the existing governed direction.

Mutable Dropbox files, filename dates, directory modification time and a
different ticker's row are never fallback sources.

### 7.2 Field mapping

| Target field/group | Primary source | Fallback | Rule |
|---|---|---|---|
| ticker/sector/industry | Exact Lab row | None | Exact normalized identifiers only |
| governed direction | Lab `governed_direction` | None | Read-only conditioning input |
| ticker roles/themes/guards | Packet `ticker_advisories[ticker]` | Empty with `NO_TICKER_MAPPING` | Exact ticker key; no fuzzy matching |
| sector alignment | Packet sector rotation plus normalized USMI advisory | `UNMAPPED` | May describe thesis relationship, never reverse direction |
| equity participation | `market_environment_v1` | `UNAVAILABLE` | Reference existing global snapshot; do not recalculate |
| rates transmission | Packet bond/core rates plus ticker sector/industry | Global rates state | Preserve nested source timestamp and stale flag |
| oil transmission | USMI oil state plus ticker sector/industry/themes | Global oil state | No inference of company exposure without a mapped record |
| risk appetite | Existing global volatility/credit state | `UNAVAILABLE` | Investor intent must not be claimed |
| GEX/positioning context | Frozen core GEX status and Lab wall/GEX fields | `UNAVAILABLE` | State source mode and quality; no dealer-intent claim |
| monitoring conditions | Mapped event guards and forward triggers | Empty | Human review observations, not gates |
| conflicts | Packet conflicts plus contradictory mapped records | Empty | Preserve all bounded conflict codes |
| quality | Source manifest and nested source quality | `UNKNOWN` | Never infer freshness from packet creation time |

Conditional labels such as `DAL_IF_OIL_STAYS_HIGH` must not be parsed by Worker
3 as ticker identities. Only normalized catalyst records already mapped to an
exact ticker may enter ticker-specific evidence.

## 8. `macro_ticker_context_v1` contract

### 8.1 Required shape

```json
{
  "schema_version": "macro_ticker_context_v1",
  "authority": "ADVISORY_ONLY",
  "run_id": "20260911_...",
  "session_date": "2026-09-10",
  "evidence_cutoff_utc": "2026-09-11T...Z",
  "ticker": "NVDA",
  "sector": "XLK",
  "industry": "SEMICONDUCTORS",
  "governed_direction": "CALL",
  "source_packet_id": "MACRO:...",
  "source_packet_sha256": "...",
  "source_fingerprint": "...",
  "applicability": {
    "state": "APPLICABLE",
    "alignment": "TAILWIND",
    "reason_codes": ["SECTOR_LEADERSHIP", "TICKER_THEME_MATCH"]
  },
  "roles": ["BENEFICIARY"],
  "themes": ["AI_HARDWARE_LEADERSHIP"],
  "event_guards": ["LEADERSHIP_REVERSAL"],
  "transmission": {
    "equity_participation": "SELECTIVE_CONCENTRATION",
    "rates": "HEADWIND",
    "oil": "NEUTRAL",
    "risk_appetite": "MIXED",
    "volatility": "CONTAINED",
    "gex": "AVAILABLE_CONTEXT_ONLY"
  },
  "monitoring_conditions": [],
  "data_quality": {
    "status": "PARTIAL",
    "stale_sources": [],
    "missing_sources": [],
    "unverified_metric_count": 0
  },
  "source_items": [],
  "contradictions": [],
  "omitted_counts": {},
  "candidate_retained": true
}
```

### 8.2 Invariants

- `schema_version` is exactly `macro_ticker_context_v1`.
- `authority` is exactly `ADVISORY_ONLY`.
- `run_id`, `session_date`, ticker and governed direction exactly match the
  evidence bundle identity and run contract.
- Source packet ID, SHA-256 and fingerprint are mandatory and revalidated.
- `candidate_retained` is always `true`.
- Missing numeric values remain `null` or are represented by an unavailable
  typed observation; they never become zero.
- Every supplied theme, guard and alignment reason is traceable to a source
  item and hash.
- Future evidence relative to the bundle cutoff fails projection.
- Stale evidence is retained with a stale quality state; staleness alone never
  removes a candidate.
- No field may grant execution or capital authority.

### 8.3 Prohibited keys

The projector must recursively reject or remove:

- `capital_permission`
- `execution_permission`
- `final_action`
- `final_verdict`
- `trade_go`
- `position_size` and `position_size_pct`
- `selected_contract` and `selected_contract_symbol`
- `direction_override`, `direction_vote` and `governed_direction_override`
- any equivalent field that attempts to mutate upstream identity or authority

`governed_direction` is allowed only as an immutable conditioning attribute.

### 8.4 Size and cardinality

- Canonical serialized context: maximum 16 KiB per ticker.
- Maximum themes: 8.
- Maximum event guards: 8.
- Maximum monitoring conditions: 12.
- Maximum contradictions: 12.
- Maximum source items: 8.
- Text reason: maximum 320 characters per item.

Ordering is deterministic. If valid upstream evidence exceeds a limit, the
projector uses documented source priority and lexical tie-breaking and records
the exact omitted count by category. Silent truncation is prohibited.

## 9. Applicability logic

### 9.1 Exact ticker mapping

Use the frozen packet's normalized `ticker_advisories` dictionary with the
canonical uppercase ticker. No substring, alias, company-name or conditional
label matching is permitted.

### 9.2 Sector and industry mapping

Use the Lab row's governed sector/ETF and industry fields. Sector evidence may
be used when exact ticker evidence is absent, but the contract must disclose
`SECTOR_ONLY_MAPPING`. An absent mapping produces `UNMAPPED`, not `NEUTRAL`.

### 9.3 Thesis-conditioned alignment

Alignment describes the relationship between macro evidence and the existing
direction:

- `TAILWIND`: mapped evidence supports the existing direction.
- `HEADWIND`: mapped evidence opposes the existing direction.
- `MIXED`: material mapped evidence exists on both sides.
- `NEUTRAL`: mapped evidence explicitly indicates limited transmission.
- `UNMAPPED`: insufficient applicability evidence.

The projector does not create a new direction. CALL and PUT use the same
mapping rules with symmetric inversion only where a source mapping explicitly
defines bullish/bearish transmission. Narrative sentiment alone cannot perform
that inversion.

### 9.4 Event guards

An event guard is rendered as a condition to reassess evidence, never as a
veto or entry trigger. Guard records must carry event identity, source time,
applicability and state. Expired guards remain historical evidence only and do
not appear in current monitoring conditions.

## 10. Time, freshness and uncertainty

Three times remain distinct:

1. Source observation time: when the underlying fact was measured.
2. Source availability time: when AVSHUNTER could have known it.
3. Packet creation time: when the run-frozen context was materialized.

Packet creation time must never make an old source appear fresh. For example,
a bond packet generated on 10 September may still contain yield-curve evidence
dated 8 September. The context must report the nested yield-curve date and its
stale flag.

Quality states:

- `AVAILABLE`: required source fields present and not marked stale/unverified.
- `PARTIAL`: useful evidence with known missing or unverified components.
- `STALE`: applicable evidence exists but its source policy marks it stale.
- `CONFLICTING`: applicable sources materially disagree.
- `INSUFFICIENT_DATA`: no defensible applicability conclusion.

Quality is evidence, not authority. All states retain the candidate.

## 11. Contradiction handling

- Preserve the existing packet conflict codes.
- Add bounded ticker-specific contradictions when two applicable mapped records
  disagree.
- Do not average categorical conflicts into a false consensus.
- Use explicit precedence only for source identity, not for selecting the more
  convenient market conclusion.
- Worker 3 must explain both sides and their source quality.
- A contradiction cannot change the governed direction or pipeline verdict.

Examples include stale `BEAR_STEEPENING` versus a fresher flattening reading,
sector leadership versus weak breadth, and contained VIX versus weakening
credit. Each retains its own timestamp and quality.

## 12. Failure policy

| Failure | Required behaviour |
|---|---|
| Frozen packet missing | Attach unavailable context and reason; retain ticker |
| Packet/session mismatch | Mark packet invalid for Worker 3; retain ticker |
| Packet hash mismatch | Fail macro context closed; retain ticker |
| Ticker absent from advisory index | Produce `NO_TICKER_MAPPING`; use disclosed sector-only mapping if available |
| Sector absent | Produce `UNMAPPED`; do not infer from company name |
| Source stale | Retain evidence and mark stale |
| Source unverified | Retain with count and source limitation |
| Conflicting sources | Preserve contradiction list and mark `CONFLICTING` |
| Non-finite numeric value | Mark unavailable; never serialize NaN or zero |
| Context exceeds size contract | Fail that context projection with a durable reason; never silently truncate |
| One ticker context fails | Isolate that advisory context; do not abort peer tickers or pipeline |

Because macro is optional advisory evidence, a macro-context failure must not
turn an otherwise valid source-bridge entry into a ticker `DATA_EXCEPTION`.
Worker 3 can proceed while clearly stating that ticker macro context is
unavailable.

## 13. Security and authority

- All macro narratives are untrusted data, never instructions.
- No macro source can enable tools, network calls or provider fallback.
- The provider request remains constrained by the existing Worker 3 output
  schema and evidence citation rules.
- No source file path outside the run directory is exposed to the provider.
- The context contains source identifiers and hashes, not credentials.
- Macro cannot grant capital, select contracts or alter pipeline state.
- Provider activation and cost controls remain governed by AVS-W3-SD-003.

## 14. Integration design

### 14.1 New domain module

Add `worker3/macro_ticker_context.py` containing immutable dataclasses and a
pure function similar to:

```python
project_macro_ticker_context(
    *,
    packet: Mapping[str, Any],
    packet_sha256: str,
    market_environment: MarketEnvironmentSnapshot,
    lab_row: Mapping[str, Any],
    run_id: str,
    session_date: str,
    evidence_cutoff_utc: str,
) -> MacroTickerContext
```

The function performs no IO and returns canonical JSON-compatible data plus a
deterministic context hash.

### 14.2 Source bridge

Update `AvshunterSourceBridge` to:

1. Load and verify the macro packet once per run, as it does now.
2. Retain the parsed immutable packet alongside `market_environment_v1` for
   in-process projection.
3. Project one ticker context from the exact Lab row.
4. Attach one TICKER-scoped `Observation`:
   - field: `macro_ticker_context`
   - unit: `structured_json`
   - calculation version: `macro_ticker_context_v1`
   - source hash: frozen packet SHA-256
5. On optional macro failure, attach an unavailable observation and a bounded
   reason code without converting the ticker to `DATA_EXCEPTION`.

### 14.3 Integration contract

Advance `contracts/worker3_integration_v1.json` from 1.2.0 to 1.3.0 and add:

```json
{
  "macro_ticker_context": "macro_ticker_context_v1"
}
```

No authority or runtime activation flag changes are permitted in this release.

### 14.4 Report coverage

Update Worker 3 detailed-report coverage so the `CONTEXT` section explicitly
recognizes `macro_ticker_context`. The report should display:

- alignment and applicability;
- applicable themes and event guards;
- transmission channels;
- source dates and quality;
- conflicts and omitted counts;
- the statement `ADVISORY_ONLY — DOES NOT CHANGE THE GOVERNED THESIS`.

The existing native Lab document remains attached for audit traceability, but
the new typed context becomes the preferred citation for ticker macro claims.

### 14.5 Refresh behaviour

The existing `compare_evidence` mechanism will detect the context hash change.
Refresh reports must explain which bounded fields changed. A later enhancement
may add `macro_context_change_v1`, but W3-ME3 does not need to read Archive
files or create a second history database.

## 15. Observability

Record the following run-level diagnostics without affecting pipeline health:

- `macro_ticker_context_requested`
- `macro_ticker_context_available`
- `macro_ticker_context_partial`
- `macro_ticker_context_stale`
- `macro_ticker_context_conflicting`
- `macro_ticker_context_unmapped`
- `macro_ticker_context_invalid`
- `macro_ticker_context_bytes_total`
- `macro_ticker_context_omitted_items_total`
- counts by exact-ticker, sector-only and unmapped applicability

Reconciliation invariant:

```text
requested = available + partial/stale/conflicting + unmapped + invalid
```

Categories must be mutually exclusive at the top-level status even when the
context carries multiple detailed quality flags.

## 16. Test strategy

### 16.1 Domain tests

1. Valid CALL ticker with exact mapped tailwind.
2. Valid PUT ticker with the same evidence and symmetric thesis relationship.
3. Headwind does not change direction or discard candidate.
4. Exact ticker mapping cannot leak another ticker's themes or guards.
5. Sector-only mapping is disclosed.
6. Missing ticker and sector produce `UNMAPPED`, not neutral.
7. Missing numeric evidence remains unavailable, not zero.
8. Stale bond evidence preserves nested date and stale status.
9. Unverified USMI metrics remain counted and disclosed.
10. Conflicting sources remain separate and mark `CONFLICTING`.
11. Future source availability fails projection.
12. Forbidden authority fields cannot survive serialization.
13. Reordered equivalent inputs produce the same context hash.
14. Material evidence changes produce a different context hash.
15. Size and cardinality limits use deterministic disclosed compaction.

### 16.2 Source-bridge tests

1. Packet is read once for a multi-ticker batch.
2. Every prepared ticker receives exactly one context observation.
3. Macro absence leaves valid ticker preparation intact.
4. Packet/session and hash failures are disclosed without peer failure.
5. Context observation identity matches run, session, ticker and direction.
6. Existing option-chain, quote, profile and trade-plan evidence is unchanged.
7. Restart reproduces the exact evidence and job hashes.

### 16.3 Report and provider tests

1. Context claims require the typed context evidence ID.
2. Numeric facts must match exact typed observations.
3. Model cannot use a native document to invent a missing typed number.
4. Macro headwind cannot become a direction reversal or NO_GO instruction.
5. No raw Dropbox or Archive path appears in a provider request.
6. Input-size ceilings and provider call ceilings remain unchanged.
7. Prior assessment refresh reports context changes without reusing old values
   as current facts.

### 16.4 Full regression

- Complete Worker 3 suite.
- Interpreter macro advisory-handoff suite.
- Intelligence Lab opportunity-book and manifest suite.
- CALL/PUT direction-governance tests.
- Provider activation, evidence binding and cost-limit tests.
- Static scan for prohibited authority fields.

## 17. Acceptance criteria

W3-ME3 is accepted only when:

1. All planned focused and full regression tests pass.
2. CALL and PUT behaviour is symmetric and neither is filtered by context.
3. Two different tickers cannot receive each other's mapped evidence.
4. Mutable Dropbox and Archive files are absent from Worker 3 runtime reads.
5. Every context binds the frozen packet ID, hash, run and session.
6. Stale, missing, conflicting and unverified evidence is visible.
7. No missing value is converted to zero.
8. Macro cannot change direction, contract, lifecycle, execution permission,
   capital permission or position size.
9. Repeated preparation is idempotent.
10. Run-level population diagnostics reconcile exactly.
11. A controlled completed run produces the expected context for every Worker
    3 worklist ticker or a disclosed optional-context status.
12. The final run manifest records the W3-ME3 contract version and aggregate
    diagnostics without making them pipeline-fatal.

## 18. Build and implementation sequence

### Phase 1 — Contract and fixtures

- Add immutable domain classes and enumerations.
- Create representative frozen fixtures from current macro v1, bond v2.1,
  USMI v2 and enrichment v1.2 shapes.
- Add forbidden-key, identity, time and size invariants.

Gate: pure contract tests pass with no IO.

### Phase 2 — Deterministic projector

- Implement exact ticker and sector applicability.
- Reuse `market_environment_v1` rather than recomputing global states.
- Add quality, conflict and disclosed compaction logic.
- Validate CALL/PUT symmetry and idempotent hashes.

Gate: domain and adversarial tests pass.

### Phase 3 — Source bridge integration

- Preserve one packet read per run.
- Attach typed ticker context without altering existing evidence.
- Add optional failure observations and aggregate counters.
- Advance the integration contract to 1.3.0.

Gate: bridge, evidence-hash and restart tests pass.

### Phase 4 — Report and refresh integration

- Add typed macro context coverage and display.
- Prefer typed context citations over the native Lab document.
- Confirm existing refresh comparison records material changes.

Gate: response validation, semantic review and report tests pass.

### Phase 5 — Regression and controlled production acceptance

- Run all focused suites and the complete Worker 3 regression pack.
- Perform static authority and direct-file-read scans.
- Execute one normal completed pipeline run after W3-ME2/W3-ME3 deployment.
- Prepare Worker 3 evidence from that explicit run without activating the
  provider.
- Reconcile counts, hashes, source dates and representative CALL/PUT contexts.
- Run a separately approved one-ticker provider canary only if the controlled
  provider release already authorizes it.

Gate: all acceptance criteria pass and rollback evidence is recorded.

## 19. Rollback

The change is additive. Rollback consists of:

1. Restore Worker 3 integration contract 1.2.0.
2. Stop attaching `macro_ticker_context_v1` observations.
3. Retain `market_environment_v1`, `trade_plan_snapshot_v1` and native Lab
   evidence unchanged.
4. Preserve already-created Worker job and assessment records as historical
   evidence; never rewrite them under the old contract.

Rollback triggers include cross-ticker leakage, authority-field survival,
session/hash mismatch being accepted, evidence-hash instability, unreconciled
population counts or regression failure in existing Worker 3 functionality.

## 20. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Duplicate macro facts inflate confidence | One source packet, typed provenance and no derived thesis input |
| Narrative changes governed direction | Immutable direction and recursive prohibited-key checks |
| Stale source appears current | Preserve nested source time and quality, never packet time as freshness |
| Cross-ticker evidence contamination | Exact key matching plus evidence-bundle ticker invariant |
| Oversized provider request | 16 KiB context cap with deterministic disclosed compaction |
| Archive creates temporal leakage | No runtime Archive reads; future comparisons use prior frozen evidence |
| Macro failure blocks valid trade | Optional advisory failure policy and `candidate_retained=true` |
| Lab and Worker show different context | Both derive from the same frozen packet and exact Lab row |

## 21. Final architectural judgement

Approve W3-ME3 for implementation under this design. It closes a genuine
evidence-coverage gap without creating another data store or granting macro new
authority. The key architectural decision is that Worker 3 reviews governed
information derived from the macro folder, not the folder itself.

No pipeline behaviour, provider release, database or production output is
changed by this design document.

## 22. Implementation record — 2026-09-11

Phases 1–4 are implemented in production code. The implementation adds the
pure `macro_ticker_context_v1` domain model and reconciliation service, exact
ticker/sector projection in the read-only Worker 3 source bridge, typed report
coverage, integration contract 1.3.0, an atomic run-level diagnostics artifact,
and non-fatal final-manifest disclosure.

Validation completed:

- 114/114 Worker 3 regression tests passed.
- Focused domain, bridge, orchestrator and final-manifest tests passed.
- A read-only projection over run `20260909_071646` reconciled 235/235 Lab rows
  with zero invalid contexts and no candidate filtering.
- The production-shape check identified and corrected false propagation of
  packet-wide warnings as ticker-specific conflicts. Raw conflicts remain
  visible; only materially mixed applicable mappings elevate a ticker to
  `CONFLICTING`.

No provider release, call ceiling, capital authority or database schema was
changed. Phase 5 production acceptance remains pending one new completed
pipeline run created after this implementation; that run must publish the
macro ticker context diagnostics and the refreshed final manifest before the
feature is formally signed off.

## 23. Independent pre-run correction record — 2026-09-11

An independent adversarial review found four handoff defects after the initial
implementation: supplied Lab rows were not compared with the hashed persisted
book, the final manifest did not verify that Lab hash, negative aggregate
diagnostics could reconcile arithmetically, and generic source `STALE` states
were not propagated. It also identified two incomplete acceptance requirements:
source-level future timestamps and deterministic report visibility.

The implementation now:

- rejects supplied Lab rows that differ from the exact hashed Lab book;
- recomputes and verifies the Lab-book SHA-256 in the final manifest;
- requires non-negative and fully reconciled status/applicability diagnostics;
- propagates `STALE` from every canonical source manifest entry;
- rejects future packet, source-manifest and nested source observation times;
- uses the frozen packet creation time for idempotent rematerialisation; and
- visibly renders the typed ticker macro context with the mandatory
  `ADVISORY_ONLY — DOES NOT CHANGE THE GOVERNED THESIS` statement.

The focused correction suite passed 34/34. The consolidated Worker 3 and
pipeline-boundary pack passed all 151 unique tests; seven cases initially hit
an inaccessible shared pytest temporary directory and passed when rerun in an
isolated writable temporary directory. No provider activation, authority,
candidate filtering, database schema or external-data call changed.

The remaining Phase 5 gate is operational rather than code-level: one fresh
completed evening run must demonstrate the corrected hashes, counts, source
quality and report output on production-shaped artifacts.
