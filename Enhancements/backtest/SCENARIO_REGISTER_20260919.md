# Backtest scenario register — why the pipeline is not yet monetisable, and what to test

19 September 2026 · v2 · ACK instructions: backtest the pipeline **as is**; evaluate alternative scenarios **inside
the backtest only** until a way forward is agreed; the plan must address **every reservation** about why the
pipeline is not monetisable. Nothing here is implemented in the pipeline. Definitions, populations, measures and
pass criteria are fixed here **before** any scenario result is read. Every run is a ledger trial
(`Enhancements/backtest/ledger/run_ledger.py`) and counts toward the multiple-testing controls.

Sources of the reservations: `Enhancements/assessment/MONETISATION_BLOCKERS_20260918.md` (M1–M11),
`SIGNAL_TICKET_BACKTEST_20260917.md`, `EXIT_RULE_STUDY_20260917.md`, the 18–19 Sep fix work and the anticipatory
design thesis (M12–M24).

---

## 0. H+ is now live (19 Sep 2026, re-scored after the 760-ticker daily backfill)

`Enhancements/research/legacy_signal_scoring.py` re-run: 1,786 legacy recommendations, 26 May-27 Aug 2026, option
coverage 96.3% (1,719/1,786) now that the backfill supplies daily rather than weekly-only chains. Corroborates
round 1 on an independent, earlier, larger sample: underlying ~flat (h20 mean -0.7%, hit 50%), options lose far
more (h20 mean -26.4%, hit 27%, >=+100% share 9.7%), CALLs underperform PUTs (regime, not stock skill). Top-5-per-
run beats the field on a second sample (-8.4% mean / 33% hit / 11.9% >=+100% vs -19.2%/28%/6.3% at h5) -
independent confirmation the ranking carries information even though options remain net negative. New finding:
NEGATIVE_RR-flagged trades carry the highest 20-session tail share of any verdict bucket (15.1% >=+100%) despite
the worst 5-session result - direct evidence for rank-not-gate, feeds FX/TC. Full detail:
`Enhancements/research/legacy_signals/legacy_signal_summary.json`.

## 1. Populations

| Id | Population | Source | Judges |
|---|---|---|---|
| H | Recorded evening books 31 Aug–16 Sep 2026 (**pre-fix pipeline**), today's ticket rules and calibrated valuation | `signal_ticket_backtest_rows.csv` (frozen, sha-checked) | Rules applied to the old candidates only |
| H+ | H plus the 1,786 legacy recommendations re-scored after the weekend Phantom backfill | backfill + `legacy_signal_scoring.py` | Larger sample for exits, eligibility, spread |
| U | Recorded Discovery books, underlying only (price store since Aug 2021; books where recorded) | canonical price store | Direction, lead time, anticipation — no option data needed |
| N | Evening runs on the **fixed** pipeline, from the next run; outcomes mature over the following sessions | run outputs + outcome ledger + open-record marks | Everything this week's fixes changed |

Results from H never judge the fixed pipeline; N does. A scenario is only proposed for build when it passes on the
historical population **and** keeps its sign on N.

## 2. Standard measures and pass criteria (apply to every scenario unless stated)

- Option layer: mean, median, share profitable, share ≥ +100%, mean issue-day portfolio return, max drawdown, under
  three fill models (quoted / timed / mid).
- Signal layer: forward underlying return in the thesis direction at 1 / 5 / 20 sessions, hit rate, expansion-event
  rate, each against a matched base rate.
- Ranking: Spearman correlation with realised return; rank-bucket means (1–5, 6–10, 11–25, 26–50, 51–100, 101+);
  monotonicity.
- **Pass criterion (pre-registered):** paired difference versus the "as is" baseline on the same trades with
  t ≥ 2.0 on the historical population, **and** the same sign on N once N has ≥ 40 closed results. Anything else is
  "no evidence", never "fail forward".
- Every trial is counted; Probability of Backtest Overfitting and the deflated Sharpe ratio are reported once ≥ 10
  trials exist in a family.

## 3. Reservation map — every reason the pipeline is not monetisable

| # | Reservation | Evidence | Status after 17–19 Sep fixes | Tested by |
|---|---|---|---|---|
| M1 | **No demonstrated direction skill** (~51%) — the root cause | Direction studies 2022–2026; H9; O1–O5 | Open | S-DIR-1…5, S-EXP-1 |
| M2 | Issuing gate rejected every large winner | 20 of 2,992 kept, all big winners rejected | **Fixed** (rank, not gate; daily cap) | Baseline on N |
| M3 | Stop at ~0.6 expected moves — noise stops trades in 2 sessions | 20/21 tickets stopped; no-stop +2.9 pts, t = 3.21 | **Open** (plan_exit still uses the underlying stop) | S-EXIT-2, S-EXIT-3 |
| M4 | Contract expires before the planned hold | Median 0.54 of hold covered; expiry cap the most common exit | **Fixed 19 Sep** (runway floor = planned hold, 40 days) | S-RUN-1, S-RUN-2 |
| M5 | Execution cost — spread consumes the premium | Legacy ~35% round trip; OTM 73–120% of mid | **Partly fixed** (single 25% selection limit; 10% ticket limit) | S-COST-1…3 |
| M6 | The convex tail is not in the instruments bought | 2.24% ≥ +100%; chains only 8–45 DTE historically | Partly (selector now buys 64–92 DTE; chains to 110 DTE) | S-CONV-1, S-CONV-2 |
| M7 | Missing data (delayed quotes, flow, long chains, event calendar, half the universe) | Provider entitlements | Open; some capture started | S-TIME-1 (quote delay); others not testable yet |
| M8 | Data integrity (GEX algorithm and invented GEX map, corporate actions, money index) | GEX investigation | Open (GEX still reaches size and exit) | S-ABL-3 |
| M9 | Gate architecture produced empty days | 0 actionable on 17 Sep | **Partly fixed** (daily tickets); 430 FINAL_ACTION_BLOCKED remain, allowed if understood (CI) | S-ELIG-1…3 |
| M10 | Nothing validated forward | Forward gate 40 tickets / 15 sessions | Running | Forward record (N) |
| M11 | Product framing — expectancy vs "alerts with winners" | 2.24% ≥ +100% | Open (strategic) | S-PORT-1, S-PORT-2 |
| M12 | Ranking key favours capped losses, not asymmetry | Cautious rank 0.518 vs central 0.429; XLP-type tickets | Kept (evidence) | S-RANK-1…5 |
| M13 | Valuation shows negative value almost everywhere | Central negative on most rows | Open — **the path model has no drift: it is a cost model and cannot show value without a measured edge input** | S-VAL-1, S-VAL-2 |
| M14 | Direction contradicts Wyckoff structure (163 rows unvaluable) | 18 Sep | Labelled 19 Sep | S-ELIG-2, S-DIR-3 |
| M15 | Stop too distant for a target (42 PUTs) | 18 Sep | Labelled 19 Sep | S-ELIG-3 |
| M16 | Features never enter the ranking | Deep dive | Open | S-RANK-4, S-ABL-1, S-ABL-2 |
| M17 | Entry timing — evening signal, morning entry on a 15-minute delayed quote, overnight gap | Quote-feed evidence | Open | S-TIME-1, S-TIME-2 |
| M18 | Book direction vs market regime (64% CALL in a falling tape) | Exit study window | Open (macro informs, never scores) | S-REG-1, S-REG-2 |
| M19 | Hold length — 20 sessions of theta vs the anticipated move | D2 decision | Open | S-EXIT-1, S-EXIT-4 |
| M20 | Buying expensive implied volatility | True IV percentile (F2) available from N | Open | S-IV-1, S-IV-2 |
| M21 | Event convexity untested (earnings) | Blockers item 4 | Open | S-CONV-2 |
| M22 | Flat features hid the edge (volume, sector, regime, physics, IV) | 18–19 Sep | **Fixed** (F1–F8 minus F4/F7) | S-ABL-1 on N |
| M23 | Entering early may mean false starts | Anticipatory thesis | Open | S-ANT-1…3 |
| M24 | Concentration (same sector / root cause) | Ticket lists | Open | S-RANK-3 |

## 1a. Four monetisation layers (ACK 19 Sep 2026)

Every scenario belongs to one layer; each layer has its own scorecard so a loss can be traced to the layer that
caused it (wrong direction / wrong timing / wrong instrument / excessive friction / premature exit).

| Layer | Question | Scenario families |
|---|---|---|
| **A — Intelligence** | Does AVSHUNTER find movement, direction, timing and regime-specific effects — market-adjusted? | IA-1, IA-2, IA-4, IA-5, IA-7, IA-9; S-DIR-1…5; S-ANT-1…3; S-REG-1…2; S-ABL-1…3 |
| **B — Pricing** | Is the expected move larger or more favourable than the market already charges (realised vs implied; distribution vs price)? | IA-3; IA-8; S-VAL-1…2; S-IV-1…2 |
| **C — Expression** | Which permitted instrument, contract and cost best monetise the opportunity? | EXPR-*; opportunity rank vs expression rank (S-RANK split); S-RUN; S-VALSEL; S-COST; S-TIME; S-CONV; S-PORT; S-ELIG |
| **D — Management** | How to hold, exit, re-express and preserve the right tail? | S-EXIT-1…7; TAIL-CAPTURE; right-tail measures |

Ranking is split in two for layer C: **opportunity rank** (which underlying opportunity has the strongest evidence —
movement, direction, timing, structure, regime, calibrated confidence) and **expression rank** (which instrument /
contract monetises it best — expected value against the price, cautious scenario, cost, liquidity). The cautious
return is tested in the expression role.

Order of evidence: layer A and IA-3 first — they confirm or refute the two premises the monetisation study rests on
(magnitude information; fast signal decay) before layers C and D are built on them.

### Right-tail measures (required in every layer C and D scenario)

Mean, median, share ≥ +50 / +100 / +200 / +500%, largest winner retained, tail contribution (share of total profit
from trades ≥ +100%), time to +50 / +100 / +200 / +500%. A rule that improves the median while reducing tail capture
is reported as such, never as a plain improvement.

### Family FX — Extreme-winner forensics (layer A/C, measurement only)

| Id | Test | Population |
|---|---|---|
| FX-1 | State at entry of every closed trade ≥ +100% and ≥ +200% (+500% as case studies): direction, move, time to peak, delta, gamma, DTE, moneyness, IV and IV percentile, spread, volume, OI, sector, regime, Wyckoff, Crabel, relative strength, physics, catalyst proximity | H, H+, N |
| FX-2 | The same state for matched losing contracts (same session, same direction, similar premium) — what was systematically different before the winners? | H, H+, N |
| FX-3 | Calls and puts studied separately (downside tails behave differently: IV expansion, skew repricing) | H, H+, N |

Sample sizes are small (67 trades ≥ +100%, 13 ≥ +200%, none ≥ +500% — best +479% — in 2,992 closed on H; +515% exists only in the rebuilt-contract set); FX findings are
hypotheses for layer A/B tests, never selection rules on their own.

### Family TC — Tail capture (layer D/C, measurement only)

| Id | Test | Population |
|---|---|---|
| TC-1 | Every historical underlying move large enough that a listed option returned ≥ +100 / +200 / +500%: was the ticker in Discovery, direction right, rank, contract chosen, winning contract available, and which rule (spread, delta, DTE, rank, stop, cap) removed it? | H, H+ (chains where stored) |
| TC-2 | Tail capture rate = tail opportunities captured ÷ tail opportunities available, per threshold, per stage | H, H+, N |
| TC-3 | Convex frontier: per thesis, all eligible contracts on (probability of loss, tail payoff); share of chosen contracts that are dominated | N (long-dated chains now stored) |

Forward ledger fields for every option mark (from N): hit_50 / hit_100 / hit_200 / hit_500, max return, time to each
threshold — the survival data a tail model will need.

### Pre-registered after batch 4 (approved by ACK 19 Sep 2026; definitions frozen before any test)

- **S-IV-3 — expression-rank tilt by volatility cheapness (layer B/C).** Expression rank = 0.7 × percentile rank of
  the cautious return + 0.3 × percentile rank of volatility cheapness, where cheapness = the mean of the percentile
  ranks of (forecast volatility ÷ contract IV) and (1 − true IV percentile), both within the session. Weights fixed
  here. Compared with A0 (cautious only) on the same eligible set: top-5 and rank-bucket outcomes, right-tail
  measures. Populations: N; the weekly-chain year where contract IV and forecast exist point-in-time.
- **EXPR-BAR-2 — core + convex satellite (layer C).** Core: the contract the pipeline selects today (runway ≥ planned
  hold). Satellite, added only when all hold at entry: anticipated move horizon 1–5 sessions; same direction;
  |moneyness| ≤ 2%; 7–21 days to expiry; entry spread ≤ 10% of mid; contract IV ÷ forecast volatility ≤ 1.0.
  Premium split 75% core / 25% satellite of the same total premium. Satellite managed by S-EXIT-8 (no stop, fair
  value, right-tail floor); core by the policy under test. Compared with core-only on the same trades. Populations:
  H+ (where chains hold both contracts), N.
- **FX hypotheses (to be confirmed or rejected on H+ and N; never selection rules on their own):**
  H-FX-1 winners bought cheaper volatility (IV ÷ realised / forecast lower; IV rank lower);
  H-FX-2 winners had tighter spreads and more open interest / volume;
  H-FX-3 winners traded with the stock's own recent trend — to be re-tested market-adjusted (regime confound);
  H-FX-4 the extreme tail (≥ +200%) came from near-the-money, 9–20 DTE contracts on fast moves (1–11 sessions);
  H-FX-5 Wyckoff structure did not predict direction (10 of 12 put winners ≥ +200% sat in ACCUMULATION).
  Source: `Enhancements/research/intelligence_audit/fx_extreme_winner_forensics_H.json` (67 winners ≥ +100%,
  13 ≥ +200% of 2,992 closed; one falling regime; ~37 features per direction tested, so p-values are indicative).

- **EXPR-CHOOSE-2 — choose the instrument by the option's price (layer C; registered 19 Sep 2026, before any test).**
  At entry compute cheapness = contract (ATM) IV ÷ trailing 20-session realised volatility, and its percentile within
  the tradeable universe on that date (point-in-time). If cheapness is in the **cheapest 40%** of the universe: express
  with a long call (bullish) or long put (bearish), nearest-to-the-money eligible contract (|moneyness| ≤ 2.5%), runway
  per the planned hold. Otherwise: bullish → **long shares**; bearish → **no trade** (short shares not permitted).
  Management: no underlying stop (S-EXIT-2); options additionally reported under the fair-value exit (S-EXIT-6).
  Compared with the fixed current expression (always the selected option) on the same opportunities, per layer
  scorecard and right-tail measures. Populations: N; the weekly-chain year for the option leg; U for the share leg.
  Evidence behind the definition: IA-3 year (below).

### Round 1 findings (19 Sep 2026) — recorded for the reassessment

- **Baseline (trial 9):** tickets −19.5% (timed), 5 per session, no zero days; 83% of candidates fail the 10% ticket
  spread limit.
- **IA-6:** the spread costs ~21 (top fifth) to ~39 (all) points at one session; direction ≈ market beta; the ranking
  selects magnitude, not direction.
- **IA-1/IA-2 (U 2021–2024, holdout sealed):** no market-adjusted directional information in bar features; strong
  magnitude information vs trailing realised volatility (compression t 16–24, persistent; volume ratio t 22 → 9,
  decays in days).
- **IA-3 (H):** candidates realise ~20–35% more movement relative to their IV than the universe, but still less than
  priced.
- **IA-3 (weekly-chain year, 94 Fridays, 337k observations, both halves consistent):** variance ratio 0.61–0.65
  overall (options overpriced ~35–40% in variance); cheapest IV-vs-realised fifth 0.84–1.03 (≈ fair), richest fifth
  ~0.3; low own-IV-percentile third 0.78–0.86 vs high third 0.50–0.56; high volume 0.91 at one session fading to
  0.66; **most compressed fifth 0.51–0.58 — compression is fully (over)priced, not an edge against the option price**.
  No state clearly underpriced.
- **Exits (H top fifth):** no stop +2.9 pts t 3.25 (best tail, hit 36%); fair value +4.9 pts t 3.86 (tail given up
  before +100%); S-EXIT-8 +4.8 pts t 3.78 — the +100% floor acts too late to restore the tail; fixed 1 session raises
  the mean by destroying the tail.
- **Costs (22–25 closed tickets per trial — direction only):** nearer the money (OTM limit 2.5%) tickets −13.2% vs
  −19.5%; tighter spread improves the eligible pool.
- **FX forensics:** winners bought cheaper volatility and tighter markets; extreme tail from near-the-money 9–20 DTE
  contracts on fast moves; Wyckoff structure did not predict direction (H-FX-1…5).
- **Reading:** the levers found (cheap volatility / shares when options are rich, no stop, near the money, tight
  spreads) should shrink the loss toward break-even; a profit still needs a direction or timing edge — next round:
  S-REG-2 (regime mix) and the non-price features on N, with H+ after the backfill.

### Family IV-LAG — does IV lag the structure, or price it before we can trade it? (layer B; registered 19 Sep 2026)

Motivation: IA-3 (weekly-chain year) found the *most* compressed names carry the *worst* mispricing (variance ratio
0.51–0.58) — worse than mild compression (0.62–0.67) or no compression (0.82). Read together with how IV actually
gets set (realised-vol tracking + dated catalysts + order flow — nothing reads a Bollinger/ATR percentile directly),
this says the crude compression heuristic is well-followed enough that flow has already priced it, and priced it
past fair. The edge, if any, is in getting there before that heuristic is obvious, or in a state flow hasn't reached
yet. Three sub-scenarios, each pre-registered exactly as follows before any run:

- **IA-3b — onset vs level.** Onset = first session a ticker enters the top compression quintile after ≥10 prior
  sessions outside it (point-in-time). At event-relative offsets e = 0, 5, 10, 15, 20 sessions after onset, measure
  variance ratio and IV percentile (nearest available sample). Tests whether the transition into compression prices
  closer to fair than the static extreme state.
- **IA-3c — dated vs undated catalyst.** Split variance ratio (compression-quintile-4 rows only) by whether
  `days_to_catalyst` is populated and ≤ 20 at the observation date, vs absent/further out. Tests whether "no known
  event" compression is less overpriced (off the market's mechanical radar) than compression with a scheduled
  catalyst (IV already kinked for it).
- **IA-3d — before vs after flow arrives.** Split variance ratio (compression-quintile-4 rows) by contract volume
  and open-interest percentile in the prior 5 sessions (proxy for "has the crowd already positioned"). Tests
  whether pre-flow compression prices fairer than post-flow.

Populations, in order of what they can honestly answer:
1. **Coarse / full universe (now):** the weekly-chain year (94 Fridays), ~5-session event resolution. Unbiased
   across the tradeable universe; can't resolve a lag shorter than one weekly step.
2. **Fine / biased (after the weekend backfill):** the 760 tickers and 21 May – 2 Aug 2026 windows the targeted
   backfill restores at daily resolution. Daily resolution, but **selection-biased** — only names the old pipeline
   already flagged as candidates, not a random cross-section. Reported as a validity check on the coarse result,
   never as the clean answer.
3. **Fine / unbiased (from N, as it accumulates):** every evening run now derives that session's IV history
   automatically (the 19 Sep refresh fix), so a genuine daily, unbiased series builds itself going forward. This is
   the population that settles IA-3b/c/d once enough sessions exist.

## 2a. Permitted expressions for research (ACK 19 Sep 2026)

The expression layer chooses among permitted **long** instruments — one, or a combination — rather than a fixed
call-or-put: **shares (long only; never short), a long call, a long put, or shares combined with a long option**
(shares + long call; shares + long put), or **no trade**. Long straddles / strangles (long call + long put on the
same name) are **not permitted** (ACK 19 Sep 2026). Research scenarios may compare any
of these on the same opportunity; nothing is implemented in the pipeline. Shares are priced with the existing
share leg of the path valuation (`emp_share_r_*`, measured share spread).

Expression scenarios (layer C): EXPR-SHARES-1 (shares only), EXPR-CALL-1 / EXPR-PUT-1 (single option),
EXPR-BAR-1 (shares + convex long call, one risk budget), EXPR-HEDGE-1 (shares + long put), EXPR-CHOOSE-1 (the best expression per opportunity by expected value against
the market price, versus the fixed current choice). Every expression scenario reports the right-tail measures below.

## 3a. Family IA — Intelligence Audit (runs first; ACK 19 Sep 2026)

Question before any strategy: **what does AVSHUNTER know that the market does not yet price, and where along the
chain is that information kept or lost?** Temporarily ignore GO/WAIT/BLOCK, tickets, cap, stop, contract and exit;
measure the information content of the pipeline's own evidence, then how much survives each transformation.

| Id | Test | Population |
|---|---|---|
| IA-1 | Information per feature: rank correlation of the **raw continuous** value with forward return at 1 / 2 / 3 / 5 / 10 / 20 sessions | U (bar-derived features, ~5 years); weekly chains (options-state features, ~1 year) |
| IA-2 | Decay: IA-1 by horizon for each feature — the signal half-life that contract expiry should follow | U |
| IA-3 | Magnitude vs direction: forward absolute move **÷ implied move at entry** (realised ÷ priced), then direction conditional on large moves. Raw magnitude is never the outcome: the option price already charges for it | U + weekly chains |
| IA-4 | Conditional information by regime (volatility regime, trend, sector state) | U |
| IA-5 | Incremental information: does a feature add anything once the others are known (partial correlation; model with and without it on the holdout) | U |
| IA-6 | **Transformation loss**: information surviving each step — universe → Discovery candidates → ranking → tickets → option expression → after stop → after spread → net | H now; N later |
| IA-7 | Discretisation loss: continuous value vs its label, same holdout | U |
| IA-8 | Calibration: stated probabilities (Layer 2 target-hit probability) vs realised; outcome monotonicity by confidence bucket | H+, N |
| IA-9 | Interactions: a short list fixed before looking (compression × relative strength, structure × IV state, early pressure × regime); any wider search only inside the exploration period | U |

Governance for IA: exploration 2021–2024, confirmation holdout 2025–2026 (untouched until exploration findings are
frozen), purging between train and test, every test logged, PBO / deflated Sharpe reported for the family.
Features are used only where they exist point-in-time: bar-derived over ~5 years, options-state over ~1 year of
weekly chains, full-pipeline features (physics verdict, geometry, value fields, macro) only where runs are recorded.

The scientifically accurate statement until IA reports: "we have not yet identified where AVSHUNTER's information
becomes economic edge, or where the decision chain destroys it."

## 4. Scenario catalogue

Format: **hypothesis** · variant against "as is" · population · what a pass would lead to (a design proposal, never
an automatic build).

### Direction (M1, M14)
- **S-DIR-1 Direction hit rate by evidence group.** Is direction skill concentrated anywhere? Hit rate at 1/5/20
  sessions by physics verdict, geometry label, volatility regime, relative strength, IV direction. · U, N ·
  → restrict or reweight direction where skill exists.
- **S-DIR-2 Cross-sectional tilts as direction.** 5-session reversal and distance from the 52-week low (the two
  robust findings, IC +0.02) used to rank CALL vs PUT candidates. · U · → a cross-sectional score (blockers item 5).
- **S-DIR-3 Structure wins vs governed direction wins.** For DIRECTION_CONTRADICTS_STRUCTURE rows, measure the
  underlying move in both directions. · U, N · → the direction-conflict decision.
- **S-DIR-4 Relative strength as direction.** Direction = sign of rs_vs_sector_20d_pct. · U · → RS input to
  direction governance (research only).
- **S-DIR-5 Market-neutral pairing.** Long the top CALL and top PUT per session together. · H, N · → removes market
  direction from the book's result.

### Expansion without direction (M1 alternative)
- **S-EXP-1 — withdrawn (ACK 19 Sep 2026: long straddles / strangles are not permitted).** Magnitude information,
  if IA-3 confirms it, must be monetised through a permitted directional expression: which name to trade (magnitude
  ranking) and which permitted instrument (layer C).

### Ranking — the de facto gate (M12, M16, M24)
- **S-RANK-1** central return · **S-RANK-2** upside ÷ |cautious| · **S-RANK-3** cautious with one ticket per sector
  and per root cause · **S-RANK-4** cautious plus a feature tilt (physics verdict, true IV percentile, relative
  strength, volatility regime, reversal, 52-week-low distance), weights fixed before the run · **S-RANK-5** cap 10
  and cap 20 instead of 5. · H, N · → the D3 ranking decision.

### Exits (M3, M19)
- **S-EXIT-1** fixed 1 / 3 / 5 / 10 / 20 sessions (signal quality without exit logic).
- **S-EXIT-2** no underlying stop inside the planned hold (premium is the maximum loss) — replicate +2.9 pts on H+.
- **S-EXIT-3** stop at 1.5 expected moves.
- **S-EXIT-4** exit at the anticipated move horizon (anticipated_move_sessions) instead of the 20-session hold.
- **S-EXIT-5** sell into the first expansion event after entry ("sell into the herd", P6).
- **S-EXIT-6** option-value exit that compares holding against the **bid** (the fair version of the degenerate
  re-value rule).
- **S-EXIT-7** roll at the last exit session (ledger trial 18 Sep).
- **S-EXIT-8** (registered 19 Sep 2026, before any run) — **no underlying stop + fair-value exit + right-tail floor.**
  Each session with a stored quote: exit when the option's expected (central) value of holding the rest of the plan,
  priced against the current **bid**, is below zero (S-EXIT-6) — **unless** the position is already at ≥ +100% (bid ≥ 2
  × entry ask), in which case the fair-value exit is suspended and the trade runs to target, planned hold or the
  contract's last usable session. No underlying stop at any point. Compared paired against baseline, S-EXIT-2 and
  S-EXIT-6, with the right-tail measures. Motivation: batch 2 (history H) — S-EXIT-2 +2.9 pts t 3.25 with the best
  tail; S-EXIT-6 +4.9 pts t 3.86 with some tail given up.
- · H, H+, N · → the exit policy decision (D4).

### Runway and contract (M4, M6)
- **S-RUN-1** nearest expiry covering the hold vs longest eligible expiry (premium vs runway).
- **S-RUN-2** share of exits at the last usable session, before vs after the 19 Sep runway fix.
- **S-CONV-1** long-dated convexity: 60–120 DTE, ~0.25 delta on COMPRESSION / EARLY_PRESSURE names. · N (chains now
  reach 110 DTE) · → a convex expression.
- **S-CONV-2** earnings convexity: cheap volatility bought before dated catalysts. · H+ where event dates exist, N ·
  → blockers item 4.
- **S-VALSEL-1/2** contract chosen by value (central / cautious) among contracts covering the hold (the SHADOW
  fields) vs score choice. · N · → ACTIVE value selection.

### Costs and timing (M5, M7, M17)
- **S-COST-1** ticket spread limit 5% / 10% / 15%.
- **S-COST-2** limit order at mid vs the ask (fill-model sensitivity already in the harness).
- **S-COST-3** delta band 0.35–0.55 vs 0.20–0.75 (tighter moneyness, lower spread).
- **S-TIME-1** return by quote age at entry (15-minute delayed feed).
- **S-TIME-2** entry at the evening close ask vs morning (open + 15 min) vs open + 60 min, using the open-record
  marks. · N · → entry timing rule.

### Valuation (M13)
- **S-VAL-1** calibration by bucket: predicted vs realised return, per decile of central and cautious value. · H+, N ·
  → trust in the cost model.
- **S-VAL-2** conditional drift: value with a drift equal to the measured forward return of the candidate's evidence
  group (from S-DIR-1), research only. · N · → whether any measured edge makes value positive after costs.

### Eligibility (M9, M14, M15)
- **S-ELIG-1** C0 plus rows removed by FINAL_ACTION_BLOCKED, split by block reason (first: the fact / threshold /
  forecast mix, and whether a blocked row can still become a ticket). Blocks are allowed when understood; this
  prioritises the continuous-improvement list.
- **S-ELIG-2** DIRECTION_CONTRADICTS_STRUCTURE rows, underlying both ways (with S-DIR-3).
- **S-ELIG-3** STOP_TOO_DISTANT_NO_TARGET rows with a nearer structural stop (most recent swing high), underlying.

### Volatility price (M20)
- **S-IV-1** outcome by true IV percentile bucket at entry. · **S-IV-2** IV direction (rising / falling) at entry. ·
  N (true IV percentile exists from N; history restored) · → an IV tilt in ranking.

### Regime (M18)
- **S-REG-1** outcome by volatility regime (F3) and macro regime (recorded, display-only).
- **S-REG-2** CALL/PUT mix vs market direction per session. · H, N · → a regime-aware mix (never a macro score
  without evidence).

### Anticipation (M23, the thesis)
- **S-ANT-1 Lead time.** T0 = first session in a Discovery book; TC = first governed expansion event (P2 definition
  registered before the run). · U
- **S-ANT-2 Confirmation tax on the underlying** (move T0→TC) and on the option where daily chains exist (same and
  equivalent contract). · U, N (indicative)
- **S-ANT-3 False-start rate and cost** (no event within 20 sessions; adverse excursion; stop hits). · U
- Net anticipation value = confirmation tax saved − false-start cost − extra execution cost.

### Component ablation (M8, M16, M22)
- **S-ABL-1** remove one feature at a time from the S-RANK-4 tilt (physics, IV, RS, regime, Crabel/Wyckoff detail).
- **S-ABL-2** leading-only vs leading+context vs all (roles assigned **by measured lead time** from S-ANT-1, not by
  opinion).
- **S-ABL-3** outcomes with and without GEX influence on size and exit.

### Portfolio and product (M11)
- **S-PORT-1** breadth: top 20 per session at equal small premium — distribution of ≥ +100% winners vs the average.
- **S-PORT-2** barbell: top 5 by cautious plus 5 convex (S-CONV-1) per session.

## 5. Order and dependencies

| Step | Scenarios | Needs |
|---|---|---|
| 1 | Baseline "as is" on H; S-RANK-1…5, S-EXIT-1…3/6/7, S-COST-1…3, S-VAL-1, S-REG-2 | IV catch-up finished (Phantom free) |
| 2 | S-ELIG-1 (understanding first), S-EXIT on H+ | Weekend backfill, legacy re-score |
| 3 | P2 expansion-event definition registered (ACK) → S-ANT-1…3, S-DIR-1…4, S-EXIT-4/5 on U | ACK approves the event definition |
| 4 | Everything on N: S-VALSEL, S-RUN, S-IV, S-EXP-1, S-CONV-1, S-TIME, S-ABL, S-PORT | First evening runs on the fixed pipeline; results as outcomes mature |

## 6. Rules

- Definitions are frozen; a changed definition is a new scenario id, never an edit of this one.
- Every run is a ledger trial; results are compared with the baseline on the same dataset hash only.
- No scenario changes the pipeline. A scenario that passes becomes a written design proposal for ACK with its
  evidence; nothing is built without that decision.
- Blocks are allowed when their reason is understood (ACK 19 Sep); S-ELIG results feed the continuous-improvement
  list, not a removal programme.
- Pipeline behaviour observed during the backtest is recorded in `PIPELINE_AS_IS_NOTES_20260919.md`.
