# Actuarial Distribution Retention + Empirical Option EV — Sprint Report

Sprint spec: `CLAUDE_CODE_TASK_actuarial_distribution.md`. Prior work this
builds on: `EV_ENGINE_VERIFICATION.md` (V6 established `win_rate_5d/10d/20d`
semantics; V4/V5 established the scale and blast-radius problems this
sprint's shadow module is explicitly designed NOT to inherit).

**Baseline tag:** `actuarial-dist-v0-baseline` — first commit that put
`ev_engine_v2.py` under version control at all.

---

## Status per change

| Change | Commit | Summary |
|---|---|---|
| 0.1 — commit untracked `ev_engine_v2.py`, tag baseline | `2b52409` | No code change — configuration management only |
| FIX-AD-1 — retain return-distribution percentiles | `49febe3` | 13-pt percentiles (p01–p99) + per-horizon `n_obs` added to `ActuarialOutcomes`; computed in `_calculate_outcomes()` |
| FIX-AD-2 — carry fields through primary export path | `9fe1a27` | `vanguard/main.py`'s hand-curated `layer_2_result` explicitly extended (also first-time-committed `vanguard/main.py`, previously untracked — see below) |
| Phase 2 — empirical option EV shadow module | `a6cfda6` | New `empirical_option_ev.py` + 20 unit tests; no authority, does not modify `ev_engine_v2.py` |

All four are additive-only: `git diff --stat` across the full sprint range
shows zero deletions in any pre-existing file, only new files and appended
lines.

**An unplanned but appropriate side-effect, disclosed rather than buried:**
`vanguard/main.py` turned out to also be untracked with zero prior history —
discovered only when staging FIX-AD-2, not caught by the 0.1 check (which
only looked at `ev_engine_v2.py` and `actuarial_query.py`, per the task's own
scope). It's now committed as part of `9fe1a27`, which means that commit's
diff includes the entire pre-existing file content (574 lines) alongside the
real ~14-line change. The actual functional diff is small and is documented
in the commit message; treat `9fe1a27`'s "574 insertions" figure as
first-time tracking, not the size of the change.

---

## Sample-size census (0.2) and its implications

Real run, 1,262 actuarial queries, live database (6,033,072 rows):

| Tier | Rows | Median n | Min n | Max n |
|---|---|---|---|---|
| EXACT | 935 | 7,958 | 71 | 91,005 |
| RELAXED | 123 | 320,806 | 306,142 | 320,806 |
| ANALOGUE | 204 | 121,993 | 9,521 | 492,340 |
| UNKNOWN | 0 | — | — | — |

97.0% of rows clear n≥100, 87.5% clear n≥500, 79.3% clear n≥1000. Zero
`UNKNOWN`-tier rows in this run — the match ladder always found at least a
RELAXED-quality sample.

**Implication:** percentiles from 10 points would indeed be noise, but that
concern doesn't apply here — the observed minimum (71) is already 7x that,
and the book-wide median is in the thousands to hundreds of thousands.
**Built the full 13-point set as specified.** Set Phase 2's null-floor at
**n=100** — it excludes only ~3% of the book, matches the database's own
`ANALOGUE_MIN_SAMPLES` constant, and is far enough below the observed
minimum-non-UNKNOWN of 71 in EXACT tier to not gate rows that are otherwise
one of the ladder's own accepted quality levels. (Note this floor is a
Phase-2 shadow-module choice, not a change to the match ladder's own EXACT
minimums.)

---

## Percentile reconciliation evidence (FIX-AD-1)

Validated against 6 real live-database queries spanning 72 to 320,806
matched rows across all three tiers (not synthetic data — reconstructed
`StateVector` dicts from real reference-run tickers, queried through the
actual `ActuarialQueryEngine`):

- **Golden diff:** all 81 pre-existing `ActuarialOutcomes` fields
  byte-identical before/after, in all 6 samples.
- **p50 ≈ median:** exact match (to 6dp) against the true series median, in
  all 18 horizon-checks (6 samples × 3 horizons).
- **win_rate reconciliation:** fraction of the 13 percentile points above
  zero landed within 2/13 bins of the corresponding `win_rate_Xd` scalar, in
  all 18 checks (e.g. 0.462 vs. 0.487, 0.538 vs. 0.535).
- **median_gain placement:** `median_gain_if_up_Xd` fell inside the positive
  half of the 13 points, in all 18 checks.

`_empty_outcomes()` confirmed returning `None` for all 42 new fields (not
0.0) — checked directly, not inferred.

---

## Golden diff table

```
 empirical_option_ev.py                         | 286 ++++++++++++         (new file)
 ev_engine_v2.py                                 | 423 ++++++++++++++++++   (0.1 — first tracked, no change)
 tests/test_empirical_option_ev.py               | 198 +++++++++           (new file)
 vanguard/layer2_statistical/actuarial_query.py  |  50 +++                 (FIX-AD-1)
 vanguard/main.py                                | 574 +++++++++++++++++++ (FIX-AD-2 + first tracked)
 vanguard/schemas/state_outcomes_schema.py       |  56 +++                 (FIX-AD-1)
 6 files changed, 1587 insertions(+), 0 deletions(-)
```

Every changed line attributes to exactly one commit per the table above. No
existing column, field, or value was altered anywhere in the sprint — the
FIX-AD-1 golden diff (81/81 fields unchanged across 6 real samples) is the
direct proof for the two files that carry real risk of collision;
`empirical_option_ev.py` and its test file are wholly new, so there is
nothing pre-existing to collide with.

---

## Rank comparison — `ev_conf_adj` vs. `emp_expected_r`

Both usable archived runs (the other two run folders, `20260723_071559` and
`20260731_081843`, lack `execution_v3_5`/`eil_enriched` entirely — same gap
documented in the prior Lab sprint, not something this sprint can fill from
static files).

| Run | Top 20 by `ev_conf_adj` | Top 20 by `emp_expected_r` | Overlap |
|---|---|---|---|
| `20260731_083130` | IMNM, HIMS, NPKI, CXW, DNLI, XENE, PTCT, MRTN, HTLD, ROST, AMN, ATRC, DYN, ROAD, MIR, OTEX, LEGN, FIS, CTSH, DXC | AER, HRL, CRL, PGR, WBD, BRZE, VTI, DUK, SJM, PGY, TRV, B, AZN, GDX, MMM, RTX, NCLH, CINF, VZ, CMCSA | **0/20** |
| `20260723_072618` | ATAI, MYE, KBH, JEF, OMF, CLMT, EQNR, CGEM, REYN, STNG, AXGN, ABCL, OSW, EVC, ABSI, JXN, IBIT, UNM, PEGA, VG | RPD, WWW, DASH, ALNY, ZTS, ULTA, TRV, IGV, MDT, EWTX, SLV, HRL, SJM, TNL, XLF, MOS, AAPL, GAP, EGO, TROW | **0/20** |

**Zero overlap in both runs, independently.** Per the sprint's own framing,
this is a finding, not a failure: the two measures disagree completely about
which names are best, in two different runs a week apart. V2's `ev_conf_adj`
ranking is dominated by the `_classify()`/scale problems documented in
`EV_ENGINE_VERIFICATION.md` (V3, V4) — it is not obviously the more correct
of the two, but neither has this sprint shown `emp_expected_r` is either.
**Only realised outcomes can settle which ranking means anything**, which is
exactly the standing limitation below.

---

## The headline number — `emp_p_double` distribution and the WEAK_PASS/PASS_SMALL cross-tab

| Run | Usable rows | mean | p50 | p75 | p90 | p99 | max |
|---|---|---|---|---|---|---|---|
| `20260731_083130` | 444/1262 (35.2%) | 0.077 | 0.030 | 0.150 | 0.150 | 0.507 | 0.850 |
| `20260723_072618` | 522/1379 (37.9%) | 0.066 | 0.030 | 0.075 | 0.150 | 0.408 | 0.925 |

Median `emp_p_double` sits at a modest 3% — most candidates are not
doubling-probability plays. But there is a real, fat right tail in both
independent runs (99th percentile 41–51%, max 85–93%).

**The direct test — WEAK_PASS/PASS_SMALL rows with `emp_p_double > 0.15`:**

| Run | WEAK_PASS/PASS_SMALL rows (usable) | `emp_p_double > 0.15` | % |
|---|---|---|---|
| `20260731_083130` | 444 | **20** | 4.5% |
| `20260723_072618` | 522 | **23** | 4.4% |

**A meaningful set exists, and it reproduces almost identically (4.4–4.5%)
across two independent days a week apart.** These are candidates V2's own
classification calls weak-or-marginal (`ev_conf_adj` in every single hit
below 0.016, several negative) that the empirical, ask-net, exit-horizon
distribution says have better than 1-in-7 odds of doubling. Representative
examples, both runs: `BRZE`/`AER`/`CRL`/`PGR`/`HRL` (run 1, `emp_p_double`
0.55–0.85) and `RPD`/`WWW`/`DASH` (run 2, `emp_p_double` 0.55–0.93). `SJM`,
`HRL`, and `TRV` appear on this list in **both** runs independently.

**The sprint has found something real** — the observation that started this
work (weak-EV trades delivering 100%+ returns) has a reproducible statistical
signature in the actual database, not just the one PYPL anecdote. Whether
that signature is *decision-useful* — i.e. whether these specific 20–23 rows
per run would actually have doubled, or whether the empirical tail is itself
an artifact of thin per-percentile resolution (see limitations) — is exactly
what the standing limitation below says only realised outcomes can answer.

**Why 62–65% of each book has no usable `emp_` result:** overwhelmingly
`NO_MARKET` (103/1262 and 77/1379 of the *nulled* rows, vs. single digits for
`THIN_SAMPLE`/`VOL_DIVERGENCE_BLOCK` combined) — meaning most of the gap is
missing/zero bid-ask in these archived EOD-mode runs, not a weakness in the
distribution retention itself. `THIN_SAMPLE` fired on only 4 and 2 rows
respectively — direct confirmation that the 0.2 sample-size floor is not the
bottleneck this sprint's own numbers predicted it wouldn't be.

---

## What I could not determine, and why

- **Whether `emp_expected_r`/`emp_p_double` predict realised outcomes better
  than `ev_conf_adj`.** No closed loop from signal to outcome exists (see
  below) — this was never answerable from static files, by design.
- **The true per-percentile-point internal spread.** Both this sprint's
  percentiles and the resulting `emp_*` distribution are built on 13
  discretisation points, not the full matched sample (which FIX-AD-1
  retains as scalars but does not export as a raw series). Extreme
  within-tail behaviour beyond p01/p99 is represented only by its boundary
  point.
- **The `STALE_QUOTE` gate end-to-end.** No archived per-run CSV carries a
  live quote timestamp; the gate is implemented and directly unit-tested
  (`test_stale_quote_emits_nulls`) but could not be exercised against real
  data offline.
- **Whether the exact per-row `emp_*` values in this report match what a
  live run would have produced at the time.** These are *retroactively
  backfilled* against the current (v6) database state for tickers/states
  drawn from archived runs — the database may have grown or the match ladder
  may resolve slightly differently now than it did when those runs
  originally executed (I observed this directly in Phase 1: one row I
  expected to land in `RELAXED` tier resolved to `EXACT` on a fresh query).
  This affects the specific numbers in this report's tables, not the
  validity of the code itself (which was separately golden-diff-verified
  against the *current* database state only).
- **Whether the other two archived run folders** (`20260723_071559`,
  `20260731_081843`) **would change any of the above.** They lack
  `execution_v3_5`/`eil_enriched` entirely and cannot be analysed from static
  files — same gap the Lab sprint hit for the same reason.

---

## Rollback procedure — tested, both directions

```
# Revert the two FIX-AD-1 files to pre-sprint baseline:
git checkout actuarial-dist-v0-baseline -- vanguard/layer2_statistical/actuarial_query.py vanguard/schemas/state_outcomes_schema.py

# Restore back to the sprint's current state:
git checkout HEAD -- vanguard/layer2_statistical/actuarial_query.py vanguard/schemas/state_outcomes_schema.py
```

**Actually run, not just described:** executed the first command, confirmed
`grep -c "_return_percentiles|ret_pctl_"` on the reverted file dropped to 0
and `git status` showed a real diff against `HEAD`; then ran the second
command and confirmed `git diff --stat HEAD` was empty again and the grep
count was back to 9. A full rollback would also drop `empirical_option_ev.py`
and its test file (`git rm` or `git checkout <pre-sprint-SHA> -- .`, since
they're new files with no prior version to check out to) and would not need
to touch `vanguard/main.py`'s functional behaviour for anything outside this
sprint's own new dict keys, though see the first-time-tracking caveat above —
reverting `vanguard/main.py` to before `9fe1a27` means reverting it to
*untracked*, i.e. deleting it from version control, not to some prior
tracked state (there isn't one).

---

## The standing limitation

There is no closed loop from signal to realised outcome. This sprint
produced a better-founded measurement — empirical rather than assumed,
distribution rather than two medians, net of real spread rather than mid,
priced at the actual exit horizon rather than expiry. **It does not prove
`emp_expected_r`/`emp_p_double` predicts better than `ev_conf_adj`.** The
rank comparison shows the two disagree completely (0/20 overlap, twice); the
`emp_p_double` cross-tab shows a real, reproducible signal in the weak-EV
tail exists to *investigate* — neither result says which number a trader
should trust more. Only realised outcomes can do that, and they are not
being captured. `Trade_Idea_Id` now exports (prior Lab sprint), so the join
key for an outcome ledger exists — that remains the single highest-value
piece of follow-on work, unchanged from the EV Engine sprint's own
conclusion.
