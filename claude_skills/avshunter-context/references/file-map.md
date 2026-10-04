# File map (verified by direct listing, 21 Sep 2026)

Repo root: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`

## Rebuild layer (spec-governed, newer)

- `avshunter/` — the package CLAUDE.md says owns measurement (C12 outcome
  scoring), configuration and run context.
  - `avshunter/c0_run/` — C0 Run Context.
  - `avshunter/c12_outcome/` — C12 Outcome: `signal_ledger.py`, `service.py`
    (large, 40KB — main service logic), `hypotheses.py`, `base_rate.py`,
    `estimators.py`, `conditions.py`, `expression.py`, `passage.py`,
    `records.py`, `geometry.py`, `model.py`, `signal_service.py`,
    `signals.py`, plus an `adapters/` subfolder.
  - `avshunter/config/`, `avshunter/shared/`.
- `contracts/` — rebuild-layer contract/domain modules (see
  entities-and-schemas.md for the file list).
- `domain/` — separate domain package (older DDD attempt; check overlap
  with `avshunter/` and `contracts/` before assuming ownership of a fact).
- `Enhancements/` — governing spec, method notes, decision maps, and
  per-topic audit folders (`assessment/`, `backtest/`, `data_freshness/`,
  `decision_map/`, `direction_evidence/`, `expression_forensics/`,
  `forensic_mapping/`, `gex/`, `iv_history/`, `knowledge/`, `outcomes/`,
  `phase0/`, `research/`, `signal_accuracy/`, `structural_edge/`).
  `Enhancements/knowledge/` holds the governing spec + method notes 01–07 +
  `REPLICATION_PLAN.md` + `README.md`.
  `Enhancements/AVSHUNTER_END_TO_END_REPORT_20260919.md` is the latest
  full end-to-end report (19 Sep 2026) — read this for current build state
  before assuming anything from an older memory of the project.

## Legacy layer (still what runs live)

- Root-level numbered/named engine `.py` files — `intelligent_orchestrator.py`
  (399KB, the orchestrator), `morning_gate.py`, `morning_handoff_finalizer.py`,
  `execution_intelligence_runner.py`, `execution_gate.py`,
  `eod_candidate_engine.py`, `avshunter_discovery_ULTIMATE.py`,
  `garch_runner.py`, `layer3_forward_variance.py`, `layer4_mispricing.py`,
  `layer6_path_survival.py`, `empirical_option_ev.py`, `kelly_sizer.py`,
  `position_sizing_engine.py` (retired-on-path per earlier audit — verify),
  `trade_book_builder.py`, `final_decision_engine.py`,
  `execution_decision_engine.py`, `build_macro_json.py`,
  `bond_macro_intelligence.py`, `handoff_contract_audit.py`, and many more —
  full listing is long; use targeted search rather than reading the whole
  root.
- `enums_structural.py`, `execution_schema.py` — canonical enums / EIL
  schema, both read directly and summarised in entities-and-schemas.md.
- `desk_card.py`, `CLAUDE_CODE_TASK_lab_qa_audit.md`, `LAB_QA_REPORT.md` —
  older QA/desk-card work; check dates before treating as current.

## Data

- `data/output/` — per-run CSV/JSON output (see entities-and-schemas.md for
  the file naming pattern); `data/output/runs/`, `run_contexts/`,
  `run_plans/`, `outcomes/`, `qa/`, `state/`.
- `data/daily/`, `data/daily_history_v7/`, `data/phantom/`,
  `data/vanguard/`, `data/vanguard_output/`, `data/worker3/`,
  `data/universe/`, `data/canonical/`, `data/cache/`, `data/journal/`,
  `data/macro/`, `data/probe_output/`, `data/scratch/`, `data/archive/`,
  `data/audit/`, `data/logs/`.
- `data/actuarial_db.sqlite` — currently 0 bytes at last check; confirm
  before assuming it's populated.

## Dropbox (macro / manual pre-pipeline inputs and coaching outputs)

- `dropbox/macro/` — `macro_intelligence_latest.json`, `bond_macro_state.json`,
  `avshunter_us_money_index.json`, `avshunter_macro_enrichment_delta.json`,
  `avshunter_us_economic_event_payload_*.json`,
  `macro_input_manifest_latest.json`, `auction_calendar.csv`,
  `bonds_etf_*.csv`, plus `Archive/`, `coaching/`, `thesis/` subfolders.
- `dropbox/market_data/` — GEX proxy output (not re-verified this pass;
  confirmed to exist in earlier sessions).
- `dropbox/inputs/` — catalyst CSV intake (Catalyst Truth engine), per
  earlier sessions; not re-verified this pass.

## Tests

- `tests/`, `tests_rebuild/` (isolated rebuild-package tests — never touch
  live `data/` or network, per CLAUDE.md), `test_pipeline_regression.py`,
  `test_macro_redesign.py`.

## Do not confuse these with the live repo

- `_attic/`, `_cleanup_holding/`, `_quarantine/`, `decommissioned/`,
  `legacy/`, `backups/` — retired/quarantined code, not the live pipeline.
- `venv/`, `.codex_python313_runtime/`, `.codex_test_runtime/`,
  `.testdeps/`, numerous `pip-*` scratch directories — build/runtime
  artefacts, ignore.

## Where to write analysis/tooling output (per governance-and-gates.md)

Never into `avshunter/`, `contracts/`, `domain/`, `orchestrator/`, or a
numbered root engine file. Use `dropbox/macro/coaching/` (the established
location for Desk Gate, rank engine, and coaching-board output) or another
clearly-separate new folder, and say explicitly where you wrote it.
