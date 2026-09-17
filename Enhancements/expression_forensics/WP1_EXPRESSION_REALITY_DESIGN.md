# WP1 — Reality-calibrated expression selection: Design

Status: **DRAFT for ACK approval** · 17 Sep 2026 · Branch `wp1-expression-tradeability` (worktree `..\AVSHUNTER-wp1`; main tree stays clean for the morning run)

Approved inputs: forensic `EXPRESSION_FORENSIC_AND_TDD_APPROACH_20260917.md` (D1–D4); ACK direction: *use reality rather than textbook options logic; historic data, implied vs realised volatility and forward probabilities; benchmark = a human option trader without a pipeline.*

## 1. Business rule (what a good human trader does)

A trader buys an option only when, **after the cost of getting in and out**, the option is expected to return more per unit of risk than the shares on the same thesis, and only in contracts that actually trade. They check four things: *can I trade it* (two-sided quote, activity), *what will it cost me* (spread in and out), *is the move priced cheaply* (implied vs realised volatility), and *does the option pay if I am right within my time frame* (probability and timing of the move vs decay).

## 2. Current behaviour (characterised, `tests/test_wp1_select_best_contract_characterisation.py`)

`select_best_contract` (`scripts/avshunter_options_intelligence.py` 4534–4762) ranks by a fixed textbook composite (0.30 delta fit + 0.20 DTE fit + 0.20 theta/mark + 0.15 vega + 0.15 liquidity). Pinned defects: spread limit not applied (E1); zero volume / zero OI selectable (E1); one-sided quote selectable with a mark (E2); a wide-spread contract on target delta beats a tight-spread contract. Measured cost: round-trip spread −35% of premium; zero-volume entries −66%.

## 3. Design

Replace the composite score with an **expected net value (ENV) per contract**, computed from observed market reality, and keep a small set of hard *priceability* rules (decide before depend, R4). Ranking, not gating, for everything that is a cost (R11).

### 3.1 Priceability (hard rules; reasons recorded)
- P1 two-sided quote: bid > 0, ask > 0, ask ≥ bid, from the session's chain → else `NOT_PRICEABLE:NO_TWO_SIDED_QUOTE`.
- P2 quote age within the session (from `updated_ts` / quote timestamp) → else `NOT_PRICEABLE:STALE_QUOTE`.
- P3 contract side matches the governed direction (E5 is WP3; the selector already filters side).

### 3.2 Execution cost — calibrated on history, not assumed
`expected_round_trip_cost_fraction = entry_half_spread_observed + E[exit_half_spread | liquidity cell, holding sessions] + P(unquoted at exit | cell) × unquoted_loss`

- Liquidity cell = entry spread band × traded today (volume > 0) × open-interest band (probe §5).
- Calibration table produced by a reproducible script from `chain_snapshots` (entry session *t*, exit *t + k*), versioned with the data hash and date range, stored as a calibration artefact referenced from the configuration registry (`expression.execution_cost_calibration_id`). Refreshed on a schedule; stale calibration is flagged, never silently used.
- Validation: the calibrated cost must reproduce the measured round-trip cost on the 2,265 scored book contracts (out-of-sample by session).

### 3.3 Payoff — forward probabilities and implied vs realised volatility
For each thesis the scenarios are those the outcome scorer measures: *target first by session k*, *stop first by session k*, *neither by the horizon*.
- **Scenario probabilities**: from the matched base rate for the thesis geometry (barrier distances in ATR, same session universe, first passage — C12 `matched_incidence`) as the no-skill prior; the pipeline's own probability replaces it only for a signal family that has passed G1–G4 against the base rate (today none has). This makes "is the option worth it" honest about the fact that direction is currently at chance.
- **Option value in each scenario**: reprice at the scenario's underlying level and session with the contract's implied volatility (inverted from the observed mid when the provider IV is missing — greeks are null on 95% of rows), then apply the observed **IV change** for that scenario from history (IV on up-moves vs down-moves by moneyness/DTE cell) instead of assuming constant volatility; subtract the expected exit half-spread.
- **Implied vs realised**: `vol_edge = realised_vol_forecast / implied_vol` where the realised forecast comes from the price store (e.g. recent realised volatility blended with the ticker's volatility regime in the actuarial database); reported per contract and used through the repricing, not as a separate gate.
- The residual of this repricing against actual next-session marks is measured on history (probe: residual +6% of premium today) and published with the calibration.

### 3.4 Selection and the option-vs-shares answer
- `ENV_option = Σ_s P(s) × value_at_exit_s − ask` (per contract, per share of premium) and `RAEV = ENV / premium at risk`.
- The same scenarios give `ENV_shares` (entry at ask, exit at bid/limit, stop fill at worse of level and open).
- Rank all contracts in the DTE / side family by RAEV; the thesis records the best option, the share expression and `expression_preference = OPTION | SHARES | NEITHER` with both values. `NEITHER` when no expression has positive ENV after costs.
- Output fields are additive to the book (no removed columns); legacy `contract_score` is kept as `legacy_contract_score` for comparison during validation.

### 3.5 Authority
Shadow first: the new ranking runs beside the legacy selector and writes `wp1_*` fields; the outcome scorer measures both on the same sessions. It replaces the legacy choice only after ACK approval of the acceptance evidence (§6). Configuration values are PROVISIONAL registry entries.

## 4. Where the code goes (enhance the existing owner, D1)
| Piece | Location |
|---|---|
| Priceability, ENV ranking inside the selector | `scripts/avshunter_options_intelligence.py` `select_best_contract` (shadow fields first) |
| Pure value model (execution cost, scenario repricing, IV inversion) | `contracts/expression_value.py` (new pure module used by the owner; no I/O) |
| Calibration builder (reads chain history, writes versioned artefact) | `scripts/calibrate_expression_execution_cost.py` |
| Scenario probabilities | reuse `avshunter/c12_outcome/base_rate.py` (pure) through an adapter |

## 5. Evidence so far (probe, daily panel 28 Aug – 16 Sep)
Probe: every contract with a two-sided quote and 7–60 DTE on 8 daily entry sessions (28 Aug – 9 Sep), re-observed 5 sessions later (1,046,400 contract pairs still quoted), `execution_cost_calibration_probe.json`.

| Entry spread (of ask) | Median round-trip cost (of premium) | Entry half-spread | Exit half-spread 5 sessions later | Median ask→bid return | Unquoted after 5 sessions |
|---|---|---|---|---|---|
| < 5% | 3–4% | 1.4–1.8% | 1.2–1.9% | −7% to −18% | 23–40% |
| 5–10% | 7–8% | 3.7–3.8% | 3.4–3.9% | −10% to −25% | 14–36% |
| 10–20% | 14–15% | 7.1–7.5% | 6.3–7.7% | −17% to −33% | 12–27% |
| 20–35% | 25–26% | 13% | 11–12.5% | −29% to −53% | 15–25% |
| ≥ 35% | 50–63% | 29–35% | 20–26% | −73% to −86% | 13–26% |

Findings:
1. **Spreads persist.** The exit half-spread five sessions later is almost the same as the entry half-spread in every cell, so the observable entry spread (ask − bid) / ask is itself a calibrated estimate of the round-trip cost. Volume and open interest change the cost very little once the spread is known; they matter for fill risk, not quoted cost.
2. **A ≥ 35% spread contract loses about half its premium to the round trip before any market move** — consistent with the book contracts (−71% in that band).
3. "Unquoted after 5 sessions" is inflated by the stored chain's 40-strike / OI ≥ 1 / 7–60 DTE request window (DQ-6) and must not be read as true disappearance; the targeted quote tool (backfill option B) is needed to measure it.
4. Median mid-to-mid return over 5 sessions is negative in every cell (−1% to −33%): time decay and the period's moves; it will be separated per scenario by the repricing model (§3.3) once implied volatility is available for backfilled sessions (§5a).

## 5a. Implied volatility and greeks gap (found 17 Sep)

The provider's historical chain endpoint returns no IV or greeks; the established weekly procedure computes them locally with `scripts/phantom_compute_historical_greeks.py` (Black-Scholes from stored quotes, no API calls; `greeks_source = COMPUTED_BS`). The Phase 0 backfill did not run that step (B4 review missed this script), so the daily sessions have no IV. Running it over the backfilled sessions is a prerequisite for §3.3 and needs ACK approval (writes computed columns into `chain_snapshots` and `options_greeks_history`, filling nulls only).

## 5b. Volatility evidence step (ACK approved 17 Sep 2026, before any selection change)

1. **Estimators** (`contracts/realised_volatility.py`, pure, tests `tests/test_realised_volatility.py`): close-to-close, Parkinson, Garman-Klass, Yang-Zhang, EWMA; per-session units; explicit annualisation; missing or non-positive prices raise, never neutral.
2. **Forecast study** (`volatility_forecast_study.py`, read-only, price store 2022 → 2026, every 5th session, all tickers): each forecast vs delivered volatility over the next 5 / 10 / 20 sessions; bias, mean absolute log error, QLIKE; share of windows with a jump > 4× forecast (event contamination). The forecast used by WP1 is the one that wins on our data, not a textbook default.
3. **Implied vs delivered** (after G1): at-the-money IV per ticker and session (provider IV where present, local `COMPUTED_BS` otherwise; local vs provider agreement 79% within 5%, 91% within 10% on 16 Sep) vs volatility delivered over the option's holding window → measured volatility premium by ticker, regime and DTE; the scenario repricing uses this, not an assumed constant.
4. **Legacy defects to fix test-first** (owner modules, D1): `layer3_forward_variance.py` returns 0.25 volatility when prices are missing and treats missing IV as neutral 0 (R1); `vanguard/core/actuarial_core_v7.py` 182/254 names an ATR-based realised regime `LOW_IV` / `HIGH_IV` (R6); RIEG (`layer4_mispricing.py`) and the vol-divergence gate (`empirical_option_ev.py`) have no recorded validation against delivered volatility.
5. **Point-in-time**: forecasts use bars up to the evidence session only; delivered volatility is used only for scoring and calibration. Full-session option volume is look-ahead for anything decided intraday (provider documentation).

### 5b.1 Forecast study result (17 Sep 2026; ~410,000 ticker-session evaluations per horizon; rolling implementation matches the pure estimators exactly)

| Horizon | Best by QLIKE (variance-pricing loss) | Best by mean absolute log error | Typical error of the best forecast |
|---|---|---|---|
| 5 sessions | EWMA 0.94 (QLIKE 0.98; median over-forecast +18%) | Parkinson 60 (0.395) | ±40–55% |
| 10 sessions | EWMA 0.94 (0.89; +11%) | Parkinson / Garman-Klass 60 (0.32) | ±32–43% |
| 20 sessions | EWMA 0.94 (0.81; +5%) | Parkinson / Garman-Klass 60 (0.28; but under-forecast in 57–58% of cases) | ±28–37% |

Findings:
1. **EWMA (0.94) is the best volatility forecast for option pricing** at every horizon under QLIKE, which punishes under-forecasting the most — the costly error when buying premium. Long-window range estimators are closer in the typical case but under-forecast more often and miss bursts. The 20-session close-to-close estimate that textbooks default to is among the worst (QLIKE 2.9 at 20 sessions).
2. **Volatility is only moderately predictable per ticker**: even the best forecast is typically off by roughly a third at 20 sessions and by half at 5 sessions. Option value must carry this uncertainty (scenarios over a volatility distribution), not a single number.
3. **Jumps dominate the tail**: 13–16% of 20-session windows (3–4% of 5-session windows) contain a daily move larger than 4× the forecast daily volatility. An event flag (earnings and other scheduled events) is required before comparing IV with delivered volatility; the source of a reliable event calendar is still to be confirmed.
4. **Legacy forecast checked** (`legacy_forward_variance_study.py`; 158 tickers of a 300-ticker random sample with enough history, 6,623 evaluations every 20th session, horizon 20): the pipeline's forecast runs **HAR-RV in every case** — GARCH/EGARCH never run because the `arch` package is not installed. With the macro multiplier disabled it matches EWMA on QLIKE (0.565 vs 0.565) and absolute error (0.320 vs 0.322) but over-forecasts more (median +14.6% vs +5.2%; below delivered 34% vs 44%). **Accuracy is not the defect; the wrappers are**: missing prices return 25% volatility, missing IV is treated as neutral, a 5% floor and 250% cap are unvalidated, and a macro-regime multiplier (×1.10 RISK_OFF/BEAR, ×1.05 TRANSITIONAL) changes the forecast — a macro label influencing a score, against `CLAUDE.md` rule 6. Recommendation (D1): keep HAR-RV in its existing owner and fix the wrappers test-first.

### 5b.2 Implied vs delivered (17 Sep 2026, `implied_vs_delivered_study.py`)

At-the-money IV (|delta| 0.40–0.60) from `options_greeks_history` for 1,752 tickers over 126 weekly/daily sessions (17 May 2024 → 15 Sep 2026; 216,995 ticker-tenor-session observations), against volatility delivered over the next 10 / 20 sessions and the EWMA forecast at the same session.

| Tenor, horizon | Median IV ÷ delivered | IV above delivered | In jump windows (10–15% of cases): IV ÷ delivered / IV above delivered |
|---|---|---|---|
| 7–19 DTE, 10 sessions | 1.18 | 68% | 0.72 / 22% |
| 7–19 DTE, 20 sessions | 1.13 | 64% | 0.76 / 27% |
| 20–45 DTE, 10 sessions | 1.20 | 69% | 0.64 / 10% |
| 20–45 DTE, 20 sessions | 1.13 | 65% | 0.77 / 21% |

"Cheap vs our forecast" (20–45 DTE, 20 sessions):

| IV ÷ EWMA forecast | Observations | Median IV ÷ delivered | Delivered above IV |
|---|---|---|---|
| ≤ 0.8 | 18,049 | 1.07 | 41% |
| 0.8–1.0 | 29,512 | 1.07 | 41% |
| 1.0–1.2 | 29,659 | 1.10 | 37% |
| 1.2–1.5 | 23,511 | 1.17 | 31% |
| 1.5–2.0 | 12,515 | 1.32 | 25% |
| > 2.0 | 6,128 | 2.22 | 9% |

Findings:
1. **Buying options pays a volatility premium most of the time**: IV exceeds the volatility that follows in about two thirds of cases, by a median 13–20% (18–24% outside jump windows). A long-option-only pipeline starts every trade against this headwind, before spreads (§5) and before direction.
2. **The premium reverses in jump windows**: when a large move happens, delivered volatility beats IV 73–90% of the time. IV is already elevated before those windows (IV ÷ EWMA 1.28–1.57 vs ~1.04 otherwise), so the market partly prices events; an event calendar is needed to separate scheduled events from surprises.
3. **Our forecast adds information**: when IV is at or below the EWMA forecast, delivered volatility exceeds IV 41% of the time (vs 9% when IV is more than 2× the forecast) — options are close to fairly priced there, and expensive above ~1.2×. This is a measured, not textbook, cheapness rule for the value model.
4. **IV and EWMA predict delivered volatility about equally well** in typical absolute error (0.29–0.38 vs 0.27–0.35); IV's QLIKE is inflated by a small number of extremely low computed IVs — data-quality rule **DQ-11** (implausible IV values, e.g. deep ITM / bad quotes) required before IV feeds any value.

Implication for WP1: the value model must (a) price options against the measured volatility premium and spread cost, (b) prefer shares (or no trade) when IV ÷ forecast is high and no event edge exists, and (c) treat event windows separately. A human option trader does exactly this.

### 5b.3 GARCH investigation and model comparison (ACK request 17 Sep 2026)

**Why "GARCH" never ran:** (1) `garch_runner.py` 283–285 counts `HAR_RV` as a GARCH success, so the run log shows `GARCH=1476` while `l3_method = HAR_RV` for all 1,476 tickers (20260916_223756); (2) HAR-RV is tried first and succeeds; (3) the EGARCH / GARCH(1,1) fallback needs `arch`, which is not in the production lock; (4) **defect**: even with `arch`, `layer3_forward_variance.py` 355 and 387 called `.iloc[-1]` on ndarray output, raised AttributeError and `except Exception: pass` hid it — the fallback could never return a forecast. (5) Last night's values carry the macro ×1.10 multiplier (AAPL 0.3143 = 0.2857 × 1.10, reproduced exactly for AAPL, MSFT, NVDA).

**Fix (test-first, `tests/test_layer3_garch_fallback.py`):** ndarray-safe access, `res.scale` conversion back to percent units, failures logged with reason, `method_used` recorded (`EGARCH` / `GARCH`). Rules G1–G4 failed before the fix and pass after (production venv, stand-in arch); G5 passes against real arch 8.0.0 in the isolated test environment. No production dependency change.

**Comparison** (`garch_comparison_study.py`, test environment; 158 tickers, 6,640 evaluations, horizon 20 sessions, no floor / cap / macro multiplier; 6,199 evaluations where all models produced a forecast):

| Model | QLIKE (lower is better) | Mean abs log error | Median over-forecast | Fit failures | QLIKE low / mid / high vol |
|---|---|---|---|---|---|
| **HAR-RV** (production) | **0.511** | 0.314 | +13.0% | 0 | **0.74 / 0.35 / 0.44** |
| EWMA 0.94 | 0.589 | 0.314 | +3.9% | 0 | 0.79 / 0.42 / 0.55 |
| GARCH(1,1) | 0.593 | 0.323 | +13.5% | 441 non-stationary (6.6%) | 0.96 / 0.36 / 0.45 |
| EGARCH (legacy horizon formula) | 319 | 0.368 | +9.9% | 540 not converged (8.1%) | 16.9 / 503 / 437 |

Conclusions:
1. **HAR-RV is the better model** — best QLIKE overall and in every volatility regime, never fails. GARCH(1,1) is close in mid / high volatility but worse in low volatility and fails stationarity 6.6% of the time. EGARCH as coded is unsafe: 99 forecasts below a third of delivered volatility (as low as 0.1%), which would badly under-price option risk.
2. **ACK decision 17 Sep 2026 — done:** fallback order is now HAR-RV → GARCH(1,1) → EWMA and EGARCH is removed (`layer3_forward_variance.py`; rules F1–F6 in `tests/test_layer3_garch_fallback.py`: F1–F5 pass in the production venv, all six pass with real arch in the test environment).
3. `arch` does not need to enter the production environment for accuracy reasons.

## 5c. G1 — local IV and Greeks for backfilled sessions (ACK approved 17 Sep 2026)
Provider documentation: historical chains (`date=`) return null IV and Greeks on every plan; current chains carry them. G1 computes them locally (`scripts/phantom_compute_historical_greeks.py`, no API calls, fills nulls only) for 14 sessions / 2,958,244 rows, driven per session and ticker chunk (`Enhancements/phase0/greeks_backfill/run_g1_greeks.py`). Provider values always take precedence; computed values keep `greeks_source = COMPUTED_BS`.

## 6. Tests (written first) and acceptance
Business-rule tests (fail before the change): no-two-sided-quote contract is not priceable; contract above the spread limit is ranked by its full measured cost and loses to a tighter equivalent; untraded contract carries its measured cost and unquoted risk; ranking uses ENV after costs (the characterised wide-vs-tight case flips); value model reproduces calibration table and hand-computed scenarios; IV inversion round-trips; `NEITHER` when no expression has positive ENV; shares chosen when the option's ENV per risk is lower.

Acceptance against reality (outcome scorer, same sessions, shadow vs legacy): round-trip spread cost share of premium, zero-volume share, mean and median return on premium, win rate, and option-vs-shares realised difference — on history (out-of-sample sessions) and on at least 10 forward sessions.

## 7. Decisions for ACK
1. Approve the design (ENV ranking with calibrated costs; base-rate probabilities until a signal passes G1–G4; shadow first).
2. Approve the new pure module `contracts/expression_value.py` and calibration script (enhancing the existing owner).
