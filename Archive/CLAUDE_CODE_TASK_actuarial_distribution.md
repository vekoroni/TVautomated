# Claude Code Task — Actuarial Distribution Retention + Empirical Option EV

## Your role

**Quant Developer.** This pipeline trades live capital. Positions are taken
manually on the strength of these numbers.

## The finding this sprint acts on

`actuarial_query.py:query()` calls `_find_similar_states(state)`, which returns
`similar_states` — a DataFrame of the matched historical sample carrying raw
`outcome_5d_return`, `outcome_10d_return`, `outcome_20d_return` per row. **The
full empirical return distribution, conditional on matched state.**

`_calculate_outcomes(similar_states)` reduces it to ~20 scalars and the sample is
discarded. The reduction includes:

```python
ev_5d = (wr_5d * med_gain_5d) + ((1 - wr_5d) * med_loss_5d)
```

Win rate × **median** win, plus loss rate × **median** loss. For a fat-tailed
distribution the median winner is far from the mean winner, and for a convex
payoff (long options) the tail *is* the edge. This two-point collapse is
structurally blind to it.

The expensive work — matching millions of rows across 9 dimensions — already
happens. This sprint stops discarding its output.

## Rules

1. **Phase gates are hard.** Report and stop at each one.
2. **One change, one commit.** No batching, no drive-by refactors.
3. **Additive only.** Every existing field keeps its current name, type and
   value. This sprint adds columns; it changes none.
4. **No authority.** The new EV does not gate, rank, filter, veto or replace
   anything. It is a shadow computation reported alongside the existing numbers.
5. **No position sizing, no Kelly, no size multipliers.** Sizing is manual and
   stays manual. `kelly_fraction` already exists in `ActuarialOutcomes` — do not
   touch it, do not extend it, do not consume it.
6. **Never weaken fail-closed behaviour** or modify sovereign/permission constants.
7. **Confidence percentage on every conclusion.** "I could not determine this" is
   a complete answer.

## Out of scope

`ev_engine_v2.py` internals, `_classify` thresholds, `_blend_win_probability`,
the `stop_price`/`target_price`/`direction` wiring defects, the Intelligence Lab,
Webull capture, `position_sizing_engine.py`, `final_decision_engine.py`.

Those are real and documented in `EV_ENGINE_VERIFICATION.md`. They are not this
sprint. Note anything you notice in passing and move on.

---

# PHASE 0 — Baseline and feasibility

## 0.1 — Configuration management first

`ev_engine_v2.py` has **zero commits** — it has never been committed to this
repository, and a duplicate exists at `vanguard/ev_engine_v2.py`.

Before anything else:
1. Report the state of both files and which one live callers resolve to.
2. Commit the live one. Tag `actuarial-dist-v0-baseline`. Record the SHA.
3. Do **not** delete the duplicate this sprint — flag it.

Check the same for `actuarial_query.py`: is it tracked, does it have history?
Report before editing.

## 0.2 — Sample size census

The match ladder (`EXACT → RELAXED → ANALOGUE → UNKNOWN`) accepts a minimum of
10 observations. **Percentiles from 10 points are noise.**

Across a full run's worth of queries, report the distribution of
`n_observations` broken down by match tier. State what fraction of rows would
support a usable empirical CDF at thresholds of 100, 500 and 1000 observations.

**This determines whether the sprint is worth completing.** If most rows match on
a few dozen observations, the empirical CDF is not usable and you should stop and
report rather than build it.

## 0.3 — Confirm the sample is genuinely discarded

Verify that `similar_states` is not already retained or persisted anywhere. If
some path already keeps it, say so — that changes the design.

## 0.4 — Baseline

Record the current test suite pass/fail count. Freeze a reference output for one
run so later diffs are attributable.

**Report. Stop. Wait.**

---

# PHASE 1 — Retain the distribution

Proceed only if 0.2 shows adequate sample sizes.

## FIX-AD-1 — Emit return percentiles from the matched sample

In `_calculate_outcomes()`, alongside the existing scalars, compute percentiles
of `rets_5d`, `rets_10d`, `rets_20d` — the series already in scope.

**Percentile set:** p1, p5, p10, p20, p30, p40, p50, p60, p70, p80, p90, p95, p99.
Thirteen points per horizon. Enough to reconstruct a CDF with usable tails; small
enough to carry through the pipeline.

Add to `ActuarialOutcomes` as new declared fields. Suggested naming —
confirm against existing convention before committing:

```
ret_pctl_5d_p01 ... ret_pctl_5d_p99
ret_pctl_10d_p01 ... ret_pctl_10d_p99
ret_pctl_20d_p01 ... ret_pctl_20d_p99
n_obs_5d, n_obs_10d, n_obs_20d
```

**Requirements:**
- Percentiles computed on the same `.dropna()` series the existing scalars use,
  so they are consistent with `win_rate` and `median_gain` by construction
- Per-horizon `n` — the three horizons can have different non-null counts
- Absent horizon columns → nulls, never zeros. **Zero is a valid return; null is
  not the same thing.** This is the `Vetoes_Count` failure mode; do not repeat it
- `_empty_outcomes()` returns nulls for all new fields

**Sanity test — required.** For each horizon, verify against the existing
scalars computed from the same sample:
- `p50` ≈ median of the full series
- fraction of percentile points above zero ≈ `win_rate`
- `median_gain_if_up` sits between the p50 and p90 of the positive tail

If those don't reconcile, the percentiles are being computed on a different
series than the scalars and the change is wrong.

## FIX-AD-2 — Carry the fields through to export

Trace the path from `ActuarialOutcomes` to the exported CSV. Add the new fields
at every hop.

**Watch specifically for whitelist filters.** The Intelligence Lab drops fields
via `_slim_lab_payload()`'s allow-list, which is why ten `Horizon_*`/`Trigger_*`
fields have always been blank in the export. Check every intermediate stage for
the same pattern and report what you find.

**Golden diff after each commit. Only the new columns may appear. Any existing
column that moves is a stop condition.**

**Report. Stop. Wait.**

---

# PHASE 2 — Empirical option EV (shadow)

New module. **Do not modify `ev_engine_v2.py`.**

## The computation

For each candidate with a selected contract:

```
For each percentile point r_i in the empirical CDF (horizon = hold window):
    S_i      = live_spot × (1 + r_i)
    value_i  = Black-Scholes(S_i, strike, DTE − hold_days, vol, ...)
    R_i      = (value_i − ask) / ask

E[R]        = mean over R_i, weighted by percentile spacing
P(R ≥ 0)    = fraction of points with R_i ≥ 0
P(R ≥ 1.0)  = fraction with R_i ≥ 1.0        ← the doubling probability
P(R ≥ 2.0)  = fraction with R_i ≥ 2.0
P(R ≤ −1.0) = fraction at total loss
E[R | win], E[R | loss], skew
```

**Design notes, each deliberate:**

- **Price at the exit horizon, not expiry.** A 3–12 day hold on a 21-DTE contract
  exits with time value remaining. Terminal-payoff EV systematically understates
  a swing trade. Use `DTE − hold_days` remaining.
- **Everything on the ask, never the mid.** Median live contract spread across
  the book is ~32%. EV on mid is fiction.
- **Empirical distribution, no lognormal.** This is the point of the sprint —
  the database has already measured the real tails on your universe. Do not fit
  a parametric distribution to the percentiles.
- **Percentile spacing is uneven** (p1→p5 is 4 points, p40→p50 is 10). Weight
  correctly. Getting this wrong biases E[R] toward the dense middle and hides
  exactly the tail this sprint exists to expose.
- **Horizon selection** must match the actual hold window, not the DTE.

## Quality gates — emit nulls, not numbers

The output is only as good as its inputs. Set `emp_quality_flag` and **emit
nulls, not values**, when:

- `n_observations` below the Phase 0.2 threshold
- No two-sided market (bid ≤ 0)
- Live quote older than 30 minutes
- Match tier is `UNKNOWN`
- `forecast_vol / live_iv ≥ 2.0`

A confidently wrong `P(R ≥ 1.0)` is worse than no number, because it looks precise.

## Emitted columns

```
emp_expected_r, emp_p_profit, emp_p_double, emp_p_triple,
emp_p_total_loss, emp_e_r_given_win, emp_e_r_given_loss,
emp_skew, emp_n_obs, emp_horizon_used, emp_quality_flag
```

## Constraint restated

Nothing branches on these. No consumer changes. They sit beside `ev_conf_adj`
and `ev_status` so the two can be compared.

**Report. Stop. Wait.**

---

# PHASE 3 — Comparison and regression

1. **Full test suite.** Pass count ≥ Phase 0 baseline. Any new failure is a blocker.
2. **Golden diff.** Every changed column attributed to one commit. Existing
   columns unchanged.
3. **Rank comparison.** For every archived run available, produce the top 20 by
   `ev_conf_adj` and the top 20 by `emp_expected_r`. **Report the overlap.**
   A low overlap is a finding, not a failure — it means the two disagree, and
   only realised outcomes can settle which is right.
4. **The headline number.** Across the book, report the distribution of
   `emp_p_double`, and specifically: **how many rows currently classified
   `WEAK_PASS` or `PASS_SMALL` have `emp_p_double > 0.15`?**

   That is the direct test of the observation that started this work — weak-EV
   trades delivering 100%+ returns. If a meaningful set exists, the sprint has
   found something real. If not, say so.
5. **Multi-run.** Confirm across every archived run folder, not one day.

## Final report — `ACTUARIAL_DISTRIBUTION_SPRINT_REPORT.md`

- Status per change, with commit SHA
- Sample-size census from 0.2 and its implications
- Percentile reconciliation evidence from FIX-AD-1
- Golden diff table
- Rank overlap between V2 and empirical EV
- The `emp_p_double` distribution and the WEAK_PASS cross-tab
- **What I could not determine, and why**
- Rollback procedure, tested

---

# The standing limitation

There is no closed loop from signal to realised outcome. This sprint produces a
**better-founded** measurement — empirical rather than assumed, distribution
rather than two medians, net of real spread rather than mid.

**It does not prove the new number predicts better than the old one.** Only
realised outcomes can do that, and they are not being captured.

State this plainly in the final report. `Trade_Idea_Id` now exports, so the join
key for an outcome ledger exists — flag it as the highest-value follow-on.
