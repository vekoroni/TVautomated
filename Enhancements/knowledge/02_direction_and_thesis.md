# 02 — Direction and Thesis

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capability: O1 Directional thesis · Contexts: **C3 Market Structure** (candidate geometries), **C5 Thesis** · Governing: spec §7, §9

## Question this method answers

> What exactly do we believe (direction), where are we wrong (invalidation), where do we take profit (target, if any), over which 1–20 session window and with what resolution timing — and how strongly does the evidence support it?

## Principles

1. **A structural pattern is a hypothesis, not a signal.** Wyckoff phases, trend labels and breakouts define *candidate geometries*. Whether they carry an edge is an empirical question answered by the evidence packet (note 01) — never by the pattern's name.
2. **Direction state is measured and descriptive, not a gate.** Every thesis records a direction state so outcomes can be compared by state; weak or opposing evidence lowers valuation and rank, it does not drop the thesis (spec S1).
3. **The thesis is decided before any instrument is generated.** Window, invalidation and target are thesis properties; instruments are generated to express them and each carries its own last exit session — the thesis is never shortened to fit a contract.
4. **No invented levels.** A level used for evidence or valuation comes from market structure; formula fallbacks (3R, expected-move targets, reference levels) are never targets or barriers.
5. **No fixed holding bucket.** The thesis owns a 1–20 session opportunity window and a resolution distribution, not a 5/10/20 hold.

## Method

### Candidate geometries (C3)
For each candidate direction, Market Structure proposes one or more geometries: structural invalidation (required, correct side of reference), structural target (`LEVEL`) or `NONE`, distances in σ, derivation rule. Evidence produces a packet per geometry (note 01).

### Underlying expectancy in volatility units
For each geometry with a packet (probabilities by Day 20, or at the window end):

```
target_state = LEVEL:
  expectancy = P_target_first × target_distance_σ
             − P_stop_first   × invalidation_distance_σ
             + E[unresolved return in σ] × P_timeout

target_state = NONE:
  expectancy = − P_stop_first × invalidation_distance_σ
             + E[unresolved return in σ over the full timeout distribution] × P_timeout
```

Evaluated across the packet's bootstrap draws to give a lower and upper bound.

### Direction state (per geometry, descriptive)
- `SUPPORTED` if the expectancy lower bound > 0;
- `OPPOSED` if the upper bound < 0;
- `UNSUPPORTED` if the interval straddles 0;
- `INSUFFICIENT_EVIDENCE` if the packet is null.

Never auto-flip direction. A structurally proposed opposite direction is its own candidate geometry.

Testing across many tickers and states is a **multiple-comparison** problem: expect false "SUPPORTED" states by chance. Control with shrinkage (note 01) and validate out of sample (note 06).

### Geometry selection (R-H; authority `IMPLEMENTED_FOR_REPLICATION`)
- Select the geometry with the **highest lower-bound expectancy** among geometries with usable evidence (any state except `INSUFFICIENT_EVIDENCE`); tie-break structural priority of the derivation rule, then geometry id.
- Choosing by target probability alone is forbidden — it biases towards the nearest target.
- The rule uses underlying evidence only (no option prices, EV or rank).
- All geometries insufficient → thesis published as `NOT_VALUED` (recorded; underlying outcome still matures).
- To be confirmed by replication R4 before production authority.

### Invalidation
- Structural level that, if traded through, falsifies the thesis (e.g. the low of an accumulation range for a bullish thesis).
- Correct side of reference price; record `stop_distance_in_atr` and `stop_distance_sigma`.
- Missing invalidation → `INCOMPLETE_THESIS` (the only thesis-level exclusion; it cannot be valued).

### Target
- Structural level (prior range extreme, measured move, significant volume node) on the correct side and > 0 → `target_state = LEVEL`.
- Otherwise `target_state = NONE`: evidence and valuation use stop and forced-exit paths only. A volatility reference level may be displayed under a different name, never as a target or barrier.
- Distances far beyond the expected move are allowed; their low first-passage probability must come from evidence, not assumption.

### Window and resolution timing
- `trade_window` = sessions 1–20 from `window_start_session` (Day 1 = first session after the evidence session).
- Resolution distribution from the packet: expected and median resolution session, quantiles (e.g. q25, q75). These describe timing; they do not shorten the window.
- Earlier time stops are **expression exit policies** valued in note 03, not thesis properties.

### Thesis identity and supersession
- Same thesis while ticker, direction, invalidation (within tolerance), target (within tolerance) are unchanged and the thesis is unresolved; re-publishing it creates no new version.
- Genuine change (levels beyond tolerance, direction state change, better-supported geometry) → new version with `supersedes_thesis_id` that **inherits `window_start_session`**.
- A new window clock starts only after the previous thesis resolved (target, stop, invalidation or timeout). Superseded versions still mature and are validated.
- Tolerances are configuration (spec Appendix B).

## Output contract (Thesis aggregate)

`thesis_id, thesis_version, supersedes_thesis_id, ticker, evidence_session, window_start_session, reference_price, direction, direction_state, geometry_id, edge (expectancy), edge_ci, invalidation_price, stop_distance_sigma, target_state (LEVEL | NONE), target_price, target_distance_sigma, trade_window_min_sessions = 1, trade_window_max_sessions = 20, expected_resolution_session, median_resolution_session, resolution_session_quantiles, evidence_packet_id, structure_assessment_id, formula_version, configuration_versions`. Frozen once published.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Direction "CONFIRMED" without checking evidence | 65% of rows oppose their evidence scores |
| Evidence that is really the same signal twice | Auction-driven "actuarial" vote + trend/VWAP "price flow" vote |
| Default to CALL on neutral | `_determine_direction` |
| Hold read from selected contract | 100% `DTE_FALLBACK_LOW_CONFIDENCE` (DM-38) |
| Formula targets treated as structure | 3R fallback; negative PUT targets |
| ATR fallback stop presented as structural | `structural_stop_source=ATR_FALLBACK` on 1,504 rows |

## Validation (gate G4; replication R4)

1. Outcomes by `direction_state` on matured theses: SUPPORTED > UNSUPPORTED > OPPOSED in realised expectancy; SUPPORTED significantly above base rate (block-bootstrap intervals with n_eff).
2. Geometry selection (R-H) vs alternatives (nearest target, highest probability, structural priority only): realised underlying expectancy per unit risk higher for the R-H choice, out of sample.
3. Timing: realised resolution sessions consistent with the predicted resolution distribution.
4. Structural targets: realised first-passage frequency within the predicted interval.
5. Supersession: no restarted clocks in the ledger; superseded versions matured.

## References

- Wyckoff method texts are descriptive, not statistical — treat as hypothesis generators (e.g. Pruden, H. *The Three Skills of Top Trading*, 2007) [verify]
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley — meta-labelling: separate the side decision from the size/confidence decision [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). …and the Cross-Section of Expected Returns. *Review of Financial Studies* — multiple testing in finance [verify]
