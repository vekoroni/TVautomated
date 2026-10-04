# Data Integrity Remediation — working record (Fix Spec, 24 Sep 2026)

**Spec:** "AVSHUNTER Pipeline Fix Spec — Data Integrity Remediation" (ACK, 24 Sep 2026).
**Status (24 Sep 2026, evening):** ACK approved D1–D5 as recommended. Fix 1a verified; Fix 1b, Fix 2, Fix 3, Fix 4 and D5 implemented test-first and green; regression gate built with the flagged-state and wall-side checks. Uncommitted. Outstanding: a real pipeline run and Lab visual check post-fix (ACK runs pipelines), and the gate's ≥ 95 percent target measured on that run.
**Rule kept:** every producer change is characterised on stored runs first, per direction, then pinned by a failing business-rule test, then changed minimally, then traced to every consumer in the graph below (spec cross-cutting protocol, CLAUDE.md rule 4).

## 1. Consumer graph (production modules only; tests, docs, archives excluded)

| Field | Producer (one owner after the fix) | Readers that change decisions or display |
|---|---|---|
| `rr_options` | `scripts/avshunter_options_intelligence.py::compute_trade_economics` (L6300) | same file: OIS score L6590 (`econ.get('rr_options', 0)`), wrong-strike demotion L6897, research handoff L7318 (`_oi_float`), contract-selection metrics L8467/L8523; `scripts/avshunter_superbrain_layer.py` L1337 (`float(... or 0)`), L1980, L2130; `eod_candidate_engine.py` L1517, L1557, L1586, L2207; `contracts/lab_control.py` L2948, L3791–3792 (`rr_premium_expected` alias); `contracts/opportunity_tier.py` L155, L286; `morning_gate.py` L2202, L3936; `execution_intelligence_runner.py` L1993, L2160; `scripts/core_intel_exporter.py` L246, L430; `intelligence-lab/intelligence_lab.py` L840, L1134, L1917, L2976, L3134 (`float(s.get("rr_options",0) ...)`); Lab page shows `rr` (book alias) |
| `iv_rank`, `iv_percentile`, `ivp_label` | options script, **seven** writers today (see §3) | same file: EV `iv_factor` L6398, verdict L6477, L6774, research L7342; spread tiers `_derive_eod_spread` L2631 (CHEAP 0.04 / FAIR 0.06 / else 0.10); convexity `_ivp_from_ctx` L838; `scripts/avshunter_superbrain_layer.py` L547, L784, L1879; `execution_intelligence_runner.py` L520, L616, L2161; `position_sizing_engine.py` (18 refs); `vanguard/layer2_statistical/state_calculator.py`, `edge_detector.py`; `mcmillan_advisory_layer.py`; `contracts/lab_control.py` L602–603, L3449–3450, L3858–3859; `intelligence-lab/intelligence_lab.py` L1354, L2014–2017 (**writes its own label from `_iv_pct` with 20/50 thresholds — an eighth writer, on the display side**); Lab page L1148, L2204, L2260, L2275, L2483–2484, L2826, L3319 (labels the number "IVP" while reading `iv_rank`); `scripts/core_intel_exporter.py` L429–437 |
| `call_wall`, `put_wall` | `compute_oi_walls` (L3205), published L7612 → row L8251 area | `wall_break_scorer.py` L191–192, L277–279 (distance, phase B/C triggers, grade); `execution_gate.py` L371–379 (runway from put wall); `avshunter_exit_engine.py` L317–328; `execution_intelligence.py` L288–293 (synthesised GEX map anchors); `scripts/avshunter_superbrain_layer.py` L616–660 (runway, V2_NO_RUNWAY); `eod_candidate_engine.py` L2319; `contracts/lab_control.py` L612–613, L3459–3460; Lab L1360–1361; page L1155, L2767–2768 |
| `gamma_flip` | `compute_gex` (L3048), published L7611 → row L8251 | `execution_gate.py` L372, L381–391 (0.75× size when spot above flip); `wall_break_scorer.py` F3 L231 and `gamma_flip_conf` F2; `catastrophe_gate.py` L199–253, L327–349; `execution_intelligence.py` L296; `avshunter_monetisation_policy.py` (9); `contracts/lab_control.py` L614, L3461; page L1156, L2769 |

Silent-failure handlers found (spec protocol step 2): `econ.get('rr_options', 0)` L6590; superbrain `float(_f(signal,'rr_options') or 0)` L1337; `eod_candidate_engine` L1517 `_flt(...) or _flt(...)` then `>= 1.0` at L1557; Lab L3134 `float(s.get("rr_options",0) or ... or 0)`; `execution_intelligence_runner` L616 `_fv("iv_rank", 50.0)`; research L7344 `(iv_rank or 50.0)/100`. Each must accept `None` plus a state once Fix 1b lands.

## 2. Fix 1 — `rr_options`: evidence on 12 runs, by direction

Columns: rows with a numeric `rr_options`; negatives; exactly −1.0; above 20×; mark ≤ $0.01; bid and ask both empty; target on the wrong side of entry; among −1.0 rows, strike beyond target; among negatives, breakeven beyond target.

| Run | Dir | n | neg | −1.0 | >20× | mark≤.01 | bid/ask 0 | wrong side | strike beyond tgt | be beyond tgt |
|---|---|---|---|---|---|---|---|---|---|---|
| 20260909_071646 | CALL | 659 | 62 | 12 | 36 | 0 | 0 | 0 | 12 | 62 |
| | PUT | 382 | 9 | 0 | 32 | 0 | 0 | 0 | 0 | 9 |
| 20260913_143230 | CALL | 747 | 117 | 22 | 12 | 0 | 0 | 0 | 22 | 117 |
| | PUT | 330 | 3 | 0 | 13 | 0 | 0 | 0 | 0 | 3 |
| 20260917_214854 | CALL | 309 | 29 | 6 | 7 | 0 | 0 | 0 | 6 | 29 |
| | PUT | 132 | 8 | 2 | 7 | 0 | 0 | 0 | 2 | 8 |
| 20260919_205844 | CALL | 818 | 274 | 49 | 1 | 0 | 0 | 0 | 49 | 274 |
| | PUT | 323 | 22 | 1 | 7 | 0 | 0 | 0 | 1 | 22 |
| 20260922_223221 | CALL | 875 | 245 | 35 | 5 | 0 | 0 | 0 | 35 | 245 |
| | PUT | 301 | 40 | 0 | 7 | 0 | 0 | 0 | 0 | 40 |

(The other seven runs show the same pattern; full table in the session log.)

Findings:
- **1a is resolved on every run since 9 Sep**: no PUT or CALL target on the wrong side of entry. `tests/test_fixspec_rr_options_direction.py` pins `_governed_structural_target` for both directions and every source (discovery, L1 far, 3R), 19 tests green.
- **The mark-floor mechanism never fires** in stored data: 0 rows with mark ≤ $0.01, 0 rows with empty quotes, in either direction on any run. The spec's 659× example (WBD, 22 Sep) is a genuine $0.02/$0.03 quote with a 40 percent spread, already `STAND_DOWN` with `BLOCK_SPREAD`.
- **Every negative is target inside breakeven** (premium exceeds intrinsic at target) and **every −1.0 is a strike beyond the target** (call strike ≥ target, put strike ≤ target). These are facts about the trade geometry, identical in mechanism for calls and puts, and today indistinguishable from a defect because the row carries no state.
- **Every >20× is a real mark against a target 48–156 percent from entry**, 1,108 of 1,176 priced rows on 22 Sep use `TARGET_3R` (entry ± 3 × stop distance). The extreme R:R is a thesis-target geometry question (Thesis Context owns the target), not the options engine.
- A gate at the ticket spread limit (`outcome.signal.max_entry_spread_fraction` = 0.10) would flag **70–90 percent of priced rows every day** (972 of 1,176 on 22 Sep); the 25 percent liquidity block already exists as `spread_above_limit` / `BLOCK_SPREAD`.

### Adjusted Fix 1b design (decision D1 requested)

Single owner `compute_trade_economics` publishes, for both directions, with sign-aware geometry:

| `rr_options_state` | `rr_options` | Meaning |
|---|---|---|
| `PRICED_TARGET_ABOVE_BREAKEVEN` | > 0 | intrinsic at target exceeds premium |
| `PRICED_TARGET_INSIDE_BREAKEVEN` | −1 < rr ≤ 0 | target beyond strike but inside breakeven: partial loss at target |
| `STRIKE_BEYOND_TARGET` | −1.0 | option worthless at target |
| `MARK_UNPRICED` | `None` | mark missing, ≤ 0 or not finite: **no $0.01 floor, no computation** |
| `QUOTE_MISSING` | `None` | bid and ask both missing or zero |
| `NOT_EVALUATED` | `None` | existing non-directional / target-unresolved cases (unchanged) |

Plus `rr_options_spread_fraction` and `rr_options_tradeability` ∈ {`WITHIN_TICKET_SPREAD_LIMIT`, `ABOVE_TICKET_SPREAD_LIMIT`, `QUOTE_UNAVAILABLE`} using the registry value (never a literal). **Deviation from the spec:** a wide spread flags the row but does not null `rr_options`, because (a) the number is computable and true, (b) R11 rank-don't-gate, (c) it would blank the ranking input on most of the book, and (d) tradeability is already gated at 25 percent. `MARK_UNPRICED` and `QUOTE_MISSING` do null it, as the spec asks. All consumers in §1 are then made `None`-safe and the Lab shows the state.

**Decision D2 (approved 24 Sep):** the >20× rows are a `TARGET_3R` geometry issue outside this spec, recorded as a Thesis Context finding (stop distance × 3 with wide stops); R:R is not clamped. The gate keeps >20× as a flag.

### Fix 1b implementation record (24 Sep 2026, D1 approved)

Engine (`scripts/avshunter_options_intelligence.py`), test-first (`tests/test_fixspec_rr_options_state.py`, 22 green for long calls and long puts; the characterisation of the $0.01 floor was green before and retired with the change):
- `compute_trade_economics` reads mark, bid and ask through `_oi_float`; an unpriced mark (missing, ≤ 0, not finite) returns `_economics_not_evaluated('MARK_UNPRICED')`, a priced mark with no quote at all returns `QUOTE_MISSING`; the `$0.01` floor is gone (source-guarded). Every NOT_EVALUATED row now carries `rr_options_state` and `rr_options_tradeability`.
- Priced rows publish `rr_options_state` from sign-aware geometry: `PRICED_TARGET_ABOVE_BREAKEVEN`, `PRICED_TARGET_INSIDE_BREAKEVEN`, `STRIKE_BEYOND_TARGET`; `rr_options_spread_fraction` = (ask − bid)/mid and `rr_options_tradeability` against the registry value `outcome.signal.max_entry_spread_fraction` (`ticket_spread_limit_fraction()`, cached, `TICKET_LIMIT_UNAVAILABLE` when the registry cannot be read; no literal). A wide spread flags, it does not null.
- OIS scorer is None-safe for `rr_options`, `theta_drag_pct`, `breakeven_pct`, `ev_ratio` and names the state in its factor text. Row projection, CSV export and the vanguard pass-through carry the three fields; `scripts/avshunter_superbrain_layer.py` and `eod_candidate_engine.py` copy them.
- Replay of run `20260922_223221` (1,176 priced rows): every `rr_options` identical to the stored value (0 differences); states CALL 630 above / 210 inside / 35 strike-beyond, PUT 261 / 40 / 0; tradeability 971 above the 10 percent ticket limit, 205 within. No row is MARK_UNPRICED or QUOTE_MISSING, as the 12-run evidence predicted.

**Lab display, correction to D1.** `write_final_opportunity_book` strips every `rr_`-prefixed field before publication by an earlier governed decision (commit `c36c55b`, 12 Sep 2026: "R:R is retained in upstream research artefacts only. It is neither a v4 ranking input nor a required/displayed Lab field"). The state therefore travels with the R:R in the options CSV, the SuperBrain/EIL layer and the EOD engine, and the Lab shows no R:R at all — there is no stale number on screen to replace. My D1 text ("the Lab shows the state") is withdrawn in favour of that decision; reinstating R:R on the Lab would be a separate product decision (spec Fix 1b ripple item 3), recorded here as open.

## 3. Fix 2 — IV fields: writers found (seven in the engine, one in the Lab)

| # | Site | Writes | Basis | Threshold |
|---|---|---|---|---|
| A | L1868–1878 per-contract MarketData `ivRank` | `iv_rank`, `iv_percentile`, `ivp_label`, `ivp_source='marketdata.app'` on the contract dict | provider field | 30/70 |
| B | L4230–4260 inside `compute_iv_context` | `iv_percentile` = max(IV vs 252d realised-vol range, IV vs 30d range), `iv_rank` = ×100, label CHEAP only if both windows agree | **realised-vol range, not IV history** (spec §1042: "not an IV percentile") | 0.40/0.65 |
| C | L3850 `_apply_true_iv_percentile`, called L4285 after B | `iv_percentile` share of own ATM-IV history below today, `iv_rank` = ×100, label, `iv_percentile_source='IV_HISTORY_252D'`; keeps B under `iv_vs_rv_range_*` | IV history (`iv_history` SQLite, ≥ 20 samples) | 0.40/0.65 |
| D | L4183 iv_engine proxy when chain has no IV | `iv_rank` clamped 20–80, `iv_percentile` 0.20–0.80, label = VRP signal | proxy | n/a |
| E | L4199 no IV at all | `iv_rank` 50, `iv_percentile` 0.50, `FAIR` | **neutral default (violates R1)** | n/a |
| F | L4214 (< 60 closes) and L7860 (contract IV proxy) | 20/40/60/80 buckets from absolute IV level | absolute level | 0.30/0.70 at L7864 |
| G | L7652 scanner branch | `iv_rank` = scanner `iv_rank` × 100, `iv_percentile` = scanner `iv_rank`, `iv_percentile_source='SCANNER_IV_RANK'` | scanner value | `_ivp_lbl` |
| H | L7891 VRP refinement | flips `FAIR` → `CHEAP`/`EXPENSIVE` from `vrp_signal` | overrides the label after the number | n/a |
| Lab | `intelligence_lab.py` L2014–2017 | `opt__iv_rank`, `ivp_label` from `_iv_pct` | display-side recompute | 20/50 |

`iv_rank == iv_percentile × 100` on 1,379 of 1,379 populated rows (22 Sep): the field is a percentile under a rank's name (spec 2a confirmed). The A-path comment about Polygon is stale (Polygon options decommissioned).

Design to implement (spec 2a/2b, no deviation): one resolver at the end of `iv_ctx` assembly publishes `iv_percentile` (C, else B, else A, else `None`), `iv_rank_range` = (IV − min)/(max − min) over the same IV history with `iv_rank_window_sessions` disclosed (`None` below 20 samples), `iv_rank` **becomes the range rank on the 0–100 scale its readers expect**, with the additive version marker `iv_rank_definition='RANGE_IV_HISTORY'` (old runs carry no marker and are therefore distinguishable, spec protocol step 3) and `iv_rank_window_sessions`, `ivp_label` from one threshold pair (0.40/0.65, governed constants), `ivp_source` on every row naming the winning path and the suppressed ones; D, E, F, G, H stop writing the three fields (D/F/G may publish their own values under their own names; E becomes `None` + `UNAVAILABLE`). Lab: display IV Rank (range) and IV Percentile as two labelled fields, source on hover; stop recomputing a label at L2014.

### Fix 2 implementation record (24 Sep 2026)

Engine (`scripts/avshunter_options_intelligence.py`), test-first (`tests/test_fixspec_iv_single_owner.py`, 10 green; characterisation of the old behaviour was green before the change and retired with it):
- `iv_rank_from_history` (range statistic over the ticker's IV history, `None` below 20 samples or on a flat range) and `IV_RANK_DEFINITION='RANGE_IV_HISTORY'`.
- `resolve_iv_ownership(iv_ctx, contract)` is the only writer of `iv_percentile`, `iv_rank`, `ivp_label`, `ivp_source` (guarded by a source-scan test): precedence IV history > realised-vol range proxy (`iv_vs_rv_range_primary`, no rank) > MarketData contract ivRank (`iv_*_marketdata`) > `UNAVAILABLE`; suppressed candidates listed in `ivp_suppressed_sources`; `iv_rank_definition` and `iv_rank_window_sessions` disclosed; one threshold pair (`IVP_CHEAP_MAX` 0.40 / `IVP_EXPENSIVE` 0.65) applied to the published 3-decimal percentile so label and number always agree.
- Writers A (per-contract ivRank, 30/70), B (realised-vol range), D (engine proxy 20–80), E (neutral 50 / FAIR), F (absolute-level buckets, 20/80 and 30/70), G (scanner branch) now publish candidates under their own names; H (VRP flips FAIR → CHEAP/EXPENSIVE) no longer touches the label. Stale Polygon comment removed. Row and CSV pass-through carry the four new fields.

Book and Lab (`contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py`, `intelligence-lab/static/index.html`; `tests/test_fixspec_iv_lab_display.py`, 4 green): the book publishes `iv_percentile`, `ivp_source`, `iv_rank_definition`, `iv_rank_window_sessions` beside `iv_rank` and `ivp_label`, from the options owner's names only (the copied `ivp` / `iv_alignment` aliases are dropped); the Lab server's live-IV overwrite (an eighth writer, 20/50 thresholds, label RICH) is removed; the page shows IV Rank and IV Percentile as two numbers with the source on hover, exports both, and no longer invents a label from a number. Regression: 15 existing engine, book and Lab test files green after the change; the ILA-003 golden guard now lists these four fields as later additive fields.

Consumers re-verified and left as they are, with the meaning change recorded (spec ripple step 5): `position_sizing_engine.py` L384 reads `iv_rank` first where its comment says it meant the percentile — with the range rank its `> 0.80` penalty now means "IV in the top fifth of its yearly range", the industry meaning; `scripts/avshunter_superbrain_layer.py` L784 convexity "underpriced vol" reads `iv_rank` (now a range rank, the intended meaning); `execution_intelligence_runner.py` L616 still defaults a missing `iv_rank` to 50 in its synthetic-spread proxy (legacy EIL, display diagnostics). **Decision D5 requested:** whether position sizing should read `iv_percentile` (its stated intent) or keep the range rank (industry meaning).

Historical comparability: books published before 24 Sep carry no `iv_rank_definition`; their `iv_rank` is the percentile × 100. Saved thresholds on "IV Rank" must be re-read as percentile thresholds.

## 4. Fix 3 — equal walls: mechanism confirmed

Replaying the 22 Sep stored chain snapshots (`data/canonical/market_observations/option_chain/2026-09-22/<ticker>/`) through `compute_oi_walls` reproduces the published `call_wall`, `put_wall` and `max_pain` **exactly** for every sampled affected ticker (REAX, HLF, BHVN, GNTX, PATH, ESAB). Nothing downstream introduces the equality, and the GEX-based fallback at L970 is a reader for the convexity score, not the publisher. The same strike simply carries the largest summed open interest on both sides: REAX 16 of 58 rows have any OI; 68 of 96 equal-wall rows also equal `max_pain`; **38 of 96 "call walls" are below spot and so cannot be a ceiling**. Root cause: the definition (max-OI strike per side, unconstrained by side of spot) is unfit for the consumers that treat walls as a ceiling above and a floor below (wall-break scorer distance and phase triggers, execution-gate runway, exit engine).

**Decision D3 requested:** publish side-constrained walls as the governed fields the consumers read (`call_wall` = strongest strike **above** spot, `put_wall` = strongest strike **below** spot, `None` with a reason when no strike qualifies), keep the raw max-OI strikes under `oi_max_call_strike` / `oi_max_put_strike`, and decide whether "strongest" is OI (today) or GEX (GEX investigation recommendation 2). Consumers to re-verify: wall-break scorer through to the Lab "Distance to Wall".

## 5. Fix 4 — gamma flip: source located, mechanism confirmed

`opt__gamma_flip` is written by `compute_gex` (options script L3048–3083), not by `canonical_data/gamma_exposure_store.py`. Replay reproduces all 9 implausible values on 22 Sep exactly. Mechanism (GEX investigation GEX-D1, 14 Sep): the flip is the **first sign change scanning from the lowest strike**, so deep out-of-the-money strikes win (MRNA flip 15.20 vs spot 182.56; HOOD 10.01 vs 124.25), and when no crossing exists the code **falls back to the strike with the smallest |GEX|** (STNE 0.47 = the lowest strike). Consumers that change decisions: `execution_gate.py` sizes 0.75× when spot is above the flip (81.6 percent of rows per the GEX investigation), wall-break F3/F2, catastrophe gate.

**Decision D4 requested:** implement the GEX investigation's design (flip from the crossing nearest spot on a re-priced grid, `None` with reason `NO_GEX_CROSSING` when none, sanity band relative to spot with reason code, never a fallback strike), and confirm that the execution-gate size rule is re-measured or suspended when the flip changes meaning, since that rule currently acts on 4 of 5 rows.

### Fix 3 implementation record (24 Sep 2026, D3 approved: side-constrained OI walls, raw maxima kept)

`compute_oi_walls(df, spot)` (`tests/test_fixspec_oi_walls_side.py`, 10 green; the unconstrained characterisation was green first and retired): `call_wall` is the strongest call-OI strike strictly above spot, `put_wall` the strongest put-OI strike strictly below it; `call_wall_state` / `put_wall_state` name absence (`NO_STRIKE_ABOVE_SPOT`, `NO_OPEN_INTEREST_BELOW_SPOT`, `SPOT_UNAVAILABLE`, `NO_CHAIN_DATA`); the old per-side maxima stay as `oi_max_call_strike` / `oi_max_put_strike`; `max_pain` unchanged. Engine passes spot at the call site; both row projections and the CSV export carry the four new fields; the book and the page carry the two states (an absent wall shows its reason, not "$—"). Replay of all 1,379 stored 22 Sep chains: before 96 coincident walls and 529 rows with a wall on the wrong side; after 0 and 0, 1,379 call walls above spot, 1,374 put walls below, 5 puts with no OI below spot; raw maxima equal the previously published walls on every ticker. Consumers checked: wall-break scorer, execution gate, exit engine, superbrain runway and EIL map all guard `None`/0 already; the superbrain `V2_AT_WALL` veto fired 0 times on 22 Sep so no decision changes. Gate gains `wall_side_bad`.

### Fix 4 implementation record (24 Sep 2026, D4 approved)

`compute_gamma_flip(df, spot)` and `dealer_gamma_profile` (`tests/test_fixspec_gamma_flip.py`, 8 green; legacy characterisation green first, retired): total signed dealer gamma (calls +, puts −) re-priced with each contract's IV and expiry on a ±25 percent grid in 0.5 percent steps; the flip is the crossing nearest spot, interpolated; no crossing → `None` + `NO_GEX_CROSSING_WITHIN_GRID`; no usable IV/expiry/OI → `INSUFFICIENT_CHAIN_DATA`; the fallback to the smallest-|GEX| strike is gone (source-guarded). `compute_gex` keeps the per-strike surface for gamma islands and returns the new flip; `gamma_flip_state`, `gamma_flip_method` and `gamma_flip_legacy_first_sign_change` are published beside it (row, CSV, book state, page). Replay of 1,379 stored chains (41 s): legacy replica equals the published flip on all 1,379 (GEX-D1 confirmed as the source); new flip found on 955, none on 424; distance from spot median 27.1 → 8.0 percent, p90 67.1 → 19.7 (the GEX investigation's re-priced figures were 5.5 / 21.5); `gf_bad` 9 → 0. **Size rule:** `execution_gate.py` already made walls and the flip display-only on 19 Sep (D6, rule 6: warnings kept, size no longer scaled), so no sizing decision changes; the display-only `ABOVE_FLIP` share moves from 83.8 percent of 1,379 to 65.1 percent of 955. Consumers checked: wall-break F3 (`gamma_flip_gap_pct` default), catastrophe gate (default 25), gamma velocity (`None`-safe), Lab. `gamma_flip_conf` remains the ad hoc density score (GEX-D3), unchanged and out of scope.

### D5 implementation record

`position_sizing_engine._options_multiplier` reads `iv_percentile` → `ivp_252d` → legacy `iv_rank` only when `iv_rank_definition` is absent → its own 0.50 default (`tests/test_fixspec_position_sizing_iv.py`, 3 green); sizing behaves exactly as before Fix 2 on old and new books.

## 6. Regression gate

`Enhancements/assessment/dossier_field_integrity_gate.py` (+ `tests/test_dossier_field_integrity_gate.py`, 5 green): the spec's four checks plus the flagged-state check, per direction. `rr_bad` now treats a negative R:R as bad only when it lacks the state that explains it (once the state exists), and keeps >20× as a flag. Baseline on 22 Sep: CALL 73.9 percent clean, PUT 70.1 percent, all 75.7 percent (ivp 286, walls 96, gamma 9, rr 12). The ≥ 95 percent target is unreachable while `ivp_bad` counts A-path 30/70 labels and walls use the current definition; it becomes meaningful after Fix 2 and D3.

## 7. Other candidates from the spec, checked

- R11 (`025c284`) changing `apply_daily_cap` to rank-not-gate: cannot raise the mark-floor rate because that rate is zero; it does raise the count of priced rows with inside-breakeven targets reaching the ticket stage, measurable with the new state.
- Multi-writer pattern beyond `ivp_label`: yes, `rr`/`rr_predicted`/`rr_premium_expected` aliases and walls (`top_call_wall`/`gex_wall_call`/`call_wall`) show the same shape; recorded here, not fixed in this spec.
- `MONETISATION_BLOCKERS_20260918.md` read: §8 already lists the gamma flip (GEX-D1) and OI-walls-as-GEX-walls defects; item 8 of its remediation order is the same work as Fix 3/4.
