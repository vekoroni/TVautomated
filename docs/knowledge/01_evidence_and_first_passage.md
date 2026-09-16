# 01 — Evidence and First-Passage Probabilities

Status: **Draft** · Capabilities: O1 Directional thesis, O7 Learning loop · Context: C4 Evidence

## Question this method answers

> Historically, from market states like today's, how often did price reach the thesis target before the invalidation level within the hold period, how often the reverse, and what happened otherwise — and how sure are we?

## Established method

### 1. Labels: the triple-barrier method
For each historical observation (ticker, date t) define three barriers relative to the entry close S_t:
- **upper barrier** (target in the thesis direction),
- **lower barrier** (invalidation),
- **vertical barrier** (hold horizon h sessions).

The label is whichever barrier is touched first; on the vertical barrier record the terminal return. This is the standard labelling approach for path-dependent trading outcomes (López de Prado, *Advances in Financial Machine Learning*, 2018, ch. 3 [verify]).

Rules:
- Barriers are **per observation**, set the same way the live thesis sets them (e.g. in units of that stock's volatility or at structural levels), not fixed % grids.
- Use intraday high/low for touches; if both barriers are touched on the same bar the order is unknown → label `AMBIGUOUS` and exclude or count conservatively, recording the count.
- Stops fill at the **worse of the barrier and the next open** (gap risk).
- Store the **session of first touch** k, not only the outcome, so valuation can price the exit on the correct day.

### 2. Conditioning: state definition
The "state" is the set of features describing today (structure phase, trend, volatility regime, etc.).
- One state key, one query library, used by every consumer.
- Every state dimension must be **known at time t** (trailing windows only; no forward-filled or revised data).
- Prefer few, well-populated states over many sparse ones; report sample per state.

### 3. Data hygiene before any statistic
- **Split / corporate-action adjusted** prices; returns that imply > ±100% in a session or implausible jumps are data errors until proven otherwise → reject or winsorise with a logged count.
- **Point-in-time universe including delisted tickers** (survivorship bias inflates historical results).
- **Label as-of date**: an observation is usable only once its horizon has matured before the evidence date.
- Use **medians and quantiles**, not means, for return summaries unless outliers are demonstrably clean.

### 4. Overlapping labels and effective sample size
Daily observations with 10–20 session horizons overlap heavily, and many tickers move together on the same dates. Treating them as independent overstates confidence.
- Count **effective samples** as independent time blocks (e.g. distinct weeks or non-overlapping horizon windows) across the pooled observations, not rows.
- Alternative: weight each label by its **average uniqueness** (inverse of how many concurrent labels overlap it) [López de Prado 2018, ch. 4, verify].

### 5. Probability estimates with uncertainty
- Outcome counts per state → **Dirichlet / multinomial** (target-first, stop-first, timeout) or Beta-binomial for binary outcomes.
- **Shrink toward a pooled prior** (empirical Bayes): p = (n_eff · p_state + k · p_prior) / (n_eff + k), where k is chosen by out-of-sample likelihood.
- Uncertainty: posterior draws, or a **block bootstrap** over time blocks (stationary bootstrap: Politis & Romano, 1994 [verify]).
- Binary proportions: **Wilson score interval** is preferred to the normal approximation for small samples.

### 6. Calibration
A probability is only a probability if it is calibrated out of sample.
- **Reliability diagram**: bucket predicted probabilities; compare with realised frequencies.
- **Brier score** and **log loss** against a baseline (unconditional base rate for the same horizon and barrier distances).
- A state model that does not beat the unconditional base rate out of sample carries **no evidence**, whatever its in-sample numbers.

## Output contract (evidence packet)

Per state × direction × horizon × barrier setting:
`p_target_first_by_session[k]`, `p_stop_first_by_session[k]`, `p_timeout`, `timeout_return_quantiles`, `n_rows`, `n_eff`, `posterior_draws or CI`, `prior_weight`, `calibration_brier_oos`, `baseline_brier_oos`, `data_as_of`, `label_as_of`, `formula_version`.
Missing or insufficient evidence → packet `null` with reason (rule R1), never a default probability.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Uncleaned outliers corrupt means | Actuarial v7: 20d return max 46.9M, mean 72 vs median 0.0004 |
| Rows treated as independent | Confidence = 1.0 on every row |
| Probabilities read at snapped grid levels, payoff at exact levels | EV3 grid snapping |
| Stale labels presented as current | Last mature label ~10 weeks before run |
| Default probability when no match | Cache `no_match` → 0.52 |
| Hand-set multipliers and calibration weights | Intraday multipliers 0.4–2.5× |

## Validation (gate G4)

1. Walk-forward (purged, with embargo — see note 06): out-of-sample Brier/log loss of the state model **beats the base rate** for each horizon.
2. Reliability: realised frequency within the CI of predicted probability in every populated bucket.
3. Stability: probabilities for the same state do not swing beyond their CI between monthly refits.

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. — triple-barrier labels, sample uniqueness, purged CV [verify]
- Politis, D. & Romano, J. (1994). The stationary bootstrap. *Journal of the American Statistical Association* [verify]
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA* [verify]
- Brier, G. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review* [verify]
