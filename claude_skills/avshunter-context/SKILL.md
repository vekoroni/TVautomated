---
name: avshunter-context
description: Domain knowledge for the AVSHUNTER options trading pipeline (ACK's repo) — entities, schemas, governance chain, known defects and file locations. Load before analysing runs, designing fixes, or answering questions about this codebase.
---

# AVSHUNTER Context

This skill exists so a session working in the AVSHUNTER-Intelligence repo doesn't
need ACK to re-explain the domain from scratch. Read the reference file that
matches the task before doing anything else.

## What AVSHUNTER is

A live, real-capital, advisory-only options intelligence pipeline on Tastytrade.
ACK is architect and primary trader. Mandate: long single-leg CALLs/PUTs, max
hold ~15–20 sessions. The pipeline finds candidates, prices and ranks
expressions, and hands a human a decision; it never executes trades itself.

## Authority chain (read in this order for any design/logic question)

1. ACK's own decisions (stated directly, or in `Enhancements/knowledge/ACK_DECISIONS_*.md`)
2. `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` — **governing**
3. Method notes `Enhancements/knowledge/01..07_*.md` — statistical/financial method correctness
4. `Enhancements/decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md`
5. `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`
6. Code

A lower document may add detail, never contradict a higher one. See
`references/governance-and-gates.md` for the full rule set (R1–R12, gates
G1–G4, authority states) — this is not optional context, it's a hard
constraint on any proposed change.

## Navigation

- `references/specification-map.md` — the C0–C14 context map, what each owns, and which method note governs it
- `references/entities-and-schemas.md` — the real objects (run, candidate, contract, thesis, decision record, outcome) and where their fields live in code/CSV/JSON
- `references/governance-and-gates.md` — CLAUDE.md rules, design rules R1–R12, gates G1–G4, authority states, the rank-don't-gate principle
- `references/known-defects-and-gotchas.md` — historical bugs and traps already found by audit, so they aren't rediscovered or silently reintroduced
- `references/file-map.md` — where things actually live on disk (repo root, `data/`, `dropbox/`, `contracts/`, `avshunter/`, `Enhancements/`)

## Working rules that always apply

- No pipeline code changes without an approved root cause and design (CLAUDE.md).
- Enhance existing modules in place; do not build a parallel system beside them (CLAUDE.md rule 4, ACK decision D1, 17 Sep 2026).
- Macro/event guards are display-only — they never gate, score, or rank (CLAUDE.md rule 6).
- No logic gets decision authority without passing gates G1–G4 and spec §24.
- A fix is accepted only when the outcome scorer (`avshunter/c12_outcome`) shows the targeted metric moving on history and forward sessions — not just that a test passes.
- Configuration values live in versioned config (spec Appendix B), never literals in domain code.
- Commit/push only when ACK asks.

## When ACK asks for analysis, dashboards, or calibration work

That is not "pipeline logic" under rule 4 — it's read-only tooling that reads
governed output and writes to a new location (pattern already used for
`build_macro_json.py`, the GEX proxy script, and Desk Gate). Do not edit
`avshunter/`, `orchestrator/`, `contracts/`, or any of the numbered engine
files at repo root as part of this kind of work. Write output under
`dropbox/macro/coaching/` or a similarly clearly-separate folder, and say
so explicitly.
