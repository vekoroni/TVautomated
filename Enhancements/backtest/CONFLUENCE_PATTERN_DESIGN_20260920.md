# Confluence Pattern Recognition — Design Proposal

Status: **superseded by `SCENARIO_REGISTER_ADDENDUM_IA9_CONFLUENCE_20260920.md`.** The P1–P5 patterns below
were proposed before checking the parent register and turned out to overlap, with different specifics, the
already-frozen IA-9 interaction list (compression × relative strength; structure × IV state; early pressure
× regime — register §4, and quoted verbatim in `AVS-SD-MON-003` §9.7). The reconciled addendum is now the
single source of truth for pattern ids, evaluation order and evidentiary status; this document's content
(the "correction" framing and the additive-vs-actual methodology in §4 below) is carried forward there
unchanged and should be read from the addendum going forward, not from here. Kept for provenance only.

Original status line: **proposal only — not built, not backtested**. For ACK approval before any test or
code. Root cause this replaces: single-factor, isolated hypothesis testing (S-DIR-3, S-VAL-1, IA-1/2/3 run
as independent questions) does not reflect how a trade thesis is actually formed — by several things lining
up together, not any one signal alone. Confirmed by ACK, 20 Sep 2026.

## 1. The correction, precisely

Everything measured this weekend so far was tested **additively**: does factor X alone move the outcome,
holding nothing else fixed. That produced real, individually significant findings (structure-vs-direction,
IV cheapness, compression pricing, cost-model calibration) but never asked the question that actually
matters for a trade: **when several of these line up together, is the result better than what you'd expect
from just adding their individual effects?** If yes, the pipeline should learn to recognise the combination
as its own thing. If no — if confluence is just addition — then the fix is calibrating the existing
additive score better, not building a new layer. This design tests which one is true, and is built either
way to answer it honestly rather than assume it.

## 2. Building blocks (already measured, reused — not reinvented)

Every leg below already exists as a live, computed field in the pipeline or was measured this weekend.
No new detection logic — this design only asks how to *combine* what's already there.

| Leg | Source (already live) | States used | Evidence this weekend |
|---|---|---|---|
| **Structure agreement** | `thesis_geometry_review_state` (`_STRUCTURE_SIDE`) | AGREES / CONFLICTS | S-DIR-3: conflict rows favour structure at 10–20d, t=-4.89 / -4.73, p<0.0001 |
| **Volatility cheapness** | true IV percentile (F2) vs realised vol | CHEAP (bottom quintile) / RICH (top quintile) / MID | IA-3 weekly-chain year: cheapest ≈ fair (0.84–1.03), richest ≈ 0.3 |
| **Compression state** | Crabel/ATR compression quintile | EXTREME (top quintile) / MODERATE / LOW | IA-3: extreme compression is the *worst*-priced state (0.51–0.58) — a crowded heuristic, not an edge |
| **Spread/liquidity** | `contract_spread_pct` | TIGHT / WIDE | Round 1 costs: near-the-money + tight spread −13.2% vs −19.5% baseline |
| **Moneyness** | `directional_distance_to_strike_pct` | NEAR (≤2.5% OTM) / FAR | Round 1 costs; EXPR-CHOOSE-2 definition |
| **Cost-model rank** | `cautious` (compute_path_option_ev) | TOP quintile / BOTTOM quintile | S-VAL-1: win rate 4.2%→17.6% worst-to-best decile, ρ=0.44 |

**Explicitly excluded from any confluence leg: PCR / open-interest positioning (`dw_signal`, `pcr_signal`,
`option_activity_state`).** A parallel change already in the working tree (`test_f7_delta_weighted_pcr.py`
and its dependents) has just redefined these as `ADVISORY_ONLY` / `POSITIONING_CONTEXT_ONLY` — explicitly
never a directional confirm or conflict signal, confidence weight 0.0. This design respects that: OI/PCR
may ride along as a *display* tag on a matched pattern, never as one of the legs that defines a pattern.

## 3. Pre-specified patterns (frozen before any result is read)

Five patterns, chosen from trading logic, not from trying combinations until one looks good. Each is a
falsifiable prediction, stated before measurement — exactly the IA-9 discipline ("pre-specified
interactions only") that was registered in the scenario register and never run.

| # | Pattern | Legs required | Trading rationale |
|---|---|---|---|
| **P1** | Confirmed aligned setup | STRUCTURE AGREES + CHEAP vol + TIGHT spread + NEAR the money | Direction and structure agree, the option isn't fighting a rich-IV headwind, entry is efficient — the textbook case for a long option |
| **P2** | Structural override | STRUCTURE CONFLICTS (all other legs neutral/unspecified) | S-DIR-3's own finding, held on its own — the market's structure has been a better call than governed direction at 10–20d; worth recognising standalone, independent of the other legs |
| **P3** | Priced-in compression fade | EXTREME compression + RICH vol | The worst-priced state IA-3 found — a name the market has already crowded into; candidate for skip, or for a shares-only expression instead of a long option |
| **P4** | Stacked high-conviction | TOP-quintile `cautious` + STRUCTURE AGREES + CHEAP vol | Tests the actual "togetherness" hypothesis directly: does stacking three independently-proven-positive legs beat any one of them alone (best single-leg result so far: 17.6% win rate), or are they redundant/correlated and stacking adds nothing? |
| **P5** | No pattern matched | none of the above | Control bucket — everything else. Necessary to know what "no recognised confluence" looks like, for comparison |

Patterns are evaluated in the order above; a row matches the first pattern it satisfies (P1 before P2, etc.)
so every row gets exactly one label, and P5 is the residual. Order is part of the frozen definition.

## 4. What gets measured, and the actual test

For each pattern, on H (and H+/N as they mature): n, win rate, mean/median return, right-tail measures
(per the register's standard measures), same pass bar as every other scenario (paired t ≥ 2.0 on history,
same sign on N once ≥40 closed results).

**The confluence-specific test (this is the point of the whole exercise):** for P1 and P4, compute the
return each individual leg alone was worth (already measured this weekend — e.g., CHEAP vol's own lift,
STRUCTURE AGREES' own lift) and sum them as a naive additive prediction. Compare the pattern's *actual*
measured return against that additive prediction.

- **Actual ≈ additive prediction** → confluence is just addition. The finding is: keep an additive score,
  but recalibrate the weights using what was actually measured this weekend (many current weights are
  unmeasured literals, not calibrated — a separate, smaller fix).
- **Actual > additive prediction** → real synergy exists. The finding is: build the pattern-recognition
  layer, because it captures something an additive score structurally cannot.
- **Actual < additive prediction** → the legs interfere (e.g., they're partially redundant, or one leg's
  edge only exists *without* the other). Also a real finding, and evidence against combining them naively.

Any of the three outcomes is useful and answers the actual question. None of them requires guessing in
advance.

## 5. What ships, and what doesn't (yet)

If a pattern clears the pass bar: a new field, `confluence_pattern` (P1–P5), computed alongside the
existing scoring — **display and ranking-tilt only, never a gate**, consistent with the standing rule that
macro/GEX/OI guards never gate (rule 6) and the "rank, don't gate" design rule. No capital-authority change;
this stays within the current V1 scope (stable pipeline, tangible outputs — authority is explicitly out of
scope until later).

**Continuous improvement, concretely:** each pattern's trust is re-measured on a rolling basis as N
accumulates (owned by `avshunter/c12_outcome`, the existing measurement/outcome-scoring module — not a new
parallel system). A pattern that stops clearing its bar loses ranking influence automatically; a pattern
that keeps clearing it can be proposed for more influence, always as an explicit written decision, never
silently.

## 6. Process (per standing rule — no pipeline change without this)

1. This document is the design; ACK approval is the root cause sign-off.
2. Test-first: a failing test per pattern, stated in trading language ("P1 requires structure agreement,
   cheap vol, tight spread, and near-the-money, in that check order") before any implementation.
3. Backtest on H first (data already in hand, no new collection needed) — should take one focused session,
   not a multi-day research program, since every leg is already computed and this design only asks how to
   combine existing fields.
4. Written result — additive vs. synergy vs. interference — before any code changes to production scoring.
5. If synergy is confirmed: minimal, display-only field addition, tested, committed, same discipline as
   F1–F8 this weekend.

## 7. What this deliberately does not do

- Does not touch the current additive `options_score` — that stays as-is until result #4 tells us what to
  do with it.
- Does not reopen D1/D5 — this design consumes their results (STRUCTURE AGREES/CONFLICTS, `cautious`
  quintile) as inputs, it doesn't re-litigate them.
- Does not attempt D2 (S-ELIG-3) again — that remains blocked on N accumulation, per the 20 Sep finding
  that its stop-selection logic isn't reconstructable from stored history.
- Does not add PCR/OI as a directional leg, respecting the parallel advisory-only redesign already in
  progress in the working tree.
