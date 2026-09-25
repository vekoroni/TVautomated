# Research assessment — eight proposed models against the AVSHUNTER desired outcome

**Date:** 2026-09-25 · **State:** research, no authority · **Source under review:** "Research paper, 25 September 2026", model table (models 1–8)
**Governing references:** spec v1.1 §1 (purpose), §3 (Invariants A–G), §7 (dealer positioning), §13 (ranking), §14 (advisory inputs); method notes 01, 03, 04, 05, 07; `docs/requirements/AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md` (ALG-04, ALG-07, ALG-09, ALG-10, ALG-12)
**Companion:** `docs/AVS-FIX-REVIEW_APPROVED_FIXES_20260925.md` (the seven approved fix items referenced below as F1–F7)

---

## 0. The desired outcome the models must serve

Spec §1: *find, for every supportable directional thesis, the strongest way to express it and whether the money is in the option or in the ticker, ranked by risk-adjusted expected value rather than filtered by gates.* The unit of work is a per-ticker thesis over a 1–20 session window; the output is a ranked book of valued expressions.

Three governing constraints decide most of what follows:

1. **Macro and event information is display-only** (spec §14, ACK decision): "not automated gates, scores or rank inputs". Spec §26 lists "Macro context → influences any gate, score, floor or rank" and "Event guards → used as automated gates" as forbidden.
2. **Authority is earned** (Invariant G): nothing influences a gate, valuation or rank before passing §24. Dealer positioning is "a structural observation" (§7).
3. **One owner per fact, unknown means unknown** (Invariants A, B): a new model may not recreate direction, probability, EV or rank owned elsewhere, and may not emit a neutral default.

The paper's eight models form a top-down macro transmission stack (surprise → transmission → regime → sector → contract → dealer → execution → decision). AVSHUNTER's outcome is bottom-up per-thesis valuation. That mismatch is the main finding: models 5, 7 and 8 are the solution core and are already the approved design; models 1–4 can only serve as display, validation covariates or research; model 6 is an observation awaiting validation.

---

## 1. Summary verdicts

| # | Paper model | Existing AVSHUNTER owner | Data readiness (note 07) | Fit to outcome | Verdict |
|---|---|---|---|---|---|
| 1 | Event surprise and revision engine | None for macro releases. Earnings: `catalyst_truth_engine.py` (advisory, operator CSV). MarketData earnings endpoint "available, unused" | Consensus distribution: **absent**. Earnings calendar: available, unused | Display and validation covariate only (ACK) | **Adopt narrowly**: point-in-time earnings date and timing capture for note 04 §4; no consensus-surprise engine |
| 2 | Local projections / regularised VAR | None | Macro series not captured at aligned times; macro packet is a label mapper | Research diagnostic only | **Defer** to C13 validation research; never a rank input under the current decision |
| 3 | HMM / threshold regime | Two rule-based owners: per-ticker `hidden_state_label` in `vanguard/physics_state_engine.py` (thresholds, defaults to 50 when inputs missing); macro `_regime_label` in `scripts/macro_quant_packet.py` (string mapping of an upstream label) | Ticker level: bars available. Macro level: display-only | Ticker-level state is the ALG-09 calibration key, so its quality matters for F1 | **Do not build a macro HMM.** Fix the default-50 (Invariant B) first; treat a ticker-level state model as note 01 §2 research with a measured OOS lift requirement |
| 4 | Relative strength and breadth | `_sector_rotation_state` in the macro packet (display); sector concentration reporting in Ranking (§13) | Sector classification partial | Display; comparator for F7 | **Do not build.** Use the sector ETF as a matched comparator and, if ACK approves, as an expression candidate |
| 5 | Event variance plus option repricing | ALG-04 `scenario_valuation_v2`, C8, note 04 §4 | Daily IV term structure: **gap**; rates and dividends defaulted; earnings calendar unused | Core | **Adopt**: already the approved design. The paper adds the event-variance split and term-structure use, both in note 04 |
| 6 | Dealer inventory bounds and gamma stress | `compute_gex`, `compute_gamma_flip`, `dealer_gamma_profile` in Options Intelligence; `canonical_data/gamma_exposure_store.py`; note 07 records "GEX logic defective" and SPY/QQQ chains not captured since 2026-09-04 | No signed flow. OI and greeks only | Observation, not a driver | **Keep as observation**; repair defects; label `GEX_UNAVAILABLE` or `SCENARIO_UNOBSERVED` exactly as the paper says; validate as a C13 covariate |
| 7 | Execution model (fill probability, effective spread, adverse exit bid) | ALG-12 `execution_quality_v1` (state machine), `friction_model_v1` (spread haircut). No fill model. Journal has 14 unlinked trades | Quotes and displayed sizes captured (`contract_bid_size`, `contract_ask_size` in the Lab book). Fills: **gap** | Core, but unestimable today | **Adopt the outputs as ledger fields** through F7; estimate the model only once fills exist. Add displayed-depth versus order-size check now |
| 8 | Net payoff and decision model (CALL / PUT / WAIT) | ALG-07 `calibrated_utility_v2` (`domain/dynamic_options_ranking.py`), C9 RAEV ranking, C10 actions `BUY_NOW / BUY_SMALL / MONITOR / NO_EDGE / INVALIDATED` | Gated by ALG-09 (F1) and ALG-10 (F4) | Core | **Adopt in the spec's form.** "Risk limits" and sizing stay out (F3). WAIT already exists as MONITOR / NO_EDGE |

---

## 2. Model-by-model assessment

### Model 1 — Event surprise and revision engine

**What the paper proposes.** Standardised surprise from release timestamp, consensus distribution, actual, previous and revision, with consensus frozen before release and first publication tested separately from revisions.

**What the literature supports.** The discipline is right: high-frequency surprise measures are contaminated when they correlate with information public before the announcement, and the fix is to orthogonalise against pre-announcement data ([SUERF note on predictability of policy surprises](https://www.suerf.org/publications/suerf-policy-notes-and-briefs/predictability-of-monetary-policy-surprises-and-euro-area-macroeconomic-dynamics/)). Freezing consensus before release and separating first print from revisions is the same point-in-time rule as Invariant E.

**What exists here.** No consensus feed for macro releases. For earnings, `catalyst_truth_engine.py` is an advisory lens over an operator-supplied CSV, and note 07 records the MarketData earnings endpoint as available and unused, with no morning field for it.

**Fit.** Under the ACK decision this model can never feed a gate, score or rank. It can serve two legitimate purposes: (a) supply the point-in-time earnings date and before/after-market flag that note 04 §4 needs to split event variance from diffusive variance before calling IV rich or cheap; (b) act as a validation covariate in C13 so that outcome scoring can "control simultaneous news", which the paper lists as the essential check for model 2.

**Verdict.** Adopt only the earnings-calendar capture (point-in-time, with `observed_at`). Do not build a macro consensus-surprise engine; the data is absent and the output would be display-only.

### Model 2 — Local projections or regularised VAR

**What the paper proposes.** Response of USD, 2y/10y yields, credit, VIX, index and sector returns to a surprise, by horizon, with uncertainty intervals, controlling simultaneous news and comparing signs across regimes.

**What the literature supports.** Local projections estimate impulse responses horizon by horizon without a full dynamic system, are robust to misspecification, and handle state-dependent specifications ([Jordà 2005, AER](https://www.aeaweb.org/articles?id=10.1257%2F0002828053828518); [Montiel Olea et al. primer](https://economics.mit.edu/sites/default/files/2025-01/lp_var_primer.pdf)). Efficiency drops with volatility clustering in high-frequency data ([arXiv 2503.02217](https://arxiv.org/pdf/2503.02217)).

**What exists here.** Nothing. The macro packet maps upstream text labels to RISK_ON / RISK_OFF / CHOPPY / CRISIS and adds a hand-scored `_risk_score` (+55 for RISK_ON, −65 for RISK_OFF). No aligned macro time series is captured.

**Fit.** Transmission estimates describe the index and sectors over hours to weeks after a release. AVSHUNTER's thesis is per ticker over 1–20 sessions and its expression is a single contract. Even if the response were well estimated, it could not enter the rank under the current decision.

**Verdict.** Defer. If ACK ever reopens the macro decision, this is the correct estimator and the paper's checks (simultaneous-news control, sign stability across regimes) are the right ones. Until then, its only use is as a C13 research diagnostic to explain outcome dispersion by session.

### Model 3 — Hidden Markov or threshold regime model

**What the paper proposes.** Probabilities for easing, growth scare, inflation shock and mixed states from rates, USD, curve, credit, breadth, volatility and lagged returns, with stability and no-future-leakage checks.

**What the literature supports.** The leakage warning is the main practical finding: smoothed HMM probabilities use the full sample and inflate backtests, while filtered probabilities are the only ones available in real time; more states fit history better and destabilise out of sample; refitting shifts historical labels even under filtered decoding ([Filtering vs smoothing](https://mathandmarkets.com/p/regime-detection-part-2-the-latency); [QuantStart HMM regime detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/); [HMA Quant](https://hmaquant.substack.com/p/regime-detection-with-hidden-markov)).

**What exists here.** Two regime owners, both rule-based:

- Per ticker, `vanguard/physics_state_engine.py:300-340` assigns `hidden_state_label` by fixed thresholds on compression, force, inertia, entropy and volatility pressure. `_num()` at line 91 returns **50.0 when an input is missing**. That is the Invariant B failure the spec names explicitly ("a 0.5 regime value").
- At macro level, `scripts/macro_quant_packet.py:252` maps an upstream label string; there is no estimation.

**Fit.** The ticker-level label is a dimension of the ALG-09 calibration key, so its stability directly affects F1. A macro HMM is display-only by decision.

**Verdict.** Do not build a macro regime model. For the ticker state: first remove the default-50 so missing inputs yield `STATE_UNAVAILABLE`; then, only if note 01 §2's rule is met (measured out-of-sample lift, few well-populated states), evaluate a filtered-probability state model as a replication candidate. Any such model must publish filtered, not smoothed, probabilities and must be frozen per model version so historical labels do not move.

### Model 4 — Relative strength and breadth model

**What the paper proposes.** Ranked sector and stock probabilities from sector ETF and constituent returns, volume, breadth, size and industry exposures, calibrated against a simple relative-strength baseline.

**What the literature supports.** Industry momentum is robust in stocks ([Moskowitz and Grinblatt 1999 via Quantpedia](https://quantpedia.com/strategies/sector-momentum-rotational-system)), but out-of-sample tests on sector ETFs are mixed, with one clean test finding no momentum in sector ETFs ([Journal of Asset Management](https://link.springer.com/article/10.1057/jam.2014.24); [Momentum strategies with index ETFs](https://www.sciencedirect.com/science/article/abs/pii/S106294081500042X)). The paper's own check, calibration against a simple baseline, is the right one and is where such models usually fail.

**What exists here.** `_sector_rotation_state` in the macro packet (display); §13 lets Ranking report sector concentration without changing rank.

**Fit.** Sector flow does not answer "which expression of this thesis is strongest". Its legitimate roles are portfolio-awareness reporting and, for F7, a matched comparator: the sector ETF option with the same direction, horizon and moneyness is the cleanest "simple alternative" the fix review asks for. AVS-RANK-001 §4 also noted that two-thirds of the universe cannot be expressed in single-name options, which makes the ETF a candidate expression rather than a signal.

**Verdict.** Do not build the model. Use sector ETFs as comparators now and, if ACK approves under §10 (approved expression scope), as expression candidates.

### Model 5 — Event variance plus option repricing

**What the paper proposes.** Spot / IV / time scenario values from the live chain, term structure, skew, dividends, rates and the event window, priced with one consistent engine and compared with the market bid after costs.

**What the literature supports.** The slope of the IV term structure predicts short-dated straddle returns ([Jones and Wang](https://msbfile03.usc.edu/digitalmeasures/christoj/intellcont/jones_wang-1.pdf); [JFQA, equity volatility term structures](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/equity-volatility-term-structures-and-the-cross-section-of-option-returns/F0A40E99FD2458367DD9A56A89783D38)). Implied earnings moves frequently overstate realised moves, though not always ([ORATS 2026 season note](https://orats.com/blog/earnings-straddles-strong-season-2026)). Note 04 §5 already records the variance risk premium as "the core fact".

**What exists here.** This is ALG-04 (`scenario_valuation_v2`): BSM at constant IV, a FLAT / 1σ / 2σ / REACHABLE / STRUCTURAL / INVALIDATION grid, EARLY / MID / LATE timings, IV stresses 0.8 / 1.0 / 1.2, entry at ask, exit at modelled bid under `friction_model_v1`. Note 04 §4 specifies the event-variance split. What is missing is data: a daily constant-maturity IV series (gap), rates and dividends currently defaulted, and the earnings calendar unused.

**Fit.** Exact. This is the valuation context C8.

**Verdict.** Adopt; it is already the approved design and F2 in the fix review. The paper adds two things worth taking: use the term structure to separate event variance before judging IV, and compare every scenario value with the market bid after costs (already the ALG-04 friction rule). Do not add skew-based repricing until the daily IV panel exists.

### Model 6 — Dealer inventory bounds and gamma stress

**What the paper proposes.** Long / neutral / short inventory bands and conditional hedge size from signed flow, offsets, gamma, delta and hedge-market depth; if only OI exists, label the scenario unobserved.

**What the literature supports.** Dealer gamma imbalances interact with illiquidity to produce intraday momentum or reversal, strongest in the least liquid names ([Barbon and Buraschi, Gamma Fragility](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454)); hedging demand explains market intraday momentum across 60 futures ([Baltussen, Da, Lammers and Martens](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598)). The evidence is intraday and largely index-level; it does not establish a 1–20 session directional effect for single names.

**What exists here.** A full GEX engine (`compute_gex`, `compute_gamma_flip`, `dealer_gamma_profile`, walls) and a canonical store. Note 07 records the logic as defective and SPY/QQQ chains not captured since 2026-09-04. No signed opening/closing flow is available, so the paper's own rule applies: the scenario is unobserved.

**Fit.** Spec §7 already defines this as an observation with no authority until validated, computed by one engine and reporting `GEX_UNAVAILABLE` rather than a neutral value.

**Verdict.** Keep as observation. Repair the engine defects and the index-chain capture, stamp `SCENARIO_UNOBSERVED` when only OI exists, and evaluate GEX as a covariate in C13 outcome scoring. It is not a solution driver for the desired outcome.

### Model 7 — Execution model

**What the paper proposes.** Fill probability, effective spread and the adverse-exit bid distribution from timestamped quotes, displayed depth, order size, underlying liquidity and event phase, validated against actual fills.

**What the literature supports.** Effective spreads in options are materially smaller than quoted spreads for traders who time executions, roughly a quarter smaller on average and up to five times smaller for timed trades ([Muravyev and Pearson, RFS 2020](https://academic.oup.com/rfs/article-abstract/33/11/4973/5732665)). Note 03 §3 already cites this and adds the correct guard: nothing better than the quoted spread may be assumed until validated on our own fills.

**What exists here.** ALG-12 `execution_quality_v1` classifies quotes (unavailable, defect, zero bid, stale, wide, reviewable, executable now) and `friction_model_v1` haircuts the exit. Displayed sizes are captured (`contract_bid_size`, `contract_ask_size`, `underlying_nbbo_*_size` in the Lab book). The journal holds 14 unlinked trades, so no fill model can be estimated.

**Fit.** Exact, but unestimable today. The 20 September backtest already showed that friction decides sign: +10.9% at ask-to-bid became +4.6% with spreads widened 50%.

**Verdict.** Adopt the paper's outputs as ledger fields under F7: for every prospective decision record the quote, displayed depth, intended size, whether a fill occurred, and the realised effective spread. Add a displayed-depth versus order-size flag now, since the data exists. Estimate fill probability and the adverse-exit distribution only once the ledger holds enough fills; until then the quoted-spread haircut remains the friction model.

### Model 8 — Net payoff and decision model

**What the paper proposes.** From the joint spot/IV distribution, modelled fills, DTE, fees, risk limits and the trade plan: expected net P&L, a downside quantile, probability of a positive net exit, and a CALL / PUT / WAIT choice.

**What exists here.** ALG-07 `calibrated_utility_v2` combines ALG-09 probabilities with ALG-04 net payoffs; C9 ranks by RAEV with a time-normalised return and liquidity-cost tie-break; C10 issues `BUY_NOW / BUY_SMALL / MONITOR / NO_EDGE / INVALIDATED`. `NO_POSITIVE_EDGE` rows stay visible (§13). The paper's WAIT is MONITOR or NO_EDGE.

**Fit.** Exact, with two differences. First, AVSHUNTER uses a scenario grid with IV stresses, not a joint spot/IV distribution; the grid is the approved first release and a joint distribution needs the daily IV panel. Second, "risk limits" in the paper's inputs is sizing, which stays outside AVSHUNTER (F3).

**Verdict.** Adopt in the spec's form. The activation order is fixed by dependencies: ALG-10 vol validation (F4) → outcome labels and ALG-09 calibration (F1) → ALG-07 utility (F2.3) → rank test against the desk gate (F1.4). The paper's downside quantile and probability of positive net exit are cheap additions to ALG-07's output once the probabilities exist and should be included then.

---

## 3. What the paper adds that AVSHUNTER should take

Independent of the individual models, four disciplines in the table are worth adopting as written:

1. **Freeze the consensus before the release; test first print separately from revisions.** The same rule as Invariant E and F7's frozen decision record. Apply it to every external input with a revision history, including the macro packet.
2. **Filtered, never smoothed.** Any state or regime probability shown to a trader or used in a calibration key must be computable from data up to that session only, and the model version must be frozen so historical labels do not move.
3. **Label the scenario unobserved.** Where signed flow, fills or consensus are missing, the field says so. This is Invariant B applied to models 6 and 7, and it is exactly what the physics engine's default-50 violates today.
4. **Validate against actual fills.** No execution-cost assumption better than the quoted spread until the ledger proves it.

## 4. What the paper cannot give

- Models 1–4 cannot enter a gate, score or rank under the ACK decision recorded in spec §14 and §26. Reopening that is a business decision, not a research finding.
- No model in the table supplies the two things the fix review identified as the binding constraints: verified multi-session exact-contract quotes (F6) and a prospective, hindsight-free record (F7). Both are data and process, not models.
- The literature behind models 2, 3 and 6 is index-level and intraday to weekly; none of it establishes a per-ticker 1–20 session directional edge, which is what the thesis needs.

## 5. Mapping onto the approved fix items

| Fix item | Models that aid it | How |
|---|---|---|
| F1 Edge ranking | 8 (ALG-07), 3 (state quality) | ALG-07 output gains downside quantile and P(positive net exit); ticker state must stop defaulting to 50 before it is a calibration key |
| F2 rr_predicted | 5 | ALG-04 grid with event-variance split; scenario values compared with market bid after costs |
| F3 Sizing | none | Paper's "risk limits" input is excluded |
| F4 GARCH / convexity | 5, 1 | Term-structure event split before judging IV; earnings date capture feeds note 04 §4 |
| F5 Invalidation | none | Data provenance, not a model |
| F6 Multi-session paths | 7 | Ledger fields for depth, size and fills ride on the same capture |
| F7 Prospective record | 7, 4 | Fill and effective-spread fields in the decision record; sector ETF option as the matched comparator |

## 6. Decisions needed from ACK

1. Whether sector ETF options enter the approved expression scope (§10) as a candidate expression, given the capacity finding in AVS-RANK-001 §4.
2. Whether the point-in-time earnings calendar becomes a captured C1 field (display and note 04 §4 only, no gate).
3. Confirmation that models 1–4 remain display-only; this assessment assumes the decision stands.

## Sources

- [Jordà (2005), Estimation and Inference of Impulse Responses by Local Projections, AER](https://www.aeaweb.org/articles?id=10.1257%2F0002828053828518)
- [Montiel Olea et al., Local Projections or VARs? A Primer](https://economics.mit.edu/sites/default/files/2025-01/lp_var_primer.pdf)
- [SUERF, Predictability of monetary policy surprises](https://www.suerf.org/publications/suerf-policy-notes-and-briefs/predictability-of-monetary-policy-surprises-and-euro-area-macroeconomic-dynamics/)
- [Enhancing efficiency of local projections with volatility clustering (arXiv)](https://arxiv.org/pdf/2503.02217)
- [Filtering vs smoothing: why backtests lie about regime detection](https://mathandmarkets.com/p/regime-detection-part-2-the-latency)
- [QuantStart, Market regime detection using HMMs](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- [HMA Quant, Regime detection with HMMs](https://hmaquant.substack.com/p/regime-detection-with-hidden-markov)
- [Quantpedia, Sector momentum rotational system (Moskowitz and Grinblatt)](https://quantpedia.com/strategies/sector-momentum-rotational-system)
- [Journal of Asset Management, Market states and momentum in sector ETFs](https://link.springer.com/article/10.1057/jam.2014.24)
- [Momentum strategies with stock index ETFs (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S106294081500042X)
- [Jones and Wang, The term structure of equity option implied volatility](https://msbfile03.usc.edu/digitalmeasures/christoj/intellcont/jones_wang-1.pdf)
- [JFQA, Equity volatility term structures and the cross-section of option returns](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/equity-volatility-term-structures-and-the-cross-section-of-option-returns/F0A40E99FD2458367DD9A56A89783D38)
- [ORATS, Earnings straddles 2026 season](https://orats.com/blog/earnings-straddles-strong-season-2026)
- [Barbon and Buraschi, Gamma Fragility (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454)
- [Baltussen, Da, Lammers and Martens, Hedging demand and market intraday momentum (JFE)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598)
- [Muravyev and Pearson, Options Trading Costs Are Lower than You Think (RFS 2020)](https://academic.oup.com/rfs/article-abstract/33/11/4973/5732665)
