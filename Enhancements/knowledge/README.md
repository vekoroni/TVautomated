# AVSHUNTER Knowledge Base

Version: **v2 (draft)** · Reconciled to specification v1.1 on 16 Sep 2026 · Owner: ACK · Status: method notes **for review — not yet approved as Standard**; specification **signed off (governing)**

## Purpose

This folder is the single source of domain knowledge the rebuild is designed against. It exists so that:

1. Every context is designed from established, cited methods — not from ad-hoc heuristics.
2. The **design-adequacy gate (G2)** in `Enhancements/decision_map/OBJECTIVE_ASSURANCE_ASSESSMENT.md` has a written reference to check against.
3. Every Claude Code session, Claude chat session and human reviewer works from the same standards.

## Document authority

```text
BUSINESS DECISIONS (ACK)
        ↓
AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md   governs behaviour, ownership, contracts, states
        ↓
METHOD NOTES 01–07 + REPLICATION_PLAN                    govern statistical and financial method correctness
        ↓
Enhancements/decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md
        ↓
Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md   (map and migration design)
        ↓
CODE
```

A lower document may add detail; it may not contradict a higher one. A conflict between the specification and a method note on method correctness is escalated to ACK. The legacy Python pipeline is an asset mine, not a design reference.

## Governing documents

| File | Role |
|---|---|
| [AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md](AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md) | **Governing behavioural specification v1.1** — contexts C0–C14, invariants, 1–20 session window, candidate geometries, expressions and last exit session, valuation, RAEV ranking, ledger, outcomes, authority progression, configuration governance (Appendix B) |
| [REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md](REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md) | Review changes C1–C14 and ACK decisions C3 / C4 / C9 / Q1 (incorporated in v1.1) |

## Method notes

| File | Capability | Context | Answers |
|---|---|---|---|
| [01_evidence_and_first_passage.md](01_evidence_and_first_passage.md) | O1, O7 | C4 | Competing-risks first-passage probabilities and timing per candidate geometry over sessions 1–20 |
| [02_direction_and_thesis.md](02_direction_and_thesis.md) | O1 | C3, C5 | Candidate geometries, descriptive direction state, geometry selection (R-H), window clock and supersession |
| [03_option_valuation_and_ev.md](03_option_valuation_and_ev.md) | O2, O3 | C8 | EV per $ at risk for options and shares on a common path set with forced exits; single EV_LB; RAEV; time-normalised return |
| [04_volatility_and_cheap_convexity.md](04_volatility_and_cheap_convexity.md) | O4 | C7 | Volatility term forecast, daily IV series, IV dynamics, cheap-convexity profile (display until validated) |
| [05_expression_selection_and_ranking.md](05_expression_selection_and_ranking.md) | O3, O5, O6 | C6, C9, C10 | Bounded expression generation, tradeability, strongest expression, money location, rank not gate, morning decision |
| [06_validation_and_backtesting.md](06_validation_and_backtesting.md) | G3, G4, O7 | C11, C12, C13 | Authority progression, validation rules, ledger and outcomes as validation backbone |
| [07_data_requirements_and_sources.md](07_data_requirements_and_sources.md) | O8 | C1, C2 | Data per method, point-in-time and freshness rules, capture panel, sources and gaps |
| [REPLICATION_PLAN.md](REPLICATION_PLAN.md) | G4 | C3, C4, C5, C7 | Known results to reproduce on our own data (R1–R4) through shadow services before authority |

## Status conventions

- **Governing** — signed off; all lower documents and code must conform.
- **Standard** — approved method; code must follow it.
- **Draft** — proposed; open for review (all method notes in v2).
- **[verify]** after a reference — cited from general knowledge; confirm title, year and venue before relying on it. Claude can misremember citations.
- **Open question** — needs a business or expert decision.
- Authority states for rules/models: `IMPLEMENTED_FOR_REPLICATION`, `NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY`, `SHADOW`, `AUTHORITATIVE`.

## How to use this knowledge base

1. **Research** deeper topics in the Claude Chat tab (Research mode, or a Project containing the books/papers listed here). Bring conclusions back as edits to these notes.
2. **Design**: every context design references the specification section and the method note it follows; deviations are written down with the reason.
3. **Review**: an independent options-quant reviewer signs off the valuation, convexity and ranking notes before they become **Standard**.
4. **Build**: Claude Code sessions read the specification and these notes first (see proposed `CLAUDE.md` below).
5. **Validate**: each note lists the validation test that must pass on real outcomes before the logic gains authority.

## Root `CLAUDE.md` (created and approved 16 Sep 2026 — the repository root file is authoritative; text below is the original proposal)

```markdown
# AVSHUNTER — instructions for Claude Code

Before designing or changing pipeline logic:
1. Read Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md (governing),
   Enhancements/knowledge/README.md and the method note for the context you are touching.
2. Follow the design rules R1–R12 in Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md
   (missing is never neutral, one owner per fact, units in names, decide before depend,
   explicit authority, labels say what was measured, reproducible inputs, clean release,
   fewer owned components, measured against reality, rank don't gate, fresh or flagged).
3. The legacy pipeline is an asset mine, not a design reference. Migrate by strangler:
   build → shadow → replication → validation → authority → retire legacy.
4. No logic gains decision authority without passing gates G1–G4 and spec §24.
5. No pipeline code changes without an approved design. Keep enhancement documents in Enhancements/.
6. Tests: venv\Scripts\python.exe -m pytest (not C:\Python314); use a short --basetemp on Windows.
```

## Changelog

| Date | Change |
|---|---|
| 2026-09-16 | v1 draft: seven method notes and replication plan |
| 2026-09-16 | Specification v1.0 added (ACK); review C1–C14; decisions C3/C4/C9/Q1 |
| 2026-09-16 | Specification v1.1 reconciled and signed off (S1–S5, Appendix B) |
| 2026-09-16 | v2: all method notes, replication plan and README reconciled to spec v1.1 — 1–20 window replaces 5/10/20 holds; competing-risks evidence per candidate geometry; descriptive direction state and R-H; bounded generation with immutable last exit session; long shares in scope; single EV_LB; RAEV with time-normalised tie-break; convexity display-only until validated; ledger for every record; expression outcomes; authority progression; data status updated (weekly IV history, freshness, SPY/QQQ, backfill) |
