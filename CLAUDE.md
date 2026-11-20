# AVSHUNTER — instructions for Claude Code

Approved by ACK on 16 Sep 2026; rule 4 amended by ACK on 17 Sep 2026 (decision D1); rule 4 suspended by ACK on 7 Oct 2026; rule 6 amended by ACK on 20 Nov 2026 (intelligence mining).

## Before designing or changing pipeline logic

1. Read `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` (v1.1, **governing**), `Enhancements/knowledge/README.md` and the method note for the context you are touching.
2. Authority order: business decisions (ACK) → specification → method notes 01–07 → `Enhancements/decision_map/BUSINESS_DOMAIN_DESIGN_ADDENDUM.md` → `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` → code. A lower document may add detail, never contradict a higher one. Conflicts on method correctness go to ACK.
3. Follow design rules R1–R12 in the end-to-end design: missing is never neutral, one owner per fact, units in names, decide before depend, explicit authority, labels say what was measured, reproducible inputs, clean release, fewer owned components, measured against reality, rank don't gate, fresh or flagged.
4. **SUSPENDED by ACK on 7 Oct 2026** ("due to the nature of the current pipeline disable this rule"): Discovery and Vanguard may be redesigned and modules replaced rather than only fixed in place. The working rules below (test-driven, approved root cause and design first, measured against reality) still apply. Original text, kept for the record: Enhance the existing pipeline; do not rebuild it beside itself. Fix existing modules in place, test-first, one defect at a time (characterise → failing business-rule test → minimal change → acceptance against reality with the outcome scorer). The `avshunter/` package owns measurement (C12 outcome scoring), configuration and run context, and new contexts only where no existing owner exists. Where the specification describes a context as a new build, apply its rules to the existing owner instead. (Replaces the strangler-migration rule, ACK D1, 17 Sep 2026.)
5. No logic gains decision authority without passing gates G1–G4 and spec §24. Legacy EV v2 is not an expected value; EV3 authority stays retired until the new valuation core is validated.
6. **Macro intelligence identifies and explains; the human decides.** *(Amended by ACK on 20 Nov 2026; replaces "Macro and event guards are display-only for manual review; they never influence a gate, score or rank.")*
   - **a. Purpose.** The ETF Macro Board and the three automations (US Money Index, Economic Event Engine, News Terminal) are an intelligence-mining system. It may identify opportunities, decide which ETFs and pipeline names are looked at first, and propose decision scenarios for human review: continuation, reversal, alternative explanation or stand aside, each with evidence for and against, the level that would prove it wrong, and a time frame (D-14.2, D-14.8).
   - **b. Honest evidence.** Every piece of intelligence states where it came from (measured, model, or LLM), its as-of time and what contradicts it. An LLM item built from our own measured sheet is labelled as such. Repeated reports from one source are not independent confirmation. Missing is never neutral.
   - **c. Limits.** Intelligence may order and highlight. On its own it never changes a pipeline gate, score, rank, contract selection or trade direction, and never places or sizes a trade. Any step that alters a pipeline decision needs rule 5 (G1–G4, spec §24) and ACK's written approval.
   - **d. No edge requirement.** Intelligence does not have to prove a predictive edge, and it is not scored as a forecaster. Where we do check whether a pattern holds, the check is written down as a hypothesis before the result is seen.

## Working rules

- No pipeline code changes without an approved root cause and design.
- Validate that logic achieves the business objective, not only that code matches its spec.
- Test-driven: every pipeline change starts with a failing test that states the business rule in domain language; legacy behaviour being changed is pinned by a characterisation test first. A fix is accepted only when the outcome scorer shows the targeted metric moving on history and forward sessions. For the macro board and the three automations (rule 6), a change is accepted when it shows the source data correctly and serves the human review, checked against the source files (ACK, 20 Nov 2026).
- Use reality over textbook: thresholds and models are calibrated on recorded market data (chain quotes, realised outcomes) and stated with their evidence; textbook formulas are a starting point, not an authority.
- Keep enhancement documents, reports and replications in `Enhancements/` until the build is complete.
- Configuration values (thresholds, bands, tolerances) live in versioned configuration (spec Appendix B), never as literals in domain code.
- Never print API key values. Keys are rotated by ACK after the build.
- Commit or push only when ACK asks; ACK runs force pushes.

## Environment

- Windows. Tests: `venv\Scripts\python.exe -m pytest` (not `C:\Python314`); run one file per process and use a short `--basetemp` (e.g. `%TEMP%\avs_pt`) to avoid long-path failures.
- Rebuild package tests: `venv\Scripts\python.exe -m pytest tests_rebuild -q -p no:cacheprovider --basetemp=%TEMP%\avs_rb` (isolated; never touch live `data/` or the network).
- Pipelines are run manually from PowerShell (not the `.bat` files): evening `python intelligent_orchestrator.py --evening`, morning ~15 minutes after the US open `python intelligent_orchestrator.py --morning`. Check a plan first with `--plan-only` (no provider calls, no file changes). Do not run a pipeline while a Phantom backfill is writing.
