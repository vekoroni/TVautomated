# Claude Code Task — Sprint Validation + Direction Field Conflict

## Your role

**Quant Developer.** Live pipeline, real capital, positions taken manually on
these numbers.

Two parts. **Part A is validation** of two results from
`ACTUARIAL_DISTRIBUTION_SPRINT_REPORT.md` that may be artefacts rather than
findings. **Part B is an investigation** into a data conflict, with a fix only
if the investigation shows one is needed.

Part A is under an hour. Do it first. Part B's scope depends on what you find.

## Rules

1. **Do not fix what is correct by design.** Several things in this pipeline look
   like defects and are not: `NO_MARKET` on archived EOD runs is what correct
   looks like (the evening pipeline runs on close data; option quotes at EOD are
   legitimately wide or absent). `tradeable=False` after the evening run is
   correct. Before flagging anything as broken, state what it would look like if
   the system were working properly.
2. **Part A changes no code.** Analysis only.
3. **Part B: investigate before fixing.** The fix is conditional on the finding.
4. **One change, one commit.** Golden diff after each.
5. **No position sizing, no Kelly, no size multipliers.** Sizing is manual.
6. **Do not touch** `_classify` thresholds, `_blend_win_probability`,
   `position_sizing_engine.py`, `final_decision_engine.py`, the Intelligence Lab,
   or Webull capture. All deferred for reasons recorded in prior reports.
7. **Confidence percentage on every conclusion.** "I could not determine this"
   is a complete answer.

---

# PART A — Validate two sprint results

## A1 — Is the zero rank overlap real, or a coverage artefact?

The sprint reported **0/20 overlap** between the top 20 by `ev_conf_adj` and the
top 20 by `emp_expected_r`, in two independent runs.

**The alternative explanation:** `emp_expected_r` only exists for the ~35% of
rows with usable quotes. If `ev_conf_adj`'s top 20 sits largely in the 65% that
were nulled, the two lists **cannot** intersect and zero overlap is arithmetic,
not disagreement.

For both runs (`20260731_083130`, `20260723_072618`), report:

1. Of the top 20 by `ev_conf_adj`, how many have a non-null `emp_expected_r`?
2. Restricted to rows where **both** measures exist, what is the top-20 overlap?
3. Spearman rank correlation between the two, on that common subset only.
4. The `emp_quality_flag` breakdown for `ev_conf_adj`'s top 20.

**Interpretation:**
- Few of V2's top 20 have an `emp_` value → zero overlap is largely arithmetic.
  The finding is much weaker than reported.
- Most have values and the overlap is still ~0 with near-zero or negative rank
  correlation → the two genuinely disagree, and that is a real and serious result.

State which, with confidence.

## A2 — Is the 4.5% `emp_p_double` signal real, or a bin-boundary effect?

The sprint reported 4.4–4.5% of `WEAK_PASS`/`PASS_SMALL` rows with
`emp_p_double > 0.15`, reproducing across two runs.

**The concern:** with 13 percentile points, `emp_p_double` can only take values
at ~1/13 intervals (0.077, 0.154, 0.231, ...). The 0.15 threshold sits almost
exactly on a bin boundary. The report's own percentile table shows `p75` and
`p90` both reading **exactly 0.150** — the tell.

For both runs:

1. Re-run the cross-tab at thresholds **0.05, 0.10, 0.15, 0.20, 0.25, 0.30**.
2. Report the full histogram of distinct `emp_p_double` values actually observed.
   Confirm or refute that they cluster at multiples of 1/13.
3. State whether the finding is stable across thresholds or an artefact of 0.15.

**Interpretation:** stable across thresholds → real signal. Collapses or explodes
between 0.10 and 0.25 → the 4.5% was the bin edge.

## A3 — Sanity-check three repeat names

`SJM`, `HRL` and `TRV` appear in the high-`emp_p_double` set in **both** runs
independently. These are defensive, low-volatility, dividend-paying names. A
doubling probability above 55% on Smucker's is implausible on its face.

For each, report: the matched sample's actual return distribution (the 13
percentiles), `n_observations`, match tier, the contract selected (strike, DTE,
ask), and the mapping from return percentile to option payoff.

**The question to answer:** is a >55% doubling probability plausible given that
return distribution and that contract? If not, something in the payoff mapping is
wrong — most likely the return-to-price transform, the horizon selection, or the
percentile weighting.

**A defect found here would invalidate A2's result**, so do A3 even if A2 looks
clean.

## Part A deliverable

`SPRINT_VALIDATION_FINDINGS.md` — A1, A2, A3 each with evidence, a plain verdict
(**real finding / artefact / inconclusive**), and confidence.

**Report. Stop. Wait.** Part B may proceed independently.

---

# PART B — The direction field conflict

## The finding

`EV_ENGINE_VERIFICATION.md` established that the bare `direction` field
disagrees with `options_direction` on **235 of 339 economically-PUT rows** — the
engine often evaluates them as CALLs.

This matters more than it did when first reported, because the empirical
distribution module now depends on the actuarial state match, and direction may
be part of that match.

## B1 — Investigate first (read-only)

Answer these before changing anything:

1. **Does `StateVector` construction use direction at all?** If so, which field —
   bare `direction` or `options_direction`? Give `file:line`.
2. **Is direction one of the 9 match dimensions** in `_find_similar_states`?
   If yes, a wrong direction returns a sample matched on the wrong state, and
   every downstream number for those rows is drawn from the wrong population.
3. **Does `empirical_option_ev.py` use direction** for the payoff mapping
   (call vs put)? If it reads the bare field, put payoffs are being computed as
   call payoffs on 235 rows.
4. **Which field is authoritative?** Trace both to their writers. Establish which
   reflects the actual contract selected — cross-check against
   `live_contract_symbol`, whose OCC encoding carries C/P unambiguously.
5. **Enumerate every consumer** of the bare `direction` field across the pipeline.
   State for each whether it branches on the value or merely displays it.

**Report B1 before proceeding.** The results determine whether B2 is a one-line
mapping or a wider change.

## B2 — Fix, conditional on B1

**If `empirical_option_ev.py` reads the bare field:** fix it there first. It is
new, has no other consumers, and put payoffs computed as call payoffs is an
outright correctness bug. Highest priority regardless of anything else in B1.

**If `StateVector` uses the bare field and direction is a match dimension:** this
is the serious case. 235 rows are matched against the wrong historical
population. Fix at the point of construction, using whichever field B1 established
as authoritative.

**If neither uses it:** the conflict is real but inert for these paths. Report
that, fix nothing, and record it as a known inconsistency.

### Constraint on how you fix it

Direction is already resolved independently in at least five components
(Discovery, Options Intelligence, morning candidates, EIL, the Lab). **Do not add
a sixth local resolution** without recording it.

Prefer, in order:
1. Read `options_direction` directly where it is already the authoritative field.
2. If a mapping is unavoidable, put it in **one** place, comment it as technical
   debt, and name the canonical-direction-resolution work as a follow-on.
3. Do **not** attempt canonical direction resolution across all components in
   this sprint. It is a separate initiative and would make everything here
   unattributable.

### Tests required

- A row with `options_direction = PUT` produces a **put** payoff, not a call
- A row with `options_direction = CALL` is **unchanged** — this is the regression
  that matters most
- `STRANGLE` rows behave as they did before (do not fix strangles here; the Lab
  sprint's `LAB_STRANGLE_POLICY` covers that ground and it is out of scope)
- Direction derived from `live_contract_symbol`'s OCC encoding agrees with
  `options_direction` wherever both exist; report any row where it does not

### Blast radius — report before committing

- Rows whose direction changes, by original value
- If `StateVector` was affected: how many rows now match a different historical
  sample, and how much `win_rate` / percentiles move for them
- `emp_expected_r` and `emp_p_double` before and after for affected rows
- **Whether A2's headline result changes** — if the 4.5% figure moves materially
  once direction is correct, that is a significant finding in its own right

---

# Final report — `VALIDATION_AND_DIRECTION_FIX_REPORT.md`

- Part A: A1, A2, A3 verdicts with evidence and confidence
- Part B: B1 findings with `file:line`; B2 changes with commit SHAs
- Blast radius table
- Whether the sprint's headline results survive validation
- **What I could not determine, and why**
- Rollback procedure, tested

## Standing limitation

There is still no closed loop from signal to realised outcome. Part A can
establish whether the sprint's findings are statistically real. **It cannot
establish whether either ranking predicts profitable trades.** Only realised
outcomes can, and they are not being captured.

Do not overstate what a validated finding means. "The signal is real and not an
artefact" is a much weaker claim than "the signal is tradeable."
