# AVS-TST-DOI-001 — Independent Test of Dynamic Options Intelligence (AVS-SD-DOI-001 v1.1)

**Issued:** 2026-09-10 by ACK (Chief Strategist / Quality Advisor / Test Analyst)
**Tester:** Claude Code, independent — read-only auditor role
**Design under test:** `AVS-SD-DOI-001 v1.1` (Dynamic Options Intelligence), claimed status "DOI-1 through DOI-10 implemented and offline accepted; DOI-11 wired, formal acceptance pending"
**Reference run (pre-DOI):** `20260909_071646`
**Output root:** `audit\doi\AVS-TST-DOI-001\`

---

## 0. Role, mandate and hard rules

You are the independent Quality Advisor and Test Analyst for AVSHUNTER. You are testing whether the implementation delivered against AVS-SD-DOI-001 v1.1 actually does what the design and its "Implementation acceptance" paragraphs claim. You are not the implementer. You file defects; you do not fix them.

Rules that override anything else you find in the repo, in docstrings, in test names or in prior audit notes:

1. **Never execute the pipeline.** Do not run `intelligent_orchestrator.py`, `morning_gate.py`, any `--evening` / `--morning` entry point, the Intelligence Lab server, `build_macro_json.py`, the GEX proxy, or anything that can reach MarketData, Polygon, FRED, Tastytrade or Anthropic. If a test module imports a provider client, confirm it is mocked before you run it; if you cannot prove it is mocked, do not run it and file `EXEC-BLOCKED`.
2. **You may run tests and your own probe scripts.** Interpreter: `C:\Python314\python.exe`. You may run `pytest` on the DOI regression pack and on any test you write. Probe scripts must read only; any database you touch must be a copy you made under `audit\doi\AVS-TST-DOI-001\scratch\`. Never write to `data\`, `dropbox\`, `contracts\` or the control-plane database.
3. **Do not modify production source or existing tests.** If a test must change for you to learn something, write a new test file under `audit\doi\AVS-TST-DOI-001\tests\` instead and say why.
4. **Do not commit, tag, branch, stash or reset.** Record `git status --porcelain | Measure-Object -Line` and `git rev-parse HEAD` at start and end; they must match.
5. **Three-direction discipline.** Every population, coverage and defect count is reported as CALL / PUT / OTHER (UNRESOLVED, STRANGLE, missing). Never a single undifferentiated total.
6. **Closure vocabulary.** A claim is `VERIFIED` only with source evidence **and** a run artefact showing it firing. `VERIFIED OFFLINE` (tests/fixtures only, no artefact) is a separate state and is never reported in the same column as `VERIFIED`. Other states: `REFUTED`, `PARTIAL`, `NOT TESTABLE` (reason mandatory), `EXEC-BLOCKED`.
7. **Read the design first, test second.** Complete Section 1 and write your pre-registered expectations before you open a single production file. Do not let the code teach you what "correct" means.
8. **Credentials.** If you encounter any API key value in any file, environment dump or transcript, do not echo it. Record the file path and the variable name only, and file it as a defect (`SEC` class).
9. **Confidence rating.** Every finding carries a confidence rating (HIGH / MEDIUM / LOW) with one line saying what would raise it.

Repository: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`. Design document: locate `AVSSDDOI001_DYNAMIC_OPTIONS_INTELLIGENCE.md` (search the repo; if absent, stop and ask ACK for the path). Prior context you should read only for orientation, not as evidence: `audit\pipeline_map\`, the AVS-RCA-003 and AVS-THS-001 notes if present (they establish that the δ 0.40–0.60 single-contract preselection and EIL `BLOCKED` row deletion were the two main recoverable losses DOI is meant to remove).

---

## 1. Comprehension gate (mandatory, before any code is opened)

Write `01_comprehension.md` containing, in your own words:

1. The three independent questions DOI must keep separate (§1) and which domain owns each.
2. The non-discard principle (§1.1) stated as a testable invariant: *what observable in a run artefact would prove it is violated?*
3. The full thesis-state and contract-entry-state vocabularies (§8.1–8.2) and the rule that they must not be folded into `eil_v3_verdict`.
4. The authority matrix (§6) and the four `decision_authority` fields every DOI/Phantom output must carry.
5. The six structural hard exclusions (§10) — and, explicitly, the list of things that are **not** exclusions (OI, volume, PCR, IV percentile, ordinary spread, entry/exit/timing).
6. What "calibrated probability" requires before the word *probability* may appear on an output (§11.6, §17.3), and what name uncalibrated ranking must carry (`ranking_score_uncalibrated`).
7. The hysteresis rule and the "no carried-forward economics" rule on contract switch (§12.3, invariant 10).
8. Trading sessions vs calendar DTE (§9.4, invariant 9).
9. The fifteen regression invariants (§16) numbered exactly as the design numbers them.
10. What each "Implementation acceptance" paragraph (DOI-7, DOI-8, DOI-9, DOI-10, DOI-11) claims as *numbers*: 115-test then 120-test regression pack; run `20260909_071646` rehearsal preserving 235 opportunities with exactly 4 accepted actionable rows overlaid and an unchanged canonical DB hash; production-data rehearsal on an isolated DB copy retaining 20/20 tickers balanced CALL/PUT, 6,740 structurally valid contracts audited, 240 bounded contracts valued/ranked, 20 canonical chains reused, 0 provider calls, 0 exceptions; at most 12 contracts per family in the live path; zero persisted DOI-7 labels; no accepted probability model or ranking policy.

Then write `02_expectations.md`: for every claim in item 10 and every invariant in item 9, state **before testing** what evidence you expect to find, where you expect to find it (module, table, artefact path), and what result would refute it. This file is frozen once written — do not edit it afterwards; corrections go in the findings.

---

## 2. Inventory and baseline (Track T0)

Produce `03_inventory.md`:

- `git rev-parse HEAD`, current branch, tag list containing `avs-`, and the porcelain count. Note whether the DOI work is committed or sits in the working tree (recall QT-D02: runs that cannot identify their code).
- Locate every module, package, schema, migration, contract JSON and test file that implements DOI-1..DOI-11. Map each to the phase it serves. Flag any module in a package that was previously flagged as unauthorised (`domain/` — QT-D11) and say whether DOI extended that pattern.
- Count the DOI regression pack. Report the collected test count with the exact `pytest --collect-only -q` selector you used. Reconcile against the claimed 115 (DOI-10) and 120 (DOI-11). If you cannot reach 120 with any reasonable selector, that is a finding, not a rounding error.
- Identify the control-plane database(s), the option-liquidity lifecycle tables, and the new DOI tables (families, assessments, rankings, labels, models, policies). Record row counts CALL/PUT/OTHER on a **copy**. The design says the live control plane has zero DOI-7 labels, no accepted models and no accepted policies — confirm or refute.
- Identify the eight-plus runtime flags / the checked-in runtime profile (`contracts\dynamic_session_runtime_v1.json` or successor) and record which DOI switches exist, their defaults, and who reads them.

---

## 3. Test tracks

Each track gets its own file `T<n>_<name>.md` with: objective, method, evidence (paths, line numbers, test IDs, artefact fields), result per claim using the closure vocabulary, CALL/PUT/OTHER split, defects raised, confidence.

### T1 — Authority leakage and non-discard (DOI-1, invariants 1–7, 13, 15)

This is the track that matters most. The design exists because `eil_v3_verdict=BLOCKED`, spread, OI, volume, missing quotes, elapsed timing and exit conditions were deleting governed opportunities.

1. Static: grep every consumer of `eil_v3_verdict`, `BLOCKED`, `WATCHLIST`, `EXECUTE_WITH_CAUTION`, spread thresholds, `open_interest`, `volume`, `HORIZON_ELAPSED`, `INVALIDATION_LEVEL_BREACHED`, `TARGET_TOUCHED`, exit-discipline outputs, `tradeable`, `final_action`, Phase 10 removal logic, Lab hard veto, Interpreter handoff guard, sovereign gate. For each consumer classify: **deletes row / caps population / alters ranking or tier / sets capital or size field / advisory only**. Anything in the first four classes is a defect against invariants 3, 4, 6 unless it is the accepted actionable Interpreter handoff (§DOI-10 says that handoff remains actionable-only — check that it is a *projection*, not a mutation of the book).
2. Permutation test (the DOI-1 exit criterion): write a probe that takes the governed opportunity book from run `20260909_071646` (or the fixtures the regression pack uses), permutes EIL verdicts, entry/exit/timing states and spread/OI/volume values, and re-runs the DOI-10 projection and the Lab `ALL OPPORTUNITIES` resolver. The governed population must be invariant; only advisory states and ordering may change. Report population before/after CALL/PUT/OTHER.
3. Confirm the four `decision_authority` fields are present and set to NONE/false on every DOI and Phantom output type, and that nothing downstream reads them as anything other than telemetry.
4. Confirm macro cannot approve/block/reverse (invariant 2): find every macro input to Model A / ranker and prove it is a feature, not a gate.
5. Confirm no automated exit closes or removes a human-held trade (invariant 15): trace Exit Discipline Engine outputs to the ledger and Lab.
6. Dormant/breached/elapsed acquisition suppression (invariant 13, DOI-3.4): prove the suppression is an *acquisition* state and does not remove the row; prove reactivation on underlying-price condition or manual refresh exists in code, not only in the design.

### T2 — Domain contracts, vocabulary and persistence (DOI-2, invariants 11–12)

1. The nine contract-entry states and eight thesis states exist as their own enums and are **not** added to `eil_v3_verdict`.
2. `ContractCandidate` identity = `thesis_id + OCC + observation_dataset_id`; a later observation of the same OCC is a new row, not an update. Prove append-only at the schema level (no UPDATE/DELETE path, or an explicit guard) and at the test level.
3. Round-trip and restart idempotency tests exist and pass; run them. Then write your own: persist a family, restart (re-import), persist the same family again — no duplicate, no overwrite.
4. DOI extended the existing option-liquidity lifecycle schema rather than creating a second raw-data store (DOI-2.3). Confirm no new raw option-observation table exists outside the Canonical Data System.
5. Every assessment binds to immutable dataset IDs and an evidence cutoff (invariant 11). Pick five persisted or fixture assessments and trace each to its canonical dataset ID.

### T3 — Observation bridge and reuse-first (DOI-3, invariant 13, §9.1–9.3)

1. Reuse-first / fetch-missing-only: find the decision point. Prove that identical ticker/session/scope cannot trigger a second provider call. Note the prior finding that `scope_fingerprint` was unstable and `expires_at` NULL — check whether DOI inherits that cache identity or fixed it.
2. Phantom receives canonical dataset IDs and does not refetch (§9.2). Static trace.
3. PCR features are computed at chain / expiry / strike-region / delta-bucket scope, never as a single-contract attribute (§9.3). Verify the scoping code and its unit tests.
4. Snapshots never claim signed order flow (§9.3, non-goal). Grep for "order flow", "flow imbalance", "premium flow" producers and confirm they require actual prints or are flagged as unavailable.
5. Null-vs-zero (invariant 7): find every place a missing bid/ask/IV/OI/volume could become `0`, `0.0` or `False`. Fixtures: quote with `bid=None`, `ask=None`, `oi=None`, `volume=None` must produce `CONTRACT_DATA_INSUFFICIENT`, not a zero-valued economic row.

### T4 — Contract-family generator (DOI-4, §10, invariants 8, 14)

1. Only long single-leg contracts of the governed side are generated. Write a fixture with a PUT thesis and confirm no CALL enters the family and vice versa.
2. Only the six structural exclusions are applied. Enumerate every exclusion condition in the generator source and classify it structural / non-structural. Any non-structural exclusion (an OI floor, a spread cap, a fixed delta band) is a defect against §10 — this is the specific reversal of the δ 0.40–0.60 preselection that cost ~121 tickers per run.
3. Excluded observations remain in the family audit with reason; the ticker remains visible with zero eligible contracts. Fixture: chain where every contract is expired or crossed.
4. One-sided quotes remain monitorable but are never `CONTRACT_ENTRY_ACCEPTABLE`.
5. Family diversity: strike/moneyness, expiry/DTE, liquidity quality, target reachability. Confirm the complete taxonomy is persisted and that the live-path bound of 12 contracts per family is a **display/valuation subset**, not a deletion.
6. DTE-outlives-hold check uses the exchange calendar (invariant 9), not `dte - planned_hold_sessions`. Fixture: planned hold 10 sessions across a holiday weekend.

### T5 — Deterministic scenario and valuation engine (DOI-5, §11.4–11.6, invariant 8)

1. Independent arithmetic: write your own dividend-adjusted Black–Scholes and Greeks for at least six fixtures (CALL and PUT; ITM/ATM/OTM; short and long DTE; one deep-ITM PUT) and compare to the engine to a stated tolerance. Report every discrepancy with both values.
2. Greek-sign and payoff symmetry CALL vs PUT.
3. American-exercise disclosure: the deep-ITM PUT fixture must be flagged with reduced applicability (§11.4).
4. Scenario grid covers early/mid/late favourable, invalidation, base/contracted/expanded IV, friction, dividend flags. Confirm every cell is present in the persisted assessment.
5. **Mislabelling test:** grep every output field name and every Lab label in the DOI-5 path for the tokens `prob`, `probability`, `p_`, `likelihood`, `confidence`. Each must be either a calibrated DOI-8 output with an applicable model or be named `ranking_score_uncalibrated` / clearly scenario-labelled. Any deterministic value wearing a probability name is a defect against §11.6 and non-goal 5.
6. Session/calendar conversion unit tests exist and pass; extend with the holiday fixture from T4.6.

### T6 — Lifecycle, hysteresis, supersession (DOI-6, §8.3, §12, invariant 10)

Using the regression pack's lifecycle simulations plus your own:

1. Monitor → acceptable (quote improves).
2. Acceptable → degraded (IV collapse, adverse move, time decay).
3. Supersession by a family member that exceeds the versioned margin — and **non**-supersession when the margin is not met (hysteresis).
4. Supersession only within the same thesis family unless a new reassessment version exists.
5. On supersession, every contract-specific field (premium, Greeks, payoff, IV, liquidity) is recomputed from the new contract's own observation. Probe: make the replacement contract's observation differ in every field and assert none of the old values survive in the new assessment.
6. Breach → recovering, and elapsed → reassess, with the row present throughout. Count rows before and after every transition.
7. Expired contract stays historical, is never re-queried, and a new family is generated under a new append-only reassessment version only if the ticker is still observed.
8. Material triggers (§12.2): each of the seven triggers has a code path and a test.

### T7 — Outcome labels and no-lookahead (DOI-7, §13)

1. Every assessed candidate — not just the preferred — receives labels where evidence permits. Fixture: family of five, assert five label rows.
2. Label states: completed / option-path-partial / option-return-unavailable / deferred / data-exception all exist and are reachable.
3. No-lookahead: write a test that plants a future observation before the cutoff and asserts it is not used in features. Chronological split test: the cohort builder must exclude labels whose outcome window crosses a split boundary.
4. Hypothetical outcomes are stored separately from realised fills and never presented as P&L. Trace to the ledger schema and to any Lab field.
5. Confirm the live control plane holds zero DOI-7 labels (on your copy) — this is what makes DOI-8/9 correctly unavailable.

### T8 — Probability models (DOI-8, §11.1–11.3, §17.3)

1. The interpretable logistic baseline with Platt calibration exists; CALL and PUT are independent cohorts.
2. Model-card fields: Brier, log loss, ECE, calibration-bin uncertainty, temporal holdout windows, OOD rate, feature ranges, missingness, DTE/delta/spread cohort diagnostics. Confirm each is *computed*, not hard-coded, by running the training path on synthetic fixture data.
3. Rejection gate: a model that does not beat constant-prevalence on both Brier and log loss is rejected. Construct a synthetic cohort where the model cannot beat prevalence and assert rejection.
4. Missing support / cohort mismatch / OOD → no calibrated probability published, DOI-5 deterministic assessment left in place.
5. **Promotion guard:** prove that synthetic/frozen test data cannot be promoted as production evidence. Find the guard; attempt (in your scratch copy) to register a synthetic model as accepted and assert it is refused.
6. Confirm no accepted model exists in the live control plane copy.

### T9 — Ranker (DOI-9, §11.6, §12.3)

1. Calibrated combination is used only when every comparable candidate has an unambiguous applicable probability set; otherwise the entire family uses deterministic ordering. Fixture: family of four with three applicable and one OOD — whole family must fall back.
2. Full family retained; incomplete candidates visible.
3. Policy weights and switch margin are learned on chronological replay and accepted only on non-inferior holdout windows without coverage reduction. Locate the acceptance test; assert it rejects a policy that improves reward by dropping coverage.
4. CALL/PUT symmetry of the ranking path.
5. Preferred and ≥2 alternatives with rank difference and trade-off explanation are produced.
6. No accepted policy exists in the live control plane copy.

### T10 — Intelligence Lab and Interpreter projection (DOI-10, §14) — run `20260909_071646`

This is the only track with a real run artefact. Everything here is evidence toward `VERIFIED`; everything in T1–T9 without an artefact is at most `VERIFIED OFFLINE`.

1. Reproduce the claimed rehearsal on a **copy** of the run and control-plane DB: the projection must preserve all 235 opportunities and overlay exactly 4 accepted actionable rows; the canonical DB hash must be unchanged before/after. Report the 235 and the 4 as CALL/PUT/OTHER. If you get any other numbers, that is the headline finding.
2. `ALL OPPORTUNITIES` is the default view; entry/exit/timing/evidence warnings never remove rows. Compare row counts between the unfiltered governed book and every filtered view.
3. Missing/inactive DOI tables → `DATA_UNAVAILABLE` / `NOT_EVALUATED` states, never removed rows, never zero-valued evidence. Test by pointing the projection at an empty DOI schema.
4. Governed contract and DOI-preferred contract are shown separately with an alignment field.
5. Legacy EIL wording is relabelled as non-authoritative entry telemetry. Grep the Lab templates for any surviving "BLOCKED", "veto", "reject" wording presented as thesis authority (recall the earlier false "advisory" text finding).
6. Interpreter receives the same latest assessment as the Lab (§17.4). Diff the two payloads for a sample of tickers.
7. The advisory resolver rejects executable-session requests (DOI-10 acceptance). Test it.
8. Exact source reconciliation: for 10 rows (5 CALL / 5 PUT), trace every displayed DOI value to thesis_id, contract observation dataset ID and model/calculation version. Any value with no traceable source is a defect against the DOI-10 exit criterion.
9. DOI-10 changes no direction, thesis, lifecycle, action, size or capital field: diff the governed v2 book before and after projection on every non-DOI column.

### T11 — Production wiring and acceptance control (DOI-11) — offline only

Do **not** run the orchestrator. Static and test-based:

1. Locate DOI's call in the evening orchestrator: it must sit after governed horizon propagation and before downstream overlays. Record the call order with line numbers.
2. DOI reads only canonical completed-session MarketData chains; no provider client is importable from the DOI package (static import graph).
3. Ticker-level data exceptions are retained and do not stop or reduce the population.
4. The 12-contract live bound is deterministic and diversified (same input → same subset).
5. The read-only release assessor reports "pending one new evening artefact and next valid Morning Gate" and **cannot** promote a pre-DOI run. Run the assessor against `20260909_071646` on a copy and confirm it refuses.
6. Rollback point: the pre-DOI control-plane DB is retained; record its path and hash. Confirm a documented rollback procedure exists.
7. Release diagnostics (§18): confirm every listed aggregate has a producer — in particular `reconciliation: input theses = assessed + explicitly failed` and `canonical reuse vs provider-call count`.
8. Mark all DOI-11 live claims (`20/20 tickers`, `6,740`, `240`, `20 chains`, `0 provider calls`, `0 exceptions`) as `NOT TESTABLE` unless you can reproduce them from a persisted rehearsal artefact on your copy — if such an artefact exists, reproduce and reconcile.

### T12 — Regression pack quality

1. Run the full DOI pack. Report pass/fail/skip/xfail with the exact command.
2. Read every test that asserts an invariant from §16. Rate each: **strong** (would fail if the invariant were broken in production), **weak** (asserts a fixture constant or tests the mock), **misnamed** (name promises more than the assertion). Recall QT-D01, where a test named "all features disabled by default" passed while production enabled 8/9.
3. Check for tests that were edited or weakened during the DOI build (`git log -p` on the test tree if committed; otherwise diff against `avs-baseline-20260906` or the latest tag).
4. Check whether `tests\msi` and the earlier 24 msi failures are still excluded from the matrix.
5. Report the run-time and any test that touches the network, the real DB or `data\`.

---

## 4. Defect register

`04_defects.md`, one row per defect: `DOI-D<nn>` | phase | class (`AUTH` authority leakage, `DEL` row deletion, `NULL` null-as-zero, `PROB` mislabelled probability, `TIME` session/calendar, `LIN` lineage, `PERSIST` append-only, `SYM` CALL/PUT asymmetry, `TEST` weak/misnamed test, `DOC` claim sheet inaccuracy, `SEC` credential, `EXEC-BLOCKED`) | severity P0–P3 | evidence (file:line, test ID, artefact field) | CALL/PUT/OTHER impact | confidence | what would close it (source evidence + which run artefact).

P0 = any automated layer can delete, hide, permanently invalidate or close a governed opportunity, grant capital, or change direction; any deterministic value labelled as a probability; any null coerced to economic zero on a path that reaches the Lab; any credential exposure.

---

## 5. Claim sheet reconciliation

`05_claims.md`: every numeric or categorical claim from the five "Implementation acceptance" paragraphs and the DOI-11 status paragraph, with columns: claim | where the design says it | what you found | state (`VERIFIED` / `VERIFIED OFFLINE` / `REFUTED` / `PARTIAL` / `NOT TESTABLE`) | evidence | confidence. `VERIFIED` and `VERIFIED OFFLINE` in separate columns.

---

## 6. Verdict

`06_verdict.md`, no more than two pages:

1. **Is DOI safe to leave wired into tonight's Evening run?** Answer YES / YES WITH CONDITIONS / NO, with the conditions enumerated. The question is not "does it work" but "can it remove, hide, close or fund anything" — that is the only thing that can hurt live capital, since DOI is advisory by design.
2. Invariant scorecard: the fifteen invariants of §16, each `VERIFIED` / `VERIFIED OFFLINE` / `REFUTED` / `NOT TESTABLE`.
3. The three most important defects and why.
4. What the next Evening run and the next Morning Gate must show for the `VERIFIED OFFLINE` items to become `VERIFIED` — as a checklist ACK can tick against the artefact (extend `check_run_gates.py` conventions if useful; put the new checker under `audit\doi\AVS-TST-DOI-001\tools\`, do not modify the existing one).
5. Deviations from this prompt (anything you could not do, and anything you did that this prompt did not authorise).
6. Start/end `git rev-parse HEAD` and porcelain counts, proving you left the tree as you found it.

---

## 7. Working method

- Work track by track; write each track file as you finish it so partial progress survives interruption.
- Use subagents for T5 (independent arithmetic) and T10 (artefact reconciliation) so those two are produced by an agent that has not read the implementation — give each only the design section and the fixtures.
- When a claim cannot be tested without running the pipeline or calling a provider, say so and stop; do not approximate.
- Where the design and the code disagree, the design is the specification and the code is the defect — unless the code is more conservative on authority (removes more automation), in which case note it as a positive deviation.
- Prefer small, reproducible probes with the exact command over prose assertions.
- Final message to ACK: the YES / YES WITH CONDITIONS / NO verdict, the P0 count CALL/PUT/OTHER, and the path to `06_verdict.md`. Nothing else.
