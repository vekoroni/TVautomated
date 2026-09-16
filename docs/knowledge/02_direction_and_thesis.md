# 02 — Direction and Thesis

Status: **Draft** · Capability: O1 Directional thesis · Context: C3 Market Structure, C5 Thesis

## Question this method answers

> What exactly do we believe (direction), where are we wrong (invalidation), where do we take profit (target), for how long (hold) — and does the evidence support it?

## Principles

1. **A structural pattern is a hypothesis, not a signal.** Wyckoff phases, trend labels and breakouts define *candidate* theses. Whether they carry an edge is an empirical question answered by the evidence packet (note 01) — never by the pattern's name.
2. **Direction must be measurable against outcomes.** Every thesis records a direction state derived from evidence, so hit rates can be compared by state.
3. **The thesis is decided before any instrument is chosen.** Hold, invalidation and target are thesis properties; the contract is chosen to fit them, never the reverse (removes the DTE → horizon → DTE loop).
4. **No invented levels.** A level used for valuation must come from market structure or from a stated statistical rule; formula fallbacks (e.g. 3R) are not targets.

## Method

### Direction state
Given candidate direction d from structure and evidence packet for (state, d, h):
- `edge = p_target_first − p_stop_first` (or expected terminal return when no target), with its uncertainty interval.
- `SUPPORTED` if the lower bound > 0; `OPPOSED` if the upper bound < 0; `UNSUPPORTED` if the interval straddles 0; `INSUFFICIENT_EVIDENCE` if no packet or n_eff below minimum.
- Never auto-flip direction. Opposed evidence reduces valuation (note 03) and is visible; the trader decides.

Testing across many tickers and states is a **multiple-comparison** problem: expect false "SUPPORTED" states by chance. Control with shrinkage (note 01) and validate out of sample (note 06).

### Invalidation
- Structural level that, if traded through, falsifies the thesis (e.g. the low of an accumulation range for a bullish thesis).
- Must be on the correct side of reference price; stop distance should be meaningful relative to volatility — record `stop_distance_in_atr` and `stop_distance_in_sigma_h`.
- Missing invalidation → thesis incomplete (hard exclusion in the decision tree).

### Target
- Structural level (prior range extreme, measured move, significant volume node) on the correct side and > 0.
- If none exists, **no target**: valuation uses stop and timeout exits only (note 03). An optional *reference* level (spot ± k × expected move) may be shown but never valued.
- Record `target_distance_in_sigma_h`; distances far beyond the expected move are allowed but their low first-passage probability must come from evidence, not assumption.

### Hold horizon
- Candidate holds H ∈ {5, 10, 20} sessions (policy set).
- Choose h* maximising the **lower bound of expected underlying payoff per unit risk** from the evidence packet; if no horizon has a packet → thesis not valuable.
- Options must then satisfy `dte_sessions ≥ h* + exit_buffer` (note 03).

## Output contract (Thesis aggregate)

`thesis_id, ticker, evidence_session, reference_price, direction, direction_state, edge, edge_ci, invalidation_price, stop_distance_sigma_h, target_state (STRUCTURAL | NONE), target_price, target_distance_sigma_h, hold_sessions, evidence_packet_id, structure_assessment_id, formula_version`. Frozen once published.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Direction "CONFIRMED" without checking evidence | 65% of rows oppose their evidence scores |
| Evidence that is really the same signal twice | Auction-driven "actuarial" vote + trend/VWAP "price flow" vote |
| Default to CALL on neutral | `_determine_direction` |
| Hold read from selected contract | 100% `DTE_FALLBACK_LOW_CONFIDENCE` |
| Formula targets treated as structure | 3R fallback; negative PUT targets |

## Validation (gate G4)

1. Hit rate by `direction_state` on matured outcomes: SUPPORTED > UNSUPPORTED > OPPOSED, SUPPORTED significantly above base rate (binomial test with n_eff, Wilson CI).
2. Chosen hold vs alternative holds: realised payoff per unit risk higher for h* on average.
3. Structural targets: realised first-passage frequency within the predicted CI.

## References

- Wyckoff method texts are descriptive, not statistical — treat as hypothesis generators (e.g. Pruden, H. *The Three Skills of Top Trading*, 2007) [verify]
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley — meta-labelling: separate the side decision from the size/confidence decision [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). …and the Cross-Section of Expected Returns. *Review of Financial Studies* — multiple testing in finance [verify]
