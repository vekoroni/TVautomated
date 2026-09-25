# F1.b — The ledger cannot score the cohort pair: root cause and design

**Date:** 2026-09-25 · **Owners of the change:** `contracts/lab_control` (Lab extract, existing owner of the book's field set) and `canonical_data/decision_outcome_ledger` (existing owner of the decision record) · **Authority:** none; ledger is OBSERVATION_ONLY, additive fields only · **Requested by:** ACK ("carry on with F1.b")

## 1. Symptom

The cohort protocol (F1) needs, per decision record, the legacy contract and the shadow contract with their quotes, before the outcome is known. Today the ledger candidate event carries the legacy symbol and a quote snapshot id, and nothing about the shadow selector.

## 2. Root cause (confirmed)

| Fact | Evidence |
|---|---|
| The shadow selector's fields (`contract_value_*`) are written by Options Intelligence and are present, populated, in the options, superbrain, EIL and execution CSVs | 25 Sep run: `contract_value_basis` populated on 1,345 rows in each |
| They are blank in the Lab book and absent from the morning candidates and validated-trades files | Lab book: 1,549 × None; morning files: column absent |
| The Lab book is built by `_enrich_lab_extract_rows_from_run_sources`, which fills **only** the fields listed in `_lab_extract_field_aliases()`; the twelve `contract_value_*` fields are in `FINAL_BOOK_FIELDS` and in the projection, but not in the alias map | `lab_control.py:3944-4110` vs `:333-344` |
| The evening ledger candidate events are built from the Lab book rows; the morning events from the validated-trades rows | `intelligent_orchestrator.py:7218`; `morning_handoff_finalizer.py:398` |
| The candidate payload records no quote values, only `selected_quote_snapshot_id` | `decision_outcome_ledger.py:290-393` |

So the shadow evidence B1 now produces stops at the options CSV, and the ledger could not score a pair even if it did arrive.

## 3. Design (additive)

**Lab extract.** Add the twelve `contract_value_*` fields to `_lab_extract_field_aliases()` (each aliased to itself). The default source priority already reads `options_intelligence` after the morning files and the execution CSV, so the first non-missing value is found. Effect: the Lab book and every consumer that reads it, including the evening ledger events, carry the shadow selector's basis, quality, both symbols, value, alternatives and the forecast provenance.

**Ledger candidate event.** New payload block `selection_pair`, built from the row by a pure function `selection_pair_from_row(row)`:

```
legacy_contract_symbol        selected contract (score choice)
legacy_bid / legacy_ask / legacy_quote_timestamp_utc
legacy_quote_basis            MORNING_REQUOTE when execution_viability_bid/ask are present, else EVENING_CHAIN
shadow_contract_symbol        contract_value_best_symbol (None when the shadow valued nothing)
shadow_bid / shadow_ask / shadow_quote_timestamp_utc
shadow_quote_basis            EVENING_CHAIN_DERIVED_BID: ask and spread_pct from the alternatives entry,
                              bid = ask × (2 − s) / (2 + s), timestamp = the row's evening chain timestamp;
                              a morning requote of the shadow contract is not captured today (F1.c, capture)
shadow_basis / shadow_quality_flag / shadow_r_central
shadow_forecast_source / shadow_forecast_run_id / shadow_forecast_age_sessions
symbols_differ                bool, None when either symbol is absent
pair_state                    PAIR_RECORDED | SHADOW_UNAVAILABLE | LEGACY_QUOTE_MISSING
```

and `prospective_cohort = {"cohort_id", "registration", "variant_counter"}` from a module constant `PROSPECTIVE_COHORT` in the ledger module. Changing that constant is a cohort change by definition.

**Out of scope, recorded as F1.c.** The morning candidates file has a fixed schema; carrying the shadow fields into the morning rows, and requoting the shadow contract at the open, are capture changes. Until then the morning event holds the legacy requote and the evening event holds the pair; they join on `ticker` and `thesis_id`.

**Invariants.** Nothing is derived that was not measured, and every derived value says so (`EVENING_CHAIN_DERIVED_BID`). Unknown stays unknown (`SHADOW_UNAVAILABLE`, `None`). Every record is written before the outcome (spec §15).

## 4. Tests (written first)

`tests/test_f1b_ledger_selection_pair.py`:
- Characterisation: a row without any shadow field yields `pair_state = SHADOW_UNAVAILABLE`, legacy symbol recorded, and every pre-existing payload key unchanged.
- Evening row with shadow fields and alternatives → full pair, derived bid, `EVENING_CHAIN` legacy basis, `symbols_differ`.
- Morning row with `execution_viability_bid/ask` → `MORNING_REQUOTE` legacy basis.
- Shadow symbol equal to legacy → `symbols_differ = False`.
- `prospective_cohort` present with the registered cohort id.
- Lab alias map carries the twelve fields, and an extract from a fixture options CSV populates them in the row.

## 5. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `contracts/lab_control.py` +14: the twelve `contract_value_*` fields in the extract alias map. `canonical_data/decision_outcome_ledger.py` +86: `PROSPECTIVE_COHORT`, `selection_pair_from_row`, `selection_pair` and `prospective_cohort` on every candidate event |
| Tests written first | `tests/test_f1b_ledger_selection_pair.py`: 1 characterisation, 6 business rules; all pass |
| Regression | DDD decision outcome 20/20, stage-6 outcome learning 22/22, dynamic session phase 7 7/7, pretrade focus handoff 9/9, evening thesis decision 17/17, ILA golden 7/7, Lab ranking export 2/2, contract value selection 10/10; `--evening --plan-only` exit 0 |
| Preview on this morning's real run (in memory) | The extract now carries `contract_value_basis` (SCORE_FALLBACK_VALUE_UNAVAILABLE, as this morning's run predates B1). The pair from TSM's Lab row: `pair_state = SHADOW_UNAVAILABLE`, legacy `TSM261120P00450000`, `MORNING_REQUOTE` 21.45 / 21.85 at 13:42:52Z, cohort `COHORT_1_SHADOW_SELECTOR_20260925` |

## 6. Acceptance

Tonight's evening run: Lab book rows show `contract_value_basis` and, where B1 found a forecast, `contract_value_best_symbol`; the evening ledger events for that run carry `selection_pair` with `pair_state = PAIR_RECORDED` on those rows.
