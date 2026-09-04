# 04 — Atlas Part D · Midstream (EIL / Execution / GARCH / WBS / phantom / EV3 / sizing / journal)

**Document:** AVS-E2E-CODE-001 · Lane D
**Scope:** the 103 files listed in `_tooling/lane_D_midstream.txt`
**Ordering authority:** `03_execution_order.md` (stage numbers below refer to its 51-stage evening table)
**Prior under test:** `audit/pipeline_map/AVSHUNTER_END_TO_END_DATA_LOGIC_AND_MONETISATION_REPORT_20260831.md` (AVS-E2E-DATA-LOGIC-001) — treated as claim, not truth.

Every behavioural claim carries `file:line` and is tagged **OBSERVED** (read directly in source) or
**INFERRED** (derived, with basis and confidence). The tag **MEASURED** is not used in this lane; where a
claim has a measurable consequence a `NEEDS_MEASUREMENT:` line gives the exact query.

Registers: `_lane_D_registers.csv` (CON-300..CON-399, GAP-300..GAP-399) and `_lane_D_fields.csv`.

---

## D.0 — Answers to the five lane questions (evidence index)

| Question | Answer | Primary evidence |
|---|---|---|
| What does the EIL runner write, in what order? | `execution/execution_v3_5_{run_id}.csv` **first** (L3280), then `superbrain/eil_enriched_{run_id}.csv` (L3594). Both non-atomic `to_csv`. | `execution_intelligence_runner.py:3280,3594` |
| Is `trigger_quality` in the Execution CSV? | **No.** It is neither written by the runner nor present in `EIL_COLS`. It is read once at L1989 from the *input* frame. It enters `eil_enriched` only at Trigger pass 2 (orchestrator L4770), after the Execution CSV was written. | `execution_intelligence_runner.py:1989,3306-3392` |
| Is the runner a writer or a passthrough for direction / target / invalidation / horizon? | **Passthrough for all four.** No assignment to `direction`, `target*`, `invalidation*` exists anywhere in the file; `horizon_*` is only zeroed on the gate paths and `setdefault`-ed at L1535-1538. | `execution_intelligence_runner.py:1163-1210,1535-1538` |
| Is EV3 authority enabled? | **No — hard-coded off.** `authority_active = False` is a literal, and `--enable-authority` is accepted and ignored. Documented advisory-only policy **HOLDS**; the module docstring describing a conditional activation is **FALSE**. | `scripts/apply_ev3_authority.py:153,156-157,244` |
| Is monetisability computed at EOD? | **Yes, partially.** `MonetisationPolicy.evaluate` runs per row at EIL time and `mp_state` / `mp_final_size_mult` / `mp_hard_block_reason` reach both artefacts. The prior's "not computed" claim is **FALSE as stated**, but **PARTIAL in substance**: the DTE hard gate is inert because of a code defect (CON-312) and no downstream stage in Lane D reads `mp_state` as authority. | `execution_intelligence_runner.py:905-910`; `avshunter_monetisation_policy.py:462-476` |
| Are PSE / Kelly live or retired? | PSE is retired on the pipeline path and correctly banner-marked, but still imported and instantiated by `avshunter_ticker_probe.py:184,778`. Kelly's only importer, `enhancement_integration.py`, has no importer of its own — Kelly is dead, while its own docstring claims the EIL runner imports it. | `position_sizing_engine.py:1-15`; `kelly_sizer.py:6`; `execution_intelligence_runner.py:220-222` |

---

## D.1 — Headline files

### execution_intelligence_runner.py

**Classification:** ORCHESTRATED stage script (subprocess, CLI-driven). The single largest writer in the lane; produces both midstream artefacts.
**Real execution position:** stage 32 of 51, evening, invoked by `intelligent_orchestrator.py::run_execution_intelligence_layer` at L4690 (script path from `OrchestratorConfig` L472). [OBSERVED `03_execution_order.md` row 32]
**Task in the process:** Reads `superbrain/superbrain_enriched_{run_id}.csv`, normalises the Vanguard/actuarial handoff, computes EVEngineV2 results for every row in a first pass, then for each row runs a horizon gate, the five-strategy EIL microstructure engine, a signal-aware block taxonomy, a retired-sizing overlay, a signal-authority policy and a capital-authority finaliser. It writes the full enriched frame to the Execution CSV, then rebuilds a *different* frame — superbrain rows plus a whitelist of EIL columns plus a WBS merge plus actuarial fields lifted from package JSONs — and writes that to `eil_enriched`.

**Entry points:** `__main__` block L3193-3605 (`--run_id` / `--input` / `--output`); library entry `run_engine(df)` L1565; `apply_vanguard_pre_eil_handoff(df, run_dir, logger)` L2791.
**Imports (production):** `ev_engine_v2` (L213), `final_decision_engine.make_final_decision` (L214), `execution_intelligence` (L352-354, guarded), `avshunter_monetisation_policy` (L381-385, guarded), `probability_engine` (L238, guarded), `scenario_builder` (L249, guarded), `scenario_router` (L269ff), `vanguard.physics_state_engine` (L201-211), `eil_eod_resolver`, `pipeline_interpreter.ma_inputs_sync` (L3285, L3600, dynamic).
· **Imported by:** nothing — it is only executed as a subprocess. [OBSERVED, grep across repo]
· **Broken/retired imports:** `make_final_decision` is imported at L214 and **never called anywhere in the file** [OBSERVED, grep `make_final_decision` returns only L132 comment and L214 import]. `position_sizing_engine` is deliberately not imported; `_pse_compute = None`, `_PSE_AVAILABLE = False` are unconditional literals (L220-221).

**Inputs**
- *Files/tables read:* `superbrain/superbrain_enriched_{run_id}.csv` (L3211, L3219); `packages/*.package.json` (L3420); wall-break CSV at `{run_dir}/wall_break_scores_{run_id}.csv` then `{run_dir}/wall_break/wall_break_scores_{run_id}.csv` (L3465-3473).
- *Upstream fields consumed, with fallback chains:*
  - `_bond_macro_context._first(*keys, default="")` L676 — n-key coalesce over bond/macro aliases.
  - `_authority_float(row, *keys, default=0.0)` L1881 and `_authority_text` L1895 — first-non-blank across an alias list; used for `rr_underlying|rr|rr_options` (L1997), `contract_spread_pct|contract_spread_pct_eod|eil_spread_pct_live` (L1998), `contract_premium|premium|premium_eod` (L1999).
  - `_meets_current_edge_clearance._num(*keys, default=0.0)` L2157 — `options_score|options_research_score|ois_score`, `estimated_R|estimated_r|rr_options|risk_reward`, `contract_spread_pct|eil_spread_pct_live|spread_pct`.
  - `_first_present_side(row, ...)` L2527 over eight direction aliases (L2537) and four Vanguard aliases (L2538).
  - `_correct_ev = eil_row.get("ev2_ev_conf_adj") or eil_row.get("fd_ev_used")` L3513 — bridges *numeric zero* to *missing*; an EV of exactly 0.0 silently falls through to the second key.
  - `_sp = merged.get("signal_price") or sb_row.get("signal_price")` L3532.
  - `_finalize_execution_authority`: `row.get("pse_final_size", row.get("fd_size", 0.0))` L2336; `row.get("eod_candidate_size", row.get("candidate_size", row.get("pse_pre_horizon_size", 0.0)))` L2337-2340; `row.get("layer2__kelly_fraction", row.get("kelly_fraction", 0.0))` L2412.
  - Silent-swallow blocks: `except Exception: pass` L3429-3430 (per-package JSON parse), L2513-2514 (`pd.isna`), L2438-2439 (confidence haircut), L1379-1380 (spread compute), L3525-3526 (EV display fix); `except Exception as _e: logger.warning("eil_enriched write failed (non-critical)")` L3604-3605 wraps the **entire** eil_enriched production block.
- *External calls:* none. No API, no DB. `pipeline_interpreter.ma_inputs_sync.on_pipeline_complete` is called twice (L3286, L3601) with a hard-coded absolute path inserted onto `sys.path` (L3284, L3599).
- *Config/policy read:* `AVSHUNTER_ACCOUNT_RISK_BUDGET` env, default `"1000"` (L2413). Module constants: `_PSE_RETIRED_ADVISORY_ONLY = True` (L222), `PSE_RETIRED_POLICY = "PSE_IGNORED_MANUAL_SIZING"` (L223), `OPTIONS_RESEARCH_PERMISSION = "MANUAL_REVIEW_REQUIRED"` (L227), the five options-route constants (L228-232), `_EIL_TOKEN_NORMALISE` (L365-372), `_EIL_DATA_MODE` from wall-clock hour (L332-343).

**Logic and algorithms**
- **Two-pass structure.** Pass 1 `_compute_all_ev` L920-940 enriches and evaluates EV for every row; pass 2 `_process_row` L1120-1558 runs per-row decisioning with the pre-computed `EVResult`.
- **v4.1 Horizon gate** L1155-1215 (named in the docstring L1136-1140). Ordered: `horizon_action == "MONITOR_ONLY"` → early return with `eil_v3_verdict="MONITOR_ONLY"` (L1180-1195); `horizon_bucket == "blocked"` → early return `BLOCKED` (L1197-1210); otherwise proceed. Both early returns skip EIL scoring entirely.
- **`eil_v3_verdict` derivation chain** (the lane's central question): `execution_intelligence.evaluate(ctx)` → `_composite_verdict(score, hard_block)` (`execution_intelligence.py:149-158`) → token → `_EIL_TOKEN_NORMALISE.get(token, "BLOCKED")` (L1323). Unknown tokens map to `BLOCKED`. On engine exception → `BLOCKED` + `eil_failure_reason` (L1387-1388); on engine unavailable → `BLOCKED` + `EIL_UNAVAILABLE` (L1394-1395).
- **Signal-aware block taxonomy** L1406-1508, reached when `campaign == "REJECT" or execution == "SKIP"`. Ordered branches on `signal_type`: `{NO_EDGE, DATA_MISSING}` or tier `{TIER_4_FLAT, DATA_MISSING}` → EOD probe / data-insufficient (L1432-1437); `STRUCTURAL_MATCH` → `STRUCTURAL_WATCH` (L1439-1443); `FUTURE_EDGE` → `FUTURE_WATCH` (L1445-1449); `{CURRENT_EDGE, TRANSITION}` → four-way SKIP reason ladder (L1451-1469); else campaign REJECT → `FATAL_BLOCK`, otherwise `UNCLASSIFIED_SIGNAL_EXECUTION_SKIP` (L1471-1483).
- **`_eod_candidate_profile`** L1976-2051 — the actual EOD monetisation gate. `allowed` requires signal ∈ {CURRENT_EDGE, FUTURE_EDGE, STRUCTURAL_MATCH, TRANSITION} **and** `eil_ok` **and** `economics_ok` **and** `support_ok` **and** `contract_seen` **and** `liquidity_ok` **and not** direction-conflict-unresolved **and not** options-research-blocked (L2020-2029).
- **`_finalize_execution_authority`** L2317-2459 — six-way ladder producing `effective_execution_verdict` and `capital_authorization_state`.
- **`_ensure_eil_audit_contract`** L2590-2708 — vectorised backfill of 15 audit columns, then per-row `_catalyst_conflict_row` and `_direction_arbitration_row`, then a conflict-status resolution.
- *Decision branches — CALL / PUT / other-blank:* The file contains **exactly one** direction vocabulary, `_handoff_side` L2518-2524. CALL-family → `"CALL"`; PUT-family → `"PUT"`; **everything else returns `""`** — including `STRANGLE`, `UNRESOLVED`, `NEUTRAL`, `NONE` and blank (L2524). Consequence chain: `_first_present_side` returns `""` (L2533) → `_direction_arbitration_row` takes the `if not option_side` branch → `direction_arbitration_status = "NOT_EVALUATED"`, `direction_conflict_gate = "NONE"` (L2540-2545). A STRANGLE row and a row with no direction at all are therefore indistinguishable in every downstream direction-audit field. There is no branch anywhere in the file that treats CALL and PUT asymmetrically.

**Computations and formulas (exact)**
- `_default_hsm` = `0.0` if `horizon_action=="MONITOR_ONLY"` or `horizon_bucket=="blocked"`; `0.70` if bucket `6_10d`; else `1.0` (L1163-1168). `_hsm = max(0.0, min(1.5, _f(row,"horizon_size_multiplier", _default_hsm)))` (L1169-1170) — clamp [0.0, 1.5], dimensionless.
- `eil_spread_pct_live = round((ask - bid) / mid * 100.0, 4)` (L1374-1376), percent, 4 dp; written only when bid, ask and mid are all non-None and `mid > 0`; otherwise `float("nan")` when the key is absent (L1377-1378).
- `economics_ok` (no contract present) = `rr >= 1.35 and options_score >= 20.0` (L2008) — dimensionless ratio and 0-100 score.
- `liquidity_ok = options_ok or spread <= 30.0 or spread <= 0.0` (L2016), percent. Note the third disjunct: a spread of exactly 0.0 — the value produced when the field is missing — satisfies the gate.
- `suggested = max(1, round(kelly * risk_budget / max(premium * 100.0, 1.0)))` when EOD-authorised and `premium > 0`, else `default_probe_size` (L2414), contracts, floor 1.
- Confidence haircut: `confidence_score = round(conf * 0.875, 4)` when `spread_source == "OI_DERIVED"` (L2437), i.e. a flat 12.5 % reduction, tagged `microstructure_confidence_haircut = "OI_DERIVED_SPREAD_12_5PCT"` (L2440).
- Display overwrite: `merged["ev"] = merged["ev_conf_adj"] = merged["ev_final"] = merged["ev_net"] = round(float(_correct_ev), 6)`; `merged["ev_base"] = round(float(ev2_ev_structural), 6)` (L3517-3524).
- `pin_risk_score`, `runway_to_wall_pct`, `wbs*` are **not** computed here; they are merged from the WBS CSV (L3556-3560).

**Models** — The runner hosts no model of its own. It invokes `EVEngineV2` (see §D.1 `ev_engine_v2.py`) and `execution_intelligence.evaluate` (five-strategy composite, weights `0.50/0.40/0.05/0.03/0.02`, see `execution_schema.py`). Version tag emitted per row: `eil_runner_version = EIL_RUNNER_VERSION` (L2089, L1495, L3348).

**Outputs**
1. `execution/execution_v3_5_{run_id}.csv` — L3280, `out.to_csv(args.output, index=False)`. **Column set = every column of the superbrain input frame after `apply_vanguard_pre_eil_handoff`, plus every field written by `run_engine`/`_process_row`, plus `append_physics_fields_from_source` (PHYSICS_FIELDS), plus `_ensure_eil_audit_contract` (15 audit columns), plus `enrich_dataframe_with_truth_packets` (TRUTH_PACKET_META_FIELDS).** It is a superset, not a whitelist. [OBSERVED L3270-3280]
2. `superbrain/eil_enriched_{run_id}.csv` — L3594. **Column set = the superbrain row (`merged = sb_row.to_dict()`, L3497) plus only those `EIL_COLS` (L3306-3392) present in the EIL row, plus `WBS_COLS` (L3451-3461) where non-blank, plus nine `ACTUARIAL_PROPAGATE_COLS` (L3400-3410) and five flat actuarial aliases (L3575-3580), plus physics, audit-contract and truth-packet fields.** This is a whitelist.
- *Atomic promotion:* **No.** Both writes are direct `to_csv` onto the final path; no temp file, no rename, no validation gate. This contradicts AVS-E2E-DATA-LOGIC-001 §14.6.
- *Schema/version field:* `eil_runner_version` (row-level) and `eil_schema_version` (L1359). No file-level schema block.
- *Authority-claim fields:* `execution_authorized` (L2398) — **HOLDS**, it is `False` unless `capital_permission ∈ {YES, LIVE_EXECUTE, CAPITAL_APPROVED}` **and** `size > 0.0` **and** `pse_execution_mode ∈ {PROBE, REDUCED, EXECUTE, FULL_EXECUTE}` (L2361-2365), and `pse_final_size` is unconditionally `0.0` (L1152, L2065, L2117, L3153-equivalent), so the conjunction can never be true in a production run. `execution_verdict_source` = `"CAMPAIGN_LABEL_PRE_LIVE"` on that path (L2450) — **HOLDS**. `sb_final_verdict` promotion (L3551-3553) — **PARTIAL**: only non-`BLOCK` verdicts are promoted, so a `BLOCK` row silently retains the stale SuperBrain verdict.

**Handoff** — *Receives from:* stage 28 SuperBrain passthrough (`superbrain_enriched`), stage 31 WBS (`wall_break_scores`), Phase 8.5 actuarial (`packages/*.package.json`). *Hands to:* stage 33 `inject_actuarial_into_eil_csv`, stage 34-35 GARCH merge (which patches **both** artefacts, `intelligent_orchestrator.py:3256-3303`), stage 36 Trigger pass 2 (`eil_enriched` **only**), stage 40 EOD Candidate Engine. *Join keys:* `ticker`, upper-cased and stripped (L3479, L3489, L3496).

**Missing-data handling**
| Condition | Emitted value / state | file:line | §10-compliant? |
|---|---|---|---|
| EIL engine raises | `eil_v3_verdict="BLOCKED"`, `eil_failure_reason="EIL_EVALUATION_FAILED: …"` | 1387-1388 | **N** — a `DATA_DEFECT` is emitted as a decision verdict |
| EIL engine unimportable | `eil_v3_verdict="BLOCKED"`, `eil_failure_reason="EIL_UNAVAILABLE"` | 1394-1395 | **N** — same |
| Horizon action MONITOR_ONLY | `eil_data_mode="HORIZON_GATED"` | 1188 | Y |
| No live option chain | `eil_data_mode="EOD_SYNTHETIC"` / `…_WITH_CONTRACT_QUOTE_FALLBACK"` | 1288, 1307 | Y |
| bid/ask/mid unusable | `eil_spread_pct_live = nan` | 1378 | Y |
| Package dir absent | warning only; actuarial columns simply absent | 3444-3448 | **N** — no state token written |
| WBS file absent at either path | `wbs_map = {}` silently; no WBS columns and no marker | 3466-3473 | **N** — indistinguishable from "WBS ran and scored nothing" |
| `premium == 1.0` or `contract_mark_synthetic` truthy | `premium_label="BSM"`, `premium_is_synthetic=True` | 3543-3545 | **N** — a genuine $1.00 premium is mislabelled synthetic; the test is a string comparison against `"1.0"`/`"1"` |
| eil_enriched block raises anywhere | warning "non-critical"; artefact absent | 3604-3605 | **N** — a missing primary artefact is logged at WARNING |
| MonetisationPolicy raises | `row.setdefault("mp_hard_block_reason","")` | 913 | **N** — engine failure reads as "no block" |
| MonetisationPolicy unavailable | same empty string | 915 | **N** — same |

**Contradictions found here:** CON-300, CON-301, CON-302, CON-303, CON-304, CON-305, CON-306, CON-320
**Gaps found here:** GAP-300, GAP-301, GAP-302, GAP-303, GAP-304, GAP-320

**Comment/docstring claims audited:**
- L1134 "FinalDecisionEngine produces the authoritative verdict." → **FALSE**. `make_final_decision` is imported (L214) and never called; `fd_verdict` is written by `_apply_retired_sizing_overlay` L2083 as a passthrough of `eil_v3_verdict`.
- L1130-1132 "EIL five-strategy composite engine called here, before FinalDecisionEngine" → **PARTIAL**. The first clause holds (L1318); the second names a stage that does not execute.
- L57-59 "PSE-01 … RETIRED from production authority … must not allocate, suppress, or resize trades" → **HOLDS**. `pse_final_size` is set to `0.0` at every write site (L1152, L1190, L1205, L1488, L2065, L2117, L2352) and `_PSE_AVAILABLE` is a literal `False` (L221).
- L65-67 "PSE-03 … `pse_final_size`/`fd_size` are always 0.0" → **HOLDS**.
- L3202-3206 "FIX-BASE-SCOPE … base must be set regardless" → **HOLDS** (L3207-3212).
- L3209 comment `# FIX-PATH-HARDCODE 2026-05-20` → **PARTIAL**. The runs path was de-hardcoded, but L3284 and L3599 hard-code `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter` in the same file.
- L3395-3399 "EDE reads these flat-prefixed column names from the EIL CSV … Without this EDE reads None for all actuarial fields → score=0.000." → **FALSE**. `execution_decision_engine.py` has no live caller; the orchestrator's only invocation is commented out at L4830.
- L3563-3566 "EDE reads actuarial_win_rate_10d … Without this propagation those columns are absent → EDE scores 0.000 → all BLOCKED." → **FALSE**, same reason.
- L3506-3512 "DISPLAY FIX 1 … the Intelligence Lab reads ev / ev_final for display. Overwrite them here so the Lab shows the correct EVEngineV2 value" → **HOLDS** as a description of the code, but the overwrite is applied to the *stored* columns, not to a display-only alias (L3517-3520).
- L1172-1179 "DEF-HORIZON-EIL … horizon_bucket is informational only. The router … NEVER emits MONITOR_ONLY as an action" → **PARTIAL**. The guard is retained and would fire (L1180); the assertion about the router is a claim about another lane's module and is not verified here.
- L1259-1261 "BLOCKER 2: `_ACTIVE_EOD_RESOLVER` was set in run_engine() but never used here … Resolver now called first" → **HOLDS** (L1266-1268).
- L949-951 "`_percentile_overrides` … Retired compatibility hook. EV percentile ranking is observational and cannot override or alter any production route." → **HOLDS**; the function returns `[False] * len(ev_results)` (L952).
- L2056-2058 "PSE is advisory-only and may not allocate, suppress, or resize trades." → **HOLDS**.
- L2320-2322 "execution_verdict remains the historical campaign label. Downstream funding decisions should read execution_authorized and effective_execution_verdict." → **HOLDS** as coded; whether downstream honours it is a Lane B/E question.

**Confidence in this section:** HIGH for the write order, the two column sets, the direction vocabulary and the dead-consumer findings — all read directly from source and cross-checked by repo-wide grep. MEDIUM for the exact runtime column count of `execution_v3_5`, which depends on the superbrain input schema and is not fixed in code. `NEEDS_MEASUREMENT: compare header(execution/execution_v3_5_20260831_010309.csv) against header(superbrain/eil_enriched_20260831_010309.csv); report columns present in one and absent in the other, and confirm 'trigger_quality' appears only in the latter.`

---
