# T6 / T7 / T8 / T9 — Lifecycle, outcome labels, probability models, ranker

Interpreter: `venv\Scripts\python.exe` (3.13.14).

**Ceiling statement.** No DOI row of any kind exists in the live control plane
(`03_inventory.md` §T0.4: the nine DOI tables are absent from `sqlite_master`).
Every positive result in these four tracks is therefore capped at
`VERIFIED OFFLINE`. Nothing here can reach `VERIFIED`.

---

# T6 — Lifecycle, hysteresis, supersession (§8.3, §12, invariant 10)

## T6.1–T6.2, T6.6–T6.7 State transitions without row loss

`domain/dynamic_options_lifecycle.py` carries two enums:
`DOIThesisConditionState` (7 members, `:44–51`) and `ContractTransitionState`
(`INITIAL, STABLE, MATURED, DEGRADED, SUPERSEDED, EXPIRED`, `:54–60`). Both
maturation (monitor → acceptable) and degradation are first-class states rather
than removals, and `THESIS_RECOVERING` has a live transition at `:409`.

The project's own lifecycle pack (16 tests) covers maturation, degradation,
breach → recovery (`tests/test_dynamic_options_lifecycle.py:132`, `:339–343`)
and elapsed → reassess. All pass. Rated in `T12_regression_quality.md`.

**Result: `VERIFIED OFFLINE`.** Confidence MEDIUM — I relied on the project's
own lifecycle simulations here rather than writing my own, because the
supersession probe (T6.5) was the higher-value target. Raised to HIGH by an
independent lifecycle simulation.

## T6.3–T6.4 Supersession, hysteresis and non-supersession

`domain/dynamic_options_lifecycle.py:505–560`. The decision tree is exactly
§12.3, and **retention is the default**:

| Situation | Outcome | Reason emitted |
|---|---|---|
| challenger is the incumbent | retain | `RETAIN_CURRENT_TOP_RANK` |
| incumbent has no comparable score, challenger adequate | switch | `SUPERSEDE_CURRENT_NOT_COMPARABLE` |
| incumbent has no comparable score, challenger inadequate | **retain** | `RETAIN_CURRENT_ALTERNATIVE_QUALITY_INSUFFICIENT` |
| margin ≥ policy margin **and** adequate quality **and** stress-preferable | switch | `SUPERSEDE_UTILITY_MARGIN_AND_STRESS` |
| any of those three unmet | **retain** | `RETAIN_CURRENT_HYSTERESIS` |
| challenger outside the current family | switch only via | `SUPERSEDE_CONTRACT_OUTSIDE_CURRENT_FAMILY` |

All four §12.3 conditions are conjunctive at `:537`:
`margin >= policy.minimum_utility_margin and _adequate_for_switch(best) and stress_preferable`,
with direction/horizon consistency enforced by family membership at `:517`.
The default margin is `0.10` under
`DOI_HYSTERESIS_POLICY_VERSION = "doi-hysteresis-policy-uncalibrated-v1"`
(`:29`, `:73`) — correctly named as uncalibrated.

Non-supersession is therefore tested as a first-class outcome, not just
supersession. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T6.5 No carried-forward economics (invariant 10)

**The substance holds.** `ContractRankingDecision.selected_assessment` is a
whole `ContractAssessment` object drawn from the ranked list; each was built
from its own contract's own observation row. `ContractAssessment` is
`@dataclass(frozen=True, slots=True)` (`domain/dynamic_options_intelligence.py:387`).
There is no field copy, no `dataclasses.replace`, and no `dict.update` between
assessments anywhere in the supersession path. Premium, Greeks, payoff, IV and
liquidity cannot survive a switch because the old object is discarded whole.

**But the guard that claims to prove it is vacuous.** `:196–200`:

```python
if self.switched_contract and not self.economics_recomputed:
    raise ValueError("contract supersession requires recomputed economics")
```

`economics_recomputed` is set to the literal `True` at `:559` on every return
from `rank_and_apply_hysteresis`. It is never computed from anything. The guard
can therefore never fire, and the field that is persisted to
`option_contract_selection_events.economics_recomputed`
(`canonical_data/dynamic_options_lifecycle.py:396`) is a constant, not
evidence. An auditor reading that column would believe recomputation had been
checked.

This is the QT-D01 pattern in a production field rather than a test name.
Raised as **DOI-D18** (`TEST`, P2). Confidence HIGH.

**Result: invariant 10 `VERIFIED OFFLINE` by construction; its self-reported
evidence field is worthless.**

## T6.8 Material triggers (§12.2)

`MaterialTriggerPolicy` (`:73–82`) carries thresholds for spot move, spread
change, volume/quote activity, IV change (`iv_change_points`), DTE boundary,
a better strike/expiry, and a new governed thesis version, plus explicit
`INITIAL` and `MANUAL_REFRESH` trigger kinds (`:40–41`). All seven §12.2
triggers have a code path; `tests/test_dynamic_options_lifecycle.py:76`
covers the initial/manual pair. **`VERIFIED OFFLINE`.** Confidence MEDIUM.

---

# T7 — Outcome labels and no-lookahead (§13)

## T7.1–T7.2 Every assessed candidate is labelled; five states reachable

`domain/dynamic_options_outcomes.py` (607 lines) implements the five DOI-7
acceptance states — completed, option-path-partial, option-return-unavailable,
deferred, data-exception. The project pack covers them in 16 tests
(`tests/test_dynamic_options_outcomes.py`), all passing.

**`VERIFIED OFFLINE`.** Confidence MEDIUM — I did not build my own five-member
family fixture; the higher-value target in this track was T7.5, which is a
live-data question.

## T7.3 No-lookahead and chronological splits

`domain/dynamic_options_probability.py` enforces point-in-time ordering at the
object level. The pack contains four directly relevant tests, all passing:

```
test_outcome_or_future_features_are_forbidden
test_temporally_reversed_edge_is_rejected
test_training_example_enforces_point_in_time_order
test_feature_adapter_uses_only_assessment_time_evidence
```

Rated **strong** in `T12_regression_quality.md` — they assert on rejection
behaviour, not on a fixture constant. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T7.4 Hypothetical outcomes separated from realised fills

DOI writes **nothing** to the Decision and Outcome Ledger: grep for
`decision_outcome_ledger` across all seventeen DOI modules returns no match.
Labels live in `doi_outcome_labels`, a separate table from any realised-fill
store, and `domain/dynamic_options_outcomes.py:209–211, 283` forbid
`can_change_direction`, `can_grant_capital` and `can_close_position`.

Separation is achieved, but by **omission** rather than by the design's
mechanism — §5.6 and §17.4 make the ledger the outcome authority and require it
to receive every candidate assessment. See **DOI-D07** (`DOC`, P3) in
`T1_authority.md`. **`PARTIAL`.** Confidence HIGH.

## T7.5 Zero DOI-7 labels in the live control plane

**CONFIRMED, and more strongly than claimed.** On my copy
(`scratch/control_plane.copy.sqlite`), `doi_outcome_labels` **does not exist**.
Neither do the other eight DOI tables. The live control plane holds eleven
objects, none of them DOI.

Independently corroborated: the live file, `backups/doi_phase1_20260910/control_plane.pre_doi2.sqlite`
and `backups/doi_phase11_20260910/control_plane.pre_doi11.sqlite` all share
sha256 `0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc`, so
no write occurred at any point in the eleven-phase build.

CALL 0 / PUT 0 / OTHER 0. **`VERIFIED`** — this is real production state, not a
fixture. Confidence HIGH.

---

# T8 — Probability models (§11.1–11.3, §17.3)

## T8.1 Interpretable logistic baseline with Platt calibration, independent cohorts

Present in `domain/dynamic_options_probability.py`, with
`calibration_intercept` / `calibration_slope` fields (`:231–232`) — the Platt
two-parameter form. CALL and PUT are separate cohorts, enforced in SQL:
`direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT'))` on both
`doi_probability_models` (`canonical_data/dynamic_options_probability.py:552`)
and `doi_probability_inferences` (`:565`). A model row cannot span sides.
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T8.2 Model-card fields are computed, not hard-coded

`ProbabilityModelMetrics` (`:177–202`) declares `brier_score`, `log_loss`,
`expected_calibration_error`, `baseline_brier_score`, `baseline_log_loss`,
`calibration_bins`, `ood_rate`; `ProbabilityModelCard` (`:207–305`) adds
`training_cutoff_utc`, `calibration_cutoff_utc`, `holdout_cutoff_utc` and the
three split counts. `__post_init__` validates every one is finite and that ECE
and OOD rate are ≤ 1 (`:193–198`).

I could not run the training path on synthetic fixtures to prove the numbers
are *computed* rather than passed in — that would require building a full
cohort fixture, and the project's own pack already exercises it
(`test_interpretable_model_must_pass_later_holdout`,
`test_empty_production_cohort_records_insufficient_model_idempotently`).
**`PARTIAL`.** Confidence MEDIUM. Raised to HIGH by an independent training run
on a synthetic cohort with known metrics.

## T8.3 Rejection gate — a model that cannot beat prevalence is refused

Enforced at object construction, `:269–280`. An `ACCEPTED` card raises unless
**all** of:

```
fitted coefficients and holdout metrics present
"accepted model must beat the Brier baseline"
"accepted model must beat the log-loss baseline"
"accepted model must be stable across temporal holdout windows"
"accepted model exceeds its calibration policy"          (maximum_ece default 0.10)
```

Because this is a `__post_init__` on a frozen dataclass, no application path can
construct an accepted model that fails the gate. I did not need to build the
synthetic losing cohort: the gate is unconditional at the type boundary, which
is stronger evidence than one passing fixture.
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T8.4 Missing support / cohort mismatch / OOD publish no probability

`canonical_data/dynamic_options_probability.py:683–684`:

```python
if inference.applicability_state is ModelApplicabilityState.APPLICABLE \
   and model.status is not ProbabilityModelStatus.ACCEPTED:
    raise DatasetValidationError("unaccepted model cannot publish an applicable probability")
```

and the DOI-5 deterministic assessment is left in place. Minimum cohort sizes
are policy fields (`min_training`, `min_calibration=75`, `min_holdout`,
`min_class_per_split`, `min_temporal_window`, `:163–174`).
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T8.5 Promotion guard against synthetic/frozen data — NOT FOUND

The DOI-8 acceptance paragraph states: *"frozen/synthetic test data is never
promoted as production evidence."*

I searched every DOI module for a data-provenance concept —
`synthetic`, `SYNTHETIC`, `frozen`, `FROZEN`, `promot`, `provenance`,
`PRODUCTION_EVIDENCE` — and found **no guard**. `ProbabilityModelCard` has no
field recording where its cohort came from. A synthetic cohort that happened to
beat the constant-prevalence baseline on Brier and log loss, remain stable
across holdout windows and pass the ECE policy **would be accepted**.

The claim is therefore true as a *statement of what has happened* — nothing has
been trained, because there are zero labels — but false as a *description of an
enforced control*. It is a property of the empty database, not of the code.

Raised as **DOI-D19** (`DOC`, P2). **`REFUTED` as a control; `VERIFIED` as a
statement of current state.** Confidence HIGH.

## T8.6 No accepted model in the live control plane

`doi_probability_models` does not exist. CALL 0 / PUT 0 / OTHER 0.
**`VERIFIED`.** Confidence HIGH.

---

# T9 — Ranker (§11.6, §12.3)

## T9.1 Whole-family fallback when any candidate is unresolved

`domain/dynamic_options_ranking.py:386`:

```python
and all(item.calibrated_components_complete
        for item in candidates if item.deterministic_score is not None)
```

`all(...)` over the whole candidate list. If a single member lacks a complete,
unambiguous calibrated set, `mode` becomes `RankingMode.DETERMINISTIC_FALLBACK`
(`:388`) and **the entire family** is ordered deterministically, with the reason
string at `:402` naming coverage or acceptance as the cause. The design's
"three applicable and one OOD ⇒ whole family falls back" is the literal
semantics of that line. The pack's
`test_partial_probability_coverage_falls_back_for_whole_family` and
`test_duplicate_applicable_target_inference_forces_family_fallback` both pass.
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T9.2 Full family retained, incomplete candidates visible

`test_deterministic_fallback_keeps_every_candidate` and
`test_service_falls_back_retains_low_activity_and_persists_idempotently` pass.
`:481` raises `"every ranking candidate requires exactly one future reward"`,
so a candidate cannot be silently dropped from a replay.
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T9.3 Policy acceptance must not buy reward with coverage

This is the exact test the prompt asks for, and it is enforced at the type
boundary rather than in a test. `:262–269`:

```python
if (self.validation_metrics.reward_lift < 0
        or self.validation_metrics.coverage < self.validation_metrics.baseline_coverage):
    ...
if (self.holdout_metrics.reward_lift <= 0
        or self.holdout_metrics.coverage < self.holdout_metrics.baseline_coverage):
    raise ValueError("accepted ranking policy must improve reward without reducing coverage")
```

plus `:635`, which requires every temporal window to carry
`baseline_not_worse`. A policy that improves reward by dropping coverage cannot
be constructed as accepted. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T9.4 CALL/PUT symmetry of the ranking path

`test_call_put_ranking_is_symmetric` passes; the cohort split is enforced in SQL
as in T8.1. **`VERIFIED OFFLINE`.** Confidence MEDIUM — one symmetry test on
fixtures is thinner evidence than the SQL constraint behind it.

## T9.5 Preferred plus ≥ 2 alternatives with margin and trade-off

`domain/dynamic_options_lifecycle.py:544–548` builds
`alternative_contract_symbols` as every ranked member except the selected one,
then appends any remaining family member, so alternatives are the full family
minus one. `utility_margin` and `selection_reason` are carried on the decision
(`:553–559`). **`VERIFIED OFFLINE`.** Confidence HIGH.

**Naming compliance (§11.6):** the ranker's ordering value is
`ranking_score_uncalibrated` throughout (`:531`, and 25 occurrences across
`domain/` and `canonical_data/`). `DeterministicScenarioAssessment` carries
`probabilities_calibrated: bool = False` with a `__post_init__` that raises
`"DOI-5 deterministic scenarios cannot be calibrated probabilities"` if it is
ever true (`domain/deterministic_option_valuation.py:128–133`). The independent
T5 verifier reached the same conclusion on the DOI-5 path and recorded
**no PROB defect**.

## T9.6 No accepted policy in the live control plane

`doi_ranking_policies` does not exist. CALL 0 / PUT 0 / OTHER 0.
**`VERIFIED`.** Confidence HIGH.
