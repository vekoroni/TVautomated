# Option analytics framework — review against the EV engine and the pipeline (29 Sep 2026)

Requested by ACK, 29 Sep 2026: review a proposed option-analytics framework (standard option computations, a Greek
P&L decomposition, and five trade-quality computations: expected move, required move-to-return, probability of
touch, target-before-stop, EV from an option return distribution) against the EV engine built 28 Sep (EV3 option 3,
uncommitted) and the pipeline. Evidence: the 29 Sep historical replay (`AVS_HISTORICAL_REPLAY_STUDY_PREREGISTRATION_
20260929.md`, ~200,000 signals, Sep 2022 – Sep 2026, ITM 90-day option modelled at 1.1 × realised volatility).

## 1. The framework's maths

- The standard formulas (intrinsic, extrinsic, expiry breakeven, maximum loss, return on premium, delta exposure,
  dollar delta, spread %, slippage) are correct as stated. Breakeven should use the price actually paid (the ask),
  not the mid.
- The Greek decomposition is a second-order Taylor expansion. Its example is internally consistent
  (0.90 + 0.24 − 0.55 − 0.12 − 0.10 = +0.37). It is accurate for small moves over short periods; for multi-week holds
  or large moves full repricing is required (the engine already reprices), and the decomposition is then an
  explanation of a repriced change, not the valuation itself. Units must be explicit: theta per calendar day,
  vega per one IV point.
- Expected move ≈ S × IV × √(DTE/365) is the one-standard-deviation move implied by the option market.
- EV = Σ pᵢ × payoffᵢ over the option's return distribution is the right form. The illustrative table
  (+29 % EV) is not evidence: its probabilities are assumed. Section 4 replaces them with measured ones.

## 2. EV3 (built 28 Sep) against the framework

| Framework item | EV3 | Note |
|---|---|---|
| Entry / exit execution cost | Yes | Entry = ask + 2 % of mid; exit = repriced mid × (1 − spread/2 − 2 %) |
| Option repricing at exit | Yes | American CRR at exit spot, remaining DTE, IV unchanged or −15 %; anchored to the observed mid; intrinsic floor |
| Probability of touch / target-before-stop | Partly | On the UNDERLYING's thesis target and invalidation, from state base rates (508 states); not on premium levels; no signal conditioning |
| EV from a return distribution | Partly | Three point outcomes (target, stop, timeout), each valued at one mean exit session; the timeout is valued at the entry spot (no drift, no spread of surviving paths) |
| Uncertainty | Beyond framework | Lower bound = conservative EV − probability, model, liquidity, quote and fallback uncertainty |
| Expected move vs market-implied move | No | |
| Required move-to-return | No | |
| Greek P&L decomposition | No | |
| Intrinsic / extrinsic, delta exposure, dollar delta | No (not published) | |

EV3's structural limits are the ones the TEV-001 design already names: probabilities are state base rates, not the
ticker forecast; one point per outcome instead of a path distribution; fixed hold horizons 5/10/20.

## 3. Pipeline mapping

Source: read-only code audit 29 Sep (subagent), key defects re-verified by hand (marked ✔).

| Framework item | Pipeline status | Owner | Note |
|---|---|---|---|
| Intrinsic value | Partial | `contracts/selected_contract_economics.py` (at the target only) | None at the current spot; provider `intrinsicValue` captured then dropped |
| Extrinsic value | Absent | provider `extrinsicValue` dropped in Options Intelligence | Never published |
| Expiry breakeven | Shown, three owners | OI `compute_trade_economics` (mid), monetisability (ask), Lab JS (live ask) | The shown "frozen" breakeven uses the mid; the Lab prints "+" before a put's breakeven % |
| Maximum loss | Post-entry only | Lab enter-trade API, journal | Nothing pre-trade in the book |
| Return on premium | Shown, several owners | journal, Lab monitor, c12, DOI | Mixed units (% vs fraction); monitor marks use mid/last, a Polygon fallback uses the day's (open+close)/2 as "exit premium" |
| Delta exposure, dollar delta | Absent | — | |
| Greeks | Shown | OI → `contract_delta/gamma/theta/vega` | Provider Greeks are replaced by Heston/BSM Greeks when Heston calibrates, with no provenance field; missing Greeks defaulted (θ −0.01, vega 0.05, Δ 0.35) |
| `vega_risk_pct` | Shown, **wrong** ✔ | OI:6783 | Per-share 10-point loss divided by the per-contract premium: 100× too small (vega is per vol point, e.g. MTDR 0.077) |
| Spread % | Shown | `domain/long_option_execution.quote_spread_fraction` (canonical) | ~8 inline copies; one Interpreter copy divides by the ask |
| Slippage (fill − reference) | Absent | — | Only modelled slippage exists |
| Greek P&L decomposition | Absent | — | No realised decomposition anywhere |
| Market-implied move | Computed, not shown, not compared | `iv_engine.expected_move` | OI's "expected move" takes max(target distance, ATR move, IV move), so its breakeven-feasibility check is circular |
| Required move-to-return | Absent (no inverse solve) | forward valuations only (monetisability, scenario grid ×0.8/1.0/1.2 IV) | |
| P(touch), P(stop before target) | Underlying only | c12 `passage`/`estimators`, empirical path engine, DOI models | No premium-level target/stop probability; Layer-2 `prob_target_hit` uses fixed +5/7/10 % up thresholds, not direction-aware |
| EV from a distribution | Five engines | `vectorized_research_ev` (live, shown as research EV), `empirical_option_ev` (runs 3× per candidate), `option_path_valuation` (dead duplicate, always NOT_VALUED), c12 `expression` (realised), `ev_engine_v2` (heuristic, legacy fallback) | Duplicates; EV v2 is wrong for puts ✔ (loss forced to −2× expected move) and its IV adjustment has the wrong sign |

Other verified defect: the "too late" check in Options Intelligence always uses the call wall as a put's stop and
ignores the recorded stop and invalidation (operator precedence) ✔. Also reported, not yet re-verified: Kelly sizing
forces at least one contract even above the risk budget; journal `rr_realised = pnl% / breakeven%`; `emp_path_*` and
`contract_value_*` reach the book without the quote-ownership gate (can describe the Evening contract after a
Morning swap); Lab "Expected Move 6–10d / 11–20d" shows increments, not cumulative moves; EVEngineV2 exists in four
copies; Black–Scholes is implemented about seven times.

## 4. What the historical replay says about the five trade-quality computations

**Measured option return distribution (all pipeline signals, ITM 90-day, entry at ask, exit at bid).**

| Outcome | 5 sessions | 20 sessions | 39 sessions |
|---|---|---|---|
| Wrong (< −60 %) | 2 % | 17 % | 32 % |
| Bad (−60 to −30 %) | 16 % | 23 % | 17 % |
| Flat (−30 to +10 %) | 58 % | 28 % | 17 % |
| Moderate (+10 to +40 %) | 18 % | 14 % | 9 % |
| Strong (+40 to +100 %) | 5 % | 13 % | 12 % |
| Explosive (> +100 %) | 1 % | 6 % | 12 % |
| **EV** | **−5.9 %** | **−4.2 %** | **−1.6 %** |

About a third of outcomes are profitable (the illustrative table assumes 55 %). At 39 sessions the explosive bucket
alone contributes +24 points of EV and the wrong bucket −27 points: EV is decided in the tails. For calm stocks
(bottom third ATR percentile) EV is +3.7 % at 39 sessions, subject to the implied-volatility caveat.

**Target-before-stop on the option premium destroys EV on this data.** Every take-profit/stop rule tested is worse
than holding to day 39, in every period:

| Rule (premium) | P(target first) | P(stop first) | EV of the rule | EV holding 39 sessions |
|---|---|---|---|---|
| +50 % / −30 % | 28 % | 68 % | −6.8 % | −1.6 % |
| +100 % / −50 % | 19 % | 56 % | −5.7 % | −1.6 % |
| +30 % / −30 % | 37 % | 61 % | −6.8 % | −1.6 % |
| +100 % / −35 % | 17 % | 69 % | −6.3 % | −1.6 % |

(All signals, 2022–24, 2025 and 2026 weighted by sample size; each period on its own shows the same ordering.) Premium stops
are hit first most of the time and cut paths that later recover; profit targets cap the right tail that carries
the EV. Path-sensitive probabilities are the right tool, but on this evidence they argue against tight premium
stops for long options, not for them.

**Expected move vs market-implied move.** Comparing a forecast of realised movement with the implied move is a
volatility-premium test. The replay's only consistent effect is exactly of this kind (calm stocks: long options beat
same-side options by 3–6 points, calls and puts alike), but it is measured with modelled, not real, IV. It needs
real historical option prices before it can be used.

**Required move-to-return.** Useful as a display (what the stock must do by when for +X %), but it is a reading of
the option's price surface, not a probability; it must sit beside the probability of that move, which is the part
the pipeline does not yet have (TEV-001 C4/C5).

## 5. Recommendations

1. **Adopt the standard computations as one display block, owned by one module.** Intrinsic and extrinsic at the
   current spot, breakeven at the ask, maximum loss, delta exposure and dollar delta per contract, in
   `contracts/selected_contract_economics.py` (it already owns the hydrated contract identity). Display only.
2. **Fix the verified defects, one at a time, test-first** (each needs ACK approval under CLAUDE.md): `vega_risk_pct`
   scale; the put stop in the "too late" check; the put sign and IV sign in EV v2 (or retire it — it is the legacy
   EV the Lab labels "not real EV"); the put breakeven label; Greek provenance when Heston replaces provider Greeks.
3. **One EV owner.** Per TEV-001: C8 values each contract on the ticker forecast's path set; keep
   `vectorized_research_ev` as the pricer, retire the dead `option_path_valuation` and the EV v2 copies, one
   Black–Scholes. Do not invest further in EV3 (design §5.4).
4. **Trade-quality computations, in this order:**
   - *EV from the option return distribution* — yes, from paths (the replay does this), but its probabilities must
     come from a measured ticker edge. Today there is none from price structure (29 Sep replay), so the honest
     distribution is the one in section 4, and its EV is negative except possibly for calm stocks.
   - *Target-before-stop* — measure it, but the evidence says tight premium stops lower EV for long options; do not
     adopt a premium stop rule without a replay showing it helps.
   - *Required move-to-return* — add as a display beside the move's probability (cheap, informative).
   - *Implied vs forecast move* — the most promising lead (the volatility effect in section 4); test with real
     historical option prices (Phantom snapshots from ~Aug 2025) before any use.
   - *Greek P&L decomposition* — useful after the trade for learning, once monitor marks are executable bids and
     entry/exit IV are recorded; lower priority than fixing the marks.
5. Nothing here grants authority; all of it stays advisory until G1–G4.
