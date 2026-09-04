# MSI v1.1 — Independent Test Summary

**Date:** 2026-08-30 | Design: AVS-SD-MSI-001 v1.1 | Implementer: Codex | Independent test engineer: this pack
**Full detail:** `10_findings_register.md` (68 test IDs), `20_design_inconsistencies.md` (10 items), `07_run_artefacts.md` (Section 7), `00_preflight.md` (gating facts)

## Counts by status, per category

| Category | VERIFIED/PASS | PARTIAL | FAILED/NOT_IMPLEMENTED | NOT_ACTIVATED | Total |
|---|---:|---:|---:|---:|---:|
| Functionality (F) | 6 | 6 | 3 | 0 | 15 |
| Logic (L) | 3 | 4 | 5 | 0 | 12 |
| Computation (C) | 9 | 2 | 1 | 0 | 12 |
| Flow (W) | 12 | 4 | 3 | 1 | 20 |
| Regression (R) | 3 | 4 | 2 | 0 | 9 |
| **Total** | **33 (48.5%)** | **20 (29.4%)** | **14 (20.6%)** | **1 (1.5%)** | **68** |

Section 7 (run-artefact verification) is separately tracked and not included in the 68-test count above: it is **entirely precondition-failed** (no MSI-active run exists). Of its 17 §20 acceptance-criterion cross-references, 3 resolve PASS offline (criteria 2, 8, 17), 1 resolves FAIL offline (criterion 12, via R-07), and the remaining 13 are BLOCKED pending a live run.

## What this pack found, in one paragraph

The core deterministic calculation layer (Market Structure profile/lifecycle/repair-percentage/acceptance-counter formulas, VWAP, bin width, evidence determinism, parameter-range compliance) is **thoroughly and rigorously correct** — every computation test in that space passed with hand-verified arithmetic. Foundational plumbing (worklist blocking, cached-rerun zero-refetch, atomic handoff publication, overlay allow-listing, provider-isolation, macro non-authority, dropped-ticker suppression, identity-minting discipline, session-clock correctness, OCC vector normalisation) is also solid. But the **quote-change comparison feature required by §8.8 — the mechanism that would let a trader see "how has this contract's bid/ask/spread moved since Morning Gate" — is entirely unimplemented**, confirmed independently from four different angles by four different agents (C-02, L-01/L-02/L-09, W-04/W-05/W-07). Two other propagation paths silently drop data the design requires to survive: option contract sizes never reach the selected-contract or Lab-row layer (W-01), and underlying NBBO sizes are computed then discarded before reaching any canonical field (F-08). The Lab UI itself does not display several of the §11-required field groups at all (R-05). And independent re-execution of the existing regression suites found 6 new failures the implementer's own verification-evidence section did not disclose (R-07), including one the implementer characterized as "unrelated fixture drift" that this pack's causality probe found inconclusive rather than exculpatory — the implementer's own claim is UNVALIDATED, not confirmed.

## FAILED items, ranked by which §20 acceptance criterion they block

**Criterion 10 — "Interpreter quote changes use two registered snapshots of the same exact OCC contract and match the Lab overlay" — most severely blocked, zero implementation exists.**
- C-02 (§8.8 comparison arithmetic: NOT_IMPLEMENTED)
- L-01, L-02 (§8.8 comparison_status/BASELINE_ZERO: NOT_IMPLEMENTED)
- W-04 (quote-change-suppression half: NOT_IMPLEMENTED)
- W-05 (§9.3 Interpreter refresh-execution loop steps 5–8: NOT_IMPLEMENTED — the fail-closed guard alone is not sufficient to satisfy this criterion)
- W-19 (§16.2 request coalescing/lock/budget: NOT_IMPLEMENTED — a supporting requirement for the refresh loop)

**Criterion 1 — "MarketData option bid and ask sizes reach CDS, Morning Gate, Lab and Interpreter without field loss" — blocked at two of four hops.**
- F-08 (underlying NBBO sizes dropped before any canonical field)
- W-01 (option contract sizes dropped between CDS and the Lab row)

**Criterion 7 — "Contract replacement always refreshes the replacement and recomputes every contract-dependent field" — the refetch/recompute half works; the "no false price change" half does not.**
- W-04 (same as above; the cross-contract price-change suppression this criterion also requires has no implementation)

**Criterion 9 — "Lab and Interpreter match on run, thesis, direction, contract, quote snapshot and lifecycle for every ticker" — blocked by a structural book-identity split.**
- R-06 (Lab's live book stays `lab_signal_book_v2`; `lab_signal_book_v3` exists only as a separate handoff artefact)
- W-01 (sizes missing from the Lab row is itself a match-content gap)

**Criterion 12 — "All existing authority, OLM, Morning, Lab and CDS regression suites pass" — directly failed.**
- R-07 (6 new failures across 4 of 10 independently re-run suite groups, not disclosed by the implementer)

**Criterion 8 — "Structure evidence is deterministic, versioned, quality-labelled and non-authoritative" — determinism/versioning/authority all hold; the quality-labelling half has real gaps.**
- L-07 (`TRADE_LEVEL_CONFIRMED` never emitted; no independent coarse-bar detection)
- F-13 (`MS_NONE`, an undeclared enum value, flows into the persisted `ms_lifecycle` field for most ordinary sessions)

**Criteria touched but not primarily blocked:**
- F-07 (two live OCC normalisers) and F-11 (cross-run idempotency broken) don't map to a single numbered criterion directly but undermine the design principles ("one observation, one owner" / "idempotent registration") the numbered criteria assume hold.
- L-04 (structure evaluated once per Morning Gate run, not on completed 5-minute intervals) affects the *quality* of criterion-8 evidence without being a numbered criterion itself.
- R-05 (Lab UI missing several §11 field groups, non-canonical empty-value tokens) is adjacent to criteria 1 and 9 — the data may be correct upstream in some cases but isn't shown.

## BLOCKED items and their prerequisites

| Item | Prerequisite | Owner |
|---|---|---|
| F-03 `error` fixture category | MSI-0 must add (or the implementer must locate/point to) a recorded provider-error-response fixture under `tests/fixtures/marketdata/` (or a re-namespaced `tests/fixtures/msi/`) matching §16.1's requirement. This is a genuine MSI-0 deliverable gap, not a downstream blocker. | MSI-0 |
| Section 7 — all 13 live-run-dependent §20 criteria (4, 5, 7's live portion, 9's live portion, 10's live portion, 13, 14's live portion, every §15 run-summary metric) | A completed evening→Morning Gate→Lab→Interpreter production cycle must actually execute (design §28 steps 7–9, §19 MSI-8). This is **not** an MSI-0 prerequisite — MSI-0's baseline/backup work is already done and confirmed matching HEAD — it is a later build-sequence step requiring explicit user action, real provider cost, and roughly the same ~1.5–2+ hour commitment the prior OLM packs in this repository required for their own live cycles. | User (per design's own control sequence) |
| W-17 screenshot lane (NOT_ACTIVATED) | `MSI_SCREEN_ADAPTER` flag flip in `config/msi_runtime.json`, which per design §19 is explicitly deferred to MSI-7b and "does not block structured Interpreter production." Not a defect — correctly gated off. | MSI-7b (design's own later phase, not MSI-0) |
| R-04's full live switch-off end-to-end (only the flag-mechanism and non-destructiveness halves were executable) | Same as Section 7 — requires an actual pipeline run to observe the v1-reader-restoration path live, since the no-live-provider-call rule prohibits executing the acquisition step this pack would need. | User / later acceptance run |

## What this means for the design's own acceptance bar

Per §20, "the enhancement is production-ready only when" all 17 numbered criteria hold. Based on this pack's evidence: **criteria 2, 3, 6, 8 (mostly), 15, 17 hold**; **criteria 1, 7, 9, 10, 12 are actively failed with concrete, executed evidence**; **criteria 4, 5, 11, 13, 14, 16 cannot be confirmed either way without a live production cycle** (11 is correctly NOT_ACTIVATED by design, not a gap). This is not a judgement of "production-ready" or "not production-ready" — that determination belongs to whoever owns the acceptance decision — but the evidence base does not currently support a claim that the design's acceptance bar is met, independent of whether a live cycle is ever run, because criteria 10 and 12 in particular fail on features that a live cycle cannot itself fix (10's underlying code doesn't exist yet; 12's regressions are in existing, already-executed suites).

## Confidence in this pack's own completeness

High for everything marked VERIFIED/FAILED — every one of those is backed by an executed test with source citation, independently reproduced by five agents working from the same design document without coordinating on interpretation, and cross-corroborating each other on the quote-change gap from four independent angles. Medium for PARTIAL items generally — most PARTIAL verdicts reflect a real, specific, executable sub-failure alongside real, specific passes, not ambiguity. Lower confidence specifically on: the two NEEDS_DESIGN_CLARIFICATION items (design text genuinely doesn't resolve them); R-04's un-executed live-switch portion; and Section 7 in its entirety, which by construction could not be verified beyond confirming its own precondition-failure. No test in this pack was skipped, inferred, or marked passing without execution — every BLOCKED/NOT_ACTIVATED verdict states its exact reason rather than being silently omitted.
