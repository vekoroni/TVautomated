# Backtest scenario register addendum — IA-9 confluence, reconciled

**Registered:** 20 September 2026
**Version:** 1.0
**State:** `PRE-REGISTERED — NO RESULTS READ — NO PRODUCTION AUTHORITY`
**Parent register:** `Enhancements/backtest/SCENARIO_REGISTER_20260919.md`
**Parent SHA-256:** `52cf8ac6b50d288edffb86dfb487d5d0f47db05a24dc4923dddf916c07668dcc`
**Also reconciles:** `Enhancements/backtest/CONFLUENCE_PATTERN_DESIGN_20260920.md` (uncommitted proposal, P1–P5)
and `docs/AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md` §9.7 (approved, committed `be61fab`)

This addendum does not edit or supersede the frozen register's IA-9 line (§4, "Interactions: a short list
fixed before looking (compression × relative strength, structure × IV state, early pressure × regime); any
wider search only inside the exploration period · U") or AVS-SD-MON-003 §9.7, which quotes that same frozen
list verbatim. Both were independently correct restatements of the one frozen definition — there was never
a conflict between the register and the design. The conflict was between that frozen list and a separate,
un-registered proposal (`CONFLUENCE_PATTERN_DESIGN_20260920.md`, ACK-requested 20 Sep, ahead of this
addendum) that named different, more elaborate combinations without checking the register first. This
addendum is that check, done properly, and the single reconciled list going forward.

## 1. What was reconciled

| Source | Items | Status before this addendum |
|---|---|---|
| Register IA-9 (frozen, 19 Sep) | compression × relative strength; structure × IV state; early pressure × regime | Frozen, never run |
| `CONFLUENCE_PATTERN_DESIGN_20260920.md` (P1–P5) | 4 multi-leg patterns + 1 residual bucket | Proposed, uncommitted, not checked against IA-9 |
| `AVS-SD-MON-003` §9.7 | Quotes the frozen IA-9 list verbatim | Correct as written, but silent on the P1–P5 proposal |

Two items overlapped conceptually with different specifics (structure × IV state ↔ P1; compression ×
relative strength ↔ P3, different second leg). One item was new with nothing to reconcile against (P4).
One item was mislabelled as an untested interaction when it is in fact already measured (P2 — see §3).

## 2. Reconciled list

IA-9's three original items are retained verbatim, unmodified, under their register wording. Each gets a
sibling or elaboration registered as its own id below, never as an edit to the original.

| id | Legs | Status | Provenance |
|---|---|---|---|
| **IA-9-1** | Structure × IV state | Pre-specified, untested as a joint interaction (components separately tested: S-DIR-3 for structure, IA-3 for IV) | Register, frozen, verbatim |
| **IA-9-1b** | Structure agrees + cheap vol + tight spread + near the money | Pre-specified, untested | `CONFLUENCE_PATTERN_DESIGN` P1 — a 4-leg elaboration of IA-9-1, testing whether execution-quality legs (spread, moneyness) add beyond the 2-way interaction |
| **IA-9-2** | Compression × relative strength | Pre-specified, untested | Register, frozen, verbatim |
| **IA-9-2b** | Extreme compression + rich vol | Pre-specified, untested | `CONFLUENCE_PATTERN_DESIGN` P3 — a sibling hypothesis: compression's interaction partner may be vol richness (crowding/pricing), not relative strength (momentum). Both run; they test different mechanisms, neither supersedes the other |
| **IA-9-3** | Early pressure × regime | Pre-specified, untested | Register, frozen, verbatim. No sibling proposed — nothing in the P1–P5 set addressed this pairing |
| **IA-9-4** | Top-quintile `cautious` × structure agrees × cheap vol | Pre-specified, untested — genuinely new, 3-way | `CONFLUENCE_PATTERN_DESIGN` P4 — the direct test of the "togetherness" question (§4) |
| **CONF-STRUCT** | Direction contradicts structure, alone | **Already evidenced**, not a pending interaction — see §3 | `CONFLUENCE_PATTERN_DESIGN` P2, re-labelled out of the IA-9 numbering |
| **CONF-NULL** | None of the above matched | Control/residual bucket, required for every comparison below | `CONFLUENCE_PATTERN_DESIGN` P5 |

Evaluation order for a candidate row: IA-9-1b, then IA-9-2b, then IA-9-4, then IA-9-1/-2/-3 (plain,
untested pairwise forms, evaluated only if no elaboration matched), then CONF-STRUCT, then CONF-NULL. A row
gets exactly one label. Order is part of the frozen definition, same discipline as the parent addendum
convention.

## 3. Why CONF-STRUCT is not an IA-9 interaction

IA-9 exists to test **untested** combinations before looking. `DIRECTION_CONTRADICTS_STRUCTURE` alone is not
untested: S-DIR-3 (register, Round 2 findings, 20 Sep) already measured it directly — 3,320 rows, 22 run
folders, t=-4.89 (10d) / t=-4.73 (20d), p<0.0001 both, 385/154 unique tickers. Filing it under IA-9 would
misrepresent a confirmed finding as a pending hypothesis. It is carried forward here because it is a
component leg of IA-9-1/IA-9-1b (structure *agreement* is IA-9-1's first leg; structure *conflict* is its
logical complement) and because a pattern-recognition layer needs a name for it either way — but it does not
need the incremental-information test the other rows do. It already passed its own bar.

## 4. Methodology carried over from `CONFLUENCE_PATTERN_DESIGN_20260920.md`

This is the part of the original proposal that survives reconciliation unchanged, because it is not a
pattern definition — it is the test method, and it is what actually answers ACK's "togetherness" question
(20 Sep 2026): a trade thesis is formed by legs lining up together, not by summing independent point
contributions.

For every multi-leg id above (IA-9-1, -1b, -2, -2b, -3, -4): measure each leg's own individually-measured
lift (already available for structure and IV cheapness from this weekend's work; compression/relative
strength/early-pressure/regime lifts need their own single-leg measurement first, on U, before any
combination is read — same order-of-operations the frozen IA-9 line already specifies). Sum those lifts as
a naive additive prediction. Compare the pattern's actual measured return against it.

- Actual ≈ additive → confluence is addition; recalibrate the existing additive score's weights, don't build
  a new layer.
- Actual > additive → real synergy; a pattern-recognition layer is justified for that specific combination.
- Actual < additive → the legs interfere; evidence against combining them, also useful.

Every one of these three outcomes is a real, usable finding. None require guessing which one holds before
measuring.

## 5. Standard measures and pass bar

Unchanged from the parent register §2: n, win rate, mean/median return, right-tail measures, paired t ≥ 2.0
on history and same sign on N once ≥40 closed results, PBO/deflated Sharpe after ten or more trials in the
family — this family now has eight ids (IA-9-1/-1b/-2/-2b/-3/-4, CONF-STRUCT, CONF-NULL), so that control
applies from the first run, not deferred.

## 6. What this does not do

- Does not re-run or reopen D1 or D5 — CONF-STRUCT and IA-9-1's structure leg consume S-DIR-3's and
  S-VAL-1's results as inputs, they don't re-litigate them.
- Does not touch the current additive `options_score` — unchanged until §4's additive-vs-actual result says
  what to do with it.
- Does not grant any pattern ranking or gating authority — display-only until each id clears the pass bar
  independently, same as every other scenario in the parent register and the AVS-SD-MON-003 design's own
  §9.7 rule ("a confluence label is permitted only after its components demonstrate point-in-time
  incremental value ... cannot override thesis integrity").
