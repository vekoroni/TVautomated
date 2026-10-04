# BEH-001 Phase 2 receipt: duration, 2A and 2B (1 Oct 2026)

**Design:** `Enhancements/decision_map/AVS_SD_BEH_001_PHASE2_CANDIDATE_HANDOFF_DESIGN_20261001.md`.

Nothing is committed. Production direction stays on `legacy_rollback`. 2C (candidate authority downstream, thesis identity, the C-01/C-02 survivor switch, the C6/C8 20-session caps) is **not built**; it awaits ACK approval.

## Built

| Item | Files | Tests |
|---|---|---|
| Duration (C-04, C-05, RQ-3) | `domain/structure_behaviour/duration.py`; engine wiring in `engine.analyse_ticker`; config `duration` section; evidence `config/beh001_duration_evidence_v1.json` (439 groups, 209 published, data to 2026-09-29, source sha256 recorded) from `Enhancements/direction_evidence/beh001_duration_evidence.py` | `tests/test_beh001_duration.py` (7). The six unit tests were written with the module, not seen red first; the engine integration test was seen red. |
| 2A candidate packet | `domain/structure_behaviour/handoff_packet.py`, `contracts/behavioural_candidate_packet.py`, `config/beh001_handoff_v1.json`. Evening wiring after the C5 freeze (never aborts). `status.json` is listed in the final run manifest (`contracts/lab_control.py`). | `tests/test_beh001_candidate_packet.py` (7), seen red first |
| 2B expression search per candidate | `scripts/options_candidate_lane.py`; `_run_candidate_expression_lane` in `scripts/avshunter_options_intelligence.py`, a separate pass after the per-ticker outputs are saved. Output: `options_candidate_expressions_{run}.csv`. | `tests/test_beh001_options_candidate_lane.py` (7), seen red first. It caught a rank-0 truthiness bug. |

## Behaviour of 2B (as designed)
- The chain is reused only where the existing per-ticker path already acquired it. This is a same-session canonical cache hit (CDS v2), so there is no new provider request.
- A ticker whose governed direction did not authorise a chain is recorded as `NOT_ROUTED:CHAIN_NOT_AUTHORISED_BY_GDR`, with the ticker's stand-down reason. This applies notably to tickers with live candidates on both sides (38% in replay), whose per-ticker direction resolves STRANGLE/UNRESOLVED. That existing constraint is now visible per candidate; lifting it needs 2C (GDR per candidate).
- Runway stays the existing Options policy (`runway_authority`); the candidate's duration travels beside it (C-06 is phase 3).
- Capacity: `expression.max_candidates_per_run` = 2000. Beyond it, a candidate is `DEFERRED_RESOURCE:<rank>`.
- Caveat: in the non-CDS rollback chain path, a repeat `fetch_chain` would be a second provider request. Production uses the CDS v2 resolver.

## Not yet proven on a real run
No production Evening has run with the BEH-001 Discovery wiring yet. The packet and lane will first appear on ACK's next Evening:
- `runs/{id}/forecast/behavioural_candidate_packet_v1/`
- `runs/{id}/options/options_candidate_expressions_{id}.csv`

## Regression
`regression_results.txt` in this folder: 125 files, one process per file.

**Result:** 1,018 passed, 1 skipped, and 4 failed in 2 files. Both match the 1 Oct baseline and are parked:
- `test_vanguard_reference_input_p2.py` (3): DCV-CLOCK.
- `test_macro_builder_governed_integration.py` (1): the live source is `SOURCE_NOT_PUBLISHED`.

The regression started before the timeframe-precedence change. On the final code I re-ran the Discovery-adjacent files, `test_beh001_conflict_resolution.py` (6/6) and all BEH-001 files; all pass.

## Two-sided resolution by timeframe precedence (ACK approved, 1 Oct 2026)

**Evidence:** `Enhancements/direction_evidence/beh001_two_sided_resolution.py`, with results in `Enhancements/outcomes/beh001/eval_v3/two_sided_resolution.json`. It used 8,375 two-sided ticker-days out of 22,253 scored. Outcome: the first ±2 ATR touch within 60 sessions, compared with same-day drift.

| Rule | Coverage | Excess vs drift (95%) |
|---|---|---|
| Higher timeframe one-sided | 59% | **+2.1 pt [+0.4, +3.8]**: positive in 2022-24 and 2024-26 and at ±1/2/3 ATR (+1.3 to +3.5) |
| Activated side | 32% | −0.3 [−2.1, +1.9] |
| Campaign over local | 9% | +0.4 [−3.5, +4.3] |
| Nearer trigger | 80% | −1.0 [−2.1, 0.0] |

**Built:** `handoff_thesis(readings, policy)` in `domain/structure_behaviour/engine.py`. A two-sided daily reading takes the side of the highest timeframe above daily whose live candidates are one-sided. The status is `RESOLVED_BY_TIMEFRAME:<tf>:<state>:<type>`, and the primary is the daily candidate on that side, so the invalidation stays daily. Otherwise the side stays `UNASSIGNED`, with reason `RANGE_EDGES_TWO_SIDED` or `CONFLICTING_DAILY_CANDIDATES`. Config: `beh001_behaviour_v1.json → handoff` (`NONE` disables it).

**Tests:** `tests/test_beh001_conflict_resolution.py` (6). Three were seen red; three pin unchanged behaviour.

**Replay coverage:**
- 19% of ticker-days with daily candidates are two-sided on the daily timeframe.
- Of those, 63% are resolved by timeframe, 2% are range edges, and 34% remain stated conflicts.

**Scope:** the rule changes only the shadow `thesis__side` while production direction is `legacy_rollback`. It is a weak tiebreak, in-sample, from four rules tested, and must be confirmed on forward runs.

## Pre-Evening readiness (1 Oct 2026, 21:00)

**Real-data smoke** (50 tickers, canonical bars, live intraday index, isolated temp ledger):
- 0.25 s per ticker, so Discovery adds about 15 minutes over the universe.
- The engine, ledger (two runs: FIRST_SEEN then UNCHANGED), packet and CSV all work.

**Defect found and fixed: candidate ID collision.**
- Two events of one type on one bar testing different levels shared an ID (AMRX 5m Upthrust, TAP 1d Failed Spring). The second was invisible to the ledger and dropped from the packet.
- Fix: colliding IDs gain `|L<trigger>`; unique IDs are unchanged. The ledger also marks any further same-run duplicate as `DUPLICATE_ID_IN_RUN`.
- Tests: `test_two_propositions_on_one_bar_get_distinct_ids` and `test_every_row_is_annotated_even_if_ids_collide`, both seen red. Known edge: a failure successor's parent link names the unsuffixed ID when its parent collided.

**`--plan-only` Evening:** exit 0. Last completed session 2026-10-01; stages Discovery, completed market profile, Vanguard, Options and publish thesis; requests ≤ 0 at plan time. No change to `data/`.

**Duration:** the evidence ends 2026-09-29, before tonight's as-of (2026-10-01), so estimates apply.

**No backfill was running:** the only Python processes were the Intelligence Lab.

## First production Evening (run 20261001_211641) and follow-up fixes (2 Oct 2026)

All new outputs published:
- Candidates: 20,853 on 1,898 tickers.
- Ledger: RECORDED.
- Packet: PUBLISHED, 13,233 records.
- Lane: 1,533 contracts found; 11,233 `DEFERRED_RESOURCE` (cap 2,000).
- Shadow side: 163 resolved by timeframe.
- Vanguard: `governance__*` columns present.

**Fixes, test-first:**
1. **43 exact duplicate candidates** (one event detected twice on one bar). `disambiguate_ids` now publishes one proposition once. Test: `test_exact_duplicate_propositions_are_emitted_once`.
2. **Ledger size: 90 MB after the first run** (2.35 KB per event).
   - The payload is now limited to the life-cycle fields (`PAYLOAD_FIELDS`), averaging 561 bytes on real data (−76%).
   - Test: `test_ledger_payload_keeps_lifecycle_fields_only`.
   - The existing first-run rows are append-only and stay as they are.
3. **Intraday freshness was only in Warning text.** The stale flag did fire (9,500 intraday candidates were `STALE_INTRADAY`: bars to 29 Sep, daily to 1 Oct). Every candidate now carries a `Data_Status` field: flagged, never gated.
   - Test: `test_intraday_data_status_is_a_field_on_every_candidate_not_only_warning_text`.
   - Real-data check: 112 of 112 IDs unique, and intraday `Data_Status` populated.

**Shadow comparison** (1,672 Discovery rows):

| | Shadow BEAR | Shadow BULL | Shadow UNASSIGNED |
|---|---|---|---|
| Production PUT (356) | 143 | 75 | 138 |
| Production CALL (1,039) | 495 | 251 | 293 |
| Production STRANGLE / UNRESOLVED (277) | 88 | 57 | 132 |

- Where both are directed (964), they agree on 41%.
- Agreement by shadow status: DETECTED 38%, ACTIVATED 35%, `RESOLVED_BY_TIMEFRAME` 62%.
- Options `final_direction` against the shadow side: 41% agreement (n=942).

**Reading:** production is 75% CALL. The shadow is 65% BEAR, which follows the data:
- 82% of Discovery tickers are down over 20 sessions (median −7.9%); IWM is −5.1% over 20 days.
- The daily controller is SELLERS on 408 tickers and BUYERS on 282. The weekly controller leans BUYERS (438 vs 236), which is daily markdown inside weekly up-structure.

This matches the documented legacy bull bias. Which side is right is **not yet measurable**: one session, and the replay showed no edge for either. Each night's disagreements are a forward test for C12 to score. This is not grounds to switch direction: the XLU audit's condition stands (fix D10, D01 and D13 first).

## Root cause of the shadow vs production disagreement (2 Oct 2026, run 20261001_211641)

Production `direction` comes from Precor intent (`legacy_discovery_direction_basis` = `precor_intent=…`).

| Legacy basis | Rows | Agreement with BEH-001 |
|---|---|---|
| BUY_SETUP | 673 | 26–38% |
| SELL_SETUP | 148 | 52% |
| TRANSITION + trend | 116 | 87–95% |

**Mechanism:**
1. **Spring rule** (`wyckoff_crabel_precor_logic_v2.py:470-490`): any low below the prior 20-bar low by `sweep_pct`, followed by a close back above it within `reclaim_within` bars, is a "Spring". It needs no trading range, acceptance or retention, so in a falling market every new low with a one-bar bounce qualifies.
2. A Spring primary event forces Phase C (:579).
3. Phase C with Spring + ACCUMULATION gives BUY_SETUP (:685).

**Sizing:**
- 899 of 977 raw BUY_SETUP rows are Phase C without buyer control, which is only reachable through the Spring rule.
- They account for 799 of 1,039 production CALLs and **455 of the 570 disagreements (80%)**.
- Spot check: QDEL, BWXT, SVM, OTEX and CENX (20-day returns −5% to −26%; BEH-001 daily SELLERS, mostly Phase E) all show Precor primary event "Spring" → BUY_SETUP.
- Secondary asymmetries: Phase E (ACCUMULATION gives BUY whatever the control; the fall-through default is BUY), Phase C (buyers alone give BUY, sellers need DISTRIBUTION), Phase D (the BUY test runs first), and `_reconcile_intent` rule 3 (46 SELL→BUY flips).

**By contrast:** a BEH-001 Spring needs an established trading range, a reclaim with acceptance, and retention, and it supersedes failed Springs.

**Not fixed** (root cause only, per ACK).

## Parked by ACK (2 Oct 2026): higher timeframe sets the side when daily has no directed candidate
- **Observation** after the switch to `beh001_v1`: rows whose daily reading has no live directed candidate are UNRESOLVED (`NO_DIRECTIONAL_CANDIDATE`; e.g. XLU, AAPL, NVDA on 1 Oct), even when weekly or monthly has one. About 563 of 1,672 rows were unresolved on 1 Oct.
- **Proposal:** extend timeframe precedence from conflicts to an empty daily reading.
- **To do when resumed:** measure it on the replay first, as for the conflict rule (`beh001_two_sided_resolution.py`).
- **Status:** parked until the database refresh is complete (ACK).

## Resumed 2 Oct 2026 after the database refresh: higher timeframe when the daily reading is empty (ACK "yes, start the higher timeframe test")

**Data:**
- Canonical bars run to 1 Oct 2026 (3,618 tickers).
- Stage A was regenerated with `beh001_eval_candidates.py --end 2026-10-01` (cuts every 10 sessions from Sep 2022).
- There are two panels:
  - the original 500 tickers (`eval_v4`);
  - a **holdout** of 500 tickers never used to design a rule (`--offset 500`, `eval_v4_holdout`).
- The pooled result is in `eval_v4_pooled`. No engine errors.

**Rule and criterion, fixed before results** (`Enhancements/direction_evidence/beh001_empty_daily_resolution.py`):
- The rule mirrors production precedence: walk 1mo then 1w; the first timeframe with live candidates decides if one-sided, and abstains if two-sided.
- Outcome: first touch of ±k daily ATR within 60 sessions, compared with same-cut drift, using a date-block bootstrap.
- Adopt only if the holdout excess at k=2 has a 95% lower bound above 0, and the point estimate is positive in both periods on both panels.

**Population:** 23% of ticker-cuts with candidates have an empty daily reading but higher-timeframe structure. The rule covers 83–84% of them.

| Excess vs drift, k=2 | Original | Holdout | Pooled |
|---|---|---|---|
| Empty daily → higher timeframe (new) | +1.6 pt [−0.1, +3.4] | **+0.0 [−1.6, +1.7]** | +0.8 [−0.6, +2.1] |
| Two-sided daily → higher timeframe (in production since 1 Oct) | +2.1 [+0.4, +3.7] | **+0.5 [−1.0, +2.0]** | +1.2 [+0.0, +2.5] |

- **Empty-daily rule: fails the criterion. Not built.**
  - Holdout +0.0. Holdout 2022–24 is negative (−2.6 [−4.9, −0.2]).
  - k=1 and k=3 are also inside noise on the holdout.
  - Those rows stay `NO_DIRECTIONAL_CANDIDATE`. Higher-timeframe structure remains displayed (Phase/Event on the card), not used for the side.
- **Conflict rule (production): does not replicate out of sample.**
  - On the original panel with refreshed bars it reproduces the 1 Oct estimate (+2.1).
  - On the holdout it is +0.5, not distinguishable from drift.
  - Pooled it is +1.2 pt, lower bound ≈ 0. The 1 Oct estimate was inflated by choosing the best of four rules on one panel.
  - Post hoc, not a rule: the pooled effect sits in same-timeframe conflicts (0.525 vs 0.501, n=5,921), with none in cross-timeframe ones (0.502 vs 0.505, n=4,609). Hypothesis for forward tracking only.
- **Decision for ACK:** keep the conflict rule (labelled `RESOLVED_BY_TIMEFRAME`, forward-tracked) or set `handoff.conflict_resolution` to `NONE` (config only; those rows become `CONFLICTING_DAILY_CANDIDATES`).

**ACK decision (3 Oct 2026): "switch it off".**
- **Config:** `config/beh001_behaviour_v1.json` sets `handoff.conflict_resolution` to `NONE`, with the evidence pointing to `eval_v4_holdout`. The mechanism stays in `handoff_thesis` and is re-enabled by configuration.
- **Test:** `test_production_policy_leaves_a_two_sided_daily_unassigned` was seen red, then green. The six mechanism tests now pass the rule's policy explicitly.
- **Regression:** 24 BEH-001, direction and structure-behaviour test files pass.
- **Effect from the next Evening:** a two-sided daily reading is `UNASSIGNED` (`CONFLICTING_DAILY_CANDIDATES` or `RANGE_EDGES_TWO_SIDED`), and its structure is shown on the card.
