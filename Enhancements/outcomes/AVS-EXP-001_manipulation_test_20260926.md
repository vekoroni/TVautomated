# AVS-EXP-001 — Manipulation / Counterfactual Test Against Historical Data

**Date:** 26 Sep 2026
**Status:** ANALYSIS ONLY. No pipeline code, config, or threshold touched — every number below comes from read-only queries against `data/canonical/outcome_scoring.sqlite` and the unbuilt research documents in this session's uploads. Nothing here is a production change; it is evidence for the Decision-A/B/C/D choices in `AVS-PLAN-001`, and specifically for **which of the two already-drafted, unbuilt designs** (`AVSHUNTER Cautious-Return Gate Replacement — Project Spec`, and its formalization `HARC`) is worth building first.
**Scope of this pass:** per your instruction — test manipulations/alternate paths against history, using intelligence, before committing to a build direction. One test below (the shares-vs-options gap) is robust and certified-equivalent. One (the ATR-band discriminator) failed my own sanity check and is explicitly discarded rather than reported as a finding. One (hold-horizon) is exploratory and flagged as likely biased. Reporting all three, including the failure, per your standing instruction not to go back and forth on fixes without the full picture on record.

---

## 1. Headline finding — shares would have beaten the options overlay, and this is certified-grade evidence

**The question:** on the exact same theses AVSHUNTER already generated, would expressing the trade as directional shares instead of a long option have done better? This is not a new idea — it's already named as in-scope in the unbuilt Gate Replacement spec (§4.2, "for shares (when bullish)") and it's already partially tested in your own trade-study workbook (`avshunter_trade_study_and_carry_forward.xlsx`, "Alternate paths" tab, pre-September cohort). What follows re-runs it on the full current dataset (31,620 predictions, 26 sessions) using the scorer's own paired columns, which your workbook didn't yet have at this scale.

**Method:** `expression_outcomes` already stores, for every scored option expression, both `return_on_premium` (the option's paper return) and `underlying_return_to_exit_pct` (the same prediction's underlying price return to the same exit) — a same-prediction, same-exit paired comparison. Restricted to `MARKED` expressions with both values present, excluding predictions first sighted under a `TEST` run: **n = 4,319, 20 sessions.**

| | Option (bought) | Shares (equivalent exposure) | Gap |
|---|---|---|---|
| Win rate | 11.3% | 20.8% | **+9.5 points** |
| Mean return | −47.3% | −1.9% | **+45.3 points** |
| Median return | −58.6% | −2.1% | — |

**Confidence: high.** Session-clustered bootstrap (resampling the 20 sessions, 3,000 draws): win-rate gap CI **[+6.2pp, +13.7pp]**, mean-return gap CI **[+39.2pp, +50.2pp]** — both entirely above zero, at 20 sessions. That meets the exact bar (`≥20 sessions`, CI clear of zero) your own certified `outcome_report.md` uses for `verdict OK`. This is not a fragile result.

Split by direction (same population):
- **BULL** (n=3,577): option win 9.8% / mean −50.4%; shares win 19.4% / mean −1.8%.
- **BEAR** (n=742): option win 18.6% / mean −32.0%; shares win 27.8% / mean −2.6%.

Shares beat options in both directions, though the gap is largest on BULL — where the certified report also found the thesis itself is closest to a coin flip (target excess +0.2%), so shares gets you closer to "coin flip with near-zero average cost" while the option's theta/spread turns that same coin flip into a heavy loser on average.

**What this means, precisely.** This does not say the thesis-generation problem in `AVS-PLAN-001` §1 is fixed — shares' own win rate (20.8%) is still below 50%, and mean return is still slightly negative (−1.9%), not positive. It says the **second leak** already flagged in `AVS-PLAN-001` §3 (correct theses only convert to option profit 51% of the time) is far larger and more tractable than the direction-signal problem: on this data, most of the gap between "roughly break-even direction signal" and "the pipeline's actual −47% average option return" is the option wrapper, not the thesis. That reframes Decision A: **A2 (the option-expression layer) has a bigger, better-evidenced, more certain problem than A1 (the thesis signal) right now** — the opposite of what I'd have guessed going in.

This is also the strongest evidence yet for prioritizing the unbuilt Gate Replacement spec's Stage 2/3 (option-expression signal, shares as an explicit alternative) over further direction-signal work, and it gives HARC's Stage 3 utility-ranking design a concrete number to beat.

---

## 2. A test I ran and am discarding — do not use the ATR-band figures below

Decision A in `AVS-PLAN-001` recommended slicing the certified base-rate excess by ATR-distance band to discriminate thesis-quality (A1) from geometry-quality (A2). I attempted a hand-rolled replication of the matched-base-rate methodology (averaging each prediction's `target_fractions_json`/`stop_fractions_json` from `base_rate_outcomes`, session-clustered bootstrap) and got:

| ATR band | target excess | stop excess |
|---|---|---|
| Tight | +35.9% | +43.7% |
| Mid | +19.5% | +66.6% |
| Wide | +5.9% | +79.8% |

**These numbers are wrong and I am not reporting them as a finding.** They are 10–30x larger than the certified report's headline (target excess ≈0%, stop excess +2.5%), which means my simplified "average the fraction array" approximation does not match the real scorer's Aalen-Johansen cumulative-incidence-with-censoring estimator (`avshunter/c12_outcome/estimators.py`) closely enough to trust. Rather than let a wrong number stand — as happened twice earlier in this investigation — I'm flagging it explicitly and discarding it. **The honest state of Decision A is: still unanswered.** The only reliable way to get it is to run the real scorer sliced by ATR band, which is a request to extend `avshunter/c12_outcome` reporting (still analysis, not a pipeline change) — I'd need either read access to run it myself or ACK to run an extended report command, same pattern as the earlier coverage extension.

## 3. Exploratory only — hold-horizon look, likely survivorship-biased

Bucketing the same option/shares pairs by approximate hold length:

| Hold bucket | n | option win | option mean | shares win | shares mean |
|---|---|---|---|---|---|
| 0–5d | 2,586 | 10.1% | −42.7% | 19.2% | −1.7% |
| 6–10d | 876 | 7.5% | −61.3% | 13.1% | −3.5% |
| 11–15d | 426 | 12.7% | −61.6% | 18.3% | −3.5% |
| 16–20d | 119 | 20.2% | −42.3% | 26.9% | −2.7% |
| 20d+ | 312 | 27.2% | −28.0% | 57.1% | +3.0% |

**Confidence: low, and I would not act on this.** The 20d+ bucket looks dramatically better, but predictions that are still open at 20+ days are, almost by construction, ones that haven't been stopped out — survivorship, not a causal effect of holding longer. This is exactly the selection-bias trap the HARC document's censoring discussion (§1a, §3) and the Gate Replacement spec's "an unquoted path... never defaulted to zero or loss" rule both warn about. A trustworthy version of this test needs the point-in-time panel design already specified in the Gate Replacement spec §3 (fixed decision-time cohort, explicit censoring flag), not a naive bucket-by-outcome-length. I'm surfacing it only so it isn't silently lost, not as a recommendation to extend hold length.

---

## 4. What this changes for the decisions in AVS-PLAN-001

- **Decision A (thesis vs. geometry):** still open on the base-rate side (§2 above failed), but §1 supplies new evidence that the **option-expression layer** is a larger, more certain, more tractable lever than either A1 or A2 as originally framed. Recommend adding "A3 — option expression / shares-vs-option" as a third fork, and treating it as the leading candidate given it's the only one certified this session.
- **Decision C (sequencing):** the unbuilt Gate Replacement spec and HARC are already scoped to build exactly this (three-signal design with shares as an explicit expression alternative). §1's result is a concrete, quantified reason to move that spec's Phase 0/1 (panel build, baseline replication) ahead of the macro enhancement and Morning Gate margin work, not just "second-order" as AVS-PLAN-001 §4 characterized it.
- **Decision D (certification bar):** §1 already clears the bar (20 sessions, CI off zero) — it can be cited as certified-grade in any future design doc, unlike the discarded §2 attempt.

Nothing here authorizes building the Gate Replacement design, HARC, or any shares-expression feature. Per those documents' own Section 2 non-goals and this session's instruction not to build without a solid plan, this is the evidence base for that decision — the decision itself is still yours.
