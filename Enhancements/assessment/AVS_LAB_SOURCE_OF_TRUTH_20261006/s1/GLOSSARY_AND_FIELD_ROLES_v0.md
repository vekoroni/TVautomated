# S1: glossary of core facts and field-role registry (v0, draft for ACK review)

**Status:** draft, written from the S0 baseline and the four audits. No code has been changed.
**Purpose:** E03, E28 and recurrence controls K-1 / K-2. The glossary says what each fact **means**, its **unit**, its **owner** and the **legitimate different measures**. The registry says which fields may **decide**, which **support**, and which are **audit only**. In S2 the registry becomes a versioned config file plus a test that fails if a decision, rank or primary-view reader uses a field outside its role.

**Basis (ACK E02, 6 Oct):** the ticker assessment comes first and flows into the option assessment. The business buys the ticker's move with long shares, long calls, long puts, or combinations.

---

## 1. Glossary

### 1.1 Ticker assessment
| Fact | Meaning | Unit | Owner (module) | Canonical field (proposed) | Legitimate different measures (keep, labelled) |
|---|---|---|---|---|---|
| Direction | Governed side of the ticker thesis | BULL / BEAR / UNRESOLVED | `contracts/direction_governance.resolve_governed_direction` | `direction` (governed) | Evidence scores per side; macro, bond and catalyst biases are **different concepts**, never trade direction |
| Setup | The structural setup that qualified the ticker (lane) | timeframe + signal + state | `domain/structure_behaviour/trade_lane.py` | `trade_lane`, `trade_lane_setup`, `trade_lane_side` | The other live setups on the ticker (supporting evidence) |
| Thesis event | The event whose geometry drives the move estimate | timeframe + signal | Discovery thesis fields | `thesis_event*` | **Must be traceable to the lane setup (E06)**. The S0 finding on BLDR and CENX is under S1 trace |
| Invalidation | Price that proves the thesis wrong, on the trade side | price, underlying | OI `_ev3_handoff_fields` (`invalidation_spot`) | `invalidation_spot` + `invalidation_basis` | Structural invalidation used by EV3 (audit) |

### 1.2 Three targets (all underlying prices)
| Target | Meaning | Owner | Canonical field | Must not be substituted for |
|---|---|---|---|---|
| Structural reference | The setup-derived level the structure points to | Discovery thesis geometry | `anticipated_structural_level` (from `thesis_outcome_level`) | Either of the others |
| Volatility-reachable | The level a k-σ move reaches by a stated time | `domain/anticipated_move.reach_by` | `anticipated_reachable_level` (+ sessions) | — |
| Anticipated level | The nearer of the two: what the move is valued at | `domain/anticipated_move.py` | `anticipated_level` (with `_basis`); `anticipated_level_q50` = the level reachable by the q50 time | — |

**Classified in S1** (`S1_SETUP_LINEAGE_AND_OPEN_CHECKS.md` §1): the "Discovery target" (`target_price` / `structural_target`, labelled DISCOVERY_TARGET) is the **extreme of the prior 40-bar range** (`wyckoff_phase_validator.py:137–144`, PRIOR_RANGE_EXTREME). It is a legitimate fourth measure: **range extreme / first objective**.
- **Proposed name:** `prior_range_extreme`, role SUPPORTING.
- **Defect:** it drives strike selection (OI :5594) and monetisability, while the move is valued at the anticipated level. Strikes must be chosen against the level the value is computed at.

**Also from S1 (RC5):** the anticipated level must come from the **lane-setting setup**, or from a thesis event explicitly linked to it. Today a separate 1d event is used on 32 of 51 GOs.

### 1.3 Four clocks
| Clock | Meaning | Unit | Owner | Canonical field |
|---|---|---|---|---|
| Time to move | Sessions until the anticipated level is reached: q50 and q80 of the duration evidence | trading sessions (XNYS) | `domain/anticipated_move.py` | `anticipated_sessions_q50`, `_q80` |
| Setup maturation | How long the broader setup takes to resolve | bars of the setup timeframe | duration evidence | `thesis_activation_q50_bars`, `_q80_bars` |
| Hold allowance | How long the position may be held: the evidence q80 runway | trading sessions | `planned_hold_from_evidence` (orchestrator :4152) | `planned_hold_sessions` + `planned_hold_basis` (NO_EVIDENCE_HOLD when absent; never 5/10/20 by default) |
| Contract life | Time to expiry | **calendar days** and **trading sessions**, both stated | contract selection / Morning swap | `dte_calendar_days`, `contract_sessions_to_expiry` (today `dte` / `contract_dte`; H8: one may not stand in for the other) |

A 2-session move with an 8-session hold is consistent (review §5).

### 1.4 Value (four kinds, never shown as one "value")
| Kind | Meaning | Unit | Owner | Canonical field | Role (ACK) |
|---|---|---|---|---|---|
| Scenario value | Option model value **if** the underlying reaches `anticipated_level_q50` by the q50 time, divided by the entry ask. Gross, at model mid, no exit cost | × premium (gross ratio) | `domain/anticipated_move.py` | `anticipated_value_multiple_q50` (+ `_q80`, earnings stress) | **DECISION** (pays / does not pay); label it conditional |
| Probability-weighted net return | Average net return across target, stop and timeout, after exit spread and slippage, worse of base and IV stress | net return per 1 of premium | `vanguard/ev_engine_v3.py` | `ev3_ev_conservative_return` | **SUPPORTING** (E09 b) **only after** rewiring onto the ticker assessment's target, time and invalidation **and** calibration in C12; until then AUDIT. Never gate or rank (rule 5) |
| Intrinsic at expiry | Exercise value at expiry at a target | % of premium | `contracts/selected_contract_economics.py` | `monetisability_*` | AUDIT. Today it decides the EOD Lab verdict and focus lane on the legacy target (link 5): an S2 candidate |
| Entry-price sensitivity / maximum premium | The value as entry premium varies; the highest premium meeting a stated objective | price | not built | — | Design (E10) |

### 1.5 Contract and cost
| Fact | Meaning | Unit | Owner | Canonical field |
|---|---|---|---|---|
| Contract identity | Exact OCC symbol, side, strike, expiry | — | OI selection; Morning swap creates a **new linked version** (E20) | `contract_symbol` + version |
| Quote | One coherent observation: bid, ask, time, source, for that exact contract | price, UTC | Morning live quote, else EOD quote | `quote_bid`, `quote_ask`, `quote_time_utc`, `quote_source` as one package (H5: never a bid from one quote and an ask from another) |
| Spread | (ask − bid) / mid | **fraction** (E15 a) | `contracts/long_option_policy.quote_spread_fraction` | `spread_fraction_mid`. Shown as a percent only on screen. Thresholds in config at current values, unit stated. The EIL `<= 30.0` check is removed (E15) |
| Quote age | Time since the quote | minutes | — | `quote_age_minutes`: **disclosure only**, never a gate, rank or visibility input (standing ACK rule; inventory under S1) |

### 1.6 Decision states (separate, never merged; review §8 "decision state model")
| State | Values | Owner |
|---|---|---|
| Ticker assessment | ACTIVE / WATCH / INVALIDATED / UNRESOLVED (+ reasons) | Discovery and direction governance, re-checked by Morning |
| Option assessment | EXPRESSED (value computed) / OPTION_REVIEW (NOT_COMPUTED, volatility only: E12) / NO_SUITABLE_CONTRACT | Contract selection + anticipated move |
| Validation stage | AWAITING_MORNING / MORNING_PARTIAL / MORNING_COMPLETE / MORNING_FAILED | Morning run |
| Morning verdict | GO / FLAG / BLOCK + reasons | `morning_gate.run_gate` (one name: `morning_gate_verdict`; `verdict`, `morning_validation_result` and `live_validation_state` are duplicates to retire from readers) |
| Execution permission | `final_action` | `execution_gate.py` |

## 2. Field-role registry (v0)

**Roles:**
- **DECISION:** may gate, rank, select or be the primary display.
- **SUPPORTING:** shown with its label; no gate or rank.
- **AUDIT:** audit view only.
- **MEASUREMENT_ONLY:** C12 scoring only.

| Field / family | Role | Reader that violates it today (S2 candidates; evidence in Part 2 §B3) |
|---|---|---|
| `anticipated_*` | DECISION | — |
| `planned_hold_sessions` (evidence) | DECISION | — |
| `invalidation_spot` | DECISION | 4 fallback chains (`morning_gate.py:1702` vs :2072, `execution_gate.py:126`) |
| `structural_target`, `target_price`, `target_reachable` (OI) | **to classify (S1)**; AUDIT if a duplicate | Strike filter OI :5594 (link 1); Morning lifecycle fallback :2065 |
| `rr_*`, `option_gain_at_target` | AUDIT (R:R retired) | Lab priority score (link 2); EIL `CURRENT_EDGE` in EOD_SYNTHETIC mode |
| `ev3_*` | AUDIT now → SUPPORTING after rewiring (E09 b) | — (correctly diagnostic) |
| `monetisability_*` | AUDIT | `lab_control.py:1697–1704` EOD verdict; `pretrade_focus.py:157`; `opportunity_tier.py:242` (link 5) |
| `horizon_bucket`, `time_horizon`, `layer2__preferred_horizon`, `macro_preferred_horizon`, `hold_label`, `ev3_horizon_sessions`, `hold_days`, `l2_hold_days` | AUDIT (expiry bucket / legacy holds) | Morning hold fallback + {5,10,20} check (link 3); EOD sparse-row status; Lab "Move Window" |
| `options_score`, `options_research_score`, `composite`/`eil_composite_score`, `priority_score`, `campaign_verdict`, `execution_verdict` | AUDIT (pending the E11 rank objective) | Lab rank (link 2); EOD slate rank (link 7) |
| GEX walls, gamma flip, `qomega_gate` | SUPPORTING (display-only context, CLAUDE.md rule 6) | Execution-gate warnings BUY_NOW → BUY_SMALL (link 4) |
| Spread fields (all `*spread_pct*`) | DECISION via `spread_fraction_mid` only | Unit guessing (`eod_candidate_engine.py:1530`, `dynamic_options_probability.py:75`); EIL :2026 (removed under E15) |
| `source_payload_json` | AUDIT, never in the primary payload | Lab book (`lab_control.py:4074`) |

## 3. Next in S1
1. Classify the "Discovery target" vs the thesis outcome level (§1.2 open), with the lineage trace.
2. Merge in the quote-age inventory and the lineage and open-check results (agents running).
3. Mismatch classification on the 51 GOs: LEGITIMATE_DIFFERENT_MEASURE / SILENT_SUBSTITUTION / CALCULATION_DEFECT.
4. Bring the glossary, the registry and the E11 rank objective to ACK for sign-off before S2.
