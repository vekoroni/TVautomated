# S1: setup lineage (RC5 / E06) and the open audit checks (E31), 6 Oct 2026

**Method:** read-only trace of the code and of run `20261006_060401` (`morning_validated`, the Lab book, the Discovery BEH-001 readings). The thesis-event selection rule was re-checked by me in code. Nothing was changed.

## 1. RC5: the lane is qualified on one setup, but valued on another. DEFECT (silent substitution)

**Mechanism.** Three selectors read the same BEH-001 readings, and nothing joins them:

| Selector | Rule | Code |
|---|---|---|
| **Lane** (authority: tested hit rates) | Best lane A, then B, then C, among trade-side setups on **any** timeframe → `trade_lane_setup` | `domain/structure_behaviour/trade_lane.py:112–138`; discovery `:2521` |
| **Thesis event** (feeds move, time, payoff) | First evaluated timeframe in the order **1d**, 1w, 1mo, 60m…; trade-side live candidates; ACTIVATED before DETECTED; **ties broken by the alphabetical order of `Candidate_ID`** | `domain/structure_behaviour/thesis_category.py:15, 39–47` (verified) |
| **Target** (`target_price`, labelled "DISCOVERY_TARGET") | The extreme of the prior 40-bar range (`PRIOR_RANGE_EXTREME`) | `wyckoff_phase_validator.py:137–144` → discovery `:1729/1739` → OI relabel `:4659/4665` |

The anticipated move takes its level, duration evidence and timeframe from the **thesis event** (`eod_candidate_engine.py:2861–2880`; Morning recompute `morning_gate.py:1208–1214`). Lane B's payoff confirmation uses the same thesis-event value (`eod_candidate_engine.py:2891–2893`).

**Counts.**
- **GO rows:** 51 GOs, all lane A, all with a 1d thesis event. **32 of 51** have a lane setup on another timeframe (24 on 1w, 8 on 1mo).
  - BIDU, UAMY, OUST, ETN, NET, BILI, ODFL, BIRK, PII, SARO, EFX, CP, WWD, MC, CAVA, DKS
  - COHR, TTWO, JOBY, HPQ, CALM, HSY, RARE, CYTK, STZ, FISV, BLDR, HWM, WGO, UTI, ENOV, CENX
- **Lane A/B population:** 198 of 359 rows have the mismatch.
- **No link between the two candidates.** In the sampled rows, the 1d thesis candidate is never linked to the lane candidate by `Parent_Candidate_ID`. They are different signals, with different triggers, invalidations and outcome levels.

| Ticker | Lane setup (its own outcome) | Thesis event 1d (outcome) | Valued at |
|---|---|---|---|
| RARE PUT 14.50 | 1w CoB Reversal (12.44) | Trend Cont. after Shallow Test (6.94) | 7.94 volatility-capped |
| HWM PUT 229.57 | 1w CoB Reversal (191.55) | Seller Absorption Breakdown (188.89) | 188.89 |
| FISV PUT 46.14 | 1w SOW→LPSY (40.80) | LOCAL Trend Cont. (38.38) | 38.38 |
| COHR CALL 333.64 | 1mo Failed Upthrust Cont. (440) | Buyer Absorption Breakout (401.74) | 401.74 |
| NET CALL 359.49 | 1mo SOS→LPS (461.82) | CoB Reversal (355.77, **below spot**) | 484.90 volatility only |

**Compounding defect: stale events are selected.**
- The thesis event is never on the opposite side (`Direction == side`).
- But it can be a **same-side event whose level price has already passed**. `Outcome_Reached_As_Of` is empty on all 51 GO thesis candidates, so passed levels are never retired.
- **BLDR (PUT 55.63):** a 1d BEAR "Failed Spring Continuation", detected 1 Sep, 23 bars old, outcome 63.90, is chosen. It wins only on alphabetical ID order ("…|CAMPAIGN|Failed…"), over a valid 1d Seller Absorption (50.34) and the 1mo SOW→LPSY lane setup (45.03).
- **CENX:** the same pattern (outcome 39.98 vs price 36.94; the lane is 1w SOW→LPSY at 31.86).
- `domain/anticipated_move.py:117–118` then correctly drops the wrong-side level, so no value is computed.

**This explains the 7 GOs without a computed value (RC4).**

| Ticker | Cause |
|---|---|
| NET | Level behind spot → volatility only |
| CYTK, BLDR, CENX | Stale level behind spot + no comparable evidence → no level |
| BIRK | 1d event with no outcome level |
| UNP, ENOV | Level valid, but no duration evidence → reach unknown |

6 of the 7 are mismatched timeframes; UNP's lane is that same 1d event. E12 (approved: these become an option-review FLAG) stops them reading as GO. **RC5 is the cause, and it is fixed separately.**

**Two targets, classified.**
- `target_price` = the prior 40-bar range extreme (HPQ 36.23 = the 40-bar high = the trigger).
- `thesis_outcome_level` = the event's measured move (HPQ 41.47).
- These are **legitimately different measures** (range extreme or first objective vs measured-move outcome). The defect is in how they are used:
  - the OI label "DISCOVERY_TARGET" hides the meaning (R6);
  - the range extreme drives **contract strike selection** (OI :5594, link 1) and monetisability (link 5), while the move is **valued** at the outcome level;
  - the Morning runway falls back from one to the other (`morning_gate.py:2062–2071`).

**Recommended S2 design (for ACK approval):**
1. The anticipated move, time and payoff are computed from the **lane-setting candidate**, or from a thesis event explicitly linked to it by parent ID. A 1d event may refine a 1w/1mo setup only through that link.
2. Exclude candidates whose outcome level price has already passed (set or derive `Outcome_Reached_As_Of`), and replace the alphabetical tie-break with a stated rule: nearest valid level, then most evidence, then newest.
3. Rename `target_price` to `prior_range_extreme` (role SUPPORTING), and choose strikes against the **anticipated level**, the same level the value is computed at.

## 2. Phantom: runs in production, and has a latent defect
- `run_phantom_layer` (`intelligent_orchestrator.py:3928–3959`) is **dead code**: defined, never called.
- Production runs Phantom inline as PHASE 7.5 (`:6383–6457`, `scripts/phantom_engine.py`, fail-open). Its CSV then **replaces** the OI CSV downstream (`:4256–4259`, `:3981–3985`).
- **This run:** 1,636 rows, 0 promoted, 0 score adjustments, so it had no effect.
- **Latent:** `phantom_engine.py:207–209` overwrites `options_score`, and :213–222 rewrites `options_route_verdict` (ADVISORY_PROMOTION). That is authority without G1–G4 (rule 5).
- **S2:** retire the dead function; Phantom writes only `phantom_*` fields.

## 3. Superbrain router patch (`intelligent_orchestrator.py:1847–1881`): NO-OP
- It runs before `superbrain_enriched` exists, so the file check is false.
- If it ever ran, it reads `_macro_age_h` / `_macro_ts` before they are assigned (UnboundLocalError, caught and logged).
- **Log:** 0 "Patched" and 0 "Could not patch" lines since 4 Oct.
- **S2:** delete it, or move it and key it on `signal_id`.

## 4. Horizon router ticker lookup (`:1822/1831`): NO-OP in this run, latent defect
- 1,636 rows, 1,636 unique tickers, 0 tickers with both CALL and PUT, so 0 collisions.
- The 584 `TICKER|UNRESOLVED|UNKNOWN` rows come from the unknown-instrument path, not from a collision.
- H2 (the CALL default) is therefore latent.
- **S2:** key the lookup by `signal_id`; add a multi-row characterisation test.

## 5. Runway and DTE units: label defects and latent mixed units; nothing misvalued in this run

| Field | Unit found | Issue |
|---|---|---|
| `dte` | calendar days (1,041/1,041 match expiry − today) | **595 no-contract rows carry an invented `dte=30`** (OI :4508/8608). All are BLOCK |
| `contract_dte` | XNYS sessions (1,041/1,041) | — |
| `minimum_required_dte` | calendar days | — |
| `dte_buffer_sessions` | **calendar days** | The name says sessions (R3/R6) |
| `morning_gate.py:2076–2079` | leg dte (calendar) → `contract_dte` (**sessions**) → `dte` (calendar) | Mixed-unit fallback. The calendar path was used in this run (64 RUNWAY_SHORT rows all fail on calendar `dte`). Latent. Same mix at `eod_candidate_engine.py:1040` |
| `runway_to_target` | percent of spot, **signed** | **0.0 written for missing** on 681 rows (`eod_candidate_engine.py:2545–2548`) |
| `runway_to_wall_pct` | percent of spot, unsigned | 0.0 for missing on 598 rows (`wall_break_scorer.py`) |
| Lab `runway_to_target` ↔ `runway_to_wall_pct` fallback | same unit, different meaning | Never fired here; display only |
| `remaining_runway_pct` | percent of the thesis move | OK |
| Hold and move-window fields | sessions | OK |

**S2:** rename the buffer, or convert it to sessions; use one unit in the Morning DTE chain; write missing runway as blank, not 0; drop the target/wall fallback; remove the `dte=30` default.

## Summary
| Check | Result |
|---|---|
| RC5 setup lineage | **DEFECT: silent substitution** (32/51 GO; 198/359 lane A/B), plus stale-event selection and an alphabetical tie-break. Root cause of the 7 unvalued GOs |
| Two Discovery targets | **Legitimate different measures, misused:** the range extreme selects strikes, the outcome level values them |
| Phantom | In production, no effect this run; dead duplicate function; latent score overwrite (rule 5) |
| Superbrain router patch | NO-OP |
| Router ticker lookup | NO-OP this run; latent |
| Runway/DTE units | Label defects, latent mixed units, invented `dte=30`, 0.0-for-missing runway |
