# Response to the review of the change register (25 September 2026)

**Reviewer's verdict:** approve as a research backlog, not as a production release plan.
**My response:** accepted. The review is right on the central point and on most of the detail. The register proposed making a rule selected on the research books the active contract selector tonight; that contradicts the repository's own rule 5 and Invariant G, which I had cited myself. Below, each comment is marked **Accept**, **Accept with change**, or **Push back**, with what changes in the register.

---

## 1. Point by point

| # | Comment | Response | What changes |
|---|---|---|---|
| 1 | Keep A3, B1, C3, C4, F1 as the learning path; A2, D2 as truthfulness fixes; C1 as disclosure; F3 correct | **Accept** | None. These stand as written |
| 2 | Re-selection improved model-implied value (−10.8% → −4.7%) but positive rows fell 24 → 19; evidence to investigate contract cost, not that the rule makes trades profitable | **Accept** | B2's "Improves" line is reworded: it lowers modelled expression cost; it does not create edge. The register already said so in the con; the headline now says it too |
| 3 | A1 / G: 312 of the 375 rows also lack a target, so supplying invalidation completes at most 63; all 375 were BLOCKED, none GO; the funnel line "~530 → ~900" is inconsistent | **Accept** | Correct on every count. My "~530" was wrong as well: the book has about 1,108 rows with both target and invalidation today (1,532 − 375 − 49). The funnel row becomes "1,108 → up to 1,171 with the invalidation fallback; 312 still lack a target". The phrase "up to 375 regain an invalidation" is replaced by "63 rows can become complete; 312 remain research-only". Distinct counts for missing target / missing invalidation / both are added |
| 4 | A fixed "within 1% of spot" degenerate rule is unvalidated across volatilities and horizons | **Accept with change** | The rule is restated relative to the vol budget: a level inside 0.25 × the hold-window move is degenerate for that hold. The 1% figure was a screening heuristic for the plan, not a proposed constant. On the morning book the two rules flag the same rows, which I will report when the vol-relative version runs |
| 5 | Test whether a Wyckoff level is a directionally and temporally valid Thesis fallback before adopting it | **Accept** | A1 gains a precondition: check side (below spot for BULL, above for BEAR) and age (level computed at or before the evidence session) on the 375 rows before any fallback is approved. Until then the rows stay visible and research-only |
| 6 | A2 / D1: "no quote now" is not a permanent death; use a reversible monitoring state | **Accept** | `NO_EXECUTABLE_EXPRESSION` becomes `NO_CURRENT_EXECUTABLE_QUOTE`, a per-session monitoring state, matching the spec's `EXECUTION_*_MONITOR` states. A row re-enters when a quote appears |
| 7 | Four death reasons cannot replace point-in-time correctness, contract identity, thesis invalidation and source-quality controls | **Accept** | D1 was under-specified. The hard checks (crossed or negative quote, stale quote, malformed identity, thesis invalidated or superseded, missing provider timestamp, freshness) are data states, not verdicts, and are retained. D1 is restated as four **axes**, each with its own states: thesis state (C5), data sufficiency (C1/C2), current expression and quote state (C6/C10), research rank (C9). Only advisory verdicts (EIL, physics, campaign, direction conflict, convexity, macro, trigger) move to display |
| 8 | `NO_POSITIVE_EDGE` cannot be authoritative while probability and volatility are unvalidated | **Accept** | It becomes a research-rank state, displayed, until C3 and C4 pass. My own reassessment said this and the register lost it |
| 9 | B2: changing 89% of choices is a major intervention; half the alternatives are above 0.89 delta; chains truncated; the selector is SHADOW by config; do not make B2 active tonight | **Accept** | This is the main correction. Tonight's run carries B1 (revived shadow) plus a **broadened shadow family** (delta bands removed inside the shadow shortlist), legacy selection stays authoritative, old and new choices recorded with quotes. Activation only after pre-registered acceptance on matched prospective cases |
| 10 | B3: short shares are out of scope; a share route does not "recover" 380 opportunities | **Push back on scope, accept on the claim** | Spec v1.1 §10, approved expression scope, lists **short shares (subject to borrow)** for BEAR theses beside long shares for BULL. If ACK has narrowed that since, the spec needs the amendment first; either way short shares wait for borrow data, so the practical sequence is the reviewer's. On the claim: accepted. Shares create an expression to assess on about 380 rows; they do not recover them. The funnel row "714 → ~1,100 valuable expressions" is withdrawn |
| 11 | C1–C2: the grid is not "probability-free"; thresholds were chosen after inspecting the books; the two-outcome break-even omits timeout | **Accept** | "Probability-free" becomes "thesis-probability-free, distribution-assumed (lognormal, direction 0.5)". p\* is published as review information, not a gate, and labelled as a two-outcome lower bound; the three-class version (target / invalidation / timeout) follows ALG-07 once C4 exists. Thresholds are frozen for a later untouched cohort, not applied to the cohort they were chosen on |
| 12 | C3 is a prerequisite, not a Saturday afterthought; C4 labels alone do not prove monetisable at bid; C5's gain is retrospective | **Accept** | C3 moves to "before any value-based promotion". C4 is paired with A3 (exact-option paths) before any monetisation claim. C5 stays "build with C4, activate after" |
| 13 | E1: an adverse-side flip or a frequent island does not prove GEX wrong; a single macro regime is expected for a market-level field | **Accept with change** | The convexity score stays hidden (it is a verdict re-encoding with a blank source). Gamma and macro are shown with source, timestamp, quality and limitations rather than hidden; the "no cross-sectional information" remark was true but not a reason to remove context. Ticker-specific sector-relative exposure in the overlay is noted as later research |
| 14 | F1: freezing measurement now is right; starting the cohort with B2 live is not | **Accept** | Cohort 1 is a shadow comparison cohort: current selector versus broad family, both decisions and all quotes recorded before outcomes. Activation only after pre-registered acceptance tests |
| 15 | Wording: "median expectancy" → model-implied scenario value; "30–50 probable" → unverified target for future calibration | **Accept** | Applied throughout the amendments |
| 16 | The register is untracked by Git; govern the revised version before treating it as release requirements | **Accept** | All of today's research files are untracked. I commit only on ACK's instruction; the request is recorded in the amendments |

## 2. Where I still differ, in one paragraph each

**Short shares.** The governing spec includes them. I am not proposing to build them now, because borrow data is absent, but the register should not record them as out of scope on the strength of a reviewer's recollection when the signed specification says otherwise. If the scope was narrowed after v1.1, that decision belongs in the spec's change log.

**D3 as diagnostic.** Agreed that a 0% overlap has legitimate causes and must be split by cause. I would still surface it in the manifest rather than only in a research report, because it is the one number that will tell us whether the fixes are making the book more stable. Diagnostic, not a run-health failure, is the right label.

**The value of B2's test.** The reviewer reads it as evidence to investigate contract cost. I agree, and would add that it is also evidence about the delta band specifically: 242 of 327 better contracts were excluded by a rule the spec forbids as pre-selection. Broadening the shadow family is the right way to test it, and that is what tonight's run should do.

## 3. Revised release sequence (adopting the reviewer's order)

| Step | Items | Authority |
|---|---|---|
| 1. Now | A2 relabel (reversible quote state); D2 with correct grain; D3 as a diagnostic split by cause; B1 repaired in shadow; F1 measurement frozen | Current routing preserved; shadow only |
| 2. Before any value-based promotion | C3 forecast validation; A1 counts and fallback validity test; C1 scenario display with conspicuous assumptions; A3 provenance and canary | Display and research |
| 3. Parallel shadow research | B2 broadened contract family; B3 long shares in shadow for BULL theses; old and new choices logged; matched outcomes scored without tuning the same cohort | Shadow |
| 4. After evidence accumulates | C4 calibrated probabilities; then C2 thresholds and C5 exit policies out of sample; D1 axes restated, applied only after characterisation tests show no correctness or data-quality protection was lost | Earned per §24 |

## 4. What tonight's evening run should therefore carry

B1 repaired and the shadow family broadened, nothing else. Legacy selection remains the selected contract. Every row records the legacy choice, the shadow choice, both quotes and the valuation basis. That gives the first matched comparison without deploying anything.
