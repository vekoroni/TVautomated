# 04 — Defect register (AVS-TST-DOI-001)

**Severity rubric, applied literally as the prompt defines it.**

> P0 = any automated layer **can** delete, hide, permanently invalidate or close
> a governed opportunity, grant capital, or change direction; any deterministic
> value labelled as a probability; any null coerced to economic zero on a path
> that reaches the Lab; any credential exposure.

"Can" is capability, not occurrence. One defect meets it.

**Classes:** `AUTH` authority leakage · `DEL` row deletion · `NULL` null-as-zero
· `PROB` mislabelled probability · `TIME` session/calendar · `LIN` lineage ·
`PERSIST` append-only · `SYM` CALL/PUT asymmetry · `TEST` weak/misnamed test ·
`DOC` claim-sheet inaccuracy · `SEC` credential · `EXEC-BLOCKED`.

**Totals, DOI scope: 1 P0 · 8 P1 · 22 P2 · 17 P3 = 48 defects.**
**No `PROB` defect in DOI. No `SEC` defect. No `EXEC-BLOCKED` outcome.**

**Plus 3 pre-existing `PROB` defects on the Lab surface, 2 of them P0 by the
letter of the rubric, filed in the addendum below as DOI-D49 to DOI-D51.** They
are not DOI-introduced and are excluded from the DOI counts above and from the
verdict's P0 count. Grand total 51.

Three-direction impact is given per defect. `n/a` means the defect is
structural and side-independent.

---

## P0

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf | What would close it |
|---|---|---|---|---|---|---|---|
| **DOI-D27** | DOI-10 | **AUTH** | **P0** | `domain/dynamic_options_projection.py:117–122`. `merge_all_opportunities` reconciles only `run_id, ticker, thesis_id, trade_idea_id`, and the check is `if left and right and left != right` — it **skips whenever either side is blank**. It then performs a bare `base.update(row)`, which overwrites **every** key the actionable row carries, including `governed_direction`, `final_action`, size and capital fields. The repo's own `PROTECTED_AUTHORITY_FIELDS` / `OVERLAY_ALLOWED_FIELDS` guards exist at `contracts/lab_evidence_overlay.py:51–55` and are applied at `:98–99` and `:189` for the *other* overlay path, but are not used here. Live path: called from `intelligence-lab/intelligence_lab.py:309`. Independently reproduced: a PUT actionable row flips a CALL governed row and the reconciliation still returns `status: PASS`. | all 3 (any row can be targeted) | HIGH | Apply `PROTECTED_AUTHORITY_FIELDS` to the merge, and make the identity check fail closed on a blank on either side. Closed by source evidence plus one evening artefact showing `governed_direction` byte-identical before and after projection for all rows. |

Population is **not** reduced by this defect — `merge_all_opportunities` only
updates rows that already exist and asserts `population_preserved`. The
violation is invariant 1 (direction), not the non-discard principle.

---

## P1

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf | What would close it |
|---|---|---|---|---|---|---|---|
| DOI-D01 | all | LIN | P1 | Not one line of DOI is committed. `git ls-files` matches no DOI or `dynamic_options` path outside `backups/`, `_attic/`, `_cleanup_holding/`. 103 untracked non-audit files; HEAD `00baa2b`, branch `avs-fix-001`, porcelain 306. Recurrence of QT-D02. | n/a | HIGH | Commit the DOI tree and tag it; then a run artefact can name the commit that produced it. |
| DOI-D04 | DOI-1 | AUTH | P1 | `position_sizing_engine.py:380–390` turns the EIL verdict into a size multiplier; `:661–671` turns `FATAL_EIL_BINDING_LIQUIDITY` into `pse_final_size = 0.0` / `FATAL_BLOCK`. DOI-1 step 3 required EIL be removed from capital fields. Currently unreachable because production forces `eil_advisory_only = True` (`execution_intelligence_runner.py:1345, :1814`; schema default `execution_schema.py:193`) — **but** `trade_book_builder.py:301` reads the same flag with the opposite default (`_b(row, "eil_advisory_only", False)`). A dropped column re-arms EIL as a gate in one module and not the other. | all 3 | HIGH | Remove the EIL term from the sizing chain, or make the default `True` everywhere. Closed by source evidence plus a run artefact showing `pse_eil_mult` absent or 1.0. |
| DOI-D15 | pre-existing | TIME | P1 | `contracts/selected_contract_economics.py:657`: `years = max(dte - hold_days, 0.0) / 365.0`, where `hold_days` is sourced first from `planned_hold_sessions` (a session count) and `dte` is session-typed. The exact operation §9.4 prohibits, plus a session/calendar unit mix. Measured effect: **19.08%** understatement of ATM contract value at 30 sessions to expiry with a 10-session hold over Thanksgiving (2.9224 vs 3.6116). Gates `monetisability_state_timevalue`. | all 3 | HIGH | Walk the exchange calendar. Note this file is **tracked and unmodified** — pre-existing, not introduced by DOI. |
| DOI-D28 | DOI-10 | LIN | P1 | 11 of 235 Lab rows (CALL 7 / PUT 4) display a "Governed Contract" whose OCC strike and/or expiry contradicts the row's own trade idea — e.g. ANET symbol strike 200 / expiry 09-25 against row values 195.0 / 09-18. 24 further rows (CALL 15 / PUT 9) show none at all. A contract roll updated `selected_contract_symbol` and left `strike`/`expiry`/`trade_idea_id` stale; DOI-10 takes the symbol and discards the conflict silently. All **4 accepted actionable rows** are affected. | 7 / 4 / 0 | HIGH | Reconcile symbol against strike/expiry at projection time and surface a mismatch state. Closed by an evening artefact with zero mismatches. |
| DOI-D29 | DOI-10 | AUTH | P1 | The rendered Lab still asserts thesis authority. `intelligence-lab/static/index.html:2737` renders `Advisory Only  NO` whenever `eil__advisory_only` is not the literal string `'True'`/`'true'` (`:2715`) — so a missing field reads as "EIL is authoritative". `:2116` maps every non-EXECUTE verdict, **including `NOT_EVALUATED`**, to an imperative red `STOP` pill on the main table; `NOT_EVALUATED` was 147 of 235 rows in run `20260909_071646`, so 147 rows would display "STOP" purely because EIL never ran. The adjacent line `:2736` *was* correctly relabelled ("Legacy Size Diagnostic (Non-authoritative)"), which shows the relabelling pass ran and missed these. Also `NEGATIVE_RR → NO_TRADE`. DOI-10 step 3 required exactly this wording be removed. | 151 / 84 / 0 (all rows) | HIGH | Relabel to non-authoritative entry telemetry and render absence of evidence as absence, not as STOP. Closed by the rendered template plus a screenshot of the next evening Lab. |
| DOI-D33 | DOI-10 | LIN | P1 | 9 of 14 displayed DOI values fall through to a JavaScript fallback on all 10 sampled rows (5 CALL / 5 PUT); no dataset ID and no model/calculation version is traceable from any displayed DOI value. DOI-10's exit criterion is "a trader can trace every displayed value to a thesis, contract observation and model version". | 5 / 5 / 0 sampled | HIGH | Render lineage fields. Closed by tracing 10 rows on a post-DOI evening artefact. |
| DOI-D39 | DOI-5 | LIN | P1 | `assess_american_exercise_materiality` (`domain/deterministic_option_valuation.py:219–229`) takes `option_side, spot, strike, dividend_yield, ex_dividend_within_horizon` — it has no `r`, no `T`, no `σ`. Early-exercise materiality cannot be assessed without them. Worst measured unflagged understatement **19.39%** (ATM, 1y, r=8%: 4.4175 vs 5.2739), carrying `DETERMINISTIC_ONLY`, i.e. full confidence. Meanwhile a 0.00%-error 14-day put at S/K=0.75 **is** flagged. §11.4 requires flagged cases to carry lower applicability. | asymmetric: CALL branch requires `ex_dividend_within_horizon` | HIGH | Pass r, T and σ into the predicate. |
| DOI-D40 | DOI-5 | LIN | P1 | For unflagged deep-ITM puts the engine returns a value **below intrinsic**: at S/K=0.85 it returns 13.9644 against intrinsic 15.00. `:216` clamps to the European lower bound rather than intrinsic. A holder beats the quoted value today by exercising. | PUT | HIGH | Clamp to intrinsic. Closed by an arithmetic fixture at several ITM depths. |

---

## P2

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf | What would close it |
|---|---|---|---|---|---|---|---|
| DOI-D03 | DOI-10/11 | TEST | P2 | The claimed "120-test pack" is `unittest` discovery over `test_dynamic_options_*.py` (104) + `test_doi*.py` (16). pytest collects **124**. The gap is one whole file: `tests/test_dynamic_options_non_discard_policy.py`, four module-level pytest functions that `unittest` cannot collect (`Ran 0 tests / NO TESTS RAN`). Those four guard §1.1 and invariants 3, 4, 6 — and I rated them among the strongest in the pack. All 124 pass under pytest. | n/a | HIGH | Install pytest on the acceptance interpreter, or convert the four to `TestCase` methods, and restate the number. |
| DOI-D08 | DOI-3 | AUTH | P2 | `underlying_reactivated=True` and `manual_refresh=True` appear **only in tests** (`tests/test_dynamic_options_observation_bridge.py:156, 162, 244, 289`). Production calls the bridge with neither and with `acquire_missing=None` (`canonical_data/dynamic_options_production.py:202–206`). Invariant 13's suppression half is live; its reactivation half is dead. A dormant or breached ticker can never re-acquire a chain and no operator command exists to force it. | all 3 | HIGH | Wire a reactivation caller and an operator refresh entry point. |
| DOI-D12 | DOI-11 | NULL | P2 | `canonical_data/dynamic_options_production.py:227`: `dividend = _number(...) or 0.0`, with no "dividend unknown" quality flag propagated. A genuine economic input to Black–Scholes defaulted from null to zero, on a path whose valuations reach the Lab. **Judgment call, stated openly:** a strict reading of the P0 rubric ("any null coerced to economic zero on a path that reaches the Lab") would make this P0. I rated it P2 because zero is the conventional dividend assumption and the resulting value is a modelling choice rather than fabricated evidence. ACK should overrule if the strict reading is preferred. | all 3 | HIGH | Carry a `dividend_yield_unavailable` disclosure into the assessment. |
| DOI-D16 | pre-existing | TIME | P2 | `empirical_option_ev.py:242–243` repeats the prohibited session-minus-calendar subtraction. | all 3 | HIGH | Exchange calendar. |
| DOI-D17 | pre-existing | TIME | P2 | `calculate_dte_requirement` maps sessions to calendar days 1:1 (its own docstring admits it); floor is short by **9 days**. `layer3_forward_variance.py:167` uses a holiday-blind `days*(5/7)` constant self-described as "not drift". | all 3 | HIGH | Exchange calendar in both. |
| DOI-D18 | DOI-6 | TEST | P2 | `domain/dynamic_options_lifecycle.py:559` sets `economics_recomputed=True` as a **literal** on every return, so the guard at `:196–200` ("contract supersession requires recomputed economics") can never fire, and the value persisted to `option_contract_selection_events.economics_recomputed` is a constant, not evidence. The underlying invariant 10 **does** hold — supersession selects a whole frozen `ContractAssessment` built from the replacement's own observation, with no field copying — but the field that claims to prove it proves nothing. | n/a | HIGH | Compute the flag from the observation identity of the selected assessment. |
| DOI-D19 | DOI-8 | DOC | P2 | The DOI-8 acceptance claims "frozen/synthetic test data is never promoted as production evidence". No such guard exists: `synthetic`, `frozen`, `promot`, `provenance` appear nowhere in the DOI modules, and `ProbabilityModelCard` records no cohort provenance. A synthetic cohort that beat the baselines **would** be accepted. The claim is true of the empty database, not of the code. | n/a | HIGH | Add a provenance field and refuse acceptance for non-production cohorts. |
| DOI-D21 | DOI-11 | DOC | P2 | The rollback "procedure" is one line naming a file (`audit/doi/DOI_PHASE11_IMPLEMENTATION_20260910.md:29–30`). No restore command, no verification step, and no account of the code side — which has no git handle at all because of DOI-D01. | n/a | HIGH | Write the procedure and rehearse it. |
| DOI-D22 | DOI-11 | DOC | P2 | Three of eleven §18 release diagnostics have no producer in `DOIProductionSummary`: family switches / hysteresis suppressions, probability model coverage and OOD count, and **CALL/PUT distribution**. | n/a | HIGH | Add the three aggregates. |
| DOI-D24 | DOI-11 | DOC | P2 | The six DOI-11 rehearsal numbers (20/20 tickers, 10 CALL / 10 PUT, 6,740 audited, 240 valued, 20 reuses, 0 fetches, 0 exceptions) exist only as narrative in `DOI_PHASE11_IMPLEMENTATION_20260910.md:44–54`. No persisted rehearsal artefact was retained and the isolated DB copy is gone, so none is reproducible. All six are `NOT TESTABLE`. (They are internally self-consistent: 20 × 12 = 240 requires every family to saturate the bound, and 6,740/20 = 337 average makes that plausible.) | 10 / 10 / 0 claimed | HIGH | Retain the rehearsal `DOIProductionSummary` JSON and the DB copy. |
| DOI-D25 | DOI-1..3 | TEST | P2 | All three tests in `tests/test_doi_phase_quality_assurance.py` are source-text greps wearing invariant names. `test_eil_runner_is_permanently_advisory` asserts the substring `"advisory_only = True"`; `test_observation_bridge_has_no_provider_or_network_authority` checks only **direct** imports of one file against six names; `test_domain_contracts_cannot_gain_trading_authority` asserts three literal source strings. Each passes on text, not behaviour. | n/a | HIGH | Replace with behavioural equivalents; my `probe_t11_import_graph.py` is the transitive version of the second. |
| DOI-D30 | DOI-10 | AUTH | P2 | The DOI-10 merge bypasses the repo's own overlay guard entirely; 16 of the 24 mutated fields sit outside `OVERLAY_ALLOWED_FIELDS`. Same root cause as DOI-D27. | all 3 | HIGH | Route the merge through the existing guard. |
| DOI-D31 | DOI-10 | DEL | P2 | A duplicate or empty ticker raises in `merge_all_opportunities` (`domain/dynamic_options_projection.py:109–110`) and aborts the **whole** overlay; `intelligence-lab/intelligence_lab.py:317–320` swallows the exception silently. One two-sided or STRANGLE ticker kills DOI-10 for every row with no visible signal. Reproduced. | OTHER triggers it; all 3 lose the overlay | HIGH | Skip the offending ticker with a disclosed state instead of aborting, and log. |
| DOI-D32 | DOI-10 | NULL | P2 | The merge stamps `lab_schema_version=v3` on exactly the 4 accepted rows, so `populateGovernedDisplayFields` skips them and the four most important rows lose sector/campaign/veto aliasing. | 4 / 0 / 0 | HIGH | Stop overloading the schema-version field as a rendering switch. |
| DOI-D34 | DOI-10 | DOC | P2 | The advisory resolver is real and correctly refuses executable-session requests (a `raise` before any file access; 29/29 probe assertions pass) but is **unreachable from production** — absent from `__all__`, no live caller. The DOI-10 acceptance presents it as delivered. | n/a | HIGH | Export and call it, or restate the claim. |
| DOI-D35 | DOI-10 | NULL | P2 | `doi_projection_state \|\| 'NOT_EVALUATED'` collapses "DOI never ran" into "DOI ran and found no family". §15 requires those be distinguishable (`DATA_UNAVAILABLE` vs `NOT_EVALUATED`). | all 3 | HIGH | Separate the two states in the renderer. |
| DOI-D36 | DOI-10 | LIN | P2 | The Lab book carries stale `contract_*_size` values contradicting its own `morning_contract_*_size` under a single snapshot id; bundles mislabel `lab_schema_version`. | all 3 | MEDIUM | Single-source the sizes. |
| DOI-D41 | DOI-5 | DOC | P2 | The DOI-5 engine computes **no Greeks at all** — `delta`, `gamma`, `theta`, `vega` appear zero times in `domain/deterministic_option_valuation.py`. Provider delta is passed through and never revalued in any of the 18 scenario cells. §14 requires Greeks on the preferred-contract panel and §17.1 requires Greek-sign symmetry tests. Classified `DOC` because it is an undisclosed gap against the spec, not a row deletion. | all 3 | HIGH | Implement Greeks or disclose their absence in the acceptance record. |
| DOI-D42 | DOI-5 | SYM | P2 | `ex_dividend_within_horizon` and `corporate_action_flag` are **never passed by any production caller**, so the CALL-side American-exercise governance is dead code while the PUT side is live. An invariant-8 asymmetry. | CALL | HIGH | Wire the flags from the dividend calendar. |
| DOI-D43 | DOI-5 | NULL | P2 | Post-expiry scenario points are silently valued at intrinsic with no disclosure. | all 3 | MEDIUM | Emit a disclosure. |
| DOI-D44 | DOI-5 | TEST | P2 | Existing tests **lock the time-unit bug in**: they assert `dte=5, hold=5 → T=0`. Any correct fix to DOI-D15 breaks them. | n/a | HIGH | Rewrite the fixtures against calendar-correct expectations. |

---

## P3

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf |
|---|---|---|---|---|---|---|
| DOI-D02 | all | DOC | P3 | DOI added 8 modules / 3,594 lines to `domain/`, the package flagged unauthorised by QT-D11, and modified `domain/__init__.py`. DOI did not create the pattern but is now its largest occupant. | n/a | HIGH |
| DOI-D05 | DOI-1 | SYM | P3 | In my 69,300-evaluation permutation, CALL rows reached 4 distinct `eod_candidate_status` values, PUT rows only 2. The two catalyst-dependent branches are untested on the PUT side by this artefact. Data coverage, not proven code asymmetry. | 4 / 2 statuses | MEDIUM |
| DOI-D06 | all DOI | AUTH | P3 | §6's four-field block is incomplete on 5 of 8 DOI domain modules: `contract_family_generation.py`, `deterministic_option_valuation.py` and `dynamic_options_projection.py` carry only `decision_authority`; `dynamic_options_lifecycle.py` and `dynamic_options_outcomes.py` omit `can_invalidate_thesis`. Mitigated strongly: the persistence layer enforces all four as SQL `CHECK` constraints (`canonical_data/option_liquidity_lifecycle.py:445–448`). Residual gap is the in-memory Lab/Interpreter payload (`domain/dynamic_options_projection.py:89`). | n/a | HIGH |
| DOI-D07 | DOI-7 | DOC | P3 | §5.6 makes the Decision and Outcome Ledger the outcome authority and §17.4 requires it receive every candidate assessment. DOI writes nothing to it; labels live in the control plane. A knowing divergence, disclosed in the DOI-7 paragraph, but a divergence. | n/a | HIGH |
| DOI-D09 | DOI-2 | DOC | P3 | `DOIThesisConditionState` has 7 of §8.1's 8 members: `THESIS_ACTIVE` absent, `THESIS_VALIDATED`→`THESIS_CONFIRMED`, `THESIS_DATA_INSUFFICIENT`→`DATA_INSUFFICIENT`. The two semantically loaded ones (`THESIS_CONDITION_BREACHED`, `HORIZON_ELAPSED_REASSESS`) are verbatim. Contract-entry states are 9 of 9 exact. | n/a | HIGH |
| DOI-D10 | DOI-6 | NULL | P3 | `domain/dynamic_options_lifecycle.py:354–355`: `volume or 0.0` in the material-trigger comparison. Effect is to fire more re-evaluation. | all 3 | HIGH |
| DOI-D11 | DOI-3 | NULL | P3 | `canonical_data/dynamic_options_bridge.py:280`: `abs(delta) or 0.0` buckets a missing delta as 0 for a PCR scope. | all 3 | HIGH |
| DOI-D13 | DOI-8 | NULL | P3 | `canonical_data/dynamic_options_probability.py:105`: `bid_size or 0.0`, `ask_size or 0.0` in feature construction. | all 3 | HIGH |
| DOI-D14 | DOI-4 | DOC | P3 | `canonical_data/dynamic_options_family.py:437` counts `open_interest is None or < 50` together as `retained_low_open_interest` in the §18 diagnostic. The per-contract audit keeps missing and low distinct. | all 3 | HIGH |
| DOI-D20 | DOI-11 | TEST | P3 | `tools/doi11_production_readiness.py:141–144`: `authority_separation` degrades to `AWAITING` whenever the DOI tables are missing, and a `sqlite3.Error` from schema drift is caught at `:133–134` and also yields `AWAITING`. The authority gate can never report `FAIL` for a schema problem. | n/a | HIGH |
| DOI-D23 | DOI-11 | DOC | P3 | `canonical_data/dynamic_options_production.py:270` passes `physical_fetch_count=0` as a literal, ignoring the genuine per-observation counter at `dynamic_options_bridge.py:585–600`. Vacuous as a §18 diagnostic — but the guarantee is enforced three other ways (`acquire_missing=None`; a per-ticker `UNEXPECTED_PROVIDER_FETCH` raise at `:207–208`; the `__post_init__` guard), so a real fetch would surface as an **exception**, not a wrong zero. Downgraded from my first reading. | n/a | HIGH |
| DOI-D26 | pre-existing | DOC | P3 | `tests/msi` collects 237 tests, is unmentioned in both DOI phase documents, and still fails — it did not complete in 600 s and showed ≥14 failures across ~81% of the suite. Pre-existing, not a DOI regression, but a "120 passed" headline beside it overstates coverage. | n/a | MEDIUM |
| DOI-D37 | DOI-10 | DEL | P3 | `intelligence-lab/static/index.html:706` reassigns the base population rather than filtering a view. Zero rows affected in this run, but structurally it can shrink the "unfiltered" book. | all 3 | MEDIUM |
| DOI-D38 | pre-existing | SYM | P3 | ANET and CSCO display `DIRECTION_CONFIRMED` while 100% of their resolution evidence weighs the other way. Pre-existing v2 governance, possibly intended, displayed unflagged. | 2 / 0 / 0 | MEDIUM |
| DOI-D45 | DOI-5 | PERSIST | P3 | The ex-dividend flag leaves no trace in the persisted assessment except for ITM dividend CALLs. | CALL | MEDIUM |
| DOI-D46 | DOI-5 | LIN | P3 | EARLY / MID / LATE scenario ordering is never validated. | all 3 | MEDIUM |
| DOI-D47 | DOI-9 | DOC | P3 | `CALIBRATED_POLICY_UTILITY` names a mode whose **inputs** are calibrated while its **weights** are not. Not a `PROB` defect — no value is labelled a probability — but the mode name overstates. | n/a | HIGH |
| DOI-D48 | pre-existing | DOC | P3 | A duplicate hand-copied XNYS holiday table exists in `audit/preflight/`, a second source of truth for the exchange calendar. | n/a | MEDIUM |

---

## Addendum — pre-existing `PROB` defects on the Lab surface

Found by a follow-up mislabelling sweep after the main tracks closed, and
verified by me line by line. **None is DOI-introduced**: all three files are
tracked and, apart from unrelated AVS-FIX-001 edits, carry no DOI change
(`git diff contracts/lab_control.py | grep -c '^+.*win_prob_predicted'` = 0;
`vanguard/layer2_statistical/*.py` are clean). Removing DOI would not remove
any of them.

They are filed at **P0 by the letter of the prompt's rubric** ("any
deterministic value labelled as a probability"), and they are **excluded from
the DOI P0 count** in `06_verdict.md`, which answers a question about DOI.

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf | What would close it |
|---|---|---|---|---|---|---|---|
| DOI-D49 | pre-existing | **PROB** | **P0 (non-DOI)** | `avshunter_discovery_ULTIMATE.py:612–622`. `calculate_win_probability` is a hardcoded affine transform of a composite score, `base_prob = 40.0 + (composite * 0.25)`, clamped `min(75.0, max(35.0, ...))`. Docstring: *"Estimate win probability"*. No calibration, no model, no Brier or log loss, no holdout. It then becomes an expectation at `scripts/avshunter_options_intelligence.py:5764–5767`: `win_prob = ctx['win_prob'] / 100.0` then `ev_structural = win_prob * option_gain - (1-win_prob) * mark`, under the comment *"EV using structural win probability"*. A hand-picked clamp is doing the work of a calibrated probability inside an expected-value calculation. | not measured on the book (`win_probability` is not a book column; it reaches the Lab through the EV) | HIGH | Rename to an uncalibrated score, or calibrate it against the §17.3 evidence list. |
| DOI-D50 | pre-existing | **PROB** | **P0 (non-DOI)** | `contracts/lab_control.py:2522`: `"win_prob_predicted": first(sig, "win_prob_predicted", "ev2_p_win_blended", "win_rate_20d", "win_rate_10d")`. A field named as a *predicted probability* silently falls back to a backward-looking sample **frequency** over 20 or 10 days. Those are different quantities and the Lab does not disclose which one it is showing. Populated on **235 of 235 rows**. Related: `layer2__raw_prob_target_hit` and `layer2__adjusted_prob_target_hit` (allow-listed at `contracts/lab_control.py:456–457`) originate as an empirical sample mean, `vanguard/layer2_statistical/actuarial_query.py:695` `raw_prob_target_hit = self._mean_numeric(sample, target_col, default=0.0)`, also populated on 235 of 235 rows, and carrying a `default=0.0` null-as-zero on a probability-named field. | 151 / 84 / 0 on all three fields | HIGH | Name the sample frequency as a frequency, disclose the fallback used, and drop the zero default. |
| DOI-D51 | pre-existing | **PROB** | **P1 (non-DOI)** | `vanguard/layer2_statistical/scenario_builder.py:188–201` (duplicated identically in `vanguard/layer3_execution/scenario_builder.py`, and repeated at `:319/:366` and `:432/:477`). An if-else additive ladder: start at `max(aggressive_base_probability, horizon_win_rate)`, then `+= 0.05`, `+= 0.05`, `+= 0.03` on three unrelated conditions, clamp to `max_probability`, and call the result `win_probability`. It immediately drives `expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)`. Rated P1 rather than P0 only because I did not establish that this value reaches the Lab; the two above do. | not established | MEDIUM | Trace it to the Lab, then rename or calibrate. Raised to HIGH by that trace. |

**Scope confirmation.** The DOI-5 valuation path does not import any of this.
`canonical_data/dynamic_options_valuation.py:20–42` imports only
`domain.contract_family_generation`, `domain.deterministic_option_valuation`,
`domain.dynamic_options_intelligence`, `.dynamic_options_bridge`,
`.option_identity`, `.option_liquidity_lifecycle` and `.session_clock`;
`domain/deterministic_option_valuation.py:22–25` imports only
`.dynamic_options_intelligence`. My own `probe_t11_import_graph.py` reached 29
first-party modules and none of these. DOI-5 remains clean.

---

## Addendum 2 — findings from the first real DOI run, `20260910_150045`

An evening run executed after this audit closed. It is the first artefact in
which DOI actually ran, so several items above can now be re-stated against
real evidence. I did not run the pipeline; I read its outputs.

### What the run proves (positive, now `VERIFIED`)

| Measure | Value |
|---|---|
| `input_rows` | 1,424 |
| `unique_tickers` | 1,424 |
| `retained_opportunities` | 1,424 |
| `deleted_opportunities` | **0** |
| `physical_fetch_count` | **0** |
| `canonical_reuse` | 1,241 |
| provider-related exceptions | **0** |
| Lab book population | 1,424 — CALL 791 / PUT 451 / OTHER 182 |

The non-discard guarantee held in production on a population six times larger
than the reference run, and `OTHER` rows survived rather than being dropped:
182 non-directional theses were counted `NOT_APPLICABLE_NON_DIRECTIONAL` and
**retained**. Invariants 4, 6 and 13's retention half move from
`VERIFIED OFFLINE` to **`VERIFIED`**. Reuse-first held with zero provider calls.

### DOI-D52 — DOI reads a field that does not exist yet when it runs

| ID | Phase | Class | Sev | Evidence | CALL/PUT/OTHER | Conf | What would close it |
|---|---|---|---|---|---|---|---|
| **DOI-D52** | DOI-11 | **LIN** | **P1** | `canonical_data/dynamic_options_production.py:227` gates valuation on `_first(raw, "ev3_rate_used", "risk_free_rate")`. `risk_free_rate` does not exist in the options CSV at all. `ev3_rate_used` is written **only** by `vanguard/ev_engine_v3.py:569` and `:741`, and EV3 runs at `intelligent_orchestrator.py:4838–4839`, which is **after** the DOI call at `:4828`. DOI therefore reads a column its producer has not yet written. Result on the first real run: `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` on **1,241 of 1,241 families**, `assessed_families=0`, `ranked_families=0`, `lifecycle_families=0`. DOI-5 through DOI-9 produced nothing, and `doi_projection_state` is `DATA_UNAVAILABLE` on 1,424 of 1,424 Lab rows. Only 5 of the 9 DOI tables were ever created, because the valuation, ranking and probability paths never executed. | families rejected: CALL 791 / PUT 451 / OTHER 0 of those eligible | HIGH | Source the rate from a stage that precedes DOI, or move the rate resolution ahead of the DOI call. Closed by an evening artefact with `assessed_families > 0`. |
| **DOI-D53** | DOI-11 | **TEST** | **P2** | The DOI-11 fixtures hand-supply the field production cannot have: `tests/test_doi11_production_integration.py:107, 111, 165, 202` each set `"ev3_rate_used": .045` directly on the input row. The five focused DOI-11 tests therefore pass while the production path they model cannot value a single family. This is the QT-D01 pattern again: the fixture provides the input that production lacks. | n/a | HIGH | Build the fixture from a real stage output, or assert the rate's provenance. |

The run is evidence that DOI is **safe** and that it is currently a **no-op**.
Nothing was deleted, hidden, closed or funded; and nothing was assessed.
Note the interaction with **DOI-D23**: because `physical_fetch_count` is a
literal, the honest signal for this run is that zero provider-shaped exceptions
occurred, which I checked against the exception list rather than the counter.

### DOI-D29 is now partially fixed

`intelligence-lab/static/index.html` changed overnight. The imperative `STOP`
pill is gone: `grep -c "'STOP'"` returns **0**, and `:2114` now maps
`NOT_EVALUATED` to `N/A` and everything else unmatched to `OBS`. That closes
the larger half of DOI-D29.

**Still open:** `:2737` continues to render `Advisory Only  NO` whenever
`eil__advisory_only` is not the literal string `'True'` or `'true'` (`:2715`).
Gate `DOI-G11-EIL-WORDING` still fails on it.

### Two corrections to my own checker, made after this run

`tools/check_doi_gates.py` reported two false FAILs on first contact with real
data. Both are fixed, and the reference run's result is unchanged.

- **`DOI-G03`** failed on `exception_count == 1`, treating any ticker exception
  as evidence of a provider fetch. The single exception was
  `MISSING_GOVERNED_THESIS_ID` for ticker `DEC`, retained. The gate now
  inspects the exception list for provider-shaped errors and reports other
  ticker exceptions separately.
- **`DOI-G09`** failed on four probability-named DOI columns that are `None` on
  all 1,424 rows, and on `doi_probability_model_id`, which is an identifier not
  a probability. A reserved column name is not a mislabel. The gate now
  requires a field to be **populated** before it counts, and excludes
  `_id`, `_state`, `_version` and `_applicability` suffixes.

Both were my errors, not the implementation's. Corrected gate results for
`20260910_150045`: 4 PASS, 1 FAIL (`DOI-G11`), 7 AWAITING, **0 P0 failures**.

---

## Deliberate non-findings

Recorded so their absence is not mistaken for an oversight.

- **No `PROB` defect in the DOI package.** Both the T5 verifier and I checked
  every DOI-5 output field name against `prob`, `probability`, `p_`,
  `likelihood`, `confidence`. The ranking value is `ranking_score_uncalibrated`
  (25 occurrences), `DeterministicScenarioAssessment.probabilities_calibrated`
  defaults `False` and **raises** if ever set true
  (`domain/deterministic_option_valuation.py:128–133`), and the `p_*` slots are
  never populated by DOI-5. §11.6 and non-goal 5 are satisfied **by DOI**.
  **Correction to an earlier draft of this file, which said "no `PROB` defect
  anywhere":** that was true of DOI and false of the Lab surface. Three
  pre-existing `PROB` defects reaching the same Lab are filed below as
  DOI-D49–D51.
- **No `SEC` defect.** No API key value was read or echoed at any point.
- **No `EXEC-BLOCKED` outcome.** Every module executed was proven provider-free
  first. The pipeline was never run.
- **No row-deletion defect in DOI's own code.** 69,300 permutations of EIL,
  entry, exit, timing, spread, OI and volume dropped zero rows
  (CALL 0 / PUT 0 / OTHER 0); `DOIProductionSummary.__post_init__` cannot be
  constructed if anything was dropped.
- **Macro is absent from the DOI path entirely** — more conservative than §11.1
  permits. A positive deviation.
