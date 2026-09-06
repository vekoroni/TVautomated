# AVS-IMP-SD-003-001 — Implementation instruction: AVS-SD-003 cycle 1 + W2-0 adapter fix

**Issued:** 2026-09-04
**Implementer:** Codex (integration lead + up to three bounded specialists per AVS-SD-002 §17)
**Independent tester:** Claude Code, separately (AVS-TST-SD-003, to follow) — Codex does not self-certify
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`, interpreter `C:\Python314\python.exe`
**Start point:** the `pre-tidy-20260904` tag (commit 1 of AVS-OPS-001). If that tag does not exist, stop: commit the working tree as-is and tag it first. No implementation begins on an untagged tree.
**Design authority:** `audit\pipeline_map\AVS-SD-003_GAP_ELIMINATION_20260904.md` (C1–C8), evidence in `audit\pipeline_map\AVS-RCA-002\`, adapter defects in `audit\preflight\AVS-PRE-001_20260904_075820\AVS-PRE-001_RESULT.md` §4.
**Goal today:** a release candidate proven on a Vanguard-onward replay of run `20260904_004338`'s cached inputs, then a **no-capital** Morning Gate rehearsal over the replayed book during the US session. No trading authority is claimed by anything in this instruction.

---

## 1. Decisions that bind this build — do not reinterpret

**D1 — Protections are unconditional. No flag, boolean, config key or package field may sit in front of them.** The fail-closed Vanguard verdict, the invalidation precondition, the null-target guard, the lineage mapping and the audit rules all run on the plain `--evening` path with every `AVSHUNTER_*` variable unset. A "single governed activation source" is fine for *acquisition*; it must have no effect on *protection*. If, after your change, unsetting every environment variable and deleting `config\msi_runtime.json` still leaves Vanguard capable of emitting `ALIGNED` on a null-POC profile, the build has failed regardless of what the tests say.

**D2 — Fail closed on authority, not existence.** An unusable profile makes a row `NOT_EVALUATED` with `ready_to_trade=False`, null POC/VAH/VAL, zero auction uplift and zero auction confidence. The row is **not** dropped. Book size is reported, not asserted.

**D3 — No new state names.** Use `NOT_EVALUATED` (auction), `INSUFFICIENT_DATA` / `UNAVAILABLE_PROVIDER` (profile lifecycle, `contracts\dynamic_session_contract.py`), and `DataExceptionReason` members for reason codes. Do not introduce `PROFILE_UNAVAILABLE` or any other alias. AR-003 §7 exists because of alias drift.

**D4 — Record activation state.** Write the resolved value of every `AVSHUNTER_*` flag and of `config\msi_runtime.json` into `run_meta.json` for every run, so a closure can never again claim a stage ran when it did not.

**D5 — Two-level closure.** Your claim sheet has a `run_artefact_evidence` column. A cell that says "tests pass" is empty for closure purposes. A cell that says "`vanguard_signals_enriched_<replay_id>.csv`, filter `auction_state=='ALIGNED' & poc.isna()`, count 0 (CALL 0 / PUT 0 / OTHER 0)" closes the item.

---

## 2. Scope — exactly these items, nothing else

### Cycle 1 (AVS-SD-003 §C6, W1-1 … W1-10 and W1-12)

| # | Item | Files (exclusive owner) | Closes |
|---|---|---|---|
| W1-1 | Vanguard fail-closed unconditional: `market_profile_contract_required` defaults `True` at `input_schema.py:211`, `orchestrator_adapter.py:180`, `auction_synthesizer.py:59`; explicit `False` raises `VanguardInputError`; Layer-2 uplift in `edge_detector.py:552-554` and the `auction_conf * 0.40` term both require non-null POC | `vanguard\` (Agent 2) | AG-01…AG-04 |
| W1-2 | Same default in `scripts\run_vanguard_from_packages.py:761` | Lead | AG-01 |
| W1-3 | Invalidation-presence precondition **at arming** in `scripts\avshunter_options_intelligence.py`: `invalidation_state != AVAILABLE` ⇒ `STAND_DOWN`, reason `INVALIDATION_MISSING`; OTHER direction stays `NOT_APPLICABLE` unchanged | Agent 1 | AG-05, AG-06 |
| W1-4 | Null/non-finite `structural_target` guard **before** the direction branch at `:5462` — both CALL `:5464` and PUT `:5467` — returning a governed `UNRESOLVED_EXCEPTION` record with `STRUCTURAL_TARGET_UNRESOLVED`; the generic exception handler must never publish interpreter text into `stand_down_reason` / `trigger_status_reason` | Agent 1 | AG-09, AG-10 |
| W1-5 | `eod_candidate_engine.py`: no `capital_permission=EOD_CANDIDATE_ONLY`, `capital_authorization_state=EOD_CANDIDATE_ONLY` or `eod_candidate_authorized=True` without invalidation; `NO` / `NOT_AUTHORIZED` with reason `INVALIDATION_MISSING` instead | Agent 1 | AG-07 |
| W1-6 | EOD projection emits `contract_bid_size`, `contract_ask_size`, `contract_quote_quality`, `selected_quote_timestamp_utc` (already built at `:879`, never projected) and the macro lineage identity fields | Agent 1 | AG-11, AG-12 |
| W1-7 | `contracts\lab_control.py`: add the missing `first(sig, …)` assignments for every `execution_viability_*` name at `:256-265`; widen `:2065` to accept `contract_quote_timestamp_utc` / `quote_timestamp_utc`; Lab `options_research_permission` = `NOT_EXECUTABLE` without invalidation | **Lead only** | AG-08, AG-11, AG-14 |
| W1-9 | `handoff_contract_audit.py:476-484`: zero-row artefact ⇒ `EMPTY_BY_DESIGN` **only when** the dropoff audit corroborates that nothing satisfied the shadow mask; otherwise `EMPTY_UNEXPECTED` = FAIL; a missing shadow book may not score more leniently than an empty one | Agent 3 | AG-15 |
| W1-10 | Eight semantic rules in `_semantic_contract_audit` (and the UAT generator): `INSUFFICIENT_DATA & ALIGNED`; POC `== 0.0` where profile unusable; `ARMED & invalidation MISSING`; `EOD_CANDIDATE_ONLY` without invalidation; executable Lab row without invalidation; interpreter text in trader fields; allow-listed Lab field 0/N while its source is >0/N; Options↔Lab direction hash mismatch. **Ships in the same commit as W1-9.** | Agent 3 | AG-16 |
| W1-12 | Tests T-02a…T-02e, T-03a…d, T-04a…b, T-05a…d, T-06a…d, T-09a…c, T-12a…b, T-13a per AVS-SD-003 §C5.2. Fix the two tests in §C5.1 that passed while the defect was live. | Agent 3 | all |

**Deferred, do not touch:** W1-8, W1-11, W1-13, W2-1 (flag split), W2-2, W2-3 (cache identity), W2-4 (legacy branch deletion), W2-5, W2-6, every dynamic flag, AVS-OPS-001 commits 2–3.

### W2-0 — MarketData stock-candle adapter (pulled forward from cycle 2; precondition for AG-19)

File: `canonical_data\marketdata_stock_candles.py`, plus `scripts\build_completed_market_profiles.py`. Owner: Agent 1, after W1-3…W1-6. Evidence: `AVS-PRE-001_RESULT.md` §4, `01_responses.jsonl`.

| Defect | Change | Test |
|---|---|---|
| **D1 (P0)** `from`/`to` sent as UTC `…Z` (`:135-137`); provider reads wall-clock as America/New_York and returns 13:30–15:55 ET — 30 of 78 bars, `s="ok"` | Send the window as naked Eastern wall-clock: `f"{session_date}T09:30:00"` / `T16:00:00` (or bare dates as the legacy caller at `backfill_timeseries_into_packages.py:299-304` does). **And** add a coverage gate in `build_completed_market_profiles.py`: `coverage_ratio < 0.95` ⇒ profile lifecycle `PARTIAL_SESSION`, never `COMPLETED_SESSION`, and no `MarketProfileEvidence.usable=True` | T-W20a: request params for a normal session contain no `Z` and no offset; T-W20b: a 30-bar frame for a 78-bar session cannot be published as `COMPLETED_SESSION` |
| **D2 (P1)** `no_data` arrives as HTTP 404; `urlopen` raises before the `no_data` branch at `:46-48` — dead code | Catch `urllib.error.HTTPError`, parse the body; `s="no_data"` ⇒ empty frame with reason `NOT_YET_OBSERVABLE` (future session) or `TICKER_INACTIVE` / `UNAVAILABLE_PROVIDER` (no data for a past session). Any other 4xx/5xx ⇒ `UNAVAILABLE_PROVIDER` | T-W20c: a 404 `{"s":"no_data"}` yields an empty frame with the reason code, not an exception |
| **D3 (P2)** `session_segment` stamped from the request (`:78`), never observed | Derive per bar from the timestamp against `session_bounds(session_date)`: `PREMARKET` / `REGULAR` / `AFTER_HOURS` | T-W20d: a 144-bar `extended=true` frame labels 18 / 78 / 48 |
| **D4** rate-limit headers unread | Record `x-api-ratelimit-limit/-remaining/-consumed/-reset` on the observation and pass `consumed` to the request ledger as the cost | T-W20e: ledger row carries the consumed credits |
| **D5** HTTP status unread; 203 = cached | Record status on the observation (`provider_http_status`); do not act on it | T-W20f: 203 recorded, frame accepted |

**Systemic-failure threshold (design point from EBC).** In `build_completed_market_profiles.py`, a per-ticker `no_data` is a **deferral** with a reason code, not a failure; `AVSHUNTER_PROFILE_MAX_FAILURE_RATIO` counts only transport/entitlement failures (`UNAVAILABLE_PROVIDER`). Population identity still holds: `input = processed + excluded + deferred + exceptions`.

**Real-response fixture — mandatory.** Copy three records from `audit\preflight\AVS-PRE-001_20260904_075820\01_responses.jsonl` into `tests\fixtures\marketdata_candles\`: the P1/SPY 30-bar misparse, the R2/SPY 78-bar correct frame, and one 404 `no_data`. T-W20a–c run against these bodies, not against a mock that returns what the test expects. The Phase 3 pack passed 10/10 against mocks while D1 was live; that must not be possible again.

---

## 3. Working rules

- **Backups before every item**, Phase 0 pattern: `backups\avs_sd_003_<item>_prechange_<YYYYMMDD_HHMMSS>\` with a SHA-256 `MANIFEST.json`. The Phase 2 lapse (files edited without a backup) does not recur.
- **Ownership** per AVS-SD-002 §17.1: only the lead edits `intelligent_orchestrator.py`, `morning_gate.py`, `contracts\lab_control.py` and shared schemas. **`intelligent_orchestrator.py` is not edited in cycle 1** except for the D4 `run_meta.json` activation record, which the lead makes as a separate, minimal change. No two agents edit one file concurrently; Agent 1's items are sequential.
- **No edits to surviving tests except the two named in §C5.1.** If an existing test fails after your change, either the test asserted retired behaviour (cite the AR-003 clause that retired it and change the assertion to the governed one, at equal or greater strength) or your change is wrong. Record every test edit in the claim sheet with its classification. Phase 8's 25 reconciliations are under independent audit; do not add to the pile silently.
- **Three directions on every rule and every count:** CALL / PUT / OTHER (STRANGLE, UNRESOLVED, null). RG-07 — OTHER rows stay `STAND_DOWN` / `NOT_APPLICABLE` and never reach the Lab — is the most likely accidental casualty of W1-3/W1-5; test it explicitly.
- **Isolated pytest processes** per file (the `vanguard/scripts` shadowing makes single-process collection invalid).
- **No flag is set in any shell that touches production paths.** Flag-on behaviour only via monkeypatched unit tests.
- **Commit per item** on a branch `avs-sd-003-cycle1` from `pre-tidy-20260904`; merge to main only after §4 step 3 passes. Commit messages name the item and the AG gate.

---

## 4. Proof sequence — in this order

**Step 1 — Offline replay of the AVS-SD-003 gates (AG-01…AG-17).** Replay from the pinned, cached inputs of `20260904_004338` — Vanguard onward, reusing last night's canonical equity history and MarketData option-chain datasets by exact identity so that **zero** physical provider requests occur (verify from the request ledger; if any physical request fires, stop and explain). Produce every stage artefact under a new run ID `<replay_id>` clearly marked `REPLAY_OF=20260904_004338` in `run_meta.json`. Report each gate with the artefact path, filter and three-direction count, exactly as `AVS-RCA-002\A_counts.csv` does.

Required results: AG-01 0 (was 1,068); AG-02 0 (1,551); AG-05 0 (43); AG-07 0 (13); AG-08 0 (23); AG-09 0 (36); AG-11 256/256 or named-absent; AG-15 `EMPTY_BY_DESIGN` ×2; **AG-16: the corrected audit replayed against the *original, unremediated* `20260904_004338` artefacts must report `fail_count ≥ 6` with zero shadow-book contribution** — an audit that cannot fail on a known-bad run closes nothing. Regression gates RG-01…RG-09 unchanged.

**Step 2 — Morning Gate rehearsal, no capital.** During the US session (14:30–21:00 UK), run `--morning` over `<replay_id>`'s book with all flags off. Purpose: first exercise of the post-build Morning path — live underlying price, exact contract quote, `execution_viability_*` from live bid/ask, Execution Gate `final_action`, handoff finaliser, Lab refresh, Interpreter manifest. Report: rows entering, rows with live quote, viability pass/fail/review counts (CALL/PUT), `final_action` distribution, finaliser result, and whether `execution_viability_state` now reaches the Lab (AG-11 on the Morning path). **Nothing from this run is a trade.** `morning_execution_permission` is inspected, not acted on.

**Step 3 — Full matrix.** The complete top-level production suite in isolated processes (expected 877 + 1 skipped per `dynamic_phase8_full_regression_20260903.xml`, plus the 23 QA/RCA, plus the 165 dynamic-session pack, plus the new tests). Zero unexplained failures; every explained failure classified as in §3.

**Step 4 — Claim sheet and closure.** `audit\pipeline_map\AVS-SD-003_CYCLE1_CLAIM_20260904.json` and `_CLOSURE_20260904.md` with, per item: files changed, backup path, tests added/edited (with classification), **run_artefact_evidence** (path + filter + count), and status from {`IMPLEMENTED — REPLAY VERIFIED`, `IMPLEMENTED — AWAITING LIVE RUN`, `BLOCKED`}. **No item is `CLOSED`.** `CLOSED` is assigned by the tester after AG-18 (tonight's real `--evening`) shows it firing.

---

## 5. Hand-off

Finish by printing: the branch and merge commit SHA; `<replay_id>` and its physical-request count (must be 0); the AG-01…AG-17 table with three-direction counts; the AG-16 fail-count on the unremediated run; the Morning rehearsal summary; the full-matrix totals; the count of test edits by classification; and the list of items `BLOCKED` with the reason.

Then stop. Tonight's `--evening` (AG-18) is run by ACK, and the independent tester takes it from there.
