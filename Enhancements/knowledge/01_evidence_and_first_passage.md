# 01 — Evidence and First-Passage Probabilities

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capabilities: O1 Directional thesis, O7 Learning loop · Context: **C4 Evidence** (inputs from C3 Market Structure, C2 point-in-time universe) · Governing: spec §8

## Question this method answers

> Historically, across the point-in-time market universe, from states like today's and for a given candidate geometry (target and invalidation distances), how often — and **on which session within the 1–20 session window** — did price reach the target first, the invalidation first, or neither; and how sure are we?

AVSHUNTER's own decision outcomes are an additional calibration source (C13), not the base sample.

## Established method

### 1. Labels: first passage over the 1–20 session window
For each historical observation (ticker, date t) and each candidate geometry supplied by Market Structure (spec §7), define relative to the entry close S_t:
- **target barrier** at the geometry's exact target distance (absent when `target_state = NONE`),
- **invalidation barrier** at the geometry's exact invalidation distance,
- **window end** at session 20.

Record the **session of first touch** k (1..20) and which barrier was touched; if neither, the path is unresolved at 20 and its return path is kept. This is the triple-barrier idea (López de Prado, *Advances in Financial Machine Learning*, 2018, ch. 3 [verify]) extended to preserve time-to-event.

Rules:
- Barriers are **per observation at the geometry's exact distances** (in that stock's volatility units or at structural levels), never snapped to a grid.
- Keep a **path store** (daily open/high/low/close for sessions 1..20 after each state date) so first passage can be evaluated for any geometry without precomputed fixed-horizon labels.
- Use intraday high/low for touches; if both barriers are touched in the same session the order is unknown → `AMBIGUOUS`, counted conservatively as stop-first for estimation, with the count recorded.
- Stops fill at the **worse of the barrier and that session's open** (gap risk).
- BEAR observations use mirrored barriers and mirrored returns (spec Invariant D).

### 2. Conditioning: state definition
The "state" is the set of features describing today (structure phase, trend, volatility regime, etc.).
- One state definition, one query library, used by every consumer.
- Every state dimension must be **known at time t** (trailing windows only; no forward-filled or revised data).
- Prefer few, well-populated states over many sparse ones; report sample per state.
- A dimension is added only if it shows measured out-of-sample lift (note 06).

### 3. Data hygiene before any statistic (spec Invariant E)
- **Split / corporate-action adjusted** prices.
- Returns that imply implausible jumps (e.g. > ±100% in a session) are data errors until proven otherwise → **excluded with a recorded reason**; never winsorised or capped silently, never kept.
- **Point-in-time universe including delisted tickers** (survivorship bias inflates historical results).
- **Label maturity**: an observation is usable only once its full 20-session window has matured before the evidence session.
- Use **medians and quantiles** for return summaries.

### 4. Overlapping labels and effective sample size
Daily observations with up to 20-session windows overlap heavily, and many tickers move together on the same dates. Treating them as independent overstates confidence.
- Count **effective samples** as independent time blocks (e.g. distinct weeks) across the pooled observations, not rows; never sum `n_eff` across correlated fallback states.
- Alternative: weight each label by its **average uniqueness** [López de Prado 2018, ch. 4, verify].

### 5. Estimation: competing risks in discrete time
Target-first, stop-first and still-unresolved are **competing states through time**. Estimating 20 separate per-session frequencies is sparse and unstable. Use a competing-risks survival formulation:

- **Cumulative incidence functions** CIF_U(k) and CIF_L(k) for target-first and stop-first by session k = 1..20, and survival S(k) = 1 − CIF_U(k) − CIF_L(k) (non-parametric **Aalen-Johansen** estimator, or a **discrete-time cause-specific hazard** model) (Kalbfleisch & Prentice, *The Statistical Analysis of Failure Time Data*; Aalen & Johansen, 1978 [verify]).
- Per-session incidence q_U(k) = CIF_U(k) − CIF_U(k−1), q_L(k) likewise.
- **Shrinkage** of cause-specific hazards toward pooled (less specific) states when the specific state is sparse (empirical Bayes; weight chosen by out-of-sample likelihood).
- **Uncertainty**: **block bootstrap** over time blocks (stationary bootstrap: Politis & Romano, 1994 [verify]), giving intervals for every CIF value and for derived expectancy.
- **Unresolved-path returns**: for each session F ≤ 20, keep the distribution of returns of paths still unresolved at F (needed for forced exits in valuation, note 03).
- Binary summaries only (e.g. overall target-first by Day 20): Wilson score interval may be reported alongside.

### 6. Calibration — whether and when
A probability is only a probability if it is calibrated out of sample, **in both outcome and timing**.
- **Reliability** of predicted CIF_U(k), CIF_L(k) at checkpoints (e.g. sessions 5, 10, 20) against realised cumulative frequencies.
- **Brier score** at checkpoints and an **integrated Brier score** over sessions 1–20 (Graf et al., 1999 [verify]), plus log loss, against the unconditional base rate for the same geometry distances.
- A state model that does not beat the unconditional base rate out of sample carries **no evidence**, whatever its in-sample numbers.

## Output contract (EvidencePacket, one per candidate geometry)

`evidence_packet_id`, `geometry_id`, `cumulative_incidence_target_by_session[1..20]`, `cumulative_incidence_stop_by_session[1..20]`, `survival_unresolved_by_session[1..20]`, `p_target_first_by_day20`, `p_stop_first_by_day20`, `p_timeout_day20`, `unresolved_return_distribution_by_session`, `time_to_target_distribution`, `time_to_stop_distribution`, `n_rows`, `n_eff`, `bootstrap intervals`, `shrinkage/prior information`, `ambiguous_count`, `calibration (whether and when, out of sample)`, `baseline scores`, `sample_definition`, `data_as_of`, `label_as_of`, `formula_version`.

Invariants: CIFs non-decreasing; CIF_U + CIF_L + S = 1 at every session; `target_state = NONE` → CIF_U ≡ 0.
Missing or insufficient evidence → packet `null`, `INSUFFICIENT_EVIDENCE` with reason (spec Invariant B), never a default probability.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Uncleaned outliers corrupt means | Actuarial v7: 20d return max 46.9M, mean 72 vs median 0.0004 |
| Rows treated as independent | Confidence = 1.0 on every row |
| Probabilities read at snapped grid levels, payoff at exact levels | EV3 grid snapping |
| Fixed 5/10/20 horizon labels only; no time-to-event | Actuarial v7, EV3 model limits |
| Stale labels presented as current | Last mature label ~10 weeks before run |
| Default probability when no match | Cache `no_match` → 0.52 |
| Hand-set multipliers and calibration weights | Intraday multipliers 0.4–2.5× |

## Validation (gate G4; replication R4)

1. Walk-forward (purged, with embargo — note 06): out-of-sample integrated Brier / log loss of the state model **beats the base rate** for the same geometry distances.
2. Reliability of cumulative incidence at session checkpoints: realised frequencies within predicted intervals in every populated bucket (timing calibration).
3. Stability: CIFs for the same state do not swing beyond their intervals between monthly refits.
4. Symmetry: mirrored price series give mirrored BULL/BEAR packets.

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley — triple-barrier labels, sample uniqueness, purged CV [verify]
- Kalbfleisch, J. & Prentice, R. (2002). *The Statistical Analysis of Failure Time Data*, 2nd ed. Wiley — competing risks, cumulative incidence [verify]
- Aalen, O. & Johansen, S. (1978). An empirical transition matrix for non-homogeneous Markov chains based on censored observations. *Scandinavian Journal of Statistics* [verify]
- Graf, E., Schmoor, C., Sauerbrei, W. & Schumacher, M. (1999). Assessment and comparison of prognostic classification schemes for survival data. *Statistics in Medicine* — integrated Brier score [verify]
- Politis, D. & Romano, J. (1994). The stationary bootstrap. *Journal of the American Statistical Association* [verify]
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA* [verify]
- Brier, G. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review* [verify]
