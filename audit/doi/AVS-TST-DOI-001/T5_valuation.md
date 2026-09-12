# AVS-TST-DOI-001 — Track T5: Option Valuation Verification

**Auditor role:** independent quantitative verifier
**Spec under test:** AVS-SD-DOI-001 v1.1 §11.4, §11.6, §9.4, §4 non-goal 5, invariants 8 and 9
**Date:** 2026-09-10
**Interpreter:** `venv\Scripts\python.exe` (CPython 3.13.14, scipy 1.17.0, pytest 9.1.1)

---

## 1. Objective

Verify, without trusting the implementation, that the DOI-5 deterministic option
valuation engine:

1. computes a dividend-adjusted Black–Scholes value that matches independently
   derived arithmetic, for CALL and PUT, across moneyness and tenor;
2. is side-correct and satisfies put–call parity and Greek symmetry (invariant 8);
3. discloses the American-exercise approximation and reduces applicability where
   it is material (§11.4);
4. persists every cell of the §11.4 scenario grid;
5. never labels a deterministic value as a probability (§11.6, non-goal 5);
6. converts trading sessions to calendar time through a real exchange calendar
   and never subtracts a session count from a calendar DTE (§9.4, invariant 9).

---

## 2. Method

**Order of work was enforced to prevent anchoring.** The audit's own
dividend-adjusted Black–Scholes (Merton 1973, continuous yield `q`, forward
priced as `S·e^{-qT}`) with delta, gamma, theta, vega and rho for both sides was
written and self-validated **before any engine file was opened**. Evidence of
ordering: `t5_reference_bs.py` and `test_t5_reference_selfcheck.py` were created,
run and passing (31 tests) before the first read of
`domain\deterministic_option_valuation.py`.

The reference was validated three independent ways before being used as truth:

| Check | Method | Result |
|---|---|---|
| Normal CDF/PDF | vs `scipy.stats.norm` at 9 abscissae | agree to < 1e-12 |
| All four Greeks | vs central finite differences of the audit's own price fn | delta/vega < 1e-6, theta < 1e-5, gamma < 1e-4 rel |
| Price | vs a 1200-step CRR European binomial | < $0.01 on all 8 fixtures |
| Parity | `C−P = S·e^{-qT} − K·e^{-rT}` on 3 pairs | < 1e-12 rel |

American values used for materiality sizing come from an independent 1500-step
CRR **American** binomial in the same file.

**Constraints honoured.** No pipeline entry point, orchestrator, macro build,
Lab server or provider-touching code was executed. No production source and no
existing test was modified. Nothing was committed, branched, stashed or reset.
All new files live under `audit\doi\AVS-TST-DOI-001\`. No API key value was
encountered or echoed.

### 2.1 Tolerance, stated up front

**`REL_PRICE = 1e-10` (relative).**

Justification: engine and reference evaluate the *same* closed form in IEEE754
double. The only implementation difference is the normal CDF formulation — the
engine uses `0.5·(1+erf(x/√2))` (`deterministic_option_valuation.py:165`), the
audit uses `0.5·erfc(−x/√2)`. Their disagreement is bounded by ~1e-16 absolute
in `N(·)`, amplified by the `S·e^{-qT} ≈ 1e2` coefficient, giving ~1e-14
absolute on prices of order 1e0–1e1, i.e. ~1e-13 relative. 1e-10 leaves three
orders of headroom against float noise while still catching any genuine formula
defect — a sign error, a missing discount factor, or `q` applied to the strike
instead of the spot — all of which move the price by ≥1e-3 relative.

Observed worst case across all 8 fixtures: **8.6e-14**. The tolerance was never
approached.

### 2.2 Fixtures

Eight fixtures, frozen in `t5_reference_bs.py` before engine inspection. The
brief required six spanning CALL/PUT, ITM/ATM/OTM, short/long DTE and one
deep-ITM PUT; two parity partners were added so `C−P` parity is testable on
identical parameters.

| ID | Side | Description | S | K | DTE (cal) | σ | q | r |
|---|---|---|---|---|---|---|---|---|
| T5-F1 | CALL | ATM, short | 100 | 100 | 30 | 0.28 | 0.00 | 0.045 |
| T5-F2 | CALL | OTM, short, div | 100 | 110 | 21 | 0.32 | 0.02 | 0.045 |
| T5-F3 | CALL | ITM, long, div | 120 | 100 | 365 | 0.25 | 0.03 | 0.045 |
| T5-F4 | PUT | ATM, short | 100 | 100 | 30 | 0.28 | 0.00 | 0.045 |
| T5-F5 | PUT | OTM, long, div | 100 | 85 | 180 | 0.30 | 0.02 | 0.045 |
| **T5-F6** | **PUT** | **DEEP-ITM — American case** | **60** | **100** | **270** | **0.22** | **0.00** | **0.05** |
| T5-F7 | PUT | parity partner of F3 | 120 | 100 | 365 | 0.25 | 0.03 | 0.045 |
| T5-F8 | CALL | parity partner of F6 | 60 | 100 | 270 | 0.22 | 0.00 | 0.05 |

---

## 3. Evidence — files, tests, commands

### New audit artefacts (all under `audit\doi\AVS-TST-DOI-001\`)

| Path | Contents |
|---|---|
| `tests\t5_reference_bs.py` | Independent Merton BS + Greeks, FD cross-checks, American/European CRR binomials, the 8 fixtures |
| `tests\test_t5_reference_selfcheck.py` | 31 tests validating the audit's own arithmetic |
| `tests\test_t5_engine_vs_reference.py` | 49 tests: engine vs reference, parity, American flag, grid, §11.6 |
| `tests\test_t5_session_calendar.py` | 32 tests: XNYS calendar, Thanksgiving + Christmas holiday fixtures |
| `tests\test_t5_prohibited_time_arithmetic.py` | 16 tests: the §9.4 prohibited arithmetic outside DOI-5 |
| `scratch\t5_reference_table.json` | Frozen reference price/Greek table for the 8 fixtures |

### Exact commands

```
venv\Scripts\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_reference_selfcheck.py       -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_engine_vs_reference.py       -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_session_calendar.py          -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_prohibited_time_arithmetic.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests/test_dynamic_options_deterministic_valuation.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests/test_avs_fix_001_w15_contract_dte.py            -q -p no:cacheprovider
```

Results: **31 + 49 + 32 + 16 = 128 audit tests pass.** Pre-existing suites
`test_dynamic_options_deterministic_valuation.py` (14 passed) and
`test_avs_fix_001_w15_contract_dte.py` (14 passed, 5 subtests) also pass
unmodified.

> Every defect probe asserts the **current (defective)** behaviour, so the suite
> is green today and will turn red when a defect is fixed. Each such test names
> its defect ID in the docstring and carries an assertion message saying
> "engine behaviour changed — defect may be fixed".

### Test count split (CALL / PUT / OTHER)

| Suite | CALL | PUT | OTHER | Total |
|---|---:|---:|---:|---:|
| `test_t5_reference_selfcheck` | 12 | 15 | 4 | 31 |
| `test_t5_engine_vs_reference` | 5 | 13 | 31 | 49 |
| `test_t5_session_calendar` | 0 | 0 | 32 | 32 |
| `test_t5_prohibited_time_arithmetic` | 0 | 0 | 16 | 16 |
| **Total** | **17** | **28** | **83** | **128** |

"OTHER" = tests exercising both sides simultaneously (parity, Greek symmetry,
normal-CDF precision) or side-agnostic calendar/time arithmetic. PUT outnumbers
CALL because the American-exercise investigation is put-dominated, which is
financially correct.

### Key source locations read

| File:line | What |
|---|---|
| `domain\deterministic_option_valuation.py:168-216` | `dividend_adjusted_black_scholes` — the price, and only the price |
| `domain\deterministic_option_valuation.py:208-209` | `d1`, `d2` |
| `domain\deterministic_option_valuation.py:216` | `return min(upper, max(lower, value))` — European-bound clamp |
| `domain\deterministic_option_valuation.py:219-231` | `assess_american_exercise_materiality` |
| `domain\deterministic_option_valuation.py:227` | `if side == "PUT" and ratio <= 0.80:` |
| `domain\deterministic_option_valuation.py:229` | `if side == "CALL" and ratio >= 1.20 and dividend_yield > 0 and ex_dividend_within_horizon:` |
| `domain\deterministic_option_valuation.py:318-319` | `seconds = …total_seconds()` ; `time_years = seconds / (365.0*24*60*60)` — **compliant** |
| `domain\deterministic_option_valuation.py:118, 128-135` | `ranking_score_uncalibrated`; `probabilities_calibrated` guard |
| `canonical_data\dynamic_options_valuation.py:148-172` | `build_xnys_scenario_points` — **compliant** session walk |
| `canonical_data\session_clock.py:76-93` | `xnys_holidays` — computed NYSE calendar |
| `contracts\selected_contract_economics.py:657` | `years = max(dte - hold_days, 0.0) / 365.0` — **prohibited** |
| `eod_candidate_engine.py:887` | `return float(xnys_sessions_between(session, expiry)), "AVAILABLE"` |
| `empirical_option_ev.py:242-243` | `remaining_days = max(dte - hold_days, 0.0)` ; `/ 365.0` |

---

## 4. Result per claim

Closure vocabulary: **VERIFIED** (source evidence AND a run artefact showing it
firing) / **VERIFIED OFFLINE** (tests + fixtures only, no run artefact) /
**REFUTED** / **PARTIAL** / **NOT TESTABLE** / **EXEC-BLOCKED**.

> **Ceiling declaration.** This track has **no real run artefact** for
> valuation. The pipeline was never executed (hard rule) and no persisted
> DOI-5 assessment from a live evening run was inspected. Every positive
> finding below is therefore capped at **VERIFIED OFFLINE**. Nothing here
> should be read as evidence that the code fired in production.

### Claim-by-claim

| # | Claim | State | Split (C/P/O) |
|---|---|---|---|
| 1 | Independent BS + Greeks written before engine read | VERIFIED OFFLINE | 12/15/4 |
| 2 | Engine public API and field names identified | VERIFIED OFFLINE | —/—/— |
| 3a | Engine **price** matches independent arithmetic | VERIFIED OFFLINE | 4/4/0 |
| 3b | Engine **Greeks** match independent arithmetic | **NOT TESTABLE** | 0/0/0 |
| 4 | Parity, delta difference, gamma/vega equality, theta signs | **PARTIAL** | 0/0/12 |
| 5 | Deep-ITM PUT flagged with reduced applicability | **PARTIAL** | 0/6/0 |
| 6 | §11.4 scenario grid fully persisted | **PARTIAL** | 4/1/1 |
| 7 | No deterministic value wearing a probability name | VERIFIED OFFLINE | 0/0/3 |
| 8 | Session/calendar conversion (§9.4, invariant 9) | **PARTIAL** | 0/0/48 |

---

### Claim 3a — price arithmetic — **VERIFIED OFFLINE**

Engine matches the audit's independent Merton BS on all 8 fixtures. Worst
relative error **8.6e-14**, against a stated tolerance of 1e-10.

```
T5-F1 call engine=  3.3836596978 ref=  3.3836596978 relerr=0.000e+00
T5-F2 call engine=  0.4297345341 ref=  0.4297345341 relerr=4.134e-15
T5-F3 call engine= 24.0700861220 ref= 24.0700861220 relerr=0.000e+00
T5-F4 put  engine=  3.0144798349 ref=  3.0144798349 relerr=0.000e+00
T5-F5 put  engine=  2.1716858365 ref=  2.1716858365 relerr=4.908e-15
T5-F6 put  engine= 36.3972884352 ref= 36.3972884352 relerr=0.000e+00
T5-F7 put  engine=  3.2163702795 ref=  3.2163702795 relerr=1.105e-15
T5-F8 call engine=  0.0283547870 ref=  0.0283547870 relerr=8.614e-14
```

Tests `T5-CMP-01` (8 params), `T5-CMP-02`. Split **CALL 4 / PUT 4 / OTHER 0**.
No discrepancy to report. The `§216` clamp was verified to be a strict no-op on
every fixture (`T5-CMP-22`): the price lies strictly inside `[lower, upper]`, so
the engine never silently substitutes a bound for a price.

**Confidence: HIGH.** *Raised by:* a persisted DOI-5 assessment row from a real
evening run reconciled against these same numbers.

### Claim 3b — Greeks — **NOT TESTABLE**

**Reason (mandatory): the engine has no Greek surface to compare against.**

`dividend_adjusted_black_scholes` returns a bare `float` price.
`grep -niE "\b(gamma|vega|theta|rho|greek)\b"` across both DOI-5 valuation files
returns **zero** matches other than the `d1`/`d2` intermediates used for the
price. `ScenarioValuation.__dataclass_fields__` contains `theoretical_value` and
no Greek. The `delta` at `canonical_data\dynamic_options_valuation.py:314` is
read off the provider quote row and stored as an observation attribute — it is
never computed, never recomputed under the scenario grid, and never reconciled
against the engine's own price.

Consequence: **delta is not revalued in any of the 18 grid cells.** The audit's
delta/gamma/theta/vega reference (built per the brief) has nothing to compare
against. Recorded as defect **T5-D7**. Test `T5-CMP-10` documents the gap and
will fail if a Greek is ever added, prompting a re-run of this claim.

**Confidence: HIGH** (that the gap exists). *Raised by:* nothing — this is a
direct structural observation.

### Claim 4 — parity and symmetry (invariant 8) — **PARTIAL**

Verified on the engine's own outputs (`T5-CMP-20`, `T5-CMP-21`, 4 parameter sets
each, plus 3 reference pairs in the self-check):

- **Put–call parity** `C − P = S·e^{-qT} − K·e^{-rT}`: holds to < 1e-10 relative
  on all 4 engine cases, including the deep-ITM pair. ✅
- **Side-correct formulas**: CALL uses `S·e^{-qT}N(d₁) − K·e^{-rT}N(d₂)`, PUT
  uses `K·e^{-rT}N(−d₂) − S·e^{-qT}N(−d₁)`; both match the reference to 1e-13. ✅
- **Monotonicity**: calls rise in S, puts fall in S. ✅
- **Validation symmetry**: CALL requires `target > invalidation`, PUT requires
  `target < invalidation`; both enforced. ✅
- **Clamp symmetry**: both sides clamp to their correct European bounds. ✅

**Why PARTIAL, not VERIFIED OFFLINE:** three of the six symmetry properties the
brief names — `delta_call − delta_put = e^{-qT}`, `gamma_call = gamma_put`,
`vega_call = vega_put` — and all theta-sign checks are **unverifiable against the
engine**, because the engine computes no Greeks (claim 3b). They were verified
on the audit's own reference only (`test_selfcheck_put_call_parity`,
`test_selfcheck_delta_bounds_and_signs`), which proves the audit's maths, not the
engine's.

A second, substantive invariant-8 gap: the CALL-side American-exercise predicate
requires `ex_dividend_within_horizon=True`, and **no production caller ever
passes it** (`canonical_data\dynamic_options_production.py:228-236` passes only
`generated_family`, `observation`, `contract_symbols`). In production, PUTs get
an American flag (imperfect — see claim 5) and CALLs get **none at all**.
Governance coverage is therefore *not* equivalent in practice. Defect **T5-D9**.

**Confidence: MEDIUM.** *Raised by:* the engine exposing Greeks so the three
Greek-symmetry identities can be tested against it, plus a production row showing
the CALL-side flag path reachable.

### Claim 5 — American-exercise disclosure (§11.4) — **PARTIAL**

**The required mechanism exists and fires correctly for the brief's fixture.**
For the deep-ITM PUT (T5-F6, S/K = 0.60), through the full scenario engine
(`T5-CMP-40`):

- `american_exercise_material = True`
- `american_exercise_reason = "SUFFICIENTLY_ITM_PUT_EARLY_EXERCISE_NOT_MODELLED"`
- `applicability_state = OUT_OF_DISTRIBUTION` (reduced, as §11.4 demands)
- disclosures include `EUROPEAN_BLACK_SCHOLES_AMERICAN_EXERCISE_NOT_MODELLED`
  and `CONTINUOUS_DIVIDEND_YIELD_ASSUMPTION`

Every row also carries `valuation_model = "DIVIDEND_ADJUSTED_EUROPEAN_BS_V1"`, so
the approximation is disclosed per-row as §11.4 requires. ✅

**But the predicate that decides materiality is structurally wrong** — defect
**T5-D1**. Its signature is:

```
(option_side, spot, strike, dividend_yield, ex_dividend_within_horizon)
```

It has **no `time_to_expiry_years`, no `risk_free_rate`, no `volatility`**
(`T5-CMP-42`). Early-exercise value on a put is governed precisely by `r·T`
against remaining insurance value, so a moneyness-only test cannot assess it.
Measured against the audit's 1500-step American CRR binomial:

**False negatives — materially mispriced, NOT flagged, applicability stays
`DETERMINISTIC_ONLY` (full confidence):**

| Case | S/K | r | T | Flagged | European | American | Understated by |
|---|---|---|---|---|---|---|---|
| deep-ITM 270d | 0.85 | 5% | 0.740y | ❌ False | 13.9644 | 15.4031 | **10.30%** |
| ITM 2y | 0.95 | 5% | 2.000y | ❌ False | 9.3459 | 10.8702 | **16.31%** |
| **ATM 1y r=8%** | **1.00** | **8%** | **1.000y** | ❌ **False** | **4.4175** | **5.2739** | **19.39%** |

**False positives — 0.00% error, flagged, needlessly downgraded to
`OUT_OF_DISTRIBUTION`:**

| Case | S/K | r | T | Flagged | Understated by |
|---|---|---|---|---|---|
| deep-ITM 14d r=0 | 0.75 | 0% | 0.038y | ✅ True | 0.000% |
| deep-ITM 30d r=0 | 0.78 | 0% | 0.082y | ✅ True | 0.000% |

**A related and sharper consequence — defect T5-D2.** At S/K = 0.85, which the
engine does **not** flag, the engine's own European price is **below intrinsic**:

```
engine=13.9644  intrinsic=15.0000  euro_lower_bound=11.3689  flagged=False
```

The engine returns a contract value a holder can beat *today* by exercising. The
`§216` clamp does not catch this because it clamps to the **European** lower
bound `K·e^{-rT} − S·e^{-qT}` (11.3689), not to intrinsic `K − S` (15.00). The
flagged fixture T5-F6 shows the same shape more starkly — engine 36.3973 vs
intrinsic 40.0000, a **$3.60 (9.01% of intrinsic)** shortfall — but there at
least the row is flagged.

Full sweep at K=100, T=0.740y, r=5%, σ=0.22 (`scratch` sweep, reproducible from
`t5_reference_bs.py`): the American premium exceeds 2% across the **entire**
range S/K ∈ [0.60, 1.30], from 13.3% at 0.75 down to 3.2% at 1.30. The 0.80
threshold captures only the extreme tail of a problem that is material
everywhere at this rate and tenor.

**Confidence: HIGH.** *Raised by:* nothing needed for the finding itself; a
production row showing an unflagged S/K≈0.85 put carrying
`applicability_state=DETERMINISTIC_ONLY` would upgrade this to VERIFIED.

### Claim 6 — scenario grid completeness (§11.4) — **PARTIAL**

The fixed 2 × 3 × 3 grid is complete and correctly persisted (`T5-CMP-50` …
`T5-CMP-52`): all 18 `scenario_id`s present and exactly equal to the Cartesian
product; `path ∈ {FAVOURABLE_TARGET, ADVERSE_INVALIDATION}`;
`timing ∈ {EARLY, MID, LATE}`; `iv_stress ∈ {CONTRACTED, BASE, EXPANDED}` with
multipliers exactly 0.80 / 1.00 / 1.20 of base IV.

Grid cell coverage against the §11.4 enumeration:

| §11.4 cell | Present? | Where |
|---|---|---|
| early / mid / late favourable | ✅ | `ScenarioTiming` × `FAVOURABLE_TARGET`, 9 cells |
| invalidation / adverse | ✅ | `ADVERSE_INVALIDATION`, 9 cells |
| base / contracted / expanded IV | ✅ | `IVStress`, ×3 |
| entry friction | ✅ | `entry_cost_after_friction` > `entry_reference` on every row |
| exit friction | ✅ | `exit_value_after_friction` < `theoretical_value` on every row |
| dividends | ✅ | `dividend_yield` in service metadata; priced via `S·e^{-qT}` |
| corporate-action flag | ✅ recoverable | `CORPORATE_ACTION_MODEL_APPLICABILITY_REDUCED` disclosure + `OUT_OF_DISTRIBUTION` |
| **ex-dividend window** | ❌ **not recoverable** | see below |

**Missing cell — defect T5-D8.** `ex_dividend_within_horizon` is an input the
grid claims to cover, but for every case except an ITM dividend-paying CALL,
toggling it produces a **byte-identical** persisted assessment (`T5-CMP-54`
asserts `on == off` for a PUT). It reaches the output only through the
`§229` CALL branch (`T5-CMP-55`). Elsewhere it is bound into the
`_calculation_version` SHA-256 fingerprint
(`canonical_data\dynamic_options_valuation.py:240`) and is otherwise
unreadable — an auditor cannot tell whether an ex-dividend window was declared
without brute-forcing a 12-hex hash.

Compounding this: **no production caller ever sets the flag** (defect T5-D9), so
in practice the ex-dividend cell of the grid is inert.

Two further grid-integrity gaps found:

- **T5-D10 (`T5-CMP-70`)**: a scenario point falling **after expiry** is clamped
  to `T = 0` at `§318` and valued at intrinsic, with **no disclosure** that the
  scenario is unreachable. A LATE cell 40 days past a 7-day expiry silently
  reports `theoretical_value = 15.0` (intrinsic) alongside genuinely-modelled
  cells, indistinguishable in the persisted row except by recomputing the dates.
- **T5-D11 (`T5-CMP-71`)**: `§268` validates only that the *set* of timings is
  `{EARLY, MID, LATE}`, never that `sessions_elapsed` is increasing. Points
  labelled EARLY=10, MID=5, LATE=1 are accepted, producing a LATE cell with
  *more* time to expiry than the EARLY cell.

**Confidence: MEDIUM-HIGH.** *Raised by:* a persisted assessment JSON from a
real run confirming the 18 rows and the absent ex-div field in production shape.

### Claim 7 — no probability mislabelling (§11.6, non-goal 5) — **VERIFIED OFFLINE**

**No P0 defect. The DOI-5 valuation path is clean.** This was the highest-risk
claim and it survives scrutiny.

Every field name in the DOI-5 valuation path matching
`prob|probability|p_|likelihood|confidence|odds|chance|expected_value|ev_` was
enumerated and classified:

| file:line | Field | Classification |
|---|---|---|
| `domain\deterministic_option_valuation.py:118` | `ranking_score_uncalibrated` | ✅ **Exactly the §11.6 mandated name.** Value = `median(9 favourable net returns) + min(9 adverse net returns)` (`:365-367`), an unweighted sum of two order statistics over closed-form BS outputs. Formula published alongside as `utility_formula` (`:387`). |
| `…:128` | `probabilities_calibrated: bool = False` | ✅ Explicit **negation**, not a probability. `__post_init__` (`:131-133`) **raises** if set True. |
| `…:277`, `:289` | `"NO_PROBABILITY_OUTPUT"` | ✅ Disclosure literal (a negation). |
| `…:371` | `"RANKING_SCORE_UNCALIBRATED_NOT_PROBABILITY"` | ✅ Disclosure literal (a negation). |
| `canonical_data\dynamic_options_valuation.py:360` | `"utility_is_probability": False` | ✅ Explicit negation. |
| `…:361` | `"probability_outputs_withheld": True` | ✅ Explicit negation. |
| `…:359` | `"scenario_weighting": "NONE"` | ✅ Declares the score is unweighted. |
| `…:381` | `probabilities_calibrated=False` | ✅ Hardcoded false on every DOI-5 write. |
| `domain\dynamic_options_intelligence.py:403-408` | `p_liquidity_1d/2d/3d`, `p_positive_return_before_horizon`, `p_return_hurdle_before_horizon`, `p_target_before_invalidation` | ✅ **Never populated by DOI-5** — the only kwargs passed at `:380-382` are `ranking_score_uncalibrated`, `probabilities_calibrated=False`, `metadata`. Guarded at `:453-454`: setting any of them without `probabilities_calibrated=True` **raises**. |
| `…:409-411` | `expected_net_return`, `expected_downside`, `expected_time_to_monetisation` | ✅ Same — `None` on the DOI-5 path. |
| `canonical_data\option_liquidity_lifecycle.py:472-483` | matching SQL columns | ✅ Schema slots; `CHECK(probabilities_calibrated IN (0,1))`. |
| `…:243-247` vs `:250-255` | `_probability()` [0,1] vs `_deterministic_score()` [0,100] | ✅ Two **separate validators**; the latter's docstring: *"Validate the lifecycle prioritisation scale without calling it probability."* |
| `…:366-367` | `maturation_score_is_probability INTEGER NOT NULL DEFAULT 0 CHECK(… = 0)` | ✅ **Schema-level constraint** making it impossible to mark the heuristic a probability. Backing value is a hand-tuned weighted heuristic (`domain\option_contract_liquidity.py:576-583, 638, 658`) — correctly **not** probability-named. |
| `canonical_data\dynamic_options_probability.py:469-471` | `raw_probability`, `probability` | ✅ **Genuinely calibrated DOI-8**: fitted logistic regression (`:468`) then Platt scaling (`:470`). Withheld (`None`) unless the model is ACCEPTED and in-distribution (`:446, :454, :477`). |
| `…:116` | `"deterministic_score": assessment.ranking_score_uncalibrated` | ✅ The DOI-5 utility enters DOI-8 **as a named feature**, not as a probability. |

Tokens `likelihood`, `odds`, `chance`, `confidence`, `expected_value` have **zero
hits** in the DOI-5 path (`model_uncertainty` is the term used instead).

Programmatic assertions (`T5-CMP-60`, `T5-CMP-61`, `T5-CMP-62`): no key in the
persisted `to_dict()` — top level or per-scenario row — contains a banned token
except the explicit negation `probabilities_calibrated`; constructing the
dataclass with `probabilities_calibrated=True` raises; and the published score
equals exactly `median(favourable) + min(adverse)` to 1e-12, i.e. nothing hidden
behind the name.

**One MEDIUM observation, not a §11.6 breach — T5-D12.**
`domain\dynamic_options_ranking.py:173-182` defines `calibrated_utility`, a
**weighted sum** mixing `deterministic_score` with three calibrated
probabilities, labelled `"CALIBRATED_POLICY_UTILITY"` (`:398`). It is gated on
all three calibrated probabilities being present plus `len(probability_model_ids)
>= 3` (`:163-171`), and weights are constrained non-negative and summing to one
(`:110-113`). It is *not* labelled a probability, so §11.6's letter is met. But
"CALIBRATED" describes the *inputs*; the **weights themselves are not
calibrated**. A reader may reasonably infer more warrant than exists. Naming it
`policy_utility_uncalibrated_weights` would remove the ambiguity.

Lab surface checked: `intelligence-lab\static\index.html:2699-2704` renders the
DOI-8 `doi_p_*` fields as percentages — legitimate, they are calibrated. The
uncalibrated score reaches the Lab only as an untyped `x.score` tagged with
`score_kind` = `"RANKING_SCORE_UNCALIBRATED"` (`:2709`) — correctly labelled.

**Confidence: HIGH.** *Raised by:* nothing material; the negations are enforced
by constructor guards and SQL CHECK constraints, which is stronger than naming
convention alone.

### Claim 8 — session/calendar conversion (§9.4, invariant 9) — **PARTIAL**

**The DOI-5 path is fully compliant — and is the only compliant path in the repo.**

**Conversion code located:** `canonical_data\session_clock.py` (the calendar),
`canonical_data\dynamic_options_valuation.py:148-172`
(`build_xnys_scenario_points`), `domain\deterministic_option_valuation.py:318-319`
(the calendar clock).

**It walks a real exchange calendar, not an approximation constant.**
`xnys_holidays` (`session_clock.py:76-93`) *computes* the NYSE holiday set from
nine rules: `_nth_weekday` / `_last_weekday` for the Monday holidays,
`_observed()` (Sat→Fri, Sun→Mon) for the fixed-date ones, an inline Anonymous
Gregorian Easter algorithm for **Good Friday**, and Juneteenth gated on
`year >= 2022`. Verified exactly for 2026 (`T5-CAL-01`) — including the two an
approximation always gets wrong: **Good Friday 2026-04-03** (Easter-derived) and
**2026-07-03**, Independence Day observed because July 4 falls on a Saturday.
`T5-CAL-03` statically asserts no `1.4`, `0.714`, `1.4286`, `7/5`, `5/7`,
`252/365` or `365/252` constant appears in `session_clock.py`.

**Existing unit tests exist and pass:**
`tests\test_dynamic_options_deterministic_valuation.py` —
`test_calendar_points_skip_weekend_and_are_session_closes` (`:156`),
`test_grid_is_18_and_timing_exposes_theta` (`:85`) — **14 passed**.
`tests\test_avs_fix_001_w15_contract_dte.py` —
`test_counts_sessions_not_calendar_days` (`:26`),
`test_a_long_weekend_is_not_three_days_of_life` (`:33`) — **14 passed, 5 subtests**.
Neither was modified.

**Extension: the holiday fixture the brief requested** (`T5-CAL-10`…`T5-CAL-13`).
Planned hold of **10 trading sessions from Friday 2026-11-20, spanning US
Thanksgiving (Thu 2026-11-26)**:

```
1 Mon Nov 23   2 Tue Nov 24   3 Wed Nov 25
  (Thu Nov 26 THANKSGIVING — skipped)
4 Fri Nov 27   5 Mon Nov 30   6 Tue Dec 01   7 Wed Dec 02
8 Thu Dec 03   9 Fri Dec 04  10 Mon Dec 07
→ 10 sessions span 17 CALENDAR days
```

Assertions that pass: `calendar_span != 10` (invariant 9), `calendar_span == 17`,
`xnys_sessions_between(Nov 20, Dec 7) == 10`, no scenario instant lands on
2026-11-26 or any non-session, and every instant equals an exact
`session_bounds(...)[1]` UTC close. A second fixture (`T5-CAL-12`) crosses both
**Christmas 2026-12-25** and **New Year 2027-01-01**. `T5-CAL-32` sweeps all
holds 1…20 for monotonicity.

**The prohibited computation is demonstrably absent from DOI-5** (`T5-CAL-20`).
Running the real scenario engine on the Thanksgiving fixture with a 2027-01-15
expiry:

```
exact=0.10958904y  prohibited=0.12876712y  gap=7.0000 calendar days
```

The LATE cell's `time_to_expiry_years` equals the exact-timestamp calendar
remainder to 1e-12 and differs from `(dte − planned_hold_sessions)/365` by
exactly the 7-day weekend-plus-holiday gap. `T5-CAL-21` statically asserts no
`dte - *hold` / `dte - *session` pattern in either DOI-5 file or in
`session_clock.py`.

---

**Why PARTIAL: a second option-valuation path performs the prohibited
computation verbatim and ships it to the desk.**

`contracts\selected_contract_economics.py:657`:

```python
years = max(dte - hold_days, 0.0) / 365.0
```

with operands resolved at `:648` and `:651-653`:

```python
dte = _first_present((row, "contract_dte"), (row, "dte"), (hydrated, "dte"))
hold_days = _first_present(
    (row, "planned_hold_sessions"), (row, "hold_days"), (row, "hold_sessions")
)
```

Both resolve a **session-typed** field first, and `contract_dte` is produced by
`eod_candidate_engine.py:887` as `float(xnys_sessions_between(session, expiry))`
— a pure trading-session count. This is defect **T5-D3 (P0)**, three compounding
errors on one line:

1. A **session** count is subtracted from a field that is a session count when
   `contract_dte` is present but a **calendar** count when it falls back to
   `dte` — the expression silently switches units row by row.
2. The session remainder is divided by **365.0**, treating sessions as calendar
   days. Sessions per year is 252; the ratio 252/365 = 0.690 understates `T` by
   31% before any calendar effect (`T5-TIME-13`).
3. The assumption is *published as correct* on every row —
   `selected_contract_economics.py:64`: `"T=max(dte-hold_days,0)/365; European exercise; "`.

**Measured impact** (`T5-TIME-10`, `T5-TIME-11`, `T5-TIME-12`), ATM S=K=100,
σ=0.30, r=4.5%, 30 sessions to expiry, 10-session hold over Thanksgiving:

```
engine T = (30-10)/365 = 0.054795y -> value 2.9224
true   T = calendar span = 0.082192y -> value 3.6116
understatement = 19.08% of contract value
```

Across four windows (Thanksgiving, Christmas/New Year, quiet March, short hold)
the year fraction is understated by **≥25%** and the option value at target by
**>10%**, on **both** CALL and PUT — the defect is side-symmetric, so it does not
breach invariant 8, but it breaches invariant 9 and §9.4 directly. The output
gates `monetisability_state_timevalue`, so the bias is toward false
`NOT_MONETISABLE` verdicts on contracts that are in fact monetisable.

Related, same class:

- **T5-D4 (P1)** `empirical_option_ev.py:242-243` repeats the pattern
  (`remaining_days = max(dte - hold_days, 0.0)`; `/365.0`) with
  `dte = g("dte", "contract_dte")`.
- **T5-D5 (P2)** `domain\option_contract_liquidity.py:196-226`
  `calculate_dte_requirement` maps sessions to calendar 1:1. Its own docstring
  states the violation — *"DTE is calendar time whereas the inputs are
  trading-session allowances… the integration layer may apply a larger
  calendar-day conversion if desired"* — and no such integration layer exists.
  Measured (`T5-TIME-20`): `minimum_required_dte = 18` sessions is compared raw
  against a calendar DTE, but 18 sessions actually span **27 calendar days**, so
  the floor is short by **9 days**.
- **T5-D6 (P2)** `layer3_forward_variance.py:167-180` uses an explicit
  `trading_frac = days * (5 / 7)` weekday-ratio constant, holiday-blind, whose
  docstring pre-blesses it as *"expected output behavior, not drift"*. Measured
  (`T5-TIME-21`): over the Thanksgiving window it yields 12.143 sessions where
  the real XNYS count is 10 — a 21% overstatement. Per the brief, an
  approximation constant is a TIME-class defect even when conservative.
- **T5-D14 (P2)** Existing tests **lock the defect in**.
  `tests\test_avs_fix_001_w34_timevalue_monetisability.py:142`
  `test_zero_time_remaining_reduces_to_intrinsic` asserts `dte=5, hold=5` →
  `years_to_expiry == 0.0`, which is true *only* under the prohibited
  subtraction. Also `:153` (`dte=3, hold=10`) and
  `tests\test_empirical_option_ev.py:89-90` whose comment reads
  `# hold_days == dte -> remaining_days = 0`. Any correct fix breaks these tests.
- **T5-D13 (P3)** `audit\preflight\marketdata_candle_preflight.py:103` carries a
  second, hand-copied XNYS holiday implementation — *"re-implemented, mirrors
  canonical_data/session_clock.py"* — a drift-prone duplicate source of truth.

**Confidence: HIGH** for the DOI-5 compliance and for the existence and
magnitude of T5-D3/D4. *Raised by:* an evening-run artefact showing a
`monetisability_timevalue_years_to_expiry` value on a real row reconciled
against its contract's true calendar span — that would move T5-D3 from
VERIFIED OFFLINE to VERIFIED.

---

## 5. Defects raised

| ID | Class | Sev | Summary | Side | Evidence |
|---|---|---|---|---|---|
| **T5-D3** | **TIME** | **P0** | `selected_contract_economics.py:657` computes `max(dte − hold_days,0)/365` with both operands session-typed; session remainder ÷365. **19.08% understatement** of ATM contract value; gates `monetisability_state_timevalue`. | both | `T5-TIME-01/02/10/11/12` |
| **T5-D1** | LIN | P1 | `assess_american_exercise_materiality` signature omits `r`, `T`, `σ` — structurally cannot assess early exercise. False negatives to **19.39%** (ATM 1y r=8%, unflagged, `DETERMINISTIC_ONLY`); false positives at 0.00%. | PUT (CALL inert, see D9) | `T5-CMP-42/42a/42b` |
| **T5-D2** | LIN | P1 | Engine returns a **price below intrinsic** for unflagged deep-ITM puts (S/K=0.85: 13.9644 vs 15.00). `§216` clamps to the European lower bound, not intrinsic. | PUT | `T5-CMP-42c/43` |
| **T5-D4** | TIME | P1 | `empirical_option_ev.py:242-243` repeats the prohibited subtraction with `contract_dte` as an accepted alias. | both | `T5-TIME-03` |
| **T5-D7** | DEL | P2 | **No Greeks computed anywhere** in the DOI-5 path. Provider `delta` is stored but never revalued in any of the 18 grid cells. | both | `T5-CMP-10` |
| **T5-D9** | DEL | P2 | `ex_dividend_within_horizon` / `corporate_action_flag` are **never passed by any production caller** (`dynamic_options_production.py:228-236`). CALL-side American governance and corporate-action downgrade are dead code in production — an invariant-8 coverage asymmetry. | CALL | source + grep |
| **T5-D5** | TIME | P2 | `calculate_dte_requirement` maps sessions→calendar 1:1; docstring admits it. Floor short by **9 calendar days** at hold=10. | OTHER | `T5-TIME-20` |
| **T5-D6** | TIME | P2 | `layer3_forward_variance.py:167-180` `days*(5/7)` approximation constant, holiday-blind, self-blessed. 12.143 vs real 10 sessions. | OTHER | `T5-TIME-21` |
| **T5-D10** | NULL | P2 | Scenario point past expiry silently clamped to `T=0` and valued at intrinsic with **no disclosure**; indistinguishable from a modelled cell. | both | `T5-CMP-70` |
| **T5-D14** | TEST | P2 | Existing tests assert the prohibited arithmetic's results (`dte=5,hold=5 → T=0`), locking the defect in; any correct fix breaks them. | both | `test_avs_fix_001_w34…:142,153`; `test_empirical_option_ev.py:89` |
| **T5-D8** | PERSIST | P3 | `ex_dividend_within_horizon` leaves **no trace** in the persisted assessment except for ITM dividend CALLs; only bound into a 12-hex version hash. §11.4 names it as a grid cell. | PUT + non-ITM CALL | `T5-CMP-54/55` |
| **T5-D11** | LIN | P3 | `§268` validates the timing *set* but never that `sessions_elapsed` increases; EARLY=10/MID=5/LATE=1 accepted. | both | `T5-CMP-71` |
| **T5-D12** | DOC | P3 | `dynamic_options_ranking.py:173-182` `calibrated_utility` labelled `CALIBRATED_POLICY_UTILITY`; inputs are calibrated but the **weights are not**. Not a §11.6 breach; naming invites over-reading. | OTHER | source |
| **T5-D13** | DOC | P3 | Duplicate hand-copied XNYS holiday table in `audit\preflight\marketdata_candle_preflight.py:103`; drift risk against `session_clock.py`. | OTHER | source |

**Count by class:** TIME 4 · LIN 3 · DEL 2 · DOC 2 · NULL 1 · PERSIST 1 · TEST 1.
**By severity:** P0 1 · P1 3 · P2 6 · P3 4.
**By side:** CALL-specific 1 · PUT-specific 3 · both/OTHER 10.

**No PROB-class defect was found.** Claim 7 passed cleanly — see §4 claim 7.

---

## 6. Headline numbers

| Quantity | Value |
|---|---|
| Engine vs independent BS price, worst relative error (8 fixtures) | **8.6e-14** (tolerance 1e-10) |
| Put–call parity on engine outputs, worst relative error | **< 1e-10** |
| **T5-D3** ATM contract value understatement (30 sessions, 10-session hold, Thanksgiving) | **19.08%** |
| **T5-D3** year-fraction understatement, worst of 4 windows | **≥ 25%** |
| **T5-D3** dimensional error from ÷365 on a session count alone | factor **0.690** (252/365) |
| **T5-D1** worst unflagged American understatement (ATM, 1y, r=8%) | **19.39%** (4.4175 vs 5.2739) |
| **T5-D1** unflagged deep-ITM put, S/K=0.85 | **10.30%** (13.9644 vs 15.4031) |
| **T5-D2** flagged deep-ITM put T5-F6 below intrinsic | **$3.60 = 9.01%** of intrinsic (36.3973 vs 40.00) |
| **T5-D5** DTE floor shortfall at hold=10 | **9 calendar days** (18 sessions = 27 days) |
| **T5-D6** 5/7 constant over Thanksgiving window | **12.143** vs real **10** sessions (+21%) |
| Sessions vs calendar, Thanksgiving fixture | 10 sessions = **17 calendar days** (gap 7) |
| Audit tests written / passing | **128 / 128** |

---

## 7. Confidence summary

| Finding | Confidence | What would raise it |
|---|---|---|
| Price arithmetic correct (claim 3a) | HIGH | A persisted DOI-5 row from a real evening run reconciled against these numbers |
| Greeks absent (claim 3b, T5-D7) | HIGH | — structural observation, nothing needed |
| Parity/side-correctness (claim 4) | MEDIUM | Engine exposing Greeks so the 3 Greek-symmetry identities become testable against it |
| American flag mechanism fires (claim 5, positive half) | HIGH | A production row showing `OUT_OF_DISTRIBUTION` on a deep-ITM put |
| T5-D1 predicate structurally wrong | HIGH | A production row with an unflagged S/K≈0.85 put at `DETERMINISTIC_ONLY` |
| T5-D2 price below intrinsic | HIGH | — arithmetic is closed-form and reproducible |
| Grid completeness (claim 6) | MEDIUM-HIGH | A persisted assessment JSON from a real run |
| T5-D8 ex-div not recoverable | MEDIUM-HIGH | Confirming against a production row's stored metadata shape |
| No probability mislabelling (claim 7) | HIGH | — guarded by constructor raises and SQL CHECK constraints |
| DOI-5 calendar compliance (claim 8, positive half) | HIGH | An evening-run artefact showing scenario instants at real session closes |
| T5-D3 / T5-D4 prohibited arithmetic | HIGH | A real row's `monetisability_timevalue_years_to_expiry` reconciled against its true calendar span → would upgrade to VERIFIED |
| T5-D9 flags never armed in production | MEDIUM-HIGH | Tracing every call site in a real evening run's stack |

---

## 8. Scope and honesty statement

- **No run artefact exists for valuation in this track.** The pipeline was never
  executed. Every positive claim is capped at **VERIFIED OFFLINE**; no claim in
  this document reaches **VERIFIED**.
- The audit's reference arithmetic was written before the engine was read, and
  self-validated against scipy, finite differences and a binomial lattice
  before being used as ground truth. One self-check threshold (the ATM American
  premium control) was initially set too tight at 0.5% and failed at the true
  0.816%; **the audit's threshold was widened, the arithmetic was not changed**,
  and the adjustment is recorded in the test's docstring.
- Two test-authoring bugs of the auditor's own (a wrapped-line index and a
  rounding constant) were found and fixed during the run; neither affected a
  finding.
- Defect probes assert *current* behaviour so the suite is green today; each
  names its defect ID and will fail loudly when the defect is fixed.
- No production source and no existing test was modified. No commit, branch,
  stash or reset was performed. No API key value was encountered.
