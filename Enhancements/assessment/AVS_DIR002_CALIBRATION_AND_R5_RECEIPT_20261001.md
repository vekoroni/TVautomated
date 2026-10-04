# DIR-002 side-assignment calibration and R-5 held-out receipt — 1 Oct 2026

Protocol: `AVS_DIR002_SIDE_ASSIGNMENT_CALIBRATION_PREREGISTRATION_20261001.md`, including **Amendment A1**, a deviation that ACK must review. Panel: `Enhancements/outcomes/dir002/panel_v1.jsonl` (500 tickers, 24,405 rows, every 10th session from Sep 2022 to Aug 2026). Each row is a real `scan_ticker_ultimate` run on completed canonical bars, so legacy and new outputs come from the same pass. No provider call was made, no pipeline was run and nothing was committed.

## 1. Calibration window (cuts up to 31 Dec 2024; 9,229 matured survivor rows)

- **v1 rule.** No grid point was eligible. The opposite-side rate stayed between 22% and 25% at every grid point because the v1 "symmetric case" set included 1,217 rows where legacy's asymmetric reconciliation had already overruled Precor's own symmetric detector. The pooled metric also favoured market drift: all-BULL scored +0.113σ, and legacy, which is 67% CALL, scored +0.071σ.
- **A1 rule** (symmetric cases where legacy agrees with raw Precor; drift-adjusted signed excess). All 100 grid points were eligible. The rule selected `event_strength_min 0.70`, `control_margin_min 0.10`, `contested_margin 0.05`.
  - Opposite-side rate: 2.7%. Agreement: 96.6%.
  - New-rule excess: −0.006σ (95% CI −0.036 to +0.025).
  - Legacy excess: +0.025σ (lower bound +0.005).
- **Where legacy's calibration-window edge comes from.** Only `RESOLVED_STRUCTURAL` (TRANSITION + EMA trend) was positive: +0.038σ (lower bound +0.010). No Wyckoff structure discriminated:

  | Bucket | Excess |
  |---|---|
  | Structural events | −0.031σ |
  | Event-anchored intent | −0.009σ |
  | Legacy CONFIRMED | −0.010σ |
  | Trend-phase intent (small n) | +0.091σ |

- The values were frozen in `config/dir002_side_assignment_v1.json` (`CALIBRATED_CALIBRATION_WINDOW`; evidence sha256 `8ca109b0…`) before the held-out cohort was read.

## 2. R-5 held-out (cuts from 3 Feb 2025; 8,565 matured rows; read once)

Signed values are drift-adjusted z20 means. The non-inferiority margin is −0.05, tested with a paired date-block bootstrap.

| Side | Coverage new / legacy | New | Legacy | Paired difference [95% CI] | Result |
|---|---|---|---|---|---|
| BULL | 3,408 / 4,464 | −0.010 | −0.000 | −0.010 [−0.047, +0.035] | PASS |
| BEAR | 3,622 / 2,182 | −0.003 | +0.004 | −0.006 [−0.052, +0.043] | **FAIL (by 0.002)** |
| ALL | 7,030 / 6,646 | −0.006 | +0.001 | −0.007 [−0.044, +0.036] | PASS |

- **Raw (unadjusted) signed z20:** new −0.005 vs legacy −0.012 overall.
- **First passage:** favourable-first incidence is 0.316 new vs 0.315 legacy; adverse-first is 0.297 vs 0.307.
- **Transitions:**
  - 4,463 rows keep the same side and 1,320 change side.
  - 1,247 rows are newly directed and 863 newly unassigned.
  - 40 of 271 legacy-correct large moves (|z| ≥ 2) are now unassigned.
- **Transparency variant** (any symmetric setup counts, i.e. without the DEC-1 trend-phase exclusion): all sides PASS, and 24 large winners are missed.

## 3. What this means

1. Out of sample, neither rule shows side skill at 20 sessions. The legacy edge on the calibration window was trend/momentum, and it did not persist.
2. The new rule is symmetric and auditable, and its BEAR coverage is close to BULL coverage. It is non-inferior on BULL and in total. BEAR misses the pre-registered bound by 0.002, so under the protocol the result is **FAIL for BEAR → ACK review**. It is not re-tuned.
3. Neither rule's side has demonstrated predictive authority. Both remain descriptive (`IMPLEMENTED_FOR_REPLICATION`). That is consistent with the design and with the trading-authority rules.

## 4. Decisions for ACK

- **A1.** Accept or reject the amended criteria (§1).
- **Cut-over.** Make `side_assign_v1` the production default despite the marginal BEAR result, or keep `legacy_rollback`. Production is on `legacy_rollback` until you decide.
- **DEC-1 evidence.** Trend carried the only in-sample signal and none out of sample. The data does not argue for reversing DEC-1. The `TREND_PHASE` intent exclusion (my refinement under DEC-1) costs 16 large winners relative to counting every setup; please confirm it.
