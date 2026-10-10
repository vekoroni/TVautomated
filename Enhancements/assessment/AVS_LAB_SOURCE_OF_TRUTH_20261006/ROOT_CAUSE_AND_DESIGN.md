# Intelligence Lab source of truth: root cause and design

**Status:** proposed, awaiting ACK approval. No code has been changed.
**Date:** 6 Oct 2026. **Run examined:** `20261006_060401` (Evening and Morning).
**Trigger (ACK):**
- "HL as not monetisable and ev at -0.266 make it difficult to identify the trade"
- "move window at 1_5D but the hold is 8 sessions"
- "we need a source of truth without conflicting data"
- "when a decision has been made only the important data should be carried downstream"

Governing rules: spec R1 (missing is never neutral), R2 (one owner per fact), R6 (labels say what was measured), R11 (rank, don't gate). Memory rules: repair, don't delete; newer fixes supersede.

---

## 1. What the trader sees (evidence)

HL is rank 1 in the Lab and a GO. Its card answers "does it pay?" four ways:

| Surface | HL value | Model | Status of that model |
|---|---|---|---|
| Card, "Does the move pay" | PAYS 1.32× at q50 (level 15.95, about 2 sessions) | Anticipated move (time value included) | **Approved owner** (ACK, 3–4 Oct: replaces R:R) |
| Grid "EV*", Trade Setup | −0.266 at 5 sessions, P(target) 0.31 | EV3 | Authority retired (CLAUDE.md rule 5). This row was also REJECT_LIQUIDITY (0 volume at the Evening close), and its 5-session grid cannot represent a 2-session move (BELOW_EV3_GRID_2) |
| Grid "Monetisable", Trade Setup | NOT_MONETISABLE, −61.6% at target 16.34 | Expiry-intrinsic floor v2 | Advisory. Ignores time value. Its target comes from the **legacy** `target_spot`/`target_price`/`structural_target` fields, which the card already retires (`TC_LEGACY`) |
| Rank | 1 (score 99.5) | `_compute_priority_score` | Weighted verdict labels plus **`rr_options` (R:R retired by ACK)**, EIL, options score, WBS and GARCH. Uses no value |

HL's target appears as four different prices: 16.34 (legacy target, used by monetisability), 15.69 (structural), 15.95 (anticipated q50) and 14.89 (reachable). The move window appears as "1-5D" (from `horizon_bucket`), while the planned hold is 8 sessions (evidence runway).

**Across the 51 GOs:**
- On 33, the anticipated move says PAYS while monetisability says NOT_MONETISABLE.
- EV3 is negative on all 26 it scored. The other 25 were not scored (REJECTED).
- On 33, the monetisability target differs from the anticipated structural level by more than 1%.
- Lab rank vs anticipated-value rank: Spearman **−0.02**, i.e. no relationship. COHR, the best value at 2.27×, ranks 9th.
- 6 GOs have no anticipated value at all (`NOT_COMPUTED`): BIRK, CYTK, BLDR, UNP, ENOV, CENX.
- 1 GO (NET) is valued only on volatility (`NOT_ASSESSED_VOLATILITY_ONLY`).

**Lab payload:**
- The book carries **814 columns** per row, and the Morning trades file over 1,280.
- The book JSON is 252 MB for 1,636 rows, partly because `source_payload_json` and `field_provenance_json` repeat the row inside the row.
- `/api/run/latest` takes **210 s** to load and sends 300 MB to the browser.
- The Morning handoff (gate to Lab) took 29 min, mostly writing these files.

**Display inventory** (subagent sweep of `intelligence-lab/static/`):
- The ticker view has 11 tabs, about 45 sections and about 280 labelled fields.
- About 20 surfaces answer VALUE, about 15 answer TIME, about 14 answer TARGET, about 25 answer VERDICT, and 7 answer RANK.
- Spread is computed four ways: ask-based on the card, mid-based in the summary, plus `contract_spread_pct` and `mv__spread_pct`.
- "Position Size" labels two different fields.
- The Trade Setup tab still shows the legacy "Structural Target" and "+% on premium" that the card retires.

## 2. Root cause

**RC1. No single owner per fact; superseded models were added beside the new one, not replaced.**
Each round added a better answer (anticipated move → value; evidence runway → time; structural or anticipated level → target). But the older answers kept their fields, their places on the display and their downstream consumers:
- EV3 → grid and modal;
- monetisability → grid and modal;
- `horizon_bucket` → "Move Window";
- `target_price` → monetisability and Trade Setup.

Nothing marks which answer governs. R2 is broken on value, time, target, verdict and rank.

**RC2. The handoff carries everything forward instead of the decision.**
- Every stage merges all its columns into the next (`eod__`, `exe__`, `vg__`, `opt__`, `mv__`, `wbs__` prefixes, plus JSON copies of the whole row).
- When the Morning gate decides, there is no narrow decision record. The Lab receives the union of every stage's fields and has to choose among them with fallback chains: `getTimeHorizon` tries 6 prefixed `horizon_bucket` fields, then layer-2 and macro horizons, then `hold_label`, then DTE.
- This is ACK's point: once a decision is made, only the important data should travel.
- It is also the direct cause of the 252 MB book, the 3.5-minute Lab load and most of the 29-minute handoff.

**RC3. The rank was never moved to the new value.**
- `intelligence_lab.py:_finalise_lab_priority_ranking` sorts by verdict bucket, then by `_compute_priority_score`.
- That score is built from verdict labels and the retired R:R (`rr_options`), and its header still lists R:R.
- So rank 1 is the "most agreed-upon label set", not the best trade.

**RC4. The GO rule treats a missing value as neutral (R1).**
- `morning_gate.py:2889` withholds GO only for `DOES_NOT_PAY_AT_ANTICIPATED_TIME`; its comment says "NOT_COMPUTED does not block on its own".
- So a row with no value, or a volatility-only value, can be a GO, and its card has no answer to "does it pay?".

## 3. Design

### D1. One owner per fact, with the alternates named

| Question | Owner (shown) | Demoted to the audit view (still computed, labelled, not deleted) |
|---|---|---|
| Which side | `direction` (governed) | discovery/footprint/catalyst directions |
| Which setup, which lane | `trade_lane`, `trade_lane_setup`, lane hit rates | WBS grade, convexity dots, campaign, MS life/dir |
| Where am I wrong | `invalidation_spot` (governed) | `invalidation_price`, `structural_invalidation`, forecast invalidation |
| Where am I right | `anticipated_level_q50`, plus `anticipated_structural_level` as the structural reference | `target_spot`/`target_price`/`structural_target` (legacy), forecast target, GEX walls as context |
| How long | `anticipated_sessions_q50` / `q80`, plus `planned_hold_sessions` with its basis | `horizon_bucket` ("Move Window"), Q-OMEGA 1-5/6-10/11-20d, time stop, maturation, days to trigger |
| Does it pay | `anticipated_value_multiple_q50` / `q80`, `anticipated_pays_state`, earnings stress | EV3 (both holds), monetisability (expiry intrinsic), C8, research EV, DOI probabilities, composite/options/MVS scores |
| What contract, what cost | symbol, strike, expiry, **dte (calendar) and contract_dte (sessions)**, bid/ask, **spread = (ask−bid)/mid** (one formula), quote time | other spread variants |
| Earnings | `earnings_date`, confirmation, inside hold, inside contract | catalyst engine detail |
| What do I do | **one verdict:** Morning gate verdict, plus its reason, plus post-open contract state (EXECUTABLE NOW / GAP CONFIRMATION / …) | campaign, action category, EOD status, routes, EIL verdict, Q-OMEGA gate, TCE, interpreter |
| Can I trust it | quote freshness, bar as-of, evidence status (e.g. IN_SAMPLE_REPLAY_NOT_VALIDATED) | provenance JSON |

The audit view keeps everything that exists today, so it repairs rather than deletes. It is labelled "Other models: not used for this decision", and each row carries the reason, e.g. "EV3: authority retired; this row REJECT_LIQUIDITY" or "Monetisability: intrinsic at expiry, legacy target".

### D2. The decision record is the handoff

- At the Morning gate, write one narrow, versioned record per ticker: `trade_decision_record_v1`, with about 60 fields, exactly the owners in D1 plus identity (`run_id`, `ticker`, `candidate_id`, `contract_symbol`).
- Every field comes from its owner only. There are no fallback chains: a missing owner field is shown as missing, with its reason (R1).
- Each record holds pointers to the full stage artifacts (paths and row keys) for the audit view.
- The Lab's default payload is the decision records: a few MB instead of 252 MB.
- The full-width book is still written for audit and C12, but the trader view no longer reads it. Its slimming (dropping the duplicate JSON payloads) is measured as a separate step.

### D3. Rank by value (rank, don't gate)

- Within the verdict bucket, rank by `anticipated_value_multiple_q50`, highest first.
- Rows with no value go last and are labelled VALUE_NOT_COMPUTED.
- The old `_compute_priority_score` stays as a research field in the audit view. It is removed from the rank and its R:R input is noted.
- The trade summary already sorts this way, so grid and summary will agree.

### D4. Missing value is not a GO (R1)

- In the Morning gate, `NOT_COMPUTED` and `NOT_ASSESSED_VOLATILITY_ONLY` become **FLAG**, with reasons VALUE_NOT_COMPUTED and VALUE_VOLATILITY_ONLY. Today they can be GO.
- The row stays visible for human review.
- This changes gate behaviour, so it needs ACK approval and a characterisation test of the current behaviour first.

### D5. Lab tidy-up

**Default ticker view = the trade card**, built only from the decision record, in its 8 existing sections (what/side, why now, wrong/right, how long, contract/cost, pays, context, decision, trust). One value per question.

**Grid columns become:**
- Rank, Ticker, Side, Lane, Setup
- Verdict (one), Contract state
- Option, Value (q50), Median time, Hold
- DTE (cal · sess), Spread (mid), Earnings, Quote age

These columns are removed from the default grid: Move Window, EV*, Monetisable, Campaign, Action, Conv, IVP, Vol State, WBS, MV, AM Drift, Entry Telemetry, MS Life, MS Dir and Assess. They move to the audit view.

**The other 10 tabs become one "Audit" tab.** It loads only when opened, from a per-ticker endpoint that reads the stage artifacts. The existing tab code is reused inside it, grouped by stage, with the "not used for this decision" banner.

**KPI tiles count from the decision record:** GO and executable now, GO awaiting gap confirmation, FLAG and BLOCK. The duplicate client and server armed counts are removed.

**Old runs:** the Lab opens on the latest Morning-validated run. Older runs stay selectable but are labelled with their session date. Rows from the Evening book before the Morning handoff show "awaiting Morning validation" instead of 0 executable (the confusion at 16:00 today).

### D6. Target reconciliation (before the card relies on one level)

Characterise on today's 51 GOs:
- why the legacy `target_price` (used by monetisability) differs from `anticipated_structural_level` on 33 of them;
- why many lane-A tickers on 1w/1mo setups are valued on the 1d thesis event (`thesis_event_timeframe` = 1d; e.g. RARE, HWM, FISV).

If the anticipated move values the wrong setup, that is a value defect, and it is fixed test-first before D3 ranks on that value.

## 4. Build sequence (test-first, one defect at a time)

| Step | What | Test that fails first | Acceptance |
|---|---|---|---|
| S0 | Characterise: pin HL, COHR, NET, BIRK cards and the current rank, GO rule and payload size | characterisation tests | baseline recorded |
| S1 | D6 target/timeframe reconciliation (findings first; fix only if a defect is approved) | "value is computed on the setup that qualified the lane" | 0 unexplained target mismatches on run 20261006 |
| S2 | D4 GO rule | "a row with no computed value is never GO" | the 6 + 1 rows become FLAG on replay; no other verdict changes |
| S3 | D2 decision record writer at the Morning gate | "each record field has exactly one owner and no fallback"; "a missing owner is stated, not filled" | record for all 1,636 rows; size < 10 MB |
| S4 | D3 rank | "rank within bucket follows the value multiple; missing value ranks last" | grid and summary order agree |
| S5 | D5 Lab default view from records; Audit tab lazy-loaded | "card shows one value, one time, one target, one verdict"; "audit lists alternates with reasons" | Lab first load < 10 s (now 210 s); HL card has no conflicting value |
| S6 | Handoff timing: log each handoff step, then slim the full book | timing receipt | handoff time measured; reduction reported |

**Measurement:** C12 keeps scoring every model (EV3, monetisability and the anticipated move), so the demoted models can be compared on outcomes later. Demoting a model from display never stops it being measured.

## 5. Decisions for ACK

1. **Value owner = anticipated move.** EV3, monetisability and the old scores are shown only in the audit view. Confirm.
2. **D4:** a row with no computed value, or only a volatility value, is FLAG, not GO. This changes gate behaviour; approve or reject.
3. **D3:** rank by anticipated value within the verdict. The old priority score becomes a research field. Confirm.
4. **D5:** the default Lab shows only the decision record; all other tabs move into one lazy-loaded Audit tab. Confirm.
5. **Governance:** the CLAUDE.md waiver of 4 Oct covered the Discovery/hold round only. Does this round run under CLAUDE.md as normal (failing business-rule tests, outcome-scorer acceptance), or under a new waiver?
