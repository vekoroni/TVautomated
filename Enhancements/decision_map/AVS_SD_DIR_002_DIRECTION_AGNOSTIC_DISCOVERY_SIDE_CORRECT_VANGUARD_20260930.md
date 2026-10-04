# AVS-SD-DIR-002: Direction-agnostic Discovery and side-correct Vanguard

**Status:** proposed solution design; ACK approved the review corrections on 1 October 2026. Those corrections are incorporated below. This is not an implementation, predictive-validation, cut-over or trading-authority approval.
**Date:** 30 September 2026
**Original author:** Claude, working as a read-only reviewer on 30 September. The 1 October review amendment changed this design document only; no pipeline was run or changed.

**Governing documents** (authority order per `CLAUDE.md`):
1. ACK decisions
2. `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` v1.1
3. Method notes 01, 02 and 06
4. `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md`
5. `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`
6. Code

**Relationship to other designs:**
- **AVS-SD-SOR-001** (proposed, 27 Sep). This document amends its slices S1 (C3 structure), S2 (compression/fusion) and S4 (Vanguard L1/L2) with a *symmetry and direction-assignment* contract. It keeps SOR-001's episode ontology, point-in-time rules and support floors.
- **AVS-SD-TEV-001** (signed off). This document preserves its ticker-first and anti-corruption-adapter boundaries. It also requires explicit continuity changes in Options, EIL, EOD, Morning, Lab and Interpreter (§4.7); those are substantive downstream changes to test, not a claim that C6–C14 remain untouched.

**Evidence base:** a static read of every Python module on the Discovery and Vanguard stage paths, plus their downstream consumers and the existing tests. The line-level tables are in three companion files in this folder, and Appendix A condenses them:
- `AVS_SD_DIR_002_EVIDENCE_A_DISCOVERY_AUDIT.md`
- `AVS_SD_DIR_002_EVIDENCE_B_VANGUARD_AUDIT.md`
- `AVS_SD_DIR_002_EVIDENCE_C_CONSUMERS_TESTS_RULES.md`

An independent review sampled 42 file:line claims (38 held as first written). It raised nine required corrections, all applied in this version. Line numbers refer to the working tree as of 30 Sep 2026, which includes uncommitted SOR-001 and TEV-001 changes.

---

## 0. Summary

**The problem.**

*Discovery is not direction-agnostic.* The side is shaped *before* the data is weighed:
- **Bias in the core path.** It has **21 asymmetric rules** and **10 places where a missing or tied value becomes bullish**, spread over `WyckoffEngine_3101_v2.py`, `wyckoff_crabel_precor_logic_v2.py`, `avshunter_discovery_ULTIMATE.py` and `wyckoff_phase_validator.py`.
- **Geometry for one side only.** Stop, target and invalidation are built only for the side already chosen, so the other side can never be assessed on equal terms.
- **Correlated evidence treated as independent.** The "independent" fusion direction is Wyckoff's buyer/seller control reading. Precor's intent is also reconciled against that control reading. So "CONFIRMED" is usually one signal agreeing with itself.

*Vanguard is not side-correct:*
- **It never learns the thesis side.** `VanguardInput` has no direction field.
- **Its history is upside-only.** Every historical probability, EV, "stop" and timing statistic uses upside-only labels.
- **It casts its own CALL-default vote.** `edge_detector._determine_direction` returns `"CALL"` on neutral evidence. `direction_governance.collect_resolution_evidence` then counts that output as ACTUARIAL evidence.
- **Most of the vote is circular.** Because Layer 1 is neutral on every row, the vote reduces to: P(+10% in 20d) > 0.55 → CALL, < 0.35 → PUT, otherwise CALL. So a "PUT" means only "unlikely to rise 10%".

**The design, in one sentence.** Discovery computes structure side-neutrally and builds **both** candidate geometries (BULL and BEAR). Direction is assigned as the **last** step, by a symmetric, pre-registered rule over measured evidence. Vanguard then receives the thesis and evaluates **each side on its own mirrored evidence**, never casting a direction vote.

**How regression is prevented.** "No regression" cannot mean identical outputs, because the design exists to change biased ones. It is defined in §6 as nine testable controls (R-1 to R-9). The key ones:
1. **Mirror invariance.** A price series reflected in log space must produce exactly the mirrored result.
2. **Attribution diff.** Every changed row in a stored-run replay must be explained by a registered fix ID. An unexplained difference stops the build.
3. **Reality check.** On a pre-registered, same-start matured cohort, compare new and legacy outcomes with a paired, block-aware non-inferiority rule and explicit missed-winner and coverage accounting; no inference is made from overlapping intervals alone.
4. **Consumer continuity.** Every downstream consumer keeps receiving its legacy vocabulary through a versioned adapter until it is migrated.

**What ACK has approved:** the review corrections in the 1 October amendment below: retain a supported direction when geometry is incomplete; show opposing evidence without an automatic veto; keep interim Vanguard statistics descriptive; exclude macro from Discovery direction while resolving its later forecast role explicitly; name downstream changes; and use a paired outcome test. The remaining policy choices in §8 still require their own decision unless this amendment expressly resolves them.

**1 October review amendment (ACK-approved):** The directional observation, directional assignment, geometry completeness and trade readiness are separate facts. A missing or wrong-side structural invalidation does not erase an otherwise supported BULL/BEAR assessment; it yields `INCOMPLETE_GEOMETRY` and prevents a complete trade plan. A missing structural target may be `target_state=NONE`. Opposing evidence is recorded and may make a thesis contested, but one contrary sub-observation does not automatically make it UNASSIGNED. Vanguard v7/V-A results remain shadow/descriptive until version-equivalent, point-in-time and outcome tests support their use. Macro is excluded from Discovery's direction assignment; its possible later, dated role in C5 is an unresolved authority decision because the signed TEV-001 design and `CLAUDE.md` differ. Temporary shadow/rollback switches are verification controls, not permanent opt-in production behaviour. Sections 4–8 below implement these distinctions.

---

## 1. Objective (G1 trace)

| Item | Statement |
|---|---|
| Business question | "For each ticker, what does the market structure support: a rise, a fall or neither? What would invalidate each side, and how strong is the evidence for each?" (capability **O1 Direction**, `OBJECTIVE_ASSURANCE_ASSESSMENT.md` §6) |
| User requirement (30 Sep) | Discovery must be **direction-agnostic until the data assigns a direction**, with **no regression**. |
| Spec anchors | §3 Invariant A: *Direction is owned by the Thesis context*. §7: StructureAssessment "must not contain final trade direction" and proposes geometries "for each candidate direction". §9: direction state is descriptive, not a gate. Invariant D: "No statistic, threshold or payoff may be computed upside-only and reused for the downside." Note 02: "Never auto-flip direction. A structurally proposed opposite direction is its own candidate geometry." Map S8: "Retire: `_determine_direction` CALL default"; "mirrored inputs give mirrored outputs." |
| Success measure | See §6. Symmetry is proven by construction. Every change is attributed. A pre-registered paired, same-start outcome comparison meets the approved non-inferiority margin by side, including coverage and missed-winner cost; an immature cohort cannot pass by default. |

---

## 2. Scope and non-goals

**In scope:**
- **The Discovery stage path:** universe load → `avshunter_discovery_ULTIMATE.py` and its engines → post-Discovery rewrites → `validate_quality`.
- **The Vanguard stage path:** thin package / packages → `run_vanguard_from_packages.py` → `vanguard/*` → actuarial database builder and query → enrichment pass.
- **The downstream adapters that must change for continuity:** the C5 descriptive packet, Options `parse_structural_context`, the EIL signal type, the governance evidence collector, the Morning/finaliser version check, and `pretrade_focus`.

**Non-goals:**
- No redesign of C6–C14 valuation or trading authority. Required consumer changes in Options, EIL, EOD, Morning, Lab and Interpreter are in scope (§4.7), including removal of direction fabrication and target backfill; they require integrated regression and explicit cut-over evidence.
- No new trading authority. Everything new is `IMPLEMENTED_FOR_REPLICATION` until spec §24 and gates G1–G4 are passed.
- No new macro input and no macro vote in Discovery side assignment. `CLAUDE.md` rule 6 currently makes macro display-only, while signed TEV-001 §4 permits independently sourced point-in-time macro/sector evidence to condition a later C5 forecast without owning direction. This document does not decide that conflict: obtain an explicit ACK authority decision before changing C5 macro use. Existing macro leakage into Discovery direction or scores is removed.
- No promise of a particular CALL/PUT mix. The rules become symmetric, but outputs may still differ because real markets are asymmetric (drift, volatility skew).
- No rebuild beside the existing pipeline. Existing modules are fixed in place, test-first (`CLAUDE.md` rule 4, ACK D1).

---

## 3. Verified current state

The full inventory is in Appendix A. The headline facts are below, all verified in code on 30 Sep. Earlier claims that the code **refutes** are marked ✗.

### 3.1 Discovery

| # | Fact | Where |
|---|---|---|
| 1 | Direction is frozen *inside* Discovery (`direction_authority='DISCOVERY_GOVERNED'`). Options then records it with `allow_non_directional_resolution=False`, so no later stage can ever resolve an UNRESOLVED/STRANGLE row. | discovery :1570-1588, :2078-2082; Options :4686-4694 |
| 2 | The decision table `resolve_discovery_thesis_direction` is itself mirror-symmetric and fails closed when the preliminary and structural sides conflict. **Most of the bias is in its inputs, not the table.** One exception: `preliminary_discovery_direction` silently prefers fusion over a disagreeing Wyckoff side (`:84-90`). This is rarely reachable today because both read the same control state (F1). | `contracts/direction_governance.py:84-128` |
| 3 | Fusion direction is BUYERS/SELLERS control plus an "operator" that is itself derived from control. Precor is audit-only inside fusion, and Discovery's intent reconciliation also keys on control. So the "preliminary" and "structural" votes share one source. | `swing_fusion.py:124-135`; Wyckoff :1028-1036; discovery :320-335 |
| 4 | Wyckoff counts only downside breaks and reclaims. Buyers get `reclaim_count*3` (uncapped) while sellers get a flat +2. A downside break with seller control is labelled **UTAD** (an upthrust term). A genuine upthrust cannot produce a Phase C event. | Wyckoff :350-358, :403-408, :715-722 |
| 5 | In Phase C under EQUILIBRIUM, Spring and UTAD tie at 45/45. `max()` returns Spring, and Spring under EQUILIBRIUM is LONG. | Wyckoff :723-728, :179, :884-891 |
| 6 | Phase B: two or more low-volume bars score `ST`/`Test` (up to 75). Both are "long events", with no bearish Phase B event. This is plausibly the largest single source of CALLs, but that is **unquantified**; the Stage 0 population report must measure it. | Wyckoff :673-684, :884 |
| 7 | Phase A is short-leaning: an up climax (BC) can give SHORT, but a down climax (SC) gives nothing. | Wyckoff :884-885 |
| 8 | The momentum override (C/D→B) fires only for strong **up** moves. Three existing tests pin this upside-only rule. | Wyckoff :157-167; `test_directional_bias_fixes.py:229/248/277` |
| 9 | Precor intent: Phase C BUYERS → BUY with no mode check, while SELLERS also needs DISTRIBUTION. The Phase E fallback is BUY. Mode is ACCUMULATION when data is insufficient or recent drift is zero. | precor :277, :647-651, :691-696, :727-732 |
| 10 | `_reconcile_intent` gives a SELL setup two routes to CALL but a BUY setup only one route to PUT. Rule 3 fires at 40 days above EMA50, not the 60 its docstring states. The helper set is bull-only: bullish `ALIGNED` only, `days_above_ema50` only, `pct_from_52w_low` only. | discovery :236-335 |
| 11 | The EMA 9/21/50/200 stack decides every TRANSITION row. EMA200 is computed from as few as 30 bars (70% confidence on the actual bar count). | `domain/thesis_direction.py:117-127`; discovery :236-249, :122, :1302 |
| 12 | Long-side defaults: Tier-0 `stop_loss = price×0.97`, which also overwrites `control_state` and `phase`. The ATR fallback stop is `price − dist` for every side. The validator's mode defaults to ACCUMULATION, which makes PUT invalidation missing more often. | discovery :562, :1796-1800, :2247-2248; validator :81-90, :187-198 |
| 13 | Geometry for the rejected side is still emitted on CONFLICT_REVIEW rows. Target validity uses Wyckoff `trade_direction` rather than the thesis side. `rr_underlying` uses `abs()`. Targets are 20-bar extreme ×1.05/×0.95, a formula rather than structure. | discovery :1766-1840, :1964-1976; Wyckoff :1046-1062 |
| 14 | The phase buckets cannot output DISTRIBUTION or MARKDOWN, and they feed the actuarial state key. | discovery :658-690, :818-828 |
| 15 | ✗ The earlier claim that the asymmetry gate is "unbounded" is wrong. It **can never pass**: R = width/(width + buffer + 0.75·ATR) < 1 < 2.0. It is dead geometry that still reaches the CSV. | `asymmetry_gate_swing.py`; discovery :1772-1776, :2091-2097 |
| 16 | Hidden tier-4 drop (composite < 25). Decay uses `date.today()`. The composite is non-monotonic (adding compression can lower it). An option-level VMS score (+5/+2) changes the ticker tier. Seven of eight drop reasons are mislabelled `NO_SIGNAL_AT_ANY_HORIZON`. | discovery :1637-1639 (drop; `assign_tier` :613-622), :628-636 (composite), :891-899, :1412-1417, :2570-2580 |
| 17 | Macro: inside Discovery it is labels only. **But** `apply_macro_enrichment_to_discovery.py` rewrites the finished CSV, overwrites `macro_direction_authority` and adds a CALL/PUT `macro_direction_vote` (90% confidence). Discovery and the rewrite also read different macro snapshots. | enrichment :212-265; discovery :2396 |
| 18 | The SOR-001 changes are live by default: prior-range Wyckoff, typed Crabel state and `wyckoff_mode_phase_key`. Because the prior range makes downside breaks reachable, **the buyer-only reclaim bonus and downside-only Phase C route now fire more often** (85% confidence). | Wyckoff :323-342; `audit/AVS_SOR001_BUILD_RECEIPT_20260927.md` |

### 3.2 Vanguard

| # | Fact | Where |
|---|---|---|
| 1 | The default input mode is `manifest`. The package scripts run as libraries inside `avshunter/c0_run/thin_package.py`. | orchestrator :637-647; thin_package :165-208 |
| 2 | Discovery `direction` is carried in the package but reaches no field inside the engine. `VanguardInput` has no direction field, and the adapter drops `avshunter_signal`, `wyckoff_phase_bucket`, the intraday context, the 52-week dates and the regime snapshot. `vanguard_signals.csv` does not echo `direction`. | `input_schema.py:186-224`; adapter :141-284; runner :1216-1244 |
| 3 | `_determine_direction` defaults to CALL. With Layer 1 neutral on every row, PUT comes from the absence of upside. There is a wrong-sign vote in downtrends (`prob_trend_continues_20d` = P(ret > 0)). | `edge_detector.py:503-534`; `actuarial_query.py:1102` |
| 4 | The actuarial builder produces only up-hit labels. The `hit_5pct_down_before_10up` label is only ever true when +10% was hit, and `days_to_*` uses 20 as a sentinel. Win rate = P(ret > 0). EV, Kelly, hold, `edge_quality`, `probability_edge` and the preferred horizon are all long-side. **24 upside-only sites** in total. | `actuarial_core_v7.py:310-353`; `actuarial_query.py:666-724, 1100-1130`; `main.py:44-66, 247-255, 357-396` |
| 5 | Mirrors already present, usable without a rebuild: `raw_prob_down_*` = P(ret < 0); signed close-to-close EV from `ret_pctl_*`; touch-only down hits from `outcome_max_drawdown_*`. | `actuarial_query.py:708-713, 1061-1085`; core_v7 |
| 6 | Live states are matched against differently defined history: `structure_quality` is a constant 25 (WEAK), where the database's WEAK means RSI < 40. Live and database trend definitions differ, and maturity has *opposite* EARLY semantics. Missing EMA/ADX/RSI inputs become 0/0/50. Dropped match dimensions are still tagged EXACT. | `state_calculator.py:499-533, 609-642`; core_v7 :130-155; adapter :244-251; `actuarial_query.py:485-530, 861-871` |
| 7 | No point-in-time cut: the query loader does not read `ticker`/`date`, and the baseline is computed over the whole database. `analysis_timestamp` and relative volume use the wall clock. | `actuarial_query.py:53-95, 689-693`; adapter :162-167; `state_calculator.py:664-683` |
| 8 | The trend-exhaustion veto is keyed to the *state trend*, not the thesis side, so a PUT at a late-uptrend high is vetoed. | `edge_detector.py:408-446` |
| 9 | ✗ The "RISK_OFF floors higher" effect is not live: macro is fixed to TRANSITIONAL. `macro_regime` is still an actuarial match-key dimension, which is a rule-6 leak. | `state_calculator.py:807-812`; runner :1093-1101; enrichment pass :437-441 |
| 10 | Latent Evening-abort path. A ticker with an open trade contract goes through governance, whose direction defaults to CALL, and is then skipped with no pass or reject row. The C5 packet then fails population reconciliation and the Evening run aborts. Nothing in the repo creates contracts today (85% confidence). | runner :1462-1477; `trade_governance.py:239`; `descriptive_forecast_packet.py:87-90`; orchestrator :6026 |
| 11 | Side-aware machinery already exists but is not on this path: `domain/forecast_path_label.py` (mirrored BULL/BEAR first-passage label), `domain/competing_path_estimator.py` (point-in-time incidence with floors), and `vanguard/ev3_stage0.py:626-846` (mirrored barrier grid). | as listed |

### 3.3 Downstream coupling that makes this change risky

| Risk | Where |
|---|---|
| The C5 descriptive packet (a **critical** Evening step) maps `direction` with an exact `{"CALL","PUT"}` lookup and raises `duplicate ticker`. BULL/BEAR tokens make every row non-directional. Two rows per ticker abort the Evening run. | `domain/descriptive_forecast_handoff.py:85-86, 129, 135-138`; orchestrator :6015-6028 |
| When Vanguard's edge direction is not CALL/PUT, Options **fabricates** one from `raw_prob_up` vs `raw_prob_down`, overwriting three fields. Removing Vanguard's vote alone would be illusory. | Options :4643-4658 |
| EIL `signal_type` requires `edge_dir in {"CALL","PUT"}` for CURRENT_EDGE/FUTURE_EDGE, and this feeds momentum tier and EOD status. | `execution_intelligence_runner.py:2853-2867` |
| Strict set checks silently skip when given non-CALL/PUT tokens, producing false-green audits and a skipped capital block. | EIL :2350; `handoff_contract_audit.py:478-606`; `lab_control.py:1933, 2342`; `morning_gate.py:1581`; `execution_gate.py:123` |
| `validate_direction_record` requires `dir_calc_version == DIR_CALC_VERSION ("dir_v1.2.0")` and an exact policy hash. The finaliser requires one uniform version per run. A release between an Evening run and its Morning run fails every in-flight row. | `direction_governance.py:24, 376-424`; `morning_handoff_finalizer.py:930-937` |
| Resolution requires 2 families, a 60% share and a 20% margin (literals, against `CLAUDE.md`'s configuration rule). The admitted families are ACTUARIAL (Vanguard), CATALYST, PRICE_FLOW (physics) and RELATIVE_STRENGTH. The spec and addendum retire catalyst, relative strength and physics (A.2, D2, D4). | `direction_governance.py:35-37, 158-227` |
| Options scope uses Vanguard `edge_quality` (upside-only) and `final_recommendation contains 'EDGE_STRONG'`. Side-correcting these moves the scoped population. | Options :9864-9877 |
| `validate_quality` aborts the whole Evening run if the candidate ratio is below 15%, the Tier-0 ratio below 1.5%, or there are no Tier 1/2 rows. Removing long-biased events can trip it. | orchestrator :564-568, :2113-2200 |
| `pretrade_focus.project_evening_thesis` buckets the Evening thesis from `direction_resolution_call/put_score` and PRICE_FLOW evidence. | `domain/pretrade_focus.py:282-334` |

---

## 4. Target design

### 4.1 Principles

- **P1: Neutral until assigned.** Every Discovery stage before assignment produces **side-neutral observations** (range, events with location, control evidence, compression, trend) and **per-side candidate evidence** (`bull_*`, `bear_*`). No stage before assignment may write a single side, default to a side, or build geometry for one side only.
- **P2: Symmetry by construction.** Each side-bearing rule is written once with a side parameter `s ∈ {+1 (BULL), −1 (BEAR)}` in log-price space, not as two hand-written copies. A mirror test proves each rule (§4.2).
- **P3: Assignment is the last directional step and is data-driven.** A single pre-registered, versioned function assigns `thesis__side ∈ {BULL, BEAR, UNASSIGNED}`, using measured directional evidence, with an explicit basis and never a default. Geometry completeness is a separate status and cannot erase a supported side. UNASSIGNED stays visible and is never dropped (R11).
  - `UNASSIGNED` is deliberately **not** the legacy option-side token `UNRESOLVED` (R3: one enum per concept). The adapter maps between them.
  - The assignment is written to a Thesis-owned `thesis__*` namespace, not into the StructureAssessment fields. This keeps the spec §7 rule that structure "must not contain final trade direction" (see DEC-9).
- **P4: Correlated evidence is counted once.** Wyckoff control, fusion, Precor intent and the EMA stack all come from the same OHLC bars. They form evidence **families**: STRUCTURE (events and control) and TREND (context). They are not independent votes (SOR-001 §3.3, TEV-001 §4 item 2).
- **P5: Vanguard evaluates, never decides.** Vanguard receives the thesis side and both candidate geometries, including typed missing geometry. It publishes **mirrored evidence for each side**. It has no direction vote, and nothing downstream may read a Vanguard output as a direction. Interim v7/V-A comparisons remain descriptive/shadow and cannot supply a trusted edge gate or rerank the ticker book.
- **P6: Missing is typed.** No 0.0, 50, CALL, ACCUMULATION or day-20 stand-ins. A missing input gives `NOT_EVALUATED` / `INSUFFICIENT_EVIDENCE` with a reason (R1, Invariant B).
- **P7: Legacy vocabulary behind an adapter.** Canonical fields use BULL/BEAR (spec §7, TEV-001 §3). The legacy CSV fields (`direction` CALL/PUT/UNRESOLVED/STRANGLE, `direction_authority`) are **derived** from canonical fields by one versioned adapter. They are never computed independently. Consumers migrate one at a time.
- **P8: Shadow before switch.** Every behaviour change first writes namespaced shadow fields, is measured by the attribution diff and outcome check (§6), and only then replaces legacy values behind a flag with a tested rollback.

### 4.2 The symmetry kernel

**Mirror map.**

| Legacy term | Mirror | Legacy term | Mirror |
|---|---|---|---|
| BULL | BEAR | Spring | UTAD |
| BUYERS | SELLERS | SOS | SOW |
| ACCUMULATION | DISTRIBUTION | LPS | LPSY |
| MARKUP | MARKDOWN | SC | BC |
| CALL | PUT | NEAR_LOW | NEAR_HIGH |
| BUY_SETUP | SELL_SETUP | above | below |
| BULLISH | BEARISH | range_low | range_high |

Side-neutral terms map to themselves: TR, ST, TEST, EQUILIBRIUM, TRANSITION, UNKNOWN, NONE.

**Reflection transform, used by tests.** For a reference price `K`, reflect in **log space**:

- `ln p' = 2 ln K − ln p` for open and close
- `high' = K²/low` and `low' = K²/high`
- volume unchanged

Why log space: percentage thresholds and ratios then mirror exactly, e.g. `low < range_low·e^(−k)` ⇔ `high' > range_high'·e^(+k)`. Arithmetic reflection would not do this.

**Kernel rules that make exact mirroring possible:**
1. Every side-bearing threshold is a symmetric **log distance** `k` (the bull test uses `e^(−k)`, the bear test `e^(+k)`) or an ATR multiple computed from log true range. Existing asymmetric pairs such as `×0.98` / `×1.02` become `e^(∓0.0202)`. The new value is recorded as a configuration change (Appendix B of the spec), not a literal.
2. Trend features used for side evidence are computed on **log price** (EMA of `ln p`), so that `EMA(2 ln K − ln p) = 2 ln K − EMA(ln p)` holds exactly. The legacy `EMA9/21/50/200` columns stay unchanged for display and for existing consumers. New `trend_*` fields carry the log-space values.
3. Ties are handled explicitly. Equal side scores return `AMBIGUOUS` (and, at assignment, UNASSIGNED), never "first key wins". `max()` over a side-bearing dict is forbidden; a static check in the tests enforces this (§6, R-6).
4. Each side parameter enters one function. For example, `range_break(bars, range, s)` returns break/fail-back counts for side `s`. `control_evidence(bars, s)` returns the same-shaped evidence for either side.

**Existing quantities that do not mirror under log reflection.** Each needs explicit treatment in the kernel, or is kept out of side evidence:

| Quantity | Why it does not mirror | Treatment |
|---|---|---|
| Percent-change thresholds, e.g. ROC > 30% (Wyckoff momentum override), `pct_from_52w_low ≥ 25%` (Rule 3) | +30% reflects to −23.1%, not −30% | Symmetric log thresholds: ±ln 1.3, ln 1.25 |
| Multiplicative stop/target/break factors: ×0.98, ×1.02, ×1.05, ×0.95; Precor `breakout_pct` (1±x) | Asymmetric pairs | `e^(∓k)` with one configured k |
| Close-in-bar position `poc` (Wyckoff :309, Precor `_poc`) | The reflected value is `l(h−c)/(c(h−l))`, not `1−poc` | Log version: `(ln c − ln l)/(ln h − ln l)` |
| Arithmetic true range, ATR, `spread_ratio`, ATR percentile rank, NR7/NR4 range ranking | Ranges in price units scale with price level | Log true range for side evidence; the legacy ATR stays for display and eligibility |
| RSI, ADX (price differences) | Not scale-invariant | Log-return versions for side evidence, or kept out of side evidence |
| Rolling VWAP and volume-profile POC bins | The reflected arithmetic VWAP is a harmonic mean | Volume-weighted mean of ln p; POC bins on a log grid |
| Eligibility (price 5–500, ADV$, ATR$) | Depends on price level, not side | Not side evidence. Excluded from the mirror test by construction (see R-2) |
| Arithmetic returns in Vanguard V-A blocks | +10% up reflects to −9.09% down | Side thresholds defined as `e^(±k) − 1`, and signed EV from the per-horizon mean log return (§4.6.3) |

Mirror equality is tested with a floating-point tolerance (1e-9 relative). Fixtures must avoid values sitting exactly on a threshold.

**What symmetry does not mean.** Real markets have upward drift and volatility skew, so a symmetric rule set may still produce more BULL than BEAR on real data. That is a finding, not a defect. The test is on the **rules**: a reflected universe must give the mirrored counts on the side-bearing outputs (§6, R-2).

### 4.3 Discovery: new stage order

The existing modules are kept and fixed in place. The order within `scan_ticker_ultimate` becomes:

```
1  load bars (as-of evidence session; no date.today())
2  ELIGIBILITY (ticker-level; typed reason codes, not NO_SIGNAL_AT_ANY_HORIZON)
3  SIDE-NEUTRAL OBSERVATION
     range (prior, dated — SOR-001), events with location, compression (typed),
     trend context (log EMA), control evidence per side, Precor per side
4  PER-SIDE CANDIDATE EVIDENCE   bull_* and bear_* built by the same kernel
5  PER-SIDE CANDIDATE GEOMETRY   bull_/bear_ invalidation (sourced or typed missing, correct side),
                                 target LEVEL|NONE (structural only), σ-distances
6  SIDE-NEUTRAL SCORE / TIER     from side-neutral quantities only
7  ASSIGNMENT (last directional step) assign_thesis_side(...) -> thesis__side + thesis__direction_status + thesis__direction_basis
8  LEGACY ADAPTER                derive direction/stop_loss/structural_* for the assigned side
9  GEOMETRY/READINESS STATE      complete or INCOMPLETE_GEOMETRY; never rewrites thesis__side
10 write row (one row per ticker)
```

**Per-step rules:**
- **Step 2, eligibility.** Keeps the current price, volume, liquidity and ATR thresholds unchanged until ACK decides DEC-2. Only the reason codes are corrected (F15): `ELIG_PRICE_RANGE`, `ELIG_AVG_VOLUME`, `ELIG_ADV_DOLLARS_OPTION_PROXY`, `ELIG_ATR_DOLLARS_OPTION_PROXY`, `ELIG_ATR_PCT_OPTION_PROXY`, `ELIG_TIER4_LOW_COMPOSITE`, `ELIG_INSUFFICIENT_BARS`.
- **Step 3, side-neutral observation.** Replaces the side-bearing internals listed in the fix register (§5.1). Event labels become side-neutral plus a **location** (near range low or near range high). For example, a Phase-B secondary test is `ST@LOW` or `ST@HIGH`; it is no longer "a long event".
- **Step 4, per-side evidence.** Each side gets an **evidence vector**, not a vote:
  - `s_event` (strongest confirmed structural event for side s, with strength and bar date)
  - `s_control` (control evidence for side s from the repaired Wyckoff scoring)
  - `s_intent` (Precor intent mapped to side s, with mode known or UNKNOWN)
  - `s_trend` (log-EMA stack aligned with s, only when ≥ 200 completed bars; otherwise `TREND_INSUFFICIENT_HISTORY`)
  - `s_geometry_valid`
- **Step 5, per-side geometry.** Both sides are always attempted:
  - The invalidation, where sourced, is the structural level on the correct side of the reference price. It comes from the validator's range boundary, now computed for both modes. Missing, stale or wrong-side levels are typed; they do not decide direction.
  - The ATR fallback is published as `*_reference_only` and never as invalidation. This matches the existing guard `test_direction_geometry_semantic_repairs.py:55`.
  - The target is `LEVEL` only when a structural level exists on the correct side (prior range extreme, measured move). Otherwise it is `NONE`. The 20-bar-extreme ×1.05/×0.95 formula becomes a displayed `*_reference_level`, never a target (spec §7, note 02 principle 4).
  - Distances are expressed in σ (spec §7).
- **Step 6, side-neutral score and tier.** The composite, tier and sort key use side-neutral quantities only: phase evidence, event strength regardless of side, compression, maturity.
  - Direction-conditioned scores are published per side and are not used in ranking: `vwap_acceptance_score`, `repricing_direction`, `abnormal_repricing_score`, and the `lift_proxy_score` VWAP term.
  - This removes the within-tier preference for already-directed rows (D15-D18).
- **Step 7, assignment.** Uses the evidence rule in §4.4. It does not require a target or invalidation price to describe a directional reading.
- **Step 8, legacy adapter.** Uses the mapping in §4.5.
- **Step 9, completeness.** A missing or wrong-side sourced invalidation gives `INCOMPLETE_GEOMETRY`; the direction remains visible, but the row is not a complete trade plan. `target_state=NONE` is permitted without a fabricated target.

### 4.4 Direction assignment rule (`assign_thesis_side`, policy `side_assign_v1`)

**Owner and placement.** The function is Thesis-context policy. It lives in `contracts/direction_governance.py`, the existing owner of the frozen direction table (enhance in place, not a new module).
- It is invoked at step 7 of the Discovery process only because there is no production C5 composer yet.
- Its outputs are written to the `thesis__*` namespace. They are not written to StructureAssessment fields, and no C3 function may read them back (a test enforces this).
- When the C5 composer from SOR-001 S5 goes live, the same function moves behind it unchanged.
- ACK accepted DEC-9 on 1 Oct 2026: as a time-limited exception before C5 exists, the Discovery process may write Thesis-owned `thesis__*` output. C3 structure functions must not read that output back. The exception expires when the C5 composer takes ownership.

**Inputs.** Only the per-side directional evidence vectors from §4.3 step 4. Geometry validity is an output of the separate completeness assessment, not an input to side assignment. No Vanguard output, macro, option, scanner or catalyst field is allowed; this is enforced by a signature test.

**Qualifying support.** This definition is needed because per-side control evidence is usually non-zero for *both* sides. For each STRUCTURE sub-evidence type `x ∈ {event, control, intent}`, side s is **supported by x** when:
- **event:** a confirmed side-s event exists (Spring/SOS/LPS/SC-test for BULL; UTAD/SOW/LPSY/BC-test for BEAR) with strength ≥ θ_event;
- **control:** `score_s − score_(−s) > θ_control`, a margin rather than a presence test;
- **intent:** the reconciled Precor intent maps to s and the mode is known.

`S(s)` is the set of supporting types. `T(s)` is true when the log-EMA stack is fully aligned with s, which requires ≥ 200 completed bars. The thresholds θ_event and θ_control are versioned configuration (spec Appendix B), set in Stage 0 so that legacy symmetric cases keep their legacy side. That setting is verified by the R-3 attribution diff.

When both sides have qualifying support, the policy compares a versioned, bounded **within-STRUCTURE evidence-strength summary** for BULL and BEAR, retaining the individual observations and missingness. Correlated event, control and intent are not counted as independent families. The comparison method, its margin θ_contested and minimum observation quality must be registered using earlier evidence and frozen before the outcome cohort is examined. A materially leading side is published as `CONTESTED_DIRECTION` with its counter-case; only a true tie, insufficient quality or a difference below the pre-registered margin is UNASSIGNED. The purpose is to expose uncertainty, not tune a score to manufacture more directed rows.

**Rule.** It extends the existing table; it does not replace it. Evaluate it in order.

| Order | Condition | `thesis__side` | `thesis__direction_status` | Legacy adapter output | Basis |
|---|---|---|---|---|---|
| 1 | Both sides have qualifying support; one leads by the registered margin and quality rule | Leading side | `CONTESTED_DIRECTION` | CALL / PUT | Preserve the opposing evidence and strength comparison; do not treat it as a second independent vote |
| 2 | Both sides have qualifying support; neither leads by that rule | UNASSIGNED | `CONFLICT_REVIEW` | UNRESOLVED | Genuine unresolved conflict; both evidence blocks retained |
| 3 | `S(s) ≠ ∅`, `S(−s) = ∅`, ≥ 2 distinct types in `S(s)` | s | `CONFIRMED_STRUCTURE` | CALL / PUT | Replaces `CONFIRMED`; independence = `SINGLE_FAMILY_OHLC` |
| 4 | As row 3 but exactly one type | s | `SINGLE_SOURCE_STRUCTURE` | CALL / PUT | Replaces `CONFIRMED_PRELIMINARY` / `RESOLVED_STRUCTURAL` |
| 5 | `S = ∅` for both sides, `T(s)` true | UNASSIGNED | `TREND_ONLY` | UNRESOLVED | ACK DEC-1: trend is context, not explicit structural direction; retain its observed side as context only and record `thesis__unassigned_reason=TREND_ONLY` |
| 6a | `S = ∅` for both sides; Precor intent = TRANSITION; trend available but aligned with neither side | UNASSIGNED | `TRANSITION_MIXED_TREND` | STRANGLE (until DEC-3) | The legacy STRANGLE case |
| 6b | `S = ∅` for both sides; trend unavailable (< 200 bars) | UNASSIGNED | `TREND_INSUFFICIENT_HISTORY` | UNRESOLVED | Missing is not neutral (R1) |
| 6c | Otherwise | UNASSIGNED | `NO_DIRECTIONAL_EVIDENCE` | UNRESOLVED | — |

**Separate geometry/readiness assessment.** For a directed row, missing, unsourced or wrong-side structural invalidation yields `geometry_status=INCOMPLETE_GEOMETRY`; it never changes `thesis__side` or `thesis__direction_status`. The row remains available for research and outcome capture but is not a complete actionable trade plan. Missing structural target yields `target_state=NONE` and no synthetic target. A missing reference price makes geometry unassessable and is typed separately from weak directional evidence.

**Properties, each proven by a test.**
- **Mirror:** `assign(mirror(E)) = mirror(assign(E))`.
- **No default:** a missing input never produces BULL or BEAR.
- **Purity:** no Vanguard, macro, option or scanner input.
- **Deterministic:** the same evidence and policy version give the same result.
- **Evidence monotonicity:** stronger measured support for s alone cannot improve the opposing side's strength or silently flip s to −s; it may change `CONFLICT_REVIEW` to a contested s under the registered margin.
- **Opposing-evidence visibility:** one contrary sub-observation is retained as a counter-case, not an automatic veto. R-4 reports transitions among `CONFIRMED_STRUCTURE`, `SINGLE_SOURCE_STRUCTURE`, `CONTESTED_DIRECTION` and `CONFLICT_REVIEW`, plus geometry-completeness counts, for every threshold setting considered before the untouched outcome cohort.

**Phase B (later; not part of the first release).** Once SOR-001 S3/S4 deliver point-in-time C4 packets per geometry that meet the TEV-001 §4.1 floors:
- Assignment adds `direction_state ∈ {SUPPORTED, OPPOSED, UNSUPPORTED, INSUFFICIENT_EVIDENCE}` per geometry (spec §9, note 02 expectancy bounds).
- It selects by the R-H rule: the highest lower-bound expectancy.
- A structurally assigned side that C4 finds OPPOSED is **not flipped**. It is published as OPPOSED, and the opposite geometry becomes its own candidate thesis (note 02).
- Phase B gains authority only through spec §24 and G1–G4.

### 4.5 Field contract and legacy adapter

**New canonical fields.** These are written once. Structure fields come from the kernel. `thesis__*` fields come only from the assignment function.

| Field | Values / type | Notes |
|---|---|---|
| `thesis__side` | BULL / BEAR / UNASSIGNED | Canonical (spec §7 vocabulary); Thesis-owned namespace |
| `thesis__direction_status` | from §4.4 | The adapter derives the legacy `discovery_direction_status` from it |
| `thesis__direction_basis` | structured text (families, sub-evidence, bar dates) | Legacy `discovery_direction_basis` is derived from it, so it enters the governed record hash (Options :4692) |
| `thesis__side_assignment_policy_version` | `side_assign_v1` | **Not** `direction_policy_version`: that existing field must equal `strangle_resolution_v1.1.0` and is checked at `direction_governance.py:418` |
| `thesis__evidence_independence` | `SINGLE_FAMILY_OHLC` / … | Honest label (P4) |
| `thesis__unassigned_reason` | enum (§4.4 rows 2, 6a-c and DEC-1 if selected) | Required only when UNASSIGNED; a missing stop is not an unassigned reason |
| `geometry_status` | COMPLETE / INCOMPLETE_GEOMETRY / NOT_ASSESSABLE | Separate from `thesis__side`; missing or wrong-side stop does not erase a supported direction |
| `target_state` | LEVEL / NONE | NONE is valid when no structural target is sourced; never implies a synthetic target |
| `bull_evidence_json`, `bear_evidence_json` | sub-evidence with strengths and dates | Structure-owned; mirror-tested |
| `bull_invalidation`, `bear_invalidation` (+ `_source`, `_sigma`) | price / null + reason | Required-for-side |
| `bull_target_state`, `bear_target_state` | LEVEL / NONE | Spec §7 |
| `bull_target`, `bear_target` (+ `_source`, `_sigma`) | price / null | Structural only |
| `bull_reference_level`, `bear_reference_level` | price | Display only; never a target or barrier |
| `wyckoff_mode_v2`, `wyckoff_phase_bucket_v2` | mode-aware (incl. DISTRIBUTION/MARKDOWN/UNKNOWN) | The legacy bucket is kept unchanged for the v7 key (§4.6.4) |
| `side_neutral_score`, `tier` | as today, from side-neutral inputs | Tier semantics unchanged; inputs cleaned |

**Legacy adapter** (`legacy_direction_adapter_v1`, one function, versioned). It writes **every** legacy field that a consumer reads as a side, and they must all agree:
- `direction`
- `discovery_direction_preliminary`, which Options reads **first** under `DISCOVERY_GOVERNED` (Options :4682-4692)
- `discovery_direction_status`
- `discovery_direction_basis`
- `direction_authority`

A guard test asserts all five are consistent on every row.

| Canonical `thesis__side` | `direction` and `discovery_direction_preliminary` | `direction_authority` | Other legacy fields |
|---|---|---|---|
| BULL | CALL | `DISCOVERY_GOVERNED` (kept literal; DEC-4) | See the rules below |
| BEAR | PUT | same | mirror |
| UNASSIGNED, reason `TRANSITION_MIXED_TREND` | STRANGLE (until DEC-3) | same | invalidation and target null; both per-side fields populated |
| UNASSIGNED, any other reason | UNRESOLVED | same | as above |

**How the other legacy fields are filled for a BULL row** (BEAR is the mirror):
- `governed_invalidation_spot` = `bull_invalidation`, with `governed_invalidation_source` = `WYCKOFF_VALIDATION` when the level comes from the validator range, as today.
- `structural_target` = `bull_target` only when its state is LEVEL; otherwise it is null.
- `structural_target_source` keeps the literal `WYCKOFF` for Wyckoff-derived structural levels. New structural sources require DWN-04 first.
- `stop_loss` = `bull_invalidation` or null, never the ATR or 0.97 fallback.

**Why keep `DISCOVERY_GOVERNED` for now.** It is the literal that makes Options *record* rather than *re-resolve* (Options :4686-4698), and the C5 packet requires it (`descriptive_forecast_handoff.py:129`). Changing it would re-open the legacy resolution path, which would then run on retired evidence families. The spec-correct owner name (`THESIS_GOVERNED`) is introduced in Phase B alongside a C5 composer (DEC-4).

**One row per ticker is preserved.** Both sides live in columns, so the `duplicate ticker` guard (`test_descriptive_forecast_handoff.py:63`) stays green.

### 4.6 Vanguard: side-correct evaluation

#### 4.6.1 Input contract

- Add `thesis_context: ThesisContext` to `VanguardInput` (`vanguard/schemas/input_schema.py`). It carries `thesis__side`, `thesis__direction_status`, `thesis__side_assignment_policy_version`, both candidate geometries (invalidation/target/σ) and `evidence_session`.
- The adapter (`orchestrator_adapter.py`) fills it from `pkg["discovery"]`, which already carries the row in both modes (`build_packages_from_discovery.py:385-436`; `thin_package.py:172`).
- If the context is missing, the value is `NOT_EVALUATED(THESIS_CONTEXT_MISSING)`, never a default side.
- **Echo, never overwrite.** `vanguard_signals.csv` gains `thesis__side`, `thesis__direction_status` and `thesis__side_assignment_policy_version`, copied verbatim. A test asserts Vanguard output side fields equal the Discovery input for every row (continuity; `test_ddd_thesis_direction` pattern).
- **`analysis_timestamp`** becomes the evidence-session cut from the package, not `datetime.now()` (adapter :162-167).

#### 4.6.2 No direction vote

- `EdgeDetector._determine_direction` (`edge_detector.py:503-534`) is removed as a producer. A characterisation test is written first; none exists today.
- The legacy columns `edge_direction`, `layer2__edge_direction` and `layer2__probability_direction` are written as `NONE`, with a new `edge_direction_status = RETIRED_USE_SIDE_EVIDENCE`. They are not copied from the thesis side, because that would be circular if anything still counted it as evidence.
- The candidate replacement for `final_recommendation` is `STAT_EDGE_{quality}_{h}` for the **assigned** side's validated evidence, or `STAT_NOT_APPLICABLE_UNASSIGNED`. During V-A this is a namespaced shadow value only. Options must not continue using the legacy `EDGE_STRONG` substring as a side-neutral scope rule, nor use the V-A replacement to scope contracts. Any replacement scope rule requires v8 qualification, a population/outcome comparison and separate authority approval (VNG-08).
- The same change must also:
  - remove the Options fabrication at :4643-4658 (DWN-02);
  - remove the ACTUARIAL family from `collect_resolution_evidence` (DWN-01);
  - replace EIL's retired edge-direction dependency with a typed descriptive status; only a separately approved v8-qualified side block may later drive `signal_type` routing (DWN-03).
  - retire the Vanguard direction vote in EOD and Options arbitration; show side evidence as an observation without making V-A a conflict gate (DWN-13).
  
  Otherwise the vote reappears elsewhere.

#### 4.6.3 Per-side evidence blocks

Vanguard always publishes both blocks, `side_bull__*` and `side_bear__*`, built by one side-parameterised function. The assigned side's block is also aliased as `side_assigned__*` for convenience.

**Stage V-A: interim, from existing database columns, no rebuild.** Every field carries `metric_basis`:

| Field (per side s) | Definition | Basis label |
|---|---|---|
| `p_close_favourable_{5,10,20}d` | BULL: P(ret > 0); BEAR: P(ret < 0) (existing `raw_prob_up/down_*`) | `CLOSE_TO_CLOSE` |
| `signed_mean_return_close_{5,10,20}d`; `signed_mean_log_return_close_{5,10,20}d` | s × mean arithmetic return and s × mean log return, respectively, from the same matched cohort | `CLOSE_TO_CLOSE_RESEARCH`; neither is geometry-specific expected value |
| `p_touch_favourable_{k}` | BULL: `max_gain ≥ e^k − 1`; BEAR: `max_drawdown ≤ e^(−k) − 1` (existing excursion columns) | `TOUCH_ONLY_UNORDERED` |
| `p_touch_adverse_{k}` | mirror of the above | `TOUCH_ONLY_UNORDERED` |
| `sample_size`, `match_method`, `is_exact`, `dims_dropped` | from the repaired match (§4.6.5) | — |

**Empty or thin samples.** An empty sample gives `NOT_EVALUATED(NO_MATCH)` for the whole side block. There are no 0.0 probabilities and no fallback gains of 0.05/−0.03 (today's `actuarial_query.py:162-194, 1107-1123, 680-701`), because a BEAR block that reads as a measured 0 is a silent bias.

Stage V-A **does not claim first-passage probabilities**. The unordered touch fields cannot say which barrier came first; the label says so (R6).
The v7 state key and historical cohort have not yet passed the v8 version-equivalence and point-in-time tests. Consequently every V-A field is `SHADOW_DESCRIPTIVE_ONLY`: it may be compared, displayed with provenance and evaluated retrospectively, but may not set a production edge gate, rank, trade-ready label, C5 calibrated probability, or Options scope. The signed close-to-close means are in-sample underlying-return summaries, not calibrated, geometry-specific ticker EV or option EV. Exact log-reflection equality applies to the **log-return** statistic; arithmetic returns transform nonlinearly and are tested against their corresponding transformed values, not asserted to be identical after a sign flip.

**Mirror testing of V-A.** The v7 match key is itself asymmetric (RSI > 55 / < 40, accumulation-only buckets, NEAR_HIGH precedence), so an end-to-end "reflected history → swapped blocks" test cannot pass before v8. For Stage 3 the mirror test is therefore **unit-level**: on a fixed matched cohort, reflecting the cohort's forward paths must swap the BULL and BEAR blocks within tolerance. The end-to-end mirror test is a Stage 4 exit criterion.

**Stage V-B: after the database build in §4.6.4.** Adds point-in-time, geometry-aware first-passage fields per side, reusing `domain/forecast_path_label.py` as the single label owner (SOR-001 §3.3):
- `p_target_first_{d}`, `p_stop_first_{d}`, `p_event_free_{d}`
- `n_censored`, `n_ambiguous`
- time-to-event distribution quantiles (with no sentinel)
- signed survivor return quantiles
- `n_eff` with 20-session blocks
- `estimation_reliability_state` (TEV-001 vocabulary)

These feed C5/Phase B. They are shadow until spec §24.

**Legacy upside fields are kept but namespaced.** `win_rate_*`, `prob_up_*`, `expected_value_*`, `raw_prob_stop_hit`, `raw_expected_time_to_target`, `recommended_hold_days`, `kelly_fraction` and `probability_edge` stay in their current columns for the phase-2 baton and display. Each gets a companion `*_side_basis = BULL_ONLY_LEGACY`. No consumer may use them for a BEAR row after cut-over; `raw_prob_stop_hit` also gets `LABEL_MISSPECIFIED_LEGACY`.

#### 4.6.4 Actuarial database: mirrored, point-in-time labels (v8, offline)

v7 stays untouched. A new calculation version is built by the existing builders (`scripts/build_actuarial_v7*.py` → `v8`), which refuse to overwrite the live path. It is built from `actuarial_core_v7._forward_outcomes_arrays`, the only place that holds ordered forward bars. The v8 labels:
- For each side, horizon (5/10/20) and pre-registered geometry grid, in σ units: `TARGET_FIRST | STOP_FIRST | NEITHER | AMBIGUOUS_SAME_BAR | CENSORED(reason)`, using the `forecast_path_label` convention (a same-bar double touch counts as STOP_FIRST and is flagged).
- `event_session` is NaN when there is no event, never 20.
- `label_observed_session`, plus a bar-version fingerprint, so that `label_available_at ≤ training cut` can be enforced.
- Mode-aware Wyckoff labels from the **same corrected C3 code** replayed on historical cuts (SOR-001 S3). The v7 fallback of Phase B/ACCUMULATION is not relabelled.
- Legacy columns are recomputed identically and parity-tested, so v7 consumers are unaffected.

#### 4.6.5 Match-contract repair (prerequisite for any side-correct statistic)

| Defect | Repair |
|---|---|
| Live `structure_quality` is a constant 25 (WEAK); the database means RSI-based | Compute the live value with the **database definition** (`actuarial_core_v7:155`) from live RSI. The VWAP "above" bull score is removed (`state_calculator.py:609-642`). |
| Trend and maturity definitions differ, and EARLY semantics are opposite | Use the database definitions (core_v7 :130-136) for the live state. Supply the 52-week dates, or mark maturity `UNKNOWN`. |
| Wyckoff bucket (legacy) is accumulation-only | Keep the legacy key for v7 parity. Add `wyckoff_mode_phase_key` (already built by SOR-001) as the v8 key. |
| Missing EMA/ADX/RSI become 0/0/50; `adx_14` is ignored when there are ≤ 20 bars | Typed missing, and the operator-precedence bug is fixed (runner :866-870). A missing input drops the dimension **and** sets `is_exact=False`, `match_method=DIMENSION_DROPPED`. |
| Missing match dimensions are still tagged EXACT | As above (`actuarial_query.py:485-530, 861-871`). |
| No point-in-time cut | `ActuarialQueryEngine.query(state, as_of)`: fails closed without `as_of`, loads `ticker`/`date`/`label_observed_session`, applies a 20-session embargo, and computes the baseline on the same point-in-time cohort (SOR-001 §4.5 hard prerequisite). |
| `macro_regime` is in the match key | Removed from the key (rule 6). The fallback that already drops it first shows the database supports matching without it. |
| Relative volume uses the wall clock; `Timestamp.now()` | Use the evidence-session cut (`state_calculator.py:499, 664-683`). |

#### 4.6.6 Gates, quality and timing: per side

The table below describes **candidate side-correct replacements**, not authority granted to Stage V-A. First implement and compare them in shadow; any production edge-quality/routing promotion requires the v8 version-equivalent point-in-time labels, registered outcome comparison and governing G1–G4 decision. Vanguard always evaluates the assigned thesis; it never owns the side or the execution decision. Until promotion, downstream consumers must not treat `side_assigned__has_edge` or `side_assigned__edge_quality` as a trusted gate.

| Legacy behaviour | New behaviour |
|---|---|
| Gate 5 uses long EV and P(ret > 0) (`edge_detector.py:283-296`) | In V-A, publish the assigned side's `signed_mean_return_close_20d` and `p_close_favourable_20d` as shadow diagnostics only. Do not feed either into a production veto, rank or trade-ready decision. For UNASSIGNED, publish both sides without a gate verdict. A later gate proposal must use supported, side-correct v8 evidence and separate authority approval. |
| CONTINUATION/TRANSITION fast paths use long EV (`:307-349`); signal type is bull-only (`actuarial_query.py:744-756`) | Compute mirrored candidate diagnostics in shadow, with location (NEAR_HIGH/NEAR_LOW) taken relative to the side; do not activate their fast-path routing from V-A statistics. |
| Trend-exhaustion veto keyed to the state trend (`:408-446`) | Keyed to the assigned side: a BULL late in an uptrend near the high is exhausted, and a BEAR late in a downtrend near the low is exhausted. A reversal thesis (BEAR at a late-uptrend high) is not vetoed. It is labelled as a counter-trend thesis. |
| Right-side score is bull-only (`:569-593`) | Side-mirrored. |
| `early_candidate` is bull-only (MID_RANGE/NEAR_LOW) (`state_calculator.py:553-563`); sideways maturity treats only ACCUMULATION as BUILDING (`:582-597`; database `actuarial_core_v7.py:153-154`) | Mirrored per side (NEAR_HIGH for BEAR; DISTRIBUTION is also BUILDING). The database mirror lands in v8, and the v7 behaviour is kept for parity. |
| `edge_quality` STRONG = EV20 ≥ 0.03 and P(up 10%) ≥ 0.40 (`main.py:247-255`) | Shadow quality is computed on the assigned side's block and labelled `UNVALIDATED_SIDE_COMPARISON`; it cannot affect Options scope or trade authority. UNASSIGNED → `NOT_APPLICABLE_UNASSIGNED`. Promotion requires v8 and held-out evidence. |
| `preferred_horizon` by highest long EV (`main.py:44-66`) | Shadow candidate chosen from the side block and labelled `SELECTED_IN_SAMPLE`; it is not a hold instruction or production routing input. It stays out of matching (existing guard). |
| `raw_expected_time_to_target` = median with a 20 sentinel | Stage V-B time-to-event quantiles with censoring counts. The legacy field is namespaced. |
| `recommended_hold` | Retired as a thesis property (ACK D2): the thesis window is 1–20. The legacy field is kept for display and labelled `LEGACY_FALLBACK`. |
| Earnings/IV vetoes (never fire today) | Converted to **display flags** with `NOT_EVALUATED` when the date is missing (rule 6: event guards are display-only). |

#### 4.6.7 Other Vanguard defects fixed in the same stage

- **Open-contract governance** (runner :1462-1477):
  - always write a pass or reject row, so the C5 reconciliation holds;
  - the contract direction default becomes a required field, with no CALL default (`trade_governance.py:239`).
- **`behaviour_state_key` direction dimension** equals `thesis__side`, not `edge_direction` or `selected_contract_side` (`behaviour_state_builder.py:117-133`).
- **Physics** `force_alignment_score`: stop reading `edge_direction` and the macro label (`physics_state_engine.py:221-245`). The physics output remains display-only (addendum D4).
- **Lineage relabel to V6_DB/VALID:** validated or labelled `ASSERTED_NOT_VALIDATED` (runner :1160-1176). Discovery `win_probability` no longer seeds win rates (runner :1178-1203).
- **Dead code quarantined**, with a test proving it is unreachable and outputs are unchanged:
  - legacy auction path (`auction_synthesizer.py:69-517`, `control_identifier`, `value_*`, `market_profile`);
  - `layer2_statistical/scenario_builder.py`;
  - Vanguard's use of `layer3_execution/*` (the EIL's inline copy is out of scope and is noted as risk);
  - `_adjust_for_intraday_context`;
  - the discarded EV v2 call in `edge_detector`.

### 4.7 Downstream adapter changes (continuity)

| ID | Consumer | Change | Why it is required |
|---|---|---|---|
| DWN-01 | `direction_governance.collect_resolution_evidence` (:158-227) | Remove the ACTUARIAL family (Vanguard edge direction). The CATALYST, RELATIVE_STRENGTH and PRICE_FLOW families are marked retired per spec A.2 and addendum D2/D4. They remain readable only for replay of historical runs, never for new runs. Move thresholds to versioned configuration. | Otherwise a retired, circular vote survives. It is inert for fresh DISCOVERY_GOVERNED rows but live in the legacy adapters. |
| DWN-02 | Options `parse_structural_context` (:4643-4658) | Delete the fabrication of the Vanguard edge direction from raw up/down probabilities. Read `thesis__side` via the adapter for all side logic. | A hidden direction writer. |
| DWN-03 | EIL `_derive_signal_type_from_vanguard` (:2853-2867), `_direction_arbitration_row` (:2558-2585) | Retire the `edge_dir in {"CALL","PUT"}` test without substituting the governed side as an edge flag. V-A `side_assigned__has_edge` and `side_assigned__edge_quality` remain shadow/descriptive; they cannot promote CURRENT_EDGE, momentum tier or EOD status. A later v8-validated and separately approved consumer may use them. Arbitration presents the thesis and opposing side evidence, not a Vanguard vote. **Characterise the momentum-tier distribution first; R-4 reports the diff.** | Prevents a circular or unvalidated edge promotion when `edge_direction` becomes NONE. |
| DWN-04 | C5 packet (`descriptive_forecast_handoff.py:85-154`) | Read `thesis__side` first (BULL/BEAR/UNASSIGNED), falling back to the legacy `direction` map for historical runs. Attach both candidate geometries, `geometry_status` and the shadow `side_assigned__*` block with its `metric_basis`. A directed `INCOMPLETE_GEOMETRY` row remains descriptive but cannot claim a complete trade plan. Stop attaching the upside-only `layer2__edge_quality` as context for BEAR rows. **Target gate:** today only `structural_target_source == "WYCKOFF"` is kept (`:149-152`). Replace that with the target-state rule (LEVEL + structural source list in configuration) before any new structural source is emitted, or every new target is silently nulled. | A critical Evening step, and the most fragile consumer. |
| DWN-05 | `validate_direction_record` (:390-424), `_policy_hash()` (:232-252), finaliser (:930-937) | Accept a declared set of `{dir_calc_version, direction_policy_version, direction_policy_sha256}` **tuples**: current plus previous. Removing a family (DWN-01) or moving thresholds to configuration changes the policy hash, not just the version. Record the tuple per row, and make the uniformity check "uniform within a run". Add version dispatch so Lab replays of runs older than the previous release validate against their own tuple. Flat-field comparison uses `normalise_side` on both sides. | Removes the Evening→Morning release trap (`DIRECTION_VERSION_INVALID`, `DIRECTION_POLICY_HASH_INVALID`). |
| DWN-06 | `pretrade_focus.project_evening_thesis` (:282-334) | Replace `direction_resolution_call/put_score` and PRICE_FLOW with the assigned side's evidence block and the opposing side's block. Characterise first (`test_evening_thesis_decision.py:53-86`). | The Evening bucket depends on the retired scores. |
| DWN-07 | Strict `in {"CALL","PUT"}` sites (EIL :2350; `handoff_contract_audit.py:478-606`; `lab_control.py:1933, 2342`; `morning_gate.py:1581`; `execution_gate.py:123`) | No behaviour change, because the legacy field stays CALL/PUT. Add guard tests with BULL/BEAR/UNRESOLVED tokens so any future leak fails loudly, not silently green. | Skipped capital blocks and false-green audits. |
| DWN-08 | `domain/thesis_direction.normalise_direction` (:77-100; substring tests :90-93) | Exact-token vocabulary map. Combined, ambiguous or unknown tokens → UNRESOLVED. Today *any* token containing PUT/SELL/BEAR/SHORT maps to PUT, and one containing CALL/BUY/BULL/LONG maps to CALL. So `BULL|BEAR` → PUT, `BUYERS` → CALL, and `INPUT_MISSING` → PUT. **Characterise the callers first**, because some may rely on the loose matching. | A latent mis-mapping on both sides. |
| DWN-09 | `pipeline_interpreter/direction_conflict_resolver.py` | Stop counting a Vanguard verdict as a CALL/PUT vote. Present side evidence as observations (narrative has no authority; spec). | Stops a retired vote re-entering through the Interpreter. |
| DWN-10 | Lab (`lab_control.py`, `intelligence_lab.py`, `static/index.html`) | Display `thesis__side`, `thesis__direction_status`, `geometry_status`, `target_state`, `thesis__unassigned_reason` when relevant, and both candidate geometries. A directed row with incomplete geometry remains in the directional view, visibly non-actionable as a trade plan; UNASSIGNED also remains visible and non-tradeable. **Remove the Lab side cascade** (`intelligence_lab.py:1690-1716`). It falls back through `_intent_side`, `_factor_side`, `layer2__edge_direction`, `dominant_trend`, `catalyst_direction_bias` and `selected_contract_side`, which *recomputes* a side for unresolved rows. The Lab shows the governed side or "unassigned", nothing else. | Transparency; spec §26 ("Lab recomputes…" is forbidden). |
| DWN-12 | Options `_governed_structural_target` (:4545-4575) | When the thesis target state is NONE, do not backfill with an L1_FAR or 3R target. Publish `target_state = NONE`; valuation uses stop and forced-exit paths (spec §7, note 02 principle 4). | Otherwise the new `NONE` targets are silently replaced with formula targets. |
| DWN-13 | Arbitration in EOD `_direction_arbitration` (`eod_candidate_engine.py:1076-1102`, drives `direction_conflict_gate`) and Options `_direction_arbitration_oi` (:407-455) | Remove Vanguard `edge_direction` as an opposing vote. Publish any V-A opposing-side strength/ratio as a descriptive counter-case only; it cannot set `direction_conflict_gate` or alter contract scope. `NO_PROBABILITY_OPINION` is explicit when both blocks are NOT_EVALUATED. A later v8-based conflict rule requires outcome validation and separate approval. | Retires the vote without silently turning an unvalidated comparison into a veto. |
| DWN-14 | `scripts/actuarial_enrichment_pass.py` (:397-446, :697-751) | Fix the trend vocabulary mismatch (BULLISH/BEARISH vs the cache's UP/DOWN). Label the returned `win_rate_*`, `expected_move_*` and `avg_days_to_10pct` as `BULL_ONLY_LEGACY`. Remove `macro_regime` from its key (rule 6). The side-correct replacement arrives with v8. | Upside-only outputs presented as side-neutral (audit #61, M23); 70% confidence, because `lookup_state` is out of repo. |
| DWN-15 | Morning path beyond :1581: `morning_gate.py:228-243` (`_ensure_governed_direction_record`, legacy resolution), `:1650-1674` (sector alignment), `:2521` (skew alignment); `market_structure/service.py` (double distribution vs governed direction) | Legacy resolution: no ACTUARIAL family (DWN-01). The alignment displays read the governed side. Characterise each with a Morning golden replay. | Morning consumers must see the same side and evidence as Evening. |
| DWN-16 | `ev_engine_v2.py` (`EVInputs.direction="CALL"` default, :33, :190), used by the EIL | Make direction a required argument with no default. Out of stage but on the same side-default pattern; route to the EIL owner. | A CALL default reachable from the EIL. |
| DWN-11 | Post-Discovery macro rewrite (`apply_macro_enrichment_to_discovery.py`, `contracts/macro_enrichment_delta.py:412-555`) | Write macro enrichment to namespaced `macro_advisory__*` columns only. Never overwrite `macro_direction_authority`. Remove `macro_direction_vote`/`macro_raw_direction_hint` from the Discovery CSV, or rename them `macro_advisory__side_hint` with a display-only label. Use the same run-scoped macro snapshot as Discovery. | Rule 6; one owner per fact (R2). |

---

## 5. Fix register

Stages refer to §7. Every fix follows the same sequence: characterisation test, failing business-rule test, minimal change, then mirror test.

### 5.1 Discovery

| ID | Finding (Appendix A ref) | Fix | Key tests | Stage |
|---|---|---|---|---|
| DSC-01 | Range-break counters are downside-only (W2, W3, W7) | One `range_break(bars, prior_range, s)` giving break and fail-back counts for both sides, with log-distance thresholds | Mirror: a downside break-reclaim fixture reflects to an upside break-fail fixture | 1 |
| DSC-02 | Buyer-only uncapped `reclaim_count*3` (W4) | Symmetric, capped control evidence: fail-back for sellers equals reclaim for buyers, and follow-through failure is mirrored. Weights go to configuration. | Mirror; cap; characterisation of legacy scores | 1 |
| DSC-03 | UTAD from a downside break; Spring/UTAD tie → Spring → LONG (W8, W9, W10) | Spring only from a downside break plus reclaim; UTAD only from an upside break plus fail-back. An EQUILIBRIUM tie → `AMBIGUOUS_TEST`, which is side-neutral. `max()` is banned on side-bearing dicts. | Tie fixture → UNASSIGNED; static check | 1 |
| DSC-04 | Phase B `ST`/`Test` are long events (W11, W12a) | Side-neutral `ST@LOW`/`ST@HIGH` by location. A side is inferred only through the control/intent evidence for that side. | Mirror; "low volume alone never produces a side" | 1 |
| DSC-05 | Phase A: BC → SHORT without SC → LONG (W12b) | Mirror SC/BC | Mirror | 1 |
| DSC-06 | Momentum override is up-only (W1) | Mirror the override with symmetric log thresholds (`ln(1+roc_20) > ln 1.3` and close > log-EMA50 ↔ `ln(1+roc_20) < −ln 1.3` and close < log-EMA50 → C/D→B), or remove both. **Characterise first.** Update the three BIAS tests. | Mirror; updated `test_directional_bias_fixes.py:229/248/277` | 1 |
| DSC-07 | Precor mode/intent defaults BUY/ACCUMULATION (P1, P5, P6, P7, P9) | Mode is `UNKNOWN` when data is insufficient or drift is exactly zero. Intent requirements are mirrored (Phase C SELLERS no longer needs extra conditions that BUYERS does not; drop the Phase E BUY fallback in favour of WAIT). | Mirror; "insufficient never BUY" | 1 |
| DSC-08 | `_reconcile_intent` asymmetric; bull-only helpers (D2-D6) | Symmetric helpers (`ema_stack` BULL_ALIGNED/BEAR_ALIGNED on log EMA, `days_beyond_ema50(s)`, `log_distance_from_52w_extreme(s)` with threshold ln 1.25). Rules 1-3 mirrored with the same thresholds; fix the docstring 40/60 discrepancy. | Mirror; characterisation of legacy outcomes | 1 |
| DSC-09 | Fusion is not independent (F-1, G1) | Fusion stays as a readiness/intent indicator. Its direction becomes a STRUCTURE sub-evidence (control), no longer a separate vote. `direction_evidence_independence` is labelled. | Assignment counts one family | 1 |
| DSC-10 | EMA stack decides TRANSITION; EMA200 on 30 bars (F6, D1, G4) | TREND is a context family; its use in assignment follows DEC-1. EMA200 requires ≥ 200 completed bars, otherwise `TREND_INSUFFICIENT_HISTORY`. | Insufficient history → no trend side | 1 |
| DSC-11 | Validator mode defaults to ACCUMULATION; invalidation for one side only (V1, V2, D21) | Mode UNKNOWN by default. Invalidation computed for **both** sides from the prior range (low for BULL, high for BEAR). Stop taking the side-conditioned Wyckoff `stop_loss` first (`validator:188-190`); it is built for one side only. | Both sides present; mirror | 1 |
| DSC-12 | Geometry for the rejected side; formula targets; `abs()` R:R; target validity uses Wyckoff direction (D19, D20, D22, D24, W18) | Per-side geometry (§4.3 step 5). Target `LEVEL`/`NONE`. Signed R:R per side, null when the target is NONE. Validity is checked per side. | Spec §7 invariants; mirror | 1 |
| DSC-13 | Long-only `stop_loss`; Tier-0 overwrite of `control_state`/`phase` (D8, D19) | `stop_loss` comes from the adapter: the assigned side's invalidation or null. Tier-0 writes to its own `early_*` fields and never overwrites. | ATR fallback never becomes invalidation (existing guard) | 1 |
| DSC-14 | Accumulation-only buckets (D9-D11, D14) | Add `wyckoff_phase_bucket_v2` (mode-aware) and event-family labels (side-neutral or mirrored). The legacy bucket stays for the v7 key until v8. | Legacy parity; v2 mirror | 1 |
| DSC-15 | Mislabelled drop reasons (F15, G2-G8) | Typed eligibility reason codes (§4.3 step 2). Thresholds unchanged pending DEC-2. | Reason-code test per filter | 1 |
| DSC-16 | Hidden tier-4 drop; `date.today()` decay; non-monotonic composite; VMS uplift (F10, F11, U2, U4, U5) | Decay measured in XNYS sessions from the evidence session. Monotone composite (compression cannot lower a score). VMS removed from the tier and published as a display field. The tier-4 drop keeps its behaviour but is logged with its reason. **Knock-on:** `composite_score` / `win_probability` feed Options `ev_structural` (:6802-6803) and the Options scope via tier (:9876), so R-4 must report both. | Monotonicity; run-date invariance | 2 (shadow first; changes the population) |
| DSC-17 | Direction-conditioned ranking scores (D15-D18) | Published per side; the sort key uses side-neutral terms | Mirror; UNASSIGNED not penalised in ordering | 2 |
| DSC-18 | Dead asymmetry gate; dead `trend_maturity`; duplicate `crabel_score` key (§3.1 #15, D28) | Stop emitting asymmetry geometry, or rename it `asymmetry_reference_*`. Remove the dead late-trend branch. Resolve the duplicate key as `crabel_score_atr` and `crabel_score_precor`. | Unreachability; output parity except the renamed fields | 2 |
| DSC-19 | STRANGLE in Discovery (F10, D23) | Canonical UNASSIGNED with `TRANSITION_MIXED_TREND`. The adapter keeps STRANGLE until DEC-3. | Adapter mapping | 1 |
| DSC-20 | A scan exception crashes the whole run (§3.1; `lifecycle_errors` always 0) | Per-ticker `ERROR` lifecycle outcome with the exception type. The run continues, and the row is visible. | Fault-injection test | 2 |
| DSC-21 | Macro rewrite and snapshot mismatch (M1, M2, §3.1 #17) | DWN-11 | Rule-6 guard test | 2 |
| DSC-22 | Precor phase silently overrides the Wyckoff phase when its constant confidence is higher; `phase_evidence_strength` then holds Precor's constant (D27) | Publish both phases with their sources. The phase used for buckets is chosen by an explicit, versioned rule. The mislabelled column is renamed. | Provenance test | 2 |
| DSC-23 | `TEST_OF_SPRING` in the HIGH set with no `TEST_OF_UTAD` (D12); `AR` classed as a long event (W12a) | Mirror the event sets. `AR` becomes side-neutral with a location, because an AR after a BC is bearish. | Mirror | 1 |
| DSC-24 | Precor C→D confidence is higher for bullish follow-through (78 vs 70) (P9) | Same confidence for mirrored follow-through | Mirror | 1 |
| DSC-25 | New literals introduced by this design (≥ 200 bars, 20-session embargo, `k` log thresholds, θ_event/θ_control, ≥ 2 sub-evidence types) | All in versioned configuration (spec Appendix B; `CLAUDE.md`). `MIN_EVIDENCE_FAMILIES`/0.60/0.20 move there too (`direction_governance.py:35-37`). | Configuration-contract test | 1 |

### 5.2 Vanguard

| ID | Finding | Fix | Key tests | Stage |
|---|---|---|---|---|
| VNG-01 | No thesis input; direction dropped (§3.2 #2) | `ThesisContext` in `VanguardInput`, filled by the adapter, echoed in the CSV | Continuity: output side = input side for 100% of rows | 3 |
| VNG-02 | `_determine_direction` CALL default and circular PUT (#3) | Remove as producer; legacy columns `NONE` with a status field (§4.6.2) | Characterise, then "neutral → no side"; nothing reads `edge_direction` as a side | 5 (cut-over) |
| VNG-03 | Upside-only metrics (#4) | Side blocks V-A (§4.6.3); legacy fields namespaced | Mirror: reflected history → swapped side blocks | 3 |
| VNG-04 | Upside-only database labels; sentinel; mis-specified stop label (#4) | v8 mirrored first-passage labels (§4.6.4) | Mirror on synthetic paths; v7 parity; no sentinel | 4 |
| VNG-05 | No point-in-time cut (#7) | `query(state, as_of)` fail-closed, with embargo | Future rows excluded; missing `as_of` raises | 3 |
| VNG-06 | Live/database state mismatch; missing → 0/50; dropped dimension still EXACT (#6) | §4.6.5 | Live/database parity on shared fixtures; typed missing | 3 |
| VNG-07 | Trend-keyed veto; long-EV gates; bull-only right-side score and signal type (#8) | §4.6.6, shadow comparison only until v8 validation and authority decision | Mirror; counter-trend thesis not vetoed; no V-A trade promotion | 3 |
| VNG-08 | Upside `edge_quality`/`final_recommendation` drives Options scope | Assigned-side quality may replace the legacy consumer only after v8 outcome validation and authority approval; V-A quality remains shadow and cannot scope Options | Population diff on Options scope (R-4); no V-A routing | 5, conditional |
| VNG-09 | Timing sentinel; `recommended_hold` | V-B timing; the legacy field namespaced (ACK D2) | No value equals 20 because of a non-hit | 4 |
| VNG-10 | `macro_regime` in the match key; physics uses macro and edge direction (#9) | Removed (rule 6) | Rule-6 guard | 3 |
| VNG-11 | Open-contract `continue` → C5 reconciliation abort (#10) | Always emit a row; contract direction required | Reconciliation test with an open contract | 3 |
| VNG-12 | Wall-clock timestamps (#7) | Evidence-session cut | Replay determinism (R7) | 3 |
| VNG-13 | Dead bullish code | Quarantine (§4.6.7) | Unreachability; output parity | 6 |
| VNG-14 | Behaviour key direction = Vanguard default | = `thesis__side` | Key test | 3 |
| VNG-15 | Asserted lineage; Discovery win-probability seeding | Validate or label; remove seeding (R1) | Lineage test | 3 |
| VNG-16 | Earnings/IV vetoes inert | Display flags; `NOT_EVALUATED` when missing | Rule-6 guard | 3 |
| VNG-17 | Empty or thin samples read as measured zeros (M12, M13, M15); Discovery `win_probability` seeding (M18) | Typed `NOT_EVALUATED(NO_MATCH)` side blocks (§4.6.3); no fallback gains | "Missing never 0" test per side | 3 |
| VNG-18 | Bear-only tier demotion in the runner (dead: it affects only a dropped copy) (runner :724-737) | Quarantine with VNG-13 | Unreachability | 6 |

### 5.3 Downstream

DWN-01 … DWN-16 as in §4.7. DWN-02, 03, 05, 12 and 13 are **cut-over blockers** (Stage 5): VNG-02 cannot ship without them. DWN-04's target gate must ship before any new structural target source is emitted.

---

## 6. No-regression framework

**Definition.** A change is a regression if it does any of the following:
- causes a crash, an abort or a broken contract;
- turns a currently green guard test red;
- changes any output that is not attributed to a registered fix ID;
- makes the side-level outcome on matured history worse;
- breaks symmetry.

Deliberate, attributed changes to biased behaviour are **intended changes**. They are reported, not hidden.

| ID | Control | How it is measured | Pass condition |
|---|---|---|---|
| **R-1** | **Characterise before change** (`CLAUDE.md` working rules) | Golden replays of stored runs: `20260926_173730` (the SOR-001 frozen baseline), plus at least one **normal** post-close Evening run and its Morning run (not the forced 11 Sep runs). Every Discovery, Vanguard and C5 output is pinned by characterisation tests. Includes the missing tests: `_determine_direction` neutral → CALL; Options fabrication; Phase C tie; Phase B ST → LONG. | Characterisation suite green on current code before any fix |
| **R-2** | **Mirror invariance** | (a) *Rule level:* each side-bearing function f satisfies `f(reflect(x)) = mirror(f(x))` on fixtures and on property-based random OHLCV, using the log reflection of §4.2. (b) *Population level:* reflect every ticker's bars in a stored run (K = that ticker's last close, so price-level eligibility is unchanged) and rerun Discovery structure and assignment offline, restricted to tickers eligible in both universes. | (a) Equality within 1e-9 relative tolerance, on fixtures that avoid exact threshold values. (b) `count(BULL, reflected) = count(BEAR, original)` and vice versa, `UNASSIGNED` equal, and a per-ticker mirrored reason. Any failure = regression. Holds only for kernel-covered quantities (§4.2 table); anything outside the kernel is excluded from side evidence by design. |
| **R-3** | **Attribution diff** | Run legacy and shadow side by side on every replay run. Diff per ticker and field. Every changed field must carry the fix ID(s) whose rule fired, so each fix emits a trace in shadow mode. | 0 unattributed differences. A table of attributed differences by fix ID is published with each stage receipt. Each fix has **its own flag** within a stage, so fixes are enabled and measured one at a time (`CLAUDE.md` rule 4, one defect at a time). Interacting fixes are measured singly first, then together. |
| **R-4** | **Population and run-health report** | Per replay run: counts of CALL/PUT/UNRESOLVED/STRANGLE; `CONFIRMED_STRUCTURE`/`CONTESTED_DIRECTION`/`CONFLICT_REVIEW` and `geometry_status` independently; tiers; the `validate_quality` ratios (15% candidates, 1.5% Tier-0, T1+T2 > 0) projected **before** cut-over; Options scope count; chain requests; EOD candidates; Lab rows; runtime. | No projected `validate_quality` abort. If one is projected, stop and escalate to ACK (DEC-6), never loosen silently. All deltas explained by R-3. |
| **R-5** | **Reality check (outcome scorer)** | Using `avshunter/c12_outcome` on a pre-registered, matured, point-in-time same-start cohort, compare legacy and new assignment **paired by ticker, evidence session and eligibility**, including changed-side, newly directed and newly UNASSIGNED rows. Report side-specific signed return in σ, target/stop incidence where sourced, coverage, adverse outcomes and missed large winners over sessions 1–20. Preserve censoring and use at least 20-session market-date dependence blocks with market/sector clustering. Freeze the non-inferiority margin and comparison policy on earlier evidence before inspecting the held-out cohort. | Require the paired effect's uncertainty bound to meet the pre-registered non-inferiority margin for each side and disclose coverage/missed-winner costs; overlapping separate intervals are not a pass. If there is inadequate independent support or point-in-time provenance, report `NOT_ESTIMABLE` and obtain ACK review; do not silently promote. Canonical OHLCV replay limitations remain explicit. |
| **R-6** | **Guard tests** (Appendix B) | All GUARD tests stay green unchanged. GUARD* tests change only vocabulary or fixtures, with the business rule unchanged, and each diff is reviewed. BIAS tests are replaced by mirrored versions, with a recorded reason. New guards are added *failing-first*: the 16 listed in Appendix B, including assignment purity, incomplete-geometry direction retention, non-vetoed contrary observations and a ban on V-A gate/rank/scope authority. | 100% green; every changed test listed in the receipt with its reason |
| **R-7** | **Version crossover** | Test: an Evening record at `dir_v1.2.0` validated by a Morning run at `dir_v1.3.0` (DWN-05). Release rule: releases happen **after a Morning run and before the next Evening run**. | Crossover test green; release calendar recorded |
| **R-8** | **Rollback** | Versioned flags are temporary shadow/verification and emergency rollback controls, not a permanent opt-in route or dual production authority. At approved cut-over, the corrected policy is the default for every normal run; legacy execution is disabled and retained only for an explicitly governed rollback drill. Artefacts remain immutable. An offline rollback drill reproduces the legacy golden replay after normalising run-varying fields, or after DSC-16 and VNG-12 remove those fields. | Drill passes; the production default and retirement conditions are recorded |
| **R-9** | **Whole-suite and manual proof** | Full offline suite, one file per process with a short `--basetemp` (`CLAUDE.md`). ACK then runs one manual Evening and Morning proof, with an acceptance checklist covering C5 reconciliation, handoff audit and finaliser status. | Suite green; proof checklist all PASS |

**Why the mirror test matters most.** It is the only control that proves "direction-agnostic until the data assigns" *mechanically*, without relying on a reviewer spotting every asymmetric line. It also catches any new asymmetry introduced later, including one in an unrelated fix.

---

## 7. Build sequence

The loop per stage follows SOR-001 §6: domain definition → failing tests → minimal change → component tests → contract tests → offline replay → integrated regression → evidence receipt. Commits happen only when ACK asks (`CLAUDE.md`).

| Stage | Content | Flag / mode | Exit evidence |
|---|---|---|---|
| **0: Baseline** | R-1 characterisation; golden replays; guard inventory; the missing modules audited (§9); the mirror harness built and run on *current* code, which is expected to fail, with the failure list becoming the Stage-1 work list. | none | Characterisation green; mirror-failure list reconciled with Appendix A |
| **1: Symmetric Discovery (shadow)** | DSC-01…15, 19, 23-25 and the assignment function (§4.4), each isolated for attribution before integration, writing **shadow** fields `sym_*` / `thesis_side_shadow`. Direction and geometry completeness are tested independently; opposing evidence may yield a contested side. Legacy `direction` is unchanged. | Temporary `discovery_direction_policy = legacy` while shadow is measured | R-2 exact; R-3 attributed; R-4 projected; R-5 paired comparison on matured history |
| **2: Discovery hygiene (shadow)** | DSC-16…18, 20-22, DWN-11 | shadow | Same as Stage 1, plus run-date invariance |
| **3: Side-correct Vanguard V-A (shadow)** | VNG-01, 03, 05, 06, 07, 10, 11, 12, 14, 15, 16, 17. Side blocks and echo written; legacy fields unchanged. V-A statistics are labelled descriptive and have no production gate, rank, scope or edge authority. | Temporary `vanguard_side_evidence = shadow` | Fixed-cohort unit mirror test (not an end-to-end v7 mirror claim); live/database discrepancies and point-in-time coverage reported; no V-A routing |
| **4: v8 labels (offline)** | VNG-04, 09; v8 build and parity; SOR-001 S3 episode replay dependency | offline | v7 parity; mirrored labels; point-in-time and state-definition equivalence; TEV-001 §4.1 floor audit (reported, not weakened). No numerical authority from a merely successful rebuild. |
| **5: Cut-over** | Switch legacy `direction` to the adapter from `thesis__side`; retire Vanguard direction votes; apply DWN-01…16 and the version-tuple crossover. VNG-08 side-quality routing is conditional on separately validated v8 support and approval; otherwise publish side evidence without promotion. Prove directed incomplete-geometry rows retain side but not trade-plan readiness. | Corrected direction policy is the default for every normal run after approval; temporary rollback only | R-2…R-9 all pass for the scope promoted; ACK manual Evening/Morning proof; rollback drill; no unvalidated V-A decision authority |
| **6: Retire** | VNG-13, 18; remove legacy code paths after N normal sessions (ACK to set N) | — | Unreachability tests; final receipt |
| **Phase B (later)** | C4-based `direction_state` and R-H selection; C5 composer; `THESIS_GOVERNED` authority literal | spec §24 progression | G1–G4 |

**Dependency on the in-flight work.** SOR-001's build (prior range, typed Crabel state, mode×phase key) is uncommitted in the working tree, and TEV-001 is marked "build in progress, not tested". Stage 0 must start from a **committed and tagged** baseline that includes or explicitly excludes that work, so that every characterisation and diff has a stable reference (R7, R8).

---

## 8. Decisions for ACK

| # | Decision | Options | Recommendation | Population effect |
|---|---|---|---|---|
| **DEC-1 — ACK resolved 1 Oct 2026** | Trend-only assignment (TRANSITION + EMA stack, §4.4 row 5) | (a) Keep: assign with status `TREND_ONLY`, labelled weak. (b) UNASSIGNED(`TREND_ONLY`). | **(b) approved.** A direction requires explicit qualifying structural support. Trend-only rows remain visible as UNASSIGNED with `thesis__direction_status=TREND_ONLY` and `thesis__unassigned_reason=TREND_ONLY`; any aligned trend is context, not a CALL/PUT assignment. | R-4 quantifies the reduction in directed rows; R-5 reports their later outcomes separately |
| **DEC-2** | Options-motivated Discovery filters (price 5–500, ADV$ ≥ 2.5M, ATR$ ≥ 0.40, ATR% ≥ 1) | (a) Keep as ticker eligibility with correct reason codes. (b) Move the option-motivated ones to C6 so they no longer shrink the ticker universe. | **(a) now, (b) as a separate design.** Moving them enlarges the universe, which raises provider cost and runtime and trips the `validate_quality` ratios, so it is out of scope for a no-regression release. | none under (a) |
| **DEC-3** | STRANGLE | (a) Keep emitting it via the adapter for `TRANSITION_MIXED_TREND`. (b) Retire it: UNRESOLVED everywhere; Lab strangle tests re-expressed. | **(a) until DWN-10 ships, then (b).** | none under (a) |
| **DEC-4** | Authority literal | (a) Keep `DISCOVERY_GOVERNED` and move the policy owner to the Thesis-owned function (§4.4). (b) Introduce `THESIS_GOVERNED` now. | **(a)** until Phase B | none |
| **DEC-5** | Opposite-side candidate for directed rows | (a) Display both geometries and both evidence blocks in the Lab (display only). (b) Publish the opposite geometry as its own candidate thesis now (note 02). | **(a)** now; (b) in Phase B | none |
| **DEC-6** | `validate_quality` thresholds if R-4 projects an abort | (a) Re-baseline them from the symmetric shadow run on normal sessions. (b) Keep them, and fix the cause instead. | Decide on evidence from Stage 1/2. The thresholds must not be loosened silently. | — |
| **DEC-7** | Relationship to SOR-001 | Approve this document as the symmetry and assignment amendment to SOR-001 S1/S2/S4 | Approve | — |
| **DEC-8** | Retired evidence families (CATALYST, RELATIVE_STRENGTH, PRICE_FLOW) | (a) Remove them from new-run resolution now (DWN-01). (b) Keep them. | **(a)**, per spec A.2 and addendum D2/D4. Replay of historical runs stays readable. | none for fresh DISCOVERY_GOVERNED rows; resolution was already disabled |
| **DEC-9 — ACK resolved 1 Oct 2026** | Where the assigned side lives before a C5 composer exists (spec §7: StructureAssessment "must not contain final trade direction") | (a) Accept, as a documented interim, the Thesis-owned `thesis__*` namespace written in the Discovery process, with no C3 read-back (§4.4). (b) Hold assignment until the SOR-001 S5 composer ships. | **(a) approved as a time-limited ownership exception.** The process may write `thesis__*`, but C3 structure remains direction-free and cannot read it back. Move this ownership to C5 at Phase B. | none |
| **DEC-10** | Later C5 macro/sector conditioning | (a) Keep macro/event evidence display-only under `CLAUDE.md` rule 6. (b) Permit independently sourced, point-in-time measured macro/sector context to condition C5 move/timing probabilities under signed TEV-001 §4, but never own Discovery direction or become a standalone veto. | **Pending explicit ACK authority resolution.** This DIR-002 release excludes macro from Discovery assignment under either choice; do not change C5 macro behaviour on an assumption. | none for Discovery; possible later C5 forecast change |

---

## 9. Risks, gaps and confidence

| Item | Risk | Mitigation |
|---|---|---|
| Modules not audited: `canonical_data/{feature_flags,historical_prices,session_clock,registry}.py`, `actuarial_cache_builder.py` (out of repo), the scripts that post-process the v7 parquet, `avshunter_trap_engine.py`, `orchestrator/dynamic_validation.py`, `avshunter/c12_outcome/*` | Unknown direction handling or point-in-time behaviour | Stage 0 audits them before any claim of no regression. The v7 post-process scripts must be located or reconstructed, because a bare `actuarial_core_v7` build does not satisfy `REQUIRED_ACTUARIAL_V6_COLUMNS` (85% confidence). |
| EMA200 history length | F6 severity depends on the actual bar count (70% confidence). If Discovery sees only about 62 bars (the 90-day legacy lookback), the ≥ 200-bar rule means TREND is never assessed. Under ACK's DEC-1(b), a row with no qualifying structural support is UNASSIGNED regardless; missing trend history must be distinguished from an observed trend-only row. | Stage 0 confirms the actual bar count and R-4 separately counts `TREND_ONLY` and `TREND_INSUFFICIENT_HISTORY`. Do not lower the 200-bar rule to manufacture trend evidence. |
| SOR-001 made F2/F3 more active | Current live runs may be more CALL-skewed than before 27 Sep (85% confidence) | Stage 0 population report quantifies it; Stage 1 fixes it |
| Macro rewrite overwrite | Depends on the enrichment delta being present (90% confidence) | DWN-11 removes the path regardless |
| TEV-001 support floors | C4 packets may be `NOT_ESTIMABLE` for a long time; S0 found zero matured 20-session paths in the governed cohort | Phase A assignment does not depend on C4. Phase B waits; the floors are never weakened. |
| Mirror test and real asymmetry | Reviewers may read unequal BULL/BEAR counts on real data as a bias | R-2 tests the rules on reflected data; R-5 tests reality. Report both. |
| Morning-side consumers of `stop_loss` beyond those audited | A long-side value was consumed somewhere unseen | Stage 0 greps every consumer. The adapter makes `stop_loss` side-correct or null, never long-only. |
| EIL loads EV v2.1.0 (75% confidence) | Outside this stage | Noted for the EIL owner |

---

## Appendix A: Evidence index (condensed)

**Discovery direction inventory.** The IDs match the 30 Sep audit working file.

| Group | IDs and lines |
|---|---|
| Wyckoff asymmetric | W1 157-167 · W2 350-358 · W3 363-368 · W4 403-408 · W7 520-523 · W8 715-722 · W11 673-684 · W12a/b 884-885 |
| Wyckoff defaults | W9 723-728 → 179 · W10 884-891 |
| Precor | P1 277 · P5 647-651 · P6 691-696 · P7 727-732 · P9 774-776 (P2/P3/P4 symmetric) |
| Discovery | D2 252-261 · D3 264-290 · D4-D6 320-335 · D8 561-562/2247-2248 · D9 658-690 · D10 818-828 · D11 693-740 · D15-D18 1686-1741/1912-1924 · D19 1796-1800 · D20 1801-1816 · D21 1822-1840 · D22 1964-1976 · D23 2078-2089 · D24 1984-1988/2091-2097 · D28 1390/1595-1602 |
| Validator | V1 81-90 · V2 187-198 |
| Fusion | F-1 124-135 |
| Governance | G1 dg 84-90 · G3 td 77-100 (substring tests 90-93) · G4 td 117-127 |
| Macro | M1 enrichment 212-235 · M2 136-265 |
| Scanner (out of band) | S1 1364 · S2 1336 · S3 2059-2064 · S4 2291 · S5 ~1670 · S6 discovery 1412-1417 |
| Drops | G2-G8 discovery 1298-1639; reason written 2570-2580 · run abort orchestrator 2113-2200 |

**Counts:**
- 21 asymmetric rules on the core path (26 including the scanner and macro display);
- 10 bullish defaults and 1 bearish default;
- 5 direction producers feeding 1 frozen field, 2 of them the same signal.

**Vanguard side inventory:** 69 rows.

| Category | Rows |
|---|---|
| Produce a side | 7 (#1, 40, 41, 48, 53, 69, 57/58 carry) |
| Default to CALL | 5 (#1, 9, 49, 54, 68) |
| Upside-only | 24 (#2, 4-6, 9-17, 34-39, 42, 50, 60, 61, 67…) |
| Asymmetric | 20, including 3 wrong-sign or bug cases: #3 wrong-sign trend vote, #13/35 mis-specified stop label, #65 PUT targets above spot |
| Trend-keyed | 1 (#8) |
| Dead | 11 |
| Point-in-time items | L1-L15 |
| Missing-treated-as-measured | M1-M27 |

Key lines: `edge_detector.py:503-534, 283-349, 408-446, 569-593` · `actuarial_query.py:53-95, 485-530, 666-724, 744-756, 861-871, 1100-1130` · `actuarial_core_v7.py:130-168, 268-365` · `state_calculator.py:492-533, 609-642, 664-683, 807-812, 862-883` · `main.py:44-66, 247-255, 357-396, 523` · `orchestrator_adapter.py:141-284` · runner `:655-889, 1160-1244, 1462-1497`.

## Appendix B: Guard tests

**GUARD, must stay green unchanged:**
- `test_direction_governance_contract.py`: :61 (ambiguity never CALL), :123 (confirmed side cannot be overwritten), :166, :183, :204, :220 (Options leaves WAIT unresolved even with a Vanguard CALL), :238, :260, :279, :290
- `test_ddd_thesis_direction.py`: continuity and no reversal
- `test_direction_geometry_semantic_repairs.py`: :33, :41, :55 (ATR fallback never governed), :93-:120
- `test_descriptive_forecast_handoff.py`: :47, :63 (one row per ticker), :77, :100, :131, :201
- all `test_avs_tev001_*`; all `test_avs_sor001_*`; `test_wyckoff_phase_validator.py`; `test_missing_invalidation_authority_withheld.py`
- `test_directional_bias_fixes.py`: :73-160 (macro advisory-only), :169, :190, :334-437
- `test_macro_enrichment_discovery_options.py` (GUARD*: DWN-11 changes its subject to namespaced advisory columns; the SOR-001 receipt reports it hanging, so diagnose it in isolation first)
- `test_vanguard_production_fixes.py`: :106 (`preferred_horizon` not a match dimension), :114, :184
- `test_vanguard_reference_input_p2.py`; `test_package_free_evening_p4.py`; `test_handoff_contract.py`
- `test_actuarial_cache_v7_contract.py`: :108 (`never_crosses_direction`)
- `vanguard/tests/test_vanguard_contract.py`

**GUARD\*, where the business rule stays and only vocabulary or fixtures change:**
- `test_direction_governance_contract.py`: :66, :96, :312
- `test_direction_geometry_semantic_repairs.py`: :67
- `test_descriptive_forecast_handoff.py`: :29
- `test_thesis_geometry_review_labels.py`; `test_lab_strangle_direction.py` (after DEC-3)
- `test_vanguard_production_fixes.py`: :150/:160/:175 (add bearish mirrors)
- `vanguard/tests/test_actuarial_match_ladder.py`: :154/:177; `vanguard/tests/test_phase2_baton_validation.py` (versioned baton)

**BIAS or retired, to be replaced with a recorded reason:**
- `test_directional_bias_fixes.py`: :229/:248/:277 (upside-only momentum override → mirrored)
- `test_direction_governance_contract.py`: :75, :136, :150 (catalyst family → "retired family never counts")
- `test_evening_thesis_decision.py`: :53-86 (PRICE_FLOW → side evidence; characterise first)

**New guards, added failing-first:**
1. C5 packet with BULL/BEAR and with UNASSIGNED/UNRESOLVED, and no Evening abort.
2. Strict-set consumers given BULL/BEAR/UNRESOLVED tokens: no silent skip.
3. `normalise_direction` on combined tokens returns UNRESOLVED.
4. Options with the Vanguard edge absent does not fabricate a side.
5. `_determine_direction` characterisation, then its retirement.
6. Mirrored price series give mirrored Vanguard side blocks and v8 labels.
7. `DIR_CALC_VERSION` crossover.
8. Population-diff harness (R-3/R-4).
9. Rule and population mirror tests (R-2).
10. Static ban on `max()` over side-bearing dicts.
11. Assignment signature purity: no Vanguard, macro, option or scanner input.
12. Open-contract reconciliation row.
13. Missing or wrong-side geometry retains a supported BULL/BEAR side, but cannot claim complete trade-plan readiness.
14. One contrary sub-observation remains visible without automatically making the thesis UNASSIGNED; a genuinely indeterminate comparison remains unassigned.
15. V-A side quality, horizon and counter-case never set a production EIL/EOD gate, Options scope, rank or trade-ready label.
16. R-5 compares paired same-start outcomes against a frozen non-inferiority margin; overlapping marginal intervals alone cannot pass.
