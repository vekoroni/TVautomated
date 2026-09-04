# Part G — Peripheral packages: orchestrator/, market_structure/, ml_confidence_layer/, news_terminal/, ma_cockpit/, short_swing/, zero_dte/, bridge/

_26 files. All are classified LIBRARY: each is imported by something inside its
own package, which is why they fall in atlas scope rather than the appendix —
but **no orchestrated path reaches any of them**, established per file below.
Facts extracted by `_tooling/extract_facts.py`; sections written in the main
session._

---

### orchestrator/claude_api.py
**Classification:** LIBRARY · **DEAD STUB** (16 lines)
**Real execution position:** NOT_INVOKED. Instantiated at `orchestrator/main.py:70`, called at `:218` and `:222`, both unreachable — `orchestrator/main.py` is entered only from `run.py:25`, which no `.bat`, `.ps1`, `.sh` or scheduled task launches [OBSERVED]
**Task in the process:** Nominally the macro and futures-bias analysis layer of the legacy orchestrator.
**Entry points:** `ClaudeIntelligence.analyze_macro()` (`:12`), `analyze_futures()` (`:15`)
**Imports (production):** `json`, `os`, `from anthropic import Anthropic` (`:1-3`) · **Imported by:** `orchestrator/__init__.py:8`, `orchestrator/main.py:7` · **Broken/retired imports:** `Anthropic` imported at `:3` and **never used** — the class is never constructed, so the import exists only to make the module fail at import time if the SDK is absent

**Inputs** — Files: `config_path` JSON opened at `:7` with **no encoding argument and no existence check**. Config: `ANTHROPIC_API_KEY` from the environment with the literal default `'DUMMY'` (`:9`). External calls: **NONE**
**Logic and algorithms** — NONE. Decision branches: NONE (CALL / PUT / other-blank all NOT_APPLICABLE)
**Computations and formulas (exact)** — NONE
**Models** — **NONE, despite appearances.** `config/settings.json:41-45` declares `claude_api.model = "claude-sonnet-4-20250514"`, `max_tokens: 16000`, `temperature: 0.0`. The config is loaded into `self.config` (`:8`) and never read; `self.client = None` (`:10`) is set and never assigned. No API call is made anywhere in the file
**Outputs** — `analyze_macro` returns the string `'Macro analysis placeholder'` (`:13`); `analyze_futures` returns `'Futures analysis placeholder'` (`:16`). Both are passed to `report_generator.generate()` (`main.py:236-237`) and rendered under headings "MACRO MODULE ANALYSIS" and "FUTURES BIAS ANALYSIS", then emailed. Atomic promotion: NOT_APPLICABLE. Schema/version field: NONE. Authority-claim fields: NONE
**Handoff** — Receives file lists from `main.py:218,222`; hands placeholder strings to the PDF renderer. Terminal
**Missing-data handling** — Both methods accept `csvs` and `images` and **discard both arguments unread**, so the entire upstream readiness-gating apparatus assembles inputs that are then thrown away. §10-compliant? **N**
**Contradictions found here:** the class is named `ClaudeIntelligence` and the config block is named `claude_api` with a real model id, max-tokens and temperature — an arrangement that reads as a configured live LLM integration. It is not. With `email.enabled = true` (`config/settings.json:56`) the lane is configured to distribute a report whose analytical content is two placeholder sentences
**Gaps found here:** GAP-600 (BOM), DEAD STUB
**Comment/docstring claims audited:** the file has **no docstrings and no comments**; the only claims are the method names `analyze_macro` / `analyze_futures` → **FALSE** as descriptions of behaviour
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/main.py
**Classification:** LIBRARY · **DEAD** legacy orchestrator (v2.0.0 config), superseded by `intelligent_orchestrator.py`
**Real execution position:** NOT_INVOKED. Only entry is `run.py:25`, referenced by no launcher or scheduled task [OBSERVED]
**Task in the process:** Would wait for a day's CSV/chart/screenshot drop, call Claude for macro and futures analysis, optionally run Options Intelligence, render a PDF and email it.
**Entry points:** `AVSHUNTEROrchestrator.run()` (`:113`)
**Imports (production):** `.data_monitor`, `.claude_api`, `.report_generator`, `.email_sender` (`:6-9`); lazy `.options_intelligence` (`:106`) · **Imported by:** `run.py:25`, `orchestrator/__init__.py:6` · **Broken/retired imports:** NONE at import time; see Contradictions for the call-time failure

**Inputs** — Files: `config/settings.json` (`:37`, with `encoding='utf-8'`). Env: `AVSHUNTER_CONTEXT_DIR`, `AVS_ENABLE_OPTIONS` (`:46`, `:96`). Sets `AVSHUNTER_MACRO_PATH` and `AVSHUNTER_UNIVERSE_PATH` from pinned artefacts (`:55`, `:58`). 15 fallback chains detected [OBSERVED, extractor]
**Logic and algorithms** — Monitor-mode poll loop (`:123-158`); immediate-mode governance gates (`:160-198`). Decision branches: **NONE** — this file has no direction concept (CALL / PUT / other-blank all NOT_APPLICABLE)
**Computations and formulas (exact)** — `timeout = monitoring.timeout_minutes * 60` (`:128`)
**Models** — declared in config but never used; see `claude_api.py`
**Outputs** — `reports/AVSHUNTER_Intelligence_<date>[_<session>].pdf` via the report generator; an email with that attachment (`:249-253`). Atomic promotion: **no**. Schema/version field: NONE
**Handoff** — Terminal: the PDF and email end this lane; nothing in the production pipeline reads either
**Missing-data handling** — Zero inputs → `RuntimeError("BLOCKED: Zero inputs …")` unless `immediate_discovery_only` (`:177-181`); partial inputs → `RuntimeError("BLOCKED: Data incomplete …")` unless `immediate_allow_incomplete` (`:183-193`). Both flags are `false` in `config/settings.json:6-7`, so immediate mode **fails closed** — the correct posture. Options load failure → `self.options = None` with a warning (`:109-111`). §10-compliant? **N** — raises rather than emitting typed states
**Contradictions found here:** `:107` `self.options = OptionsIntelligence()` passes no argument while `orchestrator/options_intelligence.py:109` is `def __init__(self, config)`. Every invocation raises `TypeError`, caught at `:109` and logged as "failed to load (skipping)". The archived variant `orchestrator/main_archive.py:31` calls `OptionsIntelligence(self.config)` **correctly** — the working signature survives only in the archive. Separately, `config/settings.json` has no `features` key, so `:94` `oi_cfg.get("enabled", False)` is `False` and the lazy import normally never runs, meaning the `TypeError` is never even reached
**Gaps found here:** DEAD
**Comment/docstring claims audited:** `:90` "Options Intelligence is optional; import lazily so it can't break core runs" → **HOLDS**. `:164-166` "Governance: fail-closed by default in immediate mode" → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/options_intelligence.py
**Classification:** LIBRARY · **DEAD** stale v4.1 engine, superseded by `scripts/avshunter_options_intelligence.py` (8,500+ lines vs 938 here)
**Real execution position:** NOT_INVOKED. Reachable only via `orchestrator/main.py:106-107`, itself unreachable [OBSERVED]
**Task in the process:** Would generate 50–100 tiered stock signals daily from Wyckoff + Crabel Precor + a macro regime read, exporting `reports/tier{1,2,3}_signals_*.csv`.
**Entry points:** `OptionsIntelligence.scan_options()` (`:497`)
**Imports (production):** `orchestrator.wyckoff_engine` (`:68`, a 4-line shim re-exporting `WyckoffEngine_3101_v2`); optional `wyckoff_crabel_precor_logic_v2` (`:72`), `orchestrator.macro_loader` (`:81`), `PyPDF2` (`:88`) · **Imported by:** `orchestrator/main.py:106`, `orchestrator/main_archive.py:9` · **Broken/retired imports:** **`logger` is never defined at module level** yet is called at `:74`, `:77`, `:85`, `:93`, `:371`, `:376`, `:379`. `:74` sits inside a `try/except ImportError`, so a *successful* import of the Crabel module raises an uncaught `NameError` at module import

**Inputs** — Files: `config/tickers.csv` (`:113`), `config/options_settings.json` (`:172`), `reports/daily/*macro*.pdf` (`:229`). External: Polygon aggregates (`:921`) and snapshot (`:877`), memoised in `self._price_cache` (`:914-937`). Config: `config/settings.json` has no `features` key, so the module is disabled by default
**Logic and algorithms** — Multi-tier Crabel compression scan (`:398`); Simons-style tiered thresholds (`:136-146`); regime validation GREEN/YELLOW/RED (`:358-380`)
**Decision branches** — **FINDING.** `:722` `direction = 'CALL' if wyckoff_result['trade_direction'] == 'LONG' else 'PUT'`. **CALL path:** `LONG` → CALL. **PUT path:** everything else → PUT. **Other/blank path:** `NONE`, `SHORT` and `""` all become PUT; `NONE` is caught later (`:770-771`, `:784-785`) but only inside the `CRABEL_PRECOR_AVAILABLE` branch, so an unexpected token such as `SHORT` silently produces PUT. `:764-768` Precor override: `BUYERS→CALL`, `SELLERS→PUT`, anything else → `return None`. RED-regime sizing `:595-599`: `effective_size = 0.75 if direction == 'PUT' else 0.10` — CALL and any other value share the 0.10 branch
**Computations and formulas (exact)** — `prob = min(base + 0.10, 0.90)` T1 / `+0.05, 0.80` T2 / `min(base, 0.70)` T3 where `base = wyckoff_score/100` (`:666-674`); `CRABEL_READY +0.08 → cap 0.92`, `COILING +0.04 → cap 0.88` (`:677-680`); `BUY_SETUP/SELL_SETUP +0.03`, `intent_conf>70 +0.02`, `transition_conf>70 +0.02`, `control in (BUYERS,SELLERS) +0.02`, each capped 0.92 (`:682-693`); `compression = atr7/atr20` against `0.55/0.65/0.75` (`:136-138`)
**Models** — "Jim Simons-Inspired Signal Generator v4.1" (`:98`); rule-based, hand-set constants; no calibration source claimed; version tag in the docstring only
**Outputs** — `reports/tier{n}_signals_{YYYY-MM-DD_HHMM}.csv` (`:819`), 23 fields including `direction`, `win_probability`, `position_size_mult`, `direction_confirmed` (`:821-829`); `reports/outcomes.csv` header (`:214-219`). No atomic promotion, no schema/version field
**Handoff** — Receives nothing from the production pipeline; hands to `orchestrator/report_generator.py:68-87` only. Join key: `ticker`
**Missing-data handling** — `_get_universe()` (`:845-862`) is a three-deep silent fallback CSV → dynamic Polygon → static 30-ticker hardcoded list, each guarded by a bare `except: pass` (`:852-853`, `:859-860`). Price fetch failure → `except Exception: pass` then caches `None` (`:935-937`). Whole-ticker scan failure → `except Exception: continue` (`:618-619`), so a signal can vanish with no record. No macro data → `('ABORT', 0.0, "No macro data")` (`:360-361`). §10-compliant? **N**
**Contradictions found here:** see `main.py` — the constructor mismatch makes this module unloadable even on its one reachable path
**Gaps found here:** DEAD; the undefined `logger` means the module cannot be imported cleanly when its optional dependency is present
**Comment/docstring claims audited:** `:7-8` "ALWAYS Generate Tradeable Signals — never zero output" → **FALSE** (every tier gates on `win_prob < threshold` at `:588-589`, and `scan_options` returns `signal_count: 0` on missing macro at `:514`). `:842` "Universe & data methods (unchanged from v4.0)" → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/report_generator.py
**Classification:** LIBRARY · **DEAD** PDF renderer
**Real execution position:** NOT_INVOKED. Reachable only via `orchestrator/main.py:235`, itself unreachable
**Task in the process:** Renders a three-section PDF (macro, futures bias, options intelligence) from strings and a signals dict.
**Entry points:** `ReportGenerator.generate()` (`:12`)
**Imports (production):** reportlab (`:3-6`) · **Imported by:** `orchestrator/__init__.py:9`, `main.py:8`, `main_archive.py:7` · **Broken/retired imports:** NONE, though `reportlab` appears nowhere else in the tree
**Inputs** — `macro_analysis`, `futures_analysis` (strings), `options_analysis` (dict), `date`, `session` (`:12`)
**Logic and algorithms** — Sequential flowable assembly with page breaks (`:54`, `:65`). Decision branches: **NONE** — the options section prints `signal` values verbatim (`:83`) without inspecting direction, so a CALL and a PUT render identically (CALL / PUT / other-blank all NOT_APPLICABLE)
**Computations and formulas (exact)** — NONE
**Models** — NONE
**Outputs** — `reports/AVSHUNTER_Intelligence_<date>[_<session>].pdf` (`:20-21`); `reports/` created with `mkdir(exist_ok=True)` (`:16`) — a **relative** path, so output location depends on the process working directory. No atomic promotion, no schema/version field
**Handoff** — Receives from `main.py:235`; the returned path becomes the email attachment (`main.py:252`). Terminal
**Missing-data handling** — `options_analysis['status'] == 'error'` → renders `"Error: {message}"` (`:71-72`); `signal_count == 0` → renders "No qualifying signals found. All tickers scanned with 15-filter criteria." (`:86`). **`options_analysis` is accessed by direct subscript** at `:71`, `:74`, `:82`, but `main.py:226-230` sets it to `None` whenever the options module did not load — the normal case — so `None` raises `TypeError: 'NoneType' object is not subscriptable` at `:71`. The one path that reaches this file crashes on the standard configuration. §10-compliant? **N**
**Contradictions found here:** `:86` asserts "All tickers scanned with 15-filter criteria"; the engine that would populate this section implements a tiered Crabel/Wyckoff/win-probability cascade, not a 15-filter scan — a residue of an earlier version printed to the reader as fact
**Gaps found here:** GAP-600 (BOM); DEAD; `textColor='#1a1a1a'` (`:33`) passes a string where reportlab expects a colour object — a latent failure on the title style
**Comment/docstring claims audited:** `:67` "NEW: Options Intelligence Section" → **PARTIAL** (section exists; the feature feeding it cannot load). `:86` "15-filter criteria" → **FALSE**
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/data_monitor.py
**Classification:** LIBRARY · **DEAD** readiness poller (42 lines)
**Real execution position:** NOT_INVOKED. Instantiated at `orchestrator/main.py:71`, itself unreachable. Note it is **not** exported in `orchestrator/__init__.py`, unlike its dead twin `DataCollector`
**Task in the process:** Counts CSVs, charts and screenshots in the day's folder and returns a readiness verdict for the monitor loop.
**Entry points:** `DataMonitor.check_status()` (`:13`)
**Imports (production):** pathlib (`:1`, BOM-prefixed) · **Imported by:** `main.py:6`, `main_archive.py:5` · **Broken/retired imports:** NONE
**Inputs** — `config['data_paths'][...]` (`:9-11`) and `config['expected_files']['screenshots_min']` (`:22`) — all **direct subscripts**, so a config missing any key raises rather than defaulting
**Logic and algorithms** — Glob-and-count with a three-part predicate. Decision branches: NONE (NOT_APPLICABLE)
**Computations and formulas (exact)** — `has_csvs = len(csvs) > 0`; `has_charts = len(charts) > 0`; `has_screenshots = len(screenshots) >= 8`; **`ready = has_csvs and has_screenshots`** (`:24-29`) — charts are counted and surfaced but **never gate readiness**
**Models** — NONE
**Outputs** — a dict of counts, booleans and file lists (`:31-41`). Writes nothing
**Handoff** — Returns to `main.py:133` (monitor loop) and `:162` (immediate mode). Terminal
**Missing-data handling** — Every folder read guarded by `if <folder>.exists() else []` (`:17-19`), so absent directories are indistinguishable from empty ones. **No staleness check**: a folder of last week's files reads as ready. §10-compliant? **N**
**Contradictions found here:** `main.py:190-191` lists charts among the blocking `missing` items, but `ready` never depended on charts — so immediate mode can raise `"BLOCKED: Data incomplete … Charts (found 0)"` for a condition the readiness rule does not test. The block message and the block predicate disagree
**Gaps found here:** GAP-600 (BOM); GAP-601 (duplicated readiness logic, drifted)
**Comment/docstring claims audited:** `:21` "Check requirements" → **PARTIAL** (charts collected as a requirement, not enforced as one)
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/collector.py
**Classification:** LIBRARY · **DEAD** — exported but never used
**Real execution position:** NOT_INVOKED. Exported by `orchestrator/__init__.py:7` and listed in `__all__` (`:14`), but **no module instantiates `DataCollector`** — `main.py` uses `DataMonitor` instead (`:71`) [OBSERVED]
**Task in the process:** Would create and inventory `data/daily/<date>/{csvs,charts,screenshots}` and report readiness.
**Entry points:** `DataCollector.get_today_folder()` (`:20`), `check_data_ready()` (`:28`), `collect_all_data()` (`:72`), `get_summary()` (`:110`)
**Imports (production):** os, json, pathlib, datetime, typing (`:5-9`) — **`os` imported and unused** · **Imported by:** `orchestrator/__init__.py:7` only · **Broken/retired imports:** NONE
**Inputs** — `config/settings.json` opened **without an explicit encoding** (`:13`), unlike `main.py:37`. Reads `data_paths.base_dir`, `expected_files.screenshots_min`
**Logic and algorithms** — Directory globbing and a three-part readiness test. Decision branches: NONE (NOT_APPLICABLE)
**Computations and formulas (exact)** — `ready = has_data and has_screenshots` where `has_screenshots = len(screenshots) >= 8` (`:54-59`). `has_charts` computed at `:56` and reported in `missing` at `:63-64` but **excluded from `ready`** — identical asymmetry to `data_monitor.py`
**Models** — NONE
**Outputs** — Creates `csvs/`, `charts/`, `screenshots/` as a side effect of `get_today_folder()` (`:22-25`). Returns dicts and a formatted string; writes no data files
**Handoff** — NONE — nothing consumes it
**Missing-data handling** — Every directory read guarded by `if <dir>.exists()` (`:40`, `:44`, `:49`). **`collect_all_data()` (`:72-108`) has no such guard** — it globs `self.data_dir / "csvs"` at `:83`, which raises if the directory was never created; the method is only safe if `get_today_folder()` ran first, and nothing enforces that ordering. §10-compliant? **N**
**Contradictions found here:** GAP-601 — `check_data_ready` (`:28`) and `DataMonitor.check_status` (`data_monitor.py:13`) implement the **same readiness rule twice** with different return shapes (tuple vs dict) and different glob coverage: `DataMonitor` accepts `*.png` **and** `*.jpg` (`data_monitor.py:18-19`), this file accepts `*.png` only (`:46`, `:51`). Two implementations of one contract that disagree on which files count
**Gaps found here:** GAP-601; DEAD; missing encoding on the config read (`:13`) is a latent Windows failure given the BOM-prefixed siblings
**Comment/docstring claims audited:** `:29` "Check if all required data is present" → **PARTIAL** (charts described as required, not required for `ready`)
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/email_sender.py
**Classification:** LIBRARY · **DEAD** SMTP sender (40 lines)
**Real execution position:** NOT_INVOKED. Instantiated at `orchestrator/main.py:73`, called at `:249`, both unreachable
**Task in the process:** Sends the generated PDF to a single recipient over Gmail SMTP.
**Entry points:** `EmailSender.send(subject, body, attachments)` (`:18`)
**Imports (production):** smtplib, email.mime.*, dotenv (`:1-7`, BOM-prefixed) · **Imported by:** `orchestrator/__init__.py:10`, `main.py:9`, `main_archive.py:8` · **Broken/retired imports:** NONE
**Inputs** — `.env` via `load_dotenv()` (`:11`); `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL` (`:14-16`); `config['email']['from_name']` (`:22`)
**Logic and algorithms** — MIME multipart assembly (`:21-34`); STARTTLS session (`:37-40`). Decision branches: NONE (NOT_APPLICABLE)
**Computations and formulas (exact)** — NONE. Hardcoded `smtp.gmail.com:587` (`:37`)
**Models** — NONE
**Outputs** — an outbound email. No local artefact, no log line, **no return value** — a successful send and a silently-dropped one are indistinguishable to the caller
**Handoff** — Receives the report path from `main.py:252`. Terminal
**Missing-data handling** — **NONE, and that is the finding.** `os.getenv` at `:14-16` returns `None` with no default and no check, so an unset variable yields `msg['To'] = None` (`:23`) or `server.login(None, None)` (`:39`), raising *after* the PDF has been written. `config['email']['from_name']` (`:22`) is a direct subscript. Attachment files are opened without existence checks (`:31`). §10-compliant? **N**
**Contradictions found here:** `config/settings.json:56` sets `"enabled": true`, so this lane is configured to send live email on every run — while the body it would send accompanies a PDF whose two principal sections contain `'Macro analysis placeholder'` and `'Futures analysis placeholder'`
**Gaps found here:** GAP-600 (BOM); DEAD. Note as the **contrast case**: unlike the two LLM engine files in this part, it does **not** hardcode a fallback secret, which is the correct pattern
**Comment/docstring claims audited:** `:19` "Send email with optional attachments" → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### orchestrator/macro_loader.py
**Classification:** LIBRARY · DEAD (299 lines)
**Real execution position:** NOT_INVOKED. Imported by `orchestrator/options_intelligence.py:81`, itself unreachable
**Task in the process:** Docstring: "AVSHUNTER Macro Intelligence Loader v1.1 — Replaces PDF parsing with J[SON]" — loads a macro JSON contract for the legacy engine's regime read.
**Entry points:** see `_tooling/facts/` — module-level loader functions
**Imports (production):** stdlib + json · **Imported by:** `orchestrator/options_intelligence.py:81` · **Broken/retired imports:** NONE
**Inputs** — a macro JSON path; 4 fallback chains detected [OBSERVED, extractor]
**Logic and algorithms** — JSON load and field normalisation. Decision branches: no direction branch detected (0 direction tokens) — NOT_APPLICABLE for CALL / PUT / other-blank
**Computations and formulas (exact)** — NOT_ESTABLISHED — not read in detail; extractor reports no numeric-assignment cluster
**Models** — NONE
**Outputs** — 1 write site detected [OBSERVED, extractor]; target NOT_ESTABLISHED. Atomic promotion: NOT_ESTABLISHED. Schema/version field: NOT_ESTABLISHED
**Handoff** — Would hand a macro contract to the legacy options engine. Terminal in practice
**Missing-data handling** — NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** DEAD
**Comment/docstring claims audited:** "Replaces PDF parsing with JSON" → **PARTIAL** — `orchestrator/options_intelligence.py:229` still globs `reports/daily/*macro*.pdf` and `:88` still imports `PyPDF2`, so the PDF path it claims to replace is still present in its only consumer
**Confidence in this section:** LOW — extractor facts and consumer cross-reference only; the file body was not read. Listed here for coverage; its DEAD status is HIGH confidence, its internals are UNTRACED

---

### market_structure/profile.py
**Classification:** LIBRARY (reached from the **morning** path)
**Real execution position:** Morning — `morning_gate.py:3216` imports `calculate_market_structure_evidence`, called at `:3291` from `_enrich_msi_market_structure` (entered at `:3004`); this module is reached via `market_structure/service.py:52`
**Task in the process:** Builds a one-minute-estimated market profile (price bins, TPO counts, estimated volume, POC, value area) and detects a double distribution.
**Entry points:** `build_market_profile()` (`:44`), `detect_double_distribution()` (`:77`), `profile_bin_width()` (`:30`), `round_to_tick()` (`:25`)
**Imports (production):** numpy, pandas, `.params` (`:8-10`) · **Imported by:** 5 modules incl. `market_structure/__init__.py:4`, `service.py:16` · **Broken/retired imports:** NONE
**Inputs** — a bars DataFrame requiring `{timestamp_utc, high, low, close, volume}` (`:45`); optional `session_segment` filtered to `REGULAR` (`:49`); `exchange_tick`, `atr14`, `regular_open_utc`. **No external calls, no config file, no I/O** — all parameters arrive as `MSParams` [OBSERVED]
**Logic and algorithms** — TPO period assignment and volume allocation (`:56-62`); POC and value-area expansion (`:35-41`, `:65`); peak/valley double-distribution detection with five rejection conditions (`:77-107`)
**Decision branches** — no CALL/PUT here; direction is `second_direction ∈ {"ABOVE","BELOW"}` (`:104`) derived from `lower_first`. **Both arms symmetric; no third state needed** — if no candidate qualifies the function returns `{"detected": False, …}` (`:107`) rather than a directional default. Mapping to CALL/PUT happens in `lifecycle.py:23-24`. **Other/blank path:** returns the named not-detected result
**Computations and formulas (exact)**
- `round_to_tick = round(max(tick, round(value/tick)*tick), 10)` (`:27`), raising on non-positive input (`:26`)
- `bin_width = round_to_tick(max(exchange_tick, atr14/40.0), exchange_tick)` (`:32`, divisor `params.bin_divisor = 40.0`), raising if `atr14` non-finite or ≤ 0 (`:31`)
- bin ladder `bottom = floor(low.min()/width)*width`, `top = ceil(high.max()/width)*width` (`:53`)
- `period = max(0, int((ts − open_ts).total_seconds() // (30*60)))` (`:60`)
- `allocation = max(0.0, volume)/len(indexes)` (`:61`) — volume split **evenly across every touched bin**: an explicit estimator, not observed at-price volume
- `poc_index = flatnonzero(counts == counts.max())[-1]` (`:65`) — ties resolved to the **highest** price
- value area accumulates to `counts.sum()*0.70` (`:36`), expanding to the greater-count side, preferring `high` on ties (`:39`)
- detection: `threshold = quantile(nonzero_counts, 0.60)` (`:80`); valley bins `counts[i] <= weak*0.50` (`:86`); `len(run) >= 2` (`:91`); peak separation `>= max(3*bin_width, 0.30*atr14)` (`:94`); each region `>= total_tpo*0.20` (`:96`); chronology separation at the 0.40 share threshold (`:97-98`); winner `max(candidates, key=abs(second_low − first_low))` (`:107`)
**Models** — not a fitted model. `MS_PARAMS_V1` is labelled `calibration_status = "PROPOSED_NOT_CALIBRATED"` (`params.py:10`). Version tag `ms_params_v1`
**Outputs** — returns a frozen `MarketProfile` dataclass (`:13-22`) and a detection dict (`:101-107`). Writes no files; persistence is `service.py`'s job
**Handoff** — Receives bars from `service.calculate_market_structure_evidence` (`service.py:52`); hands profile and structure to `service._metrics` (`:22`)
**Missing-data handling** — Empty frame or missing columns → `MarketProfile(…, "INSUFFICIENT_DATA", …)` (`:46-47`); empty after the REGULAR filter → same (`:51`); no TPO counts → `INSUFFICIENT_DATA` with width preserved (`:64`). Detection: `< 7` bins or `total_tpo <= 0` → `{"detected": False, "reason": "INSUFFICIENT_PROFILE"}` (`:79`); no qualifying candidate → `"NO_QUALIFYING_DOUBLE_DISTRIBUTION"` (`:107`). **Every degraded path is named, not defaulted** — the strongest missing-data discipline in the audit. §10-compliant? **N** in vocabulary, but semantically equivalent and complete
**Contradictions found here:** NONE
**Gaps found here:** GAP-602 — `data_quality` is `"ONE_MINUTE_ESTIMATED"` (`:67`) whenever any profile is built, regardless of the actual bar interval supplied; the label asserts a provenance this function never verifies
**Comment/docstring claims audited:** `:1` "Deterministic one-minute-estimated TPO and volume profile calculations" → **HOLDS** for determinism (no RNG, no clock, no I/O); **PARTIAL** for "one-minute-estimated", which is asserted rather than checked
**Confidence in this section:** HIGH — file read end to end

---

### market_structure/params.py
**Classification:** LIBRARY (morning path) · frozen calibration-seed dataclass (28 lines)
**Real execution position:** Morning, via `service.py:15` and `profile.py:10`; instantiated once as `MS_PARAMS_V1` (`:28`)
**Task in the process:** Supplies the sixteen thresholds governing profile construction, double-distribution detection, acceptance and lifecycle repair, plus the version and calibration-status tags stamped into every evidence record.
**Entry points:** `MSParams` (`:8`), `MS_PARAMS_V1` (`:28`)
**Imports (production):** dataclasses (`:4`) · **Imported by:** 8 modules — `market_structure/__init__.py:3`, `profile.py:10`, `service.py:15`, `lifecycle.py:4` · **Broken/retired imports:** NONE
**Inputs** — **NONE.** No file, no environment variable, no external call; every value is a literal default [OBSERVED]
**Logic and algorithms** — NONE (declarative). Decision branches: NONE — direction-neutral by construction, which is why the same thresholds apply symmetrically to `ABOVE` and `BELOW` structures (CALL / PUT / other-blank all NOT_APPLICABLE)
**Computations and formulas (exact)** — `version = "ms_params_v1"` (`:9`); `calibration_status = "PROPOSED_NOT_CALIBRATED"` (`:10`); `bin_divisor = 40.0` (`:11`); `tpo_period_minutes = 30` (`:12`); `value_area_share = 0.70` (`:13`); `region_share = 0.20` (`:14`); `peak_percentile = 0.60` (`:15`); `valley_ratio = 0.50` (`:16`); `valley_min_bins = 2` (`:17`); `separation_atr = 0.30` (`:18`); `separation_min_bins = 3` (`:19`); `chronology_share = 0.40` (`:20`); `acceptance_minutes = 30` (`:21`); `acceptance_five_minute_closes = 3` (`:22`); `acceptance_volume_share = 0.10` (`:23`); `intact_repair = 0.20` (`:24`); `failed_repair = 0.60` (`:25`)
**Models** — NOT_APPLICABLE — these are seeds, not fitted parameters, and `calibration_status` says so
**Outputs** — `version` and `calibration_status` are emitted into every persisted record as `ms_parameter_set_version` and `ms_parameter_calibration_status` (`service.py:64`), and `version` enters the `evidence_id` lineage hash (`service.py:60`). Authority-claim field `calibration_status = "PROPOSED_NOT_CALIBRATED"` → **HOLDS**, and is the **only** place in this audit where an uncalibrated threshold set declares itself as such in its own output
**Handoff** — Hands thresholds to `profile.py` and `service.py`; hands `version` into the evidence identity
**Missing-data handling** — NOT_APPLICABLE — `frozen=True, slots=True` (`:7`) makes the instance immutable; every field has a default so no construction can fail
**Contradictions found here:** NONE
**Gaps found here:** GAP-603 — the sixteen thresholds carry no provenance beyond the label: no source, date, sample or study is cited, and no calibration artefact exists in the tree. Because `version` is part of the `evidence_id` lineage, changing a threshold **without** bumping `version` would silently produce a different result under an unchanged identity; the version string is the only guard and nothing enforces that it moves when a value does
**Comment/docstring claims audited:** `:1` "Versioned MSI calibration seeds; not empirically accepted thresholds" → **HOLDS**, and is correctly propagated to persisted output rather than remaining a source-only caveat — the direct contrast with `ml_confidence_layer/ml_confidence_engine.py:406-418`, where an equivalent hand-set weight block carries no calibration status
**Confidence in this section:** HIGH — file read end to end

---

### market_structure/lifecycle.py
**Classification:** LIBRARY (morning path) · 25 lines
**Real execution position:** Morning, via `service.py:14`; `transition_lifecycle` called at `service.py:55`, `direction_relationship` at `:56`
**Task in the process:** Advances the market-structure lifecycle across sessions and classifies the relationship between the governed trade direction and the detected structure direction.
**Entry points:** `transition_lifecycle()` (`:7`), `direction_relationship()` (`:19`) — both keyword-only
**Imports (production):** `.params` (`:4`) · **Imported by:** 6 modules · **Broken/retired imports:** NONE
**Inputs** — `transition_lifecycle`: `prior, detected, accepted, repair_pct, invalidated, params`. `direction_relationship`: `governed_direction, structure_direction, lifecycle, quality`. No I/O, no defaults on the data-bearing arguments
**Logic and algorithms** — a six-state absorbing-terminal machine over `{MS_NONE, MS_DEVELOPING, MS_ACCEPTED, MS_CONTINUING, MS_REPAIRING, MS_FAILED}` (`:7-16`), plus a four-outcome relationship classifier (`:19-25`)
**Decision branches** — **the reference implementation for this audit.** `:20-21` quality `INSUFFICIENT_DATA`/`COARSE_DATA_LOW_CONFIDENCE` or falsy `structure_direction` → `"INSUFFICIENT_DATA"`. `:23` `direction not in {"CALL","PUT"}` **or** lifecycle not in `{MS_ACCEPTED, MS_CONTINUING}` → `"NEUTRAL"`. `:24` `aligned = (CALL and ABOVE) or (PUT and BELOW)`; `:25` → `"ALIGNED"` else `"CONFLICTING"`. **CALL path** and **PUT path** are symmetric; **other/blank path** (`UNRESOLVED`, `STRANGLE`, `""`, `NONE`) is routed to a named `NEUTRAL` with no coercion to either side. Contrast `zero_dte/zero_dte_contract.py:203` and `short_swing/short_swing_contract.py:196`, which collapse the same input space to two
**Computations and formulas (exact)** — `previous = str(prior or "").upper()` (`:8`) — the one fallback, mapping `None` to `""` so a first-ever session is treated as no-prior rather than raising. `MS_FAILED` is absorbing (`:9`). `:10-11` `not detected or invalidated or repair_pct > 0.60` → `MS_FAILED` if a prior existed else `MS_NONE`. `:12` from `""`/`MS_NONE` → `MS_ACCEPTED` if accepted else `MS_DEVELOPING`. `:13` from `MS_DEVELOPING` → `MS_ACCEPTED` if accepted. `:14` from `MS_REPAIRING` → `MS_CONTINUING` if `accepted and repair_pct < 0.20`. `:15` from `MS_ACCEPTED`/`MS_CONTINUING` → `MS_CONTINUING` under the same condition. `:16` all remaining → `MS_REPAIRING`
**Models** — NOT_APPLICABLE. Thresholds from `MSParams`, declared `PROPOSED_NOT_CALIBRATED`
**Outputs** — returns strings consumed as `ms_lifecycle` and `ms_direction_relationship` (`service.py:68`). Writes no files
**Handoff** — Receives `prior_lifecycle` from `service.py:50` and the metrics block from `service._metrics`; hands both labels into the evidence dict
**Missing-data handling** — `prior=None` → `""` → first observation (`:8`, `:12`). Absent `structure_direction` → `"INSUFFICIENT_DATA"` (`:20`). **Degraded quality is checked before any directional reasoning** (`:20`), so a low-confidence session can never produce `ALIGNED` or `CONFLICTING`. Every terminal branch returns a named state; no `None` return, no implicit fall-through. §10-compliant? **N** in vocabulary, complete in substance
**Contradictions found here:** NONE
**Gaps found here:** GAP-604 — the `repair_pct > failed_repair` test at `:10` uses strict `>` while `:14-15` use strict `<` against `intact_repair`, leaving `repair_pct` exactly in `[0.20, 0.60]` to fall through to `MS_REPAIRING` (`:16`); intended, but the boundary at exactly `0.20` is documented nowhere. Lifecycle continuity depends entirely on the caller supplying a correct `prior_lifecycle`; nothing in this module can detect a missing or wrong prior, so an omitted prior silently restarts the machine and loses `MS_FAILED`'s absorbing property
**Comment/docstring claims audited:** `:1` "Market-structure lifecycle and governed-direction relationship mapping" → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### ml_confidence_layer/ml_confidence_engine.py
**Classification:** LIBRARY · **DEAD** relative to production (658 lines)
**Real execution position:** NOT_INVOKED. `intelligent_orchestrator.py` contains **zero** references to `ml_confidence`, `run_ml_on_vanguard_output` or `adjusted_ev` [OBSERVED, exhaustive grep]
**Task in the process:** Would score each Vanguard signal 0–100 on two axes and emit a 0.5×–1.5× multiplier applied to Vanguard EV, explicitly "does NOT override the verdict. It informs it." (`:16`).
**Entry points:** `MLConfidenceEngine.score()` (`:268`), `run_outcome_regression()` (`:430`), `__main__` CLI `--apply-weights --run-id` (`:628-655`)
**Imports (production):** numpy, pandas; optional `xgboost` (`:36-40`) and `tensorflow.keras` (`:42-48`), each degrading to `*_AVAILABLE = False` · **Imported by:** `ml_confidence_layer/__init__.py:6`, `ml_confidence_layer/run_ml_on_vanguard_output.py:30`, `scripts/run_ml_on_vanguard_output.py:26`; `tests/test_audit_remediation_guards.py:76` reads its **source text** as a guard rather than importing it · **Broken/retired imports:** NONE
**Inputs** — `VanguardSignal` dataclass (`:71-86`): ticker, verdict, ev, win_rate, wyckoff_phase, control_state, compression_state, macro_regime, options_flow_score, volume_ratio, atr_pct, ev_normalised. Optional `history_df` OHLCV. Files: `models/` (`:54`), `trade_outcomes.json` (`:55`). External calls: NONE
**Logic and algorithms** — 12-feature XGB vector (`:109-131`); 60×5 LSTM sequence (`:132-166`); weighted ensemble (`:277`); linear score→multiplier map (`:346-354`)
**Decision branches** — **FINDING: there are none, and the absence is itself directional.** `VanguardSignal` has **no direction field** (`:71-86`) and the strings `CALL`/`PUT` appear nowhere. The scoring is nevertheless bull-coded: `_xgb_heuristic` (`:317-330`) awards `+8` for `wyckoff_phase in ("markup","accumulation")`, `+6` for `control_state == "BUYERS"`, `+5` for `macro_regime == "RISK_ON"`; `_lstm_heuristic` (`:332-344`) awards `+10` for `markup`, `+8` for `RISK_ON`. `PHASE_MAP` (`:63`) ordinally encodes `markup:4 > accumulation:3 > unknown:2 > distribution:1 > markdown:0`; `CONTROL_MAP` (`:64`) `BUYERS:2 > EQUILIBRIUM/NEUTRAL/UNKNOWN:1 > SHIFTING:0.5 > SELLERS:0`. A well-formed PUT thesis (markdown, SELLERS, RISK_OFF) receives the minimum on every one of these features and has its EV **reduced**. **CALL path / PUT path / other-blank path: all identical code, all bull-coded features**
**Computations and formulas (exact)** — `ensemble = round(0.55·xgb + 0.45·lstm, 1)` (`:277`); `normalised = (ensemble − 50)/50`; `multiplier = 1.0 + normalised·0.5` clamped `[0.50, 1.50]`, 3dp (`:351-354`); `adjusted_ev = round(ev · multiplier, 3)` (`:280`). XGB heuristic: `50 + (win_rate−0.5)·60 + ev_normalised·15 + 8|6|5|5 conditionals + (options_flow_score−50)·0.2`, clamped `[0,100]`, 1dp (`:322-330`). LSTM heuristic: `50 + volume_ratio·5 − atr_pct·200 + 10|8|10 conditionals + (win_rate−0.5)·30` (`:337-343`). Retrain trigger `total >= 10 and total % 5 == 0` (`:398`)
**Models** — "XGBoost + LSTM Ensemble" (`:3`). **Neither is trained in the shipped state:** `_score_xgb` requires `hasattr(self.models.xgb_model, "classes_")` (`:299`) and falls through to `_xgb_heuristic`; `_score_lstm` requires a loaded Keras model (`:309`) and falls through to `_lstm_heuristic`. Frozen weight snapshot (`:403-427`): `win_rate_weight 0.60, ev_weight 0.15, options_flow_weight 0.20, volume_ratio_weight 0.05, atr_penalty_weight 2.00, xgb_ensemble_weight 0.55, lstm_ensemble_weight 0.45`. Calibration source claimed: **none**. Version tag: **none**
**Outputs** — `MLEdgeResult` dataclass (`:88-104`); `trade_outcomes.json` (`:387-389`); `weights_baseline_<ts>.json` (`:422-425`). No atomic promotion, no schema/version field. Authority claim `:607` "This report is ADVISORY. No weights have been changed." → **HOLDS** (`:647-649` is an explicit stub)
**Handoff** — Would receive from Vanguard and hand `adjusted_ev` back. Join key: `ticker`. Neither side is wired
**Missing-data handling** — XGB/LSTM predict exception → warning then heuristic (`:303-306`, `:313-316`). **Most significant:** when `history_df` is absent or shorter than 60 bars, `build_lstm_sequence` (`:155-166`) **fabricates** the sequence — `np.random.normal(0, 0.03, (60,5))` noise around a template derived from the signal's own fields. The resulting `lstm_score` is presented as a "sequence confidence score" with no flag distinguishing it from a real 60-bar read, and is **non-deterministic across runs** because the RNG is unseeded. §10-compliant? **N** — this is a `SYNTHETIC_RESEARCH_ONLY` state emitted as `AVAILABLE`
**Contradictions found here:** the docstring `:9-12` describes the LSTM as "Reads: last 60 bars of price/volume behaviour"; the implementation synthesises those bars whenever real history is absent (`:155`), and the class's own comment calls it a "Synthetic prior derived from current signal state". Both statements coexist in one file
**Gaps found here:** DEAD; direction-blind by construction while carrying bull-coded features; `datetime.utcnow()` at `:288` and `:381` (naive) where the rest of the tree uses timezone-aware UTC
**Comment/docstring claims audited:** `:16` "It does NOT override the verdict. It informs it." → **HOLDS vacuously** (nothing consumes it). `:320` "Weights match what XGBoost will learn to weight from experience" → **PARTIAL** — an unverifiable forward claim; the frozen baseline (`:406-418`) and the heuristic constants (`:322-330`) do not use the same numbers. `:399` "auto-retrain every 5 new outcomes once 10 trades are logged" → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### news_terminal/news_terminal_engine.py
**Classification:** LIBRARY · LIVE within its own scheduled lane (190 lines)
**Real execution position:** NOT_INVOKED by the orchestrator. Imported by `news_terminal_commands.py:5,13,85,96`; that lane runs under Windows scheduled tasks (`news_terminal/install.bat:17,21,25`)
**Task in the process:** Holds `SessionState`, loads the system prompt, calls the Anthropic API with web search enabled, and extracts tagged sections, CSV/JSON blocks, desk verdict and options regime.
**Entry points:** `call_api()` (`:52`), `session` singleton (`:43`), `build_*_prompt()` family (`:125-190`)
**Imports (production):** os, json, re, csv, io (`:4`); `anthropic` imported lazily (`:54`) · **Imported by:** `news_terminal_commands.py` · **Broken/retired imports:** NONE
**Inputs** — `system_prompt_v1_3.txt` (`:13`), hard-failing if absent (`:49`). External: `client.messages.create(model=MODEL, max_tokens=8000, system=…, tools=[web_search_20250305])` (`:59-63`)
**Logic and algorithms** — regex tagged-section extractor (`:67-70`); first-match-wins verdict/regime classifiers (`:97-109`)
**Decision branches** — `extract_options_regime` (`:106-109`) iterates `["CALL_FAVOURED","PUT_FAVOURED","VOL_EXPANSION","VOL_CRUSH","WAIT"]` and returns the first substring hit, else `"WAIT"`. **CALL is tested before PUT**, so a response mentioning both always resolves CALL — an order-dependent collapse, not a genuine three-way branch. **Other/blank path:** `"WAIT"`. The prompt at `:142` constrains `catalyst_direction_bias` to `LONG_CALL_WATCH, LONG_PUT_WATCH, NEUTRAL_WATCH, WATCH_ONLY, DO_NOT_RUN`, but nothing in this file validates compliance
**Computations and formulas (exact)** — NONE
**Models** — `MODEL = "claude-sonnet-4-6"` (`:9`), `MAX_TOKENS = 8000` (`:10`). That identifier does not follow the documented Anthropic model-id convention, so every `call_api` is a candidate 404 at the API boundary [INFERRED from the id shape alone; MEDIUM]
**Outputs** — returns concatenated text blocks (`:64`); creates `outputs/daily` (`:16`). `parse_csv_section` (`:72-84`) and `parse_json_section` (`:86-95`) force `execution_permission="NONE_NEWS_TERMINAL_ONLY"` and `capital_grade="NO"` onto every parsed row. Authority claim: **PARTIAL** — enforced on parsed rows, but `write_macro_enrichment_delta` stamps the same keys onto the macro JSON that becomes `cfg.MACRO_FILE`, where no orchestrator reader checks either key
**Handoff** — Receives from the Anthropic API; hands to `news_terminal_commands` and `news_terminal_outputs`
**Missing-data handling** — System prompt absent → `FileNotFoundError` (`:49`), the only hard failure in the lane. CSV parse error → prints and returns `[]` (`:83-84`); JSON parse error → `{}` (`:94-95`) — both swallow the failure and hand an empty structure downstream. No verdict token → `"PENDING"` (`:104`); no regime token → `"WAIT"` (`:109`). §10-compliant? **N**
**Contradictions found here:** GAP-605 — `:8` `ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-api03-…")`: a **live-format Anthropic API key hardcoded as the default value** in a tracked source file. This directly contradicts `polygon_data_fetcher.py:12-15`, which records that a plaintext key was removed on 2026-08-03 and states "The exposed key must be rotated at the Polygon dashboard, not just removed here". The same key string is duplicated verbatim at `ma_cockpit/ma_cockpit_engine.py:9`
**Gaps found here:** GAP-605; no response-schema validation — the prompt's enum constraints (`:142`) are advisory text only. Because the hardcoded key is a working default, the module functions with `ANTHROPIC_API_KEY` unset, so the exposure is invisible in normal operation
**Comment/docstring claims audited:** `:2` "News Terminal v1.3 — Core Engine" → **HOLDS**. Prompt text `:135,145,152,156,160` "Execution permission: NONE_NEWS_TERMINAL_ONLY" → **PARTIAL** (an instruction to the model, not an enforced constraint)
**Confidence in this section:** HIGH — file read end to end

---

### news_terminal/news_terminal_outputs.py
**Classification:** LIBRARY · LIVE within its own lane; **writes into a production input path** (770 lines)
**Real execution position:** NOT_INVOKED by the orchestrator. Runs under `news_terminal_scheduler.py` and the interactive menu (`news_terminal/news_terminal.py:39`)
**Task in the process:** Parses an LLM response into ticker/handoff CSVs, a macro JSON, HTML briefs and three "integration" artefacts, stamping every row `execution_permission=NONE_NEWS_TERMINAL_ONLY` and `capital_grade=NO`.
**Entry points:** `write_all_outputs()` (`:77`), `write_ticker_csv_only()` (`:745`), `write_catalyst_csv_v2()` (`:634`), `write_macro_enrichment_delta()` (`:668`), `write_tickers_file()` (`:698`)
**Imports (production):** csv, json, re (`:6-10`) · **Imported by:** `news_terminal_commands.py:12,270` · **Broken/retired imports:** NONE — but the flat import form resolves only when `news_terminal/` is on `sys.path`
**Inputs** — Raw LLM text; sections extracted by `_extract_section` (`:153`, **redefined at `:364`** — a shadowed duplicate, the second silently wins). No DB, no API here. 16 fallback chains, 28 write sites [OBSERVED, extractor]
**Logic and algorithms** — tagged-section extraction + fenced-block cleaning (`:159`); permission enforcement rewriter (`:274-298`)
**Decision branches** — display-only. `:259` scans for `CALL_FAVOURED, PUT_FAVOURED, VOL_EXPANSION, VOL_CRUSH`; `:446` `rc = "#ef4444" if "PUT" in options_regime else "#22c55e" if "CALL" in options_regime else "#f59e0b"` — a **substring** test with PUT tested first, so any string containing "PUT" collides and a hypothetical `CALL_PUT_MIXED` renders as PUT. `:394-395` colours `LONG_CALL_WATCH`/`LONG_PUT_WATCH`; **other/blank path:** falls through uncoloured
**Computations and formulas (exact)** — NONE (formatting only)
**Models** — Anthropic Messages API via the engine
**Outputs** — `news_terminal/outputs/daily/<ts>/news_terminal_<ts>.csv`, `handoff_<ts>.csv`, HTML briefs; flat `news_terminal/outputs/avshunter_catalyst_csv_<YYYYMMDD>.csv` (32 cols, `:621-632`); `avshunter_macro_enrichment_delta_<YYYYMMDD>.json` **and `macro_intelligence_latest.json`** (`:672`, `:691-692`); `news_terminal_tickers_<date>.txt` (`:739`). No atomic promotion (direct `write_text`). Schema/version: the delta carries `contract_version: macro_enrichment_delta_v1_2`; the catalyst CSV carries none. Authority-claim fields `execution_permission`/`capital_grade` → **FALSE in effect**, see Contradictions
**Handoff** — Hands to `deploy_news_terminal_outputs()` (`news_terminal_commands.py:291-330`), which copies `macro_intelligence_latest.json` into `dropbox/macro/` and `pipeline_interpreter/MA_Inputs/macro/`, and the dated candidate files into `dropbox/inputs/`. Join key: `ticker`
**Missing-data handling** — Missing section → `return None` (`:26-27`, `:639`, `:673-676`). Unparseable JSON → `return None` (`:685-686`). `row.setdefault(col, "")` for all 32 columns (`:656-657`) — **every absent field becomes an empty string indistinguishable from a genuine blank**. `_enforce_permissions` wraps its rewrite in `except Exception: pass` (`:298-299`). §10-compliant? **N**
**Contradictions found here:** **the most consequential in this Part.** The lane stamps `NONE_NEWS_TERMINAL_ONLY` / `capital_grade=NO` on every row, yet `:672` writes **`macro_intelligence_latest.json`**, which the deploy step copies into `dropbox/macro/` — exactly `intelligent_orchestrator.py:407` `cfg.MACRO_FILE`, the orchestrator's authoritative macro input, validated at `:1064-1069` and consumed by every downstream module. The dated `avshunter_macro_enrichment_delta_*.json` also matches `contracts/macro_enrichment_delta.py:97`'s glob, so it is picked up by `find_macro_enrichment_delta` and merged into Discovery enrichment. **A lane declaring zero capital authority is the writer of the pipeline's macro truth.**
**Gaps found here:** `avshunter_catalyst_csv_<date>.csv` and `premarket_candidates_<date>.csv` have **no reader anywhere** in the tracked tree; `_extract_section` defined twice (`:153`, `:364`)
**Comment/docstring claims audited:** `:12-13` `EXECUTION_PERMISSION`/`CAPITAL_GRADE` constants → **PARTIAL** (true of CSV cell values, false of the lane's reach into `cfg.MACRO_FILE`). `:619` "INTEGRATION OUTPUTS (flat news_terminal/outputs/)" → **HOLDS**
**Confidence in this section:** HIGH for the write paths and deploy chain; MEDIUM for the HTML renderers (skimmed)

---

### news_terminal/news_terminal_commands.py
**Classification:** LIBRARY · LIVE within its own lane; the deployer that bridges into production paths (381 lines)
**Real execution position:** NOT_INVOKED by the orchestrator; entered from `news_terminal.py:39` and `news_terminal_scheduler.py`
**Task in the process:** Maps `/brief`, `/mna`, `/sector`, `/event`, `/forward`, `/map`, `/watchlist`, `/risk`, `/sources`, `/refine`, `/ticker-csv`, `/handoff-csv`, `/status`, `/reset` to prompt builders, API calls and writers (`:355-380`), then deploys and runs the combiner.
**Entry points:** `route_command()` (`:355`), `cmd_brief()` (`:105`) and siblings, `deploy_news_terminal_outputs()` (`:291`), `_run_combiner()` (`:334`)
**Imports (production):** `news_terminal_engine`, `news_terminal_outputs` (`:5-13`), function-local `shutil`, `subprocess` · **Imported by:** `news_terminal.py:39`, `news_terminal_scheduler.py` · **Broken/retired imports:** NONE, but `:338` hardcodes an absolute path `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\build_premarket_candidates.py`, as does `:299` for `BASE`
**Inputs** — Session state; LLM response text. External: Anthropic via `call_api`; `subprocess.run([sys.executable, combiner], check=False)` (`:341`)
**Logic and algorithms** — command dispatch chain (`:359-379`); deployment fan-out (`:302-330`)
**Decision branches** — `print_results` (`:80-86`) prints `extract_options_regime(raw_response)`, which is order-dependent (see engine `:106-109`). **CALL path** wins ties; **PUT path** only when no CALL token; **other/blank path** → `"WAIT"`. No other direction branch
**Computations and formulas (exact)** — NONE
**Models** — Anthropic Messages API, model id from the engine
**Outputs** — Copies `macro_intelligence_latest.json` and `avshunter_macro_enrichment_delta_<TODAY>.json` into `pipeline_interpreter/MA_Inputs/macro/` and `dropbox/macro/` (`:304-315`); copies `premarket_candidates_<TODAY>.csv` and `news_terminal_tickers_<TODAY>.txt` into `dropbox/inputs/` (`:322-330`). Plain `shutil.copy2` — **no atomic promotion, no schema check, no validation of what is being overwritten**
**Handoff** — Hands to `intelligent_orchestrator` preflight (`cfg.MACRO_FILE`), `contracts/macro_enrichment_delta.find_macro_enrichment_delta`, and `build_premarket_candidates.py`. Join keys: filename + date
**Missing-data handling** — `if src.exists()` guards every copy (`:311`, `:327`) — a missing source is skipped **silently apart from the absent print**, leaving yesterday's `macro_intelligence_latest.json` in place with **no staleness marker written by this lane**. `cmd_handoff_csv` returns early with a warning when the session has no handoff data (`:266-268`). §10-compliant? **N**
**Contradictions found here:** `:292-295` "Copy news terminal macro outputs to all pipeline-readable locations" — an accurate description that directly contradicts the per-row `NONE_NEWS_TERMINAL_ONLY` stamp the same lane applies. `desk_card.py:523` describes news-terminal context as "display only, never acted on"; that claim is **FALSE** for the macro JSON path
**Gaps found here:** two hardcoded absolute user paths (`:299`, `:338`) make the lane non-portable; no verification that the JSON copied into `cfg.MACRO_FILE` satisfies the orchestrator's macro contract — validation happens later, in the orchestrator, where failure aborts preflight (`:1064-1069`)
**Comment/docstring claims audited:** `:291-295` deploy docstring → **HOLDS**. `:335` "Run build_premarket_candidates.py after outputs are written" → **HOLDS**. Menu banner `:16-33` "v1.3" → **HOLDS**
**Confidence in this section:** HIGH

---

### ma_cockpit/ma_cockpit_engine.py
**Classification:** LIBRARY · LIVE within its lane; structural twin of `news_terminal_engine.py` (237 lines)
**Real execution position:** NOT_INVOKED by the orchestrator. Imported by `ma_cockpit_commands.py:5,41` and `ma_cockpit_outputs.py:210,368`
**Task in the process:** Holds `MACockpitSession`, loads the M&A system prompt, calls the Anthropic API with web search, cleans and parses CSV blocks, extracts the desk verdict.
**Entry points:** `call_api()` (`:49`), `session` singleton (`:42`), `build_full_scan_prompt()` (`:105`) and siblings
**Imports (production):** os, json, re, csv, io (`:5`); `anthropic` lazily (`:50`) · **Imported by:** `ma_cockpit_commands.py`, `ma_cockpit_outputs.py` · **Broken/retired imports:** NONE
**Inputs** — `ma_cockpit_system_prompt.txt` (`:14`), hard-failing if absent (`:47`). External: `client.messages.create(...)` (`:53-57`)
**Logic and algorithms** — tagged-section regex (`:61-63`); a two-stage regex row-repair that re-inserts newlines into space-separated CSV rows (`:65-73`); first-match-wins verdict classifier (`:87-94`)
**Decision branches** — none in this file. `extract_verdict` (`:87-94`) scans ten M&A verdict tokens in fixed order, returning `"PENDING"` if none match (`:94`) — order-dependent, so a response carrying two verdicts always yields the earlier. CALL / PUT / other-blank: **NOT_APPLICABLE**
**Computations and formulas (exact)** — NONE. The CSV repair at `:68-71` uses two hardcoded regexes keyed on the literals `NONE_MA_COCKPIT_ONLY`, `MA_COCKPIT`, `MA_COCKPIT_v1.0` — a parser whose correctness depends on the model reproducing those exact strings
**Models** — `MODEL = "claude-sonnet-4-6"` (`:10`), `MAX_TOKENS = 8000` (`:11`) — the same non-conforming identifier as the news-terminal engine [INFERRED, MEDIUM]
**Outputs** — returns text (`:58`); creates `outputs/daily` (`:17`). `parse_csv` (`:75-85`) forces `execution_permission = "NONE_MA_COCKPIT_ONLY"` (`:19`) and `capital_grade = "NO"` (`:20`, `:82`). Authority claim → **HOLDS here**, but is overwritten with the news-terminal value at `ma_cockpit_outputs.py:354`
**Handoff** — Receives from the Anthropic API; hands to `ma_cockpit_commands` and `ma_cockpit_outputs`. `MASTER_CSV` (`:16`) is the append target used at `ma_cockpit_outputs.py:87`
**Missing-data handling** — System prompt absent → `FileNotFoundError` (`:47`). CSV parse exception → print and return `[]` (`:84-85`). No verdict token → `"PENDING"` (`:94`). §10-compliant? **N**
**Contradictions found here:** GAP-605 — `:9` carries the **identical hardcoded Anthropic key string** as `news_terminal/news_terminal_engine.py:8`, duplicated verbatim in a second tracked file
**Gaps found here:** GAP-605; no response-schema validation; the regex row-repair silently mangles rows if the model varies its permission literal; `MODEL`/`MAX_TOKENS` duplicated across two lanes with no shared config
**Comment/docstring claims audited:** `:2` "M&A Cockpit v1.0 — Core Engine" → **HOLDS**. `:19-20` permission constants → **PARTIAL** (honoured at `:81-82`, contradicted at `ma_cockpit_outputs.py:354`). `:67` "Fix space-separated rows" → **HOLDS** as a description of the regex
**Confidence in this section:** HIGH

---

### ma_cockpit/ma_cockpit_outputs.py
**Classification:** LIBRARY · LIVE within its lane; outputs unconsumed (415 lines)
**Real execution position:** NOT_INVOKED by the orchestrator. Runs under `ma_cockpit/install.bat:7-9` → `ma_cockpit_scheduler.py`, or `ma_cockpit/ma_cockpit.py:30`
**Task in the process:** Parses the LLM response into a full-schema ticker CSV, a handoff CSV, a deduplicated master CSV, two HTML briefs, and a flat 32-column integration CSV.
**Entry points:** `write_all_outputs()` (`:367`), `write_ma_candidates_flat()` (`:331`), `build_html()` (`:209`)
**Imports (production):** csv, io, pathlib; function-local `from ma_cockpit_engine import MASTER_CSV, extract_verdict` (`:368`, also `:210`) · **Imported by:** `ma_cockpit_commands.py:11` · **Broken/retired imports:** NONE
**Inputs** — Raw LLM text; sections `TICKER_CSV_DATA`, `HANDOFF_CSV_DATA`, `MA_CANDIDATES_CSV_DATA` (`:377-379`, `:340`). 12 fallback chains, 15 write sites [OBSERVED, extractor]
**Logic and algorithms** — section extraction (`:42`), CSV cleaning (`:46`), master dedup by append (`:78-97`)
**Decision branches** — display-only and substring-based. `:164-165` `c = '#00c853' if 'BULL' in val or 'CALL' in val else ('#ef4444' if 'BEAR' in val or 'PUT' in val else '#f59e0b')`, applied to `ma_trade_bias` and `expected_impact_direction`. **Bullish is tested first**, so a value containing both tokens renders bullish. **Other/blank path:** `MIXED`, `NEUTRAL`, `UNKNOWN` and blank all fall to the amber default, collapsing four distinct schema values (`ma_csv_schema.py:134`) into one visual state
**Computations and formulas (exact)** — NONE (formatting and colour mapping only)
**Models** — Anthropic Messages API via the engine
**Outputs** — `<run_dir>/ma_candidates_<ts>.csv`, `ma_handoff_<ts>.csv`, `ma_brief_<ts>_full.html`, `ma_brief_<ts>_trader.html` (`:388-408`); master append (`:87`); flat `ma_cockpit/outputs/ma_candidates_<YYYYMMDD>.csv` (`:338`, 32 cols at `:318-329`). No atomic promotion, no schema/version field
**Handoff** — **NONE.** `ma_candidates_*.csv` has **no reader anywhere** in the tracked tree, and unlike the news-terminal lane there is no deploy step copying anything into `dropbox/`. Join key: `affected_ticker` / `ticker`
**Missing-data handling** — Missing section → `return None` (`:341-342`). Parse exception → print + `return None` (`:346-348`). `row.setdefault(col, "")` across all 32 columns (`:355-356`). `n == 0` rows → prints a warning (`:392`) and continues. §10-compliant? **N**
**Contradictions found here:** `:354` stamps `row["execution_permission"] = "NONE_NEWS_TERMINAL_ONLY"` on every row of the **M&A** integration CSV, while the lane's own constant is `NONE_MA_COCKPIT_ONLY` (`ma_cockpit_engine.py:19`) and `_parse_csv` correctly applies that value at `ma_cockpit_engine.py:81`. The same file emits two different provenance labels for one lane, one of them naming a different subsystem. The banner `:303` and footer `:315` render the **correct** M&A value, so the human-readable HTML and the machine-readable CSV disagree
**Gaps found here:** the flat integration CSV is a dead artefact; `_MA_INTEGRATION_COLS` (`:318-329`) is a verbatim copy of news-terminal's `_CATALYST_OUTPUT_COLS` and shares none of the 68-column M&A schema in `ma_csv_schema.py:8-71`, so M&A-specific fields (`dbs`, `ma_tps`, `ma_rcs`, `ma_verdict`, `long_call_candidate`, `long_put_candidate`) are dropped at the integration boundary by `extrasaction="ignore"` (`:359`)
**Comment/docstring claims audited:** `:332` "32-col integration schema" → **HOLDS** mechanically, **PARTIAL** as to intent. `:12` "Full schema matching ma_csv_schema.py REQUIRED_COLUMNS" → **PARTIAL** (true of `TICKER_CSV_FIELDS`, false of the flat writer)
**Confidence in this section:** HIGH for the writers; MEDIUM for the HTML builder

---

### ma_cockpit/ma_csv_schema.py
**Classification:** LIBRARY · LIVE within its lane. Declarative schema + manual-review validator (306 lines) — **the most rigorous file in the peripheral set**
**Real execution position:** NOT_INVOKED by the orchestrator. Imported by `ma_cockpit_commands.py:153` and `ma_cockpit/validate_ma_csv.py:6`
**Task in the process:** Defines the 68-column manual-review contract, generates an empty template, and validates a filled CSV against enum vocabularies and eight cross-field governance rules.
**Entry points:** `validate_ma_manual_review_csv()` (`:164`), `create_ma_manual_review_template()` (`:156`)
**Imports (production):** csv, dataclasses, pathlib (`:1-5`) · **Imported by:** `ma_cockpit_commands.py:153`, `ma_cockpit/validate_ma_csv.py:6` · **Broken/retired imports:** NONE
**Inputs** — a manual-review CSV, read with `encoding="utf-8-sig"` (`:171`)
**Logic and algorithms** — missing-column hard stop (`:174-177`); per-row enum checks and eight governance rules (`:191-283`)
**Decision branches** — **the only genuinely symmetric direction handling in this Part.** `:270-275` `long_call_candidate TRUE` + `impact == "BEARISH"` → error unless the notes contain "explicitly justified" or "call hedge"; `:277-283` `long_put_candidate TRUE` + `impact == "BULLISH"` → error unless the notes contain "explicitly justified" or "put hedge". **CALL path and PUT path are covered with identical structure.** **Other/blank path:** handled by the `IMPACT_DIRECTIONS` enum (`:134`), which admits `MIXED`, `NEUTRAL`, `UNKNOWN` — none of which triggers either rule, so **a `MIXED` impact permits both a call and a put candidate simultaneously with no warning.** The escape hatch is a **free-text substring match on reviewer notes** (`:271`, `:279`), satisfied by any note containing the phrase regardless of relevance
**Computations and formulas (exact)** — `_int_or_zero` (`:301-305`) returns 0 on `ValueError`, so a malformed `second_source_count` becomes 0 — which is the value that *triggers* the TIER_4 block at `:254-260`, i.e. this fallback **fails closed**. `_norm` upper-cases and strips (`:293`). `_is_true` against `TRUE_VALUES = {"TRUE","YES","Y","1"}` (`:143`)
**Models** — NONE
**Outputs** — `ValidationReport(path, valid, errors, warnings, row_count)` (`:148-154`); an empty template CSV (`:156-162`). No files written during validation
**Handoff** — Receives a human-authored CSV; hands a report to `ma_cockpit_commands.py:153`. Join key: `event_id` / `affected_ticker`
**Missing-data handling** — Missing required columns → immediate `ValidationReport(valid=False)` with `row_count=0` (`:174-177`), the only hard-fail path. **`_check_enum` at `:286-291` only errors `if value and value not in allowed`** — an **empty** value passes every enum check silently, so a row with all enum fields blank is reported valid. That is the principal weakness: the validator enforces vocabulary but not presence. §10-compliant? **N**
**Contradictions found here:** the governance rules block `GO`/`P1`/`FULL_PIPELINE` on TIER_4-without-second-source (`:254-260`) and on weak options liquidity (`:262-268`), asserting real gatekeeping authority — yet **no consumer of this validator's verdict exists in the pipeline**; `ma_cockpit_commands.py:153` invokes it interactively and `validate_ma_csv.py:6` is a standalone CLI. Nothing blocks on the result
**Gaps found here:** empty values bypass all enum validation (`:287`); the call/put escape hatch is a substring test on free text; the 68-column contract defined here is **not** the schema the lane actually exports (see `ma_cockpit_outputs.py:318-329`)
**Comment/docstring claims audited:** the module carries no docstring — the schema is self-describing. `:143` `TRUE_VALUES` and `:145` `GO_VALUES = {"GO","FULL_PIPELINE","P1"}` are used consistently at `:257` and `:265` → **HOLDS**
**Confidence in this section:** HIGH — file read end to end

---

### ma_cockpit/ma_cockpit_commands.py
**Classification:** LIBRARY · LIVE within its lane. Command router (212 lines)
**Real execution position:** NOT_INVOKED by the orchestrator. Entered from `ma_cockpit/ma_cockpit.py:30` and `ma_cockpit_scheduler.py:24`
**Task in the process:** Maps M&A cockpit commands to prompt builders, API calls and writers, and exposes the manual-review CSV validator.
**Entry points:** `route_command()`, `cmd_scan()`, `cmd_activist()`, validator entry at `:153`
**Imports (production):** `ma_cockpit_engine` (`:5`), `ma_cockpit_outputs` (`:11` — including the **underscore-prefixed private** names `_extract_section`, `_write_csv`), function-local `from ma_csv_schema import validate_ma_manual_review_csv` (`:153`) · **Imported by:** `ma_cockpit.py:30`, `ma_cockpit_scheduler.py:24` · **Broken/retired imports:** NONE
**Inputs** — Session state; LLM responses; a manual-review CSV path for `:153`
**Logic and algorithms** — command dispatch; verdict display. Decision branches: none in this file — direction reaches the console only through `ma_cockpit_outputs._csv_to_table` (`:137`, `:164-165`), analysed above. CALL / PUT / other-blank: **NOT_APPLICABLE here**
**Computations and formulas (exact)** — NONE
**Models** — Anthropic Messages API via the engine
**Outputs** — Delegates all writing to `ma_cockpit_outputs.write_all_outputs`. **There is no `deploy_*` function** — unlike `news_terminal_commands.py:291`, this lane never copies anything into `dropbox/` or `pipeline_interpreter/MA_Inputs/`
**Handoff** — Terminal — nothing downstream consumes M&A artefacts
**Missing-data handling** — Follows the engine's pattern: parse failures yield empty lists and the command reports zero rows rather than failing. §10-compliant? **N**
**Contradictions found here:** GAP-606 — `catalyst_truth_engine.py:149` lists `"ma_cockpit"` in `_INDEPENDENT_CATALYST_SOURCES`, the allowlist that lets a source satisfy Direction Governance's two-family resolution rule (`:153-171`, whose own docstring at `:158-162` warns that re-labelling a pipeline field as catalyst evidence "would allow one signal family to satisfy Direction Governance's two-family resolution rule twice"). But `_catalyst_source` is only ever assigned `"catalyst_calendar"` (`catalyst_truth_engine.py:360`, `:365`). **`"ma_cockpit"`, `"news_terminal"` and `"manual_upload"` are dead allowlist entries** — no ingestion path stamps them. The M&A lane is declared an independent direction authority and is architecturally incapable of acting as one
**Gaps found here:** GAP-606; the lane is a terminal branch (calls an LLM, writes files, nothing reads them); cross-module import of private names (`:11`) makes the outputs module's internals load-bearing
**Comment/docstring claims audited:** `:2-3` "Command Router / Maps /commands to prompts, API calls and output writers" → **HOLDS**. `:41` local re-import of `extract_verdict` duplicating `:5` → redundant but harmless
**Confidence in this section:** MEDIUM-HIGH — router read; individual command bodies skimmed

---

### zero_dte/zero_dte_contract.py
**Classification:** LIBRARY · LIVE within its own dead lane. Component 2 of 4 — 0DTE contract selector
**Real execution position:** NOT_INVOKED. Imported by `zero_dte/run_0dte.py:52` only; no `.bat`, `.ps1`, `.sh` or scheduled task launches that runner [OBSERVED]
**Task in the process:** For each screener survivor, fetches the live 0DTE chain from Polygon and selects one contract by side, OTM distance, delta band, OI and spread.
**Entry points:** `process_eligible_tickers()` (`:317`), `select_contract()` (`:182`)
**Imports (production):** requests, pandas, numpy · **Imported by:** `zero_dte/run_0dte.py:52` · **Broken/retired imports:** NONE
**Inputs** — Screener CSV rows. Fallback chains: `spot = data['ticker']['day']['c'] or data['ticker']['prevDay']['c']` (`:112-113`) — a silent same-day/previous-day price substitution with **no flag**; `direction = str(row.get('options_direction', 'CALL')).upper()` (`:368`); `rank = int(row.get('zero_dte_rank', 0))` (`:369`); greeks `float(g.get('delta', 0)) if g else 0` (`:166-168`) — a missing delta becomes 0.0 and is then compared against the 0.30–0.45 band. External: Polygon snapshot + chain with pagination (`:104-141`), throttled
**Logic and algorithms** — rule-based selection: side filter → OTM window → delta band → OI floor → spread cap → premium floor (`:182-315`)
**Decision branches** — **FINDING (×2, compounding).** `:368` a **missing or empty** `options_direction` silently becomes **CALL**, the bullish side, rather than being rejected. `:203` `right = 'C' if direction.upper() == 'CALL' else 'P'` — **CALL path:** `CALL` → C. **PUT path:** everything else → P. **Other/blank path:** `NEUTRAL`, `STRANGLE`, `""` (after the CALL default has already applied) and any typo become **PUT**. The two together give exactly two reachable outcomes and **no rejection path for an unresolved direction**; `:285` then writes `'direction': direction.upper()` into the output, so the fabricated CALL is stamped as resolved evidence
**Computations and formulas (exact)** — `mid = (bid + ask)/2` (`:174`); `spread_pct` rounded 4dp (`:301`); gates `TARGET_DELTA_MIN=0.30`, `TARGET_DELTA_MAX=0.45`, `MAX_OTM_PCT=0.015`, `MIN_OPEN_INTEREST=500`, `MAX_SPREAD_PCT=0.12`, `MIN_PREMIUM=0.05` (`:45-51`); `PREMIUM_STOP_PCT=0.50`, `MAX_CONTRACTS_PAPER=1`, `MAX_CONTRACTS_LIVE=5` (`:54-59`)
**Models** — NONE
**Outputs** — `zero_dte/output/zero_dte_contracts_<date>.json` (`:422-424`) with `option_symbol, direction, strike, expiry, delta, gamma, theta, iv, open_interest, volume, bid, ask, mid, spread_pct, screener_rr, screener_ev, screener_composite, phase, intent, entry_method`. `json.dump(..., default=str)` (`:424`) — non-serialisable values coerced to strings rather than raising. No atomic promotion, no schema/version field
**Handoff** — Receives from the screener (CSV); hands to `intraday_0dte_trigger.py:346` and `zero_dte_outcome_logger.py:350`. Join key: `ticker`
**Missing-data handling** — Snapshot failure → `except: return None`, ticker skipped. Empty chain or `spot <= 0` → `return None` (`:200-201`). Missing greeks → all greeks 0 (`:166-168`). **`selected.get('expiry', date.today().isoformat())` (`:287`) — a missing expiry is defaulted to today, which for a 0DTE contract is indistinguishable from a correct value and therefore undetectable downstream.** §10-compliant? **N**
**Contradictions found here:** the docstring `:11` states "Direction: from Vanguard `precor_intent` (BUY_SETUP → CALL, SELL_SETUP → PUT)". The code never reads `precor_intent` for direction — it reads `options_direction` (`:368`) and stores `precor_intent` only as a descriptive field `'intent'` (`:401`). Constants also drift: `:13` claims "first OTM within 1% of spot" vs `MAX_OTM_PCT = 0.015` (`:47`); `:16` "Max spread: 10%" vs `0.12` (`:50`); `:14` "target 0.35–0.45" vs `0.30` (`:45`)
**Gaps found here:** DEAD lane; **no rejection state for an unresolved direction — the CALL default is the single most consequential silent bridge in this Part**
**Comment/docstring claims audited:** `:11` precor_intent derivation → **FALSE**. `:13` 1% OTM → **FALSE**. `:14` delta 0.35–0.45 → **FALSE**. `:16` max spread 10% → **FALSE**. `:25-27` "Uses Polygon REST API directly. Does not import from Vanguard package. Zero shared state with the production pipeline." → **HOLDS**
**Confidence in this section:** HIGH for direction handling, gates and outputs

---

### zero_dte/intraday_0dte_trigger.py
**Classification:** LIBRARY · DEAD standalone paper-trading intraday monitor (Component 3 of 4)
**Real execution position:** NOT_INVOKED. Reachable only from `zero_dte/run_0dte.py:53`
**Task in the process:** Loads the day's contract shortlist, polls 5-minute bars during the session, fires PAPER entry alerts on spring/UTAD + volume + gamma-zone + entry-window confluence, and exits on time, stop or reversal.
**Entry points:** `ZeroDTETriggerEngine.run()` (`:508`), `run_test()` (`:543`), `scan_once()` (`:365`)
**Imports (production):** requests, pandas, numpy · **Imported by:** `zero_dte/run_0dte.py:53` · **Broken/retired imports:** NONE
**Inputs** — `zero_dte/output/zero_dte_contracts_<date>.json`, **falling back to the newest `zero_dte_contracts_*.json` by glob** (`:346-356`) — a silent cross-date fallback that can monitor yesterday's contracts. External: Polygon aggregates (`:154`) and option snapshot (`:174`), throttled
**Logic and algorithms** — `detect_spring_trigger` (`:189`), `detect_volume_confirm` (`:234`), `detect_reversal_exit` (`:249`), `ZeroDTEPosition` state (`:280`)
**Decision branches** — **FINDING (×2).** `detect_spring_trigger` `:205` `if direction.upper() == 'CALL': … else: # PUT` (`:218`) and `detect_reversal_exit` `:262`/`:267` use the same shape. **CALL path:** explicit. **PUT path:** the `else`. **Other/blank path:** `NEUTRAL`, `STRANGLE`, `""` or any typo is silently treated as PUT and evaluated against the bearish UTAD/reversal condition. There is no third arm
**Computations and formulas (exact)** — `PREMIUM_STOP_PCT` exits when premium ≤ 50% of entry (`:295-296`); `pnl = current_premium − entry_premium` scaled by contract count (`:298-299`); `mid = (bid+ask)/2 if (bid+ask) > 0 else last_trade.price` (`:181`) — a fallback silently substituting a **trade print** for a **quote midpoint**; `REVERSAL_BARS = 3` (`:66`); volume confirm requires reclaim-bar volume > 1.5× prior bar (`:19`)
**Models** — NONE (rule-based state machine)
**Outputs** — `zero_dte/output/paper_outcomes_<YYYYMMDD>.csv` (`:506`). No atomic promotion, no schema/version field. Authority claim: `type = 'ENTER_PAPER' if contract.get('paper_mode', True) else 'ENTER'` (`:466`) — the default is `True`, so an absent `paper_mode` reads as paper → **HOLDS** as a fail-safe default
**Handoff** — Receives from `zero_dte_contract.py` (JSON); hands to `zero_dte_outcome_logger.py` (CSV). Join key: `ticker` + `option_symbol`
**Missing-data handling** — Bar fetch exception → `except Exception: return` empty frame (`:166-167`); quote exception → `return None` (`:183`); no contracts file → error log (`:356`) and continues. `contract.get('zero_dte_rank', 0)` (`:476`) defaults a missing rank to 0, colliding with a genuine rank-0. §10-compliant? **N**
**Contradictions found here:** the header (`:16-17`) documents spring-for-CALL and UTAD-for-PUT as a two-sided design; the `else` arms mean the module has **no representation for a directionless or multi-leg position**, even though the sibling `short_swing_screener.py:23` documents `STRANGLE` as a legal `options_direction`
**Gaps found here:** DEAD; the contracts-file glob fallback (`:351`) has no date assertion
**Comment/docstring claims audited:** `:37-39` "Does not import from Vanguard package… Zero shared state with production pipeline." → **HOLDS**. `:29` outcome CSV path → **HOLDS**
**Confidence in this section:** MEDIUM-HIGH — structure and all direction branches read directly; the run loop skimmed

---

### zero_dte/zero_dte_outcome_logger.py
**Classification:** LIBRARY · DEAD. Component 4 of 4 — outcome aggregation and actuarial feed formatter
**Real execution position:** NOT_INVOKED. Imported by `zero_dte/run_0dte.py:54` only
**Task in the process:** Aggregates the day's paper outcomes, computes daily and cumulative statistics, formats state-hash observations for eventual actuarial ingestion, and builds an Intelligence Lab panel JSON.
**Entry points:** `run_outcome_logger()` (`:328`)
**Imports (production):** numpy, pandas · **Imported by:** `zero_dte/run_0dte.py:54` · **Broken/retired imports:** NONE
**Inputs** — `paper_outcomes_<date>.csv` (`:73`), `cumulative_outcomes.csv` (`:48`), `zero_dte_contracts_<date>.json` (`:350`), a Vanguard enriched CSV for state hashes (`:87`). Fallbacks: `str(row.get('state_hash', 'UNKNOWN'))` (`:235`) — a missing hash becomes the literal `UNKNOWN`, which then groups as a legitimate state; `float(row.get('hold_hours', 0)) if 'hold_hours' in row else 0` (`:245`)
**Logic and algorithms** — grouped statistics by direction (`:183-185`) and exit reason; n≥50 readiness gate
**Decision branches** — partition-based, not conditional: `closed.groupby('direction')` (`:184`) emits one bucket per distinct value, so **CALL, PUT and any other token each get their own `by_direction` entry** with no validation. **Other/blank path:** a blank `direction` produces an empty-string key in the output JSON (`:205`). This is the only file in the 0DTE lane that does not collapse direction to two values, but it also never asserts the vocabulary
**Computations and formulas (exact)** — `win = 1 if float(row.get('pnl_dollars', 0)) > 0 else 0` (`:244`) — **exactly-zero P&L is scored as a loss**; `max_drawdown_day = closed.groupby(entry_time or 'date')['pnl_dollars'].sum().min() if 'entry_time' in closed.columns else 0` (`:203`) — a fallback bridging two semantic types: when `entry_time` is absent the groupby key becomes the **string literal** `'date'` rather than a column, and the branch returns a hardcoded `0`; `trades_to_n50` counts down to `ACTUARIAL_THRESHOLD`
**Models** — NONE. A `sharpe_approx` is reported (`:292`) with **no stated risk-free rate or annualisation convention**
**Outputs** — `daily_summary_<date>.json`, `cumulative_outcomes.csv` (`:377`), `actuarial_feed_<date>.json` (`:383-385`), `zero_dte_intel_panel.json` (`:410`). No atomic promotion, no schema/version field. Authority-claim field `actuarial_ready` (`:389`, `:398`) gates whether the feed may be pushed
**Handoff** — Receives from `intraday_0dte_trigger.py` and `zero_dte_contract.py`. **Hands to nothing** — `zero_dte_intel_panel.json` has no reader in the tracked tree, and the actuarial feed is never consumed by `scripts/actuarial_enrichment_pass.py` or the cache builder. Join key: `state_hash`
**Missing-data handling** — Missing outcomes CSV → empty DataFrame, `trades: 0` (`:68-78`). Missing contracts JSON → panel section omitted. `cumulative_stats.get(..., default)` throughout the panel builder (`:271-294`) — **every statistic has a silent default, so a fully-empty panel is structurally identical to a populated one**. §10-compliant? **N**
**Contradictions found here:** the docstring `:14-20` asserts that outcomes are "simultaneously building … Phase E hash observations for the main actuarial database" and that the module "can feed outcomes directly into the actuarial_database.db using the same schema as swing trade outcomes". **No code path in this file or anywhere in the tree writes to that database**, and the schema equivalence is asserted rather than enforced — `format_actuarial_observations` (`:214-247`) emits a bespoke 10-field record, not the v7 observation schema used by `scripts/build_actuarial_v7.py`
**Gaps found here:** DEAD, and its principal declared output has no consumer; the `'UNKNOWN'` state-hash default would silently pollute any future ingestion
**Comment/docstring claims audited:** `:28-30` "Only writes to zero_dte/output/. Never touches the main actuarial database until explicitly invoked with --feed-actuarial" → **PARTIAL** — the write restriction **HOLDS**, but the `--feed-actuarial` path is a log-only stub (`:396-405`), so the capability the sentence implies does not exist
**Confidence in this section:** MEDIUM-HIGH

---

### short_swing/short_swing_contract.py
**Classification:** LIBRARY · DEAD. Component 2 of 5 — 7–21 DTE contract selector
**Real execution position:** NOT_INVOKED. Imported by `short_swing/run_short_swing.py:54` only
**Task in the process:** Reuses the evening-run contract when its DTE is already in range, otherwise fetches the live Polygon chain for the nearest qualifying expiry and selects a strike.
**Entry points:** `process_eligible()` (`:276`), `select_contract()` (`:191`)
**Imports (production):** requests, pandas, numpy · **Imported by:** `short_swing/run_short_swing.py:54` · **Broken/retired imports:** NONE
**Inputs** — Screener output rows. External: Polygon spot (`:103`), expiries (`:114`), chain per expiry (`:138`)
**Logic and algorithms** — reuse-or-refetch branch (`:330-390`); strike selection by side → OTM window → delta band → OI → spread → premium
**Decision branches** — **FINDING (×3).** `:318` `direction = str(row.get('options_direction', 'CALL')).upper()` — missing direction silently becomes CALL. `:196` `right = 'C' if direction.upper() == 'CALL' else 'P'` — all non-CALL values collapse to PUT. `:342` `'right': direction[0]` in the **reuse** path takes the **first character** of the raw string, so `CALL→'C'`, `PUT→'P'`, but **`STRANGLE→'S'` and `NEUTRAL→'N'`, neither a valid option right**; `:341` builds the synthetic symbol from the same character. **The reuse path and the refetch path therefore disagree about how a non-binary direction is encoded** — one produces an invalid right, the other silently produces a PUT. **Other/blank path:** CALL by default, then PUT or an invalid right depending on which branch runs
**Computations and formulas (exact)** — `DTE_MIN = 5`, `DTE_MAX = 21`, `TARGET_DELTA_MIN = 0.30`, `TARGET_DELTA_MAX = 0.50`, `MAX_OTM_PCT = 0.025`, `MIN_OI = 300`, `MAX_SPREAD_PCT = 0.15`, `MIN_PREMIUM = 0.10` (`:53-60`)
**Models** — NONE
**Outputs** — `short_swing/output/ss_contracts_<date>.json` (`:426-427`) with `direction` written back at `:245` and `:343`. `json.dump(..., default=str)`. No atomic promotion, no schema/version field
**Handoff** — Receives from `short_swing_screener.py`; hands to `short_swing_monitor.py:287`. Join key: `ticker`
**Missing-data handling** — Spot/expiry/chain failures return `None`/empty and the ticker is skipped. **`row['contract_expiry']` and `row['contract_strike']` at `:341` are direct subscripts, not `.get()`** — inside the reuse path they raise `KeyError` if absent, which is the one fail-closed access in the lane. §10-compliant? **N**
**Contradictions found here:** the docstring `:16-21` claims "DTE target: 7–21 days", "Strike: First OTM within 2% of spot", "Delta target: 0.35–0.50", "Min OI: 300", "Max spread: 15%", "Min premium: $0.10". The constants give `DTE_MIN = 5` (not 7), `MAX_OTM_PCT = 0.025` (2.5%, not 2%), `TARGET_DELTA_MIN = 0.30` (not 0.35) — **three of six documented gates are wrong.** The docstring also contradicts itself: `:11-13` says 5–21 DTE while `:16` says 7–21
**Gaps found here:** DEAD; two mutually inconsistent direction encodings within one file (`:196` vs `:342`)
**Comment/docstring claims audited:** `:16` DTE 7–21 → **FALSE**. `:17` 2% OTM → **FALSE**. `:19` delta 0.35–0.50 → **FALSE**. `:20` Min OI 300 → **HOLDS**. `:21` Max spread 15% → **HOLDS**. `:32-34` "Standalone Polygon client… Writes only to short_swing/output/" → **HOLDS**
**Confidence in this section:** HIGH for direction handling and constants

---

### short_swing/short_swing_monitor.py
**Classification:** LIBRARY · DEAD. Component 3 of 5 — EOD position monitor
**Real execution position:** NOT_INVOKED. Imported by `short_swing/run_short_swing.py:55` only
**Task in the process:** Runs once after the close to check Crabel open-range breakout entry triggers, update open positions, apply the 30% premium stop, the Day-3 hard exit and the adverse-close flag, and log outcomes.
**Entry points:** `ShortSwingMonitor.run_eod_check()` (`:356`)
**Imports (production):** requests, pandas, numpy · **Imported by:** `short_swing/run_short_swing.py:55` · **Broken/retired imports:** NONE
**Inputs** — `short_swing/output/ss_contracts_*.json` (`:287`), an open-positions state JSON (`:302`). External: Polygon daily candles (`:91`) and option mid (`:113`), throttled (`:85`)
**Logic and algorithms** — `check_crabel_trigger` (`:135`), `check_adverse_close` (`:168`), `ShortSwingPosition` lifecycle (`:198-270`)
**Decision branches** — **FINDING (×3).** `check_crabel_trigger` `:150` `if direction.upper() == 'CALL': … else:` (PUT branch `:158-162`) — no third arm. `check_adverse_close` `:180` same shape, and its PUT message at `:189` is built from a `rise_pct` computed in the else-branch, so a non-CALL, non-PUT token is **reported as "against PUT entry"**. `load_open_positions` `:314` `'direction': pos_data.get('direction', 'CALL')` — **a state file missing `direction` silently resurrects the position as a CALL**, and every subsequent trigger, adverse-close and P&L evaluation is then done on the bullish side. Together these mean a corrupted or partially-written state file **flips a short position long with no error**. **Other/blank path:** CALL on load, PUT on evaluation
**Computations and formulas (exact)** — CALL trigger `today_open > prior_high` (`:151-155`); PUT trigger `today_open < prior_low` (`:158-162`). `PREMIUM_STOP_PCT = 0.30` (`:53`), `MAX_HOLD_DAYS = 3` (`:52`), `ENTRY_WINDOW_MINS = 30` (`:54`). `pnl` at `:233`; `is_past_hard_exit` at `:221`; `days_in_trade` at `:224`
**Models** — NONE
**Outputs** — Open-positions state JSON (`:332-337`), `ss_outcomes_<date>.csv` (`:345`), a cumulative CSV (`:353`). **No atomic promotion** — `json.dump` straight onto the live state path (`:336-337`), so an interrupted write leaves a truncated state file that the `.get('direction','CALL')` default at `:314` then reinterprets as long
**Handoff** — Receives from `short_swing_contract.py`; hands to `short_swing_outcome_logger.py`. Join key: `ticker` + `option_symbol`
**Missing-data handling** — Candle/quote failures return empty/None and the ticker is skipped. Missing contracts file → empty list. Missing state file → no open positions. **Every position field in `load_open_positions` (`:302-330`) is read through `.get(..., default)`**, so a partial record is silently completed rather than rejected. §10-compliant? **N**
**Contradictions found here:** the docstring `:21-22` documents the trigger symmetrically ("For CALL: … For PUT: …"), but the implementation has no representation for the `STRANGLE` value that `short_swing_screener.py:23` documents as legal, nor for a blank. **The CALL default at `:314` is the inverse of a fail-closed posture**
**Gaps found here:** DEAD; no third direction arm anywhere; **non-atomic state persistence combined with a bullish default is the sharpest failure mode in this lane**
**Comment/docstring claims audited:** `:32-34` "Reads Polygon API for EOD prices and option quotes. Writes only to short_swing/output/" → **HOLDS**. `:26-30` exit-condition list → **HOLDS** against `:52-53` and `:420`. `:12` "NOT an intraday loop — runs once after close" → **HOLDS**
**Confidence in this section:** MEDIUM-HIGH

---

### short_swing/short_swing_outcome_logger.py
**Classification:** LIBRARY · DEAD. Component 4 of 5 — outcome aggregation and actuarial feed formatter
**Real execution position:** NOT_INVOKED. Imported by `short_swing/run_short_swing.py:56` only
**Task in the process:** Aggregates EOD-monitor outcomes, computes win rate by Crabel pattern and phase, average P&L by hold day and exit-reason distribution, and formats state-hash observations.
**Entry points:** `run_outcome_logger()` (`:295`)
**Imports (production):** numpy, pandas · **Imported by:** `short_swing/run_short_swing.py:56` · **Broken/retired imports:** NONE
**Inputs** — `ss_outcomes_<date>.csv` (`:68`), `ss_cumulative_outcomes.csv` (`:47`), `ss_contracts_<date>.json` **with a glob fallback to the newest when the dated file is absent** (`:82-85`) — the same cross-date silent substitution as the 0DTE twin
**Logic and algorithms** — grouped statistics; `ACTUARIAL_THRESHOLD = 50` readiness gate (`:45`)
**Decision branches** — partition-based only. `str(row.get('direction', ''))` (`:222`) and `c.get('direction','')` (`:271`) default a missing direction to the **empty string**, which then becomes a distinct group key. **Other/blank path:** counted in the aggregate win rate under a blank label rather than excluded. Unlike the contract selector's CALL default this is at least non-fabricating. No CALL/PUT conditional exists
**Computations and formulas (exact)** — `ACTUARIAL_THRESHOLD = 50` (`:45`); **`OUTPUT_DIR = Path('short_swing/output')` (`:46`) and `CUMULATIVE_PATH` (`:47`) are relative paths**, so all output location depends on the process working directory rather than `__file__` — running the runner from any directory other than the repo root writes the cumulative ledger elsewhere. Statistics in `compute_daily_stats` (`:95`) and `compute_cumulative_stats` (`:124`)
**Models** — NONE. A Sharpe approximation is reported without stated convention, as in the 0DTE twin
**Outputs** — `ss_daily_summary_<date>.json` (`:352-354`), `ss_cumulative_outcomes.csv` (`:331`), `ss_actuarial_feed_<date>.json` (`:336-338`), `ss_intel_panel.json` (`:347-349`). No atomic promotion, no schema/version field
**Handoff** — Receives from `short_swing_monitor.py`. **Hands to nothing** — no reader of `ss_intel_panel.json` or `ss_actuarial_feed_*.json` exists in the tracked tree. Join key: `state_hash`
**Missing-data handling** — Missing outcomes CSV → empty DataFrame (`:65-72`). Missing contracts → glob fallback then empty list (`:80-92`). Every panel field read through `.get(..., default)` (`:239-290`). §10-compliant? **N**
**Contradictions found here:** the docstring `:12-17` asserts that short-swing observations "build a SEPARATE hash accumulation layer to the swing (Scope 1) observations — same hash IDs, different trade_type", and that "the actuarial DB gains both swing AND short-swing base rates for the same market states, enabling hold-period optimisation". **No `trade_type` field is written by `format_actuarial_observations` (`:203-237`), and no ingestion path for these observations exists anywhere.** The claimed separation mechanism is absent from the code that is supposed to implement it
**Gaps found here:** DEAD, with an unconsumed principal output; relative `OUTPUT_DIR` (`:46`) makes the artefact location non-deterministic — the 0DTE twin has the identical construction (`zero_dte/zero_dte_outcome_logger.py:47`), so both ledgers share the fragility
**Comment/docstring claims audited:** `:18-24` "KEY STATS TRACKED" list → **HOLDS**. `:12-17` separate-hash-layer claim → **FALSE**. `:26-30` output list → **HOLDS**
**Confidence in this section:** MEDIUM-HIGH

---

### bridge/avshunter_reader.py
**Classification:** LIBRARY (104 lines)
**Real execution position:** NOT_ESTABLISHED — imported by 1 module [OBSERVED, extractor]; no orchestrated path reaches `bridge/`
**Task in the process:** Reader shim for AVSHUNTER artefacts consumed by the `bridge/` package.
**Entry points:** none detected (no `__main__`, no CLI) [OBSERVED, extractor]
**Imports (production):** see `_tooling/facts/` · **Imported by:** 1 module · **Broken/retired imports:** NONE detected
**Inputs** — 8 fallback chains detected [OBSERVED, extractor]; specific paths NOT_ESTABLISHED
**Logic and algorithms** — NOT_ESTABLISHED. Decision branches: **no direction token anywhere in the file** (0 hits) — CALL / PUT / other-blank all **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE (no model construct detected)
**Outputs** — 2 write sites detected [OBSERVED, extractor]; targets NOT_ESTABLISHED. Atomic promotion: NOT_ESTABLISHED. Schema/version field: none detected
**Handoff** — NOT_ESTABLISHED
**Missing-data handling** — 8 fallback chains present but individually NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** UNTRACED (GAP-607)
**Comment/docstring claims audited:** the file has **no module docstring**, so no authority claim is asserted
**Confidence in this section:** LOW — extractor facts only; the file body was not read. Recorded here for coverage completeness, and its internals are explicitly **UNTRACED**
