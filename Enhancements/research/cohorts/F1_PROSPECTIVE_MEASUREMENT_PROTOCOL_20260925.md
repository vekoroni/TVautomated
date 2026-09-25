# F1 — Frozen measurement protocol for the prospective shadow cohort

**Date:** 2026-09-25 · **State:** MEASUREMENT_ONLY, frozen on ACK's instruction ("carry on with F1") · **Registration:** `cohort_1_preregistration.json` beside this file (immutable once committed; amendments appended, never edited)
**Governing method:** spec §15 (ledger), §16 (outcomes), §17 (validation); method note 06 §4 (statistical honesty), §6 (ledger backbone), §7 (acceptance protocol, gate G4). Reviewer amendment F1: "Freeze a shadow comparison cohort now: current selector versus broad-family selector, with both decisions and all quotes recorded before outcomes. Activate only after pre-registered acceptance tests pass."

## 1. What is frozen

| Element | Frozen value |
|---|---|
| Code | git `bb4cf50`; sha256 of the seven files that decide selection, viability, valuation and the manifest are in the registration |
| Configuration | `governed_constants_v1.json` sha256 `8a12cdf5…`; `value_selection_mode = SHADOW`; vol bias multiplier unapproved; empirical path valuation `SHADOW_NO_AUTHORITY` |
| Selection rule under test | legacy score selector authoritative; shadow value selector recorded beside it (B1 makes it produce evidence) |
| Window and exit policy | thesis window 1–20 sessions (D2 decision); exit at target, invalidation, Day-20 time stop or last exit session, whichever first |
| Friction model | entry at ask, exit at bid; modelled haircut min(spread/2, 0.15) is what H3 tests, not what scoring uses |
| Variant count carried into the cohort | 15 exploratory variants run on the 24–25 Sep books, listed in the registration |

Any change to any of these starts COHORT_2 with its own registration. Nothing in this cohort is tuned on its own outcomes.

## 2. What is logged, and when

Every record is written before the outcome is known (spec §15). Per decision record in every morning-validation run:

**Already recorded today** (ledger candidate event, options row, Lab book, manifest): identity and lineage, direction, route and verdict, the legacy selected contract and its quote snapshot id, geometry and its state, planned hold, viability state and both reasons (A2), the shadow selector's basis, quality flag, score-choice symbol, best symbol, best value, alternatives with ask and spread, and the forecast's source, run and age (B1); the manifest's geometry grain (D2) and stability block (D3).

**To be added before the first scoring (F1.b, code, test-first, next item):**

1. Legacy and shadow contract bid, ask and provider timestamp at the morning requote, on the ledger candidate event, so a pair can be scored without reaching into a snapshot store.
2. ALG-04 scenario values (flat, 1σ, reachable, structural, invalidation at LATE/BASE) with `friction_assumption` and `validation_state = UNVALIDATED`, as disclosure (C1).
3. `breakeven_p_target` as review information, labelled a two-outcome lower bound.
4. Macro overlay alignment as display.
5. `variant_counter_at_decision`, read from the registration.

Until F1.b lands, the pair can still be identified from the recorded symbols and snapshot ids, and the requote quotes recovered from the run's morning artefacts; scoring simply waits.

**Every session, from the manifest:** `book_stability.retained_share` and `dropped_by_cause`; `thesis_geometry_completeness.actionable_missing_any`.

## 3. How an outcome is scored

- **Underlying** (C12, existing): TARGET_FIRST / STOP_FIRST / TIMEOUT / AMBIGUOUS with the first-touch session, for every thesis version, selected or not.
- **Expression**: for each of the pair's two contracts, entry at the morning-requote ask, exit at that contract's bid at the earliest of the underlying resolution session, the Day-20 time stop, or the last exit session. Net return on premium, realised spread cost, sessions held, exit reason, MFE and MAE at bid marks.
- **Exact-contract quotes are required.** If the exit bid was not captured, the pair is UNSCORED and counted as such. Nothing is modelled, interpolated or filled from a later snapshot. This is why A3 (provenance, coverage, canary, then capture) is on the critical path of this cohort.

## 4. Pre-registered tests

| Test | Statistic | Pass | Sample |
|---|---|---|---|
| H1 primary: shadow contract earns more than the legacy contract on the same decision | median paired difference in net return on premium; 95% block bootstrap by session, 2,000 resamples, seed 20260925 | interval lower bound > 0 and median > 0 | later of 60 sessions and 200 scored pairs, ≥ 40 with different symbols |
| H2 downside | p10 of net return, shadow vs legacy | shadow p10 ≥ legacy p10 − 0.05 | as H1 |
| H3 friction | median (realised spread cost − modelled haircut) | ≤ 0; failure re-opens the friction model in a new cohort | as H1 |
| H4 break-even (secondary, reporting only) | median net return, rows with p\* ≤ 0.40 vs above | reported with interval; no threshold tuned | as H1 |
| H5 stability (reporting only) | `retained_share` trend; `GEOMETRY_MISSING` drops | expected to rise / fall to zero after A1 | per session |

Deflated statistics are reported against the 15 pre-cohort variants plus any appended to the registration before they are run.

## 5. Comparators

Long shares of the same ticker over the same window (computable from bars now). The sector ETF option of the same direction and horizon, when its quotes are captured, otherwise UNSCORED. The desk-gate list against the harness Tier A list, research only. An index buy-and-hold is not a comparator: it mismatches the option's risk and horizon.

## 6. What this cohort can and cannot conclude

It can say whether the shadow value selector picks a better contract than the score selector on the same theses at real quotes, and whether the friction model is honest. It cannot say the pipeline has an edge: the sign of the median row is decided by the direction probability (C4), which this cohort does not test. Activation of the value selector (ACK's ACTIVE switch) requires H1–H3 to pass here **and** the historical walk-forward through the production services to pass (gate G4), with independent review.

## 7. Roles and cadence

Weekly summary to ACK from the ledger and manifests; no interim decision. Independent human quant review of the results before any authority change. The registration file is committed with this protocol; the commit hash becomes part of the cohort record.
