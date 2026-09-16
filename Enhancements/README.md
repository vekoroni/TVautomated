# AVSHUNTER Enhancements — working folder

Single location for everything needed for the rebuild, until the build is complete.

Rules: no pipeline code changes until root cause and fix design are approved; the knowledge base is read before designing logic; nothing gets decision authority until it has passed validation.

## Contents

| Folder | Document | Purpose |
|---|---|---|
| `knowledge/` | [AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md](knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md) | **Governing** behavioural specification v1.1 (contexts C0–C14, 1–20 session window; signed off) |
| | [REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md](knowledge/REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md) | Review changes C1–C14; decisions recorded in §6 |
| | [README.md](knowledge/README.md), notes 01–07, [REPLICATION_PLAN.md](knowledge/REPLICATION_PLAN.md) | Method knowledge base and replications R1–R4 |
| `decision_map/` | [END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md](decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md) | Map and migration design v2.0: legacy S0–S18 → contexts C0–C14, rules R1–R12, retire list, strangler phases 0–5 |
| | [BUSINESS_DOMAIN_DESIGN_ADDENDUM.md](decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md) | v2.0: aggregates, decision tree N0–N14, valuation formulas, convexity, ranking, code mapping |
| | [OBJECTIVE_ASSURANCE_ASSESSMENT.md](decision_map/OBJECTIVE_ASSURANCE_ASSESSMENT.md) | Business objectives O1–O8 vs current logic; gates G1–G4 |
| | [DECISION_PATH_MAP_20260914_214012.md](decision_map/DECISION_PATH_MAP_20260914_214012.md) + `decision_map_coverage.py` | Decision path breaks DM-01..DM-38 |
| `forensic_mapping/` | [FORENSIC_CODE_TO_KNOWLEDGE_MAPPING_20260916.md](forensic_mapping/FORENSIC_CODE_TO_KNOWLEDGE_MAPPING_20260916.md) | 122 requirements vs code; reusable assets; §8 EV engine validation |
| `signal_accuracy/` | `signal_accuracy_audit.py` + `runs/20260914_214012/` | Signal recomputation audit |
| `gex/` | [GEX_INVESTIGATION_20260914_214012.md](gex/GEX_INVESTIGATION_20260914_214012.md) + `evidence/` | GEX defects D1–D10 and fix design |
| `data_freshness/` | [PHANTOM_DATA_FRESHNESS_20260916.md](data_freshness/PHANTOM_DATA_FRESHNESS_20260916.md) | Why Phantom history is 12 days stale; capture and freshness fix design |
| `iv_history/` | [IV_HISTORY_INVENTORY_20260916.md](iv_history/IV_HISTORY_INVENTORY_20260916.md) | What IV history exists, gaps, recommended work |

## Document status (16 Sep 2026)

| Document | Version / status |
|---|---|
| Behavioural specification | **v1.1 — signed off, governing** |
| Knowledge notes 01–07, replication plan, knowledge README | v2 — reconciled to spec, Draft (method review pending) |
| Business domain design addendum | **v2.0 — approved (16 Sep 2026)** |
| End-to-end pipeline map and migration design | **v2.0 — approved (16 Sep 2026)** |
| Root `CLAUDE.md` | **Created and approved (16 Sep 2026)** |
| Decision path map, objective assurance assessment | Evidence documents; superseded items marked |
| Forensic mapping, signal accuracy, GEX, IV history, data freshness | Evidence documents |

## Open items

- Set initial configuration values (spec Appendix B) during Phase 0 design.
- Phase 0 — Foundation / Data Truth, starting with the missed-session backfill; then replications R1/R4 through shadow services.
- Independent quant review of method notes 01–05 before they become Standard.
