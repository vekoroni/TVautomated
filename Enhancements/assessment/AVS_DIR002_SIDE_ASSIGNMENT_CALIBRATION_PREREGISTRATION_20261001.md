# DIR-002 side-assignment calibration and R-5 outcome test — pre-registration

Date: 1 October 2026. Written **before** the historical panel was generated or inspected. Authority: signed DIR-002 design §4.4 (θ set on earlier evidence and frozen before the outcome cohort), §6 R-4/R-5; ACK DEC-1 (trend never assigns). This document fixes the sample, the grid, the selection rule and the pass rule. It grants no trading authority.

## 1. Panel (point-in-time replay)

- Code: the working tree with the DIR-002 kernel (`side_structural_evidence`, `symmetric_precor_intent`) and Discovery wiring, run through `Enhancements/direction_evidence/dir002_replay.py panel`. Each row runs the real `scan_ticker_ultimate` on completed canonical bars cut at the decision session, so legacy and new outputs come from one pass.
- Tickers: the first 500 of `config/tickers.csv` ranked by `sha256("dir002-panel-v1:" + ticker)` (deterministic, not chosen by outcome).
- Cuts: every 10th SPY trading session from 2022-09-01 to 2026-08-28; a cut needs ≥ 261 prior bars.
- Forward labels (log units from the cut close): 1/5/10/20-session returns, 20-session MFE/MAE, first passage of ±1σ√20 (σ = 20-session daily log-return s.d. at the cut, point-in-time). Same-bar double touch = AMBIGUOUS; fewer than 20 forward sessions = CENSORED.
- Known limitations (reported, not corrected): current revision of each bar (no as-of revision reconstruction); today's universe (survivorship); the Discovery decay term uses the wall clock (affects tier only, not side).

## 2. Windows

- **Calibration window:** cuts ≤ 2024-12-31.
- **Embargo:** 20 sessions after the last calibration label.
- **Held-out outcome cohort:** cuts from 2025-02-03 whose 20-session label is complete (≤ 2026-08-28 cut).
- The held-out cohort is not read until the policy values below are frozen in `config/dir002_side_assignment_v1.json` with `calibration.status = CALIBRATED_CALIBRATION_WINDOW`.

## 3. Grid (re-evaluated offline from the stored per-side evidence)

| Parameter | Values |
|---|---|
| `event_strength_min` | 0.50, 0.55, 0.60, 0.65, 0.70 |
| `control_margin_min` | 0.10, 0.15, 0.20, 0.25, 0.30 |
| `contested_margin` | 0.05, 0.10, 0.15, 0.20 |
| fixed: `control_full_scale` 0.80, `min_observation_quality` 0.65 (structure must be evaluated), `trend_min_bars` 200 | — |

Intent support is event-anchored only (DEC-1; a phase-D-without-breakout or phase-E setup is trend context). The `ANY_SETUP` variant is reported for transparency only and cannot be selected.

## 4. Selection rule (calibration window only)

1. *Legacy symmetric cases* = rows whose legacy direction is CALL/PUT **and** legacy Precor phase is C (Precor phase C is only reachable from its symmetric Spring/UTAD detector, audit P3). For each grid point compute the opposite-side rate on these cases (new side is the mirror of legacy side).
2. Eligible grid points: opposite-side rate ≤ 5 %.
3. Among eligible points choose the one with the highest lower 95 % bound of the mean σ-normalised 20-session signed return of directed rows (`s·ret_20/(σ√20)`, s = +1 BULL, −1 BEAR), using a date-block bootstrap (blocks of two consecutive cuts = 20 sessions; 2,000 resamples; seed 20261001).
4. Ties within 0.005: prefer the larger `event_strength_min`, then larger `control_margin_min`, then larger `contested_margin` (conservative).
5. Freeze the chosen values with this document's hash and the calibration summary.

## 5. R-5 held-out outcome comparison (paired, same starts)

Population: every held-out (ticker, cut) that is a Discovery survivor; legacy = `legacy_direction`, new = `thesis__side` under the frozen policy.

Reported by side and in total: coverage (directed rows), mean signed σ-return at 5/10/20 sessions, favourable/adverse ±1σ√20 first-passage incidence, adverse outcomes (signed return ≤ −1σ√20), missed large winners (|ret_20| ≥ 2σ√20 where legacy was directed on the correct side and new is UNASSIGNED), and transition counts (changed side, newly directed, newly UNASSIGNED, by status).

**Non-inferiority (per directed row quality):** for each side and in total, the date-block bootstrap 95 % lower bound of `mean_new − mean_legacy` (mean signed σ-return at 20 sessions over each method's directed rows, paired by date block) must be ≥ −0.05. Overlapping marginal intervals are not a pass. Coverage loss and missed-winner cost are disclosed regardless of pass/fail. If the number of directed held-out rows for a side is < 200 or < 20 date blocks, that side is `NOT_ESTIMABLE` and goes to ACK review — it is not promoted silently.

A failure is reported to ACK with the evidence; thresholds are not re-tuned on the held-out cohort.

---

## Amendment A1 (1 Oct 2026, after the calibration-window run, before any held-out read) — DEVIATION FOR ACK REVIEW

The v1 selection rule returned **no eligible grid point**. A diagnosis on the calibration window only (`Enhancements/outcomes/dir002/calibration_v1.json`) found two defects in the pre-registered criteria themselves, not in the thresholds:

1. **The "legacy symmetric case" definition was not symmetric.** Of the 5,320 Precor-phase-C cases, legacy's final side contradicted Precor's own symmetric detector on 1,217 rows (974 SELL_SETUP→CALL, 243 BUY_SETUP→PUT). These are the asymmetric `_reconcile_intent` and fusion/control paths (audit D4–D6, W4). Of the 1,182 opposite-side rows, 941 are SELL_SETUP rows that legacy turned into CALL. At every grid point the opposite-side rate was 22–25%, so no symmetric rule can satisfy it.
2. **The pooled mean signed return measures market drift, not side discrimination.** Assigning BULL to every calibration row scores +0.113σ. Legacy is 67% CALL and scores +0.071σ. Per side, the new BULL rows (+0.156σ) beat legacy BULL (+0.138σ). Both rules' BEAR rows have a negative signed return (legacy −0.066σ, new −0.098σ). Maximising the pooled mean selects for BULL bias, which DIR-002 §4.4 forbids ("not tune a score to manufacture more directed rows").

**Amended rules (A1), applied unchanged to the calibration window and then to the held-out cohort:**
- *Legacy symmetric case*: legacy side is CALL/PUT, legacy Precor phase is C, **and** the legacy side equals the side of the raw Precor intent (BUY_SETUP→BULL, SELL_SETUP→BEAR). These are the rows that legacy did not route through an asymmetric reconciliation. Eligibility still requires an opposite-side rate ≤ 5%.
- *Outcome metric*: **drift-adjusted signed excess** `s × (z20 − mean z20 of all matured survivors at the same cut)`, where z20 is the 20-session log return divided by σ√20. Selection maximises its date-block-bootstrap lower 95% bound over directed rows. Tie and conservatism rules are unchanged.
- *R-5 non-inferiority*: computed **per side** (BULL and BEAR separately; per DIR-002 R-5) on the drift-adjusted metric, with the same −0.05 margin and paired date-block bootstrap. Raw signed returns, coverage, first-passage incidence, adverse outcomes and missed large winners are still reported for both metrics.
- Nothing else changes: grid, windows, embargo, bootstrap and the sample-size floor for NOT_ESTIMABLE.

ACK may reject A1. In that case the v1 result stands as "no eligible policy" and the cut-over does not proceed.
