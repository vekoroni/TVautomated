# Claude Code Task — Database Current-State Report

## Your role

**Data Engineer, discovery only.** Produce a factual current-state report on the
AVSHUNTER persistent data stores.

## Scope

**This task produces a report. Nothing else.**

- **No fixes.** Not one line, however obvious.
- **No recommendations** on what should change. Facts only.
- **No rebuilds, no migrations, no schema changes, no cleanup.**
- **No API calls that consume paid credits** beyond what is needed to establish
  data availability windows — and state the credit cost of anything you do run.
- `git status` must be clean at the end apart from the report file.

If you find something alarming, **record it and keep going**. Do not act on it.

## Why this exists

A planned fix was halted because the historical database's calculation
convention was found to disagree with the live code's. Before any decision is
made about which convention becomes authoritative, we need to know what the
databases actually contain, who built them, and what depends on them.

Prior findings, established and not to be re-verified:
- `actuarial_database_v6.parquet` holds ~6,033,072 rows
- At least two producers wrote it: `avshunter_db_update.py` (untracked) and
  `scripts/polygon_actuarial_builder.py` (tracked, `0c40e42`)
- Its `date` column is split 62% full-timestamp / 38% date-only — evidence of
  two different writers
- The two producers disagree with each other on ATR smoothing and percentile
  window length

## Rules

1. **Report what is, not what should be.** No opinions on remediation.
2. **Confidence percentage on every non-trivial claim.** "I could not determine
   this" is a complete answer and preferable to inference presented as fact.
3. **Distinguish observation from inference explicitly**, every time.
4. **Never reproduce credential values** in the report, in output, or in commits.
5. If a query would be slow or expensive, say so and propose a sampling approach
   rather than running it blind.

---

# PART 1 — Inventory every persistent store

Do not assume there are exactly two. **Find them all.**

Search the repository and its configured data directories for every persistent
data store: `.parquet`, `.db`, `.sqlite`, `.duckdb`, `.h5`, `.feather`, `.pkl`
holding tabular data, and any large `.csv` acting as a store rather than a run
output.

Known candidates to confirm and include:
- `actuarial_database_v6.parquet` (and any v1–v5 predecessors still on disk)
- `phantom_history.db`

For each store, report:

| Field | Detail |
|---|---|
| Absolute path | |
| Format and engine | |
| File size on disk | |
| Row count | |
| Column count | |
| Created / last modified (filesystem) | |
| Tracked in git? | If yes, first and last commit touching it |
| Referenced in `.gitignore`? | |
| Duplicate copies elsewhere on disk | Paths and whether contents differ |

Flag any store that is **untracked**, since it has no history and cannot be
rolled back.

---

# PART 2 — Provenance: who built each store

For every store in Part 1:

1. **Every writer.** Which `.py` files write to it? Give `file:line` for each
   write call. Distinguish **producers** (compute and insert new rows) from
   **updaters** (append or modify existing) and from **consumers** (read only).
2. **Tracked or untracked**, per writer. For tracked ones, first commit, last
   commit, and dates.
3. **Invocation evidence.** Scheduled tasks, batch files, orchestrator calls,
   log entries. When did each writer last actually run?
4. **Overlap.** Where more than one writer targets the same store, state whether
   they can write the same rows and what happens if they disagree.

For `actuarial_database_v6.parquet` specifically:

5. **Map the 62/38 date-format split to date ranges.** Which calendar periods
   were written by which producer? Report the boundary dates. If it isn't a clean
   temporal split, say so — that is a more significant finding.
6. **Is there evidence of a third, earlier producer?** The prior investigation
   noted `polygon_actuarial_builder.py` was only added to git on 2026-05-20 and
   cannot be the ancestor of older rows. Look for it. If not found, say so.

---

# PART 3 — Content and coverage

For each store:

1. **Full column list** with dtype, null rate, and distinct-value count.
2. **Date range** — earliest and latest, plus row counts per year.
3. **Ticker coverage** — distinct tickers, and rows per ticker (min, median, max).
4. **Gaps** — missing date ranges, tickers with sparse coverage, columns that are
   100% null.
5. **Duplicates** — rows sharing the same ticker and date. If they exist, do they
   agree on their values? Disagreement is a significant finding.
6. **Internal consistency** — for `actuarial_database_v6.parquet`, report the
   distribution of `vol_regime` and `trend_direction` **split by the date-format
   groups from Part 2.5**. If the two producers' rows show different
   distributions, that quantifies the inconsistency.

---

# PART 4 — External data dependencies

The pipeline draws on two paid data providers. Establish precisely what each
store depends on, and what is still reachable today.

**Provider entitlements as currently held:**
- **Polygon — Stocks Starter:** US stocks only, **no options entitlement**,
  **5 years of historical data**, unlimited API calls, 15-minute delayed
- **MarketData — Trader:** 100,000 credits/day resetting 09:30 ET, real-time
  stocks and options, unlimited history, **options billed per symbol returned**,
  50 simultaneous requests, single IP

Report:

1. **Which provider supplied which columns**, per store. Trace from the builder
   source.
2. **The critical number: how many rows fall outside Polygon's 5-year window?**
   Report the count and percentage, and the cut-off date. **This determines what
   fraction of the database could be recomputed from reachable source data at
   all.** State it plainly.
3. **Which columns require options data** (implied volatility, Greeks, chain
   data) and therefore MarketData rather than Polygon.
4. **`compute_iv_context()` in `avshunter_options_intelligence.py` — what is the
   reference distribution?** The IV percentile is described as ATM implied vol
   ranked against a rolling distribution. Is that reference distribution
   **realised volatility** (price-derived, free) or **historical implied
   volatility** (options-derived, billed per symbol)? Give `file:line`.
   **This single fact determines whether IV percentile is cheap or prohibitive
   to reconstruct.**
5. **Current daily credit consumption.** From logs or by counting call sites,
   estimate what a normal evening run plus morning gate consumes against the
   100,000/day allocation. Note that both draw on the same window, since it
   resets at 09:30 ET rather than midnight.

---

# PART 5 — Dependency map

For each store, enumerate **every consumer** — the modules, scripts and pipeline
phases that read it. For each, state:

- `file:line` of the read
- Which columns it reads
- Whether it branches on the values or merely passes them through
- What happens if the store is missing or a column is absent — does it fail
  loudly, or degrade silently?

That last point matters: this codebase has a documented history of silent
degradation on missing fields.

---

# PART 6 — Observed gaps

A factual list. **No recommendations.** For each item: what was observed, where,
and confidence.

Include at minimum:
- Columns present in the schema but never populated
- Vocabulary mismatches between what a store holds and what consumers expect
- Stores or writers that are untracked
- Any store with no identified writer, or a writer with no identified store
- Date ranges present in one store and absent from another where they should align
- Anything you could not determine, and why

---

# Deliverable

`DATABASE_CURRENT_STATE_REPORT.md`, structured as Parts 1–6.

Lead with a summary table: every store, row count, date range, tracked status,
and number of identified writers.

**Then stop.** No recommendations, no proposed remediation, no next steps. The
decision about what to do with this belongs to the trader and cannot be made
without the facts this report provides.

## A note on scope discipline

You will find things that look like defects. Several are already known and
documented in prior reports. Record them in Part 6 and move on.

The value of this report is that it is **complete and neutral**. A report that
begins recommending fixes stops being an inventory and becomes an argument, and
an argument is not what is needed before this decision.
