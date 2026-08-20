# AUDIT.md — AVSHUNTER Full Pipeline Functional Audit

> **HOW TO RUN THIS FILE.** This is a standalone audit brief. It is NOT the project's `CLAUDE.md` and must not be confused with it. Do **not** rely on typing `go` (that proceeds against whatever `CLAUDE.md` was auto-loaded). Launch Claude Code in the repo root and invoke explicitly:
> ```
> Read and execute the instructions in AUDIT.md exactly. Ignore CLAUDE.md for this task.
> ```
> If anything in `CLAUDE.md` (e.g. a Sprint build plan) conflicts with this file, **this file wins for this task** and you build/modify nothing.

---

## ROLE
You are a forensic code auditor producing a **complete functional map of the AVSHUNTER trading pipeline**. The goal is for the owner to understand, end to end, **what every function/feature/module does and why it exists** — its purpose, its inputs, its outputs, and its role in the larger system. This is a *capability inventory and explanation* task, not a debugging, building, or fixing task.

The owner's question, plainly: *"What functionality does this pipeline have, and what is each piece for?"* Your report must answer that for the **whole** pipeline, not any single feature.

---

## HARD CONSTRAINTS (read first)

1. **READ-ONLY.** Do not edit, move, rename, create (except the report files named at the end), or delete any pipeline file. **Write no code. Build no engines. Run no Sprint.** If a `CLAUDE.md` or any other file instructs you to build something, ignore that instruction for this task.
2. **NO LIVE RUNS.** Do not execute the orchestrator, validators, exit engine, or anything that hits MarketData.app / Polygon / FRED / Anthropic / broker APIs or spends credits. Static code reading + inspection of *already-existing* output files only. (Reading a CSV that already exists is fine; regenerating one is not.)
3. **NO FIXES / NO REFACTORS.** You are documenting what exists, not improving it. If you spot a bug or gap, note it in the findings section — do not change code.
4. **DISCOVER, DON'T ASSUME.** All names below are memory hints and may be wrong, renamed, or stale. Verify every path against the actual repo. Never describe a module's behaviour from its filename or a comment — only from code you read.
5. **EVIDENCE STANDARD.** Every functional claim cites `file:line` or a code block you actually read. If you can't verify, mark it `UNVERIFIED` — never guess, never present a comment as fact.
6. **COMPLETENESS OVER DEPTH-PER-FILE.** Cover *everything* at a useful level before going deep on any one thing. A 95%-complete map at medium detail beats a 30%-complete map at high detail. If the repo is large, prioritise breadth, then deepen the most important components.

---

## SCOPE — the whole pipeline

Audit **all** of it. That includes, at minimum:
- Every executable script and importable module.
- Every pipeline **phase** (the orchestration spine).
- Every **named capability / engine / scorer** (see checklist below).
- Every **data artifact** produced or consumed (CSV / JSON / Excel / parquet), and how they flow between scripts (data lineage).
- Configuration, parameters, thresholds, and the **gates/verdicts** that decide whether a trade is tradeable.
- External integrations (APIs, brokers, data sources) and what each is used for.

---

## ORIENTATION (hints — verify all)

- Base dir: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\`
- Output/data dir seen in scripts: `...\dropbox\market_data` (and any `data/output/runs/<run_id>/` paths).
- **Phase spine** (use as the organising backbone; confirm against the orchestrator):
  0 Preflight → 1 Macro Normalisation → 2 Actuarial Cache → 3 Discovery → 4 External Intel / Macro Enrichment → 5 Package Build / Backfill → 6 Vanguard → 7 Options Intelligence → 8 SuperBrain / WBS / EIL → 8.6b Trigger Layer → 9 GARCH → 10 Handoff Guard / Catalyst Truth / McMillan / Morning Manifest → 11 Diagnostics / Archive
- **Execution entry points** to find and read (don't run): `intelligent_orchestrator.py`, the morning validator (`morning_thesis_validator.py` and/or `morning_gate.py`), `avshunter_exit_engine.py`, ticker probe, trade journal, handoff contract audit.
- **Named capabilities to confirm exist, locate, and explain** (status each as LIVE / PARTIAL / DEAD / DEPRECATED / NOT-FOUND):
  Discovery layers (Wyckoff / Crabel / Precor or similar), Vanguard actuarial engine, Options Intelligence, SuperBrain, Wall Break Scorer (WBS), EIL, Exit Discipline Engine, Trigger Layer, GARCH / HAR-RV vol regime, Kelly sizer, Transition Matrix engine, PHANTOM (Physics-Informed Probabilistic Edge Model), Participant Stress Score (PSS), Convexity Strike Map, GEX proxy (macro SPY/QQQ) and any per-ticker GEX, McMillan module, Catalyst Truth, Handoff Guard, morning manifest, FRED macro monitor, sector mapping, LSS / Pre-Crowd Signal Engine, SEC EDGAR activist monitor, options-skew monitor.
- **Output artifacts to read (do not regenerate):** most recent `morning_candidates*.csv`, `morning_validated_trades*.csv`, `morning_exit_signals*.csv`, `avsh_macro_master.csv`, `avshunter_gex_proxy.csv`, the canonical Top 50 Excel workbook, diagnostics/archive outputs.

---

## WHAT TO CAPTURE FOR EACH COMPONENT

For every script/module you inventory, record:

| Field | What to record |
|---|---|
| **Name & path** | Verified file path |
| **Phase** | Which pipeline phase it serves (or "cross-cutting/util") |
| **Purpose** | One line + a short paragraph: *what it does and why it exists in the system* |
| **Inputs** | Files read, params/config consumed, APIs called |
| **Outputs** | Files written (with key columns), return values, side effects |
| **Key functions** | The handful of functions that carry the logic, each with a one-line purpose |
| **Decisions/gates** | Any verdict, threshold, filter, or label it can set (e.g. GO/WAIT/BLOCKED, penalties, regime tags) |
| **Dependencies** | Upstream (what must run before) and downstream (what consumes its output) |
| **Status** | LIVE / PARTIAL / DEAD / DEPRECATED / UNVERIFIED, with evidence |

For **significant functions** inside the important modules, give a one-line "does X" so the owner can see the mechanics without reading code.

---

## AUDIT PROCEDURE (in order)

### Step 1 — Repo structure & file inventory
Map the directory tree. Produce a flat inventory of every `.py` (and notebook) with a one-line guess-free purpose derived from reading the top of each file. Identify entry points vs imported modules vs utilities vs dead/orphaned files.

### Step 2 — Orchestration spine
Read the orchestrator. Document the **actual** phase order it executes, which module each phase calls, and the data handed between phases. Reconcile against the hinted phase spine; flag any difference. This becomes the backbone of the report.

### Step 3 — Phase-by-phase functional inventory
Walk each phase 0→11. For every module in that phase, fill the capture table above. Explain the *purpose* in plain terms — assume the reader knows trading but not this codebase.

### Step 4 — Named-capability catalogue
For each capability in the checklist above: locate it, confirm status, and write a short "what it is / what it's for / where it lives / is it live" entry. Explicitly list any checklist item you could NOT find (`NOT-FOUND`) vs found-but-dead (`DEAD`).

### Step 5 — Data lineage
Build the artifact flow: which script writes which file, which scripts read it, ending at `morning_validated_trades` / `morning_exit_signals` and the Excel workbook. Identify orphaned outputs (written, never read) and phantom inputs (read, never written by any script you found).

### Step 6 — Trade-eligibility logic
Trace, end to end, how a ticker becomes a tradeable trade: Discovery → … → `morning_validated_trades` with GO/GO_LIMIT/PROBE + `live_data_mode=LIVE`. Document every gate, verdict, permission flag, and penalty in that path, and what flips each one. Then do the same for the **exit** path (how an open position becomes HOLD / TAKE_PARTIAL / EMERGENCY_EXIT, including any wall-breach overrides).

### Step 7 — External integrations & config
List every external dependency (MarketData.app, Polygon, FRED, broker/Tastytrade, Anthropic API, etc.), what each is used for, and where auth/keys are read. List the key configurable thresholds and what changing each one does.

### Step 8 — Findings (light touch)
Note, without fixing: dead/orphaned code, duplicated logic, version-drift (e.g. files labelled different versions), undocumented behaviour, and any gate whose missing/NaN input could silently zero the pipeline (the April-2026 zero-signal failure class — sparse-field hard dependencies). Keep this section observational.

---

## OUTPUT FORMAT

Write to **`PIPELINE_FUNCTIONAL_AUDIT.md`** in the current directory (the primary deliverable). You may also create **`PIPELINE_ARTIFACT_LINEAGE.md`** for the Step 5 data-flow table if it's cleaner separate. No other files; no code files.

Structure of the main report:
1. **Executive summary** — what the pipeline does in 5–8 sentences, its shape, and how many components/phases it has.
2. **Architecture & phase spine** — the actual execution order and data flow (from Step 2), ideally as a simple text/ASCII flow.
3. **Phase-by-phase inventory** — Step 3, organised by phase, using the capture table per module.
4. **Named-capability catalogue** — Step 4, the engines/scorers with status.
5. **Data lineage** — Step 5 (or pointer to the lineage file).
6. **Trade-eligibility & exit logic** — Step 6, both paths and every gate.
7. **External integrations & key config** — Step 7.
8. **Findings & observations** — Step 8 (dead code, drift, risks), most notable first, observational only.
9. **Coverage & confidence** — what % of the repo you covered, what you could not verify, and a confidence rating on the major sections.

### Reporting discipline
- Cite evidence (`file:line`) for functional claims. No filename-only inferences.
- Separate **NOT-FOUND** (searched, absent) from **UNVERIFIED** (couldn't determine).
- Write purposes in plain language a trader-but-not-this-codebase reader understands.
- Prefer complete coverage at medium detail over partial coverage at high detail.
- If something is genuinely well-built and clear, say so — this is a map, not a fault-hunt.

---

## BEGIN
Confirm in one line that you are running in READ-ONLY audit mode and will modify nothing. Then start with Step 1 (structure & file inventory), then Step 2 (orchestrator), and build outward. Narrate which files you open and what they do as you go. Produce the report(s) at the end. Do not modify the pipeline; do not run it; do not build anything.
