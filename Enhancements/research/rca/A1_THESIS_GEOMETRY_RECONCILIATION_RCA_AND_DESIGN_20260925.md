# A1 — Thesis geometry reconciliation: root cause and design

**Date:** 2026-09-25 · **Owners:** Options Intelligence (`_ev3_handoff_fields`, existing owner of the governed geometry handoff), `contracts/thesis_geometry.select_directional_invalidation` (unchanged), Lab extract (`contracts/lab_control`), run manifest (D2 block) · **Authority:** none changed; routing preserved · **Requested by:** ACK ("carry on with A1"); reviewer amendments A1 (distinct counts, validity test of the Wyckoff fallback, vol-relative degenerate rule, no revival claims)

## 1. What the register claimed and what the data says

| Register / review statement | Finding on the 25 Sep morning book (1,355 directional rows) |
|---|---|
| 375 (24 Sep) / 175 (25 Sep) rows lack an invalidation because the Thesis owner did not publish one | **The pipeline already uses the Wyckoff validation level as the governed fallback.** `select_directional_invalidation` tries, in order, the governed invalidation, the Wyckoff structural invalidation level, the structural stop and `stop_loss` (both refused when the source is `ATR_FALLBACK`), then `invalidation_price`, and takes the first level on the thesis side. 1,309 of 1,355 rows have an ATR-fallback stop, so on 1,134 rows the Wyckoff level **is** the invalidation (`invalidation_source = WYCKOFF_VALIDATION`, 1,180 rows) |
| Supplying a Wyckoff fallback could recover up to 375 (later 63) rows | **Zero.** On all 175 rows without an invalidation the Wyckoff level exists and lies on the **wrong side** of spot for the governed direction (175 of 175); the ATR stop is refused by policy; no governed level exists. These are theses whose structure contradicts their direction. A valid death, mislabelled |
| The label | The selector returns `DATA_DEFECT_WRONG_SIDE` when a numeric candidate existed off-side, but `_ev3_handoff_fields` writes `invalidation_state = MISSING` whenever the stop is `None`, discarding the selector's state. So 175 wrong-side rows read as "missing" |
| Missing targets | 223 rows. 175 lack both (no stop → no 3R fallback). Of the 48 with an invalidation: **41 are PUTs whose stop sits 34–41% above spot**, so the 3R fallback target is non-positive (`TARGET_3R_NON_POSITIVE`); **7 have a computed 3R target in `target_spot` that the Lab never reads** because `target_spot` is not in the extract's alias map (`TARGET_3R` with `target_state = UNRESOLVED` in the book) |
| The 1% degenerate rule | On the 273 actionable rows: 16 by the 1% rule, **24 by the vol-relative rule** (a level inside 0.25 × the cumulative expected move for the bucket). The vol-relative rule is adopted |
| 3R targets from wide stops | The 7 recovered targets are 25–180% from spot (NLST 5.62 → 15.64; WAFD 30.91 → 8.83): a 3R fallback on a 24–40% stop yields an unreachable target. Carrying the number is right (it is the pipeline's, labelled `TARGET_3R`); reachability is a valuation question, and the manifest should count how many targets lie beyond 3 × the expected move |

## 2. Design (additive)

1. **Options Intelligence handoff:** emit `invalidation_candidate_state` = the selector's state (`AVAILABLE`, `DATA_DEFECT_WRONG_SIDE`, `MISSING`, `MISSING_ENTRY`, `NOT_EVALUABLE`, or `NOT_APPLICABLE_NON_DIRECTIONAL`). `invalidation_state` and `invalidation_source` are unchanged, so every routing consumer behaves identically; the new field says what was measured. Emitted in the options CSV, projected to the Lab book (field list, projection, alias map), added to the ILA golden's additive list.
2. **Lab extract:** `target_spot` joins the `structural_target` alias list (after the structural sources) and gets its own alias, so a computed fallback target reaches the book with its `target_price_source`.
3. **Manifest geometry block (D2) gains:** `missing_invalidation_by_source` and `missing_target_by_source` (counters over the candidate rows' `invalidation_source` / `target_price_source`, which the fixed candidates schema already carries); `degenerate_vol_relative` and `actionable_degenerate_vol_relative` (either level inside 0.25 × the cumulative expected move for the row's bucket, reconstructed as the sum of the legacy increments `garch_expected_move_1_5d`, `_6_10d`, `_11_20d` in percent of spot); `target_beyond_3x_expected_move` as a reachability count; `degenerate_unassessed` where the move fields are absent. No flag, no label change from these counts.

**What is not done, and why.** No fallback source is added: the only candidate not already tried is the ATR stop, which the policy refuses as a convention rather than thesis evidence, and the review's precondition (side and age validity) fails on every row where it would matter. The wide-stop PUT targets are a Thesis-context question (why is the Wyckoff invalidation 34–41% above spot on a PUT thesis?) and are counted, not repaired. The wrong-side split reaches the Lab through the new field but not the manifest until the candidates schema carries it (F1.c).

## 3. Tests (written first), `tests/test_a1_geometry_labels.py`

- Handoff: stop `None` with selector state `DATA_DEFECT_WRONG_SIDE` → `invalidation_candidate_state = DATA_DEFECT_WRONG_SIDE` and `invalidation_state` still `MISSING` (characterisation of the routing field); stop present → `AVAILABLE`; non-directional → `NOT_APPLICABLE_NON_DIRECTIONAL`.
- Lab extract: alias list carries `target_spot`; an options CSV with only `target_spot` populates `structural_target` and `target_price` in the extracted row.
- Manifest: source counters, vol-relative degenerate count with the increments reconstructed cumulatively, unassessed count, reachability count; `run_tradeable`, label and permissions unchanged.

## 4. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `scripts/avshunter_options_intelligence.py` +13: `invalidation_candidate_state` in the handoff and the options CSV columns. `contracts/lab_control.py` +50: the field in the book list, projection and aliases; `target_spot` aliased; the geometry block gains `missing_invalidation_by_source`, `missing_target_by_source`, `degenerate_vol_relative`, `actionable_degenerate_vol_relative`, `degenerate_unassessed`, `target_beyond_3x_expected_move`, and the basis labels. Golden additive list extended |
| Tests written first | `tests/test_a1_geometry_labels.py`: 1 characterisation (routing state unchanged), 6 business rules; all pass |
| Regression | D2 6/6, D3 6/6, EV3 options handoff 38/38, ILA golden 7/7, book integrity E3–E7 31/31, direction geometry repairs 9/9, options research contract 11/11, pretrade focus 9/9, evening thesis 17/17, F1.b 7/7, big-bang 3/3; `--evening --plan-only` exit 0 |
| Preview on this morning's real run (in memory) | population 1,355 · missing target 224 (`NO_TARGET_SOURCE` 175, `TARGET_3R_NON_POSITIVE` 41, `TARGET_3R` 7, `DISCOVERY_TARGET` 1) · missing invalidation 175 (`MISSING_AUTHORITATIVE_STOP` 175) · degenerate vol-relative 163 of 1,180 assessed, 18 of 273 actionable · unassessed 175 · **targets beyond 3 × the expected move: 547** · label and health unchanged |

Two readings from the preview that go beyond A1's scope. The 547 targets beyond three times the bucket's expected move are the structural-versus-reachable gap of fix item F2 measured at manifest grain: a structural target set for a 20-session thesis is being compared with a 1–5 or 6–10 day bucket's move, which is the horizon-labelling defect of H1. And one row carries `target_price_source = DISCOVERY_TARGET` with no target, a labelling inconsistency to trace when the Thesis owner is next opened.

## 5. Acceptance

Monday's morning book: the 175-type rows read `invalidation_candidate_state = DATA_DEFECT_WRONG_SIDE`; the manifest shows `missing_invalidation_by_source = {MISSING_AUTHORITATIVE_STOP: n}` and `missing_target_by_source = {TARGET_3R_NON_POSITIVE: n, ...}` beside the population; the 7 `TARGET_3R` rows carry their target with its source.
