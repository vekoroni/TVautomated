# AVS-THS-001 — Review of the "signal starvation / tiered opportunity" thesis against the pipeline as it stands

**Date:** 2026-09-06
**Status:** Assessment only. Nothing here is authorised for build. Its purpose is to say which parts of the thesis are accurate against evidence, which would damage the pipeline if adopted as written, and what a Tier 1 / 2 / 3 definition should be made of.
**Evidence base:** AVS-RCA-003 Part 2 (per-ticker funnel and per-contract re-evaluation on run `20260905_151448`), AVS-TST-QT-001, AVS-RCA-002, AR-003, AVS-SD-002/003.
**Author's position in one line:** the thesis correctly identifies the *mechanism* (a ticker dies because one contract was tested), correctly identifies the *objective* (rank today's asymmetry rather than filter for perfection), and is wrong about the *state* (the pipeline is not starved; it is unranked and unconverted).

---

## 1. The premise is out of date, and that changes the diagnosis

The thesis is built on "the discovery always produces output but by the end of the pipeline there are zero monetisable signals." On the latest run that is not what the artefacts show:

| Stage | Count | Source |
|---|---|---|
| Discovery selected | 1,587 (834 CALL / 466 PUT / 287 OTHER) | RCA-003 §2 |
| Reach the Lab book | 294 (190 / 104 / 0) | RCA-003 §2 |
| `MONETISABLE` in the book | **232 (79%)** | RCA-003 §1 |
| `LIMITED` / `NOT_MONETISABLE` / `DATA_MISSING` | 12 / 23 / 27 | RCA-003 §1 |
| `BUY_NOW` / `BUY_SMALL` | 0 | QT-001 Track D — **by design**: Execution Gate grants at Morning, and no Morning run exists on any stored run |

So the pipeline produces a large monetisable set every night. What it does not produce is a *ranked* set, or a *converted* one — because the Morning stage that turns "monetisable" into "permitted" has not run on current code. The thesis's numbers ("Tier 1A 0–5, options-ready 1–5") describe a *narrower* output than the pipeline already delivers. The problem the thesis is solving — zero output — was true on the July runs (AVS-FIND-001: quote hydration failing 58.6% of rows; `select_best_contract` failing 55%) and is no longer the live problem.

The consequence is that the thesis's proposed *fixes* need re-aiming. The live problems are: (a) 1,293 candidates are lost between Discovery and the book, and RCA-003 shows where and why; (b) the 232 that survive are not ranked by expected option return, so the trader cannot tell Tier 1 from Tier 3; (c) Morning conversion is entirely unmeasured. The thesis addresses (a) well, (b) partially, and (c) not at all.

**The operator's objection — "a zero-monetisable day may be legitimate" is wrong for AVSHUNTER — is supported by the data.** With 3,300 tickers scanned and 232 monetisable on an ordinary Friday, a routinely empty `MONETISABLE` set would indicate a defect. An empty *Tier 1* is a different thing and can legitimately happen. The revised statement in the write-up ("Tier 1 can be empty; MONETISABLE should not routinely be empty") is the right formulation and matches what the pipeline already does.

---

## 2. Claim-by-claim accuracy

| Thesis claim | Verdict | Evidence |
|---|---|---|
| Starvation is caused by gate multiplication (8 gates × 70% ≈ 6%) | **Mostly wrong for this pipeline.** One gate dominates. Gate-by-gate survivorship on the 774 spread losses: correct side 74 contracts → DTE band 20 → **delta band 1** → spread 0. The funnel is flat from Discovery to EOD (1,587 → 1,461) and collapses at one place. | RCA-003 §4.1, §2 |
| Macro / sector / GEX act as universal vetoes | **Already fixed, and verified.** Macro cannot block, resize or choose direction (AVS-SD-003 F06–F08, QT-001 A-results); Discovery tiers and priors are macro-invariant; Horizon routes with macro absent. GEX is not a loss reason on any run. | QT-001, RCA-003 §2 reason table |
| Missing fields treated as hard fails | **Was true; fixed in cycle 1.** Missing target now yields a governed `STRUCTURAL_TARGET_UNRESOLVED` record (191 on the latest run, both directions), missing invalidation a governed structural block. These are still losses — 167 tickers at `MISSING_GOVERNED_INVALIDATION` — but they are the protection working, and the fix belongs at the stop ladder, not at the gate. | RCA-003 §2; AVS-SD-003 G-03/G-05 |
| Thresholds calibrated independently produce an impossible joint acceptance | **Not supported.** The spread threshold alone explains 56% of losses and the median blocked contract is at 62% of mid — more than double the 25% gate. Moving the gate to 35% admits only 172 rows. This is not a calibration artefact. | RCA-003 §7 |
| "One contract selected → contract fails → ticker dies" | **Confirmed — the thesis's most valuable claim.** The δ 0.40–0.60 band leaves the median ticker exactly one candidate, and 305 tickers none. 43 tickers had a qualifying contract on their own chain that selection did not choose (median 14.9% spread). | RCA-003 §4, RCA3-D06, RCA3-D08 |
| Contract repair is too weak | **Partly confirmed.** A `CONTRACT_REPAIR` route exists and 19 Lab rows sit in it, but repair does not search the chain for an alternative when the terminal spread gate fails — it is a Morning-side re-quote, not an Evening-side re-selection. | RCA-003 §4; AVS-REV-003 |
| Breakeven and expected move are not calibrated from the same horizon | **Confirmed in principle, small in magnitude.** Intrinsic-at-expiry valuation ignores time value remaining at the hold's final session; it is a strict lower bound and produced 10 false negatives out of 35 sub-monetisable rows, zero false positives. It is advisory and blocks nothing. | RCA-003 §3; AR-003 §7.10 |
| Better confirmation means worse options economics (IV already repriced) | **Plausible, unmeasured.** IV cost is not a loss reason code on any run, so nothing in the artefacts tests it. It is testable from stored chains (IV at selection vs. IV rank history) and should be measured before an "early lane" is built. | RCA-003 reason table |
| Theta consumes the move before the thesis matures | **Unmeasured.** No theta-based rejection exists; theta enters only through the intrinsic floor. The 7–21 DTE band for a 1–5 session hold is the pipeline's theta policy, and it is untested against outcomes. | RCA-003 §4.1 |
| A monetisation funnel and rejection taxonomy are needed | **Already exist, at ticker level.** Every loss carries a reason code (`OPTIONS_BLOCKED:BLOCK_SPREAD`, `EOD_STRUCTURAL_BLOCK:…`, etc.), the dropoff audit reconciles exactly, and RCA-003 built the funnel the thesis asks for. What does *not* exist is a **per-contract** taxonomy — which contracts were tested and why each failed — and that is the gap worth closing. | RCA-003 §2, `04_reason_classification.csv` |
| Direction-asymmetric loss (PUT targets fall through) | **Refuted on the current run.** CALL 16.0% vs PUT 12.6% unresolved targets; median R:R 4.45 vs 4.37. | RCA-003 §6 |
| Spread denominator inconsistency | **Fixed.** One definition, `(ask − bid)/mid`, in `domain/long_option_execution.py`. One residual inconsistency: per-horizon bands (15/25/35%) vs a flat 25% terminal gate. | RCA-003 §7, RCA3-D07 |

Net: of the failure modes the thesis lists, the ones that were real have mostly been fixed in the last three days; the one that remains — single-contract selection inside a narrow delta band — is the one the thesis diagnoses best, and it is the largest recoverable loss in the pipeline (~164 candidates per run, a 56% larger book, without relaxing the spread standard).

---

## 3. Impact on the pipeline if adopted as written — where the thesis would help and where it would hurt

### 3.1 Adopt — these are consistent with the accepted architecture and backed by measurement

**Contract universe → filter → rank → repair → select, with `EQUITY_VALID_OPTIONS_NOT_MONETISABLE` as a named terminal state.** This is the correct structure and RCA-003 quantifies its value. It also fits AR-003 §7.7's instruction to split contract *availability* from *feasibility* from *ranking*. The immediate, cheap version is DEC-2: widen δ ±0.10 / DTE ±7 days in shadow and count how many of the 121 recovered candidates clear economics. No live run is needed.

**A per-contract rejection taxonomy.** The thesis's list maps onto codes the pipeline mostly already emits at ticker level. Recording it per *contract tested* — and how many were tested — is the instrumentation that makes the repair loop auditable. This is a logging change, not a logic change.

**Horizon-consistent valuation as a second advisory field.** DEC-1's recommendation: keep the intrinsic floor as `monetisability_state` and add `monetisability_state_timevalue` with the model and assumptions named on the row. Both bounds visible; no authority change.

**A single ranked daily opportunity set.** The thesis is right that the trader currently faces five overlapping vocabularies — Discovery tier A/B/C, EOD status (`THESIS_READY` / `TRIGGER_READY` / `REPAIR_AT_OPEN`), monetisability state, viability state, capital permission — and no single ranking. A tier field *derived from those existing governed fields* (§4 below) would be the most useful thing the Lab could show. Deriving it from a new score would not.

**"Find the money → strongest expression → cheapest convexity → rank" as the objective statement.** This is a better description of the product than "authorise a trade", and it is consistent with the AVS-SD-002 posture that macro is advisory context. It belongs in the design's goals section.

### 3.2 Reject or defer — these conflict with accepted decisions or with the evidence

**A weighted 0–100 `MONETISATION_SCORE` with invented weights and 75/60/45 thresholds.** Three problems. The weights (20% breakeven, 15% delta, 15% theta…) are guesses; AR-003 §6.3 forbids "a neutral score that looks observed", and AVS-SD-002 §3.2 forbids inventing calibrated thresholds without outcome evidence. The ledger has 294 decisions and one outcome; there is nothing to calibrate against. Second, a composite score re-creates the exact defect the direction-governance work removed — a single number that blends evidence families so a failure in one is hidden by strength in another. Third, if the score gates anything, it becomes a second authority beside the Execution Gate, which AR-003 §8 forbids. The right version is: publish the *components* (breakeven distance in expected-move units, delta fit, DTE/hold ratio, spread, IV rank) as separate advisory columns now; derive weights from the ledger later, if ever.

**Macro/GEX as a *ranking* input inside Discovery.** The thesis wants "positive GEX → penalise index premium, reward single-name RS divergence" and "rising 10Y → adverse-regime relative-strength boost". As *advisory context after Discovery* this is legitimate and interesting. As a Discovery scoring input it reverses P0-03, which was closed three days ago precisely because macro was altering membership and rank. Any regime-conditional ranking must sit downstream (Lab ranking overlay, or a CT2-style market-context stage before Options) and carry its own lineage.

**"Weaken the gates" in any form, including via routing.** The thesis says not to, and the data agrees: 94.4% of spread losses are economic. But the tier/route architecture could become a soft version of it if `ARMED`/`WATCH` rows are presented next to `Tier 1` rows in the same table. The Lab must keep the hard-veto boundary visible.

**An "early lane" as a build item now.** The insight — confirmation may cost convexity — is sound, but nothing measures it. Before a lane exists, measure IV rank at selection for the 232 monetisable rows against their Discovery-day IV, and the premium at selection versus 3/5 sessions earlier. If confirmed rows are systematically buying repriced IV, build the lane; if not, the lane is a hypothesis.

**The target funnel counts.** "Discovery candidates 50–150, Tier 1A 0–5" would make the pipeline narrower than it is. Numbers should come from observed daily distributions over a few weeks of runs, as the thesis itself says in its last section, not be set as targets in advance.

---

## 4. A Tier 1 / 2 / 3 thesis grounded in fields the pipeline already governs

The thesis wants tiers to answer a *relative* question: of everything available today, where is the highest-quality positive asymmetry? That is right. The constraint is that tiers must be **derived**, not **scored** — every tier boundary must trace to a governed field with a named authority, so the tier is explainable and cannot become a second gate.

**Tier semantics.** A tier describes the *quality and completeness of the evidence* for an opportunity. It is advisory: it orders the Lab; it never grants capital. Execution Gate remains the sole permission writer. Tier 1 may be empty; the union of Tiers 1–3 should not routinely be.

| Tier | Meaning | Derived from (all must hold unless stated) |
|---|---|---|
| **Tier 1 — confirmed asymmetry** | Everything the pipeline can verify is present and strong | governed direction with lineage hash; invalidation and target present, correct side; underlying R:R ≥ 2.0; `MONETISABLE` under **both** intrinsic and time-value valuation; selected contract δ within band and DTE ≥ 2 × hold; spread ≤ the **horizon's** band (15% for `1_5d`); `execution_viability_state` pass on a live quote (Morning) — at EOD, the same on the EOD quote; trigger `TRIGGER_READY` or `THESIS_READY`; no `CONTRACT_REPAIR` |
| **Tier 2 — strong, one named weakness** | Monetisable, with exactly one identifiable shortfall that the row names | as Tier 1 but any **one** of: R:R 1.5–2.0; `LIMITED` rather than `MONETISABLE`; monetisable under time-value only; spread in (15%, 25%]; trigger not yet ready (`REPAIR_AT_OPEN`); contract at the edge of the DTE band. The weakness is written into a `tier_reason` field |
| **Tier 3 — tradeable, low quality** | Passes all hard vetoes but two or more Tier 2 weaknesses | as above with ≥ 2 named weaknesses; still `MONETISABLE`/`LIMITED`, still viable |
| **ARMED** | Equity thesis valid, options not yet monetisable, **with a named promoting condition** | `EQUITY_VALID_OPTIONS_NOT_MONETISABLE` plus one of: a qualifying alternative contract exists on the chain (the 43 + 121 cases); IV rank above a stated level with a stated fall that would flip the row; trigger absent where the thesis needs one. The condition is the `tier_reason`, so ARMED is actionable, not a bin |
| **WATCH** | Thesis-valid, no options expression today, no named promoter | `EQUITY_VALID_OPTIONS_NOT_MONETISABLE` with no chain contract inside widened bands; or `DATA_MISSING` awaiting re-resolution |
| **BLOCK** | Hard veto only | the existing list, unchanged: pathological/zero-bid spread; no liquidity; invalid/expired contract; missing governed invalidation; invalidation already breached; corrupt/stale data; direction unresolved |

**What this does to the latest run**, approximately (RCA-003 figures; exact counts need the derivation run): Tier 1 would be a subset of the 232 `MONETISABLE` rows passing the 15% horizon band and R:R ≥ 2 — likely tens, not hundreds; Tier 2 most of the remaining `MONETISABLE` plus the 12 `LIMITED`; Tier 3 the rows near the 25% edge; ARMED would hold the ~164 recoverable-by-repair tickers and any IV-priced-out rows; WATCH the ~426 with no tradeable contract in any band; BLOCK the 167 missing-invalidation and the 190 non-directional.

**Where this ensures monetisability, and where it cannot.** Tiers make the *existing* monetisable set usable by ranking it, and they turn the largest loss bucket (single-contract selection) into an actionable ARMED set with a named repair. They do not create edge. Whether Tier 1 rows make money is measured by the Decision/Outcome Ledger at 1/5/10/20 sessions, and that is the only route to turning tier boundaries from policy into calibration.

---

## 5. Limitations of this thesis

1. **Everything above is EOD-side.** The Morning stage — overnight gap through invalidation, quote decay, EOD-vs-Morning economics recomputation (AVS-REV-003 mechanism 2), contract identity — is unmeasured because no Morning run exists on any stored run. Tier assignments could move materially at the open. The first Morning run on current code is the single most informative artefact the project can produce this week.
2. **No outcome data.** Twelve real closed trades, three expired worthless, one ledger outcome. Tier thresholds are policy choices until the ledger has a few hundred matured candidates. Neither this thesis nor the operator's write-up can claim expectancy.
3. **The band-widening gain is availability, not profitability.** The 121 + 43 recovered candidates clear the spread gate; whether they clear economics and the floor is what the DEC-2 shadow replay measures.
4. **IV and theta effects are unmeasured**, so the "early lane" and "confirmation paradox" parts of the thesis remain hypotheses.
5. **The regime-rotation principle (US Money Index) is a research direction**, not a pipeline change: it needs a sector/regime evidence stage with lineage, downstream of Discovery, and an outcome test that adverse-regime relative strength has positive expectancy before it ranks anything.
6. **Every recommendation here is advisory-side.** None changes an authority; anything that would (a score that gates, macro in Discovery, tiers as permission) is explicitly excluded.

---

## 6. What I would do with this, in order

1. Run DEC-2's shadow replay of wider bands against stored chains — one offline afternoon — and publish how many recovered candidates clear economics. That decides whether the thesis's central fix is worth ~164 candidates or ~40.
2. Add the per-contract rejection record and the `contracts_tested` / `best_alternative` fields to the Options stage output. Instrumentation first.
3. Add `monetisability_state_timevalue` as a second advisory column (DEC-1).
4. Derive the tier field from existing governed columns per §4, show it in the Lab with `tier_reason`, and *observe* the daily distribution for two weeks. Do not set targets.
5. Measure IV-at-selection vs Discovery-day IV on the monetisable rows; decide on the early lane from the number.
6. Run Morning on current code; re-derive tiers on the Morning book; report how many Tier 1 rows survived the open.
7. Only then discuss weights, and only against ledger outcomes.
