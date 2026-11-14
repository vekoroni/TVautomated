# AVS-TRADE-001 · Design note v4: crossing scenario and expiry coverage for each contract

For ACK's approval. Builder: Claude Code (ACK, 14 Nov 2026). Reviewer: Codex.
Status (reconciled 14 Nov, after Codex's v4 review): **BUILT IN THE WORKING TREE, NOT COMMITTED, NOT RUN.** The text below from section 1 on is the design as written before the build and says "nothing is built"; the record in this box is the current state and takes precedence where they differ.

**Implementation record**

| Item | State |
|---|---|
| Approval | ACK, 14 Nov 2026, in the Claude Code session: "agreed, write the design note and i agree with all your recommendations" (section 15 recommendations), then "Yes, build v4 now" (build before Codex's fourth review, Codex to review code before commit). ACK then chose "Wait for Codex" on the commit |
| ETF handoff | The ETF identity work was validated and committed as `4010d4d` on ACK's instruction ("option 1, validate and commit the etf identity work"). The parked state in section 2 is superseded |
| Writing interval | After `4010d4d`, 14 Nov 2026, this Claude Code session only. No other writer is known to have touched the crossing files; that is a statement of what this session did, not a filesystem lock |
| Snapshot | Working tree on `laneb/lab-first-handoff` at `4010d4d` plus uncommitted changes. No commit, no push, no pipeline run, no provider call |
| Files as built | `domain\crossing_scenario.py` (new; the scenario, not inside `anticipated_move.py`), `domain\crossing_shadow.py` (new), `domain\quote_provenance.py` (new; not inside `option_contract_liquidity.py`, which must stay free of the data layer), `domain\option_valuation.py` (`net_return_on_premium_raw`), `domain\option_contract_liquidity.py` (`quote_tier`), `domain\anticipated_move.py` (wrapper with optional `crossing=` mapping), `scripts\avshunter_options_intelligence.py`, `eod_candidate_engine.py`, `morning_gate.py`, `contracts\lab_control.py`, `contracts\lab_review_projection.py`, `intelligence-lab\static\crossing-scenario.js` (new), `review-app.js`, `review.html`, `config\governed_constants_v1.json`, `data\scratch\workaround\build_lab_handoff.py`. Sections 8 and 14 name the earlier proposed locations |
| Codex v4 review, R3 | Built into `domain\quote_provenance.py` (`quote_provenance_v2`): Morning freshness is the existing effective age (raw age net of the disclosed feed delay) against the governed window, via `domain.long_option_execution`; the session clock is used for time validity and session only. Raw timestamp, raw age, delay, effective age, feed and policy versions are returned. The governed delay applies only to the governed feed; an unknown feed is PROVISIONAL. Morning also requires the spot to be the Morning's own CURRENT price (not a fallback) and the IV to be this contract's, same session. Evening: a quote after the assessment instant is PROVISIONAL even inside the close tolerance; each failure has its own reason. A saved assessment is reusable only with an equal binding (`saved_assessment_reusable`) |
| Where provenance is used today | Only in the Evening shadow comparison at the selection stage. The Morning run prices the crossing scenario but publishes no provenance label, so nothing in Morning is labelled ALIGNED. Wiring the Morning label is not built |
| Evidence | Tests only (see the code-review request). This is not run evidence and not acceptance |

Baseline read for the design: commit `23ad527` on `laneb/lab-first-handoff`, **plus uncommitted ETF identity edits by another Codex chat** (section 2), since committed as `4010d4d`.

**Revision record**

| Version | Reviewed | Outcome |
|---|---|---|
| v1 | Codex, `AVS-TRADE-001_codex_review_contract_from_clock_2026-11-14.md` | 7 findings, all accepted in v2 |
| v2 | Codex, `AVS-TRADE-001_codex_review_v2_contract_scenario_2026-11-14.md` | F1 and F3 resolved in design; F2, F4, F5, F6, F7 partly; six clarification groups and a file collision |
| v3 | Codex, `AVS-TRADE-001_codex_review_v3_contract_scenario_2026-11-14.md` | Most v2 points resolved in design; three required corrections (R1 to R3) and five clarifications |
| v4 | this note | Section 13 maps R1 to R3 and the five clarifications to their answers |

Changes in v4 (targeted, no redesign): a raw-return interface so thresholds are compared unrounded (section 9); the boundary actually searched is reported, with zero and negative windows handled (section 6); the real quote-provenance owner is named with its inputs (section 8); the sampling grid, state precedence, pool accounting, Lane B tolerance and benchmark inputs are specified (sections 5, 7, 8, 12).

Changes in v3 that still stand:

- **New field prefix `crossing_`.** v2's `scenario_state` and `scenario_basis` are already card fields with another meaning (`contracts\lab_control.py`). Publishing under them would have overwritten existing values.
- **The objective and the sort order now agree** (section 7).
- **One formula for Evening and Morning**, with explicit anchors and a timezone-aware clock (section 5).
- **One deadline convention** for search and coverage, and a state per pace, threshold and variant (section 6).
- **Existing value-selection outputs are not touched**; the scenario set is built separately (section 7).
- **Lane B's liquidity output changes in exactly one named case** (section 8).

## 1. What this delivers, and what it does not

**Delivers:** a display-only comparison, from saved data, of the session on which each exact contract would cross +20% and +30% under a stated path and two stresses; whether the contract lasts long enough for that; and a shadow alternative from a bounded, stated candidate set.

**Does not deliver:** the measured monetisation clock ACK defined on 12 Nov. That needs a replay of historical cases with non-hits, invalidation and censoring, and is a separate design (section 12). Nothing here is a forecast, a probability of profit or an empirical quantile.

**Operational boundary.** The selected contract, planned hold, rank, gates, verdicts, the existing value-selection outputs (`contract_value_*`) and Lane B's window flag do not change. **One documented correction** changes a Lane B liquidity output: a crossed quote is graded C with the reason `CROSSED_QUOTE` instead of being graded on a negative spread. No other Lane B output changes. No new field has any authority.

## 2. Precondition: the shared-file handoff

Another Codex chat ("Identify actuarial database gaps") has uncommitted ETF identity edits in five shared files. It confirmed on 14 Nov, through the review chat, that all five are **parked**: no further edits until ownership is coordinated. Nothing is committed and no commit is scheduled.

| File | ETF additions to preserve |
|---|---|
| `contracts\lab_control.py` | Identity-field import and export; disclosure attached after canonical ranking |
| `contracts\lab_review_projection.py` | Identity fields in the home and card publication |
| `intelligence-lab\static\review-app.js` | Identity disclosure renderer call |
| `intelligence-lab\static\review.html` | Identity script inclusion and cache version |
| `intelligence-lab\static\trade-card.js` | Instrument identity and research-policy display |

Dependencies to preserve: `canonical_data\instrument_identity.py`, `config\instrument_identity_v1.json`, `instrument-identity.js`, the inventory script, `tests\test_etf_identity_reliability.py` and its audit receipts.

A parked chat is not a lock, and the owner's last diff check was permission-blocked. **No build starts until:**

1. ACK confirms the handoff and names the interval in which I am the one writer in those files;
2. I re-read `git status` and the five files at that moment, and build around the identity lines; no file is reset or replaced whole;
3. I re-check `scripts\avshunter_options_intelligence.py`, `domain\option_valuation.py`, `domain\option_contract_liquidity.py` and `domain\anticipated_move.py` for other open edits before the first change.

If a file changes under me during the build, I stop and report.

**Separate from this design:** ACK decided on 14 Nov that the Evening run waits for the ETF identity work to be committed. That work is parked, not committed, and no commit is scheduled. The run is therefore waiting on a commit nobody is due to make; it needs ACK's instruction.

## 3. Decisions it rests on

| Decision | By | Date |
|---|---|---|
| Planned hold stays as the thesis runway | ACK | 12 Nov |
| Contract to be chosen from a monetisation clock; may be shorter than the hold | ACK | 12, 13 Nov |
| Selection by value stays in SHADOW | ACK | 18 Sep |
| 11 Nov liquidity tiers are the one standard | ACK | 14 Nov |
| Thin evidence stated; no invented figure | ACK | 14 Nov |
| Claude builds; Codex reviews | ACK | 14 Nov |

## 4. What the code already has

| Finding | Where | Consequence |
|---|---|---|
| Shadow value choice on one contract per expiry, with `contract_value_*` outputs | `apply_contract_value_selection`, `scripts\avshunter_options_intelligence.py:6011` | Same owner; **separate candidate set; legacy outputs untouched** |
| The contracts that reach that function have already passed selection's filters (side, holdable DTE, delta mandate, invalid quotes, positive mark, two-sided within the spread limit, strike level) | `select_best_contract`, `:5615-5722` | The scenario pool is the scored set, not the whole chain. Said so in the output |
| One pricer and one cost convention; with no bid the exit spread deducted is zero; no way to widen the exit spread | `domain\option_valuation.py:142`, `:178` | A backward-compatible spread-stress input is added there |
| `anticipated_move_fields` has no thesis origin, quote time or mode input, and several early returns | `domain\anticipated_move.py:79` | New optional inputs; explicit states at every early return |
| Morning passes today's contract date with the original arrival times | `morning_gate.py:1280` | The call is changed; listed in section 14 |
| The countdown owner counts completed sessions and needs a timezone-aware timestamp to avoid spending today's session | `remaining_hold`, `domain\trade_timing.py:65` | Reused, with a timestamp |
| Existing card fields `scenario_state`, `scenario_basis`, `scenario_exit_sessions`, `scenario_exit_date`, `scenario_iv_basis` and others | `contracts\lab_control.py` | **New fields use `crossing_`** |
| Lane B window flag acts on `monetisation_n_q50` | `build_lab_handoff.py:195` | Never published here, by name, alias, merge or default list |
| Lane B tier: `bid <= 0` is C `NO_BID`; a narrow-percent quote under 1.50 that is over 0.10 wide is B; a crossed quote is not rejected | `build_lab_handoff.py:172` | First two preserved exactly; third corrected |

## 5. The crossing scenario: one formula, explicit anchors

**Inputs**

| Input | Evening | Morning |
|---|---|---|
| Assessment instant `A` (timezone-aware) | The close of the evidence session | The Morning run's assessment time (its pricing start clock) |
| Quote timestamp | The saved Evening quote's own timestamp, recorded separately | The Morning quote's own timestamp, recorded separately |
| Quote spot `S` | Spot at the evidence close | Spot at the Morning quote |
| Entry cost | Saved Evening ask plus opening fee | Morning ask plus opening fee |
| Thesis identity | `thesis_id` and exact OCC symbol, carried on every result | The same `thesis_id`; the OCC may differ after a repair |
| Thesis origin `D0` (frozen) | The evidence session | The same `D0` from the Evening row; a repaired contract does not change it |
| Origin spot `S0` (frozen) | Spot at `D0` | The same |
| Target `L*` (frozen) | `anticipated_level_q50` | The same value; **not recomputed** |
| Arrival sessions `T` | q50 for median pace, q80 for slow pace | The same |
| Elapsed `e` | 0 | Completed sessions after `D0` up to `A`, from `remaining_hold` given `A` |
| Remaining pace `R = T - e` | `T` | Computed **separately for median and slow** |

`crossing_mode` is `EVENING_AT_EVIDENCE` or `MORNING_FRESH_ENTRY`. In both, the scenario answers: *what would a new entry at this quote need?* Managing an existing position against its entry cost stays with Lane B and the card. A date alone is never treated as a thesis identity.

**The sampling grid (session closes).** The scenario is sampled once per session, at the close.

- `grid_date(1)` is the first session close **strictly after `A`**.
  - Evening (`A` is the close of `D0`): `grid_date(1)` is the next session, `after_sessions(D0, 1)`.
  - Morning (`A` is before today's close on a session day): `grid_date(1)` is **today**, and `grid_date(j) = after_sessions(today, j - 1)`.
  - `A` at or after the close, or on a non-session day: `grid_date(j) = after_sessions(date(A), j)`.
- This matches `remaining_hold`, which does not count today's session as spent before its close. Worked example: thesis origin Monday, Morning quote Tuesday. `e = 0`, `R = T`, `grid_date(1)` is Tuesday's close, and `grid_date(T)` is the same calendar date as the Evening scenario's arrival. The two modes agree on the arrival date.
- `E` is the number of grid dates on or before the last XNYS session on or before the expiry date.
- Time left at j, for pricing, is the calendar days from `grid_date(j)` to expiry over 365, the existing convention.
- Published: `crossing_grid_first_date`, the arrival date for each pace, the expiry session, and the dates in section 6. The fixture asserts the actual date of j = 1, of j = R, of E and of U, before and after the close and across a holiday.

**The path**, for j = 1, 2, ...:

`level(j) = S + (L* - S) x min(1, sqrt(j / R))`

At each Morning this is a new conditional scenario from that quote, not a continuation of the Evening's curve. It stops at the target and never extrapolates past it. It never touches the invalidation level; invalidation is not modelled and the output says so. The path is an assumption: the evidence gives the arrival time, not the route.

**Search.** Section 6 defines the last session searched and which boundary set it. At each j the contract is priced once at `level(j)`; the **raw, unrounded** net return (section 9) is compared with both thresholds. The crossing is the first j at or above the threshold. An exact threshold crosses; a value just below it that would round up to it does not.

**Thresholds:** +20% and +30%, both, from one valuation per session. +30% is the nominated display default.

**Variants**

| Variant | IV | Exit spread deducted |
|---|---|---|
| `BASE` | Contract IV, flat | Half the quoted spread |
| `IV_DOWN` | Contract IV x the governed low IV stress (existing `iv_stress`) | Half the quoted spread |
| `WIDE_EXIT` | Flat | Half the quoted spread x the configured multiple |

`WIDE_EXIT` reuses the `BASE` model values. A stress may delay a crossing, remove it, or bring it earlier in early-exercise-sensitive cases. Whatever the pricer returns is reported; nothing is clamped.

**States: one per pace, threshold and variant (12 records per contract).** Evaluated in this order; the first that applies is the state.

| # | State | Applies when |
|---|---|---|
| 1 | `NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS` | A legacy caller passes no origin, assessment instant or mode |
| 2 | `NOT_ASSESSED_THESIS_STATUS_UNKNOWN` | Active status not supplied. Never assumed true |
| 3 | `THESIS_NOT_ACTIVE` | Thesis resolved or invalidated |
| 4 | `NOT_ASSESSED_NO_THESIS_ORIGIN` | Origin missing, unparseable or after `A`. Never replaced by today's date |
| 5 | `NOT_ASSESSED_NO_SPOT` | Quote spot missing, non-finite or not above zero |
| 6 | `NOT_ASSESSED_NO_LEVEL` | No frozen target |
| 7 | `TARGET_ON_WRONG_SIDE` | The frozen target was not on the trade's side of the **origin** spot `S0`: the thesis geometry itself is invalid |
| 8 | `TARGET_ALREADY_REACHED_AT_QUOTE` | The target was valid at origin and the quote spot is now at or beyond it in the trade's direction. This is a reached target, not a wrong side |
| 9 | `NOT_ASSESSED_NO_ARRIVAL_TIME` | No duration evidence for this pace |
| 10 | `PACE_EXHAUSTED` | `R <= 0` for this pace. The other pace is assessed on its own |
| 11 | `NOT_ASSESSED_NO_STRIKE_IV_OR_EXPIRY` | Contract input missing or non-finite |
| 12 | `NOT_ASSESSED_INVALID_QUOTE` | Ask or bid negative or non-finite, ask not above zero, or bid above ask |
| 13 | `NOT_ASSESSED_EXIT_COST_UNKNOWN` | Bid missing or zero |
| 14 | `NO_USABLE_WINDOW` | `U <= 0` (section 6). No search, no dates computed |
| 15 | `NOT_ASSESSED_PRICING_NUMERIC_FAILURE` | The pricer failed or returned a non-finite value at some j. The search stops; this is never a no-crossing result |
| 16 | `CROSSES_COVERING` / `CROSSES_NOT_COVERING` | A crossing was found (section 6) |
| 17 | `NO_CROSSING_BY_ARRIVAL` / `NO_CROSSING_BY_USABLE_DEADLINE` / `SEARCH_TRUNCATED_AT_CONFIG_CAP` | No crossing by the last session searched, named for the boundary that ended the search (section 6) |

**Crossing states and liquidity validity are two vocabularies for two uses.** For the crossing scenario a non-finite, negative or crossed quote is `NOT_ASSESSED_INVALID_QUOTE` and a zero or missing bid is `NOT_ASSESSED_EXIT_COST_UNKNOWN`. For the liquidity tier (section 8), kept compatible with Lane B, a missing or non-positive bid is `UNASSESSED_NO_BID` and only a crossed quote is `INVALID_CROSSED_QUOTE`. Both are published; neither is derived from the other.

No state is ever turned into a zero. No fallback fills a number.

## 6. One deadline convention, and the boundary actually searched

With `E` from section 5 and configured buffers (the existing 3 monitoring and 5 exit):

- **Usable deadline** `U = E - exit buffer`: the last grid session on which an exit can still be worked.
- A crossing at j **covers** when `j + monitoring buffer <= U`. A crossing with `U - monitoring buffer < j <= U` is `CROSSES_NOT_COVERING`.
- If `U <= 0` the state is `NO_USABLE_WINDOW`. Nothing is searched and no offset is passed to date arithmetic.

**Last session searched:** `J = min(R, U, cap)`. The cap is configured: proposed initial value 60 sessions, allowed range 20 to 120.

**The limiting boundary is recorded** in `crossing_search_limit`, with `crossing_search_end_session` and `_date`. On ties the precedence is arrival, then usable deadline, then cap.

| No crossing found, and | State | Meaning |
|---|---|---|
| `J = R` | `NO_CROSSING_BY_ARRIVAL` | Arrival was reached and the threshold was not |
| `J = U < R` | `NO_CROSSING_BY_USABLE_DEADLINE` | The contract's usable life ended before arrival. Arrival was **not** searched |
| `J = cap < min(R, U)` | `SEARCH_TRUNCATED_AT_CONFIG_CAP` | The search is incomplete. The contract is **not** shown to be incapable |

Fixtures: no hit with R=20, U=5, cap=30; R=20, U=30, cap=5; R=5, U=30, cap=30; each pair of tied boundaries; U=0; U<0.

**Headline coverage, `crossing_covers_slow30_base`, by a written rule:**

| Value | When the slow-pace +30% base record is |
|---|---|
| `YES` | `CROSSES_COVERING` |
| `NO` | `CROSSES_NOT_COVERING`, `NO_CROSSING_BY_ARRIVAL`, `NO_CROSSING_BY_USABLE_DEADLINE`, `NO_USABLE_WINDOW`: assessed, and it does not cover |
| `NOT_ASSESSED` | `SEARCH_TRUNCATED_AT_CONFIG_CAP`, `PACE_EXHAUSTED`, any `NOT_ASSESSED_*`, `THESIS_NOT_ACTIVE`, `TARGET_*`: incomplete or not applicable, not a failure |

Each of the 12 records carries its own state, crossing session and date, coverage, search end and limit.

Also published: `crossing_assessment_instant_utc`, `crossing_sessions_to_expiry`, `crossing_usable_deadline_session`, `_date`, and for the headline record `crossing_monitor_deadline_session`, `_date`.

The thesis runway checks (`anticipated_time_fit`, `expiry_session_check_state`) stay beside these, unchanged, and no existing hold or anticipated-value field is overwritten.

## 7. The shadow comparison

**Kept separate.** The legacy shortlist, `contract_value_best_symbol`, `contract_value_alternatives` and every other `contract_value_*` output are computed exactly as today. The scenario set is built beside them in the same function. A test compares those outputs before and after, field for field.

**Pool.** The scored contracts that `select_best_contract` hands over. `crossing_pool_basis = SCORED_CONTRACTS_AFTER_SELECTION_FILTERS`. The selector's behaviour is not changed. It records, additively, the contracts removed at each step, in the order it applies them, each count taken from the survivors of the step before so nothing is counted twice:

1. wrong side;
2. below the holdable DTE;
3. outside the delta mandate;
4. invalid or crossed quote;
5. no positive mark;
6. not two-sided;
7. spread over the limit. **When nothing is within the limit, the selector keeps the two-sided contracts above it for manual review**; that fallback is recorded as `SPREAD_ABOVE_LIMIT_FALLBACK`, with the count kept;
8. outside the preferred delta band. **This narrowing applies only when at least one contract is inside the band**; otherwise all are kept and marked best-available;
9. strike-level filter.

The counts reconcile to the chain received and are published with the result. They never imply the whole chain was assessed.

**Construction**

1. Expiries in ascending date order; take the nearest N that have at least one scored contract.
2. In each, the top M by existing score; ties by OCC symbol ascending. Fewer than M: take what exists.
3. In each, add the best-liquidity contract among those with a valid, non-provisional quote: best tier, then lowest spread as a share of mid, then higher open interest, then OCC symbol.
4. Add the selected contract.
5. Deduplicate by OCC symbol.

N and M are configured (proposed 4 and 3): at most 4 x (3 + 1) + 1 = 17 distinct contracts. Repeated requests are cached by exact contract, anchors, assumptions and config version.

**Objective.** *The earliest slow-pace +30% base crossing among contracts that cover it and are tradeable.*

**Eligibility** (all required): headline record is `CROSSES_COVERING`; quote valid; quote not provisional; tier A or B.

**Order among eligible:** earliest crossing session; then better tier; then lower entry cost; then nearer expiry; then OCC symbol. Tier is an eligibility test and a tie-break, not the first sort key, so a tier B contract crossing at session 2 is preferred to a tier A contract crossing at session 10.

**Blank, with a reason, never an implicit fallback**

| Case | `crossing_shadow_reason` |
|---|---|
| No candidate has a crossing | `NO_CROSSING_IN_SET` (or the common not-assessed state) |
| Crossings exist, none covers | `NO_COVERING_CANDIDATE` |
| Covering candidates exist, none tradeable | `NO_TRADEABLE_COVERING_CANDIDATE` |

Covering candidates that are tier C or provisional are listed separately as **research rows**, labelled, never as the shadow.

Result label `BEST_WITHIN_BOUNDED_SET_V1`, shown with the search cap. If any candidate's headline record is `SEARCH_TRUNCATED_AT_CONFIG_CAP`, `crossing_shadow_set_complete = NO`: an unsearched candidate could cross earlier than the shadow shown. Truncated and excluded candidates are never treated as proved incapable. `crossing_selection_mode` is fixed at SHADOW. `value_selection_mode` is not touched.

**Where it runs.** The full set is evaluated in the Evening only. Morning evaluates the selected contract only.

## 8. Liquidity: validity, provenance, tier

One pure function in `domain\option_contract_liquidity.py`, taking the caller's settings as today's Lane B function does, and applying the same `1e-9` tolerance at the spread and width boundaries. It returns validity, tier, reason, spread share and provenance.

**Validity**

| Condition | Validity | Lane B output (unchanged unless stated) |
|---|---|---|
| ask missing, non-finite or not above zero | `UNASSESSED_NO_ASK` | C, `NO_ASK` |
| bid missing, non-finite or not above zero | `UNASSESSED_NO_BID` | C, `NO_BID` |
| bid above ask | `INVALID_CROSSED_QUOTE` | **C, `CROSSED_QUOTE` (the one correction)** |
| open interest missing | `UNASSESSED_NO_OI` | C, `OI_NOT_RECORDED` |
| otherwise | `VALID` | tier below |

**Tier, on valid quotes, the 11 Nov rule in full**

- **C:** open interest under 100, or spread over 20% of mid.
- **B:** spread over 10% and up to 20%; **or** spread up to 10% but mid under 1.50 and width over 0.10.
- **A:** spread up to 10%, open interest at least 100, and (mid at least 1.50 or width up to 0.10).

**Provenance: the owner and its inputs.** v3 cited `classify_current_executability`. That was wrong: it takes a quote age and cannot establish which session a quote belongs to. The session-aware owner is **`canonical_data.session_clock.evaluate_freshness`** (`session_clock.py:197`). It takes the quote's aware timestamp, its dataset session, a domain and the evaluation instant, and returns EOD_CURRENT, FRESH, STALE, MISSING or INVALID. A small pure adapter, `quote_provenance(...)`, in `domain\option_contract_liquidity.py` calls it and the calendar owner. It adds no threshold of its own: the close tolerance and the live freshness limit are read from config.

Required per candidate: exact OCC symbol; quote timestamp (aware); the session that timestamp falls in; the source session of the spot and of the IV; the evidence session `D0`; the assessment instant `A`; the mode.

| Mode | `ALIGNED` requires all of | Otherwise |
|---|---|---|
| Evening | timestamp present and aware; `evaluate_freshness` (option-chain domain, now = `A`) is EOD_CURRENT; the quote's session is `D0`; the timestamp is within the configured tolerance of that session's close, early closes from the calendar; spot and IV are from `D0`; OCC matches | `PROVISIONAL` with the reason: `QUOTE_TIMESTAMP_UNKNOWN`, `QUOTE_SESSION_MISMATCH`, `QUOTE_NOT_NEAR_CLOSE`, `SPOT_OR_IV_SESSION_MISMATCH`, `IDENTITY_MISMATCH` |
| Morning | timestamp present and aware; `evaluate_freshness` (live domain, now = `A`, limit = the governed `option_quote_feed.freshness_max_seconds`) is FRESH; the quote's session is the session of `A`; OCC matches | `PROVISIONAL` with `QUOTE_STALE`, `QUOTE_SESSION_MISMATCH`, `QUOTE_TIMESTAMP_UNKNOWN`, `IDENTITY_MISMATCH` |

- The text `SESSION_ALIGNED` on a saved row, or the mere presence of a timestamp, is **not** accepted as proof.
- A quote is never restamped. An Evening quote that is not at the evidence close is provisional and labelled; the scenario is still computed and shown as provisional.
- The Morning quote's timestamp, the Morning assessment instant and the frozen thesis origin are three separate recorded values.
- Unknown alignment is provisional.
- Config: `evening_close_quote_tolerance_seconds`, proposed 1,800, the value the observed A12 clock already uses (`config\monetisation_clock_v1.json:8`). It is stated here so it is not an unstated threshold.

Fixtures: aligned close; early-close day; stale or different-session quote; unknown timestamp; fresh and stale Morning quotes.

`PROVISIONAL` travels on every candidate record and on the shadow result. A provisional quote is never described as tradeable.

**Names.** `contract_liquidity_confirmed` already exists on the book. To avoid a near-collision the new fields are `quote_tier_validity`, `quote_tier`, `quote_tier_reason`, `quote_tier_spread_share`, `quote_provenance`, `quote_provenance_reason`. No existing scalar or string is replaced by a richer object under the same name.

**Consumers.** Lane B's adapter keeps its present return shape, settings and tolerance. Before the change I list every reader of the tier (hand-off flags, triage check, packs) and pin each with a test. On the saved hand-off, tier outputs, window flags, order, batches, gates and verdicts must be identical, except rows with a crossed quote, of which the 12 Nov hand-off has none.

## 9. Cost interface

In `domain\option_valuation.py`, the existing owner:

- A new function **`net_return_on_premium_raw(model_value, *, bid, ask, exit_spread_multiple=1.0)`** returns the unrounded net return. It holds the one cost formula.
- The existing `return_on_premium` becomes that value rounded to four places, as it is today. Existing callers pass nothing new and get identical numbers; a test pins this on saved values.
- `exit_proceeds_usd_per_share` gains the optional `exit_spread_multiple`, default 1.0. It multiplies **only** the half-spread deduction. Entry ask, opening fee and closing fee are unchanged.
- The multiple is validated: finite and not negative. Config sets the value (proposed 2.0) and its allowed range (1.0 to 5.0).
- The crossing helper calls the raw function. No second cost formula exists in the crossing code. The bid is never altered to imitate a wider spread. Display fields round after the comparison.

Recorded on every result: pricing model and config version, the resolved rate and dividend values and their basis labels, and the source identity of the quote, spot and IV. A disclosed fallback is labelled an assumption, not market evidence.

## 10. Integration

**`scenario_crossing(...)`** is a pure function in `domain\anticipated_move.py`. It takes the inputs in section 5 and returns the 12 records plus the headline fields.

**`anticipated_move_fields`** gains optional inputs `thesis_id`, `thesis_origin_date`, `origin_spot`, `assessment_instant_utc`, `quote_timestamp_utc`, `crossing_mode`, `frozen_target_level`, `thesis_active`. It:

- initialises every `crossing_` field with `NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS` at the top, so a caller that passes nothing behaves exactly as today;
- sets the precise state at each existing early return;
- does not write to any existing field.

**Callers changed:** the options row build (`scripts\avshunter_options_intelligence.py`), `eod_candidate_engine.py:2890`, and `morning_gate.py:1280`. Morning passes the frozen origin and target from the Evening row, the quote's timezone-aware timestamp, and the mode, before the call instead of attaching the quote time after it.

**Candidates** in section 7 call `scenario_crossing` directly with the same frozen target, origin and paces as the row.

**Publication.** New fields are appended to the book and card lists in `contracts\lab_control.py` and `contracts\lab_review_projection.py`, after the identity fields already added there. The card section is its own renderer, `intelligence-lab\static\crossing-scenario.js`, with one call from `trade-card.js`.

## 11. Fields

| Field | Content |
|---|---|
| `crossing_n_median_pace_20`, `_30`, `crossing_n_slow_pace_20`, `_30` | Base variant sessions |
| `crossing_n_slow_pace_30_iv_down`, `_wide_exit` | Stress variants |
| `crossing_records_json` | All 12 records: pace, threshold, variant, state, session, coverage, deadline |
| `crossing_covers_slow30_base` | YES / NO / NOT_ASSESSED |
| `crossing_basis` (`SQRT_TIME_PATH_TO_FROZEN_TARGET_V1`), `crossing_authority` (`DISPLAY_ONLY_NOT_VALIDATED`), `crossing_mode` | Labels |
| `crossing_thesis_origin_date`, `crossing_assessment_instant_utc`, `crossing_elapsed_sessions`, `crossing_quote_timestamp_utc`, `crossing_contract_symbol` | Anchors |
| `crossing_rate_used`, `_rate_basis`, `_dividend_used`, `_dividend_basis`, `_iv_used`, `_model_version`, `_config_version` | Assumptions |
| Section 6 deadline fields | Offsets and dates |
| `quote_tier_validity`, `quote_tier`, `quote_tier_reason`, `quote_tier_spread_share`, `quote_provenance`, `quote_provenance_reason` | Section 8 |
| `crossing_search_limit`, `crossing_search_end_session`, `_date`, `crossing_search_cap`, `crossing_shadow_set_complete` | Sections 6 and 7 |
| `crossing_thesis_id`, `crossing_grid_first_date`, `crossing_quote_source`, `crossing_spot_source`, `crossing_iv_source` | Identity and sources |
| `crossing_shadow_symbol`, `_tier`, `_provenance`, `_n_slow_pace_30`, `_sessions_to_expiry`, `_entry_cost`, `_reason`, `_set` | Shadow comparison |
| `crossing_pool_basis`, `crossing_candidates_json` | Pool basis, upstream filter counts, candidates assessed and excluded with reasons, research rows |

Never published: `monetisation_n_q50`, `monetisation_n_q80`. The observed A12 fields keep their names and their own card section.

## 12. Tests, benchmark, acceptance

Every test is written and seen failing first.

**Path and valuation.** Path equals the formula; stops at the target. Unrounded comparison: a return that rounds up to the threshold but is below it does not cross. Slow pace never earlier than median on controlled fixtures. Each not-assessed state has a fixture and returns no number. Zero bid, zero ask, crossed, negative and non-finite quotes. Fees in stated units.

**Stress.** IV-down and wide-exit on controlled fixtures where the direction is known (no dividend, far from early exercise). A second fixture where lower IV raises an American value: the result is reported as computed.

**Deadlines.** Crossing covering, crossing not covering, no crossing by arrival, truncated by the cap; holiday, early close, expiry on a non-session day, one-session and zero-session boundaries.

**Morning.** Consecutive saved sessions across a holiday: `R` counts down from the frozen origin and never resets. A pre-close timestamp does not spend the day's session. Median pace exhausted with slow pace still assessed. Missing and future origin stay unassessed. A repaired contract keeps the thesis origin. Target already reached; wrong side; thesis not active.

**Candidate set.** Two strikes in one expiry where the lower-score strike crosses earlier and is tradeable: assessed and chosen. Tier B at session 2 against tier A at session 10: B chosen. All cross and none covers. Only tier C or provisional contracts cover. Fewer than M in an expiry. Duplicate OCC symbols. Counts reconcile to the pool and the recorded upstream filters.

**Liquidity.** The table in section 8, including the low-premium B case and exact boundaries; provisional carried through.

**No operational effect.** `contract_value_*` outputs, selected contract, score and planned hold identical on a saved options row. On a saved hand-off: window flags, order, batches, gates and verdicts identical; tier outputs identical except crossed quotes. Existing `scenario_*` fields and anticipated-value fields identical. Existing cost callers identical. Identity fields from the ETF work still present. Golden gains only the listed fields.

**Saved-data benchmark, before release.** No live run.

- **Workload:** saved run `20261111_231951`, replayed offline. Evening: its options rows (2,800). Morning: the **full** Morning candidate population of that run, not only the actionable rows.
- **Inputs fixed before the benchmark runs:** search cap 60 (range 20 to 120), N = 4, M = 3, exit-spread multiple 2.0, the governed IV stress. Recorded with the result: SHA-256 of each saved input file, source commit, config versions, machine.
- **The shadow set needs the saved candidate contracts and scores**, not only the selected rows. The first build task is to check whether `options\contracts_tested_20261111_231951.jsonl` and the saved canonical chain hold them. If they do not, that is reported to ACK as a benchmark-input gap. Candidates are never synthesised to fill it.
- **Recorded:** machine and configuration; distribution of rows by arrival sessions and sessions to expiry; valuation-call count; wall time and peak memory, **separately** for selected-contract publication and for the shadow set; the five longest-horizon rows.
- **Budget, proposed for ACK:** Morning selected-contract publication adds no more than 2 minutes. Evening adds no more than 20 minutes in total. The last Evening took about 11 hours.
- **If over budget:** N, M or the search cap are reduced by versioned config and the reduced scope is published. Long horizons and safety checks are never skipped silently; a shortened search carries `SEARCH_TRUNCATED_AT_CONFIG_CAP`.
- Worst-case arithmetic for scale: 17 contracts x up to the cap in sessions x 2 paces x 2 priced variants per row. One valuation serves both thresholds and the wide-exit variant.

**Run evidence (two-level closure), one normal Evening and Morning, after ACK's go-ahead:** fields on the card; rows by state per pace, threshold and variant; crossings beside arrival times by timeframe; coverage beside the unchanged hold check; shadow comparison counts for every reason; ten rows by hand including three ETFs; scenario against observed first-profit sessions only where entry anchor, cadence and deadline match, with unmatched pairs counted; run time against the benchmark.

**Still separate:** the measured clock by historical replay. First task: check whether `Enhancements\outcomes\beh001\` holds per-case paths.

## 13. Codex's v2 review, point by point

| Point | Answer | Section |
|---|---|---|
| F1 resolved; never populate `monetisation_n_*` by alias, merge or default list | Stated; test on the saved hand-off | 1, 11, 12 |
| F2: different anchors in sections 4 and 9 | One formula; anchors tabulated per mode | 5 |
| F2: decay after arrival not guaranteed | Search boundary declared; state `NO_CROSSING_BY_ARRIVAL` | 5 |
| F3: eligibility, dedup, ties, expiry and liquidity ordering; upstream filters | Construction steps 1 to 5; pool basis and upstream counts | 7 |
| F4: API lacks origin, identity, quote time, mode; early returns; Morning caller | New optional inputs; states at early returns; three callers changed | 10 |
| F4: partial-session counting; missing or future origin; independent pace exhaustion | Timezone-aware timestamp to `remaining_hold`; unassessed states; per-pace `R` | 5 |
| F4: target reached, wrong side, resolved thesis; do not overwrite hold fields | Three states; no existing field written | 5, 10 |
| F5: zero bid or ask, non-finite, provisional, per-variant states | Validity table; 12 records | 5, 8 |
| F5: exit-spread multiplier in the shared cost owner | `exit_spread_multiple`, default 1.0; file listed | 9, 14 |
| F6: objective against tier-first order | Tier is eligibility and tie-break; earliest crossing first | 7 |
| F6: search and coverage buffers differ | One convention: `U`, then monitoring | 6 |
| F6: which pace, threshold, variant coverage describes | `crossing_covers_slow30_base`; every record has its own | 6 |
| F7: zero-bid policy, low-premium B, provisional eligibility | Tables | 8 |
| F7: adapter change can alter downstream handling | One named correction; consumers listed and pinned | 1, 8 |
| Keep legacy value outputs unchanged | Separate set; before-and-after test | 7, 12 |
| Existing `scenario_*` names | Prefix `crossing_` | 4, 11 |
| Projection and card owner | `crossing-scenario.js` | 10 |
| Run-time budget definition | Saved workload, measures, limits, reduction rule | 12 |
| IV-down not monotonic for American pricing | Controlled fixtures plus a reported counterexample | 12 |
| File collision | Precondition | 2 |

### Codex's v3 review

| Point | Answer | Section |
|---|---|---|
| R1: unrounded return interface | `net_return_on_premium_raw`; the existing function is its rounded wrapper; multiplier validated and bounded | 9 |
| R2: report the boundary searched; zero and negative windows | `crossing_search_limit`, three no-crossing states, `NO_USABLE_WINDOW`, written headline rule, six fixtures | 6 |
| R3: real quote-provenance owner and inputs | `canonical_data.session_clock.evaluate_freshness` through a pure adapter; per-mode rules; no restamping; the v3 citation withdrawn | 8 |
| C1: Morning offsets and dates | Sampling grid at session closes; worked example; dated fixture | 5 |
| C2: pool description | Sequential accounting including the core-delta narrowing and the above-limit fallback | 7 |
| C3: state precedence; quote-state naming; missing spot, strike, status; pricing failure | Ordered state table; two vocabularies explained | 5 |
| C4: Lane B settings and tolerance; name collisions | Adapter keeps settings and `1e-9`; fields renamed `quote_tier_*` | 8 |
| C5: benchmark inputs and reproducibility | Cap and bounds fixed first; hashes and versions; full Morning population; candidate-input check | 12 |
| Thesis identity kept with the result | `crossing_thesis_id` with OCC, quote time and frozen target | 5, 11 |
| Renderer loading and export wiring | Script inclusion in `review.html` after the identity script, with the cache version raised | 10, 14 |
| ETF handoff | Parked status recorded; precondition unchanged | 2 |

## 14. Files

| File | Change |
|---|---|
| `domain\anticipated_move.py` | `scenario_crossing`; optional inputs and states in `anticipated_move_fields` |
| `domain\option_valuation.py` | `net_return_on_premium_raw`; optional `exit_spread_multiple` |
| `domain\option_contract_liquidity.py` | Validity and tier function; `quote_provenance` adapter over `canonical_data.session_clock.evaluate_freshness` |
| `scripts\avshunter_options_intelligence.py` | Upstream filter counts; scenario set, shadow comparison; caller inputs; new fields |
| `eod_candidate_engine.py`, `morning_gate.py` | Caller inputs |
| `config\governed_constants_v1.json` | `contract_crossing_scenario`, `option_liquidity_tiers` |
| `contracts\lab_control.py`, `contracts\lab_review_projection.py` | Field lists, after the identity fields |
| `intelligence-lab\static\crossing-scenario.js` (new), `trade-card.js`, `review.html` | Card section; script inclusion after the identity script; cache version |
| `data\scratch\workaround\build_lab_handoff.py` | Tier via the shared function; crossed-quote correction; window flag untouched |

## 15. For ACK to decide (all proposed, none approved)

| # | Decision | Proposed |
|---|---|---|
| 1 | The path assumption | Approve as a labelled scenario |
| 2 | Objective | Earliest slow-pace +30% crossing among covering, tradeable (tier A or B, not provisional) contracts |
| 3 | Candidate set | 4 expiries x 3 by score, plus best-liquidity per expiry and the selected contract |
| 4 | Buffers | Existing 3 monitoring and 5 exit sessions, in config |
| 5 | Stress sizes and search cap | Existing governed low IV stress; exit spread x 2 (range 1 to 5); cap 60 sessions (range 20 to 120) |
| 6 | Run-time budget | Morning +2 minutes; Evening +20 minutes |
| 7 | Lane B correction | Crossed quote graded C, `CROSSED_QUOTE`; nothing else changes |
| 8 | Operational adoption | Not now |
| 9 | Handoff | The five ETF files are parked; ACK confirms the handoff and names my writing interval |
| 10 | Next design note | The measured clock by historical replay |
