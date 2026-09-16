# AVSHUNTER — instructions for Claude Code

Approved by ACK on 16 Sep 2026.

## Before designing or changing pipeline logic

1. Read `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` (v1.1, **governing**), `Enhancements/knowledge/README.md` and the method note for the context you are touching.
2. Authority order: business decisions (ACK) → specification → method notes 01–07 → `Enhancements/decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md` → `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` → code. A lower document may add detail, never contradict a higher one. Conflicts on method correctness go to ACK.
3. Follow design rules R1–R12 in the end-to-end design: missing is never neutral, one owner per fact, units in names, decide before depend, explicit authority, labels say what was measured, reproducible inputs, clean release, fewer owned components, measured against reality, rank don't gate, fresh or flagged.
4. The legacy pipeline is an asset mine, not a design reference. Migrate by strangler: build → shadow → replication → validation → authority → retire legacy.
5. No logic gains decision authority without passing gates G1–G4 and spec §24. Legacy EV v2 is not an expected value; EV3 authority stays retired until the new valuation core is validated.
6. Macro and event guards are display-only for manual review; they never influence a gate, score or rank.

## Working rules

- No pipeline code changes without an approved root cause and design.
- Validate that logic achieves the business objective, not only that code matches its spec.
- Keep enhancement documents, reports and replications in `Enhancements/` until the build is complete.
- Configuration values (thresholds, bands, tolerances) live in versioned configuration (spec Appendix B), never as literals in domain code.
- Never print API key values. Keys are rotated by ACK after the build.
- Commit or push only when ACK asks; ACK runs force pushes.

## Environment

- Windows. Tests: `venv\Scripts\python.exe -m pytest` (not `C:\Python314`); run one file per process and use a short `--basetemp` (e.g. `%TEMP%\avs_pt`) to avoid long-path failures.
- Rebuild package tests: `venv\Scripts\python.exe -m pytest tests_rebuild -q -p no:cacheprovider --basetemp=%TEMP%\avs_rb` (isolated; never touch live `data/` or the network).
- Pipelines are run manually from PowerShell (not the `.bat` files): evening `python intelligent_orchestrator.py --evening`, morning ~15 minutes after the US open `python intelligent_orchestrator.py --morning`. Check a plan first with `--plan-only` (no provider calls, no file changes). Do not run a pipeline while a Phantom backfill is writing.
