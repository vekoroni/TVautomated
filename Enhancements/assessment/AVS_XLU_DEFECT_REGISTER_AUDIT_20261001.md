# XLU defect register: audit against the pipeline (1 Oct 2026)

**Scope:** read-only, so no fixes. Five parallel audits checked the current code and the stored run `data/output/runs/20260930_083504` (session 29 Sep), using the register's confirming tests.

**Provenance caveat:** that run was partly re-materialised on 1 Oct: options and execution 16:05, Morning 17:06, book 17:17, interpreter desk 20:31–20:38 BST, Morning gate refresh 11:40 ET. Only `trigger_layer_summary` is original.

**Today's changes** (BEH-001 phase 1/2, DIR-002, governance stamp, candidate packet, options candidate lane, timeframe precedence) are uncommitted. Production direction is `legacy_rollback`.

## Verdicts

| ID | Sev | Verdict | Corrected root cause (evidence) | Today's changes |
|---|---|---|---|---|
| D01 | P0 | **PARTIAL.** Uncapped target confirmed; put-wall anchor not confirmed | Discovery had no target (`PENDING_OI`). Options fell back to entry − 3 × invalidation distance (`_governed_structural_target`, `avshunter_options_intelligence.py:4565-4607`) on a 12.4% stop: 39.71 − 3×4.9401 = 24.8897; the wall at 25.00 is coincidence. 151 of 259 PUT targets exceed 3× the hv budget, all of them TARGET_3R. `domain/reachability.py` already computes 37.20 for XLU, as advisory only. | Not addressed. Under rollback, structural_target is unchanged. Under `beh001_v1`, `target_state=NONE` would suppress 3R, but the replacement targets (BEH-001 Outcome_Level, the LEVEL geometry, the candidate lane) also have no volatility cap. The adapter labels PRIOR_RANGE_EXTREME as "WYCKOFF". |
| D02 | P1 | **CONFIRMED** | The 10Y was in the governed record (5.26) but did not reach the desk. Book macro fields are empty (`lab_control.py:3824`), and the digest whitelist (`interactive_desk.py:42-62`) omits `macro_rates_context`. Web search is always on (`anthropic_desk_provider.py:159-167`) and "news only" is prompt text. It filled the gap with Gabelli (asof 1 Sep). There is no number-to-field checker (`_validate_report` checks structure only). | Not addressed |
| D03 | P1 | **CONFIRMED, wider:** all 1,570 rows have USMI `SECTOR_UNMAPPED` | (1) The `gics_sector="ETF"` placeholder hides `sector_etf=XLU` (`lab_control.py:4913`, `interpreter_macro_context.py:439`, `macro_quant_packet.py:503`). (2) USMI routes are keyed by free-text themes and ignore `sector_routing.routing` (`us_money_index_contract.py:278-313`, `us_money_index.py:94-118`). (3) There is no utilities route or alias. | Not addressed |
| D04 | P1 | **CONFIRMED** (stored iv_rank is 17.8, not 90; IVP is 71.6) | `trigger_layer.py:356-390` reads only Crabel state and ATR percentile. 608 of 1,619 fire; 107 of those at IVP > 70, 271 at IV/HV > 1.3. The trigger fires even at IVP 99. There is also a labelling defect: iv_rank 17.8 against IVP 71.6 on one row. | Not addressed. BEH-001's Crabel candidate isn't used by the trigger layer. It also has no IV condition, and it can take the controller's side, so "never sets direction" is imprecise. |
| D05 | P1 | **PARTIAL.** The hypothesis needs correcting | Selection isn't vega-blind; it rewards more vega whatever the IV level (`vega_score=min(100,vega*300)`, :5483). It has no IV rank, IVP or IV/HV input. A 40-day runway floor and a 0.5 per day excess-DTE penalty pull selection long. Median DTE is 79 for 20-session holds, and DTE doesn't respond to IVP. XLU had a 51-DTE alternative. | **Not addressed, and it now reaches a new output:** the candidate lane reuses `select_best_contract` unchanged (separate CSV, measurement only) |
| D06 | P1 | **PARTIAL.** The cause is elsewhere | The Morning did refresh the quote (15:32Z, FRESH, delta −0.511, spread 6.45%). The stale values come from the Interpreter's contract block, which reads EOD fields only (`confluence_evidence.py:184-189`). That raised BLOCKING_EVIDENCE_REFRESH. EV3 rejected `REJECT_QUOTE_STALE` as advisory only, so the action stayed BUY_NOW. | Not addressed (the Morning gate diff doesn't touch the confluence builder) |
| D07 | P2 | **CONFIRMED** | No signed spot-vs-flip field. `wbs_notes` "CLOSE (3.7%)" is unsigned and measured from 39.71. Two wrong-side statements in the reports. | Not addressed |
| D08 | P2 | **CONFIRMED** | The deterministic wall-side fields exist (`call_wall_state=OI_MAX_ABOVE_SPOT`) but the desk whitelist drops them. One report is inverted; the other is correct. | Not addressed |
| D09 | P2 | **CONFIRMED,** root cause corrected | "D" is a phase letter (`wyckoff_phase_validator.py:343`; `_norm_phase` truncates words to their first letter). For XLU, "D" means Phase D of a DISTRIBUTION. The digest sent `wyckoff_phase_bucket=ACCUMULATION`, which comes from a phase-B fallback default (`avshunter_db_update.py:503-506`), not `wyckoff_mode=DISTRIBUTION`. So the reports' main counter-case rests on a default label. | Not addressed. The Wyckoff `_extract_features` range-anchoring change is earlier uncommitted work, already in the 1 Oct baseline patch, not today's. BEH-001 adds another set of phase letters, which the desk doesn't receive. |
| D10 | P2 | **CONFIRMED,** and wider | `_thesis_state_from_eod_status` returns VALID_* for everything the ladder emits; all 1,570 rows are VALID_*. MITIGATED → EOD_TRIGGER_READY → VALID_THESIS_TRIGGER_PENDING (`eod_candidate_engine.py:1302, 574-592`). OBSERVE_ONLY is never read: 1,523 rows. SOFT_CONFLICT is written later by the Lab and is on all rows. | Not addressed. **Under `beh001_v1`,** the `dir_v1.3.0` branch writes OPPOSING_SIDE_OBSERVATION with gate NONE. That removes the only caution on this path, so the defect gets worse if the direction source switches before D10 is fixed. |
| D11 | P2 | **CONFIRMED,** and worse than reported | Any favourable move above 0 gives GAP_CONFIRMATION_WITH_RUNWAY (`option_contract_liquidity.py:620-625`; 0.0001 passes). An adverse move gives THESIS_UNDER_PRESSURE → EXECUTABLE_NOW → THESIS_CONFIRMED (`morning_gate.py:2104`, `dynamic_validation.py:389`). 463 rows confirmed; 299 of them moved against the thesis, 125 by more than 0.5 ATR. | Not addressed |
| D12 | P2 | **CONFIRMED,** and wider: 54 ETF rows | `confluence_evidence.py:72` collapses `{ticker, sector_etf}`, so the difference is exactly 0. Then `>0`, else OPPOSES_OR_FLAT. The sector leg double-counts the ticker's own return. | Not addressed |
| D13 | P2 | **PARTIAL.** The 8.27 is confirmed; a ≥1.5 gate on it is not | `rr_options` has no verdict authority (EOD `MIN_RR=0.0`), and the 1.5 floors read `rr_underlying`. **But there is a leak:** `rr_underlying or rr or rr_options` (`eod_candidate_engine.py:1605`) falls through when rr_underlying is 0, giving XLU the full 20-point monetisation fit. `rr_options` also feeds contract quality (:1576) and the Lab composite (8%). On a reachable target, 132–159 of 177 PUT rows fall below 1.5; XLU drops to about 0.7. | Not addressed |
| D14 | P2 | **CONFIRMED,** root cause corrected | The source is known: a fresh MarketData chain from the completed 29 Sep session, all expiries 0–110 days. Its lineage and scope stop at the options CSV and the book. The desk whitelist passes bare levels, and `gamma_surface_source` is never written. Nothing separates per-ticker chain GEX from the market-level Money Index GEX (`SOURCE_NOT_PUBLISHED`). | Not addressed |
| D15 | P2 | **CONFIRMED;** display only | The block and unblock text is written by the model (`build_macro_json.py:592/632`). `normalise_horizon_routing` never validates thresholds or diffs them against the previous packet. The only consumer is `desk_card.py:516`, as display. No git change explains it. | Not addressed |
| D16 | P2 | **PARTIAL** | Confirmed: USMI is 31–49 hours old and still FRESH, because there is no USMI age check (`interpreter_macro_context.py:354-366`). Confirmed: credit is BENIGN at HY 3.08 under literal thresholds (`build_macro_json.py:1187`) while `hy_gate_breached=True`, and BENIGN is then mapped to "EASING". VIX: the headline is overridden to 16.34, so only the model text and `put_gate.current_vix` keep 16.04. That makes the packet inconsistent with itself, not stale. | Not addressed. `--macro-path` and "latest macro wins" rank by the core timestamp only. |
| D17 | P3 | **CONFIRMED** | There is no seasonality field. The figure came from web search (heygotrade), and it is a one-month return, not seasonality. | Not addressed |

**Summary:**
- 12 confirmed (5 wider than reported), 5 partial (D01, D05, D06, D13, D16) with corrected causes. None is a false positive.
- **No defect is eliminated by today's changes.**
- One is extended: D05's selection logic now also feeds the measurement-only candidate CSV.
- One would get worse: D10 is worse under `beh001_v1` if the direction source switches before D10 is fixed.

## New findings (not in the register)
1. **R7 reproducibility:** `morning_handoff_finalizer.py:851-855` re-materialises a stored run's interpreter macro context from live `dropbox/macro` (no `prefer_run_snapshot`). The 29 Sep book carries the 30 Sep macro while Morning carries 29 Sep's.
2. **IV labelling:** `iv_rank` 17.8 (RANGE_IV_HISTORY) against IVP 71.6% on the same row.
3. **Wyckoff phase bucket:** `wyckoff_phase_bucket=ACCUMULATION` comes from a fallback default for phase B (`avshunter_db_update.py:503-506`), whatever the structure.
4. **Contract and DTE display:** XLU `contract_dte` is 107 in options but 75 in the desk. `contract_expiry_bucket=11_20d` is on a 107-DTE contract.
5. **Target labelling:** the adapter stamps PRIOR_RANGE_EXTREME targets as "WYCKOFF", so they pass C5's WYCKOFF check (`direction_governance.py` ~503).
6. **Latent, checked and not live:** Options drops a target when `target_state` is anything other than NONE or LEVEL. Under rollback, Discovery writes it as `shadow_target_state`; under `beh001_v1` it writes only LEVEL or NONE; the book's `AVAILABLE` is written after Options.

## Implication for the direction switch
Do not switch `production_direction_source` to `beh001_v1` before D10 (the status ladder) and D01/D13 (target reachability) are fixed. Switching first removes the only conflict caution and swaps one uncapped target for another.

## Fix receipt: XLU-D01 and XLU-D13 (2 Oct 2026, ACK decision "No invented target")

**Supersedes:** the 25 Sep approved-fix item that kept the structural-target R:R. Under ACK's 2 Oct rule, a newer fix supersedes an older design.

**Changes** (uncommitted):
- **`scripts/avshunter_options_intelligence.py`:**
  - `_governed_structural_target` no longer invents a 3R target; it returns `NO_STRUCTURAL_TARGET`.
  - New `three_r_scenario` publishes the 3R level only as the labelled disclosure `target_3r_scenario` / `_state`.
  - New `reachable_target_fields` publishes `target_reachable` = spot × (1 ± k·σ·√(hold/252)). It uses the governed volatility budget, k = `contract_economics.sigma_multiple` (1.5) and hold = the governed thesis window, and also writes `target_reach_ratio`.
  - The strike filter uses the structural target, else the reachable one.
  - Economics: `rr_options` is the structural disclosure (empty when there is no structural target); the new `rr_options_reachable` is the scored R:R; `rr_basis` labels which is which. Breakeven and theta stay evaluated without a structural target.
- **`eod_candidate_engine.py`:** monetisation fit and contract quality read `rr_options_reachable` only. The `rr_underlying or rr or rr_options` fall-through has been removed.
- **`intelligence-lab/intelligence_lab.py`:** the composite reads `rr_options_reachable`.

**Tests:**
- New: `tests/test_avs_d01_d13_target_reachability.py` (9), seen red first.
- Five superseded characterisation tests updated, each with a note: fixspec rr direction, WP1 T6, geometry review, EOD contract quality fixture, Lab priority fixture.
- 59 Options/EOD/Lab/target test files re-run; the only failures were those five, now updated.

**Acceptance on stored run `20261001_211641`** (rules applied offline to the stored rows; Options not re-run):

| Target state | Rows | R:R ≥ 1.5 before → after | Median R:R before → after |
|---|---|---|---|
| Invented 3R | 868 | 319 → 103 | 0.66 → 0.61 |
| Discovery target | 302 | 73 → 26 | 0.55 → 0.46 |

- XLU: R:R 11.70 → 0.96; its invented target was 9.1× the reachable move.
- 74% of rows with an R:R used an invented target before this fix.

## Fix receipt: XLU-D10, Phase and Event categorise the trade (2 Oct 2026, ACK approved)

**Root cause:** the legacy Wyckoff engine (`WyckoffEngine_3101_v2.py` `_determine_execution_bias`) returns `OBSERVE_ONLY` whenever average phase/event evidence is below 35. That was 1,619 of 1,672 tickers on 1 Oct. The value then acted as a decision, while the EOD ladder labelled every row VALID_*.

**ACK, 2 Oct:** "there should not be a decision like observe. what is required is Phase and Event; those … should categorise a trade and what the human should see".

**Changes** (uncommitted):
- **New `domain/structure_behaviour/thesis_category.py`.** For each directed row, from the BEH-001 readings on the trade's own side (daily → weekly → monthly → intraday; activated before detected), it writes:
  - `thesis_phase`, `thesis_event`, `thesis_event_state`, `thesis_event_timeframe`, `thesis_event_scope`, `thesis_event_candidate_id`;
  - `thesis_structure_alignment`: ALIGNED, OPPOSING_ONLY, NO_EVENT or NOT_APPLICABLE;
  - `thesis_category`, e.g. "Phase E · SOW -> LPSY continuation (activated, 1d)".
- **Discovery** writes these fields on every row (`_thesis_category_fields`; never raises). The legacy value moves to `legacy_wyckoff_execution_bias`; `wyckoff_execution_bias` is BULLISH, BEARISH or NO_DIRECTIONAL_BIAS, never OBSERVE_ONLY.
- **EOD:** thesis states drop the validity claim (`VALID_THESIS_*` → `THESIS_*`), and the Phase/Event fields are carried in `DISC_MERGE_COLS`.
- **Pre-trade focus:** the `WYCKOFF_OBSERVE_ONLY` flag and the legacy-bias readiness condition are replaced by Phase/Event alignment. The flag is `NO_BEHAVIOURAL_EVENT_ON_TRADE_SIDE`; missing alignment counts as not aligned.
- **Scenario router:** no OBSERVE_ONLY path. The lowest path is CONSERVATIVE. The former intent-OBSERVE_ONLY return was unreachable dead code and has been removed; the fusion-absent MODERATE fallback is kept.
- **Lab book** (`FINAL_BOOK_FIELDS`, `STRUCTURE_DETAIL_FIELDS`) and **Interpreter** (`EVIDENCE_FIELDS`) carry the Phase/Event fields. The desk no longer receives `wyckoff_execution_bias` or the fallback `wyckoff_phase_bucket`, which also removes the D09 mislabel source.

**Tests:**
- New: `tests/test_avs_d10_phase_event_thesis.py` (9), seen red at collection.
- Updated: `tests/test_evening_thesis_decision.py` fixture and flag (17 pass).

**Acceptance on run `20261001_211641`** (applied offline):
- Of 1,395 directed rows, 1,221 are ALIGNED, 153 OPPOSING_ONLY and 21 NO_EVENT. The legacy bias agreed with direction on only 44 rows.
- Phases of aligned rows: E 513, D 379, B 202, C 101, A 26.
- XLU: "Phase B · no event on the PUT side; opposing Failed Upthrust Continuation (detected, 1mo)".
- Evening buckets on 1,554 book rows are **unchanged**. Earlier gates hold every row; none was `EOD_ACTION_SETUP_READY` before or after.

## Fix receipt: XLU-D13 completion, underlying R:R (2 Oct 2026, ACK "fix D13 rr_underlying")

**Changes** (uncommitted):
- **`scripts/avshunter_options_intelligence.py`:** new `rr_underlying_reachable(direction, entry, stop, reachable)`, the signed move to `target_reachable` over the signed risk to the stop. It is None when any input is missing or the stop is on the wrong side, and is published on every Options row.
- **`eod_candidate_engine.py`:** both structural-conviction scorers (:1818, :1932) read `rr_underlying_reachable`; the `rr_underlying or rr` fall-through has been removed. `VAN_MERGE_COLS` carries the reachable fields.
- **`scripts/avshunter_superbrain_layer.py`:** the R:R gates (< 0.5 cap; live < 1.5 cap) read `rr_underlying_reachable`.
- `rr_underlying` stays as structural disclosure.

**Tests:** `tests/test_avs_d13_rr_underlying_reachable.py` (5), seen red first. One expectation was corrected: the 0–1.0 band scores 3 points by design. EOD, WBS and D01/D13 files pass.

**Acceptance on run `20261001_211641`** (1,357 directed Options rows, applied offline):
- Before, 1,055 rows had no structural `rr_underlying`, so the R:R gates and points silently skipped them (missing treated as neutral). Now 1,207 rows have a reachable R:R.
- Gate cap (0 < R:R < 0.5): 47 → 75 rows. R:R ≥ 1.5: 194 → 859.
- XLU: none → 0.49 (now capped). QDEL: 7.35 structural → 3.28 reachable.

**D13 status: CLOSED.**

## Fix receipt: XLU-D11, Morning confirmation needs a material move (2 Oct 2026, ACK "fix D11")

**Root cause** (confirmed):
1. `classify_remaining_runway` gave GAP_CONFIRMATION_WITH_RUNWAY for any favourable move above 0.
2. `morning_gate` turned THESIS_UNDER_PRESSURE into EXECUTABLE_NOW.
3. `dynamic_validation` mapped both to THESIS_CONFIRMED.

**Changes** (uncommitted):
- **Config:** `config/governed_constants_v1.json` → `morning_runway.confirmation_min_expected_move_fraction` = 0.5. This is an engineering starting point, to be calibrated with the outcome scorer.
- **`domain/option_contract_liquidity.py`:**
  - A move confirms, or counts as pressure, only when |move| ≥ fraction × the one-session expected move.
  - Without a measurable expected move nothing confirms, and an adverse move stays flagged.
  - WAIT_FOR_PULLBACK still triggers on any favourable gap of at least one expected move.
  - New output fields: `move_is_material` and the fraction.
- **`morning_gate.py`:** THESIS_UNDER_PRESSURE keeps its own transition (flagged, not blocked).
- **`orchestrator/dynamic_validation.py`:** THESIS_UNDER_PRESSURE maps to PENDING_TRIGGER, never THESIS_CONFIRMED.
- **D01 consequence fixed (fail-closed risk):** both the Morning lifecycle and the Evening Options lifecycle required a structural target. Rows without one (no longer invented) would have become DATA_INCOMPLETE. Both now measure runway to `target_reachable` when there is no structural target; Morning records `runway_target_basis`. EOD publishes `target_reachable`, `rr_options_reachable` and `rr_underlying_reachable` to Morning.

**Tests:**
- New: `tests/test_avs_d11_morning_confirmation.py` (9). Eight were seen red; the Evening Options-lifecycle fallback test was written after the fix.
- Two lifecycle tests now pass the governed threshold explicitly.

**Acceptance on the stored 29 Sep Morning** (1,234 rows re-classified offline):
- GAP_CONFIRMATION_WITH_RUNWAY: 280 → 116. The 164 sub-material moves are now THESIS_ACTIVE.
- THESIS_UNDER_PRESSURE: 550 → 348 genuine adverse moves, with 202 immaterial ones becoming THESIS_ACTIVE. The 348 were previously labelled EXECUTABLE_NOW → THESIS_CONFIRMED; they are now flagged and validated as PENDING_TRIGGER.
- Invalidated, realised and pullback states are unchanged.
- XLU (PUT 39.71 → 39.51, 0.34 of an expected move) is now THESIS_ACTIVE, not a gap confirmation.

**D11 status: CLOSED.**

## Fix receipt: Interpreter batch, XLU-D06, D02, D07/D08, D12, D14 (2 Oct 2026, ACK "start")

**Shared root cause:** the narrative was not fed the governed facts, so the model inferred them or searched for them.

**Changes** (uncommitted):
- **New `pipeline_interpreter/governed_facts.py`** (pure functions):
  - `level_relations`: the side (spot above or below), signed distance and fixed reading for the gamma flip, call wall and put wall. Covers D07/D08.
  - `gamma_provenance`: chain dataset, provider, resolution, as-of and method, scoped as per-ticker chain GEX and explicitly not the market-level Money Index GEX. Covers D14.
  - `macro_rates`: the 10-year yield, context state and rates context from the governed Morning record or the row. Covers D02.
  - `unverified_rate_claims`: flags rate figures in the narrative that the governed facts don't hold. Covers D02.
- **`pipeline_interpreter/confluence_evidence.py`:**
  - D06: when Morning refreshed the exact contract, the contract link uses that quote. It is labelled `MORNING_QUOTE`, live-executable only when FRESH, with `days_to_expiry` taken from the OCC symbol. The end-of-day spread, delta and time stay beside it.
  - D12: `_ticker_link` gives `NOT_APPLICABLE_TICKER_IS_SECTOR_ETF` when the ticker is its own sector ETF. Statuses are now SUPPORTS, OPPOSES or FLAT; an exact zero is FLAT, no longer "opposes or flat".
- **`pipeline_interpreter/interactive_desk.py`:**
  - The Morning evidence now carries the live quote and macro fields.
  - The digest gains `level_relations`, `gamma_provenance` and `macro_rates`, and adds `MORNING_QUOTE` to the evidence references when used.
  - Every report (standard and deep) carries `governed_number_check`. This is an advisory flag, consistent with the rule that the Interpreter never gates.
- **`pipeline_interpreter/desk_provider_common.py`** (both report prompts): level sides come only from `level_relations`; gamma is per-ticker chain values; rates come only from `macro_rates`; web search never supplies a price, rate or level, and an absent figure is stated as such.

**Tests:**
- New: `tests/test_avs_interpreter_governed_facts.py` (9), written together with the module rather than seen red separately.
- All 38 Interpreter, desk and automation test files pass, including the desk end-to-end tests (28).

**Acceptance, using the XLU values from run `20260930_083504` in the tests:**
- Gamma flip 38.23: spot above (+3.34%).
- Call wall 40: spot below, so the wall is overhead resistance.
- Put wall 25: support below.
- The Morning contract quote is spread 6.25% of ask, delta −0.511, 15:32Z, FRESH, with days to expiry from the symbol.
- The 4.30% 10-year claim is flagged against the governed 5.26%.

**Status:**
- D06, D07, D08, D12 and D14: **closed**.
- D02: **closed for this path.** Rates are governed, prompt-bound and checked. Wider macro-packet integrity (D15/D16) remains open.

## Fix receipt: XLU-D03, sector alignment (2 Oct 2026, ACK "fix D03")

**Changes** (uncommitted):
- **New `domain/sector_resolution.py`, the single sector owner.** A placeholder sector (ETF, FUND, blank, …) resolves through the sector ETF via the versioned map `config/sector_etf_map_v1.json`. The Lab USMI projection (`contracts/lab_control.py`), the Interpreter macro context and the macro quant packet all use it. The quant packet also matches packet lists that name the ETF symbol, and the macro-context bias lookup is case-insensitive.
- **`contracts/us_money_index_contract._v2_sector_routing`:** a priority theme routes every sector category its words name (config `theme_tokens`). For example, `RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS` → UTILITIES, RATE_SENSITIVE_REITS, HOMEBUILDERS. Exact aliases are kept.
- **`macro_domain/us_money_index.py`:**
  - Utilities, Materials and Consumer Staples aliases added.
  - A resolved sector that the Index doesn't prioritise now reads `SECTOR_NOT_IN_USMI_PRIORITIES`; `SECTOR_UNMAPPED` is kept for an unresolved sector.

**Tests:** `tests/test_avs_d03_sector_routing.py` (7), seen red first. The macro-chain, handoff and macro test files pass.

**Acceptance on the 1 Oct book** (1,554 rows, current USMI packet, applied offline):
- Before: NEUTRAL/UNMAPPED on every row.
- After: 219 ALIGNED. Of these, 129 are selective industrial quality, 49 rate-sensitive utilities/REITs/homebuilders, and 41 fuel-sensitive consumer. The other 1,335 are neutral because the Index doesn't name their sector.
- Sectors resolve on all but 29 rows; 52 Utilities rows had been hidden behind "ETF".
- XLU: ALIGNED with the PUT priority `RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS`.

**D03 status: CLOSED.** Advisory only; macro never scores.

## Fix receipt: XLU-D04, compression trigger checks its options-cheap premise (2 Oct 2026; ACK chose "flag only")

**Changes** (uncommitted):
- **`trigger_layer._t1_vol_compression`:** realised compression is unchanged. The premise is checked on `ivp_label` (implied vol against the ticker's own history, owned by Options):
  - CHEAP or FAIR → `VOL_COMPRESSION`;
  - EXPENSIVE → `VOL_COMPRESSION_IV_RICH`;
  - missing → `VOL_COMPRESSION_IV_UNVERIFIED`.
- **ACK decision:** the IV variants keep weight 2.0 and stay GO-eligible (`trigger_layer` and `execution_decision_engine`); the label is the flag. IV/HV is deliberately not used, because it is mechanically high during realised compression.
- **Config:** `config/governed_constants_v1.json` → `trigger_vol_compression.options_cheap_labels`.

**Tests:** `tests/test_avs_d04_compression_iv.py` (5), seen red first. The trigger-layer governance, trigger-spine and evening-thesis files pass.

**Acceptance on run `20261001_211641`:**
- 546 compression fires: 349 verified, 138 IV-rich (XLU among them), 59 unverified.
- GO-eligible rows: 722 before, 722 after, unchanged per ACK.

**D04 status: CLOSED (flag).**
