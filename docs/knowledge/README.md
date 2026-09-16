# AVSHUNTER Knowledge Base

Version: **v1 (draft)** · Started 16 Sep 2026 · Owner: ACK · Status: **for review — not yet approved as a standard**

## Purpose

This folder is the single source of domain knowledge the pipeline is built against. It exists so that:

1. Every stage is designed from established, cited methods — not from ad-hoc heuristics.
2. The **design-adequacy gate (G2)** in `audit/decision_map/OBJECTIVE_ASSURANCE_ASSESSMENT.md` has a written reference to check against.
3. Every Claude Code session, Claude chat session and human reviewer works from the same standards.

It complements the design documents in `audit/decision_map/`:
- `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` — stages, rules R1–R10, build phases
- `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md` — bounded contexts, decision tree, valuation, ranking
- `OBJECTIVE_ASSURANCE_ASSESSMENT.md` — capabilities O1–O8, assurance gates G1–G4

## Method notes

| File | Capability | Answers |
|---|---|---|
| [01_evidence_and_first_passage.md](01_evidence_and_first_passage.md) | O1, O7 | How to turn price history into honest probabilities for target / stop / timeout |
| [02_direction_and_thesis.md](02_direction_and_thesis.md) | O1 | How direction, hold, invalidation and target should be decided and tested |
| [03_option_valuation_and_ev.md](03_option_valuation_and_ev.md) | O2, O3 | How to compute EV per $ at risk for long options, debit verticals and short shares |
| [04_volatility_and_cheap_convexity.md](04_volatility_and_cheap_convexity.md) | O4 | How to measure realised/forecast volatility and whether convexity is cheap |
| [05_expression_selection_and_ranking.md](05_expression_selection_and_ranking.md) | O3, O5, O6 | How to pick the strongest expression and rank instead of gate |
| [06_validation_and_backtesting.md](06_validation_and_backtesting.md) | G3, G4, O7 | How to prove any of the above works, without fooling ourselves |
| [07_data_requirements_and_sources.md](07_data_requirements_and_sources.md) | O8 | What data each method needs, point-in-time rules, and where it comes from |
| [REPLICATION_PLAN.md](REPLICATION_PLAN.md) | G4 | Known results to reproduce on our own data before trusting new logic |

## Status conventions

- **Standard** — approved; code must follow it.
- **Draft** — proposed; open for review (all notes in v1).
- **[verify]** after a reference — cited from general knowledge; confirm title, year and venue before relying on it. Claude can misremember citations.
- **Open question** — needs a business or expert decision.

## How to use this knowledge base

1. **Research** deeper topics in the Claude Chat tab (Research mode, or a Project containing the books/papers listed here). Bring conclusions back as edits to these notes.
2. **Design**: every stage design references the method note it follows; deviations are written down with the reason.
3. **Review**: an independent options-quant reviewer signs off the valuation, convexity and ranking notes before they become **Standard**.
4. **Build**: Claude Code sessions read these notes first (see proposed `CLAUDE.md` below).
5. **Validate**: each note lists the validation test that must pass on real outcomes before the logic gains authority.

## Proposed root `CLAUDE.md` (not yet created — needs approval)

```markdown
# AVSHUNTER — instructions for Claude Code

Before designing or changing pipeline logic:
1. Read docs/knowledge/README.md and the method note for the capability you are touching.
2. Follow the rules R1–R10 in audit/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md
   (missing is never neutral, one producer per field, units in names, decide before depend,
   explicit authority, labels say what was measured, reproducible inputs, clean release,
   fewer owned stages, measured against reality).
3. No logic gains decision authority without passing gates G1–G4
   (audit/decision_map/OBJECTIVE_ASSURANCE_ASSESSMENT.md).
4. No pipeline code changes without an approved design.
5. Tests: venv\Scripts\python.exe -m pytest (not C:\Python314).
```

## Changelog

| Date | Change |
|---|---|
| 2026-09-16 | v1 draft: seven method notes and replication plan |
