# Interface Gaps Register — Adjacent-Stage MATCH/GAP Verdicts

**Date:** 2026-08-29 | Companion to `PIPELINE_END_TO_END_MAP_20260829.md`

Each entry covers one producer→consumer boundary in actual execution order (see the main map for why phase *numbers* don't track this order). MATCH = producer's actual output schema is exactly what the consumer actually expects, cited on both sides. GAP = a mismatch, undocumented implicit dependency, or a field the consumer needs that the producer doesn't supply.

---

### Preflight → Macro Normalisation / Discovery
**MATCH.** Preflight resolves `macro_path` (or `None` under graceful degradation) and both downstream consumers correctly branch on its presence. Today: macro was 2.1h old (within the 20h staleness threshold), preflight passed cleanly. *(Agent 1)*

### Macro Normalisation → Package Build
**MATCH.** `macro_snapshot.json`/`macro_quant_packet.json` are embedded verbatim into every package. Verified today: 1,527 packages all carry the macro payload with a consistent `built_at` timestamp. One **GAP** noted separately: `bond_macro_score` is silently nulled in the packet when the yield-curve sidecar is stale, even though a real computed score (55/100, `BOND_MACRO_CAUTION`) exists upstream — the consumer (packages) never sees it. This is a data-freshness-driven signal loss, not a schema mismatch. *(Agent 1)*

### Discovery → External Intel Lane
**MATCH.** The lane reads `discovery_candidates_ultimate_{run_id}.csv` and correctly enforces its own architectural boundary (cannot promote non-Discovery tickers into the core set). Verified: `core_membership_changed: False` in today's result artefact. *(Agent 1)*

### External Intel Lane → Package Build
**MATCH.** The patched discovery CSV (with `external_intel_*` columns stamped) flows into package build unchanged in row membership; the separate advisory-only CSV is correctly never consumed by Packages. *(Agent 1)*

### Package Build/Backfill → Vanguard
**MATCH**, via a defensive design pattern rather than a clean contract. `packages/index.json` gate confirms build success (1,527 built, 0 blocked today). Vanguard's package reader (`run_vanguard_from_packages.py`) checks multiple real OHLCV keys directly rather than trusting the packages' own `data_failure`/`dcv_valid` flags — which is fortunate, because those flags are wrong for essentially 100% of packages post-backfill (see Efficiency Gaps register). The interface *works* today only because the consumer independently re-derives ground truth instead of trusting the producer's stated contract fields. `vanguard_run_summary.json`: 1,482/1,527 passed (97.1%), 45 rejected for one clean labelled cause, within the 5% systemic-failure tolerance. *(Agent 1 + Agent 2, cross-confirmed)*

### Vanguard → Options Intelligence
**MATCH.** `vanguard_signals.csv` flows directly into Options Intelligence's ticker-selection loop; state_hash/behaviour_state_hash and actuarial fields are present as expected. One latent **GAP**: Vanguard's own module documentation states downstream consumers (EIL, MVE, PSE) "must gate on `sample_confidence_bucket`" but no such gate exists anywhere in the code that was searched (`execution_intelligence_runner.py`, `trigger_layer.py`, `final_decision_engine.py`) — the field is passed through but never enforced. Currently inert (nothing reaches capital regardless) but a real documented-vs-implemented gap. *(Agent 2)*

### Options Intelligence → Horizon Router → EV3 Governed Shadow
**MATCH.** The explicit execution-order design ("EV3 must evaluate the final governed horizon, never the provisional Options Intelligence horizon") is confirmed correctly sequenced — Horizon Router patches the OI CSV before EV3 reads it. *(Agent 2)*

### EV3 Shadow / Actuarial Enrichment / Phantom → Trigger Layer / SuperBrain Passthrough
**MATCH** on data flow (each stage's output CSV/package fields are present for the next), with one standing **GAP**: the actuarial-enrichment pass (Phase 8.5) uses a 9-dim state key that is *not* the same 9-dim key Vanguard itself uses (`CORE_HASH_DIMENSIONS`) — two independently-defined schemes for nominally the same concept, increasing audit surface for anyone trying to trace "how confident is the actuarial edge" as a single lineage. Not a breakage, a consistency gap. *(Agent 2)*

### Trigger Layer (package-patch) → SuperBrain Passthrough → Catastrophe Gate (no-op) → Wall Break Scorer
**MATCH** throughout — verified each stage receives what it expects; SuperBrain's passthrough role and Catastrophe Gate's no-op status are both honestly self-documented and confirmed accurate by direct code read. *(Agent 2)*

### Wall Break Scorer → EIL
**GAP, unconfirmed.** WBS's own docstring implies its `wbs_grade` output ("enter immediately," "full campaign") should inform capital-sizing decisions. Grep of `execution_intelligence_runner.py` for `wbs_grade`/`wbs_score` returns **zero hits** in any sizing-assignment code path. This may be a genuine unconsumed-output gap, or WBS may simply be intended as Lab-display-only — **could not fully verify intended scope this pass**; flagged for a follow-up check of whoever deep-audits EIL internals. Separately and regardless of this question, WBS output has no capital authority because the sizing valve itself is zeroed (see Efficiency Gaps register). *(Agent 2)*

### Pre-EIL Actuarial Injection → EIL
**MATCH.** Explicitly documented fix ("FIX-ACTUARIAL-SEQ") ensures actuarial columns are present in `superbrain_enriched` before EIL's `EVEngineV2` reads them; confirmed present in code. *(Agent 2)*

### EIL → GARCH
**MATCH.** `eil_enriched_{run_id}.csv` (EIL output) is what GARCH's merge patches back into; GARCH reads `superbrain_enriched_{run_id}.csv` for the ticker list. Today: EIL succeeded, GARCH's 1,316 rows line up 1:1 with `eil_enriched`'s 1,316 rows. *(Agent 3)*

### GARCH → Trigger Layer (post-EIL pass, "8.6b")
**MATCH**, confirmed working despite the confusing phase-number inversion (8.6b physically runs after 9/10). `trigger_layer_summary_20260829_100803.csv` exists and is fully populated for today's run — the wiring-gap failure mode the code comments warn about ("without this injection, every trigger evaluates [] → trigger_quality=NONE for all rows") did not occur; 74.8% go-eligible today. *(Agent 2 + Agent 3)*

### Trigger Layer (8.6b) → Catalyst Truth → McMillan → EOD Candidate Engine
**MATCH** on data flow. One standing **GAP** feeding into EOD Candidate Engine's funnel: Catalyst Truth supplies real evidence for only 1.0% of tickers (100% manually sourced), which starves Direction Governance's evidence pool and indirectly inflates the "No governed long CALL/PUT direction; chain request suppressed" dropoff reason (333 tickers today) inside EOD Candidate Engine. This is a genuine upstream-evidence-availability gap, not a code defect. *(Agent 3)*

### EOD Candidate Engine → Pipeline Integrity Report → Diagnostics/Archive
**MATCH**, strongly corroborated: `dropoff_audit`, `handoff_contract_audit`, and `uat_audit_report` are three independently-computed artefacts from the same run that agree with each other and with `final_run_manifest.json`'s stated `manifest_permission`. *(Agent 3)*

### Diagnostics/Archive → morning_gate.py
**GAP — sequencing, not schema.** Today's run stops here: `final_run_manifest.json` shows `morning_validation: "PENDING"`, and `logs/orchestrator.log`'s final lines explicitly instruct the operator to run `morning_gate.py` next. This is not a broken interface (the manifest correctly signals `NEEDS_MORNING_VALIDATION`) — it is a **process-state gap**: the evening and morning workflows are two separate manual/scheduled invocations, and as of this investigation the second has not yet run for today's data. Worth flagging as an efficiency gap in its own right (see the register). *(Agent 3)*

### morning_gate.py → morning_handoff_finalizer.py → execution_gate.py
**MATCH, strongly enforced.** `morning_handoff_finalizer.py` performs a fail-closed row-by-row reconciliation (ticker-set equality, verdict-mapping correctness, contract-identity equality, direction-field-hash equality) and raises `MorningHandoffError` on any mismatch. Aug 28 evidence (freshest available — today's run hasn't reached this stage): zero mismatches, `execution_lab_exact_match=true`. *(Agent 3)*

### execution_gate.py → Governed Book (Lab producer)
**MATCH.** `morning_gate.py::main()` and `intelligent_orchestrator.py`'s EOD path both converge on the identical `write_final_opportunity_book()`/`FINAL_BOOK_FIELDS` code path — confirmed by direct code read, both callers produce the same 297-field schema. *(Agent 4)*

### Governed Book (producer) → Intelligence Lab UI (consumer)
**GAP — the most consequential interface defect in this entire investigation.** The producer and its own schema definition agree exactly (297 fields, live artefact vs. `contracts/lab_control.py::FINAL_BOOK_FIELDS`, identical order). The UI, however, was verified via systematic field-name diff to: (a) never surface 159/297 fields at all, including the terminal `readiness_label` synthesis field, and (b) actively read legacy/pre-governed field names for five specific panels (Convexity Score/Engine tab, Vetoes Fired, Entry Reason, Composite Score, AVOID/STAGED campaign stats) that do not exist anywhere in the current 297-field schema, silently rendering 0/blank/"—" instead of the real, correct, populated governed value. This is a genuine schema-drift gap between producer and one specific consumer (the UI), not between the pipeline's internal stages — the data itself is correct all the way to the Lab's JSON output; it breaks only at the final rendering hop a human actually looks at. *(Agent 4)*

---

## Summary

Of the ~20 adjacent-stage boundaries checked, **17 are clean MATCHes** (several via defensive/re-derivation design rather than a formally enforced contract), and **3 carry a GAP worth carrying into the efficiency register**: (1) the documented-but-unenforced `sample_confidence_bucket` gate, (2) the evening→morning process-state gap (today's run simply hasn't reached morning_gate yet), and (3) the Governed Book → Lab UI schema-drift gap, which is by far the most consequential of the three because it is the last hop before a human decision-maker.
