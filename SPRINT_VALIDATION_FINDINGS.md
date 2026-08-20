# Sprint Validation Findings — Part A

Task: `CLAUDE_CODE_TASK_validation_and_direction.md`, Part A. Validates two
headline results from `ACTUARIAL_DISTRIBUTION_SPRINT_REPORT.md`. Read-only —
no source files were modified. Reconstruction scripts and full per-row output
live in the session scratchpad, not the repo (same convention as
`EV_ENGINE_VERIFICATION.md`'s `ev_verify.py`).

**Headline: A3 invalidates a material part of A2's finding, as the task
doc's own stop-condition anticipated.** Reported per the rules below,
Part B not started.

---

## Methodology and two defects found along the way

`execution_v3_5_<run>.csv` (1262 rows run 1, 1379 run 2 — matches the sprint's
counts) is the correct source for `ev_conf_adj`/`ev2_ev_status`/contract
fields; `ev_conf_adj` and `ev2_ev_conf_adj` are byte-identical. `ActuarialQueryEngine`
was run once, live, against the current `actuarial_database_v6.parquet`
(6,033,072 rows) — same retroactive-backfill caveat the sprint itself
disclosed (DB may have drifted since the original runs).

**Defect 1 — `emp_quality_flag` is unreliable on its own.** `compute_empirical_option_ev`'s
market-quote gate is `if bid is None or bid <= 0 ...`. Values pulled from a
pandas row are `np.nan` on missing data, not `None`, and `np.nan <= 0` is
`False` in Python — so the gate silently fails to catch missing quotes. The
row falls through, every per-percentile `r_i` comes out `NaN`, `emp_expected_r`
is `NaN`, but `p_double = sum(w for w, r in ... if r >= 1.0)` treats
`NaN >= 1.0` as `False` too, so it silently collapses to a **fabricated 0.0**
instead of a null — the exact failure mode the module's own docstring says it
must never produce ("a confidently wrong number is worse than no number").
576/925 (62%) and 600/969 (62%) of nominal `OK` rows in the two runs are this
bug, not genuine computations. Confidence 95% this is real and reproducible.
Not fixed (Part A is read-only); flagged because it means **`emp_quality_flag=='OK'`
alone is not a valid usability filter** — I used `OK` AND `emp_expected_r`
non-null throughout. True usable counts: **349/1262 (27.7%)** run 1,
**369/1379 (26.8%)** run 2 (lower than the sprint's reported 35.2%/37.9% —
see A3 for the reconciling mechanism).

**Defect 2 (context, not fatal) — `layer2__vol_regime` = `NORMAL` and
`layer2__trend_direction` = `SIDEWAYS` for literally every row in both runs**
(confirmed independently, not just by the sub-agent that did this
reconstruction — I re-ran the value_counts myself against both CSVs). Not
plausible as real per-ticker state across ~1300 distinct names two weeks
apart; looks like an upstream defaulting bug in whichever stage computes
these two of the ten match dimensions. Reduces match discrimination (2 of 10
EXACT dims carry zero information) but doesn't invalidate matching outright.
Also: `layer2__recommended_hold_days` ≈ 20 regardless of horizon, which
biases option-value pricing *down* (less remaining time value assumed for
5D/10D exits) — works against, not for, the sprint's headline, so it doesn't
change any verdict below.

---

## A1 — Zero rank overlap: **verdict: partially artefact, partially real. Confidence 85%.**

| | Run 1 | Run 2 |
|---|---|---|
| Top 20 by `ev_conf_adj` with non-null `emp_expected_r` | 1/20 | 5/20 |
| Overlap on the fair (both-non-null) subset | 2/20 | 1/20 |
| Spearman ρ, common subset | **-0.305** (p=6.2e-9, n=349) | **-0.162** (p=0.0019, n=369) |
| `emp_quality_flag` breakdown, `ev_conf_adj` top-20 | OK:10 (9 NaN-bug, 1 genuine), BAD_INPUT:7, NO_MARKET:3 | OK:12 (7 bug, 5 genuine), BAD_INPUT:5, NO_MARKET:3 |

The literal "0/20" is largely arithmetic, exactly as the task's alternative
explanation predicted — only 1-5 of the top-20-by-`ev_conf_adj` names even
have a comparable value. **But** restricting to the fair subset and re-ranking
within it still gives ~0/20 overlap, and the Spearman correlation is
**negative and significant in both independent runs**. That's a stronger,
more specific, and more defensible claim than the sprint's "the two disagree
completely": on a coverage-controlled comparison, high `ev_conf_adj` is
mildly but reliably associated with *lower* `emp_expected_r`. Neither
measure is shown to be "right" — per the standing limitation, only realised
outcomes settle that — but the disagreement itself survives scrutiny better
than the sprint's own headline number does.

---

## A2 — 4.4–4.5% `emp_p_double > 0.15`: **verdict: confirmed bin-boundary artefact. Confidence 90%.**

Distinct `emp_p_double` values observed, both runs, zero exceptions:
`{0.0, 0.03, 0.075, 0.15, 0.25, 0.35}`. This is a direct, verified consequence
of `PERCENTILE_WEIGHTS` (derived from the 13 **unevenly spaced** percentile
levels `0.01,0.05,0.10,0.20,...,0.90,0.95,0.99`, not from point count):
weights are `[0.03, 0.045, 0.075, 0.10×7, 0.075, 0.045, 0.03]`, so any
monotonic payoff (guaranteed here — BS price is monotonic in spot for a
fixed call/put) can only produce a cumulative sum from the fixed set
`{0, 0.03, 0.075, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.925,
0.97, 1.0}`. This is **not** the "multiples of 1/13" pattern the sprint
report speculated (0.077, 0.154, 0.231...) — it's a different, uneven set,
and critically, **0.15 sits exactly, exactly on one of these achievable
values** (the report's own p75=p90=0.150 was the tell).

| Threshold | Run 1 (n=349) | Run 2 (n=369) |
|---|---|---|
| >0.05 | 145 (41.6%) | 112 (30.4%) |
| >0.10 | 64 (18.3%) | 62 (16.8%) |
| **>0.15** | **12 (3.44%)** | **12 (3.25%)** |
| >0.20 | 12 (3.44%) | 12 (3.25%) |
| >0.25 | 1 (0.29%) | 2 (0.54%) |

~15% of the entire usable sample sits *exactly* on 0.15 in both runs.
Because nothing exists between 0.075–0.15 or 0.15–0.25, the count swings
64→12 (5x) moving from `>0.10` to `>0.15` purely from reclassifying
boundary-sitters, and is frozen 0.15→0.20 with zero rows in between. This is
precisely the artefact the task doc's "p75/p90 tell" predicted. **The
finding "reproduces at 4.4–4.5% across two runs" is not independent
confirmation of a real signal** — the boundary sits in the same mechanical
place every time by construction; it would reproduce whether or not anything
economically real underlies it.

---

## A3 — SJM, HRL, TRV: **HRL is a confirmed direction-mishandling artefact, not a real result. Confidence 85%. This invalidates a material part of A2.**

| Ticker | Run 1 `options_direction` | Run 1 result | Run 2 `options_direction` | Run 2 result |
|---|---|---|---|---|
| HRL | **STRANGLE** | BAD_INPUT (correctly null) | **STRANGLE** | BAD_INPUT (correctly null) |
| SJM | **STRANGLE** | BAD_INPUT (correctly null) | CALL | `emp_p_double=0.25` |
| TRV | PUT | `emp_p_double=0.25` | CALL | `emp_p_double=0.15` |

(`options_direction` values re-confirmed directly by me against both raw
CSVs, independent of the sub-agent's reconstruction.)

`compute_empirical_option_ev` has no strangle payoff model; a
`STRANGLE`-labeled row correctly nulls out under a faithful reading of its
direction contract. Yet the sprint's report lists SJM and HRL as qualifying
at 0.55–0.85. Testing the direction gate's own fallback behaviour
(`g("direction", default="CALL")` — i.e., what happens if a caller never
populates `direction` for a STRANGLE row) reproduces the sprint's numbers
closely: forcing STRANGLE→CALL gives **HRL run 1 = 0.55, exactly the bottom
of the sprint's cited range**; usable-row counts rise to 450/1262 (35.7%)
and 526/1379 (38.1%) — within single digits of the sprint's reported
35.2%/37.9%; and the >0.15 hit rate becomes 26/450 (5.8%) / 26/526 (4.9%),
much closer to the reported 4.5%/4.4% than the faithful reconstruction's
3.4%/3.3%. **Of those 26 qualifying rows per run, 14 (54%) are STRANGLE
positions priced as a naked CALL** — one leg of a non-directional,
two-sided position, treated as the entire directional trade.

This is convergent evidence (matching denominators, matching hit-rate order
of magnitude, an exact match on HRL's specific value) that the sprint's
original computation did not exclude STRANGLE rows the way a correct
reading of the module's own contract requires. This is not a coincidental
discretisation effect like A2's boundary issue — it's an invalid application
of a directional payoff formula to a position type the formula doesn't
model. It is also very plausibly the same direction-collapse pattern Part B
exists to investigate (bare `direction` never resolving to a
non-directional value even when the real position is one), now shown to
reach the empirical module as well.

**Per-ticker verdicts:**
- **HRL — not plausible, not real (confidence 85%).** Under the module's own
  direction contract, HRL produces no number in either run. Its appearance
  in the sprint's qualifying list is an artefact of pricing a strangle as a
  naked call. Defect location: **direction resolution / payoff mapping**,
  not the return distribution or percentile weighting.
- **SJM — mixed (confidence 70%).** Run 1 is the same STRANGLE→CALL
  artefact as HRL. Run 2 is genuinely labeled CALL and produces a real 0.25
  under the module's own logic — plausible in magnitude for its ANALOGUE-tier
  match (n=80,307), though whether `CALL` is itself the economically correct
  label for the contract actually selected that day is Part B's question,
  not this one's.
- **TRV — arithmetically consistent, but low confidence it's meaningful
  (confidence ~35%).** Not a STRANGLE artefact — computes under its own
  labeled direction both runs. Hand-walked the chain for run 1 (spot
  $375.99, strike $370 PUT, 21 DTE, ask $5.50): a -5.84% 20-day move (the
  distribution's p20 point) already produces ~$15.94 intrinsic value, a
  >2x return, and the cumulative weight of p01+p05+p10+p20 is exactly
  0.25 — matches the reported number exactly, and a ~6% 20-day down-move for
  an insurer isn't an implausible tail event, so the return-to-price
  transform and percentile weighting both check out. What undermines
  confidence is match quality: TRV matched at RELAXED (run 1, n=306,142) /
  ANALOGUE (run 2, n=39,038) tier, using only 4 (or fewer, weighted) of 10
  dimensions — two of which are the frozen `NORMAL`/`SIDEWAYS` constants
  identical for the entire book. TRV's "matched distribution" is closer to a
  generic large-cap 20-day statistic for that day's macro regime than
  anything TRV-specific. The row's own diagnostics already flag this as
  disputed — `direction_arbitration_reason = "Wyckoff SELL_SETUP vs
  actuarial CALL probability"`, status `MITIGATED_REQUIRES_CONFIRMATION` —
  i.e. even which side of the trade this is remains contested at the row
  level. If something is wrong here, it's **match-quality/dimension
  collapse upstream of the percentiles**, not the percentile-to-payoff
  mapping itself.

**Net effect on A2 (per the task's own stop-condition):** more than half of
A2's qualifying population in a faithful reconstruction is STRANGLE-mispriced,
and HRL — one of the two names emphasized as reproducing "in both runs
independently" — never legitimately qualifies under the module's own rules
in either run. **A3 does invalidate a material part of A2's headline
result.** The 4.4–4.5% figure should now be read as: a mechanical
bin-boundary artefact (A2), compounded by a direction-handling defect that
inflates the qualifying population with payoffs computed for a position type
that was never actually held (A3) — reproducing consistently across two
independent weeks not because a real, decision-useful tail signal exists,
but because both mechanisms are deterministic and fire the same way every
time.

---

## What I could not determine

- The sprint's exact original per-row numbers — its generating script isn't
  in the repo (grep-confirmed no file anywhere contains `emp_p_double` or
  `emp_expected_r`), and the DB has drifted since the original runs (the
  sprint's own disclosed limitation). Reconstruction reproduces the
  qualitative pattern and denominators within single digits, not exact hit
  counts (26 vs. 20/23) — plausibly a slightly different STRANGLE-defaulting
  mechanism in the original script, not confirmable without it.
- Whether `emp_expected_r`/`emp_p_double` predict realised outcomes better
  or worse than `ev_conf_adj` for the rows that *do* legitimately qualify —
  unanswerable from static files by design (standing limitation, unaffected
  by anything above).
- The exact upstream stage producing the frozen `vol_regime`/`trend_direction`
  constants — traced far enough to be confident it isn't real per-ticker
  data, not chased further (out of scope for Part A).

## Confidence summary

| | Verdict | Confidence |
|---|---|---|
| A1 | Partially artefact (literal 0/20), partially real (significant negative Spearman on fair subset) | 85% |
| A2 | Confirmed bin-boundary artefact | 90% |
| A3 (HRL) | Confirmed direction-mishandling artefact, not real | 85% |
| A3 (SJM) | Mixed — run 1 same artefact as HRL, run 2 plausible | 70% |
| A3 (TRV) | Arithmetically consistent; low confidence it reflects TRV-specific risk | 35% |

**Report. Stop. Part B not started**, per the task's explicit
stop-condition — A3 shows the payoff mapping is wrong for the STRANGLE-labeled
low-vol names, which invalidates part of A2's headline result and changes
what Part B's direction-conflict investigation is for (it's now clear the
same `direction` ambiguity Part B investigates for `ev_engine_v2.py` also
reaches `empirical_option_ev.py`, strengthening B1.3's premise before B1 has
even been read in detail).
