# AVSHUNTER end-to-end report — 19 September 2026

Prepared for ACK. Covers: every pipeline fix shipped today, the backtest scenario register and its round-1
results, an independent "solution tournament" found in the repository (unverified by this session — see §C), and
the honest, reconciled picture of where the pipeline stands. Branch `avs-fix-001`, nothing pushed. No production
authority has changed: `outcome.signal.min_cautious_return` gate stays retired in favour of rank-not-gate (fix 1,
already shipped before today); every change below is either a data/logic fix with a replay, or research recorded
in the scenario register with no pipeline effect.

---

## Executive summary

Today's work had two tracks. **Track 1 (fixes):** the evening pipeline was silently running on flat or defaulted
inputs — volume, sector, relative strength, volatility regime, physics, IV history — because of a merge bug and
several dead code paths. All are now fixed, test-first, each replayed against the 18 September run to show the
before/after. **Track 2 (backtest):** a scenario register was built to test, without touching the pipeline, why
recorded trades lose money and what would need to be true to fix it. Round 1 of that register, plus an
independently-run four-round "solution tournament" found in the repository, agree on the same root cause:
**options are priced above the movement that follows, execution friction is large, and no direction signal
tested — old features or new — shows a stable, market-adjusted edge.** Nothing here authorises a production
change. The next real test is the fixed pipeline's own live output (population N) and the weekend backfill
(population H+), both still pending.

---

## A. Pipeline fixes shipped today

Every fix follows the same discipline: a failing test stating the business rule, the minimal change, a replay on
the archived 18 September run (`20260918_112522`) to show before/after, then commit. Full detail is in each
commit message (`git log 22761ee..HEAD`).

| Commit | Fix | Root cause found | Replay result |
|---|---|---|---|
| `308c166` | Discovery/Vanguard field ownership | A plain merge suffixed 132 shared fields `_x`/`_y`; `volume_ratio` read its 1.0 default on all 1,499 rows, flattening volume confirmation and convexity score; the trigger layer read a name that didn't exist | Volume confirmation: 1 label → 10; convexity: 0/2 → 0/2/3; trigger GO-eligible 812 → 849 |
| `43356a8` | Discovery owns the thesis horizon; stand-down rows keep upstream facts | The Horizon Router overwrote `horizon_bucket` with the *contract's* expiry bucket (no hold-days input existed); 147 stand-down rows dropped 13 upstream facts | Router bucket kept as `contract_expiry_bucket`; horizon reverts to Discovery's (954×1-5d, 545×6-10d vs 1,036 wrongly at 11-20d); 147/147 facts restored |
| `157ab4d` | Thin-statistics review uniform across 1-20 sessions | The EOD engine's "probe candidate" class only fired at the 11-20d bucket | Now uniform; no candidate row reached the branch on 18 Sep, so no observed change yet |
| `5b0d826` | Planned hold = governed thesis window (not the router's expiry bucket) | Runway floor was set from the anticipated move, not the 20-session hold you can actually be in | Runway floor 19-26 days → 40 days on all rows; 53/1,352 contracts move to a longer expiry |
| `675b5e3` | Contract value selection (SHADOW); weekend-lookup fix | No mechanism compared contracts by expected value; separately, a lookup for a non-trading day would have failed every row on a weekend run | New `contract_value_*` fields recorded, mode=SHADOW (no authority); weekend bug fixed before any weekend run could hit it |
| `e54883d` | Thesis geometry review labels | 211/1,352 candidates had no stop/target (Wyckoff direction contradiction, or a PUT stop too far to reach a positive 3R target) and were silently unvaluable | Every row now carries `thesis_geometry_review_state`; two governed decisions surfaced for ACK (not yet made) |
| `f51babb` | Discovery structure detail reaches the Lab book | 35 Crabel/Wyckoff fields computed at Discovery never reached the book | 1,499/1,499 rows now carry them (display only) |
| `2c224e9` | Sector alignment, sector momentum, relative strength | Sector lists were iterated character-by-character (any letter "matched"); only 89 hard-coded tickers got a sector return | Alignment: 1,499 ALIGNED → 692/446/361 split; sector return coverage 69 → 1,499 rows; new `rs_vs_spy_20d_pct`/`rs_vs_sector_20d_pct` fields |
| `dc0e5af` | Physics runs on measured inputs | `avg_volume`, `beta`, `gap_pct`, `return_5d/10d` were neutral defaults on every row | 667/1,580 rows change physics state (34 → 62 distinct states); still-legitimate defaults (IV rank, spread) flagged, not invented |
| `2102fd8` | `physics_verdict` produced | EIL's no-current-edge veto has read `physics_verdict` since inception; nothing ever wrote it | 95 EARLY_PRESSURE_BUILDING, 190 MONETISABLE_PRESSURE now computed; EIL veto count unchanged (9→9) but now uses real evidence |
| `cdedf20` | IV history refreshed by every evening run; data readiness at preflight | `iv_surface_history`/IV cache stopped 4 Sep — only a manual weekly step derived them | Automatic derivation wired into the evening run after the Phantom delivery; preflight now reports FRESH/STALE per source |
| `61c16b9` | True IV percentile from real history | "IVP" was a realised-volatility-range measure mislabelled as an IV percentile; `iv_direction` was hard-coded STABLE (the loader read a file nothing writes) | One-year catch-up restored real IV history (median samples 10 → 60); true percentile now measurable on ~96% of candidates |
| `39f1ca8` | Live volatility regime matches the database's own rule | The live classifier averaged inputs that were always 50 (never forwarded), so every row matched only the database's "NORMAL" slice | 811/1,580 rows now match their real regime (COMPRESSION/EXPANSION/NORMAL); EIL veto impact neutral |

**Not touched this session (from the original deep dive, still open):** F4 (trigger timing is a synthetic bucket,
no real distance-to-breakout), F7 (options flow half-built — PCR marked unavailable although chain volume exists).

---

## B. Backtest scenario register — round 1

Full detail: `Enhancements/backtest/SCENARIO_REGISTER_20260919.md`. Nothing here touches the pipeline; every result
is either historical replay (population H, the pre-fix pipeline's recorded books) or point-in-time market data (U).

**Populations:** H (31 Aug-16 Sep books, pre-fix candidates, today's ticket rules) · H+ (H once the weekend
backfill re-scores 1,786 legacy recommendations) · U (five years of price-store history, no options needed) · N
(the fixed pipeline's own live runs, from now on).

**Baseline (ledger trial 9, "as is"):** tickets −19.5% mean (timed fill), 5/session, no zero-trade days; 83% of
candidates fail the 10% ticket spread limit before anything else is judged.

**IA-6 (transformation loss, H):** the spread costs ~21 points (top cautious fifth) to ~39 points (all candidates)
at one session. Direction tracked the market almost exactly (book was 64% CALL in a falling market: CALLs −1.64%,
PUTs +1.57% vs universe −1.42% over 5 sessions — both roughly at market beta). The ranking key selects **magnitude**
reliably (top vs bottom fifth: 4.86% vs 3.98% absolute move at 5 sessions) but not direction (rank IC ~0.02-0.04).

**IA-1/IA-2 (U, exploration period 2021-2024 only, 2025-2026 holdout sealed):** no market-adjusted directional
information in any bar feature tested (all |t| < 2). Strong, persistent magnitude information from compression
(t 16-24, builds over weeks) and volume ratio (t 22 at 1 day, decaying to t 9 at 20 days).

**IA-3 (H and the weekly-chain year, 94 Fridays, 337k observations, both halves consistent):** the whole options
universe delivers only 0.61-0.65 of the variance implied by IV — a ~35-40% average overpayment. Cheapest-IV-vs-
realised-vol names price near fair (0.84-1.03); richest price at ~0.3. **The most compressed names carry the
worst mispricing (0.51-0.58)** — compression is a well-followed heuristic and the market has already priced it,
past fair.

**Exits (H, top cautious fifth):** removing the underlying stop inside the hold: +2.9 points, t=3.25, best right
tail (hit rate 22%→36%, ≥100% share 5.8%→8.2%) — replicates the 17 Sep finding exactly. A fair-value exit (sell
when expected value of holding drops below the bid): +4.9 points, t=3.86, but gives up tail. **S-EXIT-8** (fair
value + a floor that suspends selling once already at +100%) barely differs from plain fair value — the floor
triggers too late to matter.

**Costs (small samples, 22-25 tickets/trial):** nearer-the-money (OTM limit 2.5%) tickets −13.2% vs −19.5%
baseline — directionally consistent with the register's cost family, not yet statistically established.

**FX forensics (67 winners ≥+100%, 13 ≥+200% of 2,992 closed):** winners bought cheaper volatility (IV/realised
ratio, IV rank) in tighter, more liquid markets. The ≥+200% tail came from near-the-money, 9-20 DTE contracts on
fast moves (1-11 sessions). Wyckoff structure did **not** predict direction in this sample (10/12 extreme PUT
winners sat in ACCUMULATION).

**Registered, not yet run:** S-IV-3 (expression-rank tilt by volatility cheapness), EXPR-BAR-2 (core + convex
satellite), EXPR-CHOOSE-2 (shares when options are rich, options when cheap — no short shares, per your permitted-
expression ruling), the IV-LAG family (IA-3b onset-vs-level, IA-3c dated-vs-undated catalyst, IA-3d before-vs-
after options flow) — all fixed exactly as written before any run, staged by data population (coarse/unbiased now,
fine/biased once the targeted backfill lands, fine/unbiased once N accumulates).

---

## C. Solution tournament — found in the repository, not produced by this session's tracked process

`Enhancements/backtest/solution_tournament/` contains four rounds of research (manifest timestamped 19 Sep,
branched from commit `f808cb4`, never committed to git) that I did not run and have not deep-reviewed line by
line. **Flagging this explicitly: I cannot vouch for its process the way I can for the register above** — I don't
know who ran it or whether every pre-registration was genuinely fixed before results were read. What I can say:
its manifest states `research_state: EXPLORATORY_NO_AUTHORITY`, `production_changed: false`, and it carries its
own test suite (14 passing). Its structure — frozen gates, a sealed 2026 holdout, no production authority claimed
— matches the discipline this session has followed, and its conclusions are consistent with, and materially extend,
round 1 above. Treat the summary below as a second, corroborating research thread requiring your own confirmation
of provenance before being weighted equally with the register's own tracked results.

**Round 1 (failure localisation, 8,950 rows/9 sessions/1,556 tickers):** confirms IA-6's execution-cost finding
almost exactly (36-37 points of ask-to-bid vs mid-to-mid drag at every horizon tested).

**Round 2 (full contract-family alternatives):** the real addition. For every ticker/direction, it re-selected
from the *entire* recorded chain rather than just the chosen contract. Tightest-executable-spread, near-money,
delta 0.35-0.55, and a price/value composite all beat the recorded contract in 68-76% of paired trades (+8 to +16
points). **Even the best alternative remains net negative after costs** — a cleaner selector helps but does not
by itself make the book profitable.

**Round 3 (sealed direction holdout, frozen before 2026, 2025 calibration-only, 2026 sealed):** no direction model
passed a pre-registered consistency bar across 1/3/5 sessions. Gradient boosting showed +0.76% at 5 sessions but
near-random AUC at 1/3 sessions; a regime-confounding check found signs flipping between the recorded-book sample
and the wider universe. This is the most rigorous direction test run against this pipeline's data — and it still
says no.

**Round 4 (integrated stress tournament, 311,822 scenario rows):** joined direction + contract family + dynamic
expression (option/shares/no-trade) + liquidity maturation, then stress-tested spread widening, quote dropout,
regime shifts, and removal of the best 1%. Best route found (5-day mean-reversion direction + dynamic expression):
**still negative** (−1.0% to −2.4% depending on horizon) but materially better than the recorded book, and
regime-sensitive. Core and convex contract lanes were confirmed to catch *different* extreme winners —
independent evidence for the core+satellite structure already registered as EXPR-BAR-2.

**Its root-cause list (RC1-RC7)** matches this report's §A/§B almost line for line: insufficient certified run
evidence (RC1), magnitude mistaken for direction (RC2), options rich vs delivered movement (RC3), execution
friction (RC4), mean-optimisation vs tail-capture tension (RC5), the short-horizon convex hypothesis untestable in
H because every recorded hold is 12-20 sessions (RC6 — a genuine new finding, worth registering), and no direction
replacement robust out of sample (RC7).

**Its explicit build decision:** do not change production selection or authority. Execute two further batches
(thesis-conditioned entry/path stress; full contract-family tail forensics) before any promotion.

---

## D. Where the two threads agree, and what that means

Both threads, run independently on overlapping but not identical data, reach the same three conclusions. That
convergence is the strongest evidence in this report:

1. **No direction signal tested — old or new, bar-feature or model-based — shows a stable, market-adjusted edge.**
   Round 1's bar-feature test (this session) and the tournament's sealed-2026 model test (independent) agree.
2. **Options are priced above what subsequently happens**, and the richest/most crowded setups (compression
   included) are priced worst, not best.
3. **Execution friction is the largest single controllable loss**, and cleaner contract selection materially
   improves outcomes without making them profitable on its own.

Where they add to each other rather than just agree: the tournament's Round 2 (full-family paired contract
comparison) and Round 4 (stress tournament, regime shocks) are more thorough than anything in the register so far
— worth adopting their method, not just their numbers. The register's IA-3/IV-LAG family is more precise about
*why* the mispricing happens (mechanically, from how IV actually gets set) and gives a testable mechanism
(onset-vs-level, catalyst timing, flow timing) the tournament doesn't attempt. RC6 (the convex satellite is
untestable in H because every recorded hold is 12-20 sessions) is a genuine gap the register hadn't surfaced —
recommend adding it as a data requirement against N.

---

## E. Data infrastructure — current state

- **IV history:** one year restored via weekly-Friday catch-up (median 60 samples/candidate, 96% above the F2
  20-sample floor). 53 remaining gap tickers: a targeted script is built and ready to run today (~13-14k credits).
- **Backfill staging** (`Enhancements/research/legacy_signals/`): Stage 2 (gap tickers, ready now) → Stage 3 (the
  1,671-ticker research-relevant core, daily, ~350k credits over ~4 weekend runs) → Stage 4 (the remaining ~1,647
  long-tail tickers, deferred, no measured value yet). The original 760-ticker targeted backfill (21 May-2 Aug
  windows) remains separately useful for H+ re-scoring.
- **Preflight readiness check:** every run now reports price store / Phantom chains / IV surface / IV cache as
  FRESH / BEHIND_ONE_SESSION / STALE / MISSING against the last completed session. Report-only, never blocks.

---

## F. Honest current picture

- **No production authority has changed.** Rank-not-gate (fix 1) and the retired cautious-value gate predate
  today. Value selection is SHADOW. Nothing in the scenario register or the solution tournament has been promoted.
- **No monetisable edge has been demonstrated** by either research thread. Every route tested, including the
  tournament's best integrated route, remains net negative after realistic costs.
- **What *has* been demonstrated:** the pipeline's upstream data was badly degraded (flat/defaulted on most of
  the features that matter) and is now materially repaired; the size of the execution-friction problem is now
  precisely measured; the shape of a plausible path to monetisation (cheap-volatility timing + cleaner contract
  selection + core/convex dual-lane expression + no-stop management) is now specific enough to test, not just
  argue about.
- **Everything forward depends on N** (the fixed pipeline's live output) **and H+** (the weekend backfill). Round
  1's biggest limitation — a 9-session, one-regime historical sample — is a data-availability problem, not a
  methodology problem, and it doesn't resolve until those two populations exist.

---

## G. Recommended next steps, in order

1. Run Stage 2 backfill (gap tickers) today — cheap, closes the live IV-accuracy gap completely.
2. Run Stage 3 backfill (core universe) over the coming weekends — enables the fine-resolution IV-LAG tests and
   thickens H+.
3. Reconcile RC6 into the register: the short-horizon convex satellite needs a real 1-5 session thesis population,
   which doesn't exist in H — flag as a data requirement for N, not a design failure.
4. Once you've reviewed the solution tournament's provenance, decide whether to fold its Round 2/4 methods
   (full-family paired contract comparison; the stress-shock harness) into the register as adopted tools.
5. Run your evening pipeline on the fixed code when ready — this is what starts populating N, the population every
   open question ultimately depends on.

Nothing above requires or requests a pipeline run from this session — per standing instruction, that stays yours
to start.
