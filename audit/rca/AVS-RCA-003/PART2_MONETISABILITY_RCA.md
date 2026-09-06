# AVS-RCA-003 Part 2 — Where valid Discovery candidates cease to be monetisable

**Primary run:** `20260905_151448` (latest; DDD runtime profile v1.0.0 `2b416bbe…`). No post-closure run exists.
**Contrast runs:** `20260904_122358`, `20260904_004338`.
**Network requests: zero.** Everything below is computed from stored artefacts and source.
**Companion data:** `02_cohort_20260905_151448.csv`, `03_funnel_20260905_151448.csv`, `04_reason_classification.csv`, `05_s1_timevalue_revaluation.csv`, `05_s2_contract_selection.csv`, `05_s2b_band_sensitivity.csv`, `05_s3_target_asymmetry.csv`.

---

## 1. The answer, in two sentences

**Valid Discovery candidates stop being monetisable at a single stage — the Options contract-quality gate — where 727 of 1,293 total losses (56%) are discarded on quote spread, and the funnel is essentially decided before monetisability is ever computed.** Re-evaluating every one of those losses against its own stored option chain shows **94.4% is ECONOMIC** — no contract in the horizon's DTE and delta bands had a tradeable spread — leaving roughly **120–200 candidates per run recoverable by widening the selection bands**, plus **10 rows per run mis-labelled by an intrinsic-only monetisability model that can only produce false negatives**.

A correction to the brief's framing that matters: on this run the Lab book is **232 MONETISABLE / 23 NOT_MONETISABLE / 27 DATA_MISSING / 12 LIMITED**, not the ~110/105/22/19 quoted. Those were the `20260904_004338` figures. Monetisability among rows that *reach* the Lab is now 79%; the attrition is upstream.

---

## 2. The funnel

`03_funnel_20260905_151448.csv`. Reconciles exactly: **1,293 lost + 294 survived = 1,587**.

| Boundary | Survivors | CALL | PUT | OTHER | Lost |
|---|---|---|---|---|---|
| Discovery selected | 1,587 | 834 | 466 | 287 | — |
| Vanguard row | 1,537 | 834 | 466 | 237 | 50 |
| Options row | 1,461 | 833 | 459 | 169 | 76 |
| EOD row | 1,461 | 833 | 459 | 169 | 0 |
| **Lab book** | **294** | **190** | **104** | **0** | **1,167** |

The funnel is flat until the EOD boundary and then collapses. But the EOD engine is not where the decision is made — it is where a decision already taken at Options is *applied*. `eod_candidate_engine.py:2772-2779` builds `manifest_mask = ~hard_block & ~options_blocked & (trigger_go | carry_forward_status)`, and `_options_blocked_for_morning_candidate` (`:488-498`) simply re-reads the Options verdict.

**There is no candidate cap.** `MORNING_VALIDATION_MAX_CANDIDATES = 0` (`intelligent_orchestrator.py:515`), and `:3011-3014` applies a cap only when non-zero. The 294 is not truncation — it is what survived the gates. I checked this first because a silent cap would have been the single largest design finding available; it is not there.

### Losses by reason

| Reason | CALL | PUT | OTHER | Total | Class |
|---|---|---|---|---|---|
| `OPTIONS_BLOCKED:BLOCK_SPREAD` | 417 | 243 | 0 | **660** | ECONOMIC 94.4% / DESIGN 5.6% |
| `EOD_NO_OPTIONS_ROUTE:NO_LIQUID_OTM_CONTRACT` | 1 | 2 | 169 | 172 | by design (non-directional) |
| `EOD_STRUCTURAL_BLOCK:MISSING_GOVERNED_INVALIDATION` | 135 | 32 | 0 | 167 | DESIGN — protection working |
| `OPTIONS_STAGE_ABSENT` (no governed direction) | 1 | 7 | 68 | 76 | by design |
| `OPTIONS_BLOCKED:CONTRACT_REVIEWABLE_SPREAD` | 39 | 28 | 0 | 67 | ECONOMIC |
| `EOD_NOT_IN_MANIFEST:EOD_TRIGGER_READY` | 28 | 27 | 0 | 55 | DESIGN |
| `VANGUARD_REJECT_OR_NO_ROW` | 0 | 0 | 50 | 50 | DATA |
| `EOD_NOT_IN_MANIFEST:EOD_THESIS_READY_REPAIR_AT_OPEN` | 23 | 4 | 0 | 27 | DESIGN |
| `OPTIONS_BLOCKED:STRUCTURAL_TARGET_UNRESOLVED` | 0 | 19 | 0 | 19 | DESIGN |

**Spread accounts for 727 of 1,293 losses (56%).** Everything else is a long tail.

---

## 3. S1 — Intrinsic-only monetisability

**Method.** For every Lab row with ask, strike, target, IV and DTE present (267 of 294), re-value the option with Black–Scholes at the structural target on the **final session of the planned hold** — `T = (dte − hold_days)/365`, σ = the contract's own `contract_iv` held constant, r = 0, q = 0, dividends ignored — and compare profit against the same 20% floor.

The current model is `contracts/selected_contract_economics.py:574-583`:
```python
breakeven       = strike + entry_ask          # CALL
target_intrinsic= max(target_spot - strike, 0)
target_profit   = target_intrinsic - entry_ask
```
Its own version string is `MONETISABILITY_CALCULATION_VERSION = "expiry-intrinsic-floor-v2-advisory"`.

**Result.**

| From ↓ / To → | LIMITED | MONETISABLE | NOT_MONETISABLE |
|---|---|---|---|
| LIMITED (12) | 5 | **7** | 0 |
| MONETISABLE (232) | 0 | **232** | 0 |
| NOT_MONETISABLE (23) | 3 | **3** | 17 |

- **10 of 35 sub-monetisable rows flip to MONETISABLE**; 8 more improve to LIMITED; 17 stay NOT_MONETISABLE.
- **Zero MONETISABLE rows fail.** This is not luck: Black–Scholes value ≥ intrinsic for all inputs, so **intrinsic-only is a strict lower bound and can produce false negatives but never false positives.** The reverse test the brief asks for is therefore answerable analytically, and the data confirms it.
- The flip is direction-skewed: **9 CALL, 1 PUT** to MONETISABLE.
- Ignored time value is negligible in the median (\$0.00, 0.1% of ask) because most MONETISABLE rows are deep enough for intrinsic to dominate. **It matters precisely at the margin, which is where the classification flips.**

The clearest case is **PNW CALL**: strike 100, ask \$0.85, target 100.82, breakeven 100.85. It misses by **3 cents** and is labelled `STRUCTURAL_TARGET_DOES_NOT_CLEAR_BREAKEVEN` at −3.53%. With 8 DTE still remaining at the target and IV 18.7%, Black–Scholes values it at **+84.5%**.

**Verdict: DESIGN.** AR-003 §7.10 predicted this exactly. Scale: 10 rows per run — 3.4% of the Lab book, 0.6% of the funnel. It is a real defect and it misinforms the operator, but it is **not** the main attrition driver. It is also **advisory only**, so it blocks nothing.

---

## 4. S2 — Contract selection: could a better contract have been chosen?

**Method.** For all 774 `BLOCK_SPREAD` rows, load the ticker's own stored `OPTION_CHAIN` payload (1,289 chains, JSON, from `dataset_registry`) and test every contract on the correct side against the horizon's own bands (`DTE_CONFIG`, `scripts/avshunter_options_intelligence.py:1214-1218`) and the 25% spread gate. Attribute each ticker to the first gate that no contract could clear.

| Verdict | Count | % | CALL | PUT |
|---|---|---|---|---|
| ECONOMIC — no tradeable spread within the bands | **426** | 55.0% | 263 | 163 |
| ECONOMIC — no expiry inside the DTE band | 161 | 20.8% | 116 | 45 |
| ECONOMIC — no strike inside the delta band | 144 | 18.6% | 92 | 52 |
| **DESIGN — a viable contract existed and was not chosen** | **43** | **5.6%** | 23 | 20 |

The 43 DESIGN cases had an alternative at a **median 14.9% spread** and \$2.38 mid — comfortably tradeable. Examples: `CAH` CALL 250 strike / 13 DTE / δ0.41 / **8.1% spread**; `POET` CALL 8.5 / 20 DTE / δ0.40 / **7.4%**; `MOS` PUT 26.5 / 13 DTE / δ0.57 / **10.5%**.

**Verdict: 94.4% ECONOMIC.** The option market genuinely does not offer a tradeable long single-leg structure for most of these theses. The median blocked contract has a **62% spread on a \$2.00 mid** — a round trip costing well over half the premium. And these are not junk underlyings: median price \$50.94, only 2.6% below \$10.

### 4.1 The finding underneath the finding

The gate-by-gate survivorship is more informative than the verdict:

| Gate | Median contracts surviving per ticker | Tickers with zero |
|---|---|---|
| correct side (CALL or PUT) | 74 | 0 |
| inside the DTE band | 20 | 161 |
| **inside the delta band** | **1** | **305** |
| clearing the spread gate | 0 | 731 |

**The median ticker has exactly one contract inside the delta band.** The `1_5d` band is δ 0.40–0.60 — a window 0.20 wide. Selection has essentially no choice: if that single contract carries a wide quote, the ticker is lost, even when the chain holds a tradeable contract 0.05 of delta away.

This is not "the selector picked badly" — it is "the selector was given one candidate". That reframes the recoverable opportunity, and S2b measures it.

---

## 5. S2b — Band sensitivity (the recoverable-opportunity measurement)

Holding the 25% spread gate **fixed**, how many of the 774 `BLOCK_SPREAD` losses have a contract on their own stored chain that clears it within widened bands?

| Scenario | Recoverable | % | CALL | PUT |
|---|---|---|---|---|
| baseline (δ 0.40–0.60, 7–21 DTE) | 74 | 9.6% | 43 | 31 |
| δ ± 0.05 | 106 | 13.7% | 60 | 46 |
| δ ± 0.10 | 135 | 17.4% | 72 | 63 |
| δ ± 0.15 | 164 | 21.2% | 90 | 74 |
| DTE ± 7d | 123 | 15.9% | 69 | 54 |
| DTE ± 14d | 130 | 16.8% | 75 | 55 |
| **δ ± 0.10 AND DTE ± 7d** | **195** | **25.2%** | 111 | 84 |
| δ ± 0.15 AND DTE ± 14d | 233 | 30.1% | 135 | 98 |

**Widening the delta band by ±0.10 and the DTE band by ±7 days recovers 121 additional candidates per run** (195 − 74) without touching the spread threshold — i.e. without accepting a single trade the current liquidity policy would reject.

This is a measurement of *availability*, not of profitability: each recovered candidate would still have to clear economics and the monetisability floor. It is the ceiling on the opportunity, not the realised value.

---

## 6. S3 — Target-ladder asymmetry: the prior finding is refuted for this run

AVS-RCA-002 found PUT 42 vs CALL 12 blank structural targets on `20260904_004338` and inferred a direction-asymmetric design flaw. **That asymmetry has reversed and largely closed:**

| | CALL | PUT |
|---|---|---|
| blank `structural_target` | 149 | 40 |
| `economics_reason = STRUCTURAL_TARGET_UNRESOLVED` | 133 | 58 |
| as a share of that direction's rows | **16.0%** | **12.6%** |
| median `rr_options` where a target exists | **4.449** | **4.365** |

The rate difference is 3.4 points in the *opposite* direction to the prior finding, and R:R medians are within 2% of each other. **Verdict: no material direction asymmetry in the current run.** The absolute CALL count rose because the CALL population is 1.8× the PUT population. I am reporting this as a refutation of a prior finding I contributed to, not as a new defect.

---

## 7. S4 — Spread threshold and denominator

**The denominator is consistent.** `domain/long_option_execution.py:45-66` defines `quote_spread_fraction(bid, ask) = (ask − bid) / mid` with the docstring "Every production consumer uses this definition." The unit chaos AVS-REV-003 reported across spread bases is **fixed**.

**Thresholds:** `LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT = 18.0`, `LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT = 25.0` (`domain/long_option_execution.py:16-17`). The terminal Options gate uses the reviewable 25%.

**Is 25% a cliff?** Distribution of the 774 blocked rows, as the gate measured them: p10 29%, p25 37%, **p50 62%**, p75 120%, p90 194%, max 200%. **31.4% are at or above 100%**, which is a bid at or near zero (spread/mid = 200% exactly when bid = 0). Only **172 rows sit in (25%, 35%]** — the band where a different threshold would plausibly change the answer.

So 25% is **not** a cliff for the bulk: the median blocked contract is more than twice the threshold. Moving the gate to 35% would admit 172 rows whose execution cost is a third of premium — which is a policy question, not a defect.

**One real inconsistency.** `DTE_CONFIG` defines per-horizon spread bands (15% / 25% / 35%) but the terminal gate applies a flat 25%. For `1_5d` candidates the flat gate is **looser** than the horizon's own 15% band — 3 rows passed the terminal gate that the `1_5d` band would have blocked. Small, but the two rules disagree and only one can be the authority. Filed as **RCA3-D07**.

---

## 8. S5, S6, S7 — ordering, data, Morning

**S5 — ordering effects.** AR-003 §5.1's complaint stands: Horizon runs after Options. But no candidate in this run had its economics computed under a hold that Horizon then changed — `horizon_bucket` is present on the Options rows and is what the DTE bands were keyed on. **Count: 0.** Not a live loss channel in this run.

**S6 — data availability.** 50 tickers lost at the Discovery→Vanguard boundary (`run_vanguard_from_packages.py:1399-1456` rejects when OHLCV or `regime_snapshot` is absent), all OTHER-direction. Plus 46 `PROVIDER_NO_DATA` and 50 `DATA_DEFECT` in the profile stage (`ValueError: ATR14 unavailable`). These are transient and recoverable with a retry or warm cache. **Total DATA loss ≈ 50 at the funnel boundary.**

**S7 — Morning attrition: BLOCKED.** **None of the three runs has Morning artefacts** — `20260905_151448`, `20260904_122358` and `20260901_082437` are all EOD-only; their `morning_validation/` directories hold EOD manifests, not Morning-run output. The entire Morning attrition question — overnight gaps, quote decay, EOD-vs-Morning economics basis (AVS-REV-003 mechanism 2), contract identity mismatch — **cannot be answered from stored artefacts**. It needs one Morning run on current code.

---

## 9. Step 6 — Expectancy evidence on the survivors

What the pipeline claims about the 294: median `rr_options` 4.45 (CALL) / 4.37 (PUT); 232 of 294 MONETISABLE; invalidation on the correct side 294/294 in both directions.

What outcome evidence exists: **almost none, and n is far too small for inference.**
- `data/journal/trade_journal.db`: **14 closed trades**, entries 2026-03-06 → 2026-06-24, exits to 2026-07-18, **dormant for seven weeks**. Two are `LIVE_UAT_SMOKE_FLAT` (not real trades). Three exited `EXPIRED_WORTHLESS`/`EXPIRED`. One is a recorded target hit (`T`, PUT, "Target_hit_wall_break_confirmed"). The remaining eight are broker-confirmation closes with no outcome label.
- `data/canonical/decision_outcome_ledger.sqlite`: **295 events — 294 `CANDIDATE_DECISION` and 1 `OUTCOME`.** The DDD ledger captured every candidate of the primary run and exactly one outcome.

**There is no evidence at all that `MONETISABLE` rows make money, and none that they do not.** Twelve real closed trades, three of which expired worthless, cannot support a claim in either direction. The Decision/Outcome Ledger is the right instrument and is now capturing decisions; it needs outcomes fed back before any expectancy statement is possible.

---

## 10. Recoverable opportunity, ranked

| # | Change | Recovers / run | Class | Confidence |
|---|---|---|---|---|
| **1** | Widen the contract-selection bands: δ ± 0.10 and DTE ± 7 days | **+121 candidates** | DESIGN | **High** — measured on the stored chains (S2b); each has a contract clearing the *unchanged* 25% spread gate |
| **2** | Fix contract selection so the 43 tickers with a qualifying contract actually get it | **+43** | DESIGN | High — S2; alternatives at a median 14.9% spread |
| **3** | Give monetisability a time-value model | **+10** relabelled MONETISABLE, +8 to LIMITED | DESIGN | High — S1; advisory only, so it changes the operator's read, not the slate |
| 4 | Retry/defer the 50 Discovery→Vanguard data rejects | +50 (all OTHER-direction) | DATA | Medium — transient, but non-directional so unlikely to reach the book |
| 5 | Resolve the 19 PUT + 133 CALL `STRUCTURAL_TARGET_UNRESOLVED` at source (the stop ladder) | up to +167 upstream of the invalidation block | DESIGN | Medium — fixes the cause of `EOD_STRUCTURAL_BLOCK`, not the gate |

Items 1 and 2 are the same subsystem and together are worth **~164 candidates per run — a 56% increase on a 294-row book.** That is the single highest-leverage change available, and it requires no relaxation of any liquidity or economics standard.

---

## 11. What is genuinely economic — and should be accepted

**~690 of 1,293 losses per run are the market telling the truth.** Specifically:

- **426 tickers** where no contract in the DTE and delta bands had a tradeable spread — and 31.4% of blocked contracts have spreads ≥ 100% of mid, meaning a bid at or near zero. There is no pipeline change that makes these tradeable.
- **161 tickers** where no expiry existed inside the horizon window, and **144** where no strike sat in the delta band. Widening helps some (S2b) but the residual is real chain sparsity.
- **17 of 23** `NOT_MONETISABLE` rows stay not-monetisable even with full time-value credit.

**What this says about universe/strategy fit.** The blocked names are *not* penny stocks — median underlying \$50.94, only 2.6% below \$10. So this is not a "clean up the universe by price" problem. It is that **Discovery selects on equity-thesis quality with no knowledge of options liquidity**, and roughly half its output has no viable long single-leg expression. That is a legitimate design choice — Discovery is thesis-valid, not trade-valid, by construction — but it means the funnel's shape is structural, not a defect. If the operator wants a denser book, the lever is an options-liquidity pre-filter *inside* Discovery (an ADV/OI/spread screen on the underlying's chain), not a looser gate downstream.

---

## 12. Limits

- **No Morning run exists on any stored run** — S7 is entirely unanswerable, and with it every question about overnight and quote-decay attrition.
- **No run exists under the DDD closure code** — the primary run is one release behind HEAD.
- **No warm-cache rerun exists**, so transient-vs-permanent DATA loss cannot be separated by re-resolution.
- **Outcome data is effectively absent** (12 real closed trades, dormant seven weeks; 1 ledger outcome), so no statement about realised expectancy is supportable.
- S2/S2b test *availability* of a passing contract on the stored chain. They do not assert those trades would have been profitable — economics and the monetisability floor would still apply.
- The S1 revaluation assumes constant IV, r = 0, no dividends, and values at the target on the hold's final session. It is a lower-bound-correction exercise, not a pricing model for execution.
