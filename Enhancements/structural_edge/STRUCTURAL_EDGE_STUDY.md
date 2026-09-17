# Structural edge study: does selling the volatility premium pay after real costs and tails?

ACK decision B, 17 Sep 2026. Read-only study. No pipeline code, configuration or `data/` changed, no provider calls, databases opened `mode=ro`. Not committed.

## 1. Question and answer

**Question.** The direction evidence found no directional edge. Is there a structural edge that needs no direction, mainly from selling the volatility premium, once you pay real fills and take the tail losses?

**Answer: no, not in this data.** Four short-volatility structures were tested: 576,852 trades on 1,753 tickers over 241 weekly entry sessions (Nov 2021 – Aug 2026, but 94% of trades come from May 2024 onwards). With sold legs filled at the bid and bought legs at the ask, **no structure has a positive mean with a bootstrap interval clear of zero in any liquidity band, tenor or exit.** Most are significantly negative. The volatility premium is real in this sample: IV was above the volatility that followed in 63–66% of cases, median IV ÷ delivered 1.10–1.16. What earns it is the usual win rate (57–80%) and median profit. The losses come from jump windows: in the 7–15% of trades with a daily move above 4× the forecast sigma, the premium plus the spread is lost several times over. The best result is small and not significant: index and sector ETFs (no single-company earnings) with tight spreads, about +1% to +4% per unit of risk, and every interval includes zero.

## 2. Method

Scripts, run in order with `venv\Scripts\python.exe`:
1. `build_short_vol_trades.py`: builds the trades (7 processes, 67 min) → `short_vol_trades.parquet` and `short_vol_trades_build_meta.json` (exclusion counts, 0 errors).
2. `analyse_short_vol_trades.py`: statistics and bootstraps → `structural_edge_results.json` and `structural_edge_tables.md` (all tables, both tenors, all bands and breakdowns).
3. `supplement_short_vol.py`: ETF subset, tp50 trigger rates, session-equal-weight means → `structural_edge_supplement.json`.

| Item | Rule used |
|---|---|
| Entry sessions | The latest stored session of each ISO week for each ticker (`chain_snapshots`, filtered by ticker and date range) |
| Expiry | One per ticker, session and tenor: closest to 30 DTE within 20–45 DTE, or closest to 14 within 7–20 DTE. Expiry must be on or before 16 Sep 2026, the last price bar |
| IV and delta | Computed locally with Black-Scholes from the stored mid of OTM contracts: r = 4.5% (the stored rate), q = 0, calendar DTE / 365. **One method for every session**, because provider greeks exist only on a few sessions and many weekly sessions have null IV in `chain_snapshots` |
| Short ATM straddle | Strike nearest the underlying price, with both legs two-sided |
| Short 25-delta strangle | OTM put and OTM call with delta closest to 0.25, which must fall within 0.15–0.35 |
| Iron condor (25/15) | Strangle shorts plus long wings closest to 15 delta. A wing must be at least 5 delta further OTM than its short leg, otherwise there is no trade: the stored 40-strike window often lacks wings (recorded) |
| Put credit spread (25/15) | Short 25-delta put and long put near 15 delta |
| Fills | Sold legs at the **bid**, bought legs at the **ask**. Entry credit ≤ 0 means no trade (recorded) |
| Exit: hold | Intrinsic value at the underlying close on or before expiry. The close is split-adjusted and converted to chain units with the factor chain underlying ÷ close at entry |
| Exit: mid | At the later stored session nearest half-life (within ±7 days) where every leg is two-sided: buy the shorts back at the **ask**, sell the longs at the **bid**. If no such session exists, the trade is recorded as missing, never substituted |
| Exit: tp50 | Exit at the first later stored session where the cost to close is ≤ 50% of the credit, otherwise hold to expiry |
| Risk unit | Defined-risk: maximum loss (widest wing − credit). Naked: **20% of underlying notional** (stated margin proxy) |
| Liquidity bands | Worst leg (ask − bid) / mid ≤ 10%, 20% or 35%, plus all two-sided quotes. Legs are chosen first and then filtered, so a trade is dropped, not moved to a more liquid strike |
| Forecast | EWMA 0.94 of daily log returns up to and including the entry session (point-in-time), × √252 |
| Jump window | Any daily move between entry and expiry > 4× the entry EWMA daily sigma. **Known only after the fact**; used for diagnosis, not as a filter |
| Integrity | Excluded: one-bar move ≥ 10x or sub-cent close in [entry − 60 bars, expiry]; a chain/close factor that moves > 3% from entry to expiry + 14 days (split in the window, 590 trades); any strike outside 0.6–1.6x the underlying (1,409 trades, e.g. CVNA May 2026, where the underlying was adjusted but strikes were not); straddle strike > 5% from the underlying (23,016, wide strike grids); defined-risk credit > 60% of the width (5) |
| Uncertainty | Bootstrap over **entry sessions**, 2,000 resamples. Primary: moving blocks of 4 consecutive weekly sessions (20–45 DTE) or 2 (7–20 DTE), because holding periods overlap. An i.i.d. session bootstrap is in the JSON. Observations within a session are never resampled independently |

## 3. Results: 20–45 DTE (main tenor), mean return per unit of risk

Means are per trade. The interval is the 95% block bootstrap. Worst 1% and 5% are return quantiles. "W5/G" = the sum of the worst 5% of trades ÷ the gross gains of all winners. "Cost" = entry spread paid (mid credit − fill credit) per unit of risk. "Mid-fill" = the hold result if entry had been at the mid (for reference only).

| Strategy | Band | Exit | Trades | Sessions | Mean | 95% CI | Median | Win | Worst 1% | Worst 5% | W5/G | Cost | Mid-fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short straddle | ≤10% | hold | 21,121 | 239 | **−2.2%** | [−4.2, −0.1] | +5.0% | 57% | −170% | −76% | 0.49 | 1.4% | −0.7% |
| | ≤10% | mid | 20,920 | 239 | −4.0% | [−5.4, −2.7] | +0.7% | 52% | −87% | −43% | 0.73 | | |
| | ≤20% | hold | 50,505 | 239 | −2.5% | [−4.3, −0.9] | +4.8% | 56% | −171% | −78% | 0.50 | 2.5% | 0.0% |
| | ≤35% | hold | 77,495 | 239 | −3.1% | [−4.9, −1.3] | +4.2% | 56% | −171% | −78% | 0.52 | 3.5% | +0.4% |
| Short 25-delta strangle | ≤10% | hold | 5,209 | 223 | **−1.0%** | [−3.4, +1.1] | +9.5% | 68% | −145% | −68% | 0.56 | 0.6% | −0.5% |
| | ≤10% | mid | 4,901 | 222 | −1.1% | [−2.5, +0.1] | +2.1% | 62% | −64% | −26% | 0.66 | | |
| | ≤10% | tp50 | 5,209 | 223 | −1.2% | [−3.2, +0.8] | +8.5% | 73% | −143% | −64% | 0.61 | | |
| | ≤20% | hold | 19,874 | 239 | −1.1% | [−2.7, +0.5] | +9.0% | 67% | −139% | −62% | 0.55 | 1.0% | −0.1% |
| | ≤35% | hold | 40,529 | 239 | −1.3% | [−2.7, +0.1] | +8.9% | 67% | −142% | −62% | 0.56 | 1.6% | +0.4% |
| Iron condor 25/15 | ≤10% | hold | 1,710 | 194 | **−5.7%** | [−10.7, −1.3] | +28.7% | 60% | −100% | −100% | 0.22 | 3.4% | −2.3% |
| | ≤10% | tp50 | 1,710 | 194 | −4.8% | [−9.3, −0.9] | +24.2% | 64% | −100% | −100% | 0.23 | | |
| | ≤20% | hold | 5,292 | 231 | −9.1% | [−12.9, −5.7] | +23.8% | 58% | −100% | −100% | 0.24 | 6.2% | −3.0% |
| | ≤35% | hold | 13,178 | 239 | −12.0% | [−15.1, −9.0] | +19.0% | 58% | −100% | −100% | 0.28 | 9.3% | −2.7% |
| Put credit spread 25/15 | ≤10% | hold | 3,492 | 227 | **0.0%** | [−6.0, +5.2] | +20.2% | 78% | −100% | −100% | 0.29 | 2.4% | +2.4% |
| | ≤10% | mid | 3,354 | 226 | −10.6% | [−15.5, −6.0] | +0.9% | 51% | −128% | −80% | 0.94 | | |
| | ≤10% | tp50 | 3,492 | 227 | −0.7% | [−5.7, +3.6] | +16.3% | 81% | −100% | −100% | 0.33 | | |
| | ≤20% | hold | 12,228 | 238 | −2.9% | [−8.0, +1.3] | +17.6% | 77% | −100% | −100% | 0.32 | 4.4% | +1.5% |
| | ≤35% | hold | 26,936 | 239 | −5.0% | [−10.0, −0.7] | +14.9% | 76% | −100% | −100% | 0.37 | 6.3% | +1.2% |

With all two-sided quotes (no spread limit) every structure is clearly negative: straddle −6.6%, strangle −3.2%, condor −18.6%, put spread −8.3%. Session-equal-weight means (supplement) have the same sign and are slightly worse. The average hold is 28–30 days. For the naked structures, the worst 1% is a loss of 1.4–1.7x the margin proxy (28–34% of notional in one month); the single worst was QUBT, Nov–Dec 2024, at −49x.

### 7–20 DTE (hold, mean [95% CI])

| Strategy | ≤10% | ≤20% | ≤35% |
|---|---|---|---|
| Short straddle | −0.8% [−2.3, +0.8] (n 13,527) | −1.2% [−2.5, +0.1] | −1.4% [−2.7, −0.2] |
| Short strangle 25-delta | −0.4% [−2.0, +1.0] (n 4,246) | −0.7% [−2.0, +0.6] | −0.6% [−1.7, +0.5] |
| Iron condor 25/15 | −2.6% [−6.4, +1.1] (n 1,720) | −7.7% [−10.6, −5.1] | −10.8% [−13.0, −8.6] |
| Put credit spread 25/15 | +0.5% [−3.9, +4.4] (n 2,997) | −2.5% [−6.3, +1.1] | −4.6% [−8.0, −1.5] |

The mid-life exit is worse again (for example, straddle ≤20%: −3.2% [−4.6, −2.1]).

## 4. Where it is strongest and where it breaks

**IV ÷ EWMA forecast band (20–45 DTE, ≤20%, hold).** No band turns the result positive, and there is no monotone improvement when IV is "expensive":

| IV ÷ forecast | ≤0.8 | 0.8–1.0 | 1.0–1.2 | 1.2–1.5 | 1.5–2.0 | >2.0 |
|---|---|---|---|---|---|---|
| Straddle | −2.4% | −2.7% | −2.8% | −1.7% | −2.0% | −5.8% |
| Strangle | −1.0% | −1.8% | −0.9% | −1.1% | +0.5% [−1.7, +2.9] | −2.5% |
| Iron condor | −8.5% | −11.5% | −7.4% | −7.1% | −9.7% | −23.2% |
| Put spread | −1.2% | −3.3% | −2.0% | −3.6% | −5.6% | −8.9% |

When IV is more than 2x the forecast, results are the *worst*. Those are mostly names with a known event priced in, where the event then happens. With no event calendar, "IV is expensive against our forecast" does not identify premium that can be sold. The §5b.2 finding (delivered volatility above IV only 9% of the time in that band) describes the typical window, not the P&L-weighted tail.

**Jump windows (after the fact, 20–45 DTE, ≤20%, hold).**

| | Jump (a move > 4σ occurred) | No jump |
|---|---|---|
| Straddle | −25.1% [−30.4, −21.1], n 8,110 | **+1.8% [+0.1, +3.5]**, n 42,395 |
| Strangle | −17.7% [−22.4, −14.4] | **+2.1% [+0.7, +3.6]** |
| Iron condor | −34.8% | −3.7% [−7.2, −0.7] |
| Put spread | −19.4% | +0.5% [−4.3, +4.5] |

7–20 DTE shows the same pattern: straddle +1.6% / strangle +1.7% without jumps, −31% / −27% with. **The whole edge is the premium earned outside jump windows, and it is about 2% of margin per month, before the jumps take it back.** It would only become usable with an ex-ante way to avoid jump windows, and none has been measured (see §5).

**Underlying move over the hold.** Straddles and strangles earn +14% to +31% when the stock ends within ±5%, and lose 9–27% beyond. Losses are larger on up-moves (> +5%: straddle −27%) than down-moves (−12%): the sample is a rising, momentum-heavy market. The put credit spread earns +19% to +21% in every flat or up bucket and −57% in the down > 5% bucket. **Its near-zero mean is a bet on a rising market, not a volatility premium.** By quarter it ranges from −26% (2025 Q1) to +14% (2025 Q2).

**Index and sector ETFs (supplement; about 12–25 tickers, no single-company earnings).** This is the best cell, and still not significant:

| 20–45 DTE, hold | ≤10% | ≤20% |
|---|---|---|
| Strangle | +0.9% [−0.8, +2.7], n 786, win 72%, worst 5% −37% | +0.8% [−0.9, +2.5] |
| Put spread | +2.4% [−5.7, +9.7], n 615 | +3.2% [−3.9, +8.9] |
| Straddle | −0.1% [−2.3, +2.3] | +0.4% [−1.5, +2.6] |
| Iron condor | −3.4% [−11.0, +4.2] | −4.0% [−10.9, +2.1] |

For comparison, single names in the same cells: strangle −1.4%, put spread −0.5%. At 7–20 DTE, ETF strangles are +0.6% to +0.9% and put spreads +2.4% to +4.1%, with all intervals including zero.

**Liquidity.** Every structure gets steadily worse as the spread limit widens. The entry spread alone costs 0.6–1.4% of risk for naked structures and 2.4–3.4% for spreads at ≤10%, rising to 9–17% for condors in wide bands. With mid fills the tight-band results sit near zero (straddle −0.7%, strangle −0.5%, put spread +2.4%, condor −2.3%). **Spreads turn a zero or slightly positive premium into a loss.** Four-leg condors pay the most spread and lose 100% in about 17% of trades. A 25/15 condor collects only about 16% of its width.

**Early exits do not help.** The mid-life exit is worse than holding in every cell (the ask is paid on the way out, and less time decay has been captured). tp50 triggers in 24–47% of 20–45 DTE spread and strangle trades and changes the mean by less than 1 point. The mid-exit sample is biased *favourably*: trades without a mid-life quote (the price moved outside the stored strikes) do much worse when held (straddle −44.6% vs −2.1%). The early-exit numbers are therefore, if anything, too kind.

## 5. What cannot be concluded

1. **Sample.** 94% of trades come from May 2024 – Aug 2026, about 2.3 years of weekly entries. Before that only about 26–30 tickers are stored (2021–2023). It is mostly a rising market with a few sharp drawdowns (Aug 2024, Mar–Apr 2025, Q1 2026). A 2008/2020/2022-style volatility regime is essentially absent, so **tail losses are probably understated**, not overstated.
2. **No event calendar exists historically.** Jump windows are identified only after the fact, and the only no-earnings proxy is the ETF subset. A result filtered by an earnings calendar might recover the non-jump +2% on single names. That cannot be tested until a point-in-time event calendar exists, and even then surprise jumps (13–16% of 20-session windows in §5b.1) remain.
3. **Computed IVs and deltas.** Black-Scholes, European, q = 0, a flat 4.5% rate. Strike choice for 25-delta and 15-delta legs will be off for dividend payers and deep-ITM American options. The straddle and hold P&L do not depend on IV.
4. **Stored request window (40 strikes, 7–60 DTE, OI ≥ 1).** Wings are often outside the window (58,000 condor and put-spread candidates had no valid wing), later quotes go missing when the price moves (mid-exit coverage 68–99%), and some straddles were excluded because the strike grid was too wide. Missing quotes were recorded as missing, never substituted.
5. **Fills.** EOD bid and ask are assumed achievable in the size quoted. Real fills can improve inside the spread for liquid names (the mid-fill column bounds this) but slip in size and in fast markets. Assignment, early exercise, borrow and dividend risk on short calls, and margin calls are not modelled. The 20% notional margin proxy understates broker margin in stressed names.
6. **Overlap.** Weekly entries on 30-day options overlap. The block bootstrap allows for this, but 239 sessions is still about 60 independent monthly periods, so intervals of ±2 points on naked strategies are the real precision.
7. **Would it survive an event calendar?** Possibly for strangles and straddles on single names, since the non-jump P&L is +1.6% to +2.1% with intervals clear of zero. That is an upper bound: it removes *every* jump, including unscheduled ones, which no calendar can do. Condors stay negative even without jumps (−3.7% to −4.3%). Put spreads depend on market direction.

## 6. Conclusion for ACK

- **No structural short-volatility edge survives real fills and tails in this data.** The volatility premium exists (IV above delivered about two thirds of the time), but its average value is about the size of the bid-ask spread, and jump windows take it back with interest.
- **Ranking, best to worst:** 25-delta strangle ≈ ETF put spread (about zero, not significant) > straddle (slightly negative, significant at ≤20%) > put credit spread on single names (a directional bet) > 25/15 iron condor (clearly negative: spread cost and frequent maximum loss).
- **The necessary conditions for any future edge,** which should be tested before any decision authority (G1–G4): (a) tight markets (every leg ≤ 10% of mid); (b) products without company events (index/sector ETFs), or a point-in-time event calendar; (c) hold to expiry rather than paying a second spread to exit; (d) an ex-ante jump-risk signal. IV ÷ EWMA alone is not that signal: the highest band is the worst.
- **Implication for the pipeline:** there is no case for adding a premium-selling expression. The finding supports the WP1 rule to price options against spread cost and to treat event windows separately.
