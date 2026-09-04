# Regime/Trend Input Remediation — Work Order Report

Work order: `CLAUDE_CODE_WORKORDER_regime_trend_fix.md`. Executed Stages A, B
and D. **Stage C was not attempted — the Stage B2 gate failed.** This was one
of two named stop conditions and the run order was followed exactly: no
adapter fix was implemented against an unconfirmed storage convention.

---

## Stage A — `bb_width` and IV percentile are computable, but not identically wireable

### A1 — Computability

**`bb_width`/`bb_width_history`: fully computable, confidence 95%.** Fetched
480 calendar days of daily bars per ticker via the existing
`polygon_data_fetcher.py` (unmodified) — 124/125 tickers returned ≥272
trading days (the 20-SMA + 252-day-percentile minimum), 125/125 fetches
succeeded. Throughput ~16 tickers/min end-to-end (fetch + compute + two DB
queries), no rate-limit throttling observed.

**An existing, already-live implementation was found and reused — no second
one was written**, per the work order's explicit instruction:
`scripts/run_vanguard_from_packages.py::compute_technical_enrichments()`
(lines 540–656, `bb_width` at 584–592). It is already called from
`build_orchestrator_like_payload()`, which `intelligent_orchestrator.py`'s
Vanguard phase actually executes — its own docstring (lines 545–549) already
names this exact defect: *"Without these, state_calculator defaults every
ticker to vol_regime=NORMAL... This causes Matches: 0."* A second,
numerically-equivalent implementation also exists in the offline DB-rebuild
script `avshunter_db_update.py:390-393` (different scale factor, same
percentile rank) — not used, since a live-path implementation already exists.
`ema21`/`ema50` are **also already computed and already flow into the
Vanguard payload** (`avshunter_discovery_ULTIMATE.py:139-140,1984-1987` →
`run_vanguard_from_packages.py:791-793`) — `orchestrator_adapter.py::_tech()`
simply never reads them out of the payload it's handed. For both `bb_width`
and the EMAs, **the correct Stage C fix is plumbing, not recalculation**,
exactly as the work order hoped.

**IV percentile: located, but genuinely not available at the point
`_tech()` runs — confidence 90%.** Traced to
`scripts/avshunter_options_intelligence.py::compute_iv_context()` (primary
calc lines 3341-3373, percentile rank of ATM implied vol against a rolling
realised-vol distribution). Confirmed via `intelligent_orchestrator.py`
(line 3719 Vanguard call, line 3733 Options Intelligence call) that **Options
Intelligence runs strictly after Vanguard** — the option-chain data IV
percentile depends on doesn't exist yet when `state_calculator.py` needs it.
This is not a wiring oversight of the same kind as `bb_width`/EMAs; it is a
phase-ordering fact. `scripts/actuarial_enrichment_pass.py` (Phase 8.5, runs
after Options Intelligence) only *reads* the already-frozen `vol_regime`
without ever recomputing it, even though real IV data would be available to
it by that point — flagging this as an architectural option for whoever
scopes the eventual fix (recompute at 8.5 / resequence / same-day proxy),
without picking one, per the work order's read-only Stage A scope.

**Bonus findings, outside A's scope but material to the pipeline overall:**
`scripts/actuarial_enrichment_pass.py`'s `actuarial_wyckoff_phase_bucket`/
`actuarial_crabel_state`/`actuarial_iv_regime` audit columns are 100% null
across both archived runs — dead fields never populated despite being
`intelligent_orchestrator.py`'s (lines 4082-4092, 5422-5432) intended
auditability channel. Separately, the CSV's bare `iv_regime` column uses
Options Intelligence's own vocabulary (`COMPLACENT`/`STRUCTURAL_BUILD`/
`EVENT_PRICED`), which never matches the actuarial DB's vocabulary
(`HIGH_IV`/`NORMAL_IV`/`LOW_IV`/`ELEVATED_IV`) — using it directly zeroes
every match. Neither was fixed (out of this work order's scope); both should
be tracked as follow-on defects.

### A2 — Damage range, 125 tickers (exceeds the 100+ target)

Reused production code directly (`StateVectorCalculator`'s real
`_calculate_volatility_regime`/`_calculate_trend_maturity`, queried against
the live `actuarial_database_v6.parquet`, 6,033,072 rows). A **100% match-tier
fidelity check** against the true recorded match inputs (recovered via
`layer2__original_state_key` in `vanguard_signals.csv`, not the dead audit
columns) reproduced the original tier for 125/125 rows — this is the basis
for trusting the numbers below.

| Metric | Result |
|---|---|
| `vol_regime` changed from NORMAL | 8/125 (6.4%) — all → COMPRESSION |
| `trend_direction` changed from SIDEWAYS | 37/125 (29.6%) — 25 → UP, 12 → DOWN |
| Either dimension changed | 45/125 (36.0%) |
| Match tier changed | 26/125 (20.8%): 20 EXACT→RELAXED (downgrade), 6 ANALOGUE→RELAXED (upgrade) |

| `win_rate` \|Δpp\| | median | p75 | p90 | max |
|---|---|---|---|---|
| 5d | 0.07 | 0.99 | 2.53 | 5.88 |
| 10d | 0.13 | 0.77 | 3.18 | 10.38 |
| 20d | 0.13 | 1.33 | 3.57 | 5.86 |

**This collapses the prior 5–40% range to roughly 6% (vol_regime alone) /
30% (trend_direction alone) / 21% (tier movement)** — materially narrower
than Phase 1.1's 20-ticker estimate, and consistent in order of magnitude
with it. Sample distributions (93.6% NORMAL / 70.4% SIDEWAYS) diverge from
the DB's unconditional splits (38.3%/48.9%) because the sample is
Discovery-pre-filtered live signals, not a random historical draw — expected,
not a computation error (confidence 85%).

---

## Stage B — THE GATE: **FAILS.** Stage C not attempted.

### B1 — What actually built the database

Two producers were found and read directly; several other candidates
(`actuarial_cache_builder.py`, `build_state_v2.py`, `enrich_actuarial_9dim.py`,
`add_early_candidate.py`) were confirmed to be **consumers** of
`vol_regime`/`trend_direction` as pre-existing columns, not computers of
them — ruled out.

| File | Role | Evidence |
|---|---|---|
| `avshunter_db_update.py` (untracked, mtime 2026-05-17) | Producer | Task Scheduler logs show it invoked directly against `actuarial_database_v6.parquet` on 2026-05-17; has its own `_compute_state()`, does not import `state_calculator.py` |
| `scripts/polygon_actuarial_builder.py` (tracked, commit `0c40e42`, 2026-05-20) | Producer | Independent `_calculate_state_at_date()`, also does not call `state_calculator.py` |

**Both confirmed producers are independent implementations of
`state_calculator.py`.** Corroborated at the byte level: the live parquet's
`date` column is a literal patchwork — 62% carry a full timestamp matching
`polygon_actuarial_builder.py`'s un-truncated `pd.to_datetime(unit='ms')`,
38% carry a clean date-only string matching `avshunter_db_update.py`'s
explicit `.dt.date` truncation — direct proof the file was written by at
least two different code paths.

**Exact parameters extracted from source, and they disagree on the two
decisions that matter most:**

| | DB builder family | `state_calculator.py` (live query side) |
|---|---|---|
| Vol regime formula | AND/OR: COMPRESSION if atr%ile<30 **and** bb%ile<30; EXPANSION if atr%ile>70 **or** bb%ile>70 (independently confirmed by direct read: `avshunter_db_update.py:459-465`) | Weighted average: `0.33·atr + 0.33·bb + 0.34·iv`, thresholds 20/80 |
| IV term | **None** | 0.34 weight |
| Trend direction | `close > ema21 > ema50 > ema200` triple-stack, **no ADX gate** (confirmed: `avshunter_db_update.py:472-476`) | `ema21>ema50 and close>ema21 and adx>25`, pairwise + ADX gate |

The two DB-side producers even disagree with *each other* on ATR smoothing
and percentile-window length — a second-order internal inconsistency, noted
but not the deciding factor.

### Empirical reconciliation (20 tickers × 3 dates, real Polygon OHLCV)

| Method | vol_regime agreement vs. DB | trend_direction agreement | Both |
|---|---|---|---|
| `avshunter_db_update.py` convention | 76.7–81.7% | 80–90% | 63–67% |
| `polygon_actuarial_builder.py` convention | 66.7% | 90.0% | 58.3% |
| **`state_calculator.py` convention** | **33.3–36.7%** | **80.0%** | **23–25%** |

Every builder-family variant beats `state_calculator.py` on both dimensions,
every time, by a wide margin. The residual imprecision (no builder-family
variant self-reproduces the DB at 100%, most likely because
`avshunter_db_update.py` is untracked with no version history to recover its
exact historical window parameters) affects the *precision* of the agreement
percentage, not the *direction* of the conclusion.

### B2 — Gate result: **FAILS. Confidence 90%.**

This is not "cannot determine" — the convention was identified from source,
corroborated by two independent producer scripts and by the date-format
forensic split. `state_calculator.py`'s convention (weighted-average-with-IV,
20/80 thresholds, EMA-pairwise-with-ADX) is structurally different from what
built this database (AND/OR-no-IV, 30/70 thresholds, EMA-triple-stack-no-ADX),
confirmed at 23–37% agreement — nowhere near the 90% bar, concentrated
exactly where the formulas differ most (`vol_regime`).

**Per the work order and the standing instruction: the fix is no longer
"wire the adapter," it is "reconcile two calculation paths" — separate design
work requiring its own sign-off. Stage C was not started.** Implementing the
planned adapter fix here would have replaced a known, legible defect (query
side always NORMAL/SIDEWAYS) with an unknown one (both sides vary, using
different conventions, disagreement invisible) — precisely the failure mode
Stage B existed to prevent.

---

## Stage C — Not attempted (gate failed)

No code changes were made toward the adapter fix, tier-downgrade semantics,
or full-book blast radius. All of Stage C is now blocked on a separate,
un-scoped decision: which convention should be authoritative going forward
(rebuild the DB under `state_calculator.py`'s convention, change
`state_calculator.py` to match the DB's, or something else), which is a
design question for the human trader, not something to resolve unilaterally.

---

## Stage D — Polygon key: source fixed, provider rotation still required

**Done, committed separately (`80848e1`), unrelated to Stages A-C:**
- `polygon_data_fetcher.py`'s docstring no longer carries the key in
  plaintext — replaced with an env-var pointer and a note that the exposed
  key needs rotating. This file was previously untracked; it is now
  committed with the secret already removed, so its git history carries no
  exposure.
- `pipeline_interpreter/live_market_reader.py` — found during the mandated
  grep, **fixed in the same commit**: it carried the *same* Polygon key plus
  a MarketData.app token as `os.environ.get(..., "<literal>")` fallback
  defaults. This file **is tracked** (committed in `79fcfb4`), so both
  secrets are genuinely present in this repo's git history, not just the
  working tree — this is the more urgent of the two files, and is the one
  place where "remove from source" alone provably does not undo the
  exposure. Both fallbacks are now `""` — a missing env var fails loudly
  (an auth error) rather than silently resuming on an exposed value.

**Not done — requires you, not me:**
- **Rotate the Polygon key at the Polygon dashboard.** I have not done this
  and should not do it unsupervised — it's a live, hard-to-reverse action on
  a third-party account tied to a production data feed, and I don't hold the
  login/2FA. Removing the key from source (done above) does not invalidate
  it; anyone who saw the old commits or working tree still has a working key
  until you rotate it at the provider.
- After rotating, update `POLYGON_API_KEY` in `.env` to the new value (no
  code change needed — both fixed files already read from the environment
  with no fallback).

**Grep for other hardcoded credentials — found more than the one named
target, reported per the work order's instruction, none of it fixed beyond
the two files above (out of this work order's named scope, flagging for a
decision):**

| Secret | Files | Tracked in git? |
|---|---|---|
| Same Polygon key, additional hardcoded copies | `avshunter_ticker_probe.py`, `rapid_rotation_flag.py`, `position_lifecycle_tracker.py`, `bond_macro_intelligence.py`, `avshunter_db_update.py` (both copies, this repo and the sibling `vanguard` one), `legacy/update_universe.py.backup` | **No** — all untracked. Rotating at the provider retires the literal in all of them simultaneously; the leftover text becomes a dead string, not a live secret. Still worth cleaning up. |
| MarketData.app token, additional copy | `md_api_diagnostic.py` | No — untracked |
| **Live Anthropic API key**, hardcoded as an `os.environ.get()` fallback default | `ma_cockpit/ma_cockpit_engine.py:9`, `news_terminal/news_terminal_engine.py:8`, 3 files under `pipeline_interpreter/` (backup/archive variants) | No — all untracked, **but this is the most urgent single item in this table.** `avshunter_audit_report_20260627.md` (itself untracked, also reproduces both the Polygon key and this pattern in plaintext) already flagged this exact key as needing rotation at console.anthropic.com after being transmitted through a Claude session — that rotation does not appear to have happened, since the key is still live in 5 files today. |

None of these were modified — they're outside this work order's named scope
(which called out `polygon_data_fetcher.py` specifically), and unilaterally
editing 8+ additional files touching two different credentials felt like the
wrong call to make without you seeing the list first. **My recommendation:
treat the Anthropic key as the most urgent follow-up, independent of
everything else in this report** — it's a different service, already flagged
once before, and apparently never actually rotated.

No key or token value is reproduced anywhere in this report, in commit
messages, or in the source fixes above.

---

## What I could not determine, and why

- **Which of the two DB-builder conventions (if either) should become
  authoritative**, or whether a third approach (e.g., rebuilding the DB under
  `state_calculator.py`'s convention) is preferable. This is exactly the
  separate design work the B2 gate exists to defer — not something to guess.
- **The exact historical window parameters (`FETCH_WINDOWS` boundaries, ATR
  smoothing choice) in effect for any single historical row of the DB.**
  `avshunter_db_update.py` is untracked with no version history; only the
  current on-disk version could be read. This bounds the *precision* of the
  measured 23-37% agreement rate, not its direction.
- **The identity of whatever pre-2026-04 code originally seeded the 62% of
  rows with the un-truncated timestamp format**, since `polygon_actuarial_builder.py`
  was only added to git on 2026-05-20 and can't itself be that ancestor,
  though it shares its date-serialization fingerprint (moderate confidence,
  ~70%, that it also shared the same regime/trend formula, inferred rather
  than source-confirmed for that specific unlocated file).
- **Whether the 8 Stage-A vol_regime→COMPRESSION flips are driven more by
  `bb_pct` or `iv_pct`** — not computed; low value at n=8.
- **Full completeness of the Stage D credential sweep**: ~85% confidence.
  Binary/office files (`.docx`) were not text-searched; only pattern-anchored
  search was run, so a genuinely novel unlabeled high-entropy string not
  near a keyword like `key`/`token`/`secret` could theoretically be missed.

## Golden diff

```
polygon_data_fetcher.py                       | new file, secret-free from first commit  (80848e1)
pipeline_interpreter/live_market_reader.py    | 6 insertions(+), 8 deletions(-)          (80848e1)
```
No other repository file was modified. Stages A and B produced findings only,
via read-only scratch scripts in the session scratchpad (never committed).

## Rollback procedure — for the one commit made

```powershell
# Revert Stage D's key-hardening commit:
git revert 80848e1

# Confirms: polygon_data_fetcher.py returns to untracked-with-plaintext-key
# state (working tree only — this repo's history never carried it, so
# reverting is a pure content restore, not a history rewrite); live_market_reader.py
# returns to its 79fcfb4 state with both hardcoded fallbacks restored.
# Do NOT do this except to unblock an emergency — reverting restores the
# security defect this commit exists to close.
```
No other rollback is needed — nothing else was changed.

---

## Standing limitation

No closed loop from signal to realised outcome exists. Nothing in Stages A,
B, or D changes this. Had Stage C proceeded, it would have made the
actuarial match *more correct*, not proven that the resulting win rates
predict better — only realised outcomes can, and they are not being
captured. `Trade_Idea_Id` exports, so the join key exists. This is now the
fourth independent piece of work to reach this same conclusion.
