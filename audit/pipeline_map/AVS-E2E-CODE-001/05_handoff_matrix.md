# 05 — Handoff matrix

**Document:** AVS-E2E-CODE-001 · Step 3
**Evidence run:** `data/output/runs/20260831_010309/`

Row and ticker counts are **MEASURED**. Join keys are **OBSERVED** from the consuming code. The reconciliation column tests the AVS-E2E-DATA-LOGIC-001 sect 14.5 invariant `input unique tickers = passed + rejected + deferred`.

## Per-artefact census

| Stage artefact | Rows | Unique tickers | Duplicates | Ticker column |
|---|---:|---:|---:|---|
| `discovery/discovery_candidates_ultimate_20260831_010309.csv` (Discovery) | 1,527 | 1,527 | 0 | `ticker` |
| `vanguard/vanguard_signals.csv` (Vanguard) | 1,481 | 1,481 | 0 | `ticker` |
| `options/vanguard_signals_enriched_20260831_010309.csv` (Vanguard enriched) | 1,481 | 1,481 | 0 | `ticker` |
| `options/options_intelligence_20260831_010309.csv` (Options Intelligence) | 1,248 | 1,248 | 0 | `ticker` |
| `options/options_intelligence_phantom_20260831_010309.csv` (Options (phantom)) | 1,248 | 1,248 | 0 | `ticker` |
| `horizon/horizon_1_5d_20260831_010309.csv` (Horizon 1_5d) | 655 | 655 | 0 | `ticker` |
| `horizon/horizon_6_10d_20260831_010309.csv` (Horizon 6_10d) | 284 | 284 | 0 | `ticker` |
| `horizon/horizon_11_20d_20260831_010309.csv` (Horizon 11_20d) | 0 | 0 | 0 | `ticker` |
| `horizon/horizon_blocked_20260831_010309.csv` (Horizon blocked) | 17 | 17 | 0 | `ticker` |
| `superbrain/superbrain_enriched_20260831_010309.csv` (SuperBrain enriched) | 1,248 | 1,248 | 0 | `ticker` |
| `superbrain/wall_break_scores_20260831_010309.csv` (Wall Break) | 31 | 31 | 0 | `ticker` |
| `superbrain/eil_enriched_20260831_010309.csv` (EIL enriched) | 1,248 | 1,248 | 0 | `ticker` |
| `execution/execution_v3_5_20260831_010309.csv` (Execution v3.5) | 1,248 | 1,248 | 0 | `ticker` |
| `qomega/garch_forecasts_20260831_010309.csv` (GARCH) | 1,248 | 1,248 | 0 | `ticker` |
| `morning_validation/morning_candidates_20260831_010309.csv` (EOD candidates) | 201 | 201 | 0 | `ticker` |
| `morning_validation/morning_blocked_review_20260831_010309.csv` (Morning blocked review) | 736 | 736 | 0 | `ticker` |
| `intelligence_lab/final_opportunity_book_20260831_010309.csv` (Final book (CSV)) | 201 | 201 | 0 | `ticker` |
| `options/options_blocked_review.csv` (Options blocked review) | 311 | 311 | 0 | `ticker` |
| `options/contract_rejection_log_20260831_010309.csv` (Contract rejection log) | 1,102 | 1,102 | 0 | `ticker` |

## Stage boundaries and reconciliation

### Discovery → Vanguard

- rows in **1,527** → rows out **1,481** (delta -46)
- tickers dropped: **46**; tickers appearing that were not upstream: **0**

### Vanguard → Options Intelligence

- rows in **1,481** → rows out **1,248** (delta -233)
- tickers dropped: **233**; tickers appearing that were not upstream: **0**

### Options Intelligence → SuperBrain enriched

- rows in **1,248** → rows out **1,248** (delta +0)
- tickers dropped: **0**; tickers appearing that were not upstream: **0**

### SuperBrain enriched → EIL enriched

- rows in **1,248** → rows out **1,248** (delta +0)
- tickers dropped: **0**; tickers appearing that were not upstream: **0**

### EIL enriched → Execution v3.5

- rows in **1,248** → rows out **1,248** (delta +0)
- tickers dropped: **0**; tickers appearing that were not upstream: **0**

### Execution v3.5 → EOD candidates

- rows in **1,248** → rows out **201** (delta -1,047)
- tickers dropped: **1,047**; tickers appearing that were not upstream: **0**

### EOD candidates → Final book (CSV)

- rows in **201** → rows out **201** (delta +0)
- tickers dropped: **0**; tickers appearing that were not upstream: **0**

### Options Intelligence → Wall Break

- rows in **1,248** → rows out **31** (delta -1,217)
- tickers dropped: **1,217**; tickers appearing that were not upstream: **0**

### Options Intelligence → Horizon Router (sect 14.5 test)

- input rows **1,248**, input unique tickers **1,248**
- routed 1_5d **655** + 6_10d **284** + 11_20d **0** + blocked **17** = **956**
- **unaccounted rows: 292**
- tickers present in Options but in no horizon file: **292**

**Reconciliation: FAILS** (GAP-003).
