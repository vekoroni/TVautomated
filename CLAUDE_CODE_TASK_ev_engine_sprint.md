# Claude Code Task — EV Engine V2: Verify, Fix, Extend

## Your role

**Quant Developer.** You are working on the EV engine that scores every candidate
in a live trading pipeline. Real capital is committed manually downstream on the
strength of these numbers.

## Rules

1. **Phase gates are hard.** Report and stop at each. Do not begin a phase until
   the previous one is confirmed.
2. **Phase 0 is read-only.** No edits. It exists to confirm or refute the
   findings below before any code changes.
3. **One fix, one commit.** No batching, no drive-by refactors.
4. **Golden diff after every change.** Any column that moves and shouldn't is a
   stop condition.
5. **No Kelly, no position sizing, no sizing recommendations of any kind.** PSE
   is retired; sizing is a manual trader decision and stays that way. If a change
   would emit a size or size multiplier, do not make it.
6. **Never weaken fail-closed behaviour** or modify sovereign/permission constants.
7. **Confidence percentage on every conclusion.** "I could not determine this" is
   a complete answer.

## Files in scope

- `ev_engine_v2.py` — primary
- `eod_candidate_engine.py` — the `ev2_` → `ev_structural` rename
- `avshunter_options_intelligence.py` — the V1 EV, for comparison only
- `actuarial_query.py` — read-only, to establish what the win rate measures

Out of scope: the Intelligence Lab, the Pipeline Interpreter, Webull capture,
Phase 7 contract selection.

---

# PHASE 0 — Verification (READ-ONLY)

The findings below were derived from `ev_engine_v2.py` and from
`morning_validated_trades_20260731_083130.csv` (952 rows). **Confirm or refute
each.** Where a finding is confirmed, state the confirming evidence. Where it is
wrong, say so plainly — that is the more valuable result.

## V1 — Put clamp in `_struct_ev`

`ev_engine_v2.py:245`:

```python
rr = (x.target_price - x.entry_price) / max(x.entry_price - x.stop_price, 0.001)
lm = -(em / max(rr, 0.5))
```

**Claim:** for a PUT, `target < entry` and `stop > entry`, so the numerator is
negative and the denominator clamps to `0.001`. `rr` is then large and negative,
and `max(rr, 0.5)` floors it at `0.5` — so `lm = -2 × em` for every put,
discarding the actual stop distance entirely.

**Measured:** 339 of 339 put rows hit the 0.5 floor.

**Verify:** reproduce that count. Confirm `invalidation_level` / `stop_price` is
populated and non-trivial for those rows (i.e. real data is being thrown away,
not absent data being defaulted).

## V2 — `contract_eff` bypass

`ev_engine_v2.py:335`:

```python
def _contract_eff(self, x, cev, sev):
    if abs(sev) < 0.001: return 1.0
    return _clamp(cev/abs(sev), 0.30, 1.30)
```

**Claim:** 490 of 952 rows (51.5%) have `|ev_structural| < 0.001`, so
`contract_eff` returns 1.0 and `ev_contract` — the only term modelling the
option's convex payoff — never influences `ev_final`.

**Verify the count, then answer:** what is the distribution of `cev/abs(sev)` for
those 490 rows if the cutoff were removed? **This decides whether the cutoff is a
defect or a necessary numerical guard.** With `sev ≈ 1e-4`, the ratio may be
enormous — in which case the cutoff is load-bearing and must be replaced, not
deleted.

## V3 — Unreachable classification bands

`ev_engine_v2.py:346`: `PASS_HIGH ≥ 0.25`, `PASS ≥ 0.10`, `PASS_SMALL ≥ 0.00`.

**Measured:** max `ev_conf_adj` across the entire book is **0.0234**. The `PASS`
threshold is 4× larger than the largest value that exists. Result: 924 rows
`PASS_SMALL`, 28 `WEAK_PASS`. Two of five bands ever fire.

**Verify the max and the distribution.** Then establish whether the thresholds
were ever calibrated — check git history and comments for the origin of 0.25 and
0.10, and whether they were written against a different scale.

## V4 — The scale question (the important one)

`ev_structural / expected_move` has a median of ~6e-5. For puts the formula
reduces to `em × (3p − 2)`, which implies a blended win probability of
approximately 0.6667 on essentially every put row.

**A blended win probability of 2/3 ± 0.005 across 339 different stocks is
implausible.** Either `_blend_win_probability` is returning a near-constant, or
the reduction is wrong.

**Settle it empirically.** Instrument the engine — a temporary local script, not
a source edit — to dump per row: `p` from `_blend_win_probability`, `em` selected,
`sev`, and each component of `ms` (`predictability_score`, `bmps`,
`calibration_confidence`, `flow_score`). Report the distribution of `p`.

**Also establish the unit of `expected_move`.** The Lab card displays
"EXPECTED MOVE 6–10D 1.77%" while `expected_move_10d` holds `1.77`. If a
percentage is being consumed as a fraction anywhere in the chain, that is a
100× error and likely the root of the whole scale problem. Trace it from
`l3_expected_move_*` through `ev_inputs_from_row` into `_struct_ev`.

## V5 — Blast radius

`eod_candidate_engine.py:2199` writes `ev2_ev_structural` into the column name
`ev_structural`, which is V1's name for a different quantity (V1:
`avshunter_options_intelligence.py:4215`, dollars per share).

**Enumerate every consumer** of `ev_structural`, `ev_conf_adj`, `ev_status`,
`ev_final` and `ev_selected` across the pipeline — including `morning_gate.py`
and the Lab. For each, state whether it branches on the value or merely displays
it.

**This determines whether any threshold change is contained or pipeline-wide.**
My expectation is pipeline-wide, which is why thresholds are deferred in Phase 3.

## V6 — Actuarial win rate semantics

Read `actuarial_query.py`. Establish precisely what `win_rate_5d/10d/20d`
measures: probability of what event, over what window, against what threshold.

**This is a prerequisite for the distribution module.** Layer 1 proposes deriving
a drift from the win rate via `μ = σ√T × Φ⁻¹(win_rate)`, which is only valid if
the win rate is P(price moves favourably over the horizon). If it measures
something else — a fixed percentage threshold, a different window — the drift is
wrong and the module must not be built on it.

## V7 — Additive penalty on a multiplicative scale

`ev_final = (epa × ce × em × rm × cb) − rp`, where `rp ∈ {0, 0.05, 0.12, 0.25,
0.50}` and the bracketed term is of magnitude ~1e-3.

**Claim:** any row with `rp > 0` has `ev_final ≈ −rp`, so the entire EV
computation is irrelevant to its own output.

**Verify:** count rows with `rp > 0` and compare `ev_final` to `−rp` for those rows.

## Phase 0 deliverable

`EV_ENGINE_VERIFICATION.md` — V1 to V7, each marked **CONFIRMED / REFUTED /
INCONCLUSIVE** with evidence and confidence. Plus a recommendation on whether
Phase 1 should proceed as scoped.

**Stop here. Report and wait.**

---

# PHASE 1 — The unambiguous fix

Proceed only if V1 is CONFIRMED.

## FIX-EV-1 — Direction-aware structural R:R

```python
rr = abs(x.target_price - x.entry_price) / max(abs(x.entry_price - x.stop_price), 0.001)
```

**Why:** the existing form assumes `target > entry > stop`, which holds only for
long calls. It is not a put-specific patch — it makes the expression correct for
both directions.

**Tests required:**
- A put with target below entry and stop above entry yields `rr > 0.5` where the
  geometry supports it
- A call is **unchanged** — this is the regression that matters most
- A put with a tight stop and a put with a wide stop now produce *different*
  `ev_structural`
- Degenerate case: `entry == stop` still clamps safely

**Blast radius — report before committing:**
- `ev_structural` before/after for all 339 put rows: how many move positive→
  negative and negative→positive
- Same for `ev_conf_adj` and `ev_status`
- Confirm **zero** call rows change

Expect the direction of change to vary per row. That is correct behaviour, not
noise — the fix replaces a constant with a real measurement.

**Stop. Report. Wait.**

---

# PHASE 2 — The convexity path

Proceed only if V2 is CONFIRMED **and** the ratio distribution from V2 shows the
cutoff is safely replaceable.

These two changes interact. **Do them as separate commits** or attribution is lost.

## FIX-EV-2 — Replace the `0.001` bypass with a scale-invariant guard

The problem the cutoff solves is real: `cev/abs(sev)` explodes as `sev → 0`. The
problem it creates is that half the book never sees its own option economics.

Replace division-by-`sev` with a bounded transform that degrades gracefully
rather than switching off. Propose the specific form in your report **before**
implementing, with the resulting ratio distribution for all 952 rows under each
candidate. Do not pick one unilaterally.

Requirements: no discontinuity at any `sev`; finite for `sev = 0`; monotonic in
`cev`; and for large `|sev|` it must reproduce today's behaviour closely enough
that those rows barely move.

## FIX-EV-3 — Raise the convexity ceiling

`_clamp(..., 0.30, 1.30)` discards any convexity above 1.3×. For a long option —
capped loss, unbounded gain — that is the asymmetry the instrument exists to
capture.

Raise the upper bound. **Report the ratio distribution first and propose the new
ceiling from the data**, rather than picking a round number. State how many rows
sit above the current 1.30 and by how much.

## Deliberately NOT in this phase

- `cb = self._conv_boost(x) if sev > 0 else 1.0` — boosting a negative number
  makes it more negative. Correcting this requires deciding what convexity
  *means* for a negative-EV trade. That is a modelling decision, not a bug fix.
  **Note it, do not change it.**
- `_classify` thresholds — see Phase 3.
- The additive `rp` scale — same reason.

**Stop. Report. Wait.**

---

# PHASE 3 — Distribution module (REPORTING ONLY)

Proceed only if V6 established that the actuarial win rate supports a drift
derivation. **If V6 was inconclusive, stop and report — do not build on an
assumed semantic.**

## Hard constraint on this module

**It has no authority.** It does not gate, rank, filter, veto, or size. It emits
columns that sit alongside the existing ones. Nothing downstream branches on its
output in this sprint.

The pipeline already carries two EV engines sharing a column name. This is a
third computation and it must not become a third authority until it has been
compared against V2 over real outcomes.

## New module: `ev_distribution.py`

Do not modify `ev_engine_v2.py` to add this.

**Inputs:** live spot, strike, DTE, exit horizon, ask, `l3_forward_realised_vol`,
live IV, direction, actuarial win rate.

**Layer 1 — terminal distribution.** Lognormal on forecast vol. Drift from the
actuarial win rate per V6's finding. If V6 showed the win rate means something
else, use zero drift and say so in the output.

**Layer 2 — price at exit horizon, not expiry.** A 3–12 day hold on a 21-DTE
contract exits with time value remaining. Reprice with Black-Scholes at
`DTE − h` remaining. Terminal-payoff EV systematically understates a swing trade.

**Layer 3 — emit the distribution:**

| Column | Meaning |
|---|---|
| `dist_expected_r` | E[R] in R-multiples, **net of the ask** |
| `dist_p_profit` | P(R > 0) |
| `dist_p_double` | **P(R ≥ 1.0)** |
| `dist_p_triple` | P(R ≥ 2.0) |
| `dist_p_total_loss` | P(R ≤ −1.0) |
| `dist_e_r_given_win` | E[R \| R > 0] |
| `dist_e_r_given_loss` | E[R \| R < 0] |
| `dist_skew` | Skew of the R distribution |
| `dist_vol_forecast_over_live_iv` | Forecast σ ÷ live IV |
| `dist_quality_flag` | See below |

`dist_p_double` is the point of this module. It is the statistic that explains
weak-EV trades delivering 100%+ returns, and nothing in the pipeline computes it.

**Layer 4 — cost realism.** Every figure computed on the **ask**, never the mid.
Median live contract spread across the book is ~32%; EV on mid is fiction.

**Layer 5 — quality gating on the inputs.** The module's output is only as good
as the vol forecast. Set `dist_quality_flag`:
- `VOL_DIVERGENCE` when `forecast_vol / live_iv ≥ 1.5`
- `BLOCK` at `≥ 2.0` — emit nulls, not numbers
- `NO_MARKET` when bid ≤ 0
- `STALE` when the live quote is older than 30 minutes

A confidently wrong `P(R ≥ 1)` is worse than no number, because it looks precise.

## Required disclosures in the module docstring

- Lognormal understates fat tails, so `dist_p_double` is **conservative** for
  far-out targets
- Terminal-horizon pricing does not model path-dependent early exit
- The drift derivation rests on V6's finding — cite it explicitly

**Stop. Report. Wait.**

---

# PHASE 4 — Regression, comparison, report

1. **Full test suite.** Pass count ≥ the Phase 0 baseline. Any newly failing
   test is a blocker.
2. **Golden diff.** Every changed column attributed to exactly one fix.
3. **Rank comparison.** For every archived run available, produce the top 20 by
   V2 `ev_conf_adj` and the top 20 by `dist_expected_r`. Report the overlap.
   **A low overlap is a finding, not a failure** — it means the two disagree and
   only outcomes can settle which is right.
4. **Multi-run.** Run across every archived run folder. Confirm the fixes hold
   beyond one day.

## Final report — `EV_ENGINE_SPRINT_REPORT.md`

- Status per fix, with commit SHA
- Test evidence: failing-then-passing for each
- Golden diff table, every change attributed
- Blast radius for FIX-EV-1: rows changed, direction of change
- Rank overlap between V2 and the distribution module
- **What I could not determine, and why**
- Rollback procedure, tested

---

# Deferred — do not start

- `_classify` threshold recalibration. Pipeline-wide blast radius per V5, and no
  ground truth to calibrate against until an outcome ledger exists.
- Additive `rp` rescaling. Same reason.
- `conv_boost` on negative `sev`. Modelling decision, not a fix.
- Renaming `ev_structural` to remove the V1/V2 collision. Correct, but touches
  every consumer; needs its own sprint.
- Anything involving position sizing.

## The standing limitation

There is no closed loop from signal to realised outcome. These changes alter
which trades surface, and **without outcome data neither of us can demonstrate
the new behaviour is better — only that it is different from what the code's own
comments claim.**

State this in the final report. The highest-value next piece of work is probably
not another algorithm; it is the outcome ledger that would let any of this be
evaluated. `Trade_Idea_Id` now exports, so the join key exists.
