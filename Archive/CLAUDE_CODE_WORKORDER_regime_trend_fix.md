# Claude Code Work Order — Regime/Trend Input Remediation

## Your role

**Quant Developer.** Live pipeline, real capital, positions taken manually on
these numbers.

This work order supersedes Phase 1.2 of `CLAUDE_CODE_TASK_defect_remediation.md`.
Phase 1.1 established the defect; two open questions must be resolved before the
fix can be designed correctly.

## What is already established — do not re-verify

From your own Phase 1.1 report, accepted:

- `vol_regime` is mathematically pinned to `NORMAL`:
  `avg_pct = 0.33×atr_pct + 33.5` is bounded in [33.5, 66.5], strictly inside the
  NORMAL band, because `bb_pct` and `iv_pct` are frozen at their 50.0 defaults.
- `trend_direction` is unconditionally `SIDEWAYS`: `ema21` and `ema50` are both
  0.0, so both comparisons are always `False`.
- Root cause: `vanguard/integration/orchestrator_adapter.py::_tech()`
  (lines 181–241) never sets `bb_width`, `bb_width_history`, `ivp_252d`,
  `iv_percentile`, `iv_rank`, `ema21`, `ema50` on `TechnicalData`.
- The database is **not** predominantly NORMAL/SIDEWAYS (38.3% / 48.9%). Both
  dimensions carry real discriminating power.
- `recommended_hold_days ≈ 20` is a documented conditional fallback, working as
  designed. **Not a defect. Do not touch it.**

## Rules

1. **Investigate before fixing.** Stages A and B are read-only and gate Stage C.
2. **Do not fix what is correct by design.** Before flagging anything as broken,
   state what it would look like if the system were working properly.
3. **One change, one commit.** Golden diff after each.
4. **No position sizing, no Kelly, no size multipliers.**
5. **Do not touch** `_classify` thresholds, `_blend_win_probability` internals,
   `position_sizing_engine.py`, `final_decision_engine.py`, the Intelligence Lab,
   Webull capture, or `recommended_hold_days`.
6. **Confidence percentage on every conclusion.** "I could not determine this" is
   a complete answer.
7. **Nothing ships mid-session.** Fixes land between sessions with a tested rollback.

---

# STAGE A — `bb_width` is computable (READ-ONLY)

## The challenge to your Phase 1.1 conclusion

Phase 1.1 reported `bb_width` "isn't available anywhere in this codebase, live or
archived." That is a statement about **storage**, not **computability**.

Bollinger Band width is `(upper − lower) / middle`, where the bands are a
20-period SMA of close ± 2 standard deviations. It requires **only closing
prices** — the same series you already fetch for EMA21/50 via
`polygon_data_fetcher.py`. `bb_width_history` for the percentile needs a longer
close series from the same source.

**Why this blocks the fix:** the damage estimate currently spans 5% to 40% of
tickers escaping NORMAL, depending on whether the `bb_width` term is dropped or
renormalised away. That is the difference between cosmetic and significant, and
it is unresolved only because a computable input was treated as unavailable.

## A1 — Establish computability

1. Confirm the close-price series available via `polygon_data_fetcher.py` is
   long enough for a 20-period SMA plus a 252-day percentile history.
2. Compute `bb_width` and `bb_width_history` for 20 tickers. Report success rate
   and any failures.
3. Check whether a Bollinger implementation already exists elsewhere in the
   codebase. **If one does, use it — do not write a second.** This codebase
   already resolves direction independently in five places; do not add a
   duplicate indicator calculation.
4. Same for `ivp_252d` / `iv_percentile` / `iv_rank`. `IVP` reaches the Lab card
   (65.7% for `T`), so an IV percentile exists somewhere in the pipeline.
   **Locate it.** If it is already computed upstream, the adapter fix may be
   plumbing rather than new calculation.

## A2 — Collapse the damage range

Re-run the Phase 1.1(4) comparison with `bb_width` and IV percentile properly
computed, not dropped.

**Sample: 100+ tickers, not 20.** Two of twenty moving >5pp is a 95% interval of
roughly 1–32% — too wide to size a fix against. Same reconstruction, more rows.

Report, with the full `vol_regime` and `trend_direction` distributions produced:
- % of tickers whose `vol_regime` changes
- % whose `trend_direction` changes
- Distribution of `win_rate_5d/10d/20d` movement — median, p75, p90, max
- % changing match tier, and in which direction

---

# STAGE B — Database provenance (READ-ONLY) — **THIS IS THE GATE**

## Why this is the highest-risk item

`actuarial_database_v6.parquet` holds `vol_regime` and `trend_direction` values
for 6,033,072 rows. The match compares your query-side value against those
stored values.

**If the database's values were computed by a different path — different ATR
window, different IV percentile lookback, different EMA periods, different ADX
threshold — then a "correct" query-side calculation that differs from the DB's
convention replaces a known mismatch with an unknown one.**

The current defect is at least legible: query side is always NORMAL/SIDEWAYS. A
convention mismatch is worse, because both sides vary and the disagreement is
invisible.

## B1 — Establish how the database's values were derived

1. Locate the database build code. Does it call the same
   `state_calculator.py::_calculate_volatility_regime` and
   `_calculate_trend_maturity`, or its own implementation?
2. If the same functions: was the `TechnicalData` passed to them fully populated
   at build time? **If the build path had the same adapter gap, the DB's values
   are also degenerate** — but the DB shows 38/43/19 and 49/27/25 splits, so it
   clearly was not. Establish what populated it.
3. If a different implementation: extract the exact parameters — ATR period,
   Bollinger period and standard deviations, IV percentile lookback, EMA periods,
   ADX period and threshold, and every band boundary.
4. **Reconcile.** Compute regime and trend for 20 tickers using both the DB's
   convention and `state_calculator.py`'s. Report agreement rate.

## B2 — The gate

- **Agreement ≥ 90%** → conventions are compatible. Proceed to Stage C.
- **Agreement < 90%** → **STOP AND REPORT.** The fix is no longer "wire the
  adapter"; it is "reconcile two calculation paths," which is different work
  requiring its own design. Do not proceed on your own judgement.
- **Cannot determine the DB's convention** → **STOP AND REPORT.** Do not guess.
  Shipping a query-side calculation against an unknown storage convention is
  worse than the current known defect.

**Report Stages A and B. Stop. Wait for confirmation before Stage C.**

---

# STAGE C — The fix (conditional on B2 passing)

## C1 — Populate the adapter

Fix in `orchestrator_adapter.py::_tech()`. Set the fields the calculators need:
`bb_width`, `bb_width_history`, `ivp_252d`, `iv_percentile`, `iv_rank`, `ema21`,
`ema50`.

**Constraints:**
- Use Stage B's established convention. Not a reasonable-looking one — the one
  the database uses.
- **Prefer plumbing over recalculation.** If IVP or EMAs already exist upstream,
  wire them through. Every new local calculation is a future divergence.
- **A missing input must fail loudly, not default.** The dataclass defaults are
  the entire cause of this defect. If a field cannot be computed, the row should
  carry an explicit `UNKNOWN` regime or trend, never a silent 0.0 or 50.0 that
  produces a confident wrong answer. **This is the most important line in this
  work order.**

**Tests:**
- `vol_regime` takes more than one value across a run; distribution plausible
  against the DB's 38/43/19
- `trend_direction` takes more than one value; plausible against 49/27/25
- A ticker in a clearly trending state does not report `SIDEWAYS`
- A ticker with genuinely missing data reports `UNKNOWN`, not a default
- The arithmetic bound is broken: `avg_pct` can now fall outside [33.5, 66.5]

## C2 — Tier downgrade semantics

Phase 1.1 found 3 of 20 dropping EXACT → RELAXED *because* the correction was
applied. The frozen combination co-occurred in the DB; the correct one does not.

**So the fix lowers the reported match tier and takes a 15-point confidence cut
into `_blend_win_probability` — on rows whose matches are now more correct.**

Left unhandled, confidence becomes anti-correlated with match quality for those rows.

**Report the numbers first. Do not implement a compensating adjustment without
approval.** Quantify:
- % changing tier after the fix, in each direction
- The confidence-weight impact
- Whether `n_observations` rises or falls for downgraded rows

Then **propose** an approach — no change, a flag distinguishing
"RELAXED because inputs were correct" from "RELAXED because data was thin", or
something else. Do not silently reverse the confidence cut; that would hide a
real reduction in match specificity.

## C3 — Full-book blast radius — **required before committing**

These fields feed the actuarial match → `win_rate` → `_blend_win_probability` →
`ev_status` → `final_decision_engine` hard gates. **This fix reaches live verdicts.**

Report across a full run:
- Rows changing `vol_regime`, `trend_direction`, match tier
- Distribution of `win_rate` movement
- **Rows changing `ev_status` band, and in which direction**
- **Rows changing `final_decision_engine` verdict**

**If more than 10% of rows change `ev_status`, stop and report rather than
committing.** That warrants shadow-running before promotion, not a direct cut-over.

---

# STAGE D — Unrelated, do today

`polygon_data_fetcher.py:12` carries a live Polygon API key in plaintext in the
module docstring, committed to the repository.

1. **Rotate the key at Polygon.** This is the part that matters — removal does
   not undo exposure, and the key remains in git history.
2. Move it to `.env` / environment variable.
3. Grep the repository for other hardcoded credentials and report.
4. **Do not reproduce any key value** in commits, reports or output.

Separate commit, unrelated to the rest of this work order.

---

# Final report — `REGIME_TREND_FIX_REPORT.md`

- Stage A: computability findings, the collapsed damage range on 100+ tickers
- Stage B: the DB's convention, agreement rate, gate result
- Stage C: changes with SHAs, tests failing-then-passing, tier semantics
  proposal, full-book blast radius
- Stage D: confirmation of rotation (no key values)
- Golden diff, every change attributed
- **What I could not determine, and why**
- Rollback procedure, tested

## Standing limitation

No closed loop from signal to realised outcome exists. This makes the actuarial
match **more correct** — matched on real regime and trend rather than constants.
**It does not establish that the resulting win rates predict better.** Only
realised outcomes can, and they are not being captured. `Trade_Idea_Id` exports,
so the join key exists.
