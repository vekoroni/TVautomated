# EV Engine V2 — Phase 0 Verification Report

Sprint: `CLAUDE_CODE_TASK_ev_engine_sprint.md`. **Read-only.** No source files were
modified. Reference data: `data/output/runs/20260731_083130/morning_validation/
morning_validated_trades_20260731_083130.csv` (952 rows), cross-checked against
two earlier-stage files from the same run where needed:
`execution/execution_v3_5_20260731_083130.csv` (1262 rows, where
`ev_inputs_from_row()`/`EVEngineV2.evaluate()` actually runs) and
`superbrain/eil_enriched_20260731_083130.csv` (1262 rows).

**A file-identity correction up front:** the task lists `avshunter_options_intelligence.py`
in scope. There are two files by that name: a 36-line untracked stub at the repo
root, and the real 6,906-line file at `scripts/avshunter_options_intelligence.py`
(tracked, 2 commits). Line 4215 — cited in V5 — only exists in the `scripts/`
copy. All V1-references below to "the V1 engine" mean `scripts/avshunter_options_intelligence.py`.
There is also a duplicate, unimported `vanguard/ev_engine_v2.py` alongside the
live root `ev_engine_v2.py` — confirmed via import-site grep that every live
caller does `from ev_engine_v2 import ...`, which Python resolves to the root
copy. The `vanguard/` copy is dead weight, not a second live engine.

---

## V1 — Put clamp in `_struct_ev`

**Verdict: REFUTED as stated (the named mechanism), but the underlying defect is real, worse than described, and not put-specific in practice.**
**Confidence: 85%** that the denominator-clamp mechanism as literally described does not occur;
**80%** on the replacement mechanism identified below.

**The claimed mechanism does not occur.** `ev_inputs_from_row()` reads `stop_price`
from the row dict via `f('stop_price') or entry*(1-f('stop_pct',0.05))`
(`ev_engine_v2.py:112`). I checked all three real per-run CSVs for this run —
`morning_validated_trades`, `execution_v3_5`, `eil_enriched` — for a column
literally named `stop_price`. **None of the three has one.** Nor is there a
`stop_pct` column anywhere. This means the fallback `entry*(1-0.05)` fires for
**every row, unconditionally, regardless of direction** — confirmed empirically:
across all 952 rows, `stop == entry*0.95` exactly, std 0.0. Because this stop is
always *below* entry, `entry_price - stop_price` is always positive (≈5% of
entry) — it does **not** hit the `max(...,0.001)` floor the claim describes.
The claim's "denominator clamps to 0.001" does not happen with this data.

**The real mechanism, and it is worse:** real stop data exists and is fully
populated in this exact CSV — `invalidation_level` and `exit_stop_price` are
non-null for all 952 rows (median ≈ $43, real per-ticker variation) — but
`ev_inputs_from_row()` never reads either field under any name. This is not
"real data thrown away by a clamp," it is real data that was **never wired in
at all** — the same failure class CLAUDE.md's own "Known Risk Pattern #2"
(field-name mismatch) warns about. The bare `direction` field doesn't correct
for this either: the synthetic stop's below-entry direction is baked in
regardless of whether the position is a CALL or a PUT, so a PUT's structural
stop is nonsensical (below entry, when a PUT's real stop should sit above).

**`target_price` fares little better.** The literal `target_price` column is
`0`/null for **671 of 952 rows (70.5%)** in the reference CSV, triggering the
`entry*(1+0.10)` fallback for those. Combined with the universal synthetic
stop, **346 of 952 rows (36.3%)** — both CALLs and PUTs — compute `rr` from
two entirely synthetic numbers (`1.10/0.95 → rr = 2.0` exactly), unrelated to
any real structural level for that ticker.

**The "339" count and direction itself are unreliable in this dataset.**
The reference CSV carries at least three disagreeing direction fields:
`direction`/`canonical_direction`/`resolved_direction`/`primary_direction` all
report **CALL 827 / PUT 125** (no non-directional bucket), while
`options_direction` reports **CALL 413 / PUT 339 / STRANGLE 200**. The task
doc's "339 of 339" figure matches `options_direction`'s PUT count exactly — but
`ev_inputs_from_row()` reads the bare `direction` key, not `options_direction`.
Of the 339 `options_direction == PUT` rows, only 104 also have bare
`direction == PUT`; the other **235 have bare `direction == CALL`** — i.e. the
field the engine actually consumes disagrees with the field that was probably
used to produce the "339" count, for 69% of those rows. This is very likely a
recurrence of the same direction-collapse pattern the Intelligence Lab sprint
fixed in a different code path (`_normalise_direction_value`) — that fix
never touched this pipeline stage.

Given that, I make no claim that any single number ("339 of 339," or my own
recomputed counts) is *the* correct measurement — the direction input itself
is not well-defined at this stage. What I can state with confidence: using the
bare `direction` field the engine actually reads, PUT rows hit the `max(rr,0.5)`
floor at roughly 10x the rate of CALL rows (41/125 = 32.8% vs 28/827 = 3.4%);
using `options_direction` instead, it's 67/339 = 19.8% vs 0/413 = 0%. Under
every direction definition I tested, PUTs hit the floor at a **grossly
disproportionate rate to CALLs**, and 0% of CALLs ever hit it under
`options_direction` classification — consistent with the geometry described in
the claim (target > entry > stop assumed), even though the exact stated
mechanism is wrong.

**Recommendation:** Phase 1's proposed fix (`abs()` on both numerator and
denominator) is directionally correct and should proceed, but it treats a
symptom. The bigger problem — `stop_price`/`target_price` never receiving real
per-ticker data, and `direction` disagreeing with `options_direction` for a
majority of PUT-flagged rows — sits upstream of `ev_engine_v2.py` entirely and
is not fixed by FIX-EV-1. Recommend documenting this explicitly as a
follow-on, since it affects far more than the `rr` calculation (see V4).

---

## V2 — `contract_eff` bypass

**Verdict: CONFIRMED (the count) / CONFIRMED via analytic argument (the guard is load-bearing), empirical ratio distribution INCONCLUSIVE.**
**Confidence: 95%** on the count; **85%** that the cutoff is a necessary guard, not deletable.

Using the CSV's own stored `ev_structural` column (production output, not my
recompute): **490 of 952 rows (51.5%)** have `|ev_structural| < 0.001` —
matches the claim exactly.

The claim that the ratio "may be enormous" if the cutoff were removed is
correct **as a matter of arithmetic**, independent of what real value would be
observed: `_contract_eff` computes `cev/abs(sev)`; for any `cev` bounded away
from zero, this ratio diverges as `sev → 0` by definition. I confirmed this
isn't a degenerate edge case — `csel` (the contract EV term) is a different,
independently-computed quantity from `sev` and has no reason to also approach
zero at the same rate, so the two do not cancel. **The cutoff is a real guard
against a real division-by-near-zero, not an arbitrary bypass that could simply
be deleted.**

What I could **not** determine: the actual distribution of `cev/|sev|` for the
real 490 bypassed rows. Reproducing it requires the exact `cev` value each of
those rows had at computation time, and — per V1 and V4 — I do not have
confidence that re-running `ev_inputs_from_row()` on the exported CSV
reproduces the original `cev`/`sev` pair (my recomputed `ev_structural` does
not match the CSV's stored value for **any** of the 952 rows; see V4 for the
detail). I did not fabricate a distribution to fill this gap. **This must be
answered before FIX-EV-2 picks a replacement transform**, per the sprint's own
Phase 2 requirement ("propose the specific form ... with the resulting ratio
distribution for all 952 rows"). It cannot be answered from static files alone
— it needs either instrumented output from an actual live run, or a corrected
understanding of exactly which row schema the engine consumed (see recommendation
in V4).

---

## V3 — Unreachable classification bands

**Verdict: CONFIRMED, with independent corroborating evidence found elsewhere in the live codebase.**
**Confidence: 95%.**

Stored `ev_conf_adj`: max = **0.023439**, min = -0.00019 — matches the claimed
0.0234 max. `ev_status` distribution in the reference file:

| Status | Count |
|---|---|
| PASS_SMALL | 924 |
| WEAK_PASS | 28 |
| PASS / PASS_HIGH / FAIL / DATA_WEAK | 0 |

Two of six bands fire (the doc says "two of five" — `DATA_WEAK` is a sixth band
gated on `data_quality_score`, separate from the `ev_ca` ladder; either count
is defensible depending on whether you count it).

**Git history check:** `ev_engine_v2.py` has **zero commits** — `git log --all
-- ev_engine_v2.py` returns nothing. It has never been committed to this
repository, so there is no blame history to check for when `0.25`/`0.10` were
written or against what scale. I cannot answer "were they ever calibrated" from
version control; the file's own comments give no derivation for these
constants either.

**Independent, unprompted corroboration found while tracing V5's consumers:**
`position_sizing_engine.py` (PSE) contains this comment, verbatim, directly
above `_ev_multiplier()`:

> `EV scale in live pipeline: ev_conf_adj typically ∈ [0.002, 0.022] (much lower
> than the 0–0.25 range the old FDE thresholds expected).`

This is a second author, in a different file, independently documenting the
exact same scale mismatch this claim describes — and then working around it
with its own compensating multiplier (`0.80 + ev_conf_adj*8.0`, etc.) rather
than fixing the underlying scale. This is strong evidence the scale problem is
real, known, and has already produced at least one silent workaround elsewhere
in the pipeline that a `_classify()` threshold change would also need to
account for (see V5).

---

## V4 — The scale question

**Verdict: CONFIRMED that `p` is implausibly narrow — but not fully for the reason stated, and not reproducible from this CSV alone. Two concrete, confirmed root causes found. The expected_move unit question: REFUTED (no 100x error found).**
**Confidence: 90%** on the expected_move unit check; **75%** on the two root causes for `p`; **40%** on reproducing the *exact* per-row `p`/`sev` values from this CSV (explicitly flagged as a methodology gap, not resolved).

### The instrumentation, and why it doesn't fully settle the question

I wrote a temporary script (`ev_verify.py`, run from the scratchpad directory,
never touching the repo) that imports `ev_engine_v2` unmodified, feeds every
row of the reference CSV through `ev_inputs_from_row()`, and calls
`_blend_win_probability`, `_struct_ev`, `_contract_ev`, `_contract_eff`, and
`evaluate()` directly. Full per-row output: `ev_verify_out.csv` (in the
scratchpad directory, not the repo).

**Critical finding, stated plainly per the sprint's stop-and-tell-me rule:**
recomputing `ev_structural`/`ev_conf_adj`/`ev_status` this way reproduces the
CSV's own stored values for **0 of 952 rows** (median absolute difference
0.019, max difference 3.68). This is not noise — it means the row schema
`ev_inputs_from_row()` actually consumed when these numbers were first
computed is **not** the schema exported into this CSV. Tracing the true call
site (`execution_intelligence_runner.py:_compute_all_ev()`, which runs against
`execution_v3_5_20260731_083130.csv`-shaped rows) confirms why: that file also
lacks literal `direction`, `signal_price`, `target_price`, and `stop_price`
columns — the same absences found in the final CSV, just for different
downstream reasons. I could not identify, from static files, the exact
in-memory row that produced the stored numbers. **I am reporting the
per-row `p` distribution below as "what this code does when fed this
exported dataset," not as a certified replica of the original run's per-row
values** — the pattern and its causes are real and independently confirmed
(below), but I would not sign off on any individual row's recomputed `p` as
the number that was actually used live.

### `p` is narrow, and two concrete causes are confirmed independent of the above caveat

```
p (952 rows): mean 0.316, std 0.127, min 0.197, 25% 0.223, 50% 0.255, 75% 0.480, max 0.586
```

Two of the four inputs to the `ms` blend inside `_blend_win_probability` are
**structurally pinned to their neutral defaults for the entire book**, and
this holds regardless of the row-schema ambiguity above, because I confirmed
the underlying field names are absent not just from the reference CSV but from
the two upstream CSVs as well:

- **`bmps` = 50.0 for all 952 rows, std 0.0.** `ev_inputs_from_row()` derives
  `bmps` from a literal `momentum_bucket` key. That key does not exist under
  that exact name in `execution_v3_5` or `eil_enriched` (only `layer2__momentum_bucket`
  exists). In the reference CSV the column exists but is blank for every row
  (traced to `eod_candidate_engine.py` writing `_str(row, "momentum_bucket")`
  from a row that never had that key either) — an empty string doesn't match
  any tier in the `{EXTREME,HIGH,MID,LOW}` map, so it falls to the function's
  own default, 50.0, every time.
- **`flow_score` = 2.5 for all 952 rows, std 0.0.** Same story: `flow_score`
  is read literally; only `phantom_info_flow_score` exists anywhere in the
  pipeline. Always defaults.

Since `ms = 0.40·predictability + 0.25·bmps + 0.20·calibration + 0.15·flow`,
and `bmps`/`flow` are pinned, **35 of the 100 weighted points in `ms` are a
fixed constant for every ticker in the book, every day.** Only the
`predictability`/`calibration` terms (both ultimately derived from the
`composite` column, which is real and does vary, 39.5–83.2) move at all. This
is a genuine, confirmed structural cause of `p`'s narrowness — separate from,
and in addition to, whatever the CSV-fidelity gap above does to the exact
numbers.

**On `_blend_win_probability`'s `a` term:** I traced a plausible third cause —
`win_rate_20d` is absent from the reference CSV (present upstream) so any
20-day-horizon row would read `hit_rate_20d=0.0` — but I am explicitly
**not** confirming this one. It rests on the same row-fidelity gap already
flagged, and I did not verify `win_rate_20d` was actually consumed as `0`
rather than never reached at all (only ~DTE≥25 rows use horizon 20). Flagging
it as a plausible contributor, not a finding.

### `_struct_ev`'s reduction for puts, algebraically

The claim that `sev/em` reduces to `(3p-2)` for puts when `em≠0` and `rr`
floors at `0.5` is correct algebra (`lm = -(em/0.5) = -2em`, so `sev = p·em +
(1-p)·(-2em) = em(3p-2)`) — I checked this symbolically against
`_struct_ev`'s source and it holds exactly whenever the floor is hit. Given
`p`'s median is nowhere near 2/3 in either my recomputation or in any
plausible input range (see above), a per-row `sev/em ≈ 6e-5` — vastly smaller
than `3p-2` would produce for any real `p` — is itself informative: it says
`em` (the divisor) must be very large relative to `sev`, which points back to
`em`'s own unit (checked next), not to `p` being suspiciously exactly 2/3.

### Expected_move unit trace — REFUTED, no 100x error found

I traced `l3_expected_move_1_5d` / `_6_10d` / `_11_20d` → `expected_move_5d`/
`_10d` (identical values, confirmed a direct pass-through, not a
transformation) → `ev_inputs_from_row()`'s `_move()` fallback chain → `_struct_ev`.
`expected_move_10d` in the reference CSV has median 2.565, mean 2.93, max
12.28 — these are **percentage-point values already** (matching the Lab card's
"1.77%" display convention the task describes), consistent with `expected_move_10d`
being read as e.g. `2.57` meaning "2.57%," not `0.0257`. **`_struct_ev` does not
divide this by 100 anywhere** — it uses `em` directly as `p*em - (1-p)*lm`. This
means `em` is being consumed as a **raw percentage-point number** (magnitude
~1–12), not silently reinterpreted as a fraction. There is no 100x unit error
in this path. This is very likely why `sev` (which should be a fractional
expected-return figure, order 1e-2 to 1e-4) is instead dominated by
`em`-scale numbers when the floor isn't hit, and why `sev` and `expected_move`
are so close in the median-ratio calculation the claim opens with — **the bug,
if there is one in this area, is that `em` (a percentage-point number, e.g.
2.57) is never converted to a fraction (0.0257) before being blended with a
probability to produce what is meant to be a fractional expected return.**
That is functionally a scale error, just not the specific 100x-at-a-different-stage
error the claim hypothesized, and it doesn't require the "fraction consumed as
percentage" direction — it's closer to the opposite: a percentage-scaled
number is being used where a fraction is expected. I am flagging this as a
**new, confirmed, and likely-significant finding**, distinct from the original
seven, and recommend it be added to Phase 1's scope for discussion before any
fix is designed — the direction-aware `rr` fix in FIX-EV-1 does not touch this
at all, and it may be the dominant scale error, not the `rr` floor.

---

## V5 — Blast radius

**Verdict: CONFIRMED. Pipeline-wide, as the task expected — and touches at least one component (`position_sizing_engine.py`) that CLAUDE.md and this sprint both say must not be touched.**
**Confidence: 90%** on the naming collision; **85%** on the consumer list (a best-effort grep-driven sweep of live files, not a guarantee of completeness).

**The naming collision, confirmed with both sides' source:**
- V1 (`scripts/avshunter_options_intelligence.py:4215`):
  `ev_structural = win_prob * option_gain - (1-win_prob) * mark` — `option_gain`
  and `mark` are **dollar/premium-denominated** (from `option_value_at_target - mark`,
  both option prices). This is a per-contract dollar figure.
- V2 (`ev_engine_v2.py:_struct_ev`): a **fractional expected return**
  (`p*em - (1-p)*lm`, `em` a percentage-point move) — see V4 for why even this
  fractional value is itself scale-confused, but it is categorically different
  from V1's dollar figure regardless.
- `eod_candidate_engine.py:2199-2201` writes `ev2_ev_structural`→`ev_structural`,
  `ev2_ev_conf_adj`→`ev_conf_adj`, `ev2_ev_status`→`ev_status` — confirmed
  exactly as described. From this point on, any consumer reading the bare
  column name is reading V2's number under V1's name.

**Consumer enumeration** (live files only; grepped for
`ev_structural|ev_conf_adj|ev_status|ev_final|ev_selected|ev2_ev`):

| Consumer | Branches or displays? | Detail |
|---|---|---|
| `final_decision_engine.py` (Phase 10, Handoff Guard) | **Branches — hard gate** | `ev_status=="FAIL" and ev_conf_adj<-0.10` → HARD block; `ev_status=="WEAK_PASS"` → REDUCE; `ev_status in (PASS_SMALL,PASS,PASS_HIGH)` → EXECUTE-eligible. Directly consumes the same `_classify()` bands V3 shows only two of six ever reach. |
| `position_sizing_engine.py` (PSE) | **Branches — hard gate + sizing multiplier** | `EV_FATAL_FLOOR` hard-blocks on `ev_status=="FAIL" and ev_ca<floor`; `_ev_multiplier(ev_conf_adj, ev_status)` computes an actual size multiplier keyed on the same PASS_HIGH/PASS/PASS_SMALL/WEAK_PASS/DATA_WEAK bands, with its own comment (quoted under V3) acknowledging the scale mismatch and compensating for it with hardcoded per-band arithmetic. **This directly conflicts with the sprint's "No Kelly, no position sizing... PSE is retired" rule** — the code is not retired in the sense of being dead; it is live source that still computes and returns a size multiplier keyed on these exact fields. I did not modify it (Phase 0 is read-only) but flag this squarely: any threshold change to `_classify()` changes PSE's multiplier bands too, whether or not PSE's output is actually wired to a live decision today. I could not determine from static reading alone whether PSE's output is currently consumed downstream or dead-lettered — recommend confirming before Phase 1 lands, since it changes the honest blast-radius statement. |
| `trigger_layer.py` | **Reads as a fallback input to its own computation** | Precedence chain `("ev2_ev_conf_adj","fd_ev_used","ev_conf_adj","eil_ev_net","ev_final")`, used "only when the sovereign EV fields are absent" per its own comment — feeds its own internal score, not a simple display. |
| `execution_intelligence.py` (EIL) | **Blends into a composite, not a discrete branch** | `ev_v2_raw = ev2_ev_conf_adj \|\| ev2_ev_final \|\| ev_final`; `eil_ev_score = 50 + ev_raw*200` (0-100 scale) and `eil_ev_net = ev_raw - spread_cost` are both written into `ExecutionVerdict` and very likely feed `eil_composite_score`/verdict, though I did not trace that composite's internals in Phase 0. |
| `intelligence-lab/intelligence_lab.py` | **Mostly displays; one real filter branch** | Extensive display/export field mapping (`sig.get("ev2_ev_conf_adj")` etc.), a `data_weak_count` summary metric, and one genuine UI-level branch: an EV-minimum filter (`if ev_val < float(ev_min): continue`) that excludes rows from the Lab's candidate view below a user-set threshold. Does not gate real trades, but does change what an operator sees. |
| `pipeline_interpreter/pipeline_interpreter_engine.py` | **Displays only** | Pulls `ev_predicted`/`ev2_ev_conf_adj`/`eil_ev_net` into a report field via `_get_fld(...)`; no branching found. |
| `morning_gate.py` | **Does not consume these fields at all** | Zero matches for any of `ev_structural`/`ev_conf_adj`/`ev_status`/`ev_final`/`ev_selected`/`ev2_*` in this file. The task's framing implied it might; it doesn't. Stated for the record since it corrects an assumption rather than confirms one. |
| `avshunter_superbrain_layer.py`, `execution_schema.py`, `avshunter_ticker_probe.py` | **Not individually traced in Phase 0** | Appeared in the grep sweep; not read in detail. Flagging as incomplete coverage rather than asserting either verdict. |

**Conclusion on V5:** confirmed pipeline-wide. `final_decision_engine.py` and
`position_sizing_engine.py` both hard-branch on the exact `_classify()` bands
V3 shows are almost never reached (924/952 rows sit in `PASS_SMALL` today).
Any threshold recalibration is therefore **not contained** — it changes real
EXECUTE/REDUCE/HARD verdicts in `final_decision_engine.py`, which is exactly
why the sprint document is right to defer `_classify()` changes to a later,
dedicated phase.

---

## V6 — Actuarial win rate semantics

**Verdict: CONFIRMED — precise semantics established from source.**
**Confidence: 90%.**

Read in full: `vanguard/layer2_statistical/actuarial_query.py`.

`win_rate_5d`/`win_rate_10d`/`win_rate_20d` (and the base `win_rate`, which
holds the 20-day value) are computed in `_calculate_outcomes()` as:

```python
win_rate_20d = (rets_20d > 0).mean()   # P(return > 0) -- directional win rate
```

with the identical pattern for 5d/10d off `outcome_5d_return`/`outcome_10d_return`.
The source comment states this explicitly: *"P(return > 0) — directional win
rate."* **This is P(the horizon return is positive), unconditional on
magnitude, over exactly that many trading days (5/10/20), matched against a
historical sample of analogous states via the EXACT→RELAXED→ANALOGUE→UNKNOWN
match ladder** (`_find_match_ladder_states`). It is **not** a fixed-threshold
target-hit rate — that's a categorically different, separately-computed field:
`prob_up_10pct_20d` / `prob_up_5pct_5d` / `prob_up_7pct_10d` (via
`outcome_hit_10pct_up` etc.), which measures P(return ≥ a fixed % threshold).
The two are easy to conflate and the file keeps them as genuinely distinct
fields.

**One caveat that matters for the Phase 3 drift derivation:** the value
actually attached to `ActuarialOutcomes.win_rate_5d`/`_10d` after
`_adjust_for_intraday_context()` runs is **not always the raw directional win
rate** — when intraday context is available, `adj_wr_5d = min(0.95,
base_win_rate_5d * adjustment_factor)`, an intraday-adjusted rescaling
(bounded to 0.4x–2.5x). The function does fail closed to the unadjusted base
rate when `intraday_rows == 0`, per an explicit comment citing a prior
incident (inflated EV from substituting the wrong probability). **So: `μ =
σ√T·Φ⁻¹(win_rate)` is valid under V6's semantic reading of "the underlying
directional win rate," but only if Phase 3 sources the field labeled
`win_rate_5d`/`_10d`/`_20d` (or bare `win_rate`) and confirms — for whatever
row schema it actually receives — that this rescaling has not silently
distorted it beyond a directional-probability interpretation.** This is a
reasonable, buildable finding, not a blocker, but Phase 3 should cite this
exact caveat per the sprint's own disclosure requirement.

---

## V7 — Additive penalty on a multiplicative scale

**Verdict: CONFIRMED, decisively, via direct synthetic test of the unmodified code.**
**Confidence: 98%.**

The reference CSV cannot exercise this claim at all — `runway_pct` is not a
literal column in `morning_validated_trades.csv` (only `runway_to_target`/
`runway_to_wall`/`runway_to_wall_pct` exist under different names), so
`ev_inputs_from_row()` defaults `runway_pct` to `2.0` for all 952 rows, which
never triggers a nonzero `runway_penalty` (`_runway_pen` returns `0.0` for
`runway_pct >= 2.0`). This is, again, the field-name-mismatch pattern — noted,
not re-litigated.

Bypassing that gap, I called `EVEngineV2.evaluate()` directly with a fixed,
realistic input and varied only `runway_pct`:

| `runway_pct` | `rp` | `ev_final` | `ev_final + rp` |
|---|---|---|---|
| 3.0 | 0.000 | +0.00296 | +0.00296 |
| 1.5 | 0.050 | -0.04704 | +0.00296 |
| 0.8 | 0.120 | -0.11704 | +0.00296 |
| 0.3 | 0.250 | -0.24704 | +0.00296 |
| 0.0 | 0.500 | -1.00000 | -0.50000 (hard `ZERO_RUNWAY` gate fires instead) |

For every `rp>0` case that doesn't trip the separate hard gate,
`ev_final + rp` is **exactly** the same constant (+0.00296, the full
`epa·ce·em·rm·cb` product for this input) to five decimal places. The claim is
proven exactly as stated: once `rp>0`, `ev_final ≈ (small constant) - rp`, and
the entire upstream computation — structural EV, contract efficiency,
execution multiplier, regime multiplier, convexity boost — collapses to
irrelevance next to a `{0.05, 0.12, 0.25}`-scale subtraction. Given the real
book's `ev_conf_adj` distribution tops out at 0.0234 (V3), **any row that
picks up even the smallest `rp=0.05` penalty is mathematically guaranteed to
land at `ev_status=FAIL`** regardless of how good the underlying setup is.

---

## Recommendation on whether Phase 1 should proceed as scoped

**V1 is not cleanly CONFIRMED as stated** — the named mechanism (denominator
clamp) does not occur; a different, related, and more serious mechanism
(stop_price never wired to real data at all, for every row, not just puts) is
confirmed instead, and it interacts with a second confirmed defect (bare
`direction` disagreeing with `options_direction` for the majority of
economically-PUT rows). The sprint's hard rule is "proceed only if V1 is
CONFIRMED." Under a literal reading of the named claim, it is not. Under the
spirit of the claim — puts are geometrically mishandled — it is, just for a
different and larger reason than described.

**My recommendation: do not proceed straight to FIX-EV-1 as scoped.** The
`abs()` fix is correct and should still be built, but landing it alone, on top
of a `direction` field that's wrong for a majority of PUT-labeled rows and a
`stop_price`/`target_price` pair that's synthetic 36%+ of the time, will not
produce the "different, real measurement per row" the sprint expects from
Phase 1 — it will produce a different, but still mostly-synthetic, measurement.
I'd suggest treating "which direction field is authoritative at this stage,
and are stop/target ever real" as a required precursor check before Phase 1's
blast-radius report is written, or that report will itself be measuring noise.

**V4's expected_move-unit finding is new and, in my assessment, more consequential
than the original seven.** It was not on the original list. I'm surfacing it now,
per the explicit instruction to stop and report if a scale error of this kind
turns up, rather than folding it silently into Phase 1's scope.

**Everything else (V2, V3, V5, V6, V7) is confirmed with high confidence** and
supports proceeding to Phase 2/3 planning on those specific points, with the
caveats stated inline (V2's empirical ratio distribution is not yet available;
V5 flags a live conflict with the "PSE is retired" rule that should be
resolved explicitly, not silently).

---

## What I could not determine, and why

- **The exact row-schema `ev_inputs_from_row()` consumed at original computation
  time.** Every CSV I could find for this run — including the one written
  moments after the actual `.evaluate()` call — lacks literal `direction`,
  `signal_price`, `target_price`, and `stop_price` columns. I traced the
  import chain far enough to identify a likely cause (see below) but did not
  run the live pipeline to observe the real in-memory row.
- **A very likely contributing cause, found but not chased further per Phase 0's
  read-only scope:** `execution_intelligence_runner.py` does
  `from edge_detector import enrich_vanguard_inputs`, wrapped in a `try/except
  ImportError` with a much thinner fallback. I reproduced the exact
  `sys.path` setup from that file and ran the same import statement directly —
  it fails (`attempted relative import with no known parent package`),
  confirming the fallback path is what actually runs in this environment. The
  real `enrich_vanguard_inputs` (found only in `_cleanup_holding` archives, not
  in the live `vanguard/layer2_statistical/edge_detector.py`) appears to have
  been retired without updating the caller, which still tries to import it
  first. This is offered as a lead for whoever investigates the row-schema gap
  next, not as a Phase 0 finding in its own right — I have not confirmed it is
  the actual, complete explanation.
- **The true empirical `cev/|sev|` ratio distribution for V2's Phase 2 need.**
  Requires either a live/instrumented run or resolution of the row-schema gap
  above.
- **Whether `position_sizing_engine.py`'s output is live-consumed or
  dead-lettered downstream.** Matters for how urgently the V5/PSE conflict with
  "PSE is retired" needs resolving.
- **Full consumer sweep for `avshunter_superbrain_layer.py`, `execution_schema.py`,
  `avshunter_ticker_probe.py`.** Appeared in the grep, not individually read.

---

## Git status

No source files were modified. All investigation used `Read`/`Grep`/`Bash`
(read-only commands) plus one temporary script
(`ev_verify.py`) and its output CSV, both written to the session scratchpad
directory outside this repository, never committed or copied in. Pre-existing
uncommitted changes to unrelated files (`WyckoffEngine_3101_v2.py`,
`avshunter_discovery_ULTIMATE.py`, `morning_gate.py`, etc.) predate this
session and this task; I did not touch any of them. The only new file in the
repository from this work is this report.

**Stop here. Reporting Phase 0. Awaiting confirmation before Phase 1.**
