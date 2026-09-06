# AVS-IMP-FIX-001 — Implement the AVS-FIX-001 register: key verification, Level 1 fixes, Level 2 offline items

**Issued:** 2026-09-06
**Agent:** Claude Code as **implementer** — this prompt grants write access to the repository for the items below and nothing else. A separate session (or Codex) verifies; you do not self-certify.
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence` · **Interpreter:** `C:\Python314\python.exe`
**Register of record:** `audit\pipeline_map\AVS-FIX-001_PRODUCTION_READINESS_FIX_REGISTER_20260906.md` — read it first; every item ID below refers to it.
**Design authority:** AVS-SD-003 (C1–C8), AVS-RCA-003 (defects + DECISIONS_FOR_ACK), AVS-THS-001 §4 (tier definition), AVS-TST-QT-001 (defects), AR-003 §6.3/§8.
**Outputs:** `audit\pipeline_map\AVS-IMP-FIX-001\` (claim sheet, test XMLs, scripts) and code changes on branch `avs-fix-001`.

---

## 0. Binding rules

1. **Never execute the pipeline.** No `--evening`, `--morning`, `--auto`, `--finalise`, `--replay`; no stage scripts; no Lab server; no Interpreter; no MarketData/Polygon/FRED calls. Permitted invocations, each once: `python intelligent_orchestrator.py --evening --plan-only --as-of-utc <now>` (with a filesystem snapshot diff proving no writes), `python build_macro_json.py --dry-run` (no API call), and exactly **one** `GET https://api.anthropic.com/v1/models` in Part A.
2. **Never print, log or write any secret.** Report key prefix pattern, length and whitespace booleans only. Redact `x-api-key`/`Authorization`/`token=` in every logged request. Do not define PowerShell functions named with single letters (`H` collided with `Get-History` on 6 Sep and echoed a key).
3. **Never set a production flag or edit `contracts\dynamic_session_runtime_v1.json`** except where an item below says so explicitly (none do). Flag-on behaviour is tested only via monkeypatched unit tests.
4. **Backup before every item**: `backups\avs_fix_001_<item>_prechange_<YYYYMMDD_HHMMSS>\` with a SHA-256 `MANIFEST.json` of every file the item touches. No exceptions — QT-D10 was two files changed without one.
5. **One commit per item** on branch `avs-fix-001` from the baseline tag created in W0.1. Commit message: `AVS-FIX-001 <item>: <one line> [gates: …]`.
6. **Existing tests**: edit only when an assertion encodes retired policy (cite the AR-003 clause) or a fixture lacks governed geometry; record every edit in the claim sheet with its T2 classification (`OBSOLETE_ASSERTION_CORRECTED` / `FIXTURE_CORRECTED` / `PROTECTION_WEAKENED` / `UNRELATED`). A `PROTECTION_WEAKENED` edit is forbidden.
7. **Three directions** in every rule and every test: CALL / PUT / OTHER (STRANGLE, UNRESOLVED, null). RG-07 — OTHER rows stay `STAND_DOWN` / `NOT_APPLICABLE` and never reach the Lab — is a protected positive; test it after every item that touches Options, EOD or the Lab.
8. **Isolated pytest processes** per file (the `vanguard/scripts` shadowing makes single-process collection invalid). Include `tests\msi\` in every matrix run from W0.3 onward.
9. **No new state names** (`NOT_EVALUATED`, `INSUFFICIENT_DATA`, `UNAVAILABLE_PROVIDER`, `DataExceptionReason` members only). **No new authority**: nothing you add may grant or remove capital permission; Execution Gate stays the sole writer of `final_action`.
10. **Status vocabulary in the claim sheet**: `IMPLEMENTED — OFFLINE VERIFIED`, `IMPLEMENTED — AWAITING RUN`, `BLOCKED`, `DEFERRED`. **Never `CLOSED`** — that is assigned by the tester after a run artefact shows the item firing.

---

## Part A — Credential verification (W4.1 closure evidence) — do first, ~10 minutes

The key was rotated on 6 Sep. Two consumers read `ANTHROPIC_API_KEY` from the **process environment**: `worker3/adapters/anthropic_http.py:41` (`os.environ.get`) and `build_macro_json.py:559` (`anthropic.Anthropic()` — the SDK reads the same variable). Neither loads `.env`. The orchestrator's `_load_dotenv_safe()` (`intelligent_orchestrator.py:333-350`) uses `override=False`, so a real environment variable wins over `.env`.

Write `audit\ops\verify_anthropic_key.py` (stdlib only) and run it from a **fresh** shell. It must:

```python
# audit/ops/verify_anthropic_key.py  — reports facts about the credential, never the credential
import os, re, json, sys, subprocess, urllib.request, urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
report = {}

def facts(value):
    if value is None: return {"present": False}
    return {"present": True, "length": len(value),
            "prefix_ok": value.startswith("sk-ant-api03-"),
            "has_ws": value != value.strip(),
            "has_crlf": ("\r" in value) or ("\n" in value),
            "has_quotes": value[:1] in "\"'" or value[-1:] in "\"'"}

# 1. scopes (Windows): read via PowerShell so we see User/Machine, not just Process
def scope(name):
    out = subprocess.run(["powershell","-NoProfile","-Command",
        f"[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','{name}')"],
        capture_output=True, text=True).stdout.rstrip("\r\n")
    return out if out else None
report["user_scope"]    = facts(scope("User"))
report["machine_scope"] = facts(scope("Machine"))
report["process_scope"] = facts(os.environ.get("ANTHROPIC_API_KEY"))

# 2. .env must not carry the key (single source rule)
env = REPO / ".env"
report["dotenv_has_line"] = env.exists() and any(
    l.strip().startswith("ANTHROPIC_API_KEY") for l in env.read_text(encoding="utf-8", errors="ignore").splitlines())
report["dotenv_txt_exists"] = (REPO / ".env.txt").exists()   # must be False (AVS-OPS-001)

# 3. process value must equal user value (fresh shell check)
report["process_equals_user"] = (os.environ.get("ANTHROPIC_API_KEY") == scope("User"))

# 4. one authenticated, token-free request
key = os.environ.get("ANTHROPIC_API_KEY", "")
req = urllib.request.Request("https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.loads(r.read().decode())
        report["models_status"] = r.status
        report["sonnet_4_6_listed"] = any("claude-sonnet-4-6" in m.get("id","") for m in body.get("data", []))
except urllib.error.HTTPError as e:
    report["models_status"] = e.code
    report["error_type"] = json.loads(e.read().decode()).get("error", {}).get("type")

out = REPO / "audit" / "ops" / "verify_anthropic_key_result.json"
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
ok = (report["user_scope"]["present"] and not report["machine_scope"]["present"]
      and report["process_equals_user"] and not report["dotenv_has_line"]
      and not report["dotenv_txt_exists"] and report.get("models_status") == 200
      and report.get("sonnet_4_6_listed"))
sys.exit(0 if ok else 1)
```

**Pass condition:** exit 0. If `dotenv_has_line` is true, remove that one line from `.env` (backup first; touch nothing else in the file) and re-run. If `models_status` is 401, stop and report — the environment, not the code, is wrong. Then run `python build_macro_json.py --dry-run` and record that it loads inputs without error (no API call is made in dry-run). Record both in the claim sheet as W4.1 evidence.

---

## Part B — Workstream 0: baseline and test integrity

### W0.1 — Baseline commit and tag (first action after Part A)

```
git status --porcelain                         # expect 63 modified / 33 untracked
git add -A && git commit -m "AVS-FIX-001 baseline: 4-6 Sep build (SD-003 cycle 1, adapter, DDD integration+closure, domain/ refactor) as of 2026-09-06"
git tag -a avs-baseline-20260906 -m "First committed state after AVS-SD-003 / DDD closure; runtime profile 054a76be"
git checkout -b avs-fix-001
```

Before `git add -A`: confirm `.env` is ignored and not staged; confirm no file > 100 MB; confirm `_attic/` is tracked (it must stay reversible). If the `domain/` refactor can be separated into its own commit in under an hour (it is untracked, so `git add domain/ canonical_data/outcome_maturation.py canonical_data/run_plan_store.py orchestrator/session_authority_adapter.py` as a second commit is likely trivial), do two commits; otherwise one and note it. Then ensure `run_meta.json` records the tag: locate where `baseline_commit_hash` is written in `intelligent_orchestrator.py` and add `git_describe` (`git describe --tags --always --dirty`) beside it. Test: a unit test that the run-meta writer includes both fields.

### W0.2 — Flag-default test integrity (QT-D01)

`tests\test_dynamic_session_phase0.py:54-58` currently passes `from_environment({})`, the explicit-mapping branch that hard-codes all-False, while production calls `from_environment()` and loads the runtime profile. Replace it with tests that assert the truth:

```python
def test_explicit_empty_mapping_yields_all_disabled():           # the old property, correctly named
    flags = DynamicSessionFeatureFlags.from_environment({})
    assert not any(getattr(flags, f) for f in flags.__slots__)

def test_production_profile_enables_controlled_set_and_withholds_auto(monkeypatch):
    monkeypatch.delenv("AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL", raising=False)
    flags = DynamicSessionFeatureFlags.from_environment()          # what production calls
    assert flags.auto_dispatcher is False
    enabled = [f for f in flags.__slots__ if getattr(flags, f)]
    assert len(enabled) == 8, enabled                               # pin the controlled set explicitly by name

def test_master_kill_switch_disables_everything(monkeypatch):
    monkeypatch.setenv("AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL", "1")
    flags = DynamicSessionFeatureFlags.from_environment()
    assert not any(getattr(flags, f) for f in flags.__slots__)

def test_runtime_profile_hash_is_pinned_by_release_manifest():
    live = sha256(Path("contracts/dynamic_session_runtime_v1.json").read_bytes()).hexdigest()
    pinned = json.loads(Path("audit/ddd_closure_20260905/AVS_DDD_CLOSURE_RELEASE_MANIFEST_20260905.json").read_text())["production_files"]["contracts/dynamic_session_runtime_v1.json"]
    assert live == pinned, "runtime profile changed without a release manifest update"
```

Adapt attribute names to the real `DynamicSessionFeatureFlags`. The fourth test is the guard that makes silent profile changes impossible.

### W0.3 — `tests\msi\` into the matrix (QT-001 D-04)

Add `tests\msi\` to `audit\ops\AVS-OPS-001\scripts\run_matrix.py` (or the matrix runner you use). Run all five files isolated. For `test_c07_one_minute_volume_uniformly_allocated_and_labelled`: read the test and `market_structure\profile.py`'s volume allocation; determine whether the test or the code is wrong against AVS-SD-002 §9.1 ("estimate volume across touched bins only when the method is disclosed"); fix the code if the code is wrong, otherwise file it with the reason. Retire `test_quote_change_computation_is_not_implemented_anywhere_NOT_IMPLEMENTED` (it asserts an absence that is now false) with a one-line note. Run `test_logic.py` to completion and record the result.

### W0.4 — Documentation truth (QT-D08/D09/D10)

Append a "Corrections (6 Sep)" section to `audit\ddd_closure_20260905\AVS_DDD_CLOSURE_CLAIM_SHEET_20260905.md`: the per-profile coverage gate is 0.95 before and after; the 0.90 is a new stage-level `min_usable_ratio`; the stated 77/78 rationale was wrong (the `last_region` `and` fails it, fixed by the exclusive-`to` change). Produce `audit\pipeline_map\AVS-IMP-FIX-001\test_edits_register.csv` classifying all 17 test files modified since `pre-tidy-20260904` (from `AVS-TST-QT-001\00_changed_files.csv`). Create retroactive backup manifests for `contracts\dynamic_session_authority_v1.json` and `canonical_data\request_ledger.py` from the `pre-tidy` tag content. Re-issue `AVS-AR-003_P0_RECERTIFICATION` as `_v2_20260906.md` with a `run_artefact_evidence` column per P0, citing `AVS-TST-QT-001\B_20260905_151448.csv` rows; P0-08 stays OPEN.

### W0.6 / W0.7 — CLI hygiene and arbitration

`--data-mode` on the dynamic path: emit a `WARNING` that it is ignored and why (`intelligent_orchestrator.py:6706`). `FINALISE` vs `BUILD_THESIS` callbacks (`:6721-6726`): separate them — `FINALISE` must assert provider-finalised evidence and mint a new run identity per Rev 1.1 §8.3 — or, if the dispatcher already guarantees that upstream, add the assertion and a test proving `FINALISE` cannot overwrite the accepted thesis. QT-D05: write `audit\pipeline_map\AVS-IMP-FIX-001\QT-D05_arbitration.md` citing `tests\msi\test_computation.py::test_c06` — production expands to the higher adjacent count; the independent implementation was wrong.

W0.5 (pin the venv base interpreter) is ACK's; record it as `DEFERRED — operator`.

---

## Part C — Workstream 1: data-integrity residuals

### W1.1 — `structural_target` null, never zero (QT-D04)

Locate the producer of `structural_target` for Lab rows (the ladder at `scripts\avshunter_options_intelligence.py:4138-4158` and any EOD/Lab projection that coerces `None` → `0.0` — grep for `fillna(0`, `or 0.0`, `float(x or 0)` on that field). Rule: a missing target is `None`/NaN with `target_state = UNRESOLVED`; `0.0` is never written for a price. Extend the semantic audit rule that catches `PROFILE_ZERO_AS_PRICE` to a generic `PRICE_FIELD_ZERO_AS_MISSING` covering `structural_target`, `invalidation_price`, `underlying_price`, `contract_bid`, `contract_ask` (a literal `0.0` bid is legitimate only when `contract_bid_size == 0` — encode that exception). Tests: the 13 CALL tickers from `20260905_151448` (`AEE, AVA, BEPC, CPRI, GIII, LZB, MD, NI, NSSC, OGE, TSSI, VNT, XRAY`) as a fixture → target null and audit rule fires; a PUT mirror; an OTHER row unaffected.

### W1.2 — Retired EIL telemetry cannot contradict a governed stand-down (QT-D06)

Where `eil_v3_verdict` is written into `eil_enriched` / `execution_v3_5`: if the row's governed `options_verdict == STAND_DOWN` or `invalidation_state != AVAILABLE`, the EIL verdict is written as `NOT_EVALUATED_RETIRED_TELEMETRY` (an existing-vocabulary equivalent if one exists — do not invent) and never as `EXECUTE*`. Alternatively, if EIL verdicts are genuinely retired, drop the column from those artefacts and the Lab and note it. The semantic audit rule `DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION` must then return 0 on a TTEK-shaped fixture. Three-direction test.

### W1.3 — `monetisability_authority` stamped on every row (QT-D07)

In `contracts\selected_contract_economics.py` (the record builder), set `monetisability_authority = "ADVISORY_ONLY"` and `monetisability_calculation_version` on **every** outcome including `FAILED`/`DATA_MISSING`. Ensure `lab_control.py` maps both (they are allow-listed; confirm a `first(sig, …)` assignment exists — the F29 shape). Test: fixture rows in each of the four monetisability states → 100% non-null in the Lab projection.

### W1.4 — Profile-stage guard semantics (QT-D03)

In `scripts\build_completed_market_profiles.py`: per-ticker provider `no_data` → `deferred` with `DataExceptionReason` `TICKER_INACTIVE`/`NOT_YET_OBSERVABLE`; transport/auth/rate errors → `exceptions` with `UNAVAILABLE_PROVIDER`; `failure_ratio = exceptions / input`; `usable_ratio = completed_usable / (input − deferred)`; stage status `FAIL` when `usable_ratio < min_usable_ratio (0.90)` **or** `failure_ratio > max_failure_ratio (0.05)`; population identity `input = processed + excluded + deferred + exceptions` asserted. `completed_profile_summary` must print all of: input, processed, usable, partial, deferred (by reason), exceptions (by reason), `usable_ratio`, `failure_ratio`, `guard_decision`. Tests: the `151448` shape (1,587 in, 0 usable, 46 no_data, 50 ATR exceptions) → `FAIL` with `guard_decision = MIN_USABLE_RATIO`; a healthy shape → `PASS`; 12% no_data with 95% usable among the rest → `PASS` (deferrals do not trip the guard).

### W1.5 — `contract_dte` in the Lab book

Derive from the OCC symbol's expiry and the run's completed session (trading days, XNYS calendar via `canonical_data\session_clock.py`) at the EOD projection; allow-list and map it in `lab_control.py`. Test: known symbol/session → expected DTE; absent contract → null with `NOT_APPLICABLE_NO_SELECTED_CONTRACT`.

### W1.6 — One spread authority (RCA3-D07, DEC-3)

Per-horizon `spread_max` in `DTE_CONFIG` becomes the authority; the terminal gate at `scripts\avshunter_options_intelligence.py:6018-6035` applies `min(horizon_band, flat_reviewable)` — for `1_5d` that is 15%. Remove or document the redundant constant. Test: a `1_5d` contract at 18% spread is blocked; a `6_10d` at 18% passes (its band is 25%); the 3 rows QT-001/RCA-003 found leaking are reproduced from `151448` and now blocked. Keep `domain\long_option_execution.py`'s single denominator untouched.

---

## Part D — Workstream 2: prepare the gate checks ACK will run (you do not run the pipeline)

Write `audit\ops\check_run_gates.py <run_id>` — read-only over `data\output\runs\<run_id>\` — that prints, for one run, every gate with filter and three-direction count: AG-01…AG-17 and RG-01…RG-09 exactly as `AVS-TST-QT-001\B_20260905_151448.csv` defined them; the DDD checks (one `pipeline_run_id` and one completed session across stages; build receipt present and plan-hash-bound; `run_meta.json` carries `git_describe`, all nine flags and the profile hash; `completed_profile_summary` `usable_ratio`/`guard_decision`); the audit `fail_count` split genuine/spurious with the failing tickers; and the seven AVS-MVP-001 §6 kill criteria. Exit non-zero if any P0 gate fails. Prove it on `20260905_151448` (must reproduce QT-001's numbers) and on `20260904_004338` (must show the baseline failures). This is what ACK runs after Monday's Evening (W2.1) and Tuesday's Morning (W2.2); it is also how the tester closes items.

Also write `audit\ops\check_warm_rerun.py <cold_run_id> <warm_run_id>` for W2.3: option-chain physical requests in the warm run (must be 0), `exact fresh dataset` count, ledger reconciliation, wall-time comparison.

---

## Part E — Workstream 3: the offline Level 2 items (after Parts B–D are green)

### W3.1 — DEC-2 shadow replay (measurement, no production change)

`audit\pipeline_map\AVS-IMP-FIX-001\w31_shadow_replay.py`: for every `BLOCK_SPREAD` ticker on `20260905_151448` (774) and on Monday's run when it exists, load its stored `OPTION_CHAIN` payload, re-run contract selection **in-process against the production selector** with bands δ ±0.10 and DTE ±7d (spread gate unchanged), then push each recovered contract through the production economics (`compute_trade_economics`) and the monetisability record. Report: recovered by spread (expect ~195), of which pass economics, of which `MONETISABLE`/`LIMITED`, split CALL/PUT. This number decides W3.2's scope; write it into `DECISIONS_FOR_ACK` as the DEC-2 answer.

### W3.3 — Per-contract rejection taxonomy (instrumentation)

In `select_best_contract` and its gates: record every contract evaluated as `{symbol, dte, delta, spread_pct, mid, gate_failed}` into a per-ticker `contracts_tested` list persisted alongside the Options row (JSONL sidecar or a compact column), plus `contracts_tested_count`, `best_alternative_symbol`, `best_alternative_spread_pct`, `primary_rejection_reason`, `secondary_rejection_reason`, `repair_attempted`, `repair_result`. Reason codes from the existing vocabulary plus, where absent, `REJECT_DTE_BAND`, `REJECT_DELTA_BAND`, `REJECT_SPREAD`, `REJECT_NO_CHAIN`, `REJECT_STALE_QUOTE` — add them to the central contract module, not inline. Test: a ticker with 74 side-correct contracts, 20 in DTE band, 1 in delta band, 0 passing spread → the counts and the primary reason are recorded exactly.

### W3.4 — `monetisability_state_timevalue` (DEC-1, RCA3-D05)

Add, beside the intrinsic floor, a second advisory record: Black–Scholes value of the selected contract at `structural_target` on the hold's final session (`T = max(dte − hold_days, 0)/365`, σ = `contract_iv`, r = 0, q = 0), same 20% profit floor, fields `monetisability_state_timevalue`, `monetisability_timevalue_profit_pct`, `monetisability_timevalue_model = "BS_CONST_IV_R0_Q0"`, `monetisability_timevalue_assumptions`. **Authority `ADVISORY_ONLY`; it changes nothing downstream.** Reuse `scripts\compute_greeks_bs.py` if it has a pricer; otherwise a 20-line BS in the economics module. Test: PNW CALL (strike 100, ask 0.85, target 100.82, IV 18.7%, 8 DTE at target) → intrinsic `NOT_MONETISABLE`, time-value `MONETISABLE`; a deep-ITM row → both `MONETISABLE`; assert time-value value ≥ intrinsic for every fixture (the lower-bound property).

### W3.5 — Derived tier field (THS-001 §4)

`contracts\opportunity_tier.py`: `derive_tier(row) -> (tier, tier_reason)` computed **only** from governed columns: direction lineage hash present; invalidation/target present and correct side; underlying R:R; `monetisability_state` and `_timevalue`; `contract_dte` vs hold; spread vs the horizon band; `execution_viability_state`; trigger/EOD status; `CONTRACT_REPAIR` route; `EQUITY_VALID_OPTIONS_NOT_MONETISABLE` with `best_alternative` for ARMED. Tiers `TIER_1 / TIER_2 / TIER_3 / ARMED / WATCH / BLOCK` per THS-001 §4, with `tier_reason` naming the single Tier-2 weakness or the ARMED promoter. Written into the Lab book as two advisory columns; the Lab sorts by tier then R:R. **It grants nothing** — add an authority test that `final_action` is unchanged for every fixture regardless of tier. Tests: one fixture per tier, CALL and PUT each; an OTHER row → `BLOCK`; a row with two weaknesses → `TIER_3`; a `MONETISABLE` row with `final_action = MANUAL_REVIEW` (Evening) → tier assigned, action untouched.

### W3.6 — IV-at-selection measurement (no code change)

`w36_iv_at_selection.py`: for the 232 `MONETISABLE` rows of `151448`, compare `contract_iv` at selection with the ticker's IV on the Discovery session (from the stored chain of the earlier run where available) and the premium 3 and 5 sessions earlier where chains exist. Report the distribution; if the median row is buying IV ≥ 20% above its 5-session-earlier level, recommend the early-lane design; otherwise recommend against. Write into `DECISIONS_FOR_ACK`.

### W3.9 — Outcome maturation runs nightly

`canonical_data\outcome_maturation.py` exists. Wire it as a **non-critical** post-book stage in the Evening path (governed degradation on failure, never abort) that schedules/records 1/5/10/20-session underlying outcomes for every ledger `CANDIDATE_DECISION`, including rejected/deferred (counterfactual). Test with a fixture ledger: decisions mature into `OUTCOME` events at the right sessions; append-only preserved; rerun idempotent. This is the item that makes calibration possible; nothing reads the outcomes yet.

W3.2 (contract universe → rank → repair) is **not** in this prompt: it is sized by W3.1's result and needs a short design note (AVS-SD-004) first. W3.7, W3.8, W3.10 are deferred.

---

## Part F — Workstream 4: Worker 3 transport fixes (W4.2) — package under `Documents\Codex\…\worker3_foundation\`, separate commit

In `worker3/adapters/anthropic_http.py`: on non-2xx read the body and record `error.type` and `error.message` in the receipt (never headers); do not decrement the call budget unless a 2xx with model output was received; record `credential_source = "os.environ"` and `credential_fingerprint = sha256(key)[:8]` in the receipt. Run the package's own suite (263 expected) plus new tests for the three changes. **No live call.**

---

## Part G — Verification, claim sheet, hand-off

1. After each item: its focused tests; after Parts B and C: the full matrix in isolated processes **including `tests\msi\`**, plus `tests\qa\`, `tests\rca\`, the dynamic-session pack — record XMLs under `audit\pipeline_map\AVS-IMP-FIX-001\xml\`. Zero unexplained failures.
2. Run `check_run_gates.py 20260905_151448` and confirm it reproduces `AVS-TST-QT-001\B_20260905_151448.csv` exactly; then run it against a **replay** of the Lab/EOD stages over `151448`'s pinned inputs with W1.1–W1.6 applied (no provider calls; if a replay harness does not exist, say so and mark those items `AWAITING RUN`).
3. `git diff --check`; `py_compile` every changed module; plan-only dispatch with filesystem snapshot diff (must be empty); `build_macro_json.py --dry-run`.
4. Claim sheet `audit\pipeline_map\AVS-IMP-FIX-001\CLAIM_SHEET.md` + `.json`: per item — files changed, backup path, commit SHA, tests added, existing tests edited (with classification), **`run_artefact_evidence`** (replay artefact + filter + count, or `AWAITING RUN`), status from §0 rule 10.
5. Print at the end: Part A result (exit code, `models_status`, `sonnet_4_6_listed`); baseline tag and branch head; items by status; full-matrix totals incl. `tests\msi\`; the DEC-2 shadow-replay number; the W3.6 recommendation; any `BLOCKED` item with its reason; and the exact commands ACK runs next (`--evening` Monday, then `check_run_gates.py <run_id>`).

Do not merge `avs-fix-001` to main. That happens after the tester's pass and Monday's run.
