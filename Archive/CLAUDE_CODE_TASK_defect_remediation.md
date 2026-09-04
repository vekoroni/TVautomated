# Claude Code Task — Defect 2 First, Then Shadow-Module Fixes and Direction Conflict

## Your role

**Quant Developer.** Live pipeline, real capital, positions taken manually on
these numbers.

This brief supersedes Part B of
`CLAUDE_CODE_TASK_validation_and_direction.md`. It is resequenced because
`SPRINT_VALIDATION_FINDINGS.md` surfaced one defect that affects **live trading
decisions today** and several that do not.

## The sequencing principle

`empirical_option_ev.py` is a **shadow module with no authority** — it does not
gate, rank, filter or size. Its defects (strangle mispricing, NaN fabrication,
coarse percentiles) are real but touch no trading decision.

**Defect 2 is different.** It sits upstream in the actuarial state match and
affects every `win_rate` a trader reads. It goes first.

## Rules

1. **Do not fix what is correct by design.** `NO_MARKET` on archived EOD runs is
   what correct looks like — the evening pipeline runs on close data and option
   quotes are legitimately wide or absent. `tradeable=False` after the evening
   run is correct. Before flagging anything as broken, state what it would look
   like if the system were working properly.
2. **Investigate before fixing.** Every phase below has a read-only stage. Fixes
   are conditional on what the investigation finds.
3. **One change, one commit.** Golden diff after each.
4. **No position sizing, no Kelly, no size multipliers.** Sizing is manual.
5. **Do not touch** `_classify` thresholds, `_blend_win_probability`,
   `position_sizing_engine.py`, `final_decision_engine.py`, the Intelligence Lab,
   or Webull capture. Deferred for reasons recorded in prior reports.
6. **Confidence percentage on every conclusion.** "I could not determine this" is
   a complete answer.
7. **Nothing ships to production mid-session.** Fixes land between sessions with
   a tested rollback.

---

# PHASE 1 — Defect 2: frozen regime and trend dimensions

**The only production-affecting item. Do this first.**

## The finding

`layer2__vol_regime = NORMAL` and `layer2__trend_direction = SIDEWAYS` on
**every row of both runs** — ~1,300 distinct tickers, two weeks apart. Verified
independently in `SPRINT_VALIDATION_FINDINGS.md`.

These are 2 of the 10 EXACT match dimensions in `_find_similar_states`. If they
are constant, they carry zero discriminating information and every actuarial
match is effectively 8-dimensional.

**Why this matters more than anything else on the list:** `win_rate_5d/10d/20d`
appears on the trader's card and is one of the few fields that survived earlier
verification. It is still directionally real, but it is matched on fewer
dimensions than the design intends — and the two dead ones are precisely the
regime discriminators. The stated market philosophy is
`edge × frequency × size × regime alignment`; regime alignment is currently a
constant.

Related, same section: `layer2__recommended_hold_days ≈ 20` regardless of
horizon, which biases option-value pricing downward for 5D/10D exits.

## 1.1 — Investigate (READ-ONLY)

1. **Locate the writer.** Which stage computes `vol_regime` and
   `trend_direction`? Give `file:line`.
2. **Establish whether this is a defect at all.** Three possibilities, and they
   need different responses:
   - a defaulting bug — the real value is computed but not propagated
   - the values are genuinely never computed and a default is returned
   - `NORMAL`/`SIDEWAYS` is a legitimate fallback and the fields were never wired
     for this run type
   State which, with evidence.
3. **Check the database side.** In `actuarial_database_v6.parquet`, what is the
   distribution of `vol_regime` and `trend_direction`? **If the database itself
   is predominantly `NORMAL`/`SIDEWAYS`, then matching on a constant query value
   loses less than it appears to** — the dimension was low-information to begin
   with. This changes the severity materially, so establish it before proposing
   anything.
4. **Quantify the loss.** For a sample of 20 tickers spanning tiers, run the
   match twice: once as-is, once with realistic per-ticker `vol_regime` and
   `trend_direction`. Report how much `n_observations`, match tier, and
   `win_rate_5d/10d/20d` move.

   **This is the number that decides whether to fix.** If win rates barely move,
   the frozen dimensions are cosmetic. If they move by several points, every card
   read this week was based on a materially wrong base rate.
5. **Same for `recommended_hold_days`.** Is ~20 a computed value or a default?

## 1.2 — Fix, conditional on 1.1

**Only if 1.1(4) shows material movement in win rates.**

Fix at the writer, not with a local patch in the query engine — a local override
would make the query engine disagree with every other consumer of the same field.

**Tests required:**
- `vol_regime` and `trend_direction` take more than one value across a run
- Their distribution is plausible against the database's own distribution
- A ticker in a clearly trending state does not report `SIDEWAYS`

**Blast radius — report before committing:** these fields feed the actuarial
match, and the match feeds `win_rate`, which feeds `_blend_win_probability` in
`ev_engine_v2.py`, which feeds `ev_status`, which `final_decision_engine`
hard-gates on. **A fix here propagates to live verdicts.** Report how many rows
change tier and how many change `ev_status`.

If the blast radius is large, stop and report rather than committing. This may
warrant shadow-running before promotion.

**Report. Stop. Wait.**

---

# PHASE 2 — Defect 1: the NaN quote gate

Shadow module, no authority, but the fix is trivial and the current behaviour
violates the module's own contract.

## FIX-2A — `np.nan` bypasses the market-quote gate

`compute_empirical_option_ev` gates with `if bid is None or bid <= 0`. Values
from a pandas row are `np.nan`, not `None`, and `np.nan <= 0` evaluates `False`.
The row falls through; every per-percentile `r_i` is `NaN`; and because
`NaN >= 1.0` is also `False`, `p_double` sums to a **fabricated `0.0`** rather
than nulling.

**576/925 and 600/969 of nominal `OK` rows are this bug.** The module's own
docstring states a confidently wrong number is worse than no number. This is
that failure, in the module that declares it.

**Fix:** use `pd.isna()` / `math.isnan()` checks throughout the input gate, not
`is None`.

**Sweep:** grep the module for every other `is None` guard on a numeric field
pulled from a DataFrame row. Same bug class. Fix them in this commit and list them.

**Tests:**
- `bid = np.nan` → nulls, not `0.0`
- `bid = None` → nulls (unchanged)
- `bid = 0` → nulls (unchanged)
- A valid row is unchanged — the regression that matters
- `p_double` is never `0.0` when `emp_expected_r` is null

**Report the corrected usable-row count** and how it compares to the 27.7% /
26.8% in `SPRINT_VALIDATION_FINDINGS.md`.

---

# PHASE 3 — Strangle handling in the empirical module

`empirical_option_ev.py` has no strangle payoff model, yet `STRANGLE`-labelled
rows produce output — reconstruction showed they default to `CALL` and get priced
as a naked long call. **54% of the rows qualifying for the sprint's headline were
strangles priced as one leg of a two-sided position.**

## FIX-3A — Hard-null strangles

Do **not** build a strangle payoff model. Three reasons: the Lab sprint already
established `LAB_STRANGLE_POLICY` with exclusion available; Options Intelligence
sets `option_value_at_target = mark` for strangles so no payoff is modelled
upstream either; and PHANTOM already hard-vetoes them as
`MISSING_PRIMARY_DIRECTION`. Three components treat them as unhandled. Be the
fourth, explicitly.

- `emp_quality_flag = 'STRANGLE_UNSUPPORTED'`, all `emp_*` values null
- **Remove the `default="CALL"` fallback on direction.** A missing direction must
  null the row, never silently become a call. That default is the actual defect;
  the strangle case merely exposed it.

**Tests:**
- `options_direction = STRANGLE` → nulls with the new flag
- Missing/empty direction → nulls, not a call
- `CALL` and `PUT` rows unchanged

---

# PHASE 4 — Percentile resolution

13 points is too coarse for tail probabilities. `emp_p_double` can only take 14
discrete values, and 0.15 sits exactly on one of them with a hard gap to 0.25 —
which is what made the sprint's headline an artefact.

The census showed median `n` in the thousands to hundreds of thousands, so the
samples support far finer resolution.

## FIX-4A — Widen the percentile set

Propose a set and justify it from the sample-size census **before implementing**.
Requirements: dense enough that `emp_p_double` is effectively continuous; still
weighted correctly for uneven spacing; and tails resolved better than a single
p01/p99 boundary point.

**Report:** the new achievable-value set for `emp_p_double`, and the corrected
threshold table (0.05 / 0.10 / 0.15 / 0.20 / 0.25 / 0.30) after Phases 2, 3 and 4
combined. **Does any real signal survive once strangles are excluded, NaN rows
null correctly, and the bins are fine-grained?**

That is the honest re-test of the observation that started this work.

---

# PHASE 5 — Direction field conflict

Formerly Part B. Now better motivated: A3 demonstrated the direction ambiguity
reaches `empirical_option_ev.py`, which was that investigation's premise.

## 5.1 — Investigate (READ-ONLY)

1. Does `StateVector` construction use direction? Which field — bare `direction`
   or `options_direction`? `file:line`.
2. **Is direction one of the 10 match dimensions?** If yes, the 235 put rows with
   a wrong direction are matched against the wrong historical population, and
   every downstream number for them is drawn from the wrong distribution.
3. Which field is authoritative? Cross-check both against
   `live_contract_symbol` — the OCC encoding carries C/P unambiguously.
4. Enumerate every consumer of the bare `direction` field. State for each whether
   it branches or merely displays.

## 5.2 — Fix, conditional on 5.1

**Constraint:** direction is already resolved independently in at least five
components. **Do not add a sixth local resolution** without recording it.

Prefer, in order: read `options_direction` where it is already authoritative; or
one single mapping, commented as technical debt, with canonical direction
resolution named as a follow-on. **Do not attempt canonical resolution across all
components here** — separate initiative, and it would make everything in this
brief unattributable.

**Tests:** a `PUT` row produces a put payoff; a `CALL` row is unchanged
(the regression that matters); strangles behave per Phase 3.

---

# PHASE 6 — Re-validate A1

`SPRINT_VALIDATION_FINDINGS.md` found a significant negative Spearman between
`ev_conf_adj` and `emp_expected_r` — −0.305 (p=6.2e-9) and −0.162 (p=0.0019) on
the coverage-controlled subset.

That was the one sprint result that survived scrutiny. **But it was computed
against an `emp_expected_r` now known to be defective** — NaN fabrication,
strangle mispricing, and a contaminated actuarial match on both sides.

Re-run A1 after Phases 1–4. Report the corrected Spearman for both runs and
whether the negative association survives.

**If it does, it is a genuine and important result:** the ranking currently
driving live trades associates with *lower* empirical expectancy. If it
disappears, the earlier finding was an artefact and should be retracted.

---

# Final report — `DEFECT_REMEDIATION_REPORT.md`

- Phase 1: investigation findings, the win-rate movement table, whether fixed and why
- Phases 2–4: changes with commit SHAs, tests failing-then-passing
- The corrected threshold table and whether any signal survives
- Phase 5: findings with `file:line`; changes if any
- Phase 6: corrected Spearman, survives or not
- Golden diff, every change attributed
- **What I could not determine, and why**
- Rollback procedure, tested

## Standing limitation

No closed loop from signal to realised outcome exists. These fixes make the
measurements **more correct** — they do not establish that either ranking
predicts profitable trades. Only realised outcomes can, and they are not being
captured.

`Trade_Idea_Id` exports, so the join key exists. State this again in the final
report. Three sprints have now reached the same conclusion independently.
