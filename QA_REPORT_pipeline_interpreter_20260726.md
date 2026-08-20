# QA Report — Pipeline Interpreter Automation v2
**Date:** 26 July 2026 · **Target operational run:** 27 July 2026
**QA engineer role:** independent verification, not authorship. Nothing in this report was fixed.

---

## 1. Verdict

# DO NOT APPROVE

A bypassable `NEGATIVE_RR` guard is disqualifying on its own. This is not a marginal or edge-case finding: the guard backing Phase 3's actual candidate-planning entry point (`run_lab_batch`) can be defeated by either of the two most ordinary forms of bad data — a `NaN` R:R or a blank/absent R:R field — and in both cases the affected ticker lands in the **executable candidates list**, indistinguishable from a legitimately vetted candidate. Both were reproduced end-to-end against the real production function, not inferred from reading code.

**On the handover's 14 acceptance criteria (section 11):** I could not score against them. No handover document exists in this repository — only `CLAUDE_CODE_QA_pipeline_interpreter.md` (the QA brief itself) is present, and it paraphrases handover claims (11/11 tests, specific NFLX evidence-package results) without including the source document or its criteria list. I searched the repository for any file matching "handover" and found none besides the brief. This is reported as an inability to complete part of the deliverable, not glossed over — see Section 7 (Untested).

This verdict would not change even if the acceptance-criteria document were located, because P3/P4 alone meet the brief's own CRITICAL bar: *"a sovereign control can be bypassed... or capital could be allocated."*

---

## 2. Environment Baseline (Phase 0)

- **Git HEAD:** `49de2270a7368c969631ca75db9f14a0b54a5f54`
- **Working tree:** dirty — 371 changed/untracked paths, including modifications to `pipeline_interpreter_commands.py` and `pipeline_interpreter_engine.py` (see Section 6, MEDIUM finding) and a large amount of untracked audit/spec material at repo root.
- **Python:** 3.14.0 · **OS:** Windows-11-10.0.26200-SP0 · Shell: git-bash (POSIX), cross-checked with native PowerShell 5.1 where the brief specified it.
- **Lab export freshness:** latest `lab_triage_view_*.csv` is `lab_triage_view_20260723_072618.csv` (filesystem timestamp 23 Jul 11:12). Relative to today (26 Jul) this is 3 days stale; relative to the target operational run (27 Jul), 4 days stale. **Per the brief's own gate, Phase 3 and Phase 4 were not run against this data.** All Phase 2 findings below were produced against synthetic fixtures under `tempfile.TemporaryDirectory()`, not this stale file.
- **capture_staging writability:** writable from both the Bash/git-bash process and a native PowerShell process. The brief's documented "Known Limitation" (Codex process blocked, operator PowerShell allowed) **did not reproduce under either identity tested.** **Untested:** a service-account identity (e.g., a scheduled task's own account), which could still differ from both identities I tested.
- **Webull:** running. This contradicts the brief's stated assumption of an unattended session with Webull absent. Reported factually; no phase in this QA pass depended on Webull's running state, and the capture-suite tests that touch this domain use an injected `FakeBackend()`, not the real window (confirmed, see Phase 1).

---

## 3. Test Results (Phase 1)

| Command | Collected | Passed | Failed | Errored | Skipped |
|---|---|---|---|---|---|
| Brief's exact declared automation_v2 command | 25 | 25 | 0 | 0 | 0 |
| Brief's exact declared capture_v1 command | 35 | 35 | 0 | 0 | 0 |
| Full discovery, all 13 `automation_v2*` files in `tests/` | 58 | 58 | 0 | 0 | 0 |

**The handover's "11 tests run, 11 passed" claim does not match any measurement I could produce.** Not the declared command (25), not the full automation_v2 set (58), not either combined with the capture suite. I cannot identify what subset of the current working tree corresponds to "11" — most likely explanation, **unconfirmed**, is that the claim was measured against an earlier/narrower tree state before additional test files were added.

**Coverage gap in the handover's own verification procedure, independent of the count discrepancy:** the declared Phase 1 command runs 8 of the 13 `test_pipeline_interpreter_automation_v2*.py` files present in `tests/`. It omits `_adapter`, `_phase3`, `_phase4`, `_phase5`, `_report` — all five are untracked (`git status` shows `??`) and all pass when run. `_phase5` is the only test in the repository that exercises `pipeline_interpreter/automation_v2/live_provider.py` (also untracked), the module that wires the real Claude API into the sovereign-controlled workflow. A verification procedure that cannot detect a regression in the one module touching live model output is a material gap, separate from and in addition to the 11-vs-25-vs-58 discrepancy.

**HIGH — repo-wide false-green risk under the declared test runner.** `tests/test_pipeline_interpreter_trusted_source.py` (untracked; covers the dirty-tree `get_trusted_interpreter_source()` change) collects **0 tests** under `python -m unittest` and reports `OK` — a false green. Root cause: it is written pytest-style (bare `test_*` functions using a `tmp_path` fixture), and `unittest`'s loader only collects `TestCase` subclasses. I confirmed `pytest` is not installed for the system Python, the repo-root `venv` (checked via its own `pip list`), or declared in any of the four `requirements*.txt` files in this repo. **This file cannot be executed by any method available in this environment.**

This is wider than one file: scanning all 47 non-`__init__.py` files in `tests/`, **24 use bare pytest-style functions** (vs. 23 using `unittest.TestCase`) — including tests that read as safety-relevant: `test_directional_bias_fixes.py`, `test_handoff_contract.py`, `test_pse_retired_authority.py`, `test_options_research_contract.py`, `test_macro_quant_packet.py`, and 19 others. None of these 24 are executable in this environment. I have not evaluated whether their logic is sound under pytest elsewhere — only that they cannot run here, and that anyone verifying this repository's tests with `python -m unittest discover` (a reasonable default action) would see roughly half the suite silently vanish into a false "OK."

Every file the brief's Phase 1 command actually names uses `unittest.TestCase` and executed correctly — this finding does not affect the 25/25 and 35/35 results above, both of which are real.

---

## 4. Sovereign Control Matrix (S1–S10)

| # | Control | Status | Evidence |
|---|---|---|---|
| S1 | Negative option R:R → `NEGATIVE_RR` | **COVERED** (ordinary negatives) / **BYPASSED** (NaN/absent — see P3, P4) | `test_pipeline_interpreter_automation_v2.py::SovereignVetoTests::test_negative_rr_is_negative_rr_stop_and_never_executes`; `test_pipeline_interpreter_automation_v2_lab_batch.py::test_plan_uses_lab_and_stops_negative_rr`. Both use ordinary negative floats only. |
| S2 | `NEGATIVE_RR` → effective `STOP` | **COVERED** | Same tests as S1. |
| S3 | Negative R:R can never become `GO`/`EXEC`/`READY_EXECUTE` | **COVERED** | Same test as S1. |
| S4 | EIL action on negative R:R remains `STOP` | **COVERED** | Same test as S1. |
| S5 | Upstream `BLOCKED`/`STOP`/`NO_TRADE` excluded from candidates | **COVERED** | Implicit in `test_plan_uses_lab_and_stops_negative_rr`'s fixture; explicit in new `tests/qa/test_p1_p10_adversarial_probes.py::P6UpstreamBlockedTests` (both `veto.py` and `lab_batch.py`). |
| S6 | Missing or invalid evidence fails closed | **PARTIAL** | `core.interpret_ticker`'s `EVIDENCE_INVALID` branch (core.py:36) is exercised by **zero** tests in the repository (grepped every test file for the literal string). Adjacent coverage exists for provider-exception fail-closed (`test_provider_failure_degrades_to_stop`, `test_shadow_dispatch_is_fail_closed`) and evidence-package completeness (`test_missing_assets_are_reported`, plus new P7/P8 tests) — different mechanisms, not this veto path. |
| S7 | Ticker mismatch stops the workflow | **COVERED** | `test_exact_ticker_token_prevents_f_nflx_collision`, `test_manifest_rejects_ambiguous_asset`, `test_ticker_mismatch_is_flagged_and_evidence_is_retained`. Mechanism for the capture layer is operator transcription — see P9. |
| S8 | Screen-type mismatch stops the workflow | **COVERED** | `test_wrong_visible_screen_type_is_quarantined`, `test_plain_options_label_cannot_pass_greeks_route`, `test_short_interest_mismatch_does_not_create_canonical_asset`. |
| S9 | Provider interpretation cannot promote upstream permission | **COVERED**, extended to `live_provider.py`'s seam | `test_provider_go_cannot_promote_advisory_interpreter` (existing). New `tests/qa/test_s9_live_provider_permission_promotion.py`: a hostile fake shaped exactly like `live_provider.py`'s `LegacyClaudeProvider.analyze()` contract proposes `EXECUTE` with a trade_brief claiming `FULL_EXECUTE`/`APPROVED`; `execution_permission` and `capital_permission` stay at their denied defaults, verdict never exceeds `WAIT`. Also confirmed as a hard dataclass invariant: constructing `TickerRunResult(execution_permission="FULL_EXECUTE")` directly raises `ValueError`. **Scope limit:** the real `create_live_shadow_provider()` (network call, real credential) was not invoked — out of bounds for QA. This proves the sovereign layer contains whatever a provider proposes; it does not test `live_provider.py`'s own credential-loading code path. |
| S10 | Any path never places trades or allocates capital | **COVERED** | `test_execution_enabled_request_is_rejected`; the `TickerRunResult` invariant above; new P10 batch-isolation test. |

---

## 5. Adversarial Probe Results (P1–P10)

| # | Result |
|---|---|
| **P3** | **CRITICAL (escalated from the initial MEDIUM assessment).** An absent/blank `rr_predicted` field reaches the same executable `candidates` list as P4, via the identical code path (`not ticker or vetoes` in `lab_batch.py`). Reproduced end-to-end against the real `run_lab_batch()`: a two-row fixture with one ordinary-negative-R:R control (correctly stopped) and one blank-R:R row with `lab_verdict="READY_EXECUTE"` (incorrectly reached candidates). Test: `tests/qa/test_p1_p10_adversarial_probes.py::P3AbsentFieldTests::test_absent_rr_candidate_reaches_executable_candidates_end_to_end`. |
| **P4** | **CRITICAL.** NaN R:R bypasses `lab_batch._negative_rr()` (`Decimal("nan") < 0` raises `InvalidOperation`, caught by the same `except InvalidOperation: return False` meant for unparseable strings) and reaches the executable candidates list in the real `run_lab_batch()` output. Separately, `veto.evaluate_sovereign_veto()`'s `rr < 0` comparison has no try/except anywhere and crashes uncaught on the same input — see Section 6 HIGH finding. Test: `tests/qa/test_p4_nan_rr_bypass.py` (3 methods, all fail as designed). |
| P1 | Zero R:R is not flagged negative — architecturally identical to a healthy positive R:R at this layer. Intentional per the control's literal definition (`< 0`, not `<= 0`); documented, not a defect. |
| P2 | No bypass. Both implementations correctly negate strings and native Python floats. |
| P5 | STOP survives. `eil_action` is hardcoded `"STOP"` at every construction site in `veto.py`; no code path lets an upstream or provider-claimed `EXECUTE` reach it. Confirmed directly. |
| P6 | Upstream `BLOCKED` with a perfect R:R is excluded in both implementations. Confirmed directly. |
| P7 | 11/12 assets refuses to publish. Also tested beyond the literal ask: a **falsified** `status: "complete"` does not bypass the independent required-kind recomputation in `validate_package` — genuine defense-in-depth. |
| P8 | A corrupted asset (bytes changed after hashing) produces `PACKAGE_HASH_MISMATCH` and refuses to publish; nothing is copied to the target directory. |
| P9 | **Mechanism identified — relies solely on operator confirmation.** The code calls Python's `input()`; the match method is self-labeled `"OPERATOR_EXACT_SCREEN_TRANSCRIPTION"` in `market_screen.py`. No OCR, no pixel/content check. The filename (`AAPL_daily.png`) is never validated against content. An inattentive operator who rubber-stamps the prompt defeats this control entirely. |
| P10 | One failing candidate does not abort the batch. Verified via a monkeypatched `run_e2e_workflow`: the failing ticker records `status: stopped, effective_verdict: STOP`, the other completes, overall batch status correctly becomes `"incomplete"` / `NO_GO_BATCH_INCOMPLETE`. |

---

## 6. Defects

### CRITICAL — NEGATIVE_RR guard bypassed by NaN R:R (P4)
**File:** `pipeline_interpreter/automation_v2/lab_batch.py:42-49`
**Repro:** `tests/qa/test_p4_nan_rr_bypass.py`. Minimal repro: `_negative_rr({"rr_predicted": "nan"})` returns `False`. End-to-end: a `lab_triage_view_*.csv` row with `rr_predicted="nan"`, `lab_verdict="READY_EXECUTE"` appears in `run_lab_batch()`'s `candidates` list, not `stopped`.
**Root cause:** `Decimal("nan") < 0` raises `decimal.InvalidOperation` (parsing NaN succeeds; the *comparison* fails). The `except InvalidOperation: return False` written to catch unparseable strings also catches this, conflating "cannot parse" with "is NaN."

### CRITICAL — NEGATIVE_RR guard bypassed by absent/blank R:R (P3, escalated)
**File:** `pipeline_interpreter/automation_v2/lab_batch.py:42-49`
**Repro:** `tests/qa/test_p1_p10_adversarial_probes.py::P3AbsentFieldTests::test_absent_rr_candidate_reaches_executable_candidates_end_to_end`. A row with `rr_predicted=""` and `lab_verdict="READY_EXECUTE"` reaches `candidates`, identically to P4.
**Root cause:** `if not raw: return False` — the same function's early-exit for a missing value is permissive, not fail-closed. Same code path as P4, different trigger.

### HIGH — two divergent, both-incorrect implementations of one sovereign control
**Files:** `pipeline_interpreter/automation_v2/lab_batch.py:42-49` vs. `pipeline_interpreter/automation_v2/veto.py:49-84`
Two independent functions enforce "negative/invalid R:R blocks execution" and handle the identical bad-input class in opposite, both-broken ways:
- `lab_batch._negative_rr()` — **silently permits** NaN and absent R:R (CRITICAL findings above).
- `veto.evaluate_sovereign_veto()` — **crashes uncaught** on NaN R:R. `parse_rr()` returns `Decimal("NaN")` without error; the comparison `rr < 0` at `veto.py:83` has no surrounding try/except. I traced all 4 call sites of `interpret_ticker` (`batch.py`, `package_shadow.py`, `shadow.py`, `trial.py`) — **none wrap the call itself in a try/except.** Whether a crash here ends up fail-closed is caller-dependent: `lab_batch.py`'s shadow-execution loop happens to wrap the broader `run_e2e_workflow(...)` call in `except Exception`, which would catch it and record `STOP`; I did not verify equivalent protection exists in the other three call sites.

Neither implementation is correct. The crash-based path is fail-closed **by accident of an unrelated broad except clause one layer up**, not by design — it is one refactor of that surrounding try/except away from becoming a silent pass, at which point it would degrade to the same bypass as `lab_batch.py`.

### Root cause — a repeated defect class, not an isolated bug
P3 and P4 match a pattern already present in this codebase under other names: `usslind_quarantined` false on stale data, gamma flip defaulting to `min(strike)`, morning gate CHECK 1 passing on `None` (all referenced in the QA brief's own "Known gotchas" and prior-incident framing). All four share one shape: **a guard returns a permissive default in exactly the situation where the correct output is an error or an explicit exclusion.**

I grepped `pipeline_interpreter/automation_v2/*.py` for every comparison or truthiness guard that could plausibly gate a numeric field capable of being `NaN`, `None`, or absent (`if x < 0`, `if x > threshold`, `if not x`, `is None` checks on numeric parses, and every `float(`/`int(`/`Decimal(` call site). Of the ~90 guards in the module, the large majority are path-existence, config, or count checks unrelated to this class. **Three instances of the actual pattern were found and confirmed empirically, not by inspection alone:**

1. **`lab_batch.py:47`** — `Decimal(raw) < 0` inside `_negative_rr()`. Confirmed CRITICAL above (P3, P4).
2. **`veto.py:67,83`** — `Decimal(cleaned)` / `rr < 0` inside `parse_rr()`/`evaluate_sovereign_veto()`. Confirmed HIGH above (crashes rather than bypasses, but is the same "no defined behaviour for NaN" root defect).
3. **`market_structure.py:50-51`** — `_present(value)`, defined as `value is not None and str(value).strip() != ""`. Confirmed by direct test: `_present(float("nan"))` returns `True`. This function gates **every** field in `MARKET_STRUCTURE_FIELDS` — `call_wall`, `put_wall`, `gamma_flip`, `max_pain`, `gex_score`, `wbs_score`, `trigger_score`, and seven others — used by `project_market_structure()` / `enrich_trade_brief()` to populate the trade brief. I constructed a `TickerRunRequest` with all six of `call_wall`/`put_wall`/`gamma_flip`/`max_pain`/`wbs_score`/`trigger_score` set to `float("nan")`: every one passed through into the projected trade brief unfiltered, with no numeric-validity check anywhere in the function. **No test in the repository covers this.** The only test that touches `market_structure.py` at all (`test_pipeline_interpreter_automation_v2_report.py`, itself one of the 5 untracked files the declared Phase 1 command omits) exercises only clean values (`call_wall: 50`, `gamma_flip: 44.37`) — never `NaN`, `None`, or absent. Given the QA brief's own "Known gotchas" section already flags gamma_flip/call_wall/put_wall/max_pain as historically defaulting to `min(strike)` rather than a genuine computed level, this projection layer would pass a `NaN` version of that same failure straight into the trade brief a human or the LLM narrative reads, with no guard catching it at any point in this module.

**This is the real finding.** P4 is one instance of a pattern that recurs at least three times in one module, and by the brief's own account, recurs under other names elsewhere in the codebase. A fix to `_negative_rr()` alone would leave two of the three confirmed instances in place.

### MEDIUM — chart-evidence substitution weakens the visual-evidence assumption behind S8/P9
**Files:** `pipeline_interpreter_engine.py` (dirty, uncommitted), `pipeline_interpreter_commands.py` (dirty, uncommitted)
`build_chart_evidence_block()` synthesizes a text block from pipeline-row fields and instructs the LLM: *"No manual chart screenshots are required"* / *"Do not ask for screenshots and do not say the chart section is impossible."* This is not part of the automation_v2 sovereign system under QA — it belongs to the separate interactive chat interpreter (`/triage`, `/ticker`, `/story`, etc.) — but it substitutes derived text for the visual evidence that S8 (screen-type mismatch) and P9 (ticker-in-image correctness) were designed around. Not a defect in isolation; flagged because it weakens an evidence requirement as an apparent side effect of an uncommitted, undocumented change (it appears nowhere in `pipeline_interpreter/CLAUDE.md`'s own build history, which was last updated 25 May 2026 and claims "ALL SYSTEMS CLEAN"), rather than as an explicit, reviewed decision.

---

## 7. Untested

- **Phase 3 (lab-driven planning against the real Lab export) and Phase 4 (single-ticker E2E shadow reproduction)** — not run, per the brief's own stale-data gate. The latest `lab_triage_view_*.csv` is 3–4 days stale relative to the target run. All Phase 2 findings were produced against synthetic fixtures instead; they establish that the defect exists and is reachable through the real function, not that it fires against tomorrow's actual data.
- **24 of 47 test files in `tests/`** (pytest-style) cannot be executed in this environment at all (pytest not installed anywhere I could find). Their logic is unverified here — not "passing," not "failing," genuinely unknown. This includes tests with names suggesting they guard directional-bias and PSE-retirement logic.
- **`live_provider.py`'s actual network path** (`create_live_shadow_provider()`, real Anthropic API call, real `.env` credential) — not exercised. S9 was verified at the seam it plugs into (see matrix), not through an actual live call. `_load_repository_anthropic_key()`'s regex-based `.env` parsing was read, not tested.
- **S6's `EVIDENCE_INVALID` branch in `core.interpret_ticker`** — zero existing test coverage found; not independently tested by me either (I did not write a new test for this, only identified the gap, since it was outside the four items you asked me to prioritize this pass).
- **capture_staging ACL behavior under a service-account identity** — only the interactive Bash and PowerShell identities were tested; both succeeded, contradicting the brief's documented limitation, but a scheduled-task service account remains untested and could differ.
- **The handover document itself** — does not exist in this repository under any name I could find. The 14 acceptance criteria in its section 11 could not be enumerated or scored.
- **Whether the P3/P4 defect class extends beyond `automation_v2`** — the brief names three prior instances (`usslind_quarantined`, gamma flip `min(strike)` default, morning gate CHECK 1 on `None`) in other parts of the codebase; I did not grep outside `automation_v2` for further instances, since that was scoped to this module by your instruction.
- **Whether `_phase3`/`_phase4`/`_report`'s test content (beyond `_phase5`, which I did trace) covers anything safety-relevant** — I confirmed they exist, are untracked, and pass, but did not read their bodies.

---

## 8. Confidence

**80%** in the verdict itself (DO NOT APPROVE) — the two CRITICAL findings are reproduced end-to-end against real production code with passing-when-fixed, failing-when-broken test assertions, not inference. Low residual uncertainty there.

**Materially lower confidence (I'd estimate 50–55%) in this report's completeness** as a full safety audit, for reasons stated plainly above: roughly half the test suite is unexecutable in this environment and unaudited by me; Phase 3/4 never touched real data; the acceptance-criteria scoring couldn't be performed at all; and the root-cause sweep, while it found three confirmed instances, was scoped to one module by instruction and almost certainly does not exhaust the pattern given the brief's own admission of three prior instances elsewhere.

**What would raise confidence:**
1. Installing `pytest` and re-running the 24 currently-unexecutable test files.
2. Locating or being given the actual handover document to score against its 14 acceptance criteria.
3. A fresh Lab export on or after 26 July, enabling Phase 3/4 against real data.
4. Extending the root-cause grep beyond `automation_v2` to the three named prior instances and the rest of the codebase.
5. A test for `core.interpret_ticker`'s `EVIDENCE_INVALID` branch (S6), currently at zero coverage.
