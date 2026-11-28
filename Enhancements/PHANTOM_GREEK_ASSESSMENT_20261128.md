# Phantom Greek completion — exact-session American assessment

ACK approved the saved-data-only end-to-end fix and a narrowly patched isolated production release. No provider, pipeline, scheduler, Lane B decision or promotion-policy change is part of this release.

Publication is isolated on `fix/phantom-greek-completion-e2e-20261128`, based on published commit `67d9ec9eb1d3ca1ce4151813032eaabfb26ab307`. Only the 15-path Phantom delta from local production commits `25bb22959cd97cf0b48ae7bbfa3ad0d2afa541cb` and `568953d8c9ff0eba902737e8cb3d1491ced748f6` is carried here. Their unpublished Evening/Lane B ancestry is deliberately not published. The already activated production release and launcher pin remain unchanged; this publication is not a new activation. Git and the activation receipt, not this prose, identify the active release.

## One analytical result, protected raw facts

Raw `chain_snapshots` values and their ingestion labels are preserved. Missing raw vendor IV is not silently filled with a number from a different model beside vendor delta/gamma/theta/vega. `phantom_greek_assessments` stores the current exact-contract/input-hash assessment and coherent model vector, if qualified. `phantom_greek_assessment_audit` preserves each prior/new payload transactionally. Every result carries a calculation version covering this implementation, the shared model owner, governed policy and quote-qualification code.

American CRR prices come from `domain.option_valuation`; European index style uses its European owner. The fixed 4.5% rate, zero dividend and calendar-DTE clock are explicit assumptions, not measured historical inputs. Quote/underlying synchronization remains unverified where the archived source lacks clocks. Numerical Greeks are a separately sourced model result. All results are ADVISORY_ONLY and promotion_eligible=false; global Phantom promotion blocks remain unchanged.

Point inversions must have an interior finite bracket, IV within the retained 1–500% benchmark range, stable finite numerical Greeks, and 300/600-step price agreement. Midpoints outside the model domain or on an unidentifiable boundary remain interval-only, with bid/ask model-compatible bounds where supported. No observed midpoint is clamped, no ask is substituted as an observed midpoint, and no missing underlying is invented. Wide-spread interval results do not enter point-IV benchmarks.

## Integration

- Every raw-ingestion hook performs/persists the assessment even when vendor fields are protected.
- Weekly maintenance runs bounded latest-session assessment after label work; new/stale remainder is NEEDS_LOCAL_FOLLOW_UP, never silent success.
- Session health separates raw incomplete Greeks from genuinely unassessed work and assessed exclusions.
- Surface/cache derivation and Phantom latest/history/scoring readers use the same fresh coherent assessment. Changed raw input or model version invalidates derived use.
- Vendor/unknown-origin cache observations remain protected. Disagreements stay IV_CONFLICT; other pairs continue. Existing surface/cache/queue partial-commit reporting is retained.
- The dated Lab disclosure distinguishes original missing fields from current assessment. It is a read-only overlay: saved card fields, revision, verdict and rank do not change. The older release base receives only the optional read-only coverage adapter, not other Lab or Lane B changes.

## Acceptance evidence

Evidence directory: `C:/Users/ACKVerissimo/Documents/Codex/2026-07-24/a/PHANTOM_GREEK_E2E_20261128`.

The full-Friday fixture has 268,360 exact saved rows, zero unassessed: 176,832 vendor-qualified vectors, 2,273 coherent model vectors, 13,766 interval-only, and 75,489 explicitly excluded rows. Qualified total: 179,105; interval/excluded total: 89,255. All original chain fields and protected vendor cache observations match before/after. Eight hundred affected ticker/session pairs are refreshed; 111 unavailable point-IV pairs remain explained exclusions, not unfinished work. No claim of unrestricted chain coverage or full promotion is made.

Of the formerly unassessed 15,944 partial vendor rows: 2,131 now have a separate coherent model point, 13,627 are interval-only, 95 have invalid quotes, nine fail the retained IV range, 79 have a spread incompatible with the assumed model, and three have asks below saved intrinsic value. No vendor field is overwritten. Cache membership changes despite its unchanged total: ACTG/FFIN/LRMR become available; CMTG/CVRX/HTH are explicitly excluded by the corrected American-model assessment. All 111 unavailable pairs have no qualified point row in the stored scope; their per-row causes are recorded.

The final frozen isolated-release acceptance suite has 423 passes across nine targeted files, including the independent model-owner benchmarks. Node syntax checks pass for both live and isolated review-app.js. Bounded-assessment remainder and invalid-DTE reader guards are included. This is not a claim that the entire repository suite was rerun.

`FULL_FIXTURE_RESULT_v2.json` is the full saved-data acceptance receipt. `LIVE_RESULT_v2.json` is the guarded live-application receipt; its terminal status, not this document, determines whether application completed. The interrupted first temporary fixture is retained with an explicit interruption receipt, not counted as a pass. Targeted model/maintenance/cache/scoring tests, independent shared-pricer benchmarks, read-only Lab overlay tests and bounded-remainder tests are recorded separately. No whole-pipeline run or full-repository green claim is made.

Commit, activation, raw source hashes, unchanged Lane B/runtime bindings, private training-pool preservation and launcher VerifyOnly results are recorded in the dated production activation receipt. Old release/receipts remain available for rollback. No historical failure receipt is rewritten to manufacture success.

Release hygiene follow-up: the shared Phantom store contains five typed shadow JSON artifacts and three exact operator-document/input paths that also make the old release report PARTIAL_UNTRACKED. The production patch ignores only the typed JSON patterns and exact document names, not their directories or executable source. Three packaging regressions prove .py/.ps1/.js remain visible. No files are deleted or moved from shared stores and the provenance guard is not weakened.
