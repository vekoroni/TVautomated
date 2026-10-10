# Final design, part 2: fact-ownership audit (6 Oct 2026)

This part completes `FINAL_DESIGN_SOURCE_OF_TRUTH_AND_DECISION_HANDOFF.md`. It is section §B3, plus the addition to §E1, and it closes the last pending row of §C. That file was locked by another program when this was written, so it lives here until it is merged in.

The audit was read-only and covered production code only. File:line references are given for every claim.

## B3. Who owns each fact, and which superseded sources still decide

**Why direction works.** Direction has one writer (`contracts/direction_governance.resolve_governed_direction`) and every gate calls one validator (`validate_direction_record`, at `morning_gate.py:254` and `execution_gate.py:210`). Result: 0 conflicts across 14 fields.

**Why value, time and target do not.** They have approved owners (`domain/anticipated_move.py`; the evidence hold at orchestrator :4152) but **no single resolver and no validator**. Each consumer keeps its own `or` chain:
- target: 5 chains;
- hold: 3 chains, plus the legacy {5,10,20} check;
- invalidation: 4 chains, two of them inside `morning_gate.py` (:1702 vs :2072);
- spread: 2 units under one name.

### Superseded sources still deciding, ranked by harm

| # | Link | Where | Effect |
|---|---|---|---|
| 1 | The contract strike filter uses `structural_target` / `target_reachable`, not `anticipated_level` | OI :5594–5615 | The contract is chosen against one target and valued against another, which can manufacture DOES_NOT_PAY |
| 2 | The Lab priority score has no anticipated-value input (see below) | `intelligence_lab.py:1133–1207`; rank at 1351–1360 | Rank is unrelated to value (Spearman −0.02) |
| 3 | The Morning hold fallback combined with a check that requires a non-evidence hold to be 5, 10 or 20 (see below) | `morning_gate.py:1996–2012`; `option_contract_liquidity.py:225`; OI lifecycle fallback to horizon 5/10/20 at :6225 / :5190 | The retired horizon holds still FLAG rows as CONTRACT_REPAIR |
| 4 | Execution gate warnings, from display-only GEX/gamma checks and a fifth "target" of 2× premium | `execution_gate.py:33, 384–422` | BUY_NOW becomes BUY_SMALL. This conflicts with CLAUDE.md rule 6. The thresholds are literals, and the runway check uses `put_wall` for both sides (:378) |
| 5 | Monetisability runs on the legacy target chain | `selected_contract_economics.py:892`; `lab_control.py:1697–1704`; `pretrade_focus.py:157`; `opportunity_tier.py:242` | It can turn an EOD Lab GO into CONTRACT_REPAIR, drives the focus lane and the tier, and shows NOT_MONETISABLE beside PAYS |
| 6 | The invalidation chains disagree inside one module | `morning_gate.py:1702` vs 2072 | Two answers to "where am I wrong" |
| 7 | The EOD slate rank and tier use OIS and composite, with no anticipated value | `eod_candidate_engine.py:2041, 2941` | The EOD order is unrelated to value |

**Link 2 detail.** The score is built from:
- the options verdict, which is based on wall runway;
- Superbrain-era campaign and execution verdicts;
- the EIL composite;
- **`rr_options_reachable`**;
- OIS, which scores the structural target against the walls;
- WBS;
- GARCH.

**Link 3 detail.** The Morning hold falls back through `ev3_horizon_sessions`, `hold_days`, `l2_hold_days` and finally numbers parsed from labels. Then `calculate_dte_requirement` raises an error unless a non-evidence hold is 5, 10 or 20.

### Already correctly retired
- **EV3 is diagnostic only.** It always passes in the Morning gate, its authority is forced off, and the execution gate does not read it.
- **The Morning gate does not read** R:R, EV3, monetisability or `horizon_bucket` to make its decision.
- **`_check_monetisability`** (`morning_gate.py:280`) is never called.
- **Every production spread formula is (ask−bid)/mid.** The only exception is the Lab card JS, which divides by the ask (`trade-card.js:48`); that is a display fix.

### Further defects (logged; none fixed; each needs root-cause approval)

| ID | Defect | Evidence |
|---|---|---|
| H7 | `contract_spread_pct` is a fraction from OI and a percent after Morning. Two readers guess the unit (≤1 means ×100), which the owner forbids. The EIL check `spread <= 30.0` compares a fraction with a percent, so it always passes | OI :8922; `morning_gate.py:4264`; `eod_candidate_engine.py:1530`; `dynamic_options_probability.py:75`; `execution_intelligence_runner.py:2026` |
| H8 | The lifecycle reads `leg dte or contract_dte or dte`, so trading sessions can stand in for calendar days | `morning_gate.py:2076–2079` |
| H9 | The delta band differs between gates: Morning 0.20–0.75, execution gate 0.20–0.85 | `execution_gate.py` vs `morning_gate.py` |
| H10 | Six different spread thresholds are in use: 8% (literal), 15%, 15%/25% by horizon, 18%/25% (governed) and 30% | `execution_gate.py:24`; OI :313; `opportunity_tier.py:178`; `long_option_execution.py:18–19` |
| H11 | `qomega_gate` is displayed but comes from the Superbrain layer, which is now a passthrough | `avshunter_superbrain_layer.py:2102`; orchestrator :518 |

These are added to H1–H6 in §B2.

## E1 addition: apply the direction pattern to value, time, target and invalidation

Each fact gets:
- **one resolver**, owned by its context, which returns the fact together with its basis, version and missing-reason;
- **one validator**, called by every gate, rank and selection step, the way `validate_direction_record` is called today.

The resolvers sit beside their owners:
- `resolve_target(row, kind=ANTICIPATED|STRUCTURAL|REACHABLE)`
- `resolve_time(row, clock=MOVE|MATURATION|HOLD|EXPIRY)`
- `resolve_invalidation(row)`
- `resolve_spread_fraction(row)`, with the unit in the name

Each S2 change replaces one consumer's `or` chain with a call to the resolver, test-first, starting with links 1–3 above.

## §C status update
The fact-ownership audit is complete. All four audits are now complete. Items the audits marked "not verified" become S0/S1 checks, for example:
- the HL and NVMI per-row values;
- whether `campaign_verdict` reaches Morning rows;
- whether `doi_ranking_score` is a live rank;
- the runway field units.
