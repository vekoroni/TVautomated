# Lessons and requirements register (copied from the trade journal, 12 Oct 2026)

Source: `data/journal/trade_journal.db` tables `lessons_learnt` and `mining_outcomes` (ACK, 12 Oct 2026; AVSHUNTER
lessons register 12-Oct-2026). Rule, evidence, confidence and status are copied verbatim; the last two columns
map each entry to its pipeline owner and its place in `DISCOVERY_VANGUARD_BEHAVIOURAL_STAGE_DESIGN_20261012.md`.
Aim (ACK 12 Oct): the pipeline produces accurate data early enough to get the trade; mining owns the trade.

ACK clarification, 12 Oct 2026: R4 is the flow of money as supporting context - it does not rank or gate (CLAUDE.md
rule 6 unchanged).

| Code | Title | Rule | Evidence | Confidence | Status | Pipeline owner | Where in the plan |
|---|---|---|---|---|---|---|---|
| R1 | Hand-off by trigger close | trigger_close_date, sessions_since_trigger, state at last close; Evening after every close | FRO 2 sessions late | High | OPEN | Discovery event fields + run cadence | Discovery fields (small); Evening after every close is ACK's call |
| R2 | p_fast per setup | P(+1 ATR within 3 sessions) with n, calibrated +-10 pts on 200+ rows | Base rate 28% | Medium | OPEN | Vanguard statistics keyed on the reading | Step 7 |
| R3 | Outcome ledger | Score every hand-off row and card at +1/+3/+5/+10: side, +1 ATR first, half target first, stop first; passes included | 12-Oct scorecard built by hand | High | OPEN | Measurement | Exists: decision ledger + trade journal mining_outcomes; pipeline rows to be scored automatically |
| R4 | Money alignment with holdings-based sectors | Ranked field; zero tag disagreements on 60-row sample | S, WIX, UTI, XOVR, OI mis-mapped | High | OPEN | Context field beside the reading (ACK 12 Oct: supporting money flow, not rank or gate) | Macro board per-ETF mapping by holdings |
| R5 | Event calendar per row | Earnings, peer prints, macro, geopolitical with date and skew; Friday carry flag | FRO gap was an event | Medium | OPEN | Reference data | New |
| R6 | Contract family by thesis timing | Weekly to 90 days, 10% ITM to 15% OTM, valued at q50/q80; premium ceiling input | 85/142 best contracts >$3; TEM, PLUG, FRO re-selected by hand | High | OPEN | Options | Contract-expiry defect (883 expire before the median move; no contract > 67 DTE) |
| R7 | Next-leg targets | Re-emit targets when price passes half target | FRO, TK, SOUN | High | OPEN | Discovery reference levels; target owned downstream | Step 5 |
| R8 | Entry type with evidence | Name entry type and cite its base rate and n | Pullback study | Medium | OPEN | Vanguard statistics per entry type (replay panels) | Step 7 |
| R9 | Correlation clusters | cluster_id per row; one slot per cluster | Tanker cluster | High | OPEN | Vanguard context | Step 7 |
| R10 | Timing calibration | Realised median within 30% of q50 per setup once n>=50 | FRO half target 1 session vs q50 7 | Medium | OPEN | Vanguard / calibration | Step 7 with item 10.2 (scorer window 20 sessions) |
| L1 | Enter at the first allowed close | Trade is on at the first close inside the chase limit (1 ATR daily, 2 ATR weekly/monthly) after the trigger closes; resting pullback/bounce limits need own evidence and pair with part size at the close | 60 tickers, 2,454 breakouts: 0.5 ATR pullback limit fills 75%, fills -0.29 ATR at 10 sessions; unfilled 25% +1.49 ATR (78% up). FRO and PLUG missed 12-Oct | Medium | OPEN | Mining entry; pipeline: readiness at the first allowed close | Readiness-rule test (first close vs accepted break) before step 4 |
| L2 | No extra confirmation without cross-ticker evidence | A filter goes on a card only if it beats the all-days control on 200+ cross-ticker cases | +1 ATR first: any trend day 49%, breakout close 48%, window-2 48% (n 20,842/1,294/1,057) | Medium | OPEN | Pipeline: any confirmation filter must beat the all-days control | Same test; applies to Discovery's acceptance rule |
| L3 | Expiry by speed of move | 14 DTE default; shorter when thesis timing, move vs implied move and a dated catalyst point to a fast move; same dollars at risk; exit session before expiry; premium cap is a daily parameter | Weekly ATM vs 40-day: fast (28%) +128% vs +49%; not fast -56% vs -24%; weekly wins above ~29% p_fast. FRO 16-Oct 60C +217% vs Nov 60C +41% | Medium | OPEN | Options contract family + p_fast | R2 (step 7) and R6 (Options) |
| L4 | Friday weekend-carry line | Every Friday card names weekend events, skew and whether to be in by the close | FRO +5.6% gap on 10-11 Oct tanker strikes; next-day >=1 ATR gaps after breakouts 3.9% | Medium | OPEN | Reference data: weekend events and skew | R5 |
| L5 | Money side wins ties | When base-rate challenge and money map disagree, keep money side unless challenge has 200+ cases; challenge sets entry/stop/size | 12-Oct: 18/18 money-WITH names moved right vs 15/24 AGAINST (one session, clustered). SMCI test case | Low | OPEN | Mining tie rule; pipeline supplies the money side as context | R4 (context, not rank) |
| L6 | One slot per cluster | Name the cluster and alternates; never two cards on one driver | 11 of 18 WITH names one oil move; five tanker calls in hand-off | High | OPEN | Pipeline context: cluster_id | R9 (step 7) |
| L7 | Score every card | Every card and pass written to the ledger with entry type and scored at +1/+3/+5/+10 sessions | Ledger had 2,320 blank decisions; no outcomes; journal closed_trades last entry 18-Jul | High | OPEN | Measurement: outcome ledger + trade journal | R3 (ledger updated with the trade journal, 12 Oct) |
| L8 | Re-plan when target passed | If price passes the half target before entry, re-price from next-leg targets | FRO half target in session 1; TK passed; SOUN 3 cents away | High | OPEN | Downstream re-plan; Discovery publishes next-leg reference levels | R7 (step 5 reference levels) |

## Mining outcomes, 12 Oct 2026 (provisional, 14:26 UTC marks)

| Ticker | Side | Decision | Entry state | Side right | Lessons | Requirements |
|---|---|---|---|---|---|---|
| FRO | CALL | MISSED | MISSED: trigger met only above chase limit after +5.6% weekend gap (tanker strikes 10-11 Oct) | YES | L1,L2,L3,L4,L8 | R1,R2,R5,R6,R7 |
| PUMP | PUT | WATCH | OPEN: limit order, stock 8.885 at bottom of zone; put 1.10/1.85 | YES | L1,L7 | R3,R6,R8 |
| TEM | PUT | WATCH | OPEN: entry not confirmed; put 2.87/3.10 | YES | L7 | R3,R6 |
| BTI | CALL | WATCH | OPEN: needs today close; stock 55.845, call 2.80/3.00 | YES | L1,L7 | R3 |
| SMCI | CALL | WATCH | OPEN: undercut done (low 39.68), stock 40.14, needs close >40.65; 30-Oct 42C 2.60->1.69 | NO (card); YES for first put card | L5,L7 | R3,R4 |
| OI | PUT | PASS | PASS: no trade | FLAT | L7 | R3 |
| LULU | PUT | WATCH | OPEN: on today close; failed at 95.35 (high 95.07) | YES | L1,L5 | R3,R4 |
| FISV | PUT | WATCH | OPEN: on today close | FLAT | L1,L7 | R3 |
| BILI | PUT | WATCH | OPEN: on today close | YES | L1,L7 | R3 |
| VXX | PUT | WATCH | OPEN: waits for CPI | YES | L4,L7 | R5 |
| S | CALL | WATCH | OPEN: unfilled pullback order | FLAT | L1,L7 | R4,R8 |
| LI | PUT | WATCH | OPEN: extended 3.4 ATR | YES | L1,L7 | R8 |
| HAFN | CALL | WATCH | OPEN: tanker cluster alternate | YES | L6,L1 | R9 |
| PLUG | PUT | MISSED | MISSED: no bounce; 1.55 not yet traded (low 1.585) | YES | L1,L7 | R3,R8 |
