# Governance, rules, and gates

Source: repo-root `CLAUDE.md` (approved by ACK 16 Sep 2026; rule 4 amended 17
Sep 2026, decision D1) plus `Enhancements/knowledge/README.md`. Treat the
repo-root `CLAUDE.md` as authoritative if this ever drifts from it — copy it
back into this file if it changes.

## Document authority order

```
BUSINESS DECISIONS (ACK)
  → AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md (v1.1, governing)
  → METHOD NOTES 01–07 + REPLICATION_PLAN.md (statistical/financial method correctness)
  → Enhancements/decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md
  → Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md
  → CODE
```

A lower document may add detail; it may never contradict a higher one. A
conflict between the specification and a method note on method correctness
is escalated to ACK — don't resolve it by guessing.

## Before designing or changing pipeline logic (CLAUDE.md, verbatim intent)

1. Read the governing spec, the knowledge README, and the method note for
   the context being touched — before proposing a design, not after.
2. Follow the authority order above.
3. Follow design rules R1–R12 from the end-to-end design doc: missing is
   never neutral · one owner per fact · units in names · decide before
   depend · explicit authority · labels say what was measured ·
   reproducible inputs · clean release · fewer owned components · measured
   against reality · rank don't gate · fresh or flagged.
4. **Enhance the existing pipeline; do not rebuild it beside itself**
   (ACK decision D1, 17 Sep 2026 — replaces the earlier strangler-migration
   rule). Fix existing modules in place, test-first, one defect at a time:
   characterise → failing business-rule test → minimal change → acceptance
   against reality via the outcome scorer. `avshunter/` owns measurement
   (C12 outcome scoring), configuration and run context; new contexts are
   created only where no existing owner exists. Where the spec describes a
   context as "new build," apply its rules to the existing owner instead.
5. No logic gains decision authority without passing gates G1–G4 and spec
   §24. Legacy EV v2 is explicitly **not** an expected value; EV3 authority
   stays retired until the new valuation core (C8) is validated.
6. Macro and event guards are **display-only** for manual review — they
   never influence a gate, score, or rank. This is a hard spec + CLAUDE.md
   rule, not a stylistic preference; any design that lets USMI/GEX/macro
   size or gate a trade is non-compliant regardless of backtest results.

(The precise G1–G4 gate definitions live in
`Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` —
read that file directly rather than assuming its contents; it wasn't fully
indexed when this skill was built.)

## Working rules

- No pipeline code changes without an approved root cause and design.
- Validate that logic achieves the business objective, not only that code
  matches its spec.
- Test-driven: every pipeline change starts with a failing test that states
  the business rule in domain language; legacy behaviour being changed is
  pinned by a characterisation test first. A fix is accepted only when the
  outcome scorer shows the targeted metric moving on history **and**
  forward sessions — a green test alone is not acceptance.
- Reality over textbook: thresholds/models are calibrated on recorded
  market data (chain quotes, realised outcomes) and stated with their
  evidence; textbook formulas are a starting point, never an authority.
- Keep enhancement documents, reports and replications in `Enhancements/`
  until a build is complete.
- Configuration values (thresholds, bands, tolerances) live in versioned
  configuration (spec Appendix B), never as literals in domain code.
- Never print API key values. Keys are rotated by ACK after a build.
- Commit or push only when ACK asks; ACK runs force pushes.

## Environment

- Windows. Tests: `venv\Scripts\python.exe -m pytest` (not `C:\Python314`);
  run one file per process, short `--basetemp` (e.g. `%TEMP%\avs_pt`) to
  avoid long-path failures.
- Rebuild package tests:
  `venv\Scripts\python.exe -m pytest tests_rebuild -q -p no:cacheprovider --basetemp=%TEMP%\avs_rb`
  — isolated, never touches live `data/` or the network.
- Pipelines are run manually from PowerShell, not the `.bat` files:
  evening `python intelligent_orchestrator.py --evening`; morning ~15
  minutes after the US open `python intelligent_orchestrator.py --morning`.
  Check a plan first with `--plan-only` (no provider calls, no file
  changes). Never run a pipeline while a Phantom backfill is writing.

## What this means for non-pipeline (analysis/tooling) work

Building a dashboard, running a calibration, or auditing a spreadsheet is
**not** "pipeline logic" under rule 4 above — but the same spirit applies:
read governed output, don't fork a parallel system, and be explicit about
where output lives. The established pattern (used by `build_macro_json.py`,
the GEX proxy Colab script, and Desk Gate) is: read-only overlay, run
manually or on a schedule outside the orchestrator, write to a clearly
separate location (`dropbox/macro/...`), never edit `avshunter/`,
`orchestrator/`, `contracts/`, or the numbered engine files at repo root.
Treat that boundary as fixed unless ACK says otherwise.
