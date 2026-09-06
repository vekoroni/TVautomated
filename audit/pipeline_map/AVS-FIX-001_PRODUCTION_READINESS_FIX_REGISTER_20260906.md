# AVS-FIX-001 — Consolidated fix register: from current state to production-ready

**Date:** 2026-09-06
**Consolidates:** AVS-PRR-001 (readiness review), AVS-TST-QT-001 (14 defects), AVS-RCA-003 (9 defects, 5 decisions), AVS-THS-001 (thesis review), AVS-MVP-001 (trading boundary)
**Decision owner:** ACK
**Operating decision recorded (ACK, 6 Sep):** stabilise the platform first; Worker 3 testing follows Level 1. **Anthropic key rotated 6 Sep** (earlier deferral withdrawn); the credential is single-sourced in the User environment scope.

---

## 0. Two definitions of "production-ready", because they need different evidence

**Level 1 — Stable platform.** Every run is reproducible and traceable to committed code; every protection fires unconditionally; every decision-critical field is honest or named-absent; the audit fails on known-bad and passes on known-good; the four live transitions (completed session, premarket, RTH, after-hours) and the warm-cache rerun have each passed once on one code state; rollback is proven. This is AR-003 §12 / Rev 1.1 §19. **Workstreams 0–2.**

**Level 2 — Monetisable product.** The stable platform additionally ranks its monetisable set, recovers the design-caused losses RCA-003 measured, and has begun feeding outcomes into the ledger so that tiers and thresholds can be calibrated rather than asserted. **Workstream 3.**

**Worker 3** is a separate track (Workstream 4). It is not on the production path and its readiness does not gate Level 1 or Level 2.

ACK's stated order: Level 1 → Level 2 → Worker 3 testing.

---

## 1. Workstream 0 — Baseline, test integrity, process (do first; no run needed)

| ID | Fix | Source | Sev | Owner | Evidence of done |
|---|---|---|---|---|---|
| **W0.1** | **Commit the working tree and tag it.** Two commits if separable: (a) AVS-SD-003 gap fixes + adapter + DDD integration/closure; (b) the `domain/` package refactor (10 modules + `outcome_maturation.py`, `run_plan_store.py`, `session_authority_adapter.py`). If not separable in under an hour, one commit now and the separation later. Every run from now on records the tag in `run_meta.json`. | QT-D02, QT-D11 | **P0** | ACK / Codex | `git status --porcelain` empty; tag exists; next run's `run_meta.json` carries it |
| **W0.2** | **Fix the flag-default test.** Rewrite `test_all_new_features_are_disabled_by_default` to assert what production does: runtime profile v1.0.1 loads 8/9 on, AUTO off, `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` returns every flag to off. Add a test that fails if `contracts/dynamic_session_runtime_v1.json`'s hash changes without the release manifest changing. | QT-D01 | **P0** | Codex | Test names describe the true property; XML |
| W0.3 | **Bring `tests/msi/` into the acceptance matrix.** Fix or file `test_c07_one_minute_volume_uniformly_allocated_and_labelled` (a live Market Profile volume-allocation failure); retire the stale `*_NOT_IMPLEMENTED` absence test; run `test_logic.py` (budget-blocked in QT-001). | QT-001 D-04 | P1 | Codex / tester | Matrix includes `tests/msi/`; c07 green or a filed defect with root cause |
| W0.4 | **Documentation truth.** Correct DDD-closure claim 5 (the per-profile gate was never lowered; 0.90 is a new stage-level `min_usable_ratio`); document the 16 undocumented test edits with T2 classification; record backups for `dynamic_session_authority_v1.json` and `request_ledger.py`; retire `CLOSED OFFLINE` as a status; re-issue the P0 recertification with a run-artefact evidence column. | QT-D08, D09, D10; SD-003 §C8 | P2 | Codex (lead) | Corrected files in `audit/` |
| W0.5 | Pin the base interpreter behind `venv/` (currently a Windows Store Python) and record it in the release manifest. | QT-001 D-08 | P3 | ACK | `pyvenv.cfg` home is a pinned install |
| W0.6 | CLI hygiene: `--data-mode` is silently ignored on the dynamic path (warn or remove); `FINALISE` and `BUILD_THESIS` share a callback (separate, or document why not). | QT-D12, D13 | P3 | Codex | source + test |
| W0.7 | Arbitrate QT-D05 (independent TPO vs production POC/VAH by one bin). `tests/msi` `test_c06` indicates production is right; close with a written note. | QT-D05 | P3 | tester | note in `audit/` |

---

## 2. Workstream 1 — Data-integrity residuals (small code changes; ship with W0)

| ID | Fix | Source | Sev | Owner | Evidence of done |
|---|---|---|---|---|---|
| **W1.1** | `structural_target` published as `0.0` on 13 CALL rows → null at the producer; extend the `PROFILE_ZERO_AS_PRICE` audit rule to `structural_target` (and any other price-bearing decision field). | QT-D04 | P2 | Codex | 0 rows with `structural_target == 0.0`; audit rule fires on a fixture |
| **W1.2** | Suppress or map retired EIL telemetry so `EXECUTE_WITH_CAUTION` cannot appear beside a governed `STAND_DOWN` (TTEK). This clears MVP kill criterion 6. | QT-D06 | P2 | Codex | audit `fail_count = 0` genuine on the next run, or a waiver rule for no-authority stages |
| W1.3 | Write `monetisability_authority = ADVISORY_ONLY` on every Lab row, including `FAILED`/`DATA_MISSING`. | QT-D07, RCA-002 A4-03 | P2 | Codex | 294/294 non-null |
| **W1.4** | Profile stage guard semantics: provider `no_data` counts as **deferral**, not failure; `failure_ratio` counts only transport/entitlement failures; `min_usable_ratio` is the guard that stops the stage on a 100%-unusable outcome. Prove both on the next run. | QT-D03, AVS-PRE-001 EBC | P1 | Codex | `completed_profile_summary` shows `usable_ratio` and the guard's decision explicitly |
| W1.5 | Add `contract_dte` to the Lab book so MVP §4 "DTE ≥ 2 × hold" is evaluable from the book. | MVP-001 §4; QT-001 D | P2 | Codex | column present 294/294 where a contract exists |
| W1.6 | Per-horizon spread band becomes the authority (15% for `1_5d`), the flat 25% terminal gate becomes `min(band, flat)` or is removed. | RCA3-D07, DEC-3 | P3 | Codex | one rule; the 3 rows that leaked are blocked; test |

---

## 3. Workstream 2 — Live-cycle acceptance (runs ACK produces; tester verifies)

These are gates, not code. Each is done only when a run artefact shows it.

| ID | Gate | What must be true | Source | When |
|---|---|---|---|---|
| **W2.1** | **First Evening run on committed code** (Fri 4 Sep session; Mon 7 Sep is Labor Day so Monday night's run still uses Friday's session) | `run_meta.json` carries the tag and profile `054a76be…`; build receipt present and plan-hash-bound; one `pipeline_run_id` and one completed session across Discovery/profile/Vanguard/Options/book; **78-bar frames and `usable_ratio ≥ 0.90`** (or the guard stopping the stage, visibly); AG-01…AG-11 at zero/complete as on `151448`; RG-01…RG-09 unchanged; audit `fail_count` 0 genuine | QT-D14, PRR-001 A3–A5 | Mon 7 Sep evening |
| **W2.2** | **First Morning run on current code** (Tue 8 Sep premarket, over W2.1's accepted thesis) | validation events 1:1 with actionable rows; `execution_viability_*` from live quotes; Execution Gate ↔ Lab parity; handoff finaliser pass; Interpreter bundle reconciles; ledger counts; MVP kill criterion 5 clear; **this is also the first measurement of Morning attrition (RCA3-D09)** | PRR-001 A6; RCA-003 S7 | Tue 8 Sep |
| **W2.3** | **Same-session warm rerun** | option-chain physical requests = 0; `exact fresh dataset ≥ 1,200`; ledger reconciles; runtime materially lower — recorded | AVS-SD-003 AG-20 / G19 | Tue or Wed |
| **W2.4** | Premarket validation, RTH developing-profile validation, after-hours provider-confirmed finalisation — one each | Rev 1.1 G18B–D | Rev 1.1 §19 | Tue–Thu |
| W2.5 | **Exercise the rollback switch once**: `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` on a controlled Evening run; legacy path executes; protections still fire (they are unconditional) | QT-001 D-01 | any evening after W2.1 |
| W2.6 | Re-run the full matrix incl. `tests/msi/` on the committed code; 0 unexplained failures | W0.3 | with W0 |
| W2.7 | Release assessor records hash-bound artefacts for W2.1–W2.5; status reaches `READY_FOR_CONTROLLED_PROMOTION` | Phase 8 assessor | after W2.4 |

**Level 1 — stable platform — is declared when W0, W1 and W2.1–W2.7 are all evidenced.** Earliest realistic date: **Thu 11 – Fri 12 Sep**, assuming Monday's run is clean and one more RCA loop is not needed.

---

## 4. Workstream 3 — Monetisable product (after Level 1; measured, not asserted)

Ordered by measured recoverable value (RCA-003 §10) and by the THS-001 adopt list. None changes an authority; all are advisory-side or selection-side.

| ID | Fix | Source | Recovers / effect | Precondition | Owner |
|---|---|---|---|---|---|
| **W3.1** | **DEC-2 shadow replay**: re-run contract selection offline against the stored chains of `151448` (and W2.1's run) with δ ±0.10 and DTE ±7d, spread gate unchanged; count how many of the ~121 recovered candidates clear economics and the monetisability floor | RCA3-D06, DEC-2 | decides W3.2's value (ceiling +121/run) | none — offline | tester |
| **W3.2** | **Contract universe → filter → rank → repair → select.** Evaluate 3–5 strikes around target delta × 2–3 expiry buckets; rank; repair on the chain when the first choice fails the spread gate; terminal state `EQUITY_VALID_OPTIONS_NOT_MONETISABLE` with the best alternative named. Fixes the 43 mis-selections outright. | RCA3-D06, D08; THS-001 §3.1 | up to **+164 candidates/run (+56% book)** | W3.1 result; design note (an AVS-SD-004 slice) | Codex |
| **W3.3** | **Per-contract rejection taxonomy** and `contracts_tested`, `best_alternative`, `primary_rejection_reason`, `repair_attempted/result` on every Options row | THS-001 §3.1; RCA-003 §2 | instrumentation for W3.2 | none | Codex |
| **W3.4** | `monetisability_state_timevalue` as a **second advisory column** (Black–Scholes at target on the hold's final session, IV held, assumptions named); intrinsic floor stays as `monetisability_state` | RCA3-D05, DEC-1 | +10 relabelled MONETISABLE, +8 LIMITED per run; ends the false-negative-only bias | none | Codex |
| **W3.5** | **Tier field derived from governed columns** (THS-001 §4): Tier 1 / 2 / 3 / ARMED / WATCH / BLOCK with `tier_reason`; ARMED carries the named promoting condition (repair candidate, IV level, trigger). Advisory ranking in the Lab; never permission. Observe the daily distribution for two weeks; set no targets. | THS-001 §4 | ranks the 232; makes the recoverable set actionable | W3.3, W3.4 | Codex |
| W3.6 | **Measure IV-at-selection** vs Discovery-day IV and premium 3/5 sessions earlier on the monetisable rows; decide on an "early lane" from the number, not before | THS-001 §3.2 | decides a build | W2.1 run | tester |
| W3.7 | Stop-ladder root cause for the 167 `MISSING_GOVERNED_INVALIDATION` losses (upstream of the protection, which stays) | RCA-003 §10 item 5 | up to +167 upstream | none | Codex |
| W3.8 | Retry/defer the ~50 Discovery→Vanguard data rejects (all OTHER-direction; low value) | RCA-003 S6 | +50, non-directional | warm cache | Codex |
| W3.9 | **Ledger outcomes**: schedule and record 1/5/10/20-session underlying outcomes for every candidate (`outcome_maturation.py` exists — make it run nightly); restart journal capture for every manual trade | RCA-003 §9; SD-002 §10 | the only route to calibrated tiers/thresholds | W2.1 | Codex / ACK |
| W3.10 | Regime-rotation ("US Money Index") evidence stage — research design only, downstream of Discovery, own lineage, no ranking authority until W3.9 has outcomes | THS-001 §3.2, §5.5 | research | W3.9 | design |

**Explicitly not adopted:** a weighted 0–100 monetisation score with invented weights or gating thresholds; macro/GEX as a ranking input inside Discovery; any tier or score that grants or removes capital permission; target funnel counts set in advance.

**Level 2 — monetisable product — is declared when W3.1–W3.5 and W3.9 are evidenced on run artefacts** and the ledger has begun maturing outcomes. Realistic: week of 14 Sep for W3.1–W3.5; calibration is a matter of weeks of outcomes, not of build time.

---

## 5. Workstream 4 — Worker 3 (parallel, not gating; ACK's ordering: after Level 1)

| ID | Fix | Source | Owner |
|---|---|---|---|
| W4.1 | **DONE 6 Sep — key rotated, User-scope value replaced.** Credential single-sourced in the User environment (`os.environ`). **Correction to RCA-003/DEC-5:** `build_macro_json.py:559` (`anthropic.Anthropic()`, the manual pre-Evening macro step producing `macro_intelligence_latest.json`) also reads `ANTHROPIC_API_KEY` from the environment — so the key *is* a production dependency, via the macro build, not via the orchestrator. Same variable, same scope, covered by the rotation. Remaining: delete the `.env` line (inert under the orchestrator's `override=False` loader, but still a second source); delete the Claude Code transcript that echoed the old keys; confirm the old key is revoked in the Console; run `build_macro_json.py --dry-run` then a live macro build from a fresh shell as first use | RCA3-D04, DEC-5 | ACK |
| W4.2 | Transport: capture `error.type`/`error.message` into the receipt (no headers); don't consume the call budget on a non-2xx; record credential source + `sha256(key)[:8]` fingerprint | RCA3-D01, D02, D03 | Codex |
| W4.3 | Read-only source-mapping adapter from a frozen **post-closure** run (W2.1's) into the v2 evidence bundle, with hash verification | Worker 3 README "next slice" | Codex |
| W4.4 | Put the design of record (AVS-W3-SD-001) into the repository; decide the boundary against AR-003 §7.14 (no provider call behind the Interpreter surface) **before** any live-AI slice touches the Lab | QT-001 D-07 | ACK (design) |
| W4.5 | Shadow mode for 2–3 sessions: narratives written to a store nobody trades on; then a human-labelled semantic evaluation set before anything appears beside a `BUY_*` | THS-001; PRR-001 | ACK / Codex |

### Key rotation — closed

Key rotated 6 Sep. The deferral and its mitigations are withdrawn. Two consumers read `ANTHROPIC_API_KEY` from the User environment: Worker 3's transport and `build_macro_json.py`. Both are covered by the rotation; both require a fresh shell after `setx`.

---

## 6. Sequence and dates

| Day | Work | Result |
|---|---|---|
| **Sun 6** | W0.1 commit + tag; W0.2 flag test; W1.1–W1.6 code; W0.3 `tests/msi`; ~~W4.1~~ **done — key rotated** | committed, tested tree |
| **Mon 7** (US holiday) | W0.4 docs; W2.6 full matrix; **W2.1 Evening run** (Fri session) | first run on current code |
| **Tue 8** | **W2.2 Morning**; W2.3 warm rerun; W2.4 premarket + RTH; MVP §4 applied to Tuesday's Morning book | first Morning artefact; trading decision per AVS-MVP-001 |
| **Wed 9** | W2.4 after-hours finalisation; W2.5 rollback drill; W3.1 shadow replay (offline) | live gates closing; W3.2 sized |
| **Thu 11 – Fri 12** | W2.7 assessor; **Level 1 declared** if clean; W3.3/W3.4 start | stable platform |
| Week of 14 | W3.2, W3.5, W3.6, W3.9; Worker 3 W4.2–W4.4 | Level 2 build; Worker 3 testing begins per ACK's order |
| +2–3 sessions | W4.5 shadow | — |

---

## 7. Definition of done — unchanged from AVS-SD-003 §C8

An item is done when its gate count is met on a real run artefact with path, filter and three-direction split recorded; the release assessor holds a hash-bound artefact for it; its test exists and fails on the unremediated fixture; and RG-01…RG-09 are unchanged. `CLOSED` requires a run-artefact count. `CLOSED OFFLINE` is a different state and is never reported in the same column.
