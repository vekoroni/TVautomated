# Entities and schemas

Two layers exist in this repo: the **legacy engine** (root-level `.py` files,
pre-DDD, still what actually runs live) and the **new spec-governed rebuild**
(`avshunter/` package, `contracts/`, `domain/`). Don't conflate them —
`CLAUDE.md` rule 4 says the legacy pipeline is an asset mine, not a design
reference, and the `avshunter/` package is the one that owns C12 outcome
scoring today.

## Core entities (spec vocabulary — use these terms, not ad hoc ones)

- **Run** — one evening or morning pipeline execution. Carries `run_id`,
  `decision_clock`, `market_session`, `evidence_session` (last completed
  session used as evidence), `data_as_of`, `environment`,
  `pipeline_version`, `release_id`, `clean_tree`, `configuration_version`.
  A `"latest"` file (e.g. `data/output/latest.json`) is a convenience
  pointer only — never treat it as an authoritative decision input.
- **Candidate geometry** — a target/invalidation shape proposed by Market
  Structure (C3) for a ticker; a ticker can have more than one live
  geometry at once.
- **Evidence packet** — per-geometry historical first-passage
  probabilities/timing (C4), built only from point-in-time, cleaned,
  split/dividend-adjusted returns.
- **Thesis** — the aggregate root (C5): direction, target, invalidation,
  trade window, window clock, selected geometry, evidence reference. Once
  published, immutable (Invariant C) — a real change produces a *new
  thesis version*, never a mutation.
- **Expression** — one tradeable way to express a thesis (a specific
  contract, vertical, or shares) — C6's `CandidateExpressionSet`.
- **Expression valuation** — C8's per-expression EV, RAEV (EV per $ at
  risk, lower-bound), time-normalised return. Sole authority for trade
  economics; EV3/EV v2 are explicitly non-authoritative.
- **Opportunity book** — C9's ranked output; RAEV descending is the
  ranking key, time-normalised return is the first tie-break.
- **Decision record / ledger record** — C11: what was decided and what
  was *not*, logged before the outcome is known. Every context from C2
  onward writes to it as produced, not just at the end.
- **Outcome** (`UnderlyingOutcome`, `ExpressionOutcome`) — C12, produced by
  `avshunter/c12_outcome/` (`signal_ledger.py`, `service.py`,
  `hypotheses.py`, `base_rate.py`, `estimators.py`, `conditions.py`,
  `expression.py`, `passage.py`, `records.py`, `geometry.py`, `model.py`).
  This is the engine a fix must move before it's "accepted" per the
  working rules.

## Canonical enums (legacy layer) — `enums_structural.py`

Import from here; do not redefine these strings anywhere else (this file's
own docstring calls out enum drift as a historical cause of silent
control-check failures).

- `ControlState`: `BUYERS` / `SELLERS` / `EQUILIBRIUM` / `SHIFTING` /
  `UNKNOWN` (legacy aliases like `BUYERS_IN_CONTROL` normalise to these).
- `Direction`: `LONG` / `SHORT` / `NONE`.
- `Intent`: `BUY_SETUP` / `SELL_SETUP` / `TRANSITION` / `OBSERVE_ONLY` /
  `WAIT`; `GO_INTENTS = {BUY_SETUP, SELL_SETUP}`.
- `CrabelState`: `COILING` / `READY` (canonical; `CRABEL_READY` is a legacy
  alias) / `NONE`.
- `WyckoffPhase`: `A`–`E` / `UNKNOWN`; `RANGE_PHASES = {A,B,C}`,
  `TREND_PHASES = {D,E}`.
- `Operator`: `ACCUMULATION` / `DISTRIBUTION` / `MARKUP` / `MARKDOWN` /
  `UNCLEAR`; `LONG_OPERATORS = {ACCUMULATION, MARKUP}`,
  `SHORT_OPERATORS = {DISTRIBUTION, MARKDOWN}`.

## Execution Intelligence Layer (EIL) schema — `execution_schema.py` (v3.0.0)

EIL is advisory-only (`eil_advisory_only=True` by default) and appends
columns to the superbrain-enriched CSV; it never modifies existing
Superbrain/Vanguard fields.

- Strategy weights for the **positional** (1–20 day long options) mode —
  the mode actually in use: Liquidity 0.50, IV 0.40, GEX 0.05, OBI 0.03,
  POC 0.02 (sums to 1.00). An intraday weight set (0.30/0.20/0.20/0.20/0.10)
  exists in comments but is not the live weighting.
- Composite score bands: `SCORE_EXECUTE_NOW=85`, `SCORE_EXECUTE_CAUTION=65`,
  `SCORE_EXECUTE_DEFER=40`.
- EV thresholds (EVEngineV2, the *legacy* single-EV authority pre-dating
  C8): `EV_BLOCK_HARD=-0.10`, `EV_SKIP_THRESHOLD=0.00`,
  `EV_SMALL_THRESHOLD=1.00`, `EV_STANDARD_MAX=1.30`.
- `ExecutionVerdict.eil_final_action`: `SKIP` / `SMALL` / `STANDARD` / `MAX`.
- Deprecated in v3.0 — do not resurrect: any field sourced from
  `ev` / `ev_final` / `ev_option` / `ev_regime` / old `ev_net` /
  `expected_value_20d` (the old `_choose_ev()` inputs).
- Governed trigger handoff (`TRIGGER_HANDOFF_FIELDS`): `trigger_codes`,
  `trigger_count`, `trigger_primary`, `trigger_quality`, `trigger_score`,
  `trigger_go_eligible`, `trigger_stale`, `trigger_freshness_state`,
  `trigger_data_asof`. `trigger_quality` must be one of `STRONG` / `SINGLE`
  / `NONE`; numeric scores are telemetry only and must never substitute
  for the categorical primary/quality value — `validate_trigger_handoff_row()`
  enforces this and fails closed on a missing or type-corrupted block.

## Where run output actually lands (legacy pipeline, per run_id)

`data/output/` (repo root), one set of files per `run_id` timestamp
(`YYYYMMDD_HHMMSS`): `discovery_candidates_ultimate_*.csv`,
`discovery_lifecycle_*.csv`, `discovery_summary_ultimate_*.json`,
`early_positions_ultimate_*.csv`, `external_intel_review_candidates_*.csv`,
`final_watchlist_ultimate_*.csv`, `run_manifest_ultimate_*.json`. Plus
`data/output/latest.json` (pointer only, see above), `data/output/outcomes/`
(pattern-validation + manual-exit-needed history), `data/output/runs/`,
`data/output/run_contexts/`, `data/output/run_plans/`, `data/output/qa/`,
`data/output/state/`.

Fuller-run intelligence lab output (per earlier sessions' description, not
re-verified this pass): `data/output/runs/{run_id}/intelligence_lab/` holding
`lab_signal_book_v2/v3/v4.csv` (the governed per-run book the Lab UI and
coaching tools read) — confirm the current version and field count directly
before building against it, the version has moved (v2→v3→v4) as the rebuild
progressed.

## Macro / market context inputs (`dropbox/macro/`)

`macro_intelligence_latest.json` (the macro contract the orchestrator
verifies/injects — built by `build_macro_json.py`, a manual pre-Evening
step, not part of the orchestrator), `bond_macro_state.json`,
`avshunter_us_money_index.json`, `avshunter_macro_enrichment_delta.json`,
`avshunter_us_economic_event_payload_*.json`, `macro_input_manifest_latest.json`,
plus `Archive/`, `coaching/`, `thesis/` subfolders. Per the spec and
CLAUDE.md rule 6, none of this may gate, score or rank a trade — it is
manual-review display context only.

## `contracts/` (repo root) — rebuild-layer contract modules

`selected_contract_economics.py`, `opportunity_tier.py`,
`direction_governance.py`, `dynamic_session_contract.py`,
`us_money_index_contract.py`, `interpreter_handoff.py`,
`interpreter_handoff_materializer.py`, `interpreter_macro_context.py`,
`lab_control.py` (large — the Lab's field-level control layer),
`lab_evidence_overlay.py`, `quote_change_evidence.py`,
`realised_volatility.py`, `thesis_geometry.py`, `governed_states.py`,
`core_authority_policy.py`, `handoff_contract.py`. Read the specific module
before assuming what it currently enforces — several of these were
mid-remediation as of the last full audit and may have moved since.
