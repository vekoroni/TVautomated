# Thesis reassessment and the pipeline changes that would produce monetisable trades

**Date:** 2026-09-25 · **State:** research proposal, no authority, no pipeline change made
**Objective set by ACK:** 30–50 tradeable outcomes a day with the right asymmetry, produced with confidence; a trade dies only for a valid reason, never because the pipeline is too complex. Fifty monetisable trades beat a hundred coin flips.
**Evidence base (all read-only, all on completed runs):** the fix review (`docs/AVS-FIX-REVIEW_APPROVED_FIXES_20260925.md`), the model assessment, the merged 5+7+8 harness on the full 24 September book and eleven earlier books, the bias sweep, the horizon/DTE tests, the anticipated-move DTE comparison, and static tests of the state label (model 3) and dealer positioning (model 6). One test remains deferred: recomputing GEX from the chain store, which needs the database and waits for the evening run to exit.

---

## 1. My thesis as it stood this morning

1. Calibrate probabilities first (F1), then rank; the edge question is answered by ALG-09.
2. Repair the existing owners in place and keep the gates until each model earns authority.
3. The per-ticker `hidden_state_label` is the calibration key.
4. Dealer positioning stays as a displayed observation.
5. DTE from the window is right; horizon is an output of valuation.
6. Macro, event, regime and sector models are display-only.

## 2. Where the evidence breaks it

### 2.1 Probability is not the first lever. Expression cost is.

On the 401 actionable rows, before any direction probability is applied, the median contract loses 18% of premium over the hold after friction and theta, and only 30% of the terminal grid ends with a positive net exit. The break-even probability of reaching the target before the invalidation, computed from each row's own reachable and invalidation payoffs, has a median of **0.52** and an interquartile range of 0.44–0.61. Half the actionable book needs better-than-even odds just to break even. No calibration can make a coin-flip thesis pay on a contract shaped like that; the shape has to change first. **Thesis 1 is reordered:** make the expression cheap and executable, then ask what you must believe, then calibrate.

### 2.2 The pipeline kills trades for administrative reasons, not market reasons

Why rows died on 24 September:

| Death reason | Rows | Valid market reason? |
|---|---|---|
| `PROVIDER_TIMESTAMP_MISSING` (blocked) | 191 | No. A capture defect |
| `STRUCTURAL_TARGET_UNRESOLVED` / `MISSING_GOVERNED_INVALIDATION` | 375 / 185 | No. The Thesis owner did not publish geometry |
| `ESTIMATED_R_LT_1` at contract selection (alone or combined) | 527 contracts | No. R is intrinsic value at the structural target, the number F2 says is not an expectancy |
| Wyckoff vs actuarial direction conflict → MANUAL_REVIEW | 114 | No. A disagreement between two internal scores is information, not a death |
| `SPREAD_ABOVE_REVIEW_MAXIMUM` → MANUAL_REVIEW | 371 | Partly. Wide spread is a valid reason, but review is not a decision |
| `NO_LIQUID_OTM_CONTRACT` | 190 | Yes, for the option; shares were never considered |
| `EOD_THESIS_READY_REPAIR_AT_OPEN` / `EOD_TRIGGER_READY` (parked) | 640 / 404 | Not deaths, but not decisions either |

**Thesis 2 is wrong in emphasis.** Repairing owners one at a time keeps every one of these death paths alive. The gates are the complexity. The change is to reduce the reasons a trade can die to a short list that a trader would accept, and turn everything else into display.

### 2.3 The state label is not a usable calibration key

Across eight consecutive books, the label changed on 19.8% of ticker-pairs; 242 of those changes happened with every input moving less than 5 points (threshold-edge flips), while 745 pairs saw an input move 25 points or more with no label change. The label is a coarse threshold encoding, unstable at the edges and insensitive in the middle. Stratifying calibration on it would produce strata that move with the label rather than the market. **Thesis 3 is withdrawn.** The conditioning should be on the candidate geometry and continuous evidence (method note 01), not on the label.

### 2.4 Dealer positioning as displayed is close to noise

On actionable rows the gamma flip sits on the **adverse** side of spot for 190 of 347 (55%), and `gamma_island_on_path` is true on 334 of 347 (96%), so it separates nothing. `gamma_flip_state` is blank rather than `GEX_UNAVAILABLE` on 193 rows of the book. Note 07 already records the engine as defective and index chains as uncaptured since 4 September. **Thesis 4 is revised:** a defective observation shown beside a trade is worse than no observation. Remove it from the trader's view until the recompute passes; keep the store.

### 2.5 Theses 5 and 6 stand, with one addition

The anticipated-move DTE rule cost 4 points of expectancy at the median and was worse on seven rows in ten, with two-thirds of its contracts failing the pipeline's own spread cap. Window DTE stands. But the short contract won on one row in three, identifiable in advance by liquidity and IV, so short-dated contracts belong in the expression set as candidates, not as a rule. Macro remains display-only; the book's macro regime is one constant on all 1,532 rows, so it could not rank anything even if allowed.

### 2.6 Two facts I under-weighted

- **The book has no memory.** The positive set overlaps 0%, 0% and 13% between consecutive books, and the actionable count swings between 0 and 515 on adjacent sessions. That is a configuration signature. A prospective record (F7) on a book that changes this much would be measuring the gates, not the theses.
- **The positive set is the forecast.** A 15% error in the vol forecast halves or doubles it. The forecast is above the contract IV on 46% of actionable rows. Until ALG-10 reports, "cheap convexity" is unproven on every row.

---

## 3. The revised thesis

**A trade is monetisable when it is executable, asymmetric and probable, in that order, and the pipeline's only job is to produce the ranked list of rows that are all three and to say plainly why every other row is not.**

- *Executable*: a two-sided, provider-timestamped quote inside the friction domain on at least one expression of the thesis, shares included.
- *Asymmetric*: the reachable payoff at the vol-budget target is at least a governed multiple of the loss if nothing happens by the exit, and the break-even probability p\* implied by the payoffs is below a governed ceiling.
- *Probable*: the evidence's probability of reaching the target before the invalidation by the exit session exceeds p\*. Until that probability is validated, p\* is displayed on every row as "what you must believe" and the row is ranked by asymmetry alone.

What that yields on 24 September, over the 401 actionable rows, with no new model:

| Filter | Rows |
|---|---|
| Complete geometry and contract, quote in domain | 401 |
| Spread ≤ 15% of mid and reachable ≥ 2 × |FLAT| | 173 |
| … and reachable ≥ 3 × |FLAT| | 93 |
| … and p\* ≤ 0.40 (reachable ≥ 2×) | **61** |
| Rows whose legacy probability already clears its own p\* | 77 |

The 30–50 target is inside the range of what the existing book already contains once the wrong deaths are removed and the right ordering is applied. The full-book run adds candidates from rows the Lab currently marks BLOCKED or MANUAL_REVIEW (13 and 22 positive rows respectively), so the base is wider than the GO tier.

---

## 4. Pipeline changes, in the existing owners

All changes are to existing modules, test-first, one defect at a time, per CLAUDE.md rule 4. Each is tied to the evidence above.

| # | Change | Owner (existing) | Why (evidence) | Effect on deaths |
|---|---|---|---|---|
| P1 | **Four death reasons only.** `NO_EXECUTABLE_EXPRESSION`, `GEOMETRY_UNAVAILABLE`, `ASYMMETRY_INSUFFICIENT`, `NO_POSITIVE_EDGE`. Every other verdict (EIL, physics, campaign, direction conflict, convexity, macro, trigger) becomes a displayed field with no routing power | `contracts/lab_control.py` verdict assembly; morning gate routes | 2.2 | Removes the 114 conflict reviews and the verdict-driven STAND_DOWNs; a trade cannot die for a score |
| P2 | **Fix the timestamp capture** so a quote without a provider timestamp is repaired or marked `QUOTE_UNAVAILABLE`, never a BLOCKED verdict on the thesis | quote capture (ALG-12 owner) | 191 rows | Those rows become executable or unexecutable on a real quote |
| P3 | **Geometry or an explicit gap.** Thesis publishes target and invalidation or `GEOMETRY_UNAVAILABLE` with a reason, and the manifest reports the count as an upstream defect that downgrades `run_tradeable_label` | Thesis / handoff (F5) | 375 + 185 rows; manifest says EXECUTION_READY with 185 defects | The gap is visible and owned, not a silent death |
| P4 | **Retire `ESTIMATED_R_LT_1` as a contract gate.** Replace with the ALG-04 reachable payoff as a ranking key inside expression valuation | contract selection in Options Intelligence | 527 contracts rejected on intrinsic-at-structural-target | Contracts are ordered by a scenario expectancy, not killed by a scenario ceiling |
| P5 | **Asymmetry as the selection rule.** Governed constants: spread cap (proposed 0.15), reachable/|FLAT| multiple (proposed 2), p\* ceiling (proposed 0.40). Publish p\* on every row | Valuation (ALG-04) and Ranking | 61 rows today | The only value-based death is "you would have to believe more than X" |
| P6 | **Expression set includes shares and short-dated contracts**, each with its own last exit session, valued on the same paths | Expression generation (§10) | 190 `NO_LIQUID_OTM_CONTRACT`; short contract wins 1 in 3 | A thesis with no liquid OTM option can still be expressed |
| P7 | **Probability from the geometry, not the label.** First-passage curve per candidate geometry (F1); `hidden_state_label` demoted to display | Evidence context | 2.3 | p\* is compared with a probability that does not churn 20% a session |
| P8 | **Remove defective observations from the trader view**: convexity score (a campaign encoding), gamma island/flip until recomputed, constant macro regime | Presentation | 2.4; F4.2 | Nothing on the screen implies a signal that is not one |
| P9 | **Validate the vol forecast before any "cheap convexity" language** (ALG-10, F4.3); until then the reachable payoff carries `UNVALIDATED` | Volatility context | bias sweep | The list cannot double on an unmeasured forecast |
| P10 | **Freeze one selection rule and report book stability daily**: positive-set overlap with the previous book, and actionable count, as run-health metrics | Run manifest; ledger (F7) | 2.6 | A day with 0% overlap is a health failure, not a market event |

## 5. What the funnel would look like

```
universe scanned            3,300
theses with a contract      1,500      (today; unchanged by these changes)
executable expression         ~1,100   (P2, P6 recover timestamp and no-OTM rows; spread cap removes wide ones)
complete geometry               ~900   (P3 makes the rest an owned, counted gap)
asymmetric at governed cap      ~150–200
p* below ceiling                 ~50–80
probable, once validated         30–50   (the objective; unknown until F1 reports)
```

Every row that leaves the funnel carries one of four reasons and the number it failed on.

## 6. What must still be true for this to be a tradeable pipeline

- The forecast validates (ALG-10). If the forecast is biased high, the reachable payoff shrinks, p\* rises and the list shortens; the pipeline then reports fewer, honestly.
- The first-passage probability clears p\* on enough rows. Today the legacy probability clears it on 77 of 401; the validated number is unknown and may be lower.
- The book stops changing 90% a day. That is a configuration fault to find, not a research question.
- Fills match the friction model. Nothing better than the quoted spread until the ledger shows it.

## 7. Decisions for ACK

1. Approve the four death reasons and the demotion of every other verdict to display (P1).
2. Approve the three asymmetry constants as governed configuration with initial values 0.15 / 2 / 0.40 (P5).
3. Approve shares and short-dated contracts in the expression set (P6).
4. Confirm removal of the convexity score, gamma island/flip and macro regime from the trader view until each passes validation (P8).

## 8. Correction to §2.2, after checking what the dead rows contain

ACK accepted the §2.2 diagnosis and asked whether the enhancements would change it. Checked row by row on 24 September:

| Death path | What the rows hold | Effect of the enhancement |
|---|---|---|
| 191 `PROVIDER_TIMESTAMP_MISSING` | No quote of any kind on any of the 191 | Zero revived by a timestamp fix; the label is wrong, the death (no expressible option) is valid. Only shares as an expression (P6) reach them |
| 371 `SPREAD_ABOVE_REVIEW_MAXIMUM` | Spreads 35–92% of mid; none ≤ 15%, 43 ≤ 30% | Zero revived; valid market deaths mislabelled as review |
| 114 direction conflicts to review | 76 valuable, 48 with spread > 15%, 8 pass asymmetry | About 8 revived, not 114 |
| 375 missing invalidation (312 also missing target) | All 375 carry `wyckoff_validation_structural_invalidation_level` | Up to 375 regain an invalidation if ACK approves that field as a governed, provenance-labelled source; 312 stay dead for lack of a target, validly |
| 527 `ESTIMATED_R_LT_1` contract rejections | Every ticker still ended with a selected contract; the gate demoted routes (361 probe-only, 140 half) and shaped contract choice | No deaths to revive; P4 changes which contract and which route on 527 tickers, the largest unmeasured lever on asymmetry |

Conclusion: the executable ceiling (about 700 in-domain rows today) is set by the market and by upstream publication, and the enhancements do not raise it. They change three things: every death carries a valid reason; contract choice and routing on 500-plus tickers move to a reachable-payoff expectancy; and the executable set is ordered by asymmetry. The 30–50 come from ordering and contract choice on live theses, not from reviving dead ones.

**Next test:** re-select the contract for the 527 `ESTIMATED_R_LT_1` tickers from the run's tested chain by reachable-payoff expectancy and compare with the pipeline's choice. Read-only on the completed run folder.

## 9. Deferred test

GEX recompute from the chain store against the 347 published flips, to decide whether the adverse-side result in 2.4 is the engine or the market. Runs read-only once the evening orchestrator exits.
