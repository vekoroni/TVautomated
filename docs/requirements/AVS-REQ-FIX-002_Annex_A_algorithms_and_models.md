# AVS-REQ-FIX-002 — Annex A: Algorithm and model specifications

**Companion to:** `AVS-REQ-FIX-002_developer_requirements.md` (the *what*); this annex is the *how* — every formula, rule and model a requirement depends on, specified so that two developers would produce the same number and the tester can verify it by hand.
**Status:** v1.2, 2026-09-12 — corrected against the sole implementation authority, `AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md` v1.2
**Convention:** all fractions are decimals (0.25 = 25%); all prices are dollars per share; time in years uses a 365-day calendar basis; sessions are XNYS trading sessions; every algorithm carries a version tag that is written onto every row it produces.

Where an algorithm already exists in the codebase it is named and either reused or extended; nothing here replaces working code without saying so. Existing DOI code that this annex builds on: `domain/deterministic_option_valuation.py` (Black–Scholes–Merton with dividend yield, `evaluate_deterministic_scenarios`, 2×3×3 grid), `canonical_data/dynamic_options_valuation.py` (`build_xnys_scenario_points`), `domain/dynamic_options_ranking.py` (`RankingWeights`, `calibrated_utility`).

---

## ALG-01 Volatility budget — `vol_budget_v2`

**Purpose.** One cumulative 1σ expected move for any hold h ∈ [1, 20] sessions, from the Layer 3 forecast.

**Inputs.** `forecast_vol_annual_fraction` σ_a (Layer 3, annualised); `forecast_model_id`; `bias_multiplier` m (1.0 until ALG-10 passes); h.

**Formula.**

```
expected_move_h = σ_a × m × sqrt(h / 252)
```

Checkpoints published: h = 5, 10, 20. The current Layer 3 contract supplies one annualised forecast, so every 1–20 session value is derived directly from that same forecast and carries `forecast_horizon_basis = SCALED_CURRENT_ANNUAL_FORECAST`. Never interpolate between checkpoints; never use the differenced fields (`layer3_forward_variance.py:515-517`). A future horizon-specific term structure requires a new contract and algorithm version and cannot be introduced through this field.

**Edge cases.** σ_a null → `validation_state = NOT_EVALUATED_DATA_MISSING`, no budget. σ_a ≤ 0 or σ_a > 3.0 → `DATA_DEFECT`. h outside [1, 20] → reject at the aggregate.

**Worked example.** σ_a = 0.30, m = 1.0, h = 5 → 0.30 × √(5/252) = **0.04226** (4.23%). h = 10 → 0.05976; h = 20 → 0.08452. Check: 10d ÷ 5d = 1.4142.

**Oracle.** `expected_move_10d / expected_move_5d ∈ [1.407, 1.421]` on every row; the differenced legacy field never equals the v2 field.

---

## ALG-02 Reachability — `reachability_v1`

**Inputs.** `origin_spot` S₀, `governed_direction`, `structural_target_spot` T_s, `invalidation_spot` I, h, `expected_move_h` e_h (ALG-01), `sigma_multiple` k (config, initial 1.5).

**Geometry guard (before anything else).** CALL requires I < S₀ < T_s; PUT requires T_s < S₀ < I. Violation → `GEOMETRY_INVALID`, named exception, no reachability. Missing I → `INVALIDATION_MISSING`, review state; never fabricate.

**Formulas.**

```
reachable_target = S₀ × (1 + k × e_h)      (CALL)
reachable_target = S₀ × (1 − k × e_h)      (PUT)
structural_distance_fraction = |T_s − S₀| / S₀
volatility_budget_fraction   = e_h
reach_ratio                  = structural_distance_fraction / e_h
```

**Interpretation for the Lab.** `reach_ratio ≤ 1.0`: structural target inside one budget; `1.0–1.5`: reachable at the governed k; `> 1.5`: the structural target is beyond the scenario boundary — the contract is valued at the reachable target, not the structural one.

**Worked example.** S₀ = 100, CALL, T_s = 112, I = 97, h = 5, e_h = 0.04226, k = 1.5 → reachable = 106.34; structural distance 0.12; reach_ratio = 0.12 / 0.04226 = **2.84**.

**Oracle.** Friday GO rows reproduce the verification figure (13 of 19 with reach_ratio > 3; median 4.1) when computed on cumulative moves.

---

## ALG-03 Session-to-calendar bridge — `xnys_bridge_v1`

**Purpose.** Convert "h sessions from the evidence session" into a calendar date, so remaining time to expiry is a calendar quantity.

**Rule.** `time_stop_date = advance_sessions(evidence_session, h)` using the XNYS calendar (`canonical_data/dynamic_options_valuation.py::_advance_sessions` already does this). `time_stop_instant = session_close(time_stop_date)` (16:00 ET). `remaining_years = max(0, (expiry_close − time_stop_instant).total_seconds() / (365 × 86,400))`. Using `timedelta.seconds` is prohibited because it discards whole days.

**Edge case.** `time_stop_date ≥ expiry_date` does not prove that the contract cannot monetise before expiry, but it cannot express the complete governed hold under the first-release time-stop model. The assessment remains visible with `applicability = HORIZON_LIMITED`, `dte_inside_hold = true` and full-horizon monetisability `INDETERMINATE` with reason `CONTRACT_EXPIRES_INSIDE_GOVERNED_HOLD`. No `AT_GOVERNED_TIME_STOP` value is fabricated and the assessment is not directly ranked against full-horizon contracts. A shorter-horizon supplemental valuation requires a separately versioned policy; the thesis and family are never removed.

**Worked example.** Evidence session Fri 11 Sep 2026, h = 5 → time stop Fri 18 Sep 2026 (Mon–Fri, no holiday); expiry 16 Oct 2026 → remaining 28 calendar days = 0.0767 years. h = 7 from Mon 14 Sep → Wed 23 Sep.

---

## ALG-04 Scenario valuation — `scenario_valuation_v2` (extends `evaluate_deterministic_scenarios`)

**Model.** Black–Scholes–Merton, European, continuous dividend yield, constant IV. Existing implementation `dividend_adjusted_black_scholes` is reused unchanged.

```
d1 = [ln(S/K) + (r − q + σ²/2) T] / (σ√T),   d2 = d1 − σ√T
CALL = S e^{−qT} N(d1) − K e^{−rT} N(d2)
PUT  = K e^{−rT} N(−d2) − S e^{−qT} N(−d1)
T = 0 → intrinsic
```

**Inputs per contract.** K, expiry, side; entry `ask` and `bid` at the observation (provider timestamp); σ = contract IV at the observation (mid IV from the provider; if absent, solve from mid price by bisection on [0.01, 5.0]; if unsolvable → `IV_UNAVAILABLE`, no valuation); r from `MarketRateObservation` (continuous, annual); q from dividend evidence or 0 with `dividend_available = false` (existing behaviour, disclosed).

**Scenario grid (replaces the 2-path grid).** Paths × timings × IV stresses:

| Path | Scenario spot |
|---|---|
| `FLAT` | S₀ |
| `FAVOURABLE_1SIGMA` | S₀ (1 ± e_h) |
| `FAVOURABLE_2SIGMA` | S₀ (1 ± 2e_h) |
| `FAVOURABLE_REACHABLE` | S₀ (1 ± k e_h) — ALG-02 |
| `FAVOURABLE_STRUCTURAL` | T_s (disclosure only) |
| `ADVERSE_INVALIDATION` | I |

Timings: the existing EARLY / MID / LATE points (`build_xnys_scenario_points`: ⌈h/3⌉, ⌈2h/3⌉, h sessions), each bridged by ALG-03. IV stresses: existing CONTRACTED 0.80 / BASE 1.00 / EXPANDED 1.20. Basis label on every scenario: `AT_GOVERNED_TIME_STOP` for LATE; `AT_SESSION_n` for EARLY/MID.

**Friction — `friction_model_v1` (replaces the 25 bps default as the active model; the bps model stays available by config).**

```
entry_cost = ask
s          = spread_fraction_mid at observation = (ask − bid) / ((ask + bid)/2)
exit_value = max(0, theoretical × (1 − min(s / 2, s_cap)))      s_cap config, initial 0.15
net_return = (exit_value − entry_cost) / entry_cost
```

Rationale: the round trip costs roughly the spread; entering at the ask pays half, exiting at the modelled bid pays the other half. Observed spreads in this book are 3–18%, so a 25 bps friction understates cost by an order of magnitude.

**Outputs per contract.** For each scenario: `scenario_spot_dollars`, `scenario_iv_fraction`, `remaining_years`, `theoretical_value_per_share`, `modelled_exit_value_per_share`, `net_return_fraction`, `scenario_basis` and `friction_assumption`. Headline fields on the assessment (LATE timing, BASE IV) are `payoff_flat_net_return_fraction`, `payoff_1sigma_net_return_fraction`, `payoff_2sigma_net_return_fraction`, `payoff_reachable_net_return_fraction`, `payoff_structural_net_return_fraction`, `payoff_invalidation_net_return_fraction`, plus `theta_and_friction_cost_to_time_stop_fraction = payoff_flat_net_return_fraction`. Unqualified legacy `payoff_*` names may exist only behind an explicit versioned adapter; dollars and return fractions may never share a field name.

The first-release exit haircut is a scenario assumption, not an observed future spread. Every result therefore carries `friction_assumption = CURRENT_SPREAD_PROXY_CAPPED`, the observed input spread, cap and model version. When the input spread falls outside the configured model domain, publish `applicability = FRICTION_OUT_OF_RANGE` and `INDETERMINATE`; do not manufacture confidence by silently applying the cap.

**Worked example (tester can reproduce with any BS calculator).** S₀ = 100, CALL K = 105, 30 calendar DTE, σ = 0.30, r = 0.04, q = 0. Entry theoretical 1.662; bid 1.562 / ask 1.762 → s = 0.1203; entry_cost 1.762; exit haircut = min(0.0602, 0.15) = 6.02%. h = 5 sessions → 7 calendar days elapsed → T = 23/365.

| Scenario | S | Theoretical | Exit | Net return |
|---|---|---|---|---|
| FLAT | 100.00 | 1.269 | 1.193 | **−32.3%** |
| 1σ | 104.23 | 2.890 | 2.716 | +54.1% |
| 2σ | 108.45 | 5.397 | 5.072 | +187.8% |
| REACHABLE (k = 1.5) | 106.34 | 4.036 | 3.793 | **+115.3%** |
| STRUCTURAL | 112.00 | 8.098 | 7.610 | +331.9% |
| INVALIDATION | 97.00 | 0.610 | 0.573 | −67.5% |

The structural scenario's +332% is exactly the number the old pipeline headlined; the reachable +115% is what the vol budget says is a scenario boundary; the flat −32% is what five sessions of nothing costs. PUT mirror (K = 95): entry 1.333; flat 1.021; 1σ (S = 95.77) 2.383; reachable (S = 93.66) 3.413 — symmetric behaviour, confirming the sign convention.

**Oracle.** Fixture values above within ±0.5% (differences arise only from N(·) implementation). Property: raising S raises CALL theoretical and lowers PUT theoretical; raising s never raises net_return.

---

## ALG-05 Monetisability policy — `scenario-monetisability-policy-v1`

**Inputs.** `payoff_reachable_net_return_fraction` (LATE, BASE IV), assessment applicability, `profit_floor` f (governed config; suggested candidate 0.25, not active until ACK approves it), data availability.

```
if any required input missing or IV_UNAVAILABLE       → NOT_EVALUATED_DATA_MISSING
elif applicability in {HORIZON_LIMITED,
                       FRICTION_OUT_OF_RANGE}          → INDETERMINATE (named reason)
elif payoff_reachable_net_return_fraction ≥ f         → SCENARIO_MONETISABLE
elif payoff_reachable_net_return_fraction > 0         → SCENARIO_LIMITED
else                                                   → NOT_CURRENTLY_MONETISABLE
```

Every state carries `authority = ADVISORY_ONLY`, `policy_version`, `scenario_id`, `profit_floor_applied`, `friction_model_version`, `applicability` and a named reason. No monetisability state removes a thesis, family or assessment from the governed opportunity record. `monetisability_state_structural` is computed with the same rule on `payoff_structural_net_return_fraction` and shown as disclosure only.

**Worked example.** Above: `payoff_reachable_net_return_fraction = 1.153` ≥ 0.25 → `SCENARIO_MONETISABLE`. A spread outside the governed friction-model domain produces `INDETERMINATE`, even if the capped arithmetic would be positive. The deep-OTM fixture S₀ = 100, K = 115 is retained to exercise `SCENARIO_LIMITED` only when its quote and friction inputs are inside that domain.

---

## ALG-06 Deterministic utility — `deterministic_utility_v2` (replaces `MEDIAN_FAVOURABLE_RETURN_PLUS_WORST_ADVERSE_RETURN` as the active formula)

**Why change.** The existing utility (`deterministic_option_valuation.py` ~L400–420) takes the median over the *structural-target* path. With reach ratios of 3–4× that rewards the contracts whose target is least reachable. The v2 utility uses the reachable path and keeps the adverse term.

```
U = median( net_return over FAVOURABLE_REACHABLE × {EARLY, MID, LATE} × {0.8, 1.0, 1.2} )
    + min( net_return over ADVERSE_INVALIDATION × timings × stresses )
    + w_flat × net_return(FLAT, LATE, BASE)          w_flat config, initial 0.5
```

The flat term penalises theta-and-friction cost so that two contracts with equal reachable payoff rank by what they cost to be wrong for h sessions. `ranking_score_kind = DETERMINISTIC_UTILITY`; `utility_is_probability = false`; the v1 formula is retained under `ranking_score_uncalibrated_v1` for one release so the replay diff is explicable.

**Applicability.** As today: `DATA_INSUFFICIENT` when no positive ask; `OUT_OF_DISTRIBUTION` when American-exercise materiality, corporate action or missing dividend yield; otherwise `DETERMINISTIC_ONLY`.

**Oracle.** On a replay of 20260911_115904 with the rate bridge, U is populated on every family with a positive ask; the rank correlation between U_v1 and U_v2 is reported (expected < 0.7 — that gap *is* the fix).

---

## ALG-07 Calibrated expected utility — `calibrated_utility_v2` (activates only after ALG-09 gate)

**Inputs.** From ALG-09: p_T = P(TARGET_FIRST), p_I = P(INVALIDATION_FIRST), p_O = 1 − p_T − p_I (TIMEOUT). From ALG-04: `payoff_reachable_net_return_fraction`, `payoff_invalidation_net_return_fraction`, `payoff_flat_net_return_fraction` (LATE, BASE).

```
EV = p_T × payoff_reachable_net_return_fraction
   + p_I × payoff_invalidation_net_return_fraction
   + p_O × payoff_flat_net_return_fraction
```

Published as `expected_net_return_calibrated` with `calibration_state = CALIBRATED`, model ID, `match_level`, `exact_n`. `ranking_score_kind = CALIBRATED_EXPECTED_UTILITY`. The existing `RankingWeights.calibrated_utility` (weighted sum of deterministic score, p_liquidity_3d, p_positive_return, p_target_before_invalidation, uncertainty) may be retained as `calibrated_utility_v1` but the EV above is the primary ranking number because it is in return units the trader can read.

**Timeout payoff assumption.** Using the flat scenario for TIMEOUT is conservative (a timeout with partial favourable drift would be worth more). Disclosed as `TIMEOUT_VALUED_AT_FLAT`.

---

## ALG-08 Outcome labels — `outcome_labels_v1` (WP4 and WP7B share this)

For each (ticker, decision session d, direction, h, budget e_h, k, invalidation I):

```
target_level  = S_d × (1 ± k e_h)     (ALG-02 with the point-in-time budget)
for session t = d+1 … d+h (XNYS):
    CALL: hit_target if high_t ≥ target_level ; hit_stop if low_t ≤ I
    PUT : hit_target if low_t  ≤ target_level ; hit_stop if high_t ≥ I
    if hit_target and hit_stop on the same session → AMBIGUOUS_TOUCH_ORDER
    elif hit_target → TARGET_FIRST, sessions_to_target = t − d
    elif hit_stop   → INVALIDATION_FIRST
end: TIMEOUT
```

`AMBIGUOUS_TOUCH_ORDER` is resolved to `TARGET_FIRST` or `INVALIDATION_FIRST` only when point-in-time intraday bars establish the order. An unresolved ambiguous observation is reported and excluded from the three-class probability denominator; it is never silently converted into a loss. Also record: MFE = max favourable excursion fraction, MAE = max adverse, terminal return at h, and for positions the option-level equivalents at 1/2/3/5/10/20 sessions where inside h. Inputs: daily OHLC from the canonical price store (`historical_prices.sqlite`) — closes-only labelling is **not** acceptable because stops are touched intraday.

**Point-in-time rule.** e_h and I used for the label are the values that existed at session d; a label may never use a later revision. Only `baseline_eligible = true` observations with reproducible code/config identity enter calibration data. Forced, replay, test and dirty-tree runs remain available for engineering analysis but are excluded from model fitting and performance claims.

---

## ALG-09 Probability calibration — `calibration_v1` (AVS-CAL-001)

**Key.** `hidden_state_label | phase | compression_bucket | direction | hold_bucket` where `compression_bucket` ∈ {LOW, MID, HIGH} by terciles of compression energy computed on the training partition only; `hold_bucket` ∈ {1–5, 6–10, 11–20}.

**Estimate.** For each key with n_exact labels: `p̂_exact(class) = count(class) / n_exact` for class ∈ {TARGET_FIRST, INVALIDATION_FIRST, TIMEOUT}.

**Hierarchical backoff with shrinkage.** Parent chain: drop `compression_bucket` → drop `phase` → drop `hidden_state_label` → `direction | hold_bucket` → `direction`.

```
p̂ = (n_exact × p̂_exact + κ × p̂_parent) / (n_exact + κ)       κ config, initial 50
```

applied recursively from the top of the chain down. Record `match_level` (0 = exact … 4 = direction only), `exact_n`, `parent_n`, `shrinkage_weight = κ / (n_exact + κ)`, `match_dims_used`. A key with n_exact < n_min (config, initial 200) reports the shrunk value; nothing is ever dropped silently.

**Partitions.** Time-ordered by decision session: train ≤ T₁, validation (T₁, T₂], test > T₂, with a **purge/embargo of 20 sessions** at each boundary so no label window straddles a partition (labels look up to 20 sessions ahead). Suggested T₁/T₂: 70% / 85% of the history by date.

**Metrics (per direction × hold_bucket stratum, on test).** The three mutually exclusive scoreable classes are TARGET_FIRST, INVALIDATION_FIRST and TIMEOUT. Report the multiclass Brier score and classwise metrics; ranking gates use TARGET_FIRST as the positive class.

```
Brier_multiclass = mean( Σ_c (p̂_c − 1[y=c])² / 3 )
Brier_base = the same score using the frozen training-stratum class rates
Brier_skill = 1 − Brier_multiclass / Brier_base
ECE_c = Σ_b (n_b / N) × | mean(1[y=c] in bin b) − mean(p̂_c in bin b) |  (10 fixed bins)
log_loss_multiclass = −mean(log(p̂_y)) with each p̂ clipped to [0.005, 0.995] and renormalised
ROC_AUC_target, PR_AUC_target and top_quintile_lift_target are computed for TARGET_FIRST
coverage = fraction of scoreable production rows whose key resolves at match_level ≤ 2
```

**Activation gate (from design v1.2).** coverage ≥ 0.60; overall classwise ECE maximum ≤ 0.10; stratum classwise ECE maximum ≤ 0.15 where held-out n ≥ 100; `Brier_skill > 0`; `ROC_AUC_target > 0.50`; `PR_AUC_target` exceeds the frozen training-stratum target base rate; and `top_quintile_lift_target > 1.0`. Bootstrap confidence intervals, sample sizes and class counts are reported even when not used as a hard threshold. Every threshold is governed configuration. Strata failing any test are marked `UNCALIBRATED` and the row uses ALG-06. A base-rate tie is a failure, not evidence of skill.

**Output.** `calibration_table.json`: `{key: {p_target_first, p_invalidation_first, p_timeout, n_exact, match_level, model_id, training_cutoff}}` plus a report with the reliability curve per stratum. Written in DOI's vocabulary (`p_target_before_invalidation` = p_T) so `canonical_data/dynamic_options_probability.py` consumes it without adaptation.

**What this answers.** If no stratum has p_T materially above its unconditional base rate after shrinkage, the thesis engine has no measurable directional edge at the vol-budget target, and the honest output is a rank driven by contract cost alone. That result is as valuable as the opposite one and must be reported, not tuned away.

---

## ALG-10 Forecast-volatility validation — `vol_validation_v1` (AVS-VAL-001)

For each (ticker, session d) with a Layer 3 forecast σ_f,h (annualised, horizon h ∈ {5, 10, 20}):

```
RV_h = sqrt( 252 / h × Σ_{t=d+1}^{d+h} ln(C_t / C_{t−1})² )        close-to-close, annualised
ratio_h = RV_h / σ_f,h
```

Aggregate per `hidden_state_label` bucket (and overall): median, IQR, n. Also `coverage_1σ = fraction of |ln(C_{d+h}/C_d)| ≤ σ_f,h × sqrt(h/252)` — should be ≈ 0.68 for an unbiased forecast under normality. Only baseline-eligible point-in-time forecasts enter fitting. Buckets below governed `minimum_validation_n` report diagnostics but cannot own an applied multiplier; they back off explicitly to the validated overall estimate or remain unvalidated.

**Bias multiplier.** `m_bucket = clip(median ratio on train, 0.5, 1.5)`; `m_overall` likewise. Validation passes when, on the time-ordered test partition with m applied: median ratio ∈ [0.90, 1.10] and coverage_1σ ∈ [0.60, 0.76]. Until it passes: m = 1.0, `validation_state = UNVALIDATED` on every dependent row (ALG-01, ALG-02, ALG-04).

**Interpretation.** If the median ratio is 0.75, the forecast is 33% too high, every reachable target is too far, and the cheap far-OTM contracts at the top of any rank are an artefact — which is precisely the AVS-RANK-001 concern. The multiplier fixes it at the source.

---

## ALG-11 Preferred-contract hysteresis — `hysteresis_v1`

```
incumbent U_i, challenger U_c (same family, both with observation_quality PASS)
switch if  U_c − U_i ≥ max( margin_abs, margin_rel × |U_i| )
           margin_abs config initial 0.05 (utility units of net return), margin_rel initial 0.10
immediate switch regardless of margin if incumbent is EXPIRED, identity MALFORMED, or DATA_DEFECT
```

Emit `PreferredContractSuperseded{prior, new, reason ∈ {MARGIN_EXCEEDED, EXPIRED, MALFORMED, DEFECT}, U_i, U_c}`. The canonical absolute margin is `0.05` net-return utility units; the earlier phrase "5 deterministic-utility points" is deprecated because it is unit-ambiguous. ACK must approve the value in the governed config manifest before activation.

---

## ALG-12 Quote validity, freshness and executability — `execution_quality_v1`

```
unavailable = bid is null or ask is null or provider timestamp is null
defect      = bid < 0 or ask < 0 or bid >= ask or a numeric field is unparsable
future_ts   = quote_provider_timestamp_utc > refresh_instant + clock_skew_tolerance
zero_bid    = bid == 0
two_sided   = bid > 0 and ask > bid
age         = refresh_instant − quote_provider_timestamp_utc
fresh       = 0 <= age <= F                  F config, current candidate 15 min
spread_fraction_mid = (ask − bid) / ((ask + bid)/2)
wide        = spread_fraction_mid > L        L config, current candidate 0.18

defect or future_ts          → EXECUTION_CROSSED_MARKET_DATA_DEFECT or EXECUTION_UNVALIDATED_INPUT
unavailable                  → EXECUTION_QUOTE_UNAVAILABLE
zero_bid                     → EXECUTION_ZERO_BID_MONITOR
not fresh                    → EXECUTION_QUOTE_STALE_MONITOR
wide                         → EXECUTION_WIDE_SPREAD_MONITOR
valid but outside authority  → EXECUTION_REVIEWABLE
otherwise                    → EXECUTION_EXECUTABLE_NOW

EXECUTION_EXECUTABLE_NOW requires run_condition == POSTOPEN_CONTRACT_REFRESH.
```

Order of evaluation: malformed/negative/crossed/future defect → unavailable → zero-bid → stale → wide → reviewable/executable. `refresh_window_state` ∈ {IN_PRIMARY_WINDOW, LATE_REFRESH, OUTSIDE_SESSION}. The `_utc_now()` substitution (`morning_gate.py:1891`) is removed; a missing provider timestamp is terminal for the current observation. These execution states never delete or invalidate the ticker thesis and never claim that a 1–20 session opportunity has expired.

---

## ALG-13 Capacity suggestion — `capacity_v1`

```
contract_cost_at_ask = ask × contract_multiplier
contracts_at_budget  = floor( desk_budget_amount / contract_cost_at_ask )
size_state = CONFIG_UNAVAILABLE if budget or multiplier missing/invalid
           = QUOTE_UNAVAILABLE  if ask missing or ≤ 0
           = BELOW_ONE_CONTRACT if contracts_at_budget == 0
           = AFFORDABLE otherwise
contracts_at_budget_if_capped (optional display) = floor( desk_budget_amount × horizon_cap_advisory × direction_factor_advisory / contract_cost_at_ask )
```

`horizon_cap_advisory` (from `horizon_routing`, 0.50/0.55/0.60) and `direction_factor_advisory` (0.5 when direction opposes the USMI sector list, else 1.0) are displayed and used **only** in the optional capped figure, never in `contracts_at_budget`. Property test: mutate every macro input → `contracts_at_budget` unchanged.

**Worked example.** Budget $1,500; ask $2.10 and governed multiplier 100 → cost $210 → 7 contracts, AFFORDABLE. Ask $16.00 → 0, BELOW_ONE_CONTRACT. A missing multiplier is never silently replaced by 100; it produces `CONFIG_UNAVAILABLE` with `config_missing_field = contract_multiplier`.

---

## ALG-14 Macro sector routing and scenario evaluation — `usmi_routing_v1`, `usmi_scenario_v1`

**Routing.** Read `options_monetisation.sector_routing.routing` from `extras.us_money_index.source_payload`. Build `routing_key` from GICS sector with industry-keyword overrides (the reference map is `map_routing()` in `dropbox/macro/coaching/desk_gate/desk_gate.py`; port it, do not re-derive). Root-cause groups for correlation display: OIL {XLE, XLI, XLY, XLB}, RATES {XLRE, XLF, XLU}, GROWTH {XLK, XLC}, DEFENSIVE {XLV, XLP}, INDEX.

```
alignment = UNAVAILABLE   if no packet or packet stale beyond its own freshness rule
          = UNCERTAIN     if the packet marks the route uncertain
          = SUPPORTIVE    if direction matches the route's preferred side
          = OPPOSED       if direction opposes it
          = NEUTRAL       otherwise
```

`usmi_alignment_reason` names the route and the packet ID. The join runs **after** `gics_sector`/`industry` are on the row (`morning_handoff_finalizer.py:765-780` ordering fix).

**Scenario evaluation.** For each scenario in `forward_triggers.scenarios` with `conditions_all = [{metric, op, value}]`: resolve each metric from the packet's observed metrics with its timestamp; evaluate `op ∈ {<, ≤, >, ≥, =, between}`; scenario satisfied iff all clauses true. Result: exactly one satisfied → that scenario ID (A/B/C); none → `UNRESOLVED` with the first failed clause and observed value; more than one → `MULTIPLE` listing them (a packet defect to report, not resolve); any metric missing → `UNRESOLVED` naming the metric. Context only; consumed by nothing that decides.

---

## ALG-15 Provider completeness — `provider_completeness_v1`

Provider completeness is assessed at two distinct grains; they may not be collapsed into a latest-timestamp test.

**Per ticker/chain.** A chain for session s is `PROVIDER_SESSION_COMPLETE` only when: (a) s is the last completed XNYS session; (b) the request explicitly used historical/completed-session mode; (c) the provider settlement delay elapsed; (d) the canonical underlying official close for the same ticker/session exists; (e) the chain's session-date coverage, provider-timestamp presence and configured late-session-watermark coverage pass their governed thresholds; and (f) the complete timestamp distribution `{min, median, p95, max}` is recorded. One quote at or after 16:00 ET can never prove chain completion. Failures produce `PROVIDER_SESSION_PARTIAL`, `PROVIDER_SESSION_NOT_SETTLED`, `PROVIDER_SESSION_DATE_MISMATCH` or `PROVIDER_SESSION_EVIDENCE_INSUFFICIENT` with named reasons. The ticker remains visible as a non-normal exception.

**Run level.** `normal_chain_fraction = complete_chains / chains_expected` and `official_close_fraction = closes_present / underlying_tickers_expected`. Initial candidate run thresholds are 0.95 and 0.99 respectively, governed and replay-tested before activation. A run below either threshold is not `NORMAL_COMPLETED_SESSION`; a run meeting them remains normal while its residual per-ticker exceptions remain reconciled and visible. Record both denominators, all state counts, threshold versions and `checked_at_utc` in `run_meta_v2.provider_completeness_evidence`.

---

## ALG-16 Identity and hashing — `identity_v1`

```
assessment_id     = sha256( canonical_json({thesis_id, occ_symbol, observation_dataset_id, calculation_version, evidence_cutoff_utc}) )
observation_dataset_id = sha256( canonical_json(normalized provider observation for that chain/session) )
macro packet id   = packet_id from the packet; packet_hash = sha256(file bytes)
run code identity = git commit hash + "-dirty" if the tree is dirty
```

`canonical_json` = sorted keys, no whitespace, UTF-8, ISO-8601 UTC timestamps with milliseconds. Provider rows are normalized to the canonical schema and deterministically sorted by OCC symbol and provider timestamp before hashing; transport order, fetch timestamp, request ID and JSON whitespace cannot change the observation identity. A separate raw-payload hash may be retained for forensic provenance. Changing any economic observation component changes the ID; changing transport-only metadata does not. The tester checks both properties with one-field mutations.

---

## Version register

| Algorithm | Version tag | Replaces | Written to |
|---|---|---|---|
| ALG-01 | `vol_budget_v2` | differenced L3 fields | `volatility_budget_v2` |
| ALG-02 | `reachability_v1` | — | `reachability_assessment_v1` |
| ALG-03 | `xnys_bridge_v1` | implicit DTE | assessment `calendar_version` |
| ALG-04 | `scenario_valuation_v2` + `friction_model_v1` | 2-path grid, 25 bps friction | `contract_assessment_v2` |
| ALG-05 | `scenario-monetisability-policy-v1` | intrinsic-at-structural | `monetisability_state` |
| ALG-06 | `deterministic_utility_v2` | median-favourable + worst-adverse (structural) | `ranking_score` |
| ALG-07 | `calibrated_utility_v2` | — | `expected_net_return_calibrated` |
| ALG-08 | `outcome_labels_v1` | `win_rate_20d = P(ret > 0)` | calibration inputs, `outcome_record_v2`, ambiguity count |
| ALG-09 | `calibration_v1` | pooled bucket, dropped dims | `calibration_table.json` |
| ALG-10 | `vol_validation_v1` | — | `bias_multiplier`, `validation_state` |
| ALG-11 | `hysteresis_v1` | none (flips freely) | `preferred_contract_decision_v2` |
| ALG-12 | `execution_quality_v1` | OLM classifier with `_utc_now()` fallback | `execution_state`, lifecycle |
| ALG-13 | `capacity_v1` | router size 1.0 / caps NOT_APPLIED | `capacity_suggestion_v1` |
| ALG-14 | `usmi_routing_v1`, `usmi_scenario_v1` | empty-sector join, no evaluator | `macro_ticker_context_v2` |
| ALG-15 | `provider_completeness_v1` | wall clock | `run_meta_v2` |
| ALG-16 | `identity_v1` | — | all contracts |

## Config keys introduced (all into `config/governed_constants_v1.json`)

`sigma_multiple` 1.5 · `bias_multiplier` 1.0 · `friction.s_cap` 0.15 (candidate; replay approval required) · `friction.model` `friction_model_v1` · `profit_floor` 0.25 (candidate; ACK approval required) · `utility.w_flat` 0.5 · `iv_stress` {0.8, 1.0, 1.2} · `hysteresis.margin_abs` 0.05 · `hysteresis.margin_rel` 0.10 · `freshness_minutes` 15 · `clock_skew_tolerance_minutes` 5 · `spread_executable_limit` 0.18 · `calibration.kappa` 50 · `calibration.n_min` 200 · `calibration.embargo_sessions` 20 · `calibration.gate` {coverage 0.60, ece 0.10, ece_stratum 0.15, n_stratum 100, brier_skill_min_exclusive 0.0, roc_auc_min_exclusive 0.50, top_quintile_lift_min_exclusive 1.0} · `vol_validation.minimum_validation_n` 200 · `vol_validation.pass` {ratio [0.90, 1.10], coverage [0.60, 0.76]} · `provider_completeness` {normal_chain_fraction 0.95, official_close_fraction 0.99, per_chain thresholds replay-approved} · `desk_budget_amount` (ACK) · `refresh_window` 09:35–09:45 ET.

## Confidence

| Claim | Confidence |
|---|---|
| ALG-04 worked-example values are numerically correct | 0.98 (computed; N(·) implementation differences ≤ 0.5%) |
| Reusing the existing DOI grid/BS code and extending the paths is the right integration | 0.9 |
| `friction_model_v1` is a fair first-release cost model for this book | 0.8 (half-spread each way is standard; s_cap value is a judgement) |
| ALG-09's shrinkage/embargo design will produce a usable table from 5.9M observations | 0.75 (depends on how many keys have n ≥ 200 — unknown until run) |
| ALG-10's pass band [0.90, 1.10] is achievable for HAR-RV on this universe | 0.5 (realised-vol forecasts commonly run high; the multiplier exists for that reason) |

## v1.2 correction record

This revision aligns the annex with solution design v1.2. It removes the unsupported matched-horizon forecast branch; fixes calendar duration arithmetic; prevents expiry-inside-hold from becoming a false non-monetisable conclusion; separates dollar and return units; makes same-session target/stop order explicit; strengthens calibration skill gates; completes quote-defect states; uses the governed contract multiplier; replaces latest-quote provider finality with chain-wide and run-level evidence; and hashes normalized observations rather than transport formatting.

