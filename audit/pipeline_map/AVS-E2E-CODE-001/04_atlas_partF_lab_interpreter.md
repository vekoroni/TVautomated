# 04 — Atlas Part F — Intelligence Lab UI + Pipeline Interpreter

**Document:** AVS-E2E-CODE-001 · Lane F
**Evidence run:** `data/output/runs/20260831_010309/` (EOD run)
**Scope:** `pipeline_interpreter/**` (all), `intelligence-lab/static/**`,
`contracts/interpreter_handoff.py`, `contracts/interpreter_handoff_materializer.py`,
`contracts/interpreter_macro_context.py`.
**Out of scope (Lane B owns):** `intelligence-lab/intelligence_lab.py`,
`contracts/lab_control.py`. Both are read for cross-reference only; no atlas
section is written for them here.

Claim tags: **OBSERVED** = read directly from source at the cited line.
**INFERRED** = deduced; basis and confidence stated. `NEEDS_MEASUREMENT:` marks
a claim with a measurable consequence not measured in this lane.

§10 missing-data vocabulary referenced throughout: AVAILABLE /
PENDING_MORNING_REFRESH / NOT_APPLICABLE / UNAVAILABLE_PROVIDER / DATA_DEFECT /
STALE_ADVISORY / CONTRACT_REPAIR_REQUIRED / SYNTHETIC_RESEARCH_ONLY.

---

## F0 — Lane summary: the two Interpreter input paths

The Interpreter has **two mutually exclusive input paths**, selected by the
single runtime flag `interpreter_resolver`
[OBSERVED `msi_runtime.py:42`, `msi_runtime.py:57`]:

| Path | Selector | Input artefact | Discipline |
|---|---|---|---|
| **MSI governed** | `active_flags().interpreter_resolver` is true | `data/output/runs/<run>/interpreter/handoff_manifest.json` → `intelligence_lab/lab_signal_book_v3.csv` + `interpreter/interpreter_evidence_bundle_v1.jsonl` | HOLDS |
| **Legacy** | flag false | `pipeline_interpreter/MA_Inputs/**` plus direct globs into `data/output/runs/*/{options,superbrain,execution,vanguard,discovery,horizon}/…` | FALSE |

`config/msi_runtime.json` sets `interpreter_resolver: true`
[OBSERVED `config/msi_runtime.json`], so the governed path is the configured
production path. The dataclass default is `False`
[OBSERVED `msi_runtime.py:42`], so any environment that loses the config file
silently reverts to the legacy path.

The governed book the Interpreter requires is **`lab_signal_book_v3.csv`**,
written by `contracts/interpreter_handoff_materializer.py:300,305`. It is **not**
the `final_opportunity_book_*.csv` written by the orchestrator at
`intelligent_orchestrator.py:5654` via `contracts/lab_control.py::write_final_opportunity_book`
[OBSERVED; the evidence run contains `intelligence_lab/final_opportunity_book_20260831_010309.csv`
and no `lab_signal_book_v3.csv`]. → CON-400.

The materializer is called only from `morning_handoff_finalizer.py:408-413`
[OBSERVED], i.e. the **morning** path. The evidence run is an EOD run and has no
`interpreter/` directory at all [OBSERVED — `ls data/output/runs/20260831_010309/`
returns no `interpreter`]. With `interpreter_resolver` true, every Interpreter
command therefore terminates at `EvidenceResolutionError("NO_ACCEPTED_INTERPRETER_HANDOFF")`
[OBSERVED `pipeline_interpreter/evidence_resolver.py:100`]. → CON-401.

---

## F1 — Interactive Interpreter core

### pipeline_interpreter/pipeline_interpreter.py
**Classification:** Interactive entry point / REPL launcher (69 lines).
**Real execution position:** POST-RUN / READ-PATH. Invoked by the operator as
`python pipeline_interpreter.py` (`pipeline_interpreter/start.bat`,
`pipeline_interpreter/morning.bat`). Not called by `intelligent_orchestrator.py`
at any of the 51 evening stages or the 3 morning stages [OBSERVED —
`03_execution_order.md` contains no Interpreter stage].
**Task in the process:** Prints a fixed banner, sets `sys.path` and a synthetic
`__path__` so the directory doubles as a package, runs `run_session_check()` once
at start-up, then loops on `input()` and forwards every line beginning with `/`
to `route_command`. It performs no data work of its own.
**Entry points:** `main()` (L38); `__main__` guard L68.
**Imports (production):** `pipeline_interpreter_commands.route_command`, `MENU`
(L46, deferred to inside `main`); `pipeline_interpreter_engine.run_session_check`
(L47). · **Imported by:** none at runtime; the name `pipeline_interpreter` is
also used as a package name by `pipeline_interpreter.ma_inputs_sync` imports
elsewhere, which is why `__path__` is forced at L13. · **Broken/retired imports:** NONE.
**Inputs** — *Files/tables read:* none directly. *Upstream fields consumed:* NONE.
*External calls:* `input()`, `sys.stdout.reconfigure` (L16, wrapped in
`try/except: pass` at L18-19). *Config/policy read:* NONE.
**Logic and algorithms** — Command REPL, `while True` at L49. No named algorithm.
*Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE — this module
never inspects direction.
**Computations and formulas (exact)** — NONE.
**Models** — NONE.
**Outputs** — Console only. No files. Atomic promotion: NOT_APPLICABLE.
Schema/version field: NONE. *Authority-claim fields:* the banner asserts
`EXECUTION PERMISSION: NONE — PIPELINE INTERPRETER ONLY` (L34) and on exit
`EXECUTION_PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY` (L59) — **HOLDS**: no
module in this lane writes an execution or capital permission into any governed
artefact; the only run-directory writes are additive assessment/overlay/sidecar
files (GAP-400, GAP-401, GAP-402).
**Handoff** — *Receives from:* operator keystrokes. *Hands to:*
`pipeline_interpreter_commands.route_command`. *Join keys:* none.
**Missing-data handling** — Bare `except Exception as e` at L65 prints
`⚠ Error: {e}` and continues the loop; a blocked handoff is therefore
indistinguishable from a typo at the prompt. §10-compliant? **N** — no §10 token
is emitted anywhere in this file.
**Contradictions found here:** CON-402 (partial — the banner "The machine
discovers. The narrative diagnoses." asserts advisory-only, contradicted
downstream in `pipeline_interpreter_commands.py`).
**Gaps found here:** GAP-410.
**Comment/docstring claims audited:**
- L2 "AVSHUNTER Pipeline Interpreter v1.0 — Interactive Entry Point" → **HOLDS** (L38-69).
- L8-12 "expose the directory as a package path … keeps governed imports such as
  `pipeline_interpreter.ma_inputs_sync` deterministic" → **PARTIAL**: `__path__`
  is set (L13) but only when this module is imported, not when
  `pipeline_interpreter_commands.py` is imported directly by its own sibling path
  insert at `pipeline_interpreter_commands.py:37-39`.
- L34 "EXECUTION PERMISSION: NONE" → **HOLDS**.
**Confidence in this section:** HIGH — 69 lines read in full.

---

### pipeline_interpreter/pipeline_interpreter_engine.py
**Classification:** Core engine — file discovery, session check, prompt builders,
LLM transport, response parsers (1,833 lines).
**Real execution position:** POST-RUN / READ-PATH. Invoked by
`pipeline_interpreter.py:47` (`run_session_check`) and by
`pipeline_interpreter_commands.py:49-60` (everything else).
**Task in the process:** Owns everything between the filesystem and the Anthropic
API. It resolves which CSVs count as "the pipeline output", loads them, formats
rows into prompt text, injects macro/news/lab/entry-timing blocks, calls the
model, and parses verdicts and `[TRADE_BRIEF_CSV]` back out of the response. It
also creates the whole `MA_Inputs/` tree on import (L43-44) and the
`MA_Inputs/lab_export` folder at L1823.
**Entry points:** `run_session_check` (L480); `read_pipeline_csv` (L430);
`find_pipeline_files` (L458); `scan_ma_inputs_for_ticker` (L1195);
`scan_ma_pipeline_outputs` (L1233); `classify_ma_input_csvs` (L1255);
`scan_all_ma_inputs` (L1281); `get_ma_inputs_status` (L1320); `call_api` (L377);
`load_image` (L295); `build_interpret_prompt` (L627);
`build_single_ticker_prompt` (L692); `build_triage_prompt` (L787);
`build_chart_prompt` (L997); `build_morning_validation_prompt` (L1104);
`build_intraday_prompt` (L1397); `build_story_prompt` (L1554);
`build_overnight_delta` (L1715); `extract_section` (L1133); `extract_verdict`
(L1137); `extract_interpreter_verdict` (L1161); `parse_brief_csv` (L1175);
`build_chart_evidence_block` (L65); `format_live_price_block` (L1373);
`format_live_data_for_prompt` (L15); `get_run_dir` (L1546).
**Imports (production):** `news_macro_readers` (L11-14) — `read_macro_context`,
`read_news_terminal_output`, `read_enrichment_delta`,
`read_all_news_macro_context`, `save_pasted_brief`; `msi_runtime.active_flags`
(L482, deferred); `evidence_resolver.handoff_status` (L484, deferred);
`anthropic` (L385, deferred); `PIL` (L320, deferred); `pandas` (L931, deferred).
· **Imported by:** `pipeline_interpreter.py:47`,
`pipeline_interpreter_commands.py:49-60`, `pipeline_interpreter_commands.py:1152`,
`:2245`, `:2399`. · **Broken/retired imports:** `read_macro_context` and
`read_enrichment_delta` are imported at L11-13 and **never called** anywhere in
this file [OBSERVED — no call site]; they remain live only as re-exports.
**Inputs**
- *Files/tables read:*
  - `pipeline_interpreter_system_prompt.txt` (L32, read at L239 on every API call).
  - `MA_Inputs/session_state.json` (L501, L796, L852) → `run_id`, `session_mode`,
    `macro_regime_now` / `current_regime` / `morning_macro_regime_state`.
  - `MA_Inputs/pipeline_outputs/lab_triage_view_*.csv`, `morning_candidates_*.csv`,
    `morning_validated_trades_*.csv` (L508-534).
  - `MA_Inputs/macro/macro_intelligence_latest.json` (L546, L864),
    `MA_Inputs/macro/avshunter_macro_enrichment_delta.json` (L553).
  - `MA_Inputs/news_terminal/newsroom_brief_latest.txt` (L557),
    `MA_Inputs/news_terminal/trader_notes.json` (L1591).
  - Any `*.csv` under `MA_Inputs/**` recursively (L1244, L1257).
  - Hard-coded absolute directories `…/AVSHUNTER_outputs`, `…/outputs`,
    `~/AVSHUNTER-Intelligence/outputs` (L462-464). → GAP-420.
  - `outputs/story_{TICKER}_*.html` (L1806-1810).
- *Upstream fields consumed (with fallback chains):* see the field register.
  The material chains are:
  - `_ois_val`: `ois_score` → `scs_score` → `composite_score` → `pipeline_score`
    → `0.0` (L810-818). Bridges **missing ← 0.0** (numeric ← absent).
  - `_get_scs_val`: `scs_score` → `priority_score` → `composite` → `0.0` (L835-841).
  - `_get_fld(row, "verdict", "execution_permission", "morning_execution_permission")`
    (L878, L908, L918-920). Bridges **verdict ← permission** (two different
    categorical vocabularies collapsed into one).
  - `_get_fld(row, "evening_direction", "direction", "canonical_direction")`
    (L906). Direction taken from whichever field is non-blank first.
  - `_get_fld(row, "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "evening_ev_predicted")`
    (L910).
  - `PIPELINE_FILE_KEYWORDS` (L163-182) names `options_intelligence`,
    `vanguard_signals`, `eil`/`execution_intelligence`, `superbrain`,
    `execution_v3_5`, `garch_forecasts`, `horizon_1_5d/6_10d/11_20d` — i.e. the
    raw pipeline artefacts, not the governed book. → CON-404.
- *External calls:* `anthropic.Anthropic(...).messages.create` (L387, L419) with
  optional server tool `web_search_20250305` (L416).
- *Config/policy read:* `ANTHROPIC_API_KEY` (L21); `PI_MAX_IMAGE_DIMENSION`,
  `PI_IMAGE_RESIZE_DIMENSION` (L314-315); `MSI_*` flags indirectly via
  `active_flags()` (L482).

**Logic and algorithms**
- **Session check state machine** (L480-568). Order: (1) if
  `active_flags().interpreter_resolver` → print `handoff_status()` and return
  `status == "READY"` (L483-494); (2) any exception → print
  `[MSI HANDOFF BLOCKED]` and **return False** (L495-497), so the legacy branch
  is unreachable on error; (3) otherwise fall through to the legacy MA_Inputs
  scan (L498-568).
- **Trusted-file ladder** (L508-537): `lab_triage_view_*.csv` (`trusted_lab`) →
  mode-dependent `primary` → `fallback` → any of the three patterns, newest by
  mtime. `status` is `TRUSTED_LAB` / `OK` / `!! STALE`; a stale file is still
  assigned to `SESSION["pipeline_csv"]` (L540) and used.
- **Macro staleness rule** (L548-551): `age_h = (now - mtime)/3600`; `OK` if
  `age_h < 14`, else `!! STALE`, and `all_ok=False`. Enrichment delta age is
  printed but never gates (L553-556). Newsroom brief threshold also 14 h (L559-560).
- **OIS pre-filter** (L820-824): `ois_filtered = [r for r in rows if _ois_val(r) >= 50]`;
  `rows_to_triage = ois_filtered if len(ois_filtered) >= 10 else pipeline_rows`.
  A universe with 9 qualifying names silently reverts to the unfiltered list.
- **Sector grouping** (L886-925): rows bucketed by
  `gics_sector` → `sector_name` → `sector` → `gics_sector_name` → `"UNKNOWN"`
  (L829-833), each bucket sorted by `_get_scs_val` descending.
- **Verdict counting** (L876-884): substring tests `"GO" in _vv`,
  `"FLAG" in _vv`, `"BLOCK" in _vv` against the concatenated
  verdict/permission string. Substring matching, not equality.
- **Verdict extraction** (L1137-1158): searches a 3,000-character window after
  the first occurrence of the ticker for the literal `FINAL VERDICT` plus any of
  `GO, ARMED, PROBE, WAIT, BLOCKED, MISDIAGNOSED`; falls back to a whole-response
  scan (L1155-1157); final default `"WAIT"` (L1158). Because membership is
  `v in window`, the token `GO` matches inside any word containing "GO"
  (for example `GOING`, `ALGO`), and `GO` is tested first in the list order at
  L1139. → GAP-408.
- *Decision branches (CALL / PUT / other-blank):* this module contains **no
  CALL/PUT branch at all**. `direction` is read as an opaque string at L906,
  L1775 and printed. `build_chart_evidence_block` L83-85 lists
  `direction`, `trade_direction`, `pipeline_direction` as display fields only.
  Consequently UNRESOLVED / STRANGLE / blank / NONE are all passed through
  verbatim to the prompt — no branch drops or mislabels them here. Recorded as
  handled-by-passthrough, not as a finding.

**Computations and formulas (exact)**
- `age_h = (datetime.now().timestamp() - mf[0].stat().st_mtime) / 3600` (L548) —
  hours, unbounded, no rounding; threshold `< 14` (L549).
- `age_h2` (L555), `age_h3` (L559) — same formula, thresholds none / `< 14`.
- `_ois_val(row) = float(first non-castable-free of ois_score, scs_score, composite_score, pipeline_score) else 0.0` (L811-818).
- `gap_vs_ks = ((price_float - kill_switch) / kill_switch) * 100` (L1741) —
  percent, no clamp; division guarded by `kill_switch > 0` at L1740.
- `ks_status = "BREACHED" if price_float >= kill_switch else "SAFE"` (L1742-1745).
  **This comparison is direction-blind**: for a PUT thesis a kill switch is
  breached on the *downside*, yet the same `>=` is applied. `direction` is read
  at L1775 but only used for display at L1786. → GAP-423.
- `gap_vs_probe = ((price_float - probe_trigger) / probe_trigger) * 100` (L1751);
  `TRIGGERED_OVERNIGHT` when `abs(gap_vs_probe) <= 0.5` (L1752-1754) — 0.5 %
  hard-coded tolerance, no source.
- `max_dim = min(int(env PI_MAX_IMAGE_DIMENSION or 2000), 2000)` (L314);
  `target_dim = min(int(env PI_IMAGE_RESIZE_DIMENSION or 1800), 1800)` (L315),
  clamped to `max_dim` at L316-317. JPEG quality 88 (L353), WebP quality 88
  method 6 (L356).
- Row truncation: values over 80 chars cut to 77 + `"..."` (L608-609);
  `_format_rows` default cap 15 rows (L598), 65 for triage (L824), 20 for morning
  validation (L1107); options text truncated to 800 (L644), 600 (L707), 500
  (L1021, L1428, L1580) characters; previous story HTML to 8,000 (L1646);
  governed live evidence JSON to 4,000 (L19).

**Models** — External LLM only, no local model.
- Name `claude-sonnet-4-6`, type LLM, role triage (L26).
- Name `claude-opus-4-6`, type LLM, role deep dive and default (L27-28).
- Parameters: `max_tokens` default 8000 (L29), overridden to 12000 for the story
  call (`pipeline_interpreter_commands.py:1165`); `system` = full
  `pipeline_interpreter_system_prompt.txt` (L410); no `temperature` is passed
  (L407-412), so the provider default applies. Note
  `pipeline_interpreter_commands.py:593` records `temperature=0.0` into the
  assessment record even though no temperature was sent. → CON-414.
- Calibration source claimed: none. Version tag: none — the model identifiers are
  string literals with no config binding.

**Outputs**
- Console text only from this module; artefact writing is delegated to
  `pipeline_interpreter_outputs.py`.
- `save_pasted_brief` is re-exported (L13) and writes
  `MA_Inputs/news_terminal/newsroom_brief_latest.txt`
  (`news_macro_readers.py:358`).
- Directory side effects on import: `outputs/`, `MA_Inputs/`, `MA_Inputs/charts`,
  `MA_Inputs/options_data`, `MA_Inputs/screenshots`, `MA_Inputs/pipeline_outputs`,
  `MA_Inputs/macro`, `MA_Inputs/news_terminal` (L43-44) and `MA_Inputs/lab_export`
  (L1823). Atomic promotion: NOT_APPLICABLE. Schema/version field: NONE.
- *Authority-claim fields:* `EXECUTION_PERMISSION = "NONE_PIPELINE_INTERPRETER_ONLY"`
  (L46) and `CAPITAL_PERMISSION = "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION"`
  (L47) are stamped into every parsed brief row at L1181-1189 — **PARTIAL**. The
  permission stamping itself holds, but the same loop writes the *capital
  permission string* into `live_validation_state`, `thesis_validity_state` and
  `validation_score` (L1183-1189). `validation_score` is a numeric field in the
  governed vocabulary; it receives the literal
  `CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION`. → CON-403.
- `_DISPLAY_LABEL_MAP` (L51-59) rewrites seven capital-lock codes into operator
  phrases. The docstring at L50 says "Applied in the display layer only —
  underlying field values are unchanged" → **PARTIAL**: it is applied inside
  `build_chart_evidence_block` (L136), `_format_rows` (L606),
  `build_single_ticker_prompt` (L702), `build_chart_prompt` (L1015),
  `build_intraday_prompt` (L1420) and `build_story_prompt` (L1572) — i.e. into
  the **prompt text the model reasons over**, not merely into a screen. The
  model therefore never sees `NO_LIVE_CAPITAL_EOD`; it sees
  `PENDING HUMAN REVIEW`. → CON-415.

**Handoff** — *Receives from:* `MA_Inputs/**` (legacy) or, via
`evidence_resolver`, the accepted handoff manifest.
*Hands to:* `pipeline_interpreter_commands.py` (all prompt builders and parsers),
`pipeline_interpreter_outputs.py` (via the command layer).
*Join keys:* `ticker` (upper-cased, `row.get("ticker")` / `row.get("underlying")`);
`run_id` from `session_state.json` matched by **substring containment** in the
filename (`pipeline_interpreter_commands.py:720` etc.), not by a parsed field.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| `MA_Inputs/pipeline_outputs` missing | `Pipeline output X DIR NOT FOUND`, `SESSION["pipeline_csv"]=None`, `all_ok=False` | L543-544 |
| no matching CSV | `X NOT FOUND` | L542 |
| macro JSON absent | `X NOT FOUND`, `all_ok=False` | L552 |
| macro JSON older than 14 h | `!! STALE`, `all_ok=False` | L549-551 |
| brief absent | `-- not pasted (run /brief)` | L561 |
| no pipeline row supplied to chart block | `status: unavailable / reason: no pipeline row was supplied` | L74-79 |
| no chart-specific fields populated | `status: no chart-specific fields were populated in this row` | L142 |
| price or kill switch absent | `UNKNOWN (price or kill_switch not in pipeline row)` | L1748 |
| probe trigger absent | `UNKNOWN` | L1758 |
| no verdict token found | `"WAIT"` | L1158 |
| no interpreter verdict found | `""` | L1173 |
| CSV parse failure | prints `⚠ CSV parse`, returns `[]` | L1191-1192 |
| any file read failure | prints `⚠ Could not read`, returns `[]` | L439-441 |
§10-compliant? **N** — the vocabulary used is
`NOT FOUND / STALE / UNKNOWN / unavailable / WAIT / ""`. None of the eight §10
tokens appears in this file. → GAP-410.

**Contradictions found here:** CON-403, CON-404, CON-414, CON-415.
**Gaps found here:** GAP-406, GAP-408, GAP-409, GAP-410, GAP-420, GAP-423, GAP-424.
**Comment/docstring claims audited:**
- L3 "Reads pipeline CSV outputs and produces Dr. Magnus Vale trade narratives" →
  **HOLDS**, and is itself the statement of the legacy discipline that CON-404 records.
- L16 `format_live_data_for_prompt` "Format already-governed evidence; never fetch
  from a provider here" → **HOLDS**: the function only serialises its argument (L19).
- L24-27 model-selection comment → **HOLDS** (`MODEL_TRIAGE` used at
  `pipeline_interpreter_commands.py:883`; `MODEL_DEEP_DIVE` at :1164, :1627, :2316, :2491).
- L50 "Applied in the display layer only — underlying field values are unchanged"
  → **PARTIAL** (CON-415).
- L69-71 `build_chart_evidence_block` "lets the interpreter run without manually
  captured chart screenshots … Images remain useful … no longer mandatory" →
  **HOLDS** (L732, L1453, L1676 build the block unconditionally).
- L296-300 `load_image` "Anthropic many-image requests reject any image with a
  dimension above 2000 px" → **PARTIAL**: the code enforces the cap (L314, L344,
  L366) but the 2000 px figure is a hard-coded literal with no cited source.
- L362 "Final guard: never emit a payload that can violate the many-image limit"
  → **HOLDS** for the Pillow branch (L363-371); the no-Pillow branch at
  L321-333 returns the original bytes after a header-only dimension read and
  raises only when `max(width,height) > max_dim` or dimensions are unreadable
  (L323-330) — no re-verification of the emitted payload. **PARTIAL**.
- L431 `read_pipeline_csv` "Read any pipeline CSV and return list of dicts" →
  **HOLDS**.
- L459 `find_pipeline_files` "Auto-detect pipeline output files in a directory"
  → **HOLDS**, against three hard-coded absolute paths (GAP-420).
- L590 `_select_fields` "fall back to all if none match" → **PARTIAL**: it falls
  back to the **first 20 columns**, not all (L595).
- L599 `_format_rows` "Limits tokens" → **HOLDS** (L603, L608-613).
- L807-809 "Prevents the 40-row cap from discarding high-quality signals … Falls
  back to all rows if fewer than 10 pass the filter" → **HOLDS** (L820-821).
- L1138 "Pipeline verdicts (machine layer) — checked first, used for session
  tracking" → **HOLDS** (L1142).
- L1182 "Fix v1.1: was a syntax error (tuple key assignment)" → **HOLDS** as a
  statement about the previous defect, but the replacement introduces CON-403.
- L1196-1198 `scan_ma_inputs_for_ticker` "Scan MA_Inputs folder for all files
  matching a ticker" → **PARTIAL**: matching is `ticker_upper in f.name.upper()`
  (L1210, L1217, L1228), so `C` matches every filename containing the letter C
  and `ALL` matches `SMALLCAP_*`. → GAP-424.
- L1213-1214 "CSV/JSON are text context; option screenshots are visual context
  and should travel with chart images" → **HOLDS** (L1219-1222).
- L1256 `classify_ma_input_csvs` "Classify every CSV under MA_Inputs as
  recognised pipeline or other/manual" → **HOLDS**.
- L1393 "NOTE: Live price supersedes EOD pipeline price for trigger/invalidation
  assessment" → **FALSE as an authority statement**: it is asserted in prompt
  text only (L1393); no code compares the live price to a trigger. The statement
  instructs the model to prefer an operator-typed number
  (`pipeline_interpreter_commands.py:1473`) over the governed EOD price. → CON-416.
- L763 / L1060 "The pipeline direction is FIXED and authoritative. Do not use
  search results to change direction." → **PARTIAL**: it is a prompt instruction
  with no code-side enforcement; nothing validates that the returned narrative
  preserved the direction.
- L1409-1410 `build_intraday_prompt` "Called by cmd_intraday" → **HOLDS**
  (`pipeline_interpreter_commands.py:1614`).
- L1566-1567 `build_story_prompt` "Mirrors build_intraday_prompt()
  context-gathering pattern" → **HOLDS**.
- L1798-1800 `get_latest_story_for_thesis` "Scan outputs/ for the most recent
  story_{ticker}_*.html by mtime" → **HOLDS** (L1806-1810).
- L1822 "Create lab_export folder on startup" → **HOLDS** (L1823).
**Confidence in this section:** HIGH — all 1,833 lines read.

**Defect of record — GAP-409.** `build_intraday_prompt` L1454-1461:
```
chart_source_instruction = (
    f"{chart_source_instruction}"
    if chart_images_present
    else ( "No manual chart screenshots are attached. …" )
)
```
`chart_source_instruction` is read on the right-hand side of its own first
assignment. When `chart_images_present` is true this raises
`UnboundLocalError` [OBSERVED `pipeline_interpreter_engine.py:1454-1461`].
`cmd_intraday` passes `chart_images_present=bool(all_images)`
[OBSERVED `pipeline_interpreter_commands.py:1621`], so `/intraday TICKER IMG…`
with any resolvable image fails before the API call.
INFERRED (basis: static read of the assignment; confidence HIGH) that every
`/intraday` invocation with at least one image aborts.
`NEEDS_MEASUREMENT:` run `python -c "import sys; sys.path.insert(0,'pipeline_interpreter'); from pipeline_interpreter_engine import build_intraday_prompt; build_intraday_prompt('X', {'ticker':'X'}, chart_images_present=True)"`
and record whether `UnboundLocalError` is raised.

---

### pipeline_interpreter/pipeline_interpreter_commands.py
**Classification:** Command router and per-command orchestration (2,594 lines).
The largest module in the lane and the sole decision layer.
**Real execution position:** POST-RUN / READ-PATH. Invoked by
`pipeline_interpreter.py:46,56` (`route_command`).
**Task in the process:** Implements every `/` command. For each command it
selects an input source, loads rows, assembles context blocks (lab
reconciliation, entry-timing probability, trader notes, sector notes, options
context), builds a prompt via the engine, calls the model, writes outputs, and
prints a console summary. In MSI mode it instead resolves a hash-verified
handoff and writes an assessment record and a Lab overlay record back into the
run directory.
**Entry points:** `route_command` (L2124) — the single dispatch. Commands:
`cmd_triage` (L626), `_msi_cmd_triage` (L458), `cmd_ticker` (L1028),
`_msi_cmd_ticker` (L534), `cmd_interpret` (L977), `cmd_morning` (L1021, retired),
`cmd_chart` (L1228), `cmd_live` (L1397, retired), `cmd_price` (L1423),
`cmd_intraday` (L1504), `cmd_sync` (L1640), `cmd_reset` (L1666),
`cmd_sector_note` (L1722), `cmd_notes_status` (L1750), `cmd_quick` (L1960),
`cmd_brief` (L1970), `cmd_note` (L2002), `cmd_status` (L2047), `cmd_auto` (L2057),
`cmd_load` (L2064), `cmd_options` (L2072), `cmd_macro` (L2079), `cmd_news` (L2085),
`cmd_story` (L2232), `cmd_update` (L2387), `cmd_lab` (L2538), `cmd_inputs` (L2).
**Imports (production):** `msi_runtime.active_flags` (L41);
`evidence_resolver` — `EvidenceResolutionError`, `IntendedUse`, `handoff_status`,
`resolve_interpreter_evidence`, `resolve_interpreter_run` (L42-48);
`pipeline_interpreter_engine` (L49-60); `ma_inputs_sync` (L61);
`news_macro_readers.save_pasted_brief` (L62); `pipeline_interpreter_outputs`
(L63); `interpreter_qa` (L65, guarded); and deferred:
`score_integrity_check` (L641), `lab_reconciliation` (L790, L1094, L2545),
`entry_timing_engine` (L859, L1119, L2211), `trade_brief_builder` (L946, L1217),
`assessment_contract` (L578), `contracts.lab_evidence_overlay` (L579),
`thesis_registry` (L1201, L2249, L2401), `pipeline_interpreter_outputs.write_story_outputs`
(L2248, L2400), `write_interpreter_sidecar` (L1179),
`write_all_outputs_with_junior` (L1153). · **Imported by:**
`pipeline_interpreter.py:46`. · **Broken/retired imports:**
`MA_PIPELINE_OUT` and `sync_show_status` imported at L61 are never used
[OBSERVED — no call site]; `_lab_monetisation_failure` (L185) is a dead gate that
always returns `""` (L187). → GAP-417.

**Inputs**
- *Files/tables read (MSI path):* only via `evidence_resolver` — the accepted
  `interpreter/handoff_manifest.json` and the four hash-checked artefacts it
  names. Discipline **HOLDS** on this path.
- *Files/tables read (legacy path):*
  - `MA_Inputs/session_state.json` (L239-242, L708-714, L1195-1199).
  - `MA_Inputs/lab_export/avshunter_signals_*.csv`, with fallback to
    `MA_Inputs/pipeline_outputs/lab_triage_view_*.csv` (L794, L2552-2554;
    fallback flagged at L842-845).
  - `MA_Inputs/news_terminal/trader_notes.json` (L1077, L1589, L1681, L2032).
  - Everything `scan_ma_pipeline_outputs()` finds under `MA_Inputs/**` (L155,
    L248, L690, L715).
  - **Direct globs into the run tree** (L1815-1838):
    `data/output/runs/<last 3 runs>/` ×
    `intelligence_lab/lab_triage_view_*.csv`,
    `morning_validation/morning_validated_trades_*.csv`,
    `morning_validation/morning_candidates_*.csv`,
    `options/vanguard_signals_enriched_*.csv`,
    `options/options_intelligence_*.csv`,
    `options/options_candidates_ranked.csv`,
    `execution/execution_v3_5_*.csv`,
    `superbrain/eil_enriched_*.csv`,
    `superbrain/superbrain_enriched_*.csv`,
    `vanguard/vanguard_signals.csv`,
    `discovery/discovery_candidates_ultimate_*.csv`.
    `final_opportunity_book_*.csv` is **absent from this list**. → CON-404, CON-417.
  - Option context CSVs re-read per ticker (L1908-1936, L1939-1956).
- *Upstream fields consumed (with fallback chains):* the material ones —
  - `direction()` L307-337: a 19-element chain across the morning row, the
    `morning_candidates` row and the `execution` row —
    `canonical_direction` → `resolved_direction` → `footprint_direction` →
    `direction` → `evening_direction` → `primary_direction` → (same six from
    `morning_candidates`) → (four from `execution`) → `selected_contract_side` →
    `mc.selected_contract_side` → `ex.intent`. Accepted tokens
    `CALL, PUT, LONG_CALL, LONG_PUT` (L331), plus `BUY_SETUP → CALL` (L333-334)
    and `SELL_SETUP → PUT` (L335-336); everything else → `"UNKNOWN"` (L337).
  - `score()` L342-344: `validation_score` → `pse_score` → `mc.pse_score` →
    `mc.composite_score` → `0` (**missing ← 0**).
  - `first(r.get("validation_score"), r.get("pse_score"), mc.get("pse_score"))`
    for the emitted `pipeline_score` (L408).
  - `first(r.get("horizon_bucket"), mc.get("horizon_bucket"), r.get("horizon"), "UNKNOWN")` (L410).
  - `first(eil.get("eil_v3_verdict"), eil.get("eil_label"), eil.get("final_verdict"), exe.get("eil_v3_verdict"), exe.get("final_verdict"))` (L361).
  - `first(garch.get("l3_iv_tailwind_score"), r.get("l3_iv_tailwind_score"), mc.get("l3_iv_tailwind_score"))` (L367) — legacy `l3_*` name.
  - `row.get("lab_rank") or row.get("priority_rank") or 999999` (L471).
  - `row.get("governed_direction") or row.get("final_direction", "")` (L503).
  - `row.get("priority_score") or row.get("composite_score", "")` (L504).
  - `lab_row.get("Lab_Verdict") or ...get("Verdict") or ...get("Exec_Category") or ...get("Morning_Permission")` (L813-819) — four different categorical
    vocabularies collapsed into one `lab_category`.
  - `eil_v3_verdict == "BLOCKED"` filter (L775-781) — a pre-governance EIL column.
- *External calls:* `call_api` (L572, L883, L1141, L1161, L1370, L1626, L1629,
  L2315, L2490) → Anthropic. No market-data provider: `/live` is retired
  (L1416-1420) and `/morning` is retired (L1022-1026).
- *Config/policy read:* `active_flags()` at L6, L148, L633, L1029, L1520, L1642,
  L2049, L2058, L2216, L2233, L2388. `_MORNING_ACTIONABLE` (L180),
  `_LAB_ACTIONABLE` (L181), `_MONETISABLE_EV_DECISIONS` (L182 — declared, never
  read), `_NON_LIVE` (L1057).

**Logic and algorithms**
- **`_classify_battlefield_candidate`** (L190-220) — the lane's only true rule
  set. Reads `live_validation_state`, `morning_execution_permission`,
  `contract_tradability_state`. Ladder, in order:
  1. `state ∈ {REJECTED, BLOCKED}` or `perm == "BLOCKED"` → `SKIP_TODAY`, sort key 4 (L197-198).
  2. `perm == "CONTRACT_REPAIR"` or `contract == "REPAIR_REQUIRED"` → `REVIEW_LATER`, 2 (L199-200).
  3. `state == "WAIT_RETEST"` or `perm == "WAIT"` → `REVIEW_LATER`, 2 (L201-202).
  4. `state == "CONFIRMED"` and `perm ∈ _MORNING_ACTIONABLE` → requires
     `reconciliation["run_id_match"] is True` (L206-207), ticker in
     `confirmed` (L212-213) and in `actionable` (L214-217); only then
     `DEEP_DIVE_NOW`, 0 (L218).
  5. else `WATCH_ONLY`, 3 (L220).
  Sorting: `keyed.sort(key=lambda i: (classify(...)[2], -score(...), ticker))` (L387).
- **`_build_battlefield_triage_response`** (L223-455) — deterministic morning
  triage. Guard: returns `""` unless `session_mode == "MORNING"` (L245-246) and
  unless the row set carries `live_validation_state` (L249-253). Joins five
  side files by ticker (L270-276) via `_load_keyed` (L255-268), which keeps the
  **first** row per ticker and silently swallows read errors (L262-263).
- **`_msi_cmd_triage`** (L458-531) — governed triage. Maps `final_action` to a
  triage verdict: `{BUY_NOW, BUY_SMALL} → DEEP_DIVE_NOW` (L492-494);
  `{CONTRACT_REPAIR, MANUAL_REVIEW} → REVIEW_LATER` (L495-496);
  `{BLOCK, SKIP} → SKIP_TODAY` (L497-498); else `WATCH_ONLY` (L499-500).
- **`_msi_cmd_ticker`** (L534-623) — governed deep dive: resolve evidence,
  build one prompt from the book row plus a JSON `governed_bundle` extract
  (L549-562), call the model with optional images, write outputs, build an
  assessment via `assessment_contract.build_assessment` (L587-594), append it to
  the run (L596), and if `VALID` append a Lab overlay record (L598-617).
- **`get_trusted_interpreter_source`** (L141-176) — legacy source ladder:
  MSI mode short-circuits to `("", "governed_manifest_only")` (L148-149); then
  explicit path (L151-153); then `lab_triage_view` → `morning_validated` →
  `morning_candidates` → `execution` → `eil` (L156-166); then any candidate
  path containing the ticker (L168-170); then the session CSV (L172-174); then
  `"unresolved"` (L176).
- **`cmd_triage`** (L626-974) — inventory print, source resolution, B2 BLOCKED
  filter (L775-781), lab reconciliation gate (L789-857), entry-timing block for
  the first 20 rows (L863-869), deterministic battlefield response or LLM triage
  (L873-883), output write (L886-892), console rendering, per-row trade brief
  for `DEEP_DIVE_NOW` rows only (L933-958), QA (L961-972).
- *Decision branches (CALL / PUT / other-blank):*
  - `direction()` L331-337 — **CALL and PUT are handled; `LONG_CALL`/`LONG_PUT`
    are normalised by stripping `LONG_` (L332); `BUY_SETUP`/`SELL_SETUP` are
    mapped (L333-336); every other token, including `UNRESOLVED`, `STRANGLE`,
    `NONE`, `BOTH` and blank, falls through to `"UNKNOWN"` (L337)**. A multi-leg
    structure is therefore reported as `UNKNOWN`, indistinguishable from a
    missing direction. → GAP-405.
  - L503 `row.get("governed_direction") or row.get("final_direction", "")` — no
    token inspection at all; whatever string the book carries is emitted,
    including blank.
  - L2324 `str(row.get("direction", "UNKNOWN"))` — thesis registry direction;
    no CALL/PUT branch.
  - L954 `brief.get("direction", "?")` — display only.
  There is **no `if direction != "PUT"`-shaped branch anywhere in this file**
  [OBSERVED — exhaustive read]. The finding is the opposite shape: a
  many-source coalescing chain that erases every non-CALL/PUT token.

**Computations and formulas (exact)**
- `num(v) = float(v if v not in (None,"") else 0)`, `except: 0.0` (L291-295) —
  **missing ← 0.0**, and a malformed number is also 0.0.
- `score(ticker, r) = num(first(validation_score, pse_score, mc.pse_score, mc.composite_score, 0))` (L342-344).
- `keyed.sort(key=(classify_rank, -score, ticker))` (L387) — ascending rank,
  descending score, alphabetical tie-break.
- `triage_rank = enumerate(rows, 1)` (L490) — rank is positional after
  `int(float(lab_rank or priority_rank or 999999))` sorting (L471-474).
- `ma_ready = "YES" if ticker in chart_tickers and ticker in option_tickers else ("PARTIAL" if either else "NO")` (L403).
- `_msi_cmd_triage` sets `"ma_ready": "YES"` unconditionally (L507) — the same
  field, computed in one path and asserted in the other. → CON-412.
- `prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()` (L592).
- `kill_switch_level = float(str(row.get("kill_switch_level", 0) or 0).replace("$",""))` (L2328);
  `probe_trigger` (L2329), `armed_trigger` (L2330) — same shape. **missing ← 0.0**,
  and a `0.0` kill switch is later treated as "UNKNOWN" by
  `pipeline_interpreter_engine.py:1740`, so the zero is not silently believed
  there — but it *is* persisted as `0.0` in the thesis registry. → GAP-425.
- `_blocked_in_triage = sum(1 for r in rows if str(r.get("eil_v3_verdict","")).upper() == "BLOCKED")` (L776-778).
- `elapsed = int(time.time() - t0)` (L894, L1212, L1381, L1635, L2377, L2525) — seconds.

**Models** — No local model. Two LLM call profiles:
`MODEL_TRIAGE` for `/triage` (L883), `MODEL_DEEP_DIVE` at `max_tokens=12000` for
the story pass (L1164-1165) and at the engine default 8000 elsewhere.
`temperature=0.0` is recorded into the assessment (L593) but never sent
(`pipeline_interpreter_engine.py:407-412`). → CON-414.
Calibration source claimed: none. Version tag: `prompt_version="msi-interpreter-prompt-v1.1"` (L591).

**Outputs**
| Written | Path | Line | Atomic? | Schema field? |
|---|---|---|---|---|
| Interpreter HTML/CSV | `pipeline_interpreter/outputs/<ts>/…` via `write_all_outputs` / `write_triage_outputs` / `write_story_outputs` / `write_all_outputs_with_junior` | L525, L574, L886, L1016, L1147, L1167, L1372, L1632, L2339, L2496 | see `pipeline_interpreter_outputs.py` section | see that section |
| **Assessment record** | `<run_root>/interpreter/assessments.jsonl` (append) | **L596** | append, not atomic | `assessment_status`, `authority_statement` |
| **Lab evidence overlay** | `<run_root>/intelligence_lab/lab_evidence_overlay_v1.jsonl` (append) | **L616** | append, not atomic | `source="interpreter_assessment_v1"` |
| **Interpreter sidecar** | `data/output/runs/{run_id}/interpreter/{run_id}_{TICKER}_interpreter.json` | **L1181** (writer in `pipeline_interpreter_outputs.py`) | see that section | — |
| Trader notes | `MA_Inputs/news_terminal/trader_notes.json` (full rewrite) | L2040 | **no** — `write_text` over the live file | none |
| Newsroom brief | `MA_Inputs/news_terminal/newsroom_brief_latest.txt` | L1995 → `news_macro_readers.py:358` | no | none |
| Evening baseline | `MA_Inputs/thesis_baselines/{TICKER}_evening_baseline.json` | L1203 → `thesis_registry.save_evening_baseline` | see that section | — |
| MA_Inputs copies | `MA_Inputs/{pipeline_outputs,options_data,charts,screenshots,raw_inputs}/` | L1652 → `ma_inputs_sync.sync_to_ma_inputs` | no | none |

Three of these write **into `data/output/runs/**`** from a read path:
L596, L616 and L1181. L616 writes into the **Lab's own** output directory, which
Lane B owns. → GAP-400, GAP-401, GAP-402.

*Authority-claim fields:*
- `"execution_permission": "NONE_PIPELINE_INTERPRETER_ONLY"` written into every
  MSI triage row (L512) and printed at L138, L929, L2053 — **HOLDS**.
- `interpreter_authority_statement` / `interpreter_assessment_status` in the
  overlay (L611-612) — **PARTIAL**: the statement is carried, but the overlay is
  appended into the governed Lab directory with no manifest entry and no hash,
  so nothing downstream can distinguish it from a Lab-authored artefact
  (GAP-401).
- `"why": f"Governed final_action={action or 'MISSING'}"` (L510) — **HOLDS**:
  the absence is surfaced as the literal `MISSING`.

**Handoff** — *Receives from:* `evidence_resolver.ResolvedInterpreterEvidence`
(MSI) or raw CSVs (legacy); `lab_reconciliation` for the Lab universe;
`entry_timing_engine` for the probability block; `thesis_registry` for the
carried-forward thesis. *Hands to:* `pipeline_interpreter_engine` prompt
builders; `pipeline_interpreter_outputs` writers; `assessment_contract` and
`contracts.lab_evidence_overlay` for run-directory records; `thesis_registry`
for state. *Join keys:* `ticker` upper-cased throughout; `bundle_id` (L600,
L620); `run_id` (L541-543); `thesis_id` (L2293, L2322).

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| No accepted handoff | `[MSI BLOCKED] {error}` and `return None` | L466-467, L539-540 |
| Ticker absent from handoff | `[MSI BLOCKED] {ticker}: TICKER_NOT_IN_ACCEPTED_HANDOFF` | L539-540 |
| `final_action` blank | `Governed final_action=MISSING`, verdict `WATCH_ONLY` | L500, L510 |
| No lab export | `LAB_ALIGNMENT: No lab export found in MA_Inputs/lab_export/` | L852 |
| Lab run_id mismatch | prints `STALE_LAB_DATA`, **proceeds** | L832-835 |
| Lab fallback file used | prints three `⚠` lines, **proceeds** | L842-845 |
| Ticker not in Lab export | `LAB_NOT_CONFIRMED` | L1111 |
| Ticker not actionable in Lab | `LAB_NOT_ACTIONABLE: {failure}` / `LAB_RETAINED_REPAIR_OR_CAUTION` | L216-217 |
| No Lab run match | `LAB_AUTHORITY_INVALID: missing or mismatched Lab run` | L207 |
| Ticker not in CSV (`/ticker`) | `⚠ Ticker {t} not found`, returns | L1054-1056 |
| Ticker not in CSV (`/intraday`) | synthesises `row = {"ticker": t, "note": "Not found in pipeline CSV — live price analysis only"}` | L1578 |
| `execution_permission ∈ _NON_LIVE` | `[NOTE] execution_permission={p} -- analysis proceeds` | L1057-1060 |
| No live price | three console lines, continues on EOD price | L1601-1604 |
| Score-integrity check raises | `except Exception: pass` | L656-657 |
| Sidecar write raises | `⚠ Sidecar write skipped` | L1190-1191 |
| Baseline save raises | `⚠ Baseline save skipped` | L1206-1207 |
| Junior briefing raises | `⚠ Junior Briefing merge skipped` | L1208-1209 |
| Thesis registry raises | `[THESIS] Registry create error` then `thesis_id = f"{ticker}_STORY_{ts}"` | L2333-2335 |
| Any CSV read failure in `_load_keyed` | `return {}` | L262-263 |
§10-compliant? **N** — the emitted vocabulary is
`BLOCKED / MISSING / LAB_NOT_CONFIRMED / LAB_NOT_ACTIONABLE / LAB_AUTHORITY_INVALID /
STALE_LAB_DATA / UNKNOWN / WATCH_ONLY`. `CONTRACT_REPAIR` is read as an input
token (L199) but is never emitted as a state. No §10 token is written. → GAP-410.

**Contradictions found here:** CON-400, CON-401, CON-402, CON-404, CON-411,
CON-412, CON-414, CON-417, CON-418.
**Gaps found here:** GAP-400, GAP-401, GAP-402, GAP-405, GAP-406, GAP-407,
GAP-410, GAP-416, GAP-417, GAP-419, GAP-421, GAP-425, GAP-426.
**Comment/docstring claims audited:**
- L142-147 `get_trusted_interpreter_source` "Intelligence Lab's resolved triage
  view is the master queue. Explicit user files still win, but normal interpreter
  commands should not drift back to stale session CSVs when a Lab view is
  available." → **PARTIAL**: the ladder does prefer `lab_triage_view` (L157), but
  L168-170 then admits `_candidate_pipeline_csv_paths()`, which includes
  `options_intelligence`, `eil_enriched`, `execution_v3_5`, `vanguard_signals`
  and `discovery_candidates_ultimate` from the **last three runs** (L1816-1834);
  and L172-174 still falls back to `SESSION["last_pipeline_csv"]`, the stale
  session CSV the comment disclaims.
- L186 `_lab_monetisation_failure` "Legacy compatibility hook; EV/R:R are not
  Interpreter authorities." → **HOLDS as written** (returns `""`, L187), but the
  function is called at L825 inside the actionable-set construction, so the
  monetisation gate it names is unconditionally open. → GAP-417.
- L191 `_classify_battlefield_candidate` "Apply the production authority
  contract: morning gate AND Lab approval." → **HOLDS** (L197-220): both
  authorities are required for `DEEP_DIVE_NOW`.
- L196 "Morning vetoes remain sovereign even when the Lab selected the ticker."
  → **HOLDS** (L197-202 precede the Lab checks at L204-217).
- L229-232 "Morning validator is the live gate. Other prepared outputs are
  consumed as context, but cannot override direction, permission, or
  repair/block status." → **PARTIAL**: permission and repair/block are read only
  from the morning row (L192-194) so those hold; **direction does not** —
  `direction()` L307-337 accepts a direction from the `morning_candidates` and
  `execution` side files whenever the morning row's six direction fields are all
  blank. That is an override by absence. → CON-418.
- L288-289 (`_bundle` docstring in the materializer, cross-referenced) — see that section.
- L432 "Chart and options files improve review completeness only; they cannot
  promote a repair, wait, blocked, or rejected ticker." → **HOLDS**:
  `chart_tickers`/`option_tickers` feed only `ma_inputs_ready` (L403) and
  `reason_context` (L370-373); they are absent from `_classify_battlefield_candidate`.
- L459 `_msi_cmd_triage` "Deterministic triage over one accepted, hash-verified
  handoff." → **HOLDS**: `resolve_interpreter_run` (L464) validates every
  artefact hash (`contracts/interpreter_handoff.py:284-285`) and no LLM is called.
- L535 `_msi_cmd_ticker` "One prompt contract for structured evidence, with
  optional images only." → **HOLDS** (L563-572).
- L570-571 "Images are supplemental inputs to the same prompt; they never select
  a different numerical or authority path." → **HOLDS**: `images` only reaches
  `call_api` (L572); `chart_images_present` only switches an instruction string
  (`pipeline_interpreter_engine.py:733-737`). Screenshot evidence cannot
  override the governed bundle on this path.
- L628-630 `cmd_triage` "Fast triage pass … No deep dive. One API call." →
  **PARTIAL**: zero API calls when the deterministic battlefield response is
  produced (L873-880); one otherwise (L883).
- L657 "integrity check is informational — never blocks triage" → **HOLDS**
  (`except Exception: pass`, L656-657). → GAP-421.
- L773-774 "B2 FIX: Filter BLOCKED tickers from triage session. These should not
  have reached morning_candidates but filter defensively" → **HOLDS** (L775-781),
  and is itself evidence that a pre-governance EIL column (`eil_v3_verdict`) is
  the live gate rather than the governed `final_action`.
- L931-932 "One-line brief only for the jointly approved production universe. The
  former raw rows loop could print GO for LAB_NOT_CONFIRMED names." → **HOLDS**
  (L933-940 re-classifies before printing).
- L1127-1128 "Direction and contract are upstream authorities. The Interpreter
  may disclose conflicts but never reruns a resolver or selects an alternative."
  → **PARTIAL**: true on the `/ticker` path itself (no resolver call), **false**
  for the `/triage` path, where `direction()` L307-337 re-derives a direction by
  coalescing 19 candidate fields across three files. → CON-418.
- L1641 `cmd_sync` "copy AVSHUNTER pipeline outputs into MA_Inputs/pipeline_outputs/"
  → **PARTIAL**: `sync_to_ma_inputs` routes to five destination folders, not one
  (`ma_inputs_sync.py:66-124`).
- L1667 `cmd_reset` "Clear in-memory interpreter state without changing the
  prepared run marker." → **HOLDS** (L1669-1674 touch only memory and `SESSION`).
- L1790-1796 `_candidate_pipeline_csv_paths` "Last-3-run rule: a trade can remain
  analytically valid even if it dropped out of the newest morning/EOD manifest …
  MA_Inputs is then added as trader-supplied context, not treated as inferior
  data" → **FALSE as an authority statement**. The code implements exactly what
  it describes (L1829-1843), and that is the defect: a row selected from a
  **two-run-old** `options_intelligence_*.csv` or `discovery_candidates_ultimate_*.csv`
  is fed to the deep dive with no run-identity check and no staleness marker.
  Rows from different runs can be mixed within a single `/ticker` prompt, because
  `_load_option_context_for_ticker` (L1939-1956) accumulates up to six files
  drawn from the same three-run window. → CON-417, GAP-426.
- L1940-1945 `_load_option_context_for_ticker` "This is additive context for the
  deep dive. It intentionally combines the selected pipeline row, last-3-run
  options outputs, and MA_Inputs option CSVs" → **HOLDS**, and states GAP-426 plainly.
- L1961 `cmd_quick` "run deep dive directly from prepared MA_Inputs files" →
  **PARTIAL**: it delegates to `cmd_ticker` (L1967), which resolves through
  `get_trusted_interpreter_source` and can therefore read the run tree, not only
  MA_Inputs.
- L2048 `cmd_status` "Show governed baton integrity plus non-authoritative
  session state." → **PARTIAL**: in legacy mode it prints only
  `{"status": "LEGACY_MODE", "run_id": …}` (L2049-2051); no baton integrity is
  shown and no warning distinguishes "no baton" from "baton not checked".
- L2540-2543 `cmd_lab` "/lab [FILE] … If FILE not specified, scans
  MA_Inputs/lab_export/" → **FALSE**: when `FILE` **is** specified the code calls
  `load_lab_export(Path(path).parent)` (L2552) — it discards the filename and
  loads whatever `load_lab_export` selects from that directory. A named file is
  not honoured. → GAP-416.
- L2239-2243 (`cmd_story`) and L2394-2397 (`cmd_update`): the string literal is
  placed **after** the MSI early-return block (L2233-2238 / L2388-2393), so it is
  a no-op expression statement, not a docstring. `cmd_story.__doc__` and
  `cmd_update.__doc__` are `None`. The `/menu` text at L2114-2115 is the only
  surviving description. → CON-411.
- L2494 "Write versioned outputs (never overwrite)" → deferred to
  `pipeline_interpreter_outputs.write_story_outputs`; see that section.
**Confidence in this section:** HIGH — all 2,594 lines read.

---

### pipeline_interpreter/ma_inputs_sync.py
**Classification:** Filesystem copier — pipeline artefacts → `MA_Inputs/` (391 lines).
Classified `ORCHESTRATED` in `_tooling/lane_F_lab_interpreter.txt:15`.
**Real execution position:** POST-RUN / READ-PATH. Invoked by
`pipeline_interpreter_commands.py:1648-1652` (`/sync`) and by
`pipeline_interpreter_commands.py:61` (import). Also a standalone CLI
(`__main__`, L366). `on_pipeline_complete` (L313) is the documented
orchestrator hook but has **no caller in the repository**
[OBSERVED — no reference outside this file]. → GAP-427.
**Task in the process:** Scans a fixed list of source directories (or an explicit
`--path`), matches each file against five keyword/extension routing rules, and
`shutil.copy2`s matches into one of five `MA_Inputs/` subfolders. It is the
mechanism by which raw pipeline artefacts become Interpreter inputs in legacy mode.
**Entry points:** `sync_file` (L186); `sync_to_ma_inputs` (L211);
`add_source_path` (L305); `on_pipeline_complete` (L313); `show_status` (L328);
`watch_and_sync` (L352); `__main__` (L366).
**Imports (production):** `argparse`, `shutil`, `time`, `datetime`, `pathlib`,
`typing` only — no project imports. · **Imported by:**
`pipeline_interpreter_commands.py:61` and `:1648`. · **Broken/retired imports:**
NONE. The module docstring (L17-23) names the file
`ma_inputs_sync_v1_1_FIXED.py`, which does not exist; the actual name is
`ma_inputs_sync.py`. → GAP-428.

**Inputs**
- *Files/tables read:* the 16 directories in `AVSHUNTER_OUTPUT_DIRS` (L45-64),
  filtered to those that exist (L233) and are not inside `MA_Inputs` (L236).
  The list includes **`BASE_USER / "data" / "output" / "runs"`** (L62) and, with
  `recursive=True` (the default, L215; `--recursive` default True, L375), the
  glob is `**/*` (L178). Every artefact of every run in the tree is therefore a
  candidate. It also includes `BASE_USER / "dropbox" / "macro"` (L63).
- *Upstream fields consumed:* NONE — this module never opens a file's contents.
  Routing is by **filename substring only** (L142-146).
- *External calls:* `shutil.copy2` (L201, L278) — copies content plus mtime.
- *Config/policy read:* CLI arguments only (L367-378). `BASE_USER` is a
  hard-coded absolute path (L33). → GAP-420.

**Logic and algorithms**
- **Routing rule set** `FILE_ROUTING` (L66-124), five rules evaluated in order
  (L150-153), first match wins:
  1. `pipeline_output` → `MA_Inputs/pipeline_outputs`, extensions
     `.csv .json .parquet .xlsx`, 57 keywords (L72-86) including
     `final_opportunity_book`, `lab_triage_view`, `options_intelligence`,
     `vanguard_signals`, `superbrain`, `eil`, `execution_v`, `garch`,
     `discovery`, `candidate`, `candidates`, `watchlist`.
  2. `options_data` → `MA_Inputs/options_data` (L88-99).
  3. `chart` → `MA_Inputs/charts`, image extensions, keywords including the bare
     tokens `daily`, `weekly`, `monthly`, `1h`, `15m`, `5m` (L104-107).
  4. `screenshot` → `MA_Inputs/screenshots` (L109-117).
  5. `raw_input` → `MA_Inputs/raw_inputs`, keywords `input`, `upload`, `source`,
     `raw` (L119-123).
  Rule 1 and rule 2 share the same four extensions; because rule 1 is first and
  its keyword list contains `options_intelligence`, an
  `options_intelligence_*.csv` is routed to `pipeline_outputs`, not
  `options_data` (L150-152). [OBSERVED]
- **Freshness filter** `_is_fresh` (L156-164): `age_seconds = time.time() - mtime`;
  fresh if `age_seconds <= max_age_hours * 3600`; **`max_age_hours <= 0` returns
  True unconditionally** (L158-159), which is what `--all-hours` (L373, L380) and
  the documented `max_age_hours=0` pipeline call (L23) select.
- **Duplicate suppression** `_already_synced` (L167-174):
  `src.stat().st_size == dest.stat().st_size and abs(src.st_mtime - dest.st_mtime) < 2`.
  **Content is never hashed.** Two different files of identical byte length whose
  mtimes are within 2 s are treated as the same file and the copy is skipped
  (L194-197, L272-274). → GAP-403.
- **Loop guard** (L235-236): destination folders are excluded from the source
  list via `_is_inside` (L133-138).
- *Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE — this module
  has no notion of direction.

**Computations and formulas (exact)**
- `age_seconds = time.time() - filepath.stat().st_mtime` (L161) — seconds.
- fresh iff `age_seconds <= max_age_hours * 3600` (L162) — no rounding, no clamp;
  `max_age_hours <= 0` short-circuits to True (L158).
- `same iff size_equal and abs(Δmtime) < 2` (L172) — 2-second window, hard-coded.
- `total = sum(counts[k] for k in [pipeline_output, options_data, chart, screenshot, raw_input])` (L287, L321, L359).

**Models** — NONE.

**Outputs**
- Files copied to `MA_Inputs/pipeline_outputs`, `…/options_data`, `…/charts`,
  `…/screenshots`, `…/raw_inputs` (L38-42, L201, L278). Destination filename is
  `dest_dir / src.name` — **flat, with no run-id namespacing** (L201, L278).
  Artefacts from different runs that share a filename overwrite one another
  silently; `vanguard/vanguard_signals.csv` has no timestamp in its name at all
  [OBSERVED — evidence run]. → GAP-404.
- Atomic promotion: **no** — `shutil.copy2` writes the destination in place
  (L201, L278). A concurrent Interpreter read of a partially-written CSV is
  possible.
- Schema/version field: NONE. No manifest, no provenance record, no hash.
- *Authority-claim fields:* NONE.
- **Does it write into `data/output/runs/**`?** **No.** All destinations are
  under `MA_INPUTS_BASE = Path(__file__).resolve().parent / "MA_Inputs"` (L36-42).
  The run tree is read-only to this module, and `_is_inside` (L236) only prevents
  reading *from* `MA_Inputs`, never writing *to* the run tree. Verified: the only
  write calls are `mkdir` (L200, L277) and `copy2` (L201, L278), both bounded by
  `dest_dir` values derived exclusively from L38-42. **It copies; it does not
  mutate; and it does not write back into the run directory.** [OBSERVED]

**Handoff** — *Receives from:* the run tree, `dropbox/macro/`, `input/`.
*Hands to:* `pipeline_interpreter_engine.scan_ma_pipeline_outputs` and
`classify_ma_input_csvs`, which re-discover the copies by the same keyword
vocabulary. *Join keys:* filename substring only. No run_id, no ticker, no hash.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| No routing keyword matched | `UNMATCHED {name} — no routing keyword matched`, `counts["unmatched"] += 1` | L191, L267-269 |
| Already synced | `SKIPPED already synced` / `counts["skipped_synced"] += 1` | L196, L273 |
| Too old | `counts["skipped_stale"] += 1`, silent | L261-262 |
| Copy `OSError` | `ERROR copying {name}: {exc}`, `counts["errors"] += 1` | L205-208, L282-285 |
| Directory unscannable | `Cannot scan {dir}: {exc}` | L256-257 |
| No source dirs | `No source directories found.` | L240-241 |
| `stat()` fails in `_is_fresh` | returns **False** (treated as stale) | L163-164 |
| `stat()` fails in `_already_synced` | returns **False** (treated as not synced → copied) | L173-174 |
§10-compliant? **N** — vocabulary is `UNMATCHED / SKIPPED / ERROR`. No §10 token.

**Contradictions found here:** CON-408.
**Gaps found here:** GAP-403, GAP-404, GAP-420, GAP-427, GAP-428.
**Comment/docstring claims audited:**
- L4-6 "Sync AVSHUNTER outputs and /input-style folders into MA_Inputs so the
  interpreter can consume the latest pipeline files." → **HOLDS**, and is the
  plainest statement of the legacy discipline that CON-404/CON-408 record.
- L9 "Adds input/source folder discovery." → **HOLDS** (L45-64).
- L10 "Supports recursive scanning." → **HOLDS** (L177-183, default True L215).
- L11 "Scans .json and .webp as well as CSV/images." → **HOLDS** (L70, L103, L121).
- L12 "Adds macro/catalyst/calendar routing keywords." → **PARTIAL**: `macro_*`
  and `catalyst*` keywords exist (L77-79); **no `calendar` keyword exists** —
  `catalyst_calendar` (L77) matches only because it contains `catalyst`, and a
  file named `auction_calendar.csv` matches no rule and is reported `UNMATCHED`.
- L13 "Allows force sync with --all-hours or --hours 0." → **HOLDS** (L158, L373, L380).
- L14 "Adds clearer diagnostics for unmatched and stale files." → **PARTIAL**:
  unmatched files are named (L191, L269); **stale files are counted but never
  named** (L261-262).
- L17-19 usage block naming `ma_inputs_sync_v1_1_FIXED.py` → **FALSE** (GAP-428).
- L21-23 "Pipeline usage: from ma_inputs_sync_v1_1_FIXED import sync_to_ma_inputs;
  sync_to_ma_inputs(source_dir=str(output_dir), recursive=True, max_age_hours=0)"
  → **FALSE**: no such call exists in the pipeline. `on_pipeline_complete` (L313),
  the function that would implement it, has no caller. → GAP-427.
- L35 "Put MA_Inputs beside this script. Keep this file inside the AVSHUNTER
  project root." → **PARTIAL**: the file is in `pipeline_interpreter/`, not the
  project root; `MA_INPUTS_BASE` follows the file (L36-37) so behaviour is
  correct, but `BASE_USER` (L33) is an unrelated hard-coded absolute path.
- L44 "Known folders the script should check when --path is not supplied." → **HOLDS**.
- L235 "Do not re-scan destination folders as sources; this causes noise and
  loops." → **HOLDS** (L236).
**Confidence in this section:** HIGH — all 391 lines read; write-target analysis
is exhaustive (two `copy2` and two `mkdir` call sites).

---

### pipeline_interpreter/news_macro_readers.py
**Classification:** Macro / enrichment-delta / news reader and prompt-block
formatter (361 lines).
**Real execution position:** POST-RUN / READ-PATH. Invoked by
`pipeline_interpreter_engine.py:11-14` (import) and called at
`pipeline_interpreter_engine.py:650, 717, 802, 1028, 1438, 1610`
(`read_all_news_macro_context`) and `pipeline_interpreter_commands.py:1995`
(`save_pasted_brief`).
**Task in the process:** Supplies the `MACRO + ENRICHMENT DELTA + NEWS` block
that every Interpreter prompt carries. In the current code it forwards a
governed macro string it is given and adds a news/brief block it reads itself;
its two macro readers remain fully implemented but are no longer wired into the
combined builder.
**Entry points:** `read_macro_context` (L24); `read_enrichment_delta` (L104);
`read_news_terminal_output` (L196); `read_all_news_macro_context` (L292);
`_resolve_path` (L323); `save_pasted_brief` (L350).
**Imports (production):** `json`, `csv`, `os`, `pathlib`, `datetime` only.
· **Imported by:** `pipeline_interpreter_engine.py:11`,
`pipeline_interpreter_commands.py:62`. · **Broken/retired imports:** `os` is
imported at L10 and never used [OBSERVED].

**Inputs**
- *Files/tables read:*
  - `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro\macro_intelligence_latest.json` (L15-16) — hard-coded absolute.
  - `…\dropbox\macro\avshunter_macro_enrichment_delta.json` (L17) — hard-coded absolute.
  - `pipeline_interpreter/MA_Inputs/news_terminal/newsroom_brief_latest.txt` (L20).
  - Any `*.json`/`*.txt` in a supplied `ma_macro_dir`; any `*.csv`/`*.json`/`*.txt`
    in a supplied `ma_news_dir` (L334-341).
- *Upstream fields consumed (with fallback chains):*
  - Macro contract, 20 top-level fields (L51-72): `contract_version`,
    `regime_state`, `dir_bias`, `vol_mode`, `risk_on_off_switch`,
    `macro_conviction`, `macro_filter`, `liquidity_pulse`, `regime_drift_status`,
    `vix_spot`, `sector_tilt`, `size_multiplier`, `trigger_required`,
    `trend_energy`, `usd_state`, `rates_impulse`, `notes`, `report_date`,
    `as_of_utc`, `rotation_override`; plus five `extras.*` fields (L75-80).
  - Enrichment delta: `batch_id`, `report_date`, `source` each with default
    `'UNKNOWN'` (L135-137); `narrative_overlay.overlay_summary`,
    `.base_macro_alignment` (L141-147); nine `macro_json_merge_block` keys
    (L151-155); `theme_deltas[]` and `event_guard_deltas[]`.
  - **Schema fallback chains** (the file names them as such):
    `t.get("directional_pressure", t.get("options_bias", t.get("macro_bias","")))`
    (L171) — v1.2 → older → older, bridging three different bias vocabularies;
    `t.get("beneficiary_universe", t.get("primary_tickers", t.get("tickers",[])))`
    (L173); `g.get("event_id", g.get("guard_id","?"))` (L184);
    `g.get("event_name", g.get("description",""))` (L185).
  - News CSV, 15 columns (L265-271) including `anis_total_score`, `fips_score`,
    `confidence_score`, `missing_data`.
- *External calls:* NONE — filesystem only.
- *Config/policy read:* NONE.

**Logic and algorithms**
- **`_resolve_path` precedence** (L323-346): explicit argument → newest by mtime
  in `search_dir` (optionally filtered by `filename_hint`, with
  `or candidates` restoring the unfiltered list if the hint matches nothing,
  L339) → hard-coded absolute path → `None`. Selection is by **mtime only**,
  with no run-id and no as-of check. → GAP-411.
- **News precedence** (L212-234): the pasted brief file is checked **first and
  unconditionally**, before any resolved path; if it is non-empty it is returned
  and no CSV or JSON is read at all (L232). A brief pasted days earlier therefore
  wins over a fresh news CSV; no age check exists in this function (the 14-hour
  check at `pipeline_interpreter_engine.py:559-560` is print-only).
- **Ticker filter** (L217-231): line-level substring match `ticker_upper in l.upper()`;
  L223-228 is a redundant `any(... for v in [l])` that re-tests the same line.
  For CSV rows (L254-263) the filter is
  `t in row["ticker"].upper() or t in row["narrative"].upper()`; if nothing
  matches, `rows = rows[:5]` — **the first five unrelated rows are returned in
  place of a "no news" state** (L261). → GAP-429.
- *Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE — no direction
  logic. `directional_bias` (L268) and `directional_pressure` (L171) are copied
  as opaque strings.

**Computations and formulas (exact)**
- Truncations only: `str(val)[:300]` (L87, L95, L147), `[:400]` (L142),
  `[:200]` (L161), `[:100]` (L146), `[:120]` (L185), `[:80]` (L276),
  `[:8]` tickers (L175), `[:3]` alignments (L146), `[:4]` guards (L182),
  `[:6]` news rows (L274), `[:8]` themes (L167), `[:20]` brief lines (L231),
  `[:3000]` brief (L232), `[:2000]` macro/news text (L97, L284).
- `stamped = f"[Pasted: {now:%Y-%m-%d %H:%M}]\n\n{text.strip()}"` (L357) — local
  time, no timezone, no UTC.

**Models** — NONE.

**Outputs**
- `save_pasted_brief` writes
  `pipeline_interpreter/MA_Inputs/news_terminal/newsroom_brief_latest.txt`
  (L355-358) via `write_text` — **not atomic**, fixed filename, overwrites the
  previous brief with no version history. Schema/version field: NONE.
- No write into `data/output/runs/**` [OBSERVED — the only write is L358].
- *Authority-claim fields:* none written. The returned strings are prompt text.

**Handoff** — *Receives from:* `dropbox/macro/`, `MA_Inputs/news_terminal/`,
`MA_Inputs/macro/`, and the `governed_macro_context` string passed down from
`evidence_resolver` → `macro_context.MacroContext.prompt_block()` →
`pipeline_interpreter_commands.py:546` → the engine prompt builders.
*Hands to:* the six engine prompt builders. *Join keys:* `ticker` (case-folded
substring), filename hint.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| Macro file unresolvable | `""` (empty string — block silently omitted) | L42-43 |
| Macro read raises | prints `⚠ Macro read error`, returns `""` | L98-100 |
| Enrichment unresolvable / raises | `""` | L124-125, L190-192 |
| Enrichment `batch_id`/`report_date`/`source` absent | literal `UNKNOWN` | L135-137 |
| Brief read raises | prints `⚠ Brief paste read`, falls through | L233-234 |
| News unresolvable | `""` | L242-243 |
| News CSV empty | `""` | L252-253 |
| Ticker not in news CSV | **first five unrelated rows** | L261 |
| Theme id/name absent | `"?"` / `""` | L168-169 |
| No parts at all | `MACRO_DATA_MISSING \| NEWS_DATA_MISSING — no governed context found.` | L317 |
§10-compliant? **N** — `MACRO_DATA_MISSING` / `NEWS_DATA_MISSING` (L317) are the
only explicit absence tokens and neither is in the §10 vocabulary; every other
absence is an empty string, which removes the block from the prompt without
telling the model it is missing.

**Contradictions found here:** CON-409, CON-410.
**Gaps found here:** GAP-411, GAP-420, GAP-429, GAP-430.
**Comment/docstring claims audited:**
- L3 "Macro, enrichment delta, and news terminal reader functions — appended to
  engine." → **HOLDS** (imported at `pipeline_interpreter_engine.py:11-14`).
- L5-8 "Three sources: 1. governed macro_quant_packet reference — advisory
  context only; 2. avshunter_macro_enrichment_delta.json …; 3. News terminal
  output" → **PARTIAL**: source 1 as implemented (L24-100) reads
  `macro_intelligence_latest.json`, not `macro_quant_packet.json`; and neither
  source 1 nor source 2 is called by `read_all_news_macro_context` any more
  (L304-319). → CON-409.
- L30-33 "Priority order: 1. Explicit path argument 2. Latest file matching
  'macro_intelligence_latest' in MA_Inputs/macro/ 3. Standard dropbox path
  (hardcoded fallback — **always present**)" → **PARTIAL**: the order holds
  (L34-40, L331-345); "always present" is an unverified assertion —
  `_resolve_path` returns `None` when the hard-coded path does not exist (L343-346).
- L50-51 "Actual macro_contract_v1_0 field names used by the pipeline. Extras
  fields are also walked for display purposes." → **HOLDS** (L51-95).
- L113-115 "This is the newsroom session layer — it sits ON TOP of the main macro
  contract and provides the intraday/session-specific colour." → **HOLDS** as a
  description; the function is not currently called.
- L170, L172, L183 "schema v1.2 uses X; older schemas used Y" → **HOLDS**: three
  explicit multi-schema fallbacks (L171, L173, L184-185). Each bridges a
  different vocabulary into one display slot with no marker of which schema
  supplied the value. → GAP-430.
- L202-209 "accepts three formats … The plain text brief is always returned in
  full (it already contains the full session narrative)." → **PARTIAL**: when a
  ticker filter is supplied the brief is **not** returned in full — only up to
  20 matching lines are (L229-231).
- L299-302 "Build the complete macro + enrichment delta + news context block …
  Called by build_single_ticker_prompt and build_triage_prompt in the engine." →
  **PARTIAL**: it is called by six builders, not two
  (`pipeline_interpreter_engine.py:650, 717, 802, 1028, 1438, 1610`); and the
  block it builds no longer contains the enrichment delta at all, because
  `read_enrichment_delta` is not invoked (L304-319). → CON-409.
- **L306-308 "Production macro may enter only through the hash-bound handoff
  bundle. MA_Inputs modification time and hardcoded Dropbox files are not
  evidence identity and therefore cannot be selected automatically here."** →
  **PARTIAL — the central authority claim of this file.** It **HOLDS for macro**:
  `read_all_news_macro_context` appends only the caller-supplied
  `governed_macro_context` (L309-310) and never calls `read_macro_context` or
  `read_enrichment_delta`. It is **FALSE for news**: two lines later (L312) the
  same function calls `read_news_terminal_output`, which selects a file by
  **modification time** through `_resolve_path` (L341) and reads the
  `MA_Inputs/news_terminal/newsroom_brief_latest.txt` paste unconditionally
  (L212-216). News content reaches every production prompt with no hash, no
  run-id and no as-of check. → CON-409.
- L330 `_resolve_path` "Resolve a file path from explicit arg → search_dir →
  hardcoded fallback." → **HOLDS** (L331-346).
- L351-353 `save_pasted_brief` "Save a pasted newsroom brief to the standard
  location so the interpreter can read it automatically on the next /triage or
  /ticker call." → **HOLDS** (L355-358, read back at L212).
- L357 "Prepend timestamp so the interpreter knows when it was pasted" →
  **PARTIAL**: the timestamp is written into the text (L357) but no reader
  parses it; the only staleness signal is the file mtime printed at
  `pipeline_interpreter_engine.py:559-560`, which never gates.
**Confidence in this section:** HIGH — all 361 lines read.

**Macro sidecar — direct answer.** Every macro/bond/regime read performed by the
Interpreter, and whether it can gate a ticker:

| Reader | File(s) | Can gate/block a ticker? |
|---|---|---|
| `news_macro_readers.read_macro_context` (L24-100) | `dropbox/macro/macro_intelligence_latest.json`, `MA_Inputs/macro/*` | **No** — returns prompt text only; no caller in the live path |
| `news_macro_readers.read_enrichment_delta` (L104-192) | `dropbox/macro/avshunter_macro_enrichment_delta.json` | **No** — no live caller |
| `news_macro_readers.read_news_terminal_output` (L196-288) | `MA_Inputs/news_terminal/*`, pasted brief | **No** — prompt text |
| `pipeline_interpreter_engine.run_session_check` (L545-556) | `MA_Inputs/macro/macro_intelligence_latest.json` | **No** — sets `all_ok=False` and prints `WARNING`; no command reads `all_ok` |
| `pipeline_interpreter_engine.build_triage_prompt` (L863-874) | `MA_Inputs/macro/macro_intelligence_latest.json` → `macro_regime_now`/`current_regime`/`morning_macro_regime_state` | **No** — printed into `MACRO REGIME:` header text |
| `pipeline_interpreter/macro_context.py` → `contracts/interpreter_macro_context.py` | `<run>/interpreter/interpreter_macro_context.json` | **No** — `macro_data_role = "ADVISORY_ONLY"` (`contracts/interpreter_macro_context.py:441`) and `FORBIDDEN_AUTHORITY_KEYS` (L32-38) strips every authority key before serialisation |
| `evidence_resolver._refresh_requirement` (L151-186) | bundle freshness map | **No** — `macro`, `macro_quant_packet`, `bond`, `auction_calendar`, `news`, `catalyst` are all in `ADVISORY_FRESHNESS_DOMAINS` (L32-36), so stale macro never raises `EVIDENCE_REFRESH_REQUIRED` |

**Verdict: the documented "macro is advisory only" policy HOLDS.** No macro,
bond, regime or news read in this lane can block, gate, or change the disposition
of a ticker. [OBSERVED across all seven readers.] Two qualifications are recorded
separately: the advisory text is nevertheless injected into the model prompt with
authority-shaped field names (CON-410), and macro staleness is silently tolerated
because `market_structure` shares the advisory exemption (CON-406).

---

## F2 — Governed handoff contracts

### contracts/interpreter_handoff.py
**Classification:** Contract — handoff manifest schema, validation and atomic
publication (407 lines). Pure validation; no market data, no model.
**Real execution position:** POST-RUN / READ-PATH on the read side
(`pipeline_interpreter/evidence_resolver.py:95,111`), and morning-workflow
position 3 on the write side (`morning_handoff_finalizer.py:408-413`, reached
from `intelligent_orchestrator.py:5817`).
**Task in the process:** Defines the baton between the Lab/Morning Gate and the
Interpreter. It validates that a manifest names four required artefacts, that
every artefact's SHA-256 matches, that the per-ticker evidence bundles and the
book rows agree on identity and on five authority fields, and that counts
reconcile — then, and only then, publishes the manifest atomically.
**Entry points:** `validate_evidence_bundle` (L118); `load_bundle_jsonl` (L165);
`read_book_rows` (L186); `validate_handoff_manifest` (L248);
`artifact_record` (L315); `publish_handoff_manifest` (L328); helpers
`sha256_file` (L91), `canonical_json` (L83), `utc_now` (L79).
**Imports (production):** stdlib only (`csv, hashlib, json, os, tempfile, uuid,
dataclasses, datetime, enum, pathlib, typing`). · **Imported by:**
`contracts/interpreter_handoff_materializer.py:19-30`,
`pipeline_interpreter/evidence_resolver.py:22-26`,
`intelligence-lab/intelligence_lab.py:262` (Lane B, cross-reference),
`tools/msi_reconcile.py:16`, `tools/msi_production_readiness.py:22`,
`tests/msi/test_logic.py:49`. · **Broken/retired imports:** NONE.

**Inputs**
- *Files/tables read:* the manifest JSON (L255); each artefact named in it, byte
  by byte for hashing (L284, L91-96); `INTERPRETER_BUNDLES` as JSONL (L292, L165-183);
  `LAB_BOOK` as CSV or JSON (L293, L186-195).
- *Upstream fields consumed:*
  - Manifest: `schema_version`, `handoff_status`, `run_kind`, `run_status`,
    `run_id`, `pipeline_mode`, `session_date`, `published_at_utc`, `artifacts[]`
    (`role`, `path`, `sha256`), `ticker_count`, `bundle_count`,
    `missing_bundle_count` (L258-311).
  - Bundle identity, 12 required fields (L56-69): `run_id`, `pipeline_mode`,
    `ticker`, `thesis_id`, `trade_idea_id`, `selected_structure_id`,
    `selected_contract_symbol`, `selected_quote_snapshot_id`, `bundle_id`,
    `bundle_created_utc`, `bundle_schema_version`, `authority_map_version`.
  - Bundle structure: `authority_map` (Mapping, L138), `freshness_map` (Mapping,
    L140), `governed_record` (Mapping, L142).
  - **Authority fields cross-checked book↔bundle** (L217-222):
    `governed_direction`, `thesis_state`, `olm_guard_disposition`,
    `final_action`, `capital_permission`.
  - **Fallback chain** L156-159 and L207-211:
    `selected_contract_symbol` → `contract_symbol` → `morning_selected_contract_symbol`.
    Three different column names accepted for one identity. [OBSERVED]
- *External calls:* NONE. *Config/policy read:* NONE — all thresholds are module
  constants (L23-26).

**Logic and algorithms**
- **Bundle validation** (L118-162): required-identity check → schema-version
  equality → authority-map-version equality → `bundle_id` must parse as a UUID →
  `bundle_created_utc` must parse as ISO-8601 → ticker upper-cased →
  contract symbol canonicalised → three Mapping presence checks →
  six identity fields must match `governed_record` case-insensitively →
  canonical contract must match.
- **Manifest validation** (L248-312), fail-closed at every step: schema version
  → `handoff_status == READY` → (if `require_accepted`) `run_kind == PRODUCTION`
  and `run_status == ACCEPTED` → four non-empty scalars →
  `published_at_utc` parses → artefacts is a non-string Sequence → per artefact:
  path is inside the run root (`_safe_artifact_path`, L225-236), role is unique,
  file exists, **SHA-256 matches** (L284-285) → all four required roles present
  → bundles load → book rows load → all bundle run_ids equal the manifest run_id
  → book tickers are unique and equal the bundle ticker set →
  `_validate_book_bundle_identity` per ticker → three count equalities.
- **Atomic publication** (L376-384): `tempfile.mkstemp` in the destination
  directory → write → **re-validate the temporary file with
  `validate_handoff_manifest`** (L381) → `os.replace` → `unlink(missing_ok=True)`
  in `finally`. This is a genuine write-validate-promote sequence.
- **Publication preconditions** (L350-356): only `PRODUCTION` + `ACCEPTED` may
  publish; `reconciliation_status` must be exactly `"PASS"`; every value in
  `required_stage_status` must be in `{PASS, COMPLETED, ACCEPTED}`;
  `morning_gate_completed_utc` must parse.
- **Path containment** (`_safe_artifact_path`, L225-236): `run_root` is derived
  as `manifest_path.parent.parent` (L231) — i.e. `<run>/interpreter/` → `<run>/`.
  Any artefact resolving outside `<run>/` raises `ARTIFACT_OUTSIDE_RUN`.
- *Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE by design.
  `governed_direction` is compared as an opaque upper-cased string (L221); the
  contract never inspects its value, so `UNRESOLVED`, `STRANGLE`, `NONE` and
  blank all validate provided book and bundle agree. `_text` (L99-101) maps
  `NAN/NONE/NULL/N/A` to `""` (L101), so a bundle carrying `"NONE"` and a book
  carrying `""` are treated as equal. → GAP-431.

**Computations and formulas (exact)**
- `sha256_file(path)` — SHA-256 over 1 MiB blocks (L91-96); compared
  case-insensitively via `_text(record["sha256"]).lower()` (L284).
- `canonical_json(v) = json.dumps(v, sort_keys=True, separators=(",",":"), default=str)` (L84).
- `_canonical_occ(v) = _text(v).upper().replace("O:","").replace(" ","")` (L105).
- `missing_bundle_count = max(0, ticker_count - bundle_count)` (L370) — clamped
  at 0, so a bundle surplus is recorded as 0 missing rather than as a mismatch;
  the surplus is caught separately by the ticker-set equality at L301.
- `size_bytes = artifact.stat().st_size` (L323).

**Models** — NONE.

**Outputs**
- One file: the handoff manifest at `target` (L346, L382) — in practice
  `<run>/interpreter/handoff_manifest.json`
  (`contracts/interpreter_handoff_materializer.py:345`).
- Fields: `schema_version`, `handoff_status`, `run_id`, `pipeline_mode`,
  `session_date`, `run_kind`, `run_status`, `required_stage_status`,
  `morning_gate_completed_utc`, `ticker_count`, `bundle_count`,
  `missing_bundle_count`, `reconciliation_status`, `producer_version`,
  `published_at_utc`, `artifacts[]` (L358-375).
- **Atomic promotion: YES** — mkstemp → write → self-validate → `os.replace`
  (L376-384). This is the only genuinely atomic writer in Lane F.
- **Schema/version field: YES** — `schema_version = "interpreter_handoff_manifest_v1"`
  (L23, L359); artefacts carry per-role `schema_version` (L322).
- *Authority-claim fields:* `handoff_status = READY` (L360),
  `run_status`, `run_kind`, `reconciliation_status`, `producer_version`.
  Class docstring L3-5 "It validates immutable files produced by the pipeline and
  publishes a single manifest baton only after every referenced artefact and
  per-ticker bundle has been verified." → **HOLDS**.

**Handoff** — *Receives from:* `contracts/interpreter_handoff_materializer.py`
(write side). *Hands to:* `pipeline_interpreter/evidence_resolver.py`,
`intelligence-lab/intelligence_lab.py:262-263`, `tools/msi_reconcile.py`,
`tools/msi_production_readiness.py`. *Join keys:* `run_id`; `ticker`
(upper-cased); `bundle_id` (UUID); canonical OCC `selected_contract_symbol`.

**Missing-data handling** — Every absence raises `HandoffValidationError` with a
specific code. There is **no default, no coercion and no silent pass** anywhere
in this module [OBSERVED L110-311]. Codes emitted:
`MISSING_{FIELD}`, `INVALID_{FIELD}`, `BUNDLE_MISSING_IDENTITY:{fields}`,
`BUNDLE_SCHEMA_UNSUPPORTED`, `AUTHORITY_MAP_UNSUPPORTED`, `BUNDLE_ID_NOT_UUID`,
`BUNDLE_SELECTED_CONTRACT_MISSING`, `BUNDLE_AUTHORITY_MAP_MISSING`,
`BUNDLE_FRESHNESS_MAP_MISSING`, `BUNDLE_GOVERNED_RECORD_MISSING`,
`BUNDLE_GOVERNED_IDENTITY_MISMATCH:{field}`, `INVALID_BUNDLE_LINE:{n}`,
`DUPLICATE_BUNDLE_IDENTITY:{n}`, `BUNDLE_FILE_EMPTY`, `LAB_BOOK_ROWS_INVALID`,
`HANDOFF_BOOK_BUNDLE_IDENTITY_MISMATCH:{field}`,
`HANDOFF_BOOK_BUNDLE_AUTHORITY_MISMATCH:{field}`, `ARTIFACT_OUTSIDE_RUN`,
`HANDOFF_MANIFEST_UNREADABLE`, `HANDOFF_SCHEMA_UNSUPPORTED`, `HANDOFF_NOT_READY`,
`HANDOFF_NOT_PRODUCTION`, `HANDOFF_RUN_NOT_ACCEPTED`, `HANDOFF_MISSING_{FIELD}`,
`HANDOFF_ARTIFACTS_INVALID`, `HANDOFF_ARTIFACT_RECORD_INVALID`,
`HANDOFF_DUPLICATE_ARTIFACT_ROLE`, `HANDOFF_ARTIFACT_MISSING:{role}`,
`HANDOFF_ARTIFACT_HASH_MISMATCH:{role}`, `HANDOFF_REQUIRED_ARTIFACT_MISSING`,
`HANDOFF_BUNDLE_RUN_MISMATCH`, `HANDOFF_BOOK_DUPLICATE_OR_MISSING_TICKER`,
`HANDOFF_BOOK_BUNDLE_TICKER_MISMATCH`, `HANDOFF_TICKER_COUNT_MISMATCH`,
`HANDOFF_BUNDLE_COUNT_MISMATCH`, `HANDOFF_MISSING_BUNDLES`,
`ONLY_ACCEPTED_PRODUCTION_HANDOFF_MAY_PUBLISH`,
`HANDOFF_RECONCILIATION_NOT_PASS`, `HANDOFF_REQUIRED_STAGE_NOT_COMPLETE`,
`ARTIFACT_MISSING:{role}`.
§10-compliant? **N** — this is a distinct, self-consistent and considerably more
precise error vocabulary, but it shares no token with §10. `CONTRACT_REPAIR_REQUIRED`
in particular has no counterpart here. → GAP-432.

**Contradictions found here:** NONE.
**Gaps found here:** GAP-431, GAP-432.
**Comment/docstring claims audited:**
- L1 "Governed, atomic Lab-to-Interpreter handoff contracts for MSI v1.1." → **HOLDS**.
- L3-5 "This module contains no market-data or model calls." → **HOLDS**
  (imports are stdlib only, L10-20).
- L5 "publishes a single manifest baton only after every referenced artefact and
  per-ticker bundle has been verified" → **HOLDS** (L284-311, then L381).
- L53 `HandoffValidationError` "A handoff cannot be trusted for production
  interpretation." → **HOLDS**: every raise path aborts.
- L344 `publish_handoff_manifest` "Atomically publish the production baton after
  full self-validation." → **HOLDS** (L376-384) — including the unusual and
  correct step of validating the temporary file before promotion (L381).
- L288-289 (in the materializer, cited here for the pairing) "The v3 book and
  bundle are two serialisations of the same governed record." → cross-checked
  **HOLDS** by this module's L198-222.
**Confidence in this section:** HIGH — all 407 lines read.

---

### contracts/interpreter_handoff_materializer.py
**Classification:** Contract writer — serialises governed rows into the four
handoff artefacts and publishes the baton (380 lines).
**Real execution position:** **Morning workflow, position 3 of 3** —
`intelligent_orchestrator.py:5817` → `morning_handoff_finalizer.py:408-413`
[OBSERVED]. It is **not** reached from `evening_workflow`; no evening stage in
`03_execution_order.md` calls it. This is the direct cause of CON-401.
**Task in the process:** Takes the already-governed Morning/Lab rows, derives
quote-change evidence and a freshness map for each, stamps a deterministic
`bundle_id`, writes the v3 book CSV, its manifest, the JSONL bundle file and the
reconciliation report — each atomically — then calls
`publish_handoff_manifest`. It is deliberately incapable of computing direction,
selecting a contract, or granting capital.
**Entry points:** `materialize_interpreter_handoff` (L248).
**Imports (production):** `contracts.interpreter_handoff` (L19-30);
`canonical_data.bundle_freshness.derive_bundle_freshness` (L31);
`contracts.quote_change_evidence` — `compare_exact_option_quotes`,
`quote_change_overlay_fields`, `quote_snapshot_from_row` (L32-36).
· **Imported by:** `morning_handoff_finalizer.py:408`, `tests/msi/test_logic.py:57`.
· **Broken/retired imports:** NONE.

**Inputs**
- *Files/tables read:* only the macro reference file, for hashing (L240).
  All row data arrives as the `rows` argument (L251).
- *Upstream fields consumed (with fallback chains):*
  - Identity (`_identity`, L120-141): `run_id` **or** the `run_id` argument (L122);
    `pipeline_mode` **or** the argument (L123); `ticker`; `thesis_id`;
    `trade_idea_id`; `selected_structure_id`; `selected_quote_snapshot_id`.
  - `_canonical_contract` (L53-69): `selected_contract_symbol` →
    `morning_selected_contract_symbol` → `contract_symbol`; then, if still empty,
    `selected_contract_symbols` parsed as JSON and accepted **only when it holds
    exactly one element** (L61-68). Three column names plus a one-element list
    resolve to one identity. [OBSERVED]
  - Quote snapshots by role `MORNING` and `CURRENT` (L169-170) via
    `quote_snapshot_from_row`.
  - `macro_packet_id`, `macro_packet_sha256` cross-checked against the supplied
    macro reference (L209-216).
  - `market_structure` sub-object: **every row key beginning `ms_` or
    `market_structure_`** (L201-206). The governed book emitted by
    `contracts/lab_control.py::write_final_opportunity_book` carries none —
    its market-structure columns are `call_wall`, `put_wall`, `gamma_flip`,
    `max_pain`, `wbs*`, `trigger_*` with no prefix [OBSERVED — book header,
    columns 305-351]. On that book shape the `market_structure` block would
    serialise empty. → GAP-433.
- *External calls:* NONE — no provider, no model.
- *Config/policy read:* module constants L39-41 and the imported version
  constants L20-23.

**Logic and algorithms**
- **Per-row pipeline** (L281-295): identity → duplicate-ticker guard (L284-285)
  → `_bundle` → book row = `dict(bundle["governed_record"])` re-stamped with
  identity, `lab_schema_version` and `bundle_id` (L290-293).
- **`_bundle`** (L161-218): copy row → overwrite with identity → build morning
  and current quote snapshots → `compare_exact_option_quotes` → merge the
  overlay fields **into `governed_record`** (L179) → derive `bundle_id` as
  `uuid.uuid5(NAMESPACE_URL, canonical_json({**identity, authority_map_version}))`
  (L180-190) → assemble → optional macro cross-check → `validate_evidence_bundle`.
- **`_authority_map`** (L144-154), the declarative authority table:
  `governed_direction → DIRECTION_GOVERNANCE`;
  `selected_contract_symbol → MORNING_GATE_SELECTED_CONTRACT`;
  `thesis_state → OPTIONS_LIQUIDITY_LIFECYCLE`;
  `olm_guard_disposition → OLM_EXECUTION_GUARD`;
  `final_action → MORNING_EXECUTION_GATE`;
  `capital_permission → MORNING_EXECUTION_GATE`;
  **`macro_quant_packet → ADVISORY_ONLY`**;
  **`interpreter_assessment → ADVISORY_ONLY`**.
  The last two are the machine-readable form of the advisory-only policy, and
  they hold: nothing in Lane F writes either name into an authority slot.
- **Fail-whole-publication rule** (L131-140, L284-285): a row with a mismatched
  `run_id`, any missing identity field, or a duplicate ticker raises and aborts
  the entire publication. No row is dropped or repaired.
- *Decision branches (CALL / PUT / other-blank):* the docstring L265-267 asserts
  "Rows lacking an exact long CALL/PUT contract identity fail the whole
  publication". **PARTIAL** — the enforcement is on the *presence and
  canonicalisation* of `selected_contract_symbol` (L128, L135-140, and
  `contracts/interpreter_handoff.py:136-137`), not on its **CALL/PUT nature**.
  `_canonical_occ` (`interpreter_handoff.py:105`) strips `O:` and spaces and
  upper-cases; it never parses the OCC option-type character. A multi-leg
  `selected_contract_symbols` list of length ≠ 1 yields `""` and fails
  (L67-68, L136-137) — so a two-leg spread does fail, but by arity, not by type.
  A single-leg contract of any type validates. → CON-419.

**Computations and formulas (exact)**
- `bundle_id = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_json({**identity, "authority_map_version": AUTHORITY_MAP_VERSION})))` (L180-190) —
  deterministic: the same identity in the same authority-map version always
  yields the same UUID. Note `bundle_created_utc` (L196) is **not** in the hash,
  so re-materialising an identical row produces the same `bundle_id` with a new
  timestamp.
- `fields = identity + sorted(all_keys - identity)` (L105) — the ten identity
  columns are pinned to the left of the CSV, the remainder alphabetical.
- `row_count = len(book_rows)`, `ticker_count = len(seen_tickers)`,
  `missing_bundles = 0` (hard-coded, L332), `identity_mismatches = 0`
  (hard-coded, L333). Both zeros are literals, justified because any non-zero
  value would already have raised. [OBSERVED L284-295]
- `book_sha256 = sha256_file(book_path)` computed **twice** (L314, L334).

**Models** — NONE.

**Outputs**
| Artefact | Path | Line | Atomic? | Schema field |
|---|---|---|---|---|
| v3 book | `<run>/intelligence_lab/lab_signal_book_v3.csv` | L300, L305 | **YES** (`_atomic_csv`, L92-117: mkstemp → write → `os.replace`) | `lab_schema_version = "lab_signal_book_v3"` (L292) |
| book manifest | `<run>/intelligence_lab/lab_signal_book_v3.manifest.json` | L301, L317 | **YES** (`_atomic_text`, L80-89) | `schema_version = "lab_signal_book_v3_manifest_v1"` (L307) |
| evidence bundles | `<run>/interpreter/interpreter_evidence_bundle_v1.jsonl` | L302, L318-321 | **YES** | `bundle_schema_version = "interpreter_evidence_bundle_v1"` (L193) |
| reconciliation | `<run>/diagnostics/msi_reconciliation.json` | L303, L337 | **YES** | `schema_version = "msi_reconciliation_v1"` (L324) |
| handoff manifest | `<run>/interpreter/handoff_manifest.json` | L345-360 | **YES** (delegated) | `interpreter_handoff_manifest_v1` |

All five writes land **inside `data/output/runs/<run_id>/`**. This is a *write*
path by design (it is the morning finaliser), not a read-path write, and the run
root is asserted to match the run id at L269-271. Recorded for completeness, not
as a gap.

*Authority-claim fields:* `authority_map` (L198), `authority_map_version = "msi-authority-v1.1"`,
`producer_version = "msi-handoff-materializer-v1.1"` (L39), `status: "PASS"` (L325).
The `"status": "PASS"` in the reconciliation report is **PARTIAL as a claim**: it
is a literal (L325), asserted rather than computed, and the accompanying
`missing_bundles: 0` / `identity_mismatches: 0` are likewise literals (L332-333).
They are truthful only because the code cannot reach L323 with a non-zero value —
the report records the absence of a failure it structurally cannot represent. → GAP-434.

**Handoff** — *Receives from:* `morning_handoff_finalizer.py:413` (governed rows,
run metadata, macro reference). *Hands to:*
`contracts/interpreter_handoff.publish_handoff_manifest` (L346), and thence to
`pipeline_interpreter/evidence_resolver.py`. *Join keys:* `run_id`, `ticker`,
`thesis_id`, `trade_idea_id`, `selected_structure_id`,
`selected_quote_snapshot_id`, canonical `selected_contract_symbol`, `bundle_id`.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| `run_root.name != run_id` | `MATERIALIZER_RUN_ROOT_MISMATCH` | L270-271 |
| empty row set | `MATERIALIZER_EMPTY_ROW_SET` | L274-275 |
| row `run_id` differs | `MATERIALIZER_RUN_ID_MISMATCH` | L131-134 |
| any identity field blank | `MATERIALIZER_MISSING_IDENTITY:{ticker}:{fields}` | L135-140 |
| duplicate ticker | `MATERIALIZER_DUPLICATE_TICKER:{ticker}` | L284-285 |
| macro reference outside run | `MACRO_REFERENCE_OUTSIDE_RUN` | L235-236 |
| macro reference file absent | `MACRO_REFERENCE_MISSING` | L237-238 |
| macro hash mismatch | `MACRO_REFERENCE_HASH_MISMATCH` | L242-243 |
| row macro packet id/hash disagrees | `MACRO_PACKET_ID_LAB_BUNDLE_MISMATCH` / `MACRO_PACKET_HASH_LAB_BUNDLE_MISMATCH` | L213-216 |
| `selected_contract_symbols` unparseable | `except json.JSONDecodeError: symbols = [symbols]` — the raw string is wrapped in a one-element list and then accepted as the contract identity | **L65-68** |
| no macro reference supplied | `return None`; `macro_quant_packet` key simply absent from the bundle | L222-223, L208 |
§10-compliant? **N** — a distinct `MATERIALIZER_*` / `MACRO_*` vocabulary.
The L65-68 path is the one place in this otherwise fail-closed module where a
malformed input is coerced rather than rejected: a JSON-invalid
`selected_contract_symbols` string becomes the contract symbol. → GAP-435.

**Contradictions found here:** CON-419.
**Gaps found here:** GAP-433, GAP-434, GAP-435.
**Comment/docstring claims audited:**
- L2 "Materialise the immutable MSI Lab-to-Interpreter production handoff." → **HOLDS**.
- **L3-7 "This module is deliberately data-only: it does not fetch market data,
  select a contract, calculate direction, or grant capital. It serialises already
  governed Morning/Lab rows and publishes the atomic Interpreter baton only when
  every row has complete, matching identity."** → **HOLDS**, with one
  qualification. No provider import, no direction computation, no capital field
  is written (L144-154 only *labels* authorities). "Selects a contract" is
  **PARTIAL**: `_canonical_contract` L61-68 will *choose* the sole element of a
  `selected_contract_symbols` list when the three scalar columns are blank —
  a resolution step, however narrow. Everything else holds.
- L262 "Write, reconcile and atomically publish one accepted handoff." → **HOLDS**
  (L305-360; four `_atomic_*` writes plus the delegated atomic publish).
- L264-267 "The caller must pass only the governed rows intended for Interpreter
  use. Rows lacking an exact long CALL/PUT contract identity fail the whole
  publication; they are never silently dropped or repaired here." → **PARTIAL**
  (CON-419): "never silently dropped or repaired" **HOLDS** absolutely
  (L131-140, L284-295 — every defect raises); "exact long CALL/PUT contract
  identity" is **not** what is enforced — presence and single-arity are.
- **L288-289 "The v3 book and bundle are two serialisations of the same governed
  record. Computed quote evidence must never exist only in the bundle."** →
  **HOLDS**: `book_row = dict(bundle["governed_record"])` (L290) is taken *after*
  `quote_change_overlay_fields` has been merged into `governed_record` (L179), so
  the quote-change overlay is present in both serialisations.
- L162-164 `_ticker_advisory_index` docstring (in `interpreter_macro_context.py`)
  — audited in that section.
**Confidence in this section:** HIGH — all 380 lines read; execution position
corroborated by the caller at `morning_handoff_finalizer.py:408-413` and by the
absence of any evening call site.

**The handoff bundle — direct answer.** What is materialised, and what is not:

| Required element | Present? | Evidence |
|---|---|---|
| Run identity (`run_id`, `pipeline_mode`, `session_date`) | **YES** | L122-123; manifest L361-364 |
| Ticker identity | **YES** | L124 |
| Thesis identity (`thesis_id`) | **YES** | L125 |
| Trade-idea identity (`trade_idea_id`) | **YES** | L126 |
| Contract identity (`selected_structure_id`, canonical `selected_contract_symbol`) | **YES** | L127-128 |
| Quote-snapshot identity (`selected_quote_snapshot_id`) | **YES** | L129 |
| Bundle identity + creation time (`bundle_id` UUID5, `bundle_created_utc`) | **YES** | L180-196 |
| **EOD thesis fields** | **YES, as a whole-row copy** — `governed_record = dict(row)` (L162) carries every column the caller passes, including `entry_plan`, `invalidation_price`, `target_price`, `structural_target`, `trigger_*`. There is **no explicit EOD field list**, so completeness depends entirely on the caller's row shape. | L162, L192-207 |
| **Morning delta fields** | **YES** — `quote_change_overlay_fields(quote_change)` merged into `governed_record` (L179) and preserved whole under `quote_change_evidence` (L206) | L169-179, L206 |
| **Current bid/ask** | **YES** — via `quote_snapshot_from_row(governed, role="CURRENT")` (L170) | L170 |
| **Quote timestamp** | **YES** — carried inside the snapshot objects and validated upstream by the freshness map; the governed book carries `current_quote_timestamp_utc` and `morning_quote_timestamp_utc` [OBSERVED — book header columns 92, 100] | L169-170, L199 |
| **Macro packet** | **CONDITIONAL** — only when `macro_reference` is supplied (L208-217); absent entirely otherwise, with no marker | L208-217 |
| **Evidence manifest / hashes** | **YES** — four `artifact_record` entries each carrying `role`, `path`, `schema_version`, `size_bytes`, `sha256` (L339-344 → `interpreter_handoff.py:315-325`) | L339-344 |
| **Freshness map** | **YES** — `derive_bundle_freshness(governed)` (L157-158, L199) | L157-158 |
| **Authority map** | **YES** — eight entries (L144-154) | L144-154 |
| **Explicit missing-field markers** | **NO** | — |

The last row is the gap. The bundle has **no field-level absence vocabulary**:
a governed column that the caller's row does not contain is simply absent from
`governed_record`, and nothing in the bundle distinguishes "this field was not
applicable" from "this field was expected and is missing". `freshness_map`
covers *staleness* per domain, not *presence* per field. The only presence
guarantee is the twelve-field identity check (`interpreter_handoff.py:56-69`).
None of the eight §10 tokens appears in either contract file. → GAP-432, GAP-436.

---

### contracts/interpreter_macro_context.py
**Classification:** Contract — governed advisory macro snapshot builder and
per-row advisory field projector (453 lines).
**Real execution position:** **Morning workflow, position 3 of 3** —
`intelligent_orchestrator.py:5817` → `morning_handoff_finalizer.py:606`
(`materialize_interpreter_macro_context`) and `:623` (`advisory_fields_for_row`)
[OBSERVED]. Read side: `pipeline_interpreter/macro_context.py:13` and
`intelligence-lab/intelligence_lab.py:237, 768, 1286` (Lane B, cross-reference).
**Task in the process:** Snapshots the four canonical macro drops into the run as
one hash-identified packet, records per-source status and hashes, strips every
field that could be read as trading authority, and exposes a flat set of
`macro_*` display columns for one governed row.
**Entry points:** `materialize_interpreter_macro_context` (L246);
`advisory_fields_for_row` (L370).
**Imports (production):** stdlib only. · **Imported by:**
`morning_handoff_finalizer.py:28-30`, `pipeline_interpreter/macro_context.py:13`.
· **Broken/retired imports:** NONE.

**Inputs**
- *Files/tables read* (`CANONICAL_SOURCES`, L26-31, resolved under the supplied
  `macro_dir`): `macro_intelligence_latest.json`, `bond_macro_state.json`,
  `auction_calendar.csv`, `avshunter_macro_enrichment_delta.json`. Plus, as
  fallbacks, `<run>/macro_snapshot.json` (L222) and
  `<run>/macro_quant_packet.json` (L236).
- *Upstream fields consumed (with fallback chains):*
  - `core_macro` empty → `<run>/macro_snapshot.json`, status
    `RUN_SNAPSHOT_FALLBACK` (L262-269).
  - `bond_macro` / `auction_calendar` / `enrichment_delta` empty → embedded
    copies inside `core.extras` (L271-278, `_embedded` L206-218), status
    `EMBEDDED_FALLBACK` with an `embedded_sha256` (L277-278).
  - `freshness = quant.macro_freshness_status → core.macro_freshness_status → "UNKNOWN"` (L296-300).
  - `quality = quant.macro_data_quality → core.macro_data_quality → "UNKNOWN"` (L301-303).
  - `as_of_utc = core.as_of_utc → quant.macro_generated_at_utc` (L325).
  - `usd = core.usd_state → quant.usd_state` (L343);
    `liquidity_pulse = core → quant` (L345);
    `regime_state = core.regime_state → quant.macro_regime_label` (L346);
    `macro_conviction = core.macro_conviction → quant.macro_confidence` (L347).
  - `plain_language = enrichment.narrative_overlay.overlay_summary → bond.composite.summary → core.notes` (L314-318).
  - `_load` as-of chain: `as_of_utc → generated_at → report_date → as_of_date →
    file mtime` (L190-197) — **stale ← fresh**: a packet with no declared as-of
    date is stamped with the file's modification time and thereafter reads as if
    the source had declared it. → GAP-437.
  - `advisory_fields_for_row` sector chain: `gics_sector_norm → gics_sector →
    sector` (L381-383).
- *External calls:* NONE. *Config/policy read:* module constants L20-38.

**Logic and algorithms**
- **Authority stripping** `_sanitise` (L70-79) — recursive; removes any key in
  `FORBIDDEN_AUTHORITY_KEYS` (L32-38) at every depth: `direction`,
  `governed_direction`, `selected_contract_symbol`, `contract_symbol`,
  `thesis_state`, `olm_guard_disposition`, `final_action`, `capital_permission`,
  `execution_permission`, `size_multiplier`, `macro_filter`,
  `risk_on_off_switch`, `trade_go`, `trigger_required`, `position_size`,
  `position_size_pct`, `execution_verdict`. Applied once, to the whole payload
  (L320). This is the mechanism that makes the advisory-only claim structural
  rather than declarative.
- **Two enrichment shapes** `_ticker_advisory_index` (L86-158): if
  `macro_exposure_index` is a Mapping, use it directly (L96-102); otherwise build
  the index from `theme_deltas[]` roles
  (`beneficiary_universe → BENEFICIARY`, `vulnerable_universe → VULNERABLE`,
  `context_universe → CONTEXT_ONLY`, L112-116) and from
  `macro_exposure_index_build.normalised_catalyst_records` (L138-156).
- **Context-state ladder** (L306-312):
  `STALE_CONTEXT` if `freshness ∈ {STALE, MISSING, INVALID}` →
  else `CONFLICTING_SOURCES` if `conflicts` non-empty → else `NEUTRAL`.
- *Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE by construction —
  `direction` and `governed_direction` are in `FORBIDDEN_AUTHORITY_KEYS` (L33) and
  are stripped before serialisation. `directional_pressure` survives as a joined
  display string (L405-409, L435) and is never parsed. This is the correct shape:
  the module cannot express a direction.

**Computations and formulas (exact)**
- `_sha256(path)` over 1 MiB chunks (L45-50).
- `_canonical_hash(v) = sha256(json.dumps(v, sort_keys=True, separators=(",",":"), default=str))` (L53-55).
- `source_fingerprint = _canonical_hash({name: {filename, sha256 or embedded_sha256, status} for sorted manifest})` (L288-295).
- `packet_id = f"MACRO:{source_fingerprint[:24]}"` (L322) — **24 hex characters,
  96 bits**, truncated from 256.
- `macro_sector_alignment = sector_bias_map.get(sector) or "UNMAPPED"` (L423).
- `macro_ticker_alignment = " | ".join(roles) if roles else "NO_TICKER_SPECIFIC_OVERLAY"` (L424).

**Models** — NONE.

**Outputs**
- One file: `<run>/interpreter/interpreter_macro_context.json` (L352-353).
- **Atomic promotion: YES** — `_atomic_json` (L58-67): mkstemp → write →
  `os.replace` → `unlink(missing_ok=True)`.
- **Schema/version field: YES** — `schema_version = "interpreter_macro_context_v1"`
  (L20, L321). Checked on read at `pipeline_interpreter/macro_context.py:152` and
  `intelligence-lab/intelligence_lab.py:768`.
- Returned `reference` dict (L355-366) supplies `packet_id`, `path`, `sha256`,
  `source_fingerprint`, `as_of_utc`, `session_date`, `freshness`, `quality`,
  `macro_context_state`, `authority_statement` — this is what the materializer
  cross-checks at `interpreter_handoff_materializer.py:209-217`.
- `advisory_fields_for_row` returns 21 display columns (L413-442), all prefixed
  `macro_`, terminating in `macro_authority = AUTHORITY_STATEMENT` and
  `macro_data_role = "ADVISORY_ONLY"`.
- *Authority-claim fields:* `AUTHORITY_STATEMENT` (L21-25) —
  "MACRO_ADVISORY_ONLY — macro may explain sector rotation and market context but
  cannot change direction, contract, lifecycle, final action, capital permission
  or position size." → **HOLDS**, and is *enforced* rather than merely asserted:
  every noun it disclaims appears in `FORBIDDEN_AUTHORITY_KEYS` (L32-38) and is
  stripped by `_sanitise` (L70-79) before the packet is written. This is the
  strongest authority claim in Lane F and the only one backed by a mechanism.

**Handoff** — *Receives from:* `dropbox/macro/` (via the `macro_dir` argument)
and the run directory. *Hands to:* `morning_handoff_finalizer.py:606-623`, which
merges the 21 advisory columns into each governed row and passes the `reference`
to the materializer; then `pipeline_interpreter/macro_context.py` and the Lab.
*Join keys:* `ticker` (upper-cased, L378, L99); `sector`; `packet_id`;
`macro_packet_sha256`.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| Source file absent | `status: "MISSING"`, empty value | L166-170 |
| Source unreadable / malformed | `status: "INVALID"` plus `error` | L201-203 |
| Source parses but empty | `status: "EMPTY"` | L188 |
| Source valid | `status: "VALID"` | L188 |
| `core_macro` missing, run snapshot present | `status: "RUN_SNAPSHOT_FALLBACK"` | L265-269 |
| bond/auction/enrichment missing, embedded present | `status: "EMBEDDED_FALLBACK"` + `embedded_sha256` | L277-278 |
| freshness undeclared | `"UNKNOWN"` | L296-300 |
| quality undeclared | `"UNKNOWN"` | L301-303 |
| freshness ∈ {STALE, MISSING, INVALID} | `macro_context_state = "STALE_CONTEXT"` | L306-309 |
| conflicts present | `macro_context_state = "CONFLICTING_SOURCES"` | L309-311 |
| neither | `"NEUTRAL"` | L312 |
| sector not in bias map | `"UNMAPPED"` | L423 |
| no ticker overlay | `"NO_TICKER_SPECIFIC_OVERLAY"` | L424 |
| no as-of in payload | **file mtime substituted** | L190-197 |
§10-compliant? **N**, but this is the **closest** module in the lane. Its
`MISSING / INVALID / EMPTY / VALID / STALE_CONTEXT / RUN_SNAPSHOT_FALLBACK /
EMBEDDED_FALLBACK / UNKNOWN / UNMAPPED / NO_TICKER_SPECIFIC_OVERLAY` vocabulary
is per-source, explicit and hashed — semantically equivalent to §10's
`AVAILABLE / DATA_DEFECT / STALE_ADVISORY / NOT_APPLICABLE` distinctions, but it
shares no token with them. → GAP-432.

**Contradictions found here:** CON-410 (raised against
`news_macro_readers.py`, evidenced here).
**Gaps found here:** GAP-432, GAP-437, GAP-438.
**Comment/docstring claims audited:**
- L1 "Governed advisory macro snapshot for Morning Gate, Lab and Interpreter." →
  **HOLDS** — all three consume it (`morning_handoff_finalizer.py:606`,
  `intelligence-lab/intelligence_lab.py:237`, `pipeline_interpreter/macro_context.py:13`).
- **L3-5 "This module performs filesystem reads only. It snapshots the canonical
  macro drop into the active run, records source hashes, and removes fields that
  could be mistaken for trading authority."** → **HOLDS** on all three counts:
  reads only (no provider import, L10-17); snapshot written into the run
  (L352-353); hashes recorded per source (L165, L278, L291); authority fields
  removed (L32-38, L70-79, L320).
- L21-25 `AUTHORITY_STATEMENT` → **HOLDS** (mechanism at L32-38 + L70-79).
- L87-93 `_ticker_advisory_index` "Early enrichment packets supplied
  `macro_exposure_index` directly. The current production contract supplies
  `theme_deltas` plus normalised catalyst records under
  `macro_exposure_index_build`. Supporting both shapes keeps the governed packet
  additive and prevents a valid enrichment file from becoming an empty
  Lab/Interpreter overlay." → **HOLDS** (L96-158), and it is an explicitly
  documented dual-schema fallback — the honest counterpart to the undocumented
  ones in `news_macro_readers.py:171-185`.
- L252 "Snapshot the latest valid canonical macro inputs into one run packet." →
  **PARTIAL**: "latest" is not enforced. `_load` (L161-203) reads a **fixed
  filename** per source (L26-31) with no mtime comparison and no as-of gate; a
  months-old `bond_macro_state.json` loads with `status: "VALID"` and the
  resulting `macro_context_state` stays `NEUTRAL` unless the *packet itself*
  declares `macro_freshness_status` (L296-300). Age is recorded
  (`modified_at_utc`, L172-174) but never evaluated. → GAP-438.
- L376 `advisory_fields_for_row` "Return display-only macro fields for one
  governed Lab row." → **HOLDS**: all 21 keys are `macro_*`-prefixed (L413-442)
  and none collides with a governed authority column
  [OBSERVED — cross-checked against the 375-column governed book header; the book's
  own `macro_regime`, `sector_tilt`, `regime_drift_status`, `macro_data_role`
  columns (258-261) are the *only* overlap, and `macro_data_role` is written
  `ADVISORY_ONLY` by both].
**Confidence in this section:** HIGH — all 453 lines read; the advisory-only
claim is verified against both the stripping mechanism and the governed book header.

---

### pipeline_interpreter/evidence_resolver.py
**Classification:** Governed evidence resolver — the single validated entry point
for every production Interpreter command (259 lines).
**Real execution position:** POST-RUN / READ-PATH. Invoked by
`pipeline_interpreter_commands.py:42-48` (import), `:464`
(`resolve_interpreter_run`), `:537` (`resolve_interpreter_evidence`),
`:1643, :2049` (`handoff_status`), and `pipeline_interpreter_engine.py:484`
(`handoff_status`).
**Task in the process:** Locates the newest accepted handoff manifest, validates
it and its hashes through `contracts/interpreter_handoff`, indexes book rows and
bundles by ticker, re-checks book↔bundle identity and authority agreement, applies
an intended-use-dependent freshness gate, loads the advisory macro packet, and
returns one immutable evidence object. It performs filesystem validation only.
**Entry points:** `resolve_interpreter_run` (L104);
`resolve_interpreter_evidence` (L189); `handoff_status` (L236);
`_latest_accepted_manifest` (L91); `_identity_match` (L129);
`_refresh_requirement` (L151).
**Imports (production):** `contracts.interpreter_handoff` (L22-26);
`canonical_data.bundle_freshness.derive_bundle_freshness` (L27);
`macro_context` — `MacroContext`, `load_macro_packet`, `missing_macro_context`
(L28). · **Imported by:** `pipeline_interpreter_commands.py:42`,
`pipeline_interpreter_engine.py:484`. · **Broken/retired imports:** NONE.
Note the import at L28 is `from macro_context import …` (flat), which resolves
only because `pipeline_interpreter/` is on `sys.path` (L18-20).

**Inputs**
- *Files/tables read:* `data/output/runs/*/interpreter/handoff_manifest.json`
  (L31, L93) — **every** run directory is globbed and each candidate manifest is
  fully validated, including hashing every artefact it names (L94-97). All
  further reads are delegated to `contracts/interpreter_handoff`.
- *Upstream fields consumed (with fallback chains):*
  - `published_at_utc` for manifest selection (L98, L101).
  - `required_stage_status.MORNING_GATE` **or** `.morning_gate` (L209) —
    two spellings accepted.
  - `book.selected_contract_symbol → contract_symbol → morning_selected_contract_symbol`
    (L136-140) — the same three-name chain as the contract.
  - Freshness: `derive_bundle_freshness(governed_record + quote_change_evidence)`
    (L157-161), with a **legacy overlay**: for `exact_option_quote`,
    `underlying_quote` and `market_structure`, if the derived state is
    `MISSING`/`INVALID` and the bundle's own `freshness_map` carries a value,
    the **stored** value replaces the derived one (L165-169). This bridges
    **stale ← declared-fresh**: an old bundle's self-reported freshness overrides
    a live derivation that found the timestamps absent. → GAP-439.
- *External calls:* NONE — the docstring's "never imports provider clients and
  never makes API calls" holds (L3-4; imports L10-28 confirm).
- *Config/policy read:* `DEFAULT_RUNS_DIR` (L31);
  `ADVISORY_FRESHNESS_DOMAINS` (L32-36).

**Logic and algorithms**
- **Manifest selection** (L91-101): glob all runs → validate each with
  `require_accepted=True` → discard failures silently (`except HandoffValidationError: continue`,
  L96-97) → pick `max` by the **string** `published_at_utc` (L101). ISO-8601
  strings with a uniform offset sort correctly; mixed offsets or a mix of `Z` and
  `+00:00` would not. → GAP-412.
- **Freshness gate** `_refresh_requirement` (L151-186):
  `TRAJECTORY` → no gate (L154-155);
  `EOD_REVIEW` → allowed `{FRESH, EOD_CURRENT}`; everything else → `{FRESH}` (L156).
  Domains listed in `ADVISORY_FRESHNESS_DOMAINS` are exempt (L173).
  **`market_structure` is in that exemption set** (L35), alongside `macro`,
  `macro_quant_packet`, `news`, `bond`, `auction_calendar`, `catalyst`,
  `supplemental_context`. Market structure supplies `call_wall`, `put_wall`,
  `gamma_flip`, `max_pain`, `wbs_*` and every `trigger_*` field
  (`automation_v2/market_structure.py:13-20`) — the levels an entry trigger and a
  wall-break stop are read from. Exempting it means a stale wall map never raises
  `EVIDENCE_REFRESH_REQUIRED`, while a stale option quote does. → CON-406.
- **Morning-gate precondition** (L207-211): for `EXECUTABLE_SESSION` and
  `INTRADAY_ADVISORY`, `MORNING_GATE` must be `PASS`/`COMPLETED`/`ACCEPTED`, else
  `MORNING_GATE_NOT_COMPLETED`. `EOD_REVIEW` and `TRAJECTORY` bypass this.
- **Authority re-check** `_identity_match` (L129-148): six identity fields plus
  canonical contract, then four authority fields (`governed_direction`,
  `final_action`, `thesis_state`, `olm_guard_disposition`) compared
  book↔`governed_record`. Note this is **four**, where
  `contracts/interpreter_handoff.py:217-222` checks **five** — `capital_permission`
  is checked by the contract but not re-checked here. Defensible as
  non-duplication; recorded because the two lists differ.
- *Decision branches (CALL / PUT / other-blank):* NOT_APPLICABLE — `governed_direction`
  is compared as an opaque string (L147) and never interpreted.

**Computations and formulas (exact)**
- `_canonical_contract(v) = _text(v).upper().replace("O:","").replace(" ","")` (L87-88).
- `allowed = {"FRESH","EOD_CURRENT"} if EOD_REVIEW else {"FRESH"}` (L156).
- `stale_domains = [d for d,s in freshness_map.items() if d.lower() not in ADVISORY_FRESHNESS_DOMAINS and s.upper() not in allowed]` (L170-175).
- `"provider_calls_made": 0` (L185) — a literal, and truthful: no provider is
  reachable from this module.

**Models** — NONE.

**Outputs**
- **Writes nothing.** No `open(...,'w')`, no `mkdir`, no `replace` anywhere in
  the file [OBSERVED — exhaustive read of 259 lines]. It is the only Interpreter
  module that touches the run tree and leaves it unchanged.
- Returns `ResolvedInterpreterRun` (L53-61) and `ResolvedInterpreterEvidence`
  (L64-81), both `frozen=True, slots=True`.
- `handoff_status` returns `{status, run_id, manifest, ticker_count,
  bundle_count, hashes_verified, run_status}` (L243-251) or
  `{status: "BLOCKED", reason, detail}` (L242).
- *Authority-claim fields:* `"hashes_verified": True` (L249) — **HOLDS**: the
  value is only reachable after `validate_handoff_manifest` succeeded, and that
  function hashes every artefact (`contracts/interpreter_handoff.py:284-285`).

**Handoff** — *Receives from:* `<run>/interpreter/handoff_manifest.json` and the
four artefacts it names. *Hands to:* `pipeline_interpreter_commands.py:464, 537`.
*Join keys:* `ticker` (upper-cased); `run_id`; `bundle_id`;
canonical `selected_contract_symbol`.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| No accepted manifest in any run | `EvidenceResolutionError("NO_ACCEPTED_INTERPRETER_HANDOFF")` | L100 |
| Manifest fails validation | `HANDOFF_VALIDATION_FAILED` + underlying code | L112-113 |
| Book ticker blank or duplicated | `BOOK_TICKER_IDENTITY_INVALID` | L117-118 |
| Bundle ticker duplicated | `BUNDLE_TICKER_DUPLICATE` | L123-124 |
| Blank ticker argument | `TICKER_REQUIRED` | L198-199 |
| Ticker not in the handoff | `TICKER_NOT_IN_ACCEPTED_HANDOFF` | L204-205 |
| Book↔bundle identity disagreement | `BOOK_BUNDLE_IDENTITY_MISMATCH:{field}` | L135, L142 |
| Book↔bundle authority disagreement | `BOOK_BUNDLE_AUTHORITY_MISMATCH:{field}` | L148 |
| Morning Gate not complete | `MORNING_GATE_NOT_COMPLETED` | L211 |
| Non-advisory domain stale | `EVIDENCE_REFRESH_REQUIRED:{domains}` | L214-216 |
| Macro packet absent from bundle | `missing_macro_context()` | L217 |
| A candidate manifest is invalid | **silently skipped** | L96-97 |
§10-compliant? **N** — an `EvidenceResolutionError` code vocabulary. `CDS_NARROW_REFRESH_REQUIRED`
(L179) is the nearest analogue of `PENDING_MORNING_REFRESH` but is not the same token.

**Contradictions found here:** CON-406.
**Gaps found here:** GAP-412, GAP-439, GAP-440.
**Comment/docstring claims audited:**
- L1 "Single governed evidence resolver for all production Interpreter commands."
  → **HOLDS**: every MSI command path routes through it
  (`pipeline_interpreter_commands.py:464, 537, 1643, 2049`).
- **L3-5 "The resolver performs filesystem validation only. It never imports
  provider clients and never makes API calls. When current evidence is
  unavailable it returns a narrow, declarative refresh requirement for the
  pipeline/CDS owner."** → **HOLDS**: imports are contract + freshness + macro
  only (L22-28); `_refresh_requirement` returns a declarative dict naming
  `request_type`, `domains` and `provider_calls_made: 0` (L178-186).
- L162-164 "Compatibility for already-published v1 handoffs that predate
  canonical timestamps. New production v3 books are required by the readiness
  gate to carry the timestamps, so their freshness can never use this branch." →
  **PARTIAL**. The compatibility branch behaves as described (L165-169). The
  assertion that v3 books "can never use this branch" is a claim about
  `tools/msi_production_readiness.py`, not about this file; nothing here enforces
  it, and the branch is unconditional — it fires for any bundle whose derived
  freshness is `MISSING`/`INVALID` and whose stored map is populated, regardless
  of schema version. → GAP-439.
- L1 of `handoff_status` — no docstring; behaviour verified at L239-251.
**Confidence in this section:** HIGH — all 259 lines read; the "writes nothing"
claim verified by exhaustive search for write primitives.

---

## F3 — automation_v2 — shadow decision layer

`automation_v2/` is **not imported by any production module in this lane**
[OBSERVED — repository-wide search for `automation_v2` outside `tests/` and the
package itself returns only `run_shadow_automation.bat`, `watch_lab_exports.ps1`,
`automation_v2/README.md` and audit documents]. In particular
`pipeline_interpreter_commands.py` — the sole command router — never references
it. It is reachable only by running one of its own `*_cli.py` entry points, and
`models.py:123-124` raises if `execution_enabled` is ever set. Every section
below therefore carries **Real execution position: POST-RUN / READ-PATH —
shadow-only; not reachable from `route_command`**.

### pipeline_interpreter/automation_v2/veto.py
**Classification:** Deterministic permission lattice — the shadow layer's only
gate (146 lines).
**Real execution position:** POST-RUN / READ-PATH, shadow-only. Invoked by
`automation_v2/core.py` within the shadow run; not reachable from
`pipeline_interpreter_commands.route_command` [OBSERVED].
**Task in the process:** Given one pipeline row, an evidence-findings tuple and
an optional live-validation mapping, it emits a set of veto codes and an
effective verdict. Its second function applies that decision as a one-way
downgrade over whatever verdict the provider proposed.
**Entry points:** `evaluate_sovereign_veto` (L70); `apply_sovereign_overlay` (L128);
`parse_rr` (L50); `_first_value` (L41).
**Imports (production):** `.models` — `CAPITAL_DENIED`, `EXECUTION_NONE` (L12);
`.numeric_validation` — `finite_decimal`, `invalid_or_negative` (L13).
· **Imported by:** `automation_v2/core.py`, `automation_v2/legacy_adapter.py`
(per the package's internal graph). · **Broken/retired imports:** NONE.

**Inputs**
- *Files/tables read:* NONE — operates on mappings passed in.
- *Upstream fields consumed (with fallback chains):*
  - R:R, seven names (L52-62, repeated L80-86): `option_rr` → `option_r_r` →
    `rr` → `r_r` → `r:r` → `risk_reward` → `risk_reward_ratio`. Lookup is
    **case-insensitive** — the row is lower-cased into a new dict on every call
    (L42).
  - Permission, three names (L92-100): `execution_permission` →
    `capital_permission` → `morning_permission`. **Three distinct authority
    fields collapsed into one string**, then tested by substring for
    `DENIED`/`BLOCK`/`STOP` (L102).
  - Live validation, four names (L109-115): `permission` →
    `execution_permission` → `status` → `verdict`. Four vocabularies collapsed
    into one, then matched against `{GO, CONFIRMED, APPROVED, LIVE_CONFIRMED}` (L116).
- *External calls:* NONE. *Config/policy read:* `SovereignPolicy` (L22-25),
  both fields defaulting to `True`.

**Logic and algorithms**
- **`evaluate_sovereign_veto`** (L70-125), four independent tests, all
  accumulating:
  1. `NEGATIVE_RR` if the raw value is absent **or** `invalid_or_negative(rr)`
     (L88-89). Note `invalid_or_negative` returns True for `None` and for
     `value < 0` (`numeric_validation.py:23-26`), so **`rr == 0` does not fire**
     — a zero risk-reward passes this veto.
  2. `UPSTREAM_DENIED` if the coalesced permission string contains `DENIED`,
     `BLOCK` or `STOP` (L102-103).
  3. `EVIDENCE_INVALID` if `policy.block_on_invalid_evidence` and
     `evidence_findings` is non-empty (L105-106).
  4. `LIVE_CONFIRMATION_REQUIRED` if `policy.require_live_confirmation` and the
     live state is not one of the four confirmation tokens (L117-118).
  Codes de-duplicated preserving order (L120). `effective_verdict = "STOP" if
  any code else "WAIT"` (L123). **`eil_action` is the literal `"STOP"`
  unconditionally** (L124) — including in the no-veto branch.
- **`apply_sovereign_overlay`** (L128-146): if already blocked, return unchanged
  (L133-134); if the proposal is `STOP/BLOCK/BLOCKED` → `STOP`; if
  `WAIT/NO_TRADE` → `WAIT` (L135-140); **any other proposal, including `GO`,
  returns `WAIT`** (L142-146). The lattice is genuinely one-way: no path
  produces a verdict stronger than `WAIT`.
- **The default policy makes the veto unconditional.** `SovereignPolicy()` has
  `require_live_confirmation=True` (L24) and `evaluate_sovereign_veto` is called
  with `live_validation=None` by default (L74). `live_validation or {}` (L108)
  then yields `{}`, `live_state` is `""`, `live_confirmed` is False, and
  `LIVE_CONFIRMATION_REQUIRED` is appended for **every row**. Under default
  policy the function can never return an empty `veto_codes` tuple, so
  `effective_verdict` is always `STOP` and `blocked` is always True. → CON-407.
- *Decision branches (CALL / PUT / other-blank):* **NONE — this module never
  reads a direction field.** A veto is applied identically to a CALL, a PUT, an
  `UNRESOLVED`, a `STRANGLE`, a blank and a `NONE`. For a pure downgrade lattice
  this is defensible, and it is recorded as such rather than as a finding.

**Computations and formulas (exact)**
- `parse_rr` (L50-67): take the first non-empty of seven names; then
  `cleaned = str(raw).strip().upper().replace("R","").replace("X","")`
  then `.replace(":","").replace(",","")`; then `finite_decimal(cleaned)`.
  The `.replace("R","")` and `.replace("X","")` are **global, not anchored**, so:
  `"2.5R"` → `"2.5"` ✓; `"1:2"` → `"12"` — a **ratio silently becomes twelve**;
  `"REPAIR"` → `"EPAI"` → `None` → `NEGATIVE_RR`; `"MAX"` → `"MA"` → `None`.
  Units: dimensionless ratio. Bounds: none. Rounding: none — `Decimal` throughout.
  → GAP-415.
- `invalid_or_negative(v)` = `finite_decimal(v) is None or parsed < 0`
  (`numeric_validation.py:23-26`) — note `bool` is rejected explicitly
  (`numeric_validation.py:11-12`), and non-finite `Decimal` values
  (`NaN`, `Infinity`) return `None` (`numeric_validation.py:20`).

**Models** — NONE.

**Outputs**
- Returns `SovereignDecision` (L28-38): `veto_codes`, `effective_verdict`,
  `eil_action`, `execution_permission = EXECUTION_NONE`,
  `capital_permission = CAPITAL_DENIED`. Frozen dataclass; writes no file.
- Atomic promotion: NOT_APPLICABLE. Schema/version field: **NONE** — the
  decision carries no version, so a consumer cannot tell which lattice produced it.
- *Authority-claim fields:* `execution_permission` and `capital_permission` are
  pinned to the module constants by the dataclass defaults (L33-34) and cannot be
  set to anything else by any code path in this file [OBSERVED] — **HOLDS**.

**Handoff** — *Receives from:* `automation_v2/core.py` (pipeline row, evidence
findings, live validation). *Hands to:* `automation_v2/core.py` →
`TickerRunResult` (`models.py:144-159`), whose `__post_init__` re-asserts both
permissions and raises if either was altered (`models.py:171-174`).
*Join keys:* none — the decision is positional to the row.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| R:R absent under all seven names | `NEGATIVE_RR` | L88-89 |
| R:R present but unparseable | `NEGATIVE_RR` (fail-closed) | L88-89 |
| Permission absent under all three names | `""` → no `UPSTREAM_DENIED` (silent pass) | L92-103 |
| Live validation absent | `LIVE_CONFIRMATION_REQUIRED` | L108-118 |
| Evidence findings present | `EVIDENCE_INVALID` | L105-106 |
| No vetoes | `WAIT` + `eil_action = "STOP"` | L123-124 |
§10-compliant? **N** — the vocabulary is
`NEGATIVE_RR / EVIDENCE_INVALID / UPSTREAM_DENIED / LIVE_CONFIRMATION_REQUIRED`.
Note the asymmetry: a missing R:R fails closed (L88), a missing permission fails
**open** (L102 — an empty string contains no `DENIED`/`BLOCK`/`STOP`). The
practical effect is masked by the unconditional `LIVE_CONFIRMATION_REQUIRED`,
but the asymmetry is in the code. → GAP-441.

**Contradictions found here:** CON-407.
**Gaps found here:** GAP-415, GAP-441, GAP-442.
**Comment/docstring claims audited:**
- **L1-4 "Deterministic sovereign permission lattice. Provider analysis may
  preserve or reduce permission, but never promote it."** → **HOLDS**:
  `apply_sovereign_overlay` (L128-146) has no branch returning anything above
  `WAIT`; a provider `GO` is explicitly downgraded (L141-146).
- L131 `apply_sovereign_overlay` "Apply a one-way safety overlay to a provider's
  proposed verdict." → **HOLDS** (L133-146).
- **L141 "The Interpreter is advisory: even a provider GO remains WAIT and cannot
  execute."** → **HOLDS** (L142-146), and is reinforced structurally by
  `models.py:171-174`.
- L24 `require_live_confirmation: bool = True` — no comment, but this default is
  what makes the lattice unconditional under `SovereignPolicy()` (CON-407).
- `numeric_validation.py:1` "Shared fail-closed validation for safety-critical
  numeric inputs." → **HOLDS** (L11-12, L20, L26).
- `numeric_validation.py:24` "Fail closed: invalid numeric input is treated like a
  negative value." → **HOLDS**, and note this makes `rr = 0` **pass**, since
  `0 < 0` is False — a zero-reward trade is not vetoed by `NEGATIVE_RR`. → GAP-442.
**Confidence in this section:** HIGH — all 146 lines read, plus the 33 lines of
`numeric_validation.py` and the relevant 60 lines of `models.py`.

**Veto — direct answer.** `veto.py` vetoes exactly four conditions
(L16-19, L88-118): a missing or negative risk-reward; an upstream permission
string containing `DENIED`/`BLOCK`/`STOP`; any non-empty evidence-findings
tuple; and the absence of an affirmative live confirmation. Its **authority** is
purely subtractive and is declared in the module docstring (L1-4) and enforced by
`apply_sovereign_overlay` (L128-146) and by `models.TickerRunResult.__post_init__`
(`models.py:171-174`), which raises if `execution_permission` is not
`NONE_PIPELINE_INTERPRETER_ONLY` or `capital_permission` is not
`CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION`. It can never grant, promote, or
restore permission. The finding is not that it over-reaches but that under its
default policy it blocks unconditionally (CON-407), which makes the other three
tests unobservable in their effect.

---

### pipeline_interpreter/automation_v2/market_structure.py
**Classification:** Alias-resolving projector for 20 market-structure fields
(97 lines).
**Real execution position:** POST-RUN / READ-PATH, shadow-only. Invoked by
`automation_v2/core.py` via `enrich_trade_brief`; not reachable from
`route_command` [OBSERVED].
**Task in the process:** For each of 20 target field names it walks an alias
list against three sources in a fixed precedence and copies the first present
value; it then synthesises one field that has no source.
**Entry points:** `project_market_structure` (L68); `enrich_trade_brief` (L92);
`_present` (L53).
**Imports (production):** `.models.TickerRunRequest` (L10). · **Imported by:**
`automation_v2/core.py`, `automation_v2/renderers.py` (field names).
· **Broken/retired imports:** NONE.

**Inputs**
- *Files/tables read:* NONE.
- *Upstream fields consumed:* the `ALIASES` table (L22-50), 20 targets with
  1-4 aliases each. In full:
  `call_wall ← call_wall|gex_call_wall`; `put_wall ← put_wall|gex_put_wall`;
  `gamma_flip ← gamma_flip|gex_gamma_flip`; `max_pain ← max_pain|max_pain_level`;
  `gex_regime ← gex_regime|dealer_gamma_state|gamma_regime`;
  `gex_score ← gex_score|eil_gex_score|gex_regime_score`;
  `gamma_island_on_path ← gamma_island_on_path|gamma_island`;
  `gamma_island_level ← gamma_island_level|gamma_island_target`;
  `wbs_score ← wbs_score|wall_break_score`;
  `wbs_grade ← wbs_grade|wall_break_grade`;
  `wbs_wall_price ← wbs_wall_price|wall_price|nearest_wall`;
  `wbs_wall_distance_pct ← wbs_wall_distance_pct|wbs_wall_dist_pct|wall_dist_pct|distance_to_wall`;
  `wbs_entry_guidance ← wbs_entry_guidance|wall_break_entry_guidance`;
  `wbs_stop_guidance ← wbs_stop_guidance|wall_break_stop_guidance`;
  `trigger_primary ← trigger_primary|primary_trigger|entry_trigger|trigger_type`;
  `trigger_quality ← trigger_quality|trigger_grade`;
  `trigger_score ← trigger_score|eil_trigger_score`;
  `trigger_codes ← trigger_codes|trigger_code|trigger_flags`;
  `trigger_go_eligible ← trigger_go_eligible|go_eligible`;
  `trigger_confirmation_state ← trigger_confirmation_state|trigger_status|trigger_state`.
- *External calls:* NONE. *Config/policy read:* the two module tables.

**Logic and algorithms**
- **Source precedence** (L70-72): `request.live_validation` →
  `request.lab_context` → `request.pipeline_row`. Documented at L69 as
  "live > lab > pipeline".
- **Resolution loop** (L74-83): for each target, initialise to `""`, then for
  each source in order, for each alias in order, take the first `_present` value
  and break out of both loops. First-hit wins; no reconciliation, no record of
  which source or alias supplied the value. → GAP-443.
- **`_present`** (L53-65): False for `None` and whitespace-only strings; True for
  `bool`; `Decimal.is_finite()`; `math.isfinite` for `Real`; and for anything
  else, False if the lower-cased string is one of the twelve NaN/Inf spellings
  (L62-65). Note `"NULL"`, `"NONE"`, `"N/A"` and `"-"` are **not** in that set,
  so a row carrying the string `"NONE"` is treated as present and copied through.
  This differs from `contracts/interpreter_handoff._text` (L99-101), which maps
  exactly those tokens to `""`. Two presence definitions coexist in the lane.
  → GAP-444.
- **Synthesis** (L84-88): if `trigger_confirmation_state` resolved to nothing,
  set it to `"CONFIRMED"` when `str(trigger_go_eligible).strip().lower() ∈
  {"1","true","yes","go"}`, else `"NOT_CONFIRMED"`.
- *Decision branches (CALL / PUT / other-blank):* **NONE.** No direction field
  appears in `MARKET_STRUCTURE_FIELDS` or `ALIASES`. A put wall and a call wall
  are projected identically for a CALL row and a PUT row; nothing selects the
  side-relevant wall. `wbs_entry_guidance` / `wbs_stop_guidance` are copied as
  opaque strings.

**Computations and formulas (exact)**
- The only derived value:
  `trigger_confirmation_state = "CONFIRMED" if str(trigger_go_eligible).strip().lower() in {"1","true","yes","go"} else "NOT_CONFIRMED"` (L85-88).
  No units, no bounds, no rounding. Every other field is a verbatim copy.

**Models** — NONE.

**Outputs**
- Returns a 20-key dict (L73-89); `enrich_trade_brief` merges it over a copy of
  the trade brief (L95-97) — **`enriched.update(projected)` means the projection
  overwrites any same-named key already in the trade brief**, including with an
  empty string when nothing resolved. A trade brief that already carried a
  `trigger_quality` loses it to `""` if no alias matched. → GAP-445.
- Writes no file. Atomic promotion: NOT_APPLICABLE. Schema/version field: **NONE**.
- *Authority-claim fields:* NONE written. The docstring's authority claim is
  audited below.

**Handoff** — *Receives from:* `TickerRunRequest.live_validation`,
`.lab_context`, `.pipeline_row` (`models.py:87-94`). *Hands to:*
`automation_v2/renderers.py:111-112` (displays `trigger_primary`,
`trigger_confirmation_state`, `trigger_quality`, `trigger_score` as four adjacent
labelled cells) and `automation_v2/lab_structured.py:28-29, 128`
(exports them as `Trigger_Quality` / `Trigger_Score` columns).
*Join keys:* none — positional to the request.

**Missing-data handling**
| Condition | Emitted value/state | Line |
|---|---|---|
| No alias present in any source | `""` (empty string) | L75 |
| `trigger_confirmation_state` absent and `trigger_go_eligible` truthy | `"CONFIRMED"` | L86-87 |
| `trigger_confirmation_state` absent and `trigger_go_eligible` **absent** | `"NOT_CONFIRMED"` | L85-88 |
§10-compliant? **N** — `""` and `NOT_CONFIRMED` only. The second row of that
table is the finding: absence of `trigger_go_eligible` produces
`str(None).strip().lower() == "none"`, which is not in the truthy set, so the
field is stamped `NOT_CONFIRMED` — a **positive assertion of non-confirmation
derived from missing data**. A consumer cannot distinguish "the trigger was
evaluated and is not confirmed" from "no trigger data reached this projection".
→ GAP-413.

**Contradictions found here:** CON-405, CON-420.
**Gaps found here:** GAP-413, GAP-414, GAP-443, GAP-444, GAP-445.
**Comment/docstring claims audited:**
- **L1 "Deterministic market-structure projection from authoritative pipeline
  inputs."** → **PARTIAL on both halves.** *Deterministic*: **HOLDS** — the
  resolution order is fixed and total (L74-83). *From authoritative pipeline
  inputs*: **FALSE** — `pipeline_row` is the **last** source consulted (L71).
  `live_validation` and `lab_context` are both preferred over it (L70-72), so a
  value present in the governed pipeline row is discarded whenever either of the
  two upstream mappings carries any non-empty value under any alias. → CON-405.
- **L69 `project_market_structure` "Resolve fields using explicit source
  precedence: live > lab > pipeline."** → **HOLDS** as a description of L70-72,
  and it is the precise statement of CON-405: the docstring at L1 calls the
  pipeline authoritative while the docstring at L69 ranks it third.

**Recomputation — direct answer.** The question for this file is whether it
recomputes a concept the pipeline already owns. The answer is **one field, and
only one**:

- **19 of the 20 fields are pure alias copies** (L74-83). No arithmetic, no
  re-derivation, no reconciliation. Copying under a different name is an
  **alias**, not a recompute — recorded in `_lane_F_fields.csv` with
  `write_type=alias`.
- **`trigger_confirmation_state` is a recompute** (L84-88). The pipeline owns a
  trigger confirmation concept: the governed book carries `trigger_data_state`,
  `trigger_price_source`, `trigger_evidence`, `trigger_primary`,
  `trigger_quality`, `trigger_score` and `trigger_codes` [OBSERVED — book header
  columns 344-351]. This module derives a **new categorical**
  (`CONFIRMED`/`NOT_CONFIRMED`) from `trigger_go_eligible`, under a name
  (`trigger_confirmation_state`) that the governed book does not carry, and then
  overwrites any existing value of that name in the trade brief (L96). That is a
  **DUPLICATE_WRITER** finding. → CON-420.

**The alleged `trigger_quality ← trigger_score` fallback — direct answer.**
It **does not exist in `automation_v2`**. `trigger_quality` and `trigger_score`
are kept in **separate, non-overlapping alias families** at L43 and L44:
`trigger_quality ← ("trigger_quality","trigger_grade")` — both categorical;
`trigger_score ← ("trigger_score","eil_trigger_score")` — both numeric. No
numeric name appears in the quality family and no categorical name appears in the
score family [OBSERVED L43-44]. `renderers.py:111-112` renders them as two
distinct labelled cells ("Quality", "Score") and `lab_structured.py:128` exports
them as two distinct columns. Verdict for this module: the alleged
categorical←numeric bridge is **NOT PRESENT**. The genuine categorical-from-
non-categorical bridge in this file is `trigger_confirmation_state ←
trigger_go_eligible` (boolean → categorical, L85-88), recorded as GAP-413/CON-420.

**A separate finding on the same table.** `wbs_score ← ("wbs_score","wall_break_score")`
(L31). The governed book's column is **`wbs`** [OBSERVED — book header column
313], not `wbs_score` and not `wall_break_score`. Neither alias matches, so
`wbs_score` projects to `""` against the governed book, while
`wbs_grade` (column 314), `wbs_wall_price` (315) and `wbs_wall_dist_pct` (316,
matched by the third alias at L35) all resolve. The projection silently drops the
score while keeping the grade. → GAP-414.
`NEEDS_MEASUREMENT:` `python -c "import csv;r=next(csv.DictReader(open(r'data/output/runs/20260831_010309/intelligence_lab/final_opportunity_book_20260831_010309.csv',encoding='utf-8-sig')));print([k for k in r if k.startswith('wbs')])"`
and confirm `wbs_score` is absent while `wbs` is present.
**Confidence in this section:** HIGH — all 97 lines read; alias mismatch
cross-checked against the evidence run's book header.

---
