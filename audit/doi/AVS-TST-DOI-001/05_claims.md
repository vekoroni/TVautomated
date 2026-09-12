# 05 — Claim sheet reconciliation

Every numeric and categorical claim from the five "Implementation acceptance"
paragraphs (§19, DOI-7 to DOI-11) and the DOI-11 status paragraph.

`VERIFIED` and `VERIFIED OFFLINE` are separate columns, as required.
`VERIFIED` = source evidence **and** a run artefact showing it firing.
`VERIFIED OFFLINE` = tests, fixtures or static proof only.

Run `20260909_071646` is the only real artefact available, and it **predates
DOI**, so `VERIFIED` is reachable almost nowhere outside T10 and T11.5.

---

## DOI-7 — Outcome-label capture

| Claim | Where in the design | What I found | VERIFIED | VERIFIED OFFLINE | Other | Evidence | Conf |
|---|---|---|---|---|---|---|---|
| Provider-free, append-only outcome domain in the **existing** option lifecycle control plane | §19 DOI-7 accept. | `doi_outcome_labels` created in the same control plane; no second store; no provider importable | | ✔ | | `option_liquidity_lifecycle.py` DDL; `probe_t11_import_graph.py` PASS | HIGH |
| Five label states: completed / option-path-partial / option-return-unavailable / deferred / data-exception | §19 DOI-7 accept. | All five present and reachable | | ✔ | | `domain/dynamic_options_outcomes.py`; 16 tests pass | MEDIUM |
| Labels retain exact contract and dataset lineage | §19 DOI-7 accept. | Schema binds it; **no rows exist to sample** | | | `NOT TESTABLE` | no DOI table in the live DB | HIGH |
| Chronological cohorts purge windows crossing a split boundary | §19 DOI-7 accept.; §13 | Enforced at the type boundary | | ✔ | | 4 no-lookahead tests, rated **strong** | HIGH |
| Prohibits realised fills, thesis/capital authority, automated closure | §19 DOI-7 accept. | `can_change_direction` / `can_grant_capital` / `can_close_position` all false with a raising guard | | ✔ | | `dynamic_options_outcomes.py:209–211, 283` | HIGH |
| Offline unit, authority, persistence, restart and frozen-chain rehearsals passed | §19 DOI-7 accept. | Reproduced: 124/124 pass | | ✔ | | `T12_regression_quality.md` §T12.1 | HIGH |
| **Ledger receives every candidate assessment** | §5.6, §17.4 | DOI writes **nothing** to the ledger | | | `REFUTED` | no `decision_outcome_ledger` reference in 17 DOI modules — **DOI-D07** | HIGH |

## DOI-8 — Probability models

| Claim | Where | What I found | VERIFIED | VERIFIED OFFLINE | Other | Evidence | Conf |
|---|---|---|---|---|---|---|---|
| Interpretable logistic baseline with later-period **Platt** calibration | §19 DOI-8 accept. | Present, with `calibration_intercept`/`calibration_slope` | | ✔ | | `dynamic_options_probability.py:231–232` | HIGH |
| CALL and PUT are **independent cohorts** | §19 DOI-8 accept. | Enforced in SQL: `CHECK(direction IN ('CALL','PUT'))` on models and inferences | | ✔ | | `canonical_data/dynamic_options_probability.py:552, 565` | HIGH |
| Model cards include Brier, log loss, ECE, calibration-bin uncertainty, temporal windows, OOD rate, feature ranges, missingness, DTE/delta/spread cohorts | §19 DOI-8 accept.; §17.3 | All declared and range-validated; I could not prove each is **computed** rather than passed in | | | `PARTIAL` | `:177–202`, `:207–305` — **T8.2** | MEDIUM |
| Rejected unless it beats constant prevalence on **both** Brier and log loss, is stable in **each** holdout window, and passes the calibration policy | §19 DOI-8 accept. | Enforced unconditionally in `__post_init__`; an accepted card that fails cannot be constructed | | ✔ | | `:269–280` | HIGH |
| Missing support / cohort mismatch / OOD publish no calibrated probability; DOI-5 left in place | §19 DOI-8 accept. | `raise DatasetValidationError("unaccepted model cannot publish an applicable probability")` | | ✔ | | `canonical_data/dynamic_options_probability.py:683–684` | HIGH |
| **Zero persisted DOI-7 labels in the live control plane** | §19 DOI-8 accept. | Confirmed more strongly: `doi_outcome_labels` **does not exist**. CALL 0 / PUT 0 / OTHER 0 | **✔** | | | live DB copy; sha256 identical to both pre-DOI backups | HIGH |
| No real production model trained or activated | §19 DOI-8 accept. | `doi_probability_models` does not exist | **✔** | | | same | HIGH |
| **"Frozen/synthetic test data is never promoted as production evidence"** | §19 DOI-8 accept. | **No guard exists.** No provenance field, no `synthetic`/`promot` token anywhere. True of the empty database, not of the code | | | `REFUTED` as a control | **DOI-D19** | HIGH |

## DOI-9 — Contract-family ranker

| Claim | Where | What I found | VERIFIED | VERIFIED OFFLINE | Other | Evidence | Conf |
|---|---|---|---|---|---|---|---|
| Full contract family **always retained** | §19 DOI-9 accept. | Behavioural tests pass; `:481` forbids a candidate without a reward | | ✔ | | `test_deterministic_fallback_keeps_every_candidate` | HIGH |
| Calibrated combination only when **every** comparable candidate has an unambiguous applicable probability set; otherwise the **entire family** falls back | §19 DOI-9 accept. | `all(item.calibrated_components_complete ...)` — literal whole-family semantics | | ✔ | | `domain/dynamic_options_ranking.py:386–388, 402` | HIGH |
| Policy accepted only if later cohorts improve reward **without reducing coverage**, every holdout window non-inferior | §19 DOI-9 accept. | `raise ValueError("accepted ranking policy must improve reward without reducing coverage")` | | ✔ | | `:262–269`, `:635` | HIGH |
| Ranking identity, lineage and persistence append-only and independently validated | §19 DOI-9 accept. | DB triggers ABORT UPDATE and DELETE; proven to fire | | ✔ | | `probe_t2b_trigger_fires.py`: 0 breaches | HIGH |
| CALL and PUT paths symmetric | §19 DOI-9 accept. | One symmetry test plus the SQL cohort split | | ✔ | | `test_call_put_ranking_is_symmetric` | MEDIUM |
| **No real DOI assessments, labels, accepted models or accepted policies in the live control plane** | §19 DOI-9 accept. | All nine DOI tables absent. CALL 0 / PUT 0 / OTHER 0 | **✔** | | | live DB copy | HIGH |
| Calibrated ranking correctly unavailable; no synthetic policy promoted | §19 DOI-9 accept. | True — structurally, because nothing exists | **✔** | | | same | HIGH |

## DOI-10 — Intelligence Lab and Interpreter

| Claim | Where | What I found | VERIFIED | VERIFIED OFFLINE | Other | Evidence | Conf |
|---|---|---|---|---|---|---|---|
| **235 opportunities preserved** in the rehearsal of run `20260909_071646` | §19 DOI-10 accept. | **235 in, 235 out. CALL 151 / PUT 84 / OTHER 0** | **✔** | | | reproduced on a copy; assessor independently reports `candidate_count=235 rows=235` | HIGH |
| **Exactly 4 accepted actionable rows overlaid** | §19 DOI-10 accept. | **4. CALL 4 / PUT 0 / OTHER 0** (CVNA, ANET, HPE, CSCO) | **✔** | | | reproduced | HIGH |
| Canonical database hash unchanged | §19 DOI-10 accept. | sha256 identical before and after, and identical to the live file `0f725c01…29cfdc` | **✔** | | | hashed on a copy | HIGH |
| **"The 115-test DOI regression pack passed"** | §19 DOI-10 accept. | The selector collects **124**; all 124 pass. 115 is reachable only with the `unittest` runner that cannot see 4 tests | | | `PARTIAL` | **DOI-D03**, `T12_regression_quality.md` | HIGH |
| UI defaults to `ALL OPPORTUNITIES`; warnings never remove rows | §19 DOI-10 accept.; §14 | Default view retains all 235; every other view is a user-selected organising filter, which §14 permits | **✔** | | | view census across all filters | HIGH |
| Missing/inactive DOI tables produce `DATA_UNAVAILABLE`/`NOT_EVALUATED`, never remove a row, never zero-valued evidence | §19 DOI-10 accept.; §15 | Resolver: 235/235 `DATA_UNAVAILABLE`, all probabilities `None`, zero removals. **Renderer** collapses "never ran" into `NOT_EVALUATED` | | | `PARTIAL` | **DOI-D35** | HIGH |
| Governed contract separated from DOI-preferred contract, with alignment | §19 DOI-10 accept. | Separate rendered fields exist, but preferred is empty on 235/235 and alignment is `NOT_COMPARABLE` on 235/235 — the separation is never exercised | | | `PARTIAL` | pre-DOI run has no preferred contract | HIGH |
| Legacy EIL relabelled as **non-authoritative entry telemetry** | §19 DOI-10 accept.; DOI-10 step 3 | `Advisory Only  NO` still rendered; every non-EXECUTE verdict incl. `NOT_EVALUATED` (147/235 rows) renders an imperative `STOP` pill; `NEGATIVE_RR → NO_TRADE` | | | **`REFUTED`** | **DOI-D29**, `index.html:2116, 2715, 2737` | HIGH |
| Interpreter receives the same latest assessment as the Lab | §17.4 | Byte-identical governed record for the 4 handoff tickers; the 231-row gap is documented scope and the Lab is the staler side | **✔** | | | payload diff | HIGH |
| Advisory resolver **rejects executable-session requests** | §19 DOI-10 accept. | A real `raise` before any file access; 29/29 probe assertions pass. But the resolver is unreachable from production | | ✔ | | **DOI-D34** | HIGH |
| Accepted Interpreter handoff remains **actionable-only** | §19 DOI-10 accept. | Confirmed | **✔** | | | 4 actionable rows only | HIGH |
| Every displayed value traceable to thesis, observation and model version | §19 DOI-10 exit | 9 of 14 displayed DOI values fall through to a JS fallback on 10/10 sampled rows; no dataset ID or model version traceable | | | **`REFUTED`** | **DOI-D33** | HIGH |
| **DOI-10 changes no direction, thesis, lifecycle, action, size or capital field** | §19 DOI-10 accept. | The projection leg changes **zero** non-DOI columns. The **merge** mutates 24, including `selected_contract_symbol` (a declared protected authority field), and nothing prevents it overwriting `governed_direction` or `canonical_direction` | | | **`REFUTED`** | **DOI-D27 (P0)**, **DOI-D30** | HIGH |

## DOI-11 — Controlled production acceptance

| Claim | Where | What I found | VERIFIED | VERIFIED OFFLINE | Other | Evidence | Conf |
|---|---|---|---|---|---|---|---|
| DOI runs **after governed horizon propagation, before downstream overlays** | §19 DOI-11 status | Single call site, `intelligent_orchestrator.py:4828`, between `:4813–4820` and `:4838–4839` | | ✔ | | line numbers | HIGH |
| Uses only canonical completed-session MarketData chains; no provider call | §19 DOI-11 status | No provider client and no network library importable, transitively, across a 29-module closure | | ✔ | | `probe_t11_import_graph.py` PASS | HIGH |
| Persists append-only families / assessments / rankings | §19 DOI-11 status | DB triggers ABORT UPDATE and DELETE; proven to fire on 5 tables, 0 breaches | | ✔ | | `probe_t2b_trigger_fires.py` | HIGH |
| Retains ticker-level data exceptions **without stopping or reducing** the population | §19 DOI-11 status | Every skip path is a state counter plus `continue`; `__post_init__` raises if `retained != unique` or anything was deleted | | ✔ | | `dynamic_options_production.py:102–106, 150–259` | HIGH |
| Complete taxonomy stored; **at most 12 per family** valued, deterministic and diversified | §19 DOI-11 status | Stratified on the four §10 axes, `sorted()` twice, no set/dict ordering; reconciliation guards forbid the subset exceeding the family | | ✔ | | `dynamic_options_family.py:132–160`; `contract_family_generation.py:129–130, 154–163` | HIGH |
| No DOI component may call a provider, change direction, invalidate a thesis, grant capital or remove an opportunity | §19 DOI-11 status | True inside the DOI package. **Not true of the DOI-10 Lab merge**, which can overwrite `governed_direction` | | | `PARTIAL` | **DOI-D27** | HIGH |
| Governed runtime configuration active | §19 DOI-11 status | `enabled: true`; the orchestrator **refuses to run** if the config grants provider access | | ✔ | | `intelligent_orchestrator.py:2776–2781` | HIGH |
| Pre-DOI control-plane database retained as a rollback point | §19 DOI-11 status | Retained and byte-identical to live; no written procedure | | | `PARTIAL` | **DOI-D21** | HIGH |
| **"The 120-test DOI regression pack passes"** | §19 DOI-11 status | 120 is exactly `unittest` over the two patterns (104 + 16), which **silently omits** the 4 non-discard tests. pytest collects 124; 124 pass | | | `PARTIAL` | **DOI-D03** | HIGH |
| 20/20 tickers retained | §19 DOI-11 status | No reproducible artefact | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| 10 CALL / 10 PUT balanced | §19 DOI-11 status | No reproducible artefact | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| 6,740 structurally valid contracts audited | §19 DOI-11 status | No reproducible artefact | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| 240 bounded contracts valued/ranked | §19 DOI-11 status | No reproducible artefact. Self-consistent: 20 × 12 = 240 requires every family to saturate; 6,740/20 = 337 average makes that plausible | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| 20 canonical chains reused | §19 DOI-11 status | No reproducible artefact | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| **0 provider calls** | §19 DOI-11 status | Not reproducible; and the summary field is a **literal `0`**. But the guarantee is enforced three other ways, so a real fetch would appear as an exception | | | `NOT TESTABLE` | **DOI-D23**, **DOI-D24** | HIGH |
| **0 exceptions** | §19 DOI-11 status | No reproducible artefact | | | `NOT TESTABLE` | **DOI-D24** | HIGH |
| Formal acceptance **pending one new evening artefact and the next valid Morning Gate**; the assessor cannot promote an old pre-DOI run | §19 DOI-11 status | Assessor returns `status: NOT_READY` on run `20260909_071646`, for the right reasons — no DOI report, five DOI tables absent, zero DOI advisory rows | **✔** | | | run on an isolated copy, `T11_production.md` §T11.5 | HIGH |
| No calibrated probability claimed until real cohorts pass DOI-8 gates | §19 DOI-11 status | True; and no output is mislabelled as a probability anywhere | | ✔ | | no `PROB` defect found by either verifier | HIGH |

---

## Summary of the claim sheet

| State | Count |
|---|---|
| `VERIFIED` (source evidence **and** a run artefact) | 11 |
| `VERIFIED OFFLINE` | 24 |
| `PARTIAL` | 8 |
| `REFUTED` | 5 |
| `NOT TESTABLE` | 8 |

The five refuted claims are: the ledger receiving every candidate assessment;
the synthetic-promotion guard as a control; the legacy EIL relabelling; full
source traceability of displayed values; and "DOI-10 changes no direction,
thesis, lifecycle, action, size or capital field".

The eight `NOT TESTABLE` claims are all six DOI-11 rehearsal numbers plus label
lineage sampling — every one of them blocked by the same root cause, that no
DOI row exists and no rehearsal artefact was retained.
