# AVS-EXP-003 — Why the Conditions Behave This Way, and Joint What-If Scenarios

**Date:** 26 Sep 2026
**Status:** ANALYSIS ONLY, same 26-session dataset as EXP-001/002. Goes past "what conditions correlate with wins" into (a) testing *why*, mechanistically, and (b) simulating combined filters jointly rather than one at a time. No pipeline touched.

---

## 1. Why — three mechanisms tested, and I'm reporting the two that didn't go the way I expected, not just the one that confirmed a story

**Hypothesis 1 — shorter DTE wins more because of option convexity/leverage (gamma amplifying the same underlying move). REFUTED AS STATED, replaced by a sharper and more specific finding.**
Testing this required checking whether the *underlying's own move size* (`mfe_pct`) is flat across DTE while the *target-hit rate* varies — if so, that's leverage, not a better thesis.

| DTE bucket | n | target-hit rate | underlying MFE, mean |
|---|---|---|---|
| 0–10 | 497 | 23.9% | 3.46% |
| 11–20 | 1,244 | **28.1%** | 3.84% |
| 21–30 | 6,204 | **7.4%** | 3.14% |
| 31–45 | 1,738 | 22.4% | 3.59% |
| 46+ | 1,005 | 11.0% | 1.58% |

The underlying's own move size is roughly flat across 0–45 days (3.1–3.8%) — only the 46+ tail genuinely moves less. That kills the convexity story: the underlying isn't moving bigger or smaller by DTE, so the option-leverage explanation doesn't apply to *this* metric (target-hit is measured on the underlying, not the option). **The real, more specific finding: the 21–30 day bucket has a target-hit rate roughly a third of its neighbors on both sides, despite a similar-sized underlying move.** That's not a leverage effect — it points at something in how targets/stops are *set* specifically for medium-DTE contracts (geometry, not thesis quality), which is squarely Decision A2 (geometry) from `AVS-PLAN-001`, now with a concrete DTE band to test it on. **Confidence: medium — clean, large-sample, non-overlapping result, but mechanism (why 21-30d geometry specifically) is not yet explained, only located.**

**Hypothesis 2 — BEAR/PUT theses do better when the labeled macro regime agrees with them (regime alignment). REFUTED, and inverted.**

| Direction | Regime-aligned? | n | win rate |
|---|---|---|---|
| BEAR | No (misaligned) | 942 | **18.4%** |
| BEAR | Yes (aligned) | 526 | 13.7% |
| BULL | No (misaligned) | 4,290 | **13.6%** |
| BULL | Yes (aligned) | 5,296 | 11.4% |

Both directions did *slightly better when disagreeing with the labeled regime*, not agreeing with it. **Confidence: medium** — consistent direction on both sides, moderate sample. This is a genuinely useful negative result: it's independent empirical support for your own standing design principle (CLAUDE.md rule 6, and your macro-informs-not-gates note) — not just "macro shouldn't hard-gate," but "aligning with the label doesn't obviously help even as a soft signal," at least on this window. I would not build a "prefer regime-disagreement" filter off this alone — the effect is small enough it could easily be one bearish five-week stretch — but it argues against building a regime-agreement filter, which is the opposite of the original hypothesis.

**Hypothesis 3 — LOW breadth days produce more losers because of more chop (bigger adverse excursion before resolution). REFUTED.**

| Breadth state | n | win rate | mean adverse excursion (MAE) |
|---|---|---|---|
| HIGH | 3,183 | 9.8% | −6.29% |
| LOW | 3,524 | 13.4% | **−4.78%** (least chop) |
| MID | 4,347 | **14.8%** | −6.04% |

LOW breadth actually has the *smallest* average drawdown-before-resolution, not the biggest — so "more chop" is wrong. It still has a worse win rate than MID. **Confidence: the breadth-win-rate link itself is medium-high (seen three times now: missed-winners in EXP-002, actionable-trade winners in EXP-002, and here) — but the mechanism is genuinely unresolved.** My best honest guess, not yet tested: LOW breadth may mean fewer stocks are moving *at all* — smaller favorable moves rather than bigger adverse ones — which would show up as a flatter MFE distribution, not a deeper MAE one. That's a testable next step, not a finding.

## 2. What-if — joint filters, not one condition at a time

Grid-searched direction × DTE-bucket × breadth-state jointly against the full resolved population (target-or-stop, n=11,054, baseline win rate **12.9%**). Kept only combinations with n≥100 for this table (a larger cut, n≥30, is in the underlying data if you want the noisier tail):

| Filter | n | win rate | 95% CI | option mean return | shares mean return |
|---|---|---|---|---|---|
| **BEAR & DTE 11–20 & breadth MID** | 186 | **41.9%** | [34.8%, 49.0%] | −10.1% | **+0.24%** |
| BULL & DTE 31–45 & breadth HIGH | 495 | 38.2% | [33.9%, 42.5%] | −39.3% | −2.3% |
| DTE 31–45 & breadth HIGH (either direction) | 588 | 34.5% | [30.7%, 38.4%] | −31.7% | −2.5% |
| DTE 11–20 & breadth MID (either direction) | 668 | 32.9% | [29.4%, 36.5%] | −42.5% | −0.9% |
| BEAR & DTE 11–20 (any breadth) | 343 | 28.3% | [23.5%, 33.1%] | −33.9% | −4.3% |

**The headline scenario: BEAR & DTE 11–20 days & MID breadth.** Win rate more than triples the baseline (12.9% → 41.9%), CI entirely clear of baseline, across 10 of the 20 sessions with resolved outcomes. **This is the single most concrete "what changes must be made" candidate to come out of this whole investigation.**

**But — and this is the honest caveat that matters most — I bootstrapped the mean-return CI for this exact scenario before calling it a win, and it does not clear zero yet:** shares mean return +0.24%, CI **[−0.97%, +1.50%]** (n=155); option mean return −10.1%, CI **[−25.8%, +6.5%]** (n=133). **Confidence: medium-high on the win-rate lift itself, low on whether it's economically profitable yet.** Hitting target more often is real and measured; turning that into money, on this sample size, is not yet distinguishable from breakeven. That's a meaningfully different — and more honest — claim than "found a 42%-win-rate, profitable trade filter." It's "found a real hit-rate lift; the profit case needs more sessions to certify."

The second-best large-sample scenario (BULL & DTE 31–45 & HIGH breadth, 38.2% win rate) shows the opposite split: a real, large hit-rate lift with option returns still solidly negative (−39.3%) — a case where getting the direction right more often is not enough on its own, echoing the "correct thesis, unprofitable option" leak from `AVS-PLAN-001` §3.

## 3. What this means for "collate and decide"

Two testable, named hypotheses have come out of this pass, both stated precisely enough to design a real (holdout, base-rate-adjusted) test rather than another correlation table:
1. **The 21–30 DTE band has a specific geometry problem**, not a general thesis problem — worth the ATR-band-within-DTE-band slice that AVS-EXP-001 tried and failed to compute reliably. This is the concrete next request for the real scorer, not my approximation.
2. **BEAR & DTE 11–20 & MID breadth is the strongest win-rate lever found across three passes of this investigation** — real on hit rate, unproven on profit. The next step before any pipeline change is exactly what your own governance already requires: replicate on a second, non-overlapping window, and check whether the profit CI clears zero once more sessions accrue.

Nothing here is a recommendation to change code. It's the sharpest version yet of "here's what to test next and why," which is what you asked for.
