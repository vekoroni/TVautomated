# AVS-EXP-002 — Missed Winners, Losing-Trade Diagnosis, and an Honest Read on 70% Win Rate

**Date:** 26 Sep 2026
**Status:** ANALYSIS ONLY, read-only against `data/canonical/outcome_scoring.sqlite`. No pipeline code, config, or threshold touched.
**Data available this pass:** 23,462 predictions (excl. TEST-first-sighted), 26 sessions (~5 weeks). Your machine also holds `historical_prices.sqlite` (1.09GB) and `decision_outcome_ledger.sqlite` (851MB) — likely the multi-year, 2000+-ticker depth you referenced — but this session has no shell on your machine and can't stage files over 400MB, so those aren't in this pass. See §5 for what would unlock them.
**Phantom maintenance note:** the ingest/Greeks/IV-refresh/dedupe request is logged, not actioned — it needs execution access this session doesn't have, and it's outside today's analysis-only scope by your own instruction.

---

## 1. Missed winners — 403 rejected candidates later moved ≥50%, and it's not pure luck

Defined "winner" as best observed favorable move ≥50% via underlying MFE, underlying return-to-exit, or option return-on-premium — whichever is largest. Of 23,462 predictions, **411 crossed that bar; only 8 were ever actionable (GO/GO_LIMIT/PROBE/BUY).** 403 were missed — sitting under `MANUAL_REVIEW` (177), `MORNING_VALIDATION_REQUIRED` (144), or `BLOCKED` (81).

**Comparing the 403 missed winners against the ~20,300 missed non-winners, three features discriminate, none of them noise-level:**

| Feature | Missed winners | Missed non-winners | Read |
|---|---|---|---|
| Direction: BEAR share | 45.2% | 23.9% | **PUT-side rejects are disproportionately the big winners** |
| DTE, median | 21 days | 30 days | **Shorter-dated rejects win bigger, more often** |
| Pipeline's own `lab_rank`, mean | 444 (better) | 565 (worse) | The pipeline's ranking already partially "knows" — it just can't act |
| `market_breadth_state`: MID | 45.7% | 30.9% | Wins concentrate when breadth is middling, not extreme |

Quantified against the whole rejected population (rate of ≥50% mover), with 95% CI:

| Slice | Hit rate | 95% CI | n |
|---|---|---|---|
| All rejects | 1.9% | — | 22,183 |
| BEAR rejects | 3.3% | [2.8%, 3.8%] | 5,533 |
| BULL rejects | 1.3% | [1.2%, 1.5%] | 16,650 |
| DTE 11–20d rejects | **7.2%** | [6.2%, 8.2%] | 2,479 |
| DTE 21–30d rejects | 1.2% | [0.9%, 1.4%] | 10,567 |
| DTE 46+ rejects | 0.2% | [0.1%, 0.4%] | 3,692 |
| MID breadth rejects | 2.8% | [2.4%, 3.2%] | 6,538 |
| LOW breadth rejects | 1.1% | [0.9%, 1.3%] | 12,271 |

**Confidence: medium-high on direction and DTE** (large samples, non-overlapping CIs, and the same DTE/direction pattern showed up independently in the earlier shares-vs-options test as the leak concentrating on BULL). **Confidence: medium on breadth** (real gap, smaller sample). This is not luck in the sense of "scattered across everything" — it's concentrated in specific, nameable conditions, which is what makes it a candidate signal rather than noise. It is **not yet a validated rule**: this is a single-session (26-day), single-pass look, exactly the kind of result the unbuilt Gate Replacement spec (§3.5) warns must clear a held-out replication before being trusted, and I have not done that here.

## 2. Losing-trade diagnosis on the trades actually taken

Restricting to actionable trades (GO/GO_LIMIT/PROBE/BUY) that fully resolved (hit target or stop): **n=306, 38 winners / 268 losers (12.4% hit rate)** — roughly matching the certified ~9% headline once TIMEOUT/censored rows are added back in.

**What separates the 38 winners from the 268 losers:**

| Feature | Winners | Losers | Read (confidence) |
|---|---|---|---|
| Tier A | 42.9% | 21.7% | Tier A wins twice as often as its share of losers (medium — n=38 winners is thin) |
| Tier C | 25.7% | 50.8% | Tier C is where losers concentrate |
| `market_breadth_state` MID | 18.4% | 8.2% | Same MID-breadth pattern as §1, seen twice independently (medium-high) |
| target_atr, median | 2.00 | 2.67 | Winners run tighter target geometry (low — not base-rate-adjusted, could be spurious) |
| stop_atr, median | 0.80 | 0.92 | Winners run tighter stops too (low, same caveat) |
| DTE, priority_rank | ~equal | ~equal | **Not discriminating for trades already taken** — contrast with §1, where DTE mattered a lot for rejects. Different population, different lever. |

**Time-to-resolution — your day-5-vs-day-21 question, directly:**

| Sessions held | Stops | Targets | Target share |
|---|---|---|---|
| 1–5 | 246 | 30 | 10.9% |
| 6–10 | 11 | 8 | **42.1%** |
| 11–15 | 10 | 0 | 0.0% |
| 16–20 | 1 | 0 | 0.0% |

**Confidence: low-medium — the 6–10 day bucket (n=19) is genuinely striking but thin, and the 11–20 day buckets (n=11, zero winners) are too small to certify "never wins."** The honest read: almost everything resolves fast either way (median 2–3 sessions), and there's a real hint that a trade surviving past session 5 without stopping has a much better chance of eventually winning than one judged at day 1–5 — but a trade still open past day 10–15 in this sample never converted. That's the opposite of "give it the full 15-day window" — it points toward a **middle window (roughly session 6–10) as the most informative re-evaluation point**, not day 21. This deserves a much larger sample before acting on it; 19 and 11 are not numbers to build a hold-time rule on.

## 3. The direct answer on 70% win rate

**This needs to be said plainly, per your standing instruction on accuracy: nothing in this data, or in the certified `outcome_report.md`, supports 70% as a reachable win rate from thesis/direction quality alone. Confidence: high that this specific framing is the wrong target.**

Why: the certified base rate already showed the pipeline's directional thesis has ~0% edge over matched chance (target excess ≈0%, `AVS-PLAN-001` §1). Even the best-discriminating slice found today — DTE 11–20d rejects — tops out at 7.2%, and the actionable trades taken today convert at 12.4%. Getting any of these levers (tier, breadth, DTE, direction) to jointly move a ~9–12% single-trade hit rate to 70% would require a discriminator far stronger than anything found in five weeks of data, on any thesis-quality axis tested so far, in this or the prior sessions' work.

**What could plausibly get you toward a "70%-like" outcome, and what it actually means:**
- Not a 70% *hit rate* on direction. That's not supported by anything measured.
- A **70% win rate on the shares-equivalent expression at a filtered, high-tier/MID-breadth subset**, is a different and much more plausible claim — because §1 of `AVS-EXP-001` already showed shares winning ~21% baseline vs options' 11%, and this session's tier/breadth filters roughly double the hit rate again on their own (Tier A ≈ triple the loser-population's rate). Compounding a ~2x tier lift with the shares-vs-option ~2x lift, starting from a ~9-12% base, lands you in the 30-40% range on optimistic, uncorrected arithmetic — still well short of 70%, and this arithmetic is not a validated joint estimate; the filters haven't been tested together, on a holdout, or base-rate-adjusted.
- The only mechanism in any of the documents reviewed this session that could plausibly deliver something that *behaves* like 70% success from the trader's perspective is **HARC's right-tail framing**: stop trying to be right 70% of the time and instead size for the convex payoff so a ~20-30% hit rate with a fat right tail (the two ≥500% cases, the 403 missed ≥50% movers) produces a good overall outcome. That is a payoff-shape answer, not a win-rate answer, and it is explicitly unvalidated — HARC "has not yet been fit or tested against real data."

**If 70% single-trade win rate is a hard, non-negotiable gate for continuing this project, the honest recommendation is to say so now rather than let further experimentation imply it's close:** nothing found across three analysis passes (RCA-004, AVS-PLAN-001, AVS-EXP-001, this document) gets there, and the statistical shape of the problem (a rare, right-tailed, convex payoff — HARC §1) argues that a high win-rate target is close to the wrong success metric for this instrument, not merely an unmet one.

## 4. What would raise confidence on today's leads

None of §1–2's numbers should be treated as more than promising leads: same 26-session window used in every prior document this session, no holdout, no base-rate adjustment on the ATR/tier findings, small n on the time-to-resolution split. A trustworthy next step, still analysis-only:
1. Re-run §1's DTE/direction/breadth slices as an actual held-out replication once more sessions accrue (the Gate Replacement spec's own Phase 1 requirement).
2. Get the tier/breadth/DTE filters tested jointly, not one at a time, against the certified base-rate methodology (needs the real scorer, not my approximation — see AVS-EXP-001 §2's discarded attempt).
3. Pull the missing pieces of the 5-year picture in §5 below.

## 5. To use the full 5-year/2000-ticker universe

`historical_prices.sqlite` and `decision_outcome_ledger.sqlite` exceed this session's 400MB file-transfer limit. To bring them into a future pass, the fastest path is a targeted export you run locally (read-only, no pipeline touched) — e.g. a script that dumps only the columns/date range/ticker list actually needed for a specific question into a CSV or a smaller SQLite file under a few hundred MB, the same pattern already used for the C12 coverage extension. I can write that export script whenever you want to go there; I haven't, since today's brief was analysis on what's already staged.
