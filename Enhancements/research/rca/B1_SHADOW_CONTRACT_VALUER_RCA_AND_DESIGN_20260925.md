# B1 — Shadow contract valuer returns VALUE_INPUTS_UNAVAILABLE on every row: root cause and design

**Date:** 2026-09-25 · **Owner of the change:** Options Intelligence (`scripts/avshunter_options_intelligence.py`), existing owner of contract selection · **Authority:** SHADOW_NO_AUTHORITY unchanged · **Requested by:** ACK ("start with the fixes", step 1 of the accepted sequence: repair B1 in shadow, current routing preserved)

## 1. Symptom

The value-based contract selection approved by ACK on 18 Sep 2026 (`long_option_contract_selection.value_selection_mode = SHADOW`, measure `emp_path_r_central`) has produced no evidence since it was switched on. On the 25 Sep evening run, 1,332 of 1,332 rows with a contract carry `contract_value_basis = SCORE_FALLBACK_VALUE_UNAVAILABLE` and `contract_value_quality_flag = VALUE_INPUTS_UNAVAILABLE`. The same is true of the 24 Sep book.

## 2. Root cause (confirmed)

`_default_contract_valuer(ctx)` builds its inputs with `empirical_option_ev.path_inputs_from_options_row(ctx['_signal_row'], ...)` and returns `None` (every candidate flagged) when `forecast_vol` is `None`. The forecast it wants is `l3_forward_realised_vol_raw` (or `l3_forward_realised_vol`).

That field does not exist on any row at contract-selection time:

| Fact | Evidence |
|---|---|
| `ctx['_signal_row']` is the Vanguard enriched signal row | `avshunter_options_intelligence.py:4812` |
| The Vanguard enriched CSV has **no** `l3_*` or `garch*` column (1,017 columns) | `vanguard_signals_enriched_20260925_061649.csv` |
| The Layer 3 forecast is produced by `garch_runner.py` in **Phase 10a**, after Options Intelligence, and merged into `superbrain_enriched` in Phase 10b | `intelligent_orchestrator.py:4495-4560`; `garch_runner.py` docstring |
| Mapping every Vanguard row through `path_inputs_from_options_row` gives `forecast_vol = None` on 1,609 of 1,609 | run in session, 25 Sep |
| The unit tests inject `_signal_row = {"l3_forward_realised_vol_raw": 0.35}` and therefore never exercised the production path | `tests/test_contract_value_selection.py:44` |

Secondary: `invalidation` and `target` are also missing on 429 and 402 Vanguard rows respectively, but those are the geometry defects of fix item A1 and are correctly flagged by the valuer today.

So this is an ordering defect in the data flow, not a bug in the valuer: the valuer's input is produced by a later phase.

## 3. Options considered

| Option | Change | Freshness | Risk | Verdict |
|---|---|---|---|---|
| (a) Compute the GARCH forecast inline in Options Intelligence per ticker | New GARCH fit per ticker inside OI; bars from the canonical price DB | Same session | Adds minutes of compute to OI and a second owner of the forecast (duplicates Phase 10a) | Rejected: one owner per fact |
| (b) Reorder the orchestrator so Phase 10a runs before OI | Orchestrator phase order; `garch_runner` reads OI's IV for the tailwind score, so it must be split | Same session | Structural change to the run; tailwind circularity | Rejected for now; correct long-term shape, not a step-1 fix |
| (c) Read the most recent Layer 3 forecast already on disk for the ticker, flagged with its source and age | One lookup in `_default_contract_valuer`; two additive output fields | Morning run: the evening's forecast for the same close (point-in-time correct). Evening run: the previous session's forecast (one session old, flagged) | Minimal; no API calls; no ordering change; shadow only | **Chosen** |
| (d) Move the shadow valuation to a post-Phase-10b pass | New pass; sidecar must carry per-candidate bid/ask/IV | Same session | New owner outside OI; larger change | Rejected for step 1 |

## 4. Design of (c)

`_l3_forecast_on_disk(ticker)` in Options Intelligence:

1. Candidate files, newest first: the active run's own `qomega/garch_forecasts_<run>.csv` (present in a morning run because the evening wrote it), then earlier run folders' files under `data/output/runs/*/qomega/`.
2. First file containing the ticker with `l3_forecast_state` starting `FORECAST_OK` and a positive `l3_forward_realised_vol_raw` wins. A clipped forecast is never used for value (ACK 17 Sep 2026), consistent with `path_inputs_from_options_row`.
3. Returns the raw forecast plus `source_run_id` and `age_sessions` (0 when the source is the active run, otherwise the count of XNYS sessions between the source run's session and the active session; when the calendar is unavailable, calendar days are recorded and labelled as such).
4. Result cached per run so 1,500 tickers cost one file read per run folder touched.

`_default_contract_valuer(ctx)`: when `inputs["forecast_vol"]` is `None`, call the lookup; if it returns a forecast, use it and set `forecast_source = "L3_ON_DISK"`. Nothing else in the valuer changes. When the lookup finds nothing, behaviour is exactly today's (`VALUE_INPUTS_UNAVAILABLE`).

`apply_contract_value_selection` output gains two additive fields on every row: `contract_value_forecast_source` (`SIGNAL_ROW_L3`, `L3_ON_DISK`, or `UNAVAILABLE`) and `contract_value_forecast_age_sessions` (integer, or empty). Both are projected to the Lab book through the existing `CONTRACT_VALUE_FIELDS` list.

**Invariants respected.** Fresh-or-flagged (R12): the age is recorded on the row. One owner per fact: the forecast is still Layer 3's number, read, not recomputed. Authority: `value_selection_mode` stays SHADOW; the selected contract is unchanged on every row. Unknown means unknown: no default forecast.

## 5. Tests (written before the change)

`tests/test_b1_shadow_valuer_forecast_source.py`:

- **Characterisation** (pins today): a production-shaped signal row with no `l3_*` field and no forecast file on disk → every candidate `VALUE_INPUTS_UNAVAILABLE`, basis `SCORE_FALLBACK_VALUE_UNAVAILABLE`, `contract_value_forecast_source = UNAVAILABLE`.
- **Business rule** (fails until the change): the same row with a `garch_forecasts_<run>.csv` on disk for the ticker → the shortlist is valued, basis `SCORE_VALUE_SHADOW`, `contract_value_forecast_source = L3_ON_DISK`, age recorded, and the selected contract is still the score choice.
- **Clipped forecast is refused**: a file whose state is `CLIPPED_AT_CAP` → unavailable.
- **Newest file wins**: two run folders, the newer one's forecast is used and age is 0 when it is the active run.

## 6. Acceptance

Tonight's evening run: `contract_value_quality_flag = OK` and a populated `contract_value_best_symbol` on the rows whose ticker had a forecast in the prior run's file, with `contract_value_forecast_source = L3_ON_DISK` and age 1. Selected contracts identical to what the score choice would have been (SHADOW). The morning run then uses the evening's own forecast at age 0. The register's B1 acceptance ("the shadow produces evidence") is met when `contract_value_best_symbol != contract_value_score_choice_symbol` on some rows and both are recorded with quotes.

## 7. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `scripts/avshunter_options_intelligence.py` +98 lines: `_l3_forecast_file`, `_run_session_date`, `_l3_forecast_on_disk`, fallback in `_default_contract_valuer`, three additive fields in `CONTRACT_VALUE_FIELDS` and the selection output. `contracts/lab_control.py` +4 lines: the three fields in `FINAL_BOOK_FIELDS` and the Lab projection. `tests/test_ila_selected_contract_identity.py`: the three fields added to the golden's additive list, as the 24 Sep fix did |
| Tests written first | `tests/test_b1_shadow_valuer_forecast_source.py`: 1 characterisation (passed before and after), 7 business rules (failed before, pass after), including the Friday-to-Saturday age case |
| Regression | value selection 10/10, horizon-not-a-gate 28/28, rejection taxonomy 24/24, ILA golden 7/7, tradeability 13/13, DTE policy 9/9, options research contract 11/11; `intelligent_orchestrator.py --evening --plan-only` clean |
| Age correction found in dry run | Run-id dates are local dates, one day after the US session; across Friday-to-Saturday they undercount by a session. `run_meta.json` `session_date` is now the authority, `_CDS_V2_SESSION` for the active run, run-id date only as a fallback |
| Dry run against real folders | Tonight's evening run will find this morning's forecast for TSM (0.3711), MRVL, FANG, IBIT with `source_run_id = 20260925_061649`, age 1; this morning's run would have used it at age 0 |
| Authority | `value_selection_mode` still SHADOW; the selected contract is unchanged on every row |

## 8. Rollback

Revert the single commit; the valuer returns to today's behaviour. No data written outside the run folder.
