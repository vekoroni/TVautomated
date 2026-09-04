# 08 — Gaps register: narrative

**Document:** AVS-E2E-CODE-001 · Step 6 narrative
**Data:** `08_gaps_register.csv` — **151 rows**, `GAP-001` … `GAP-502`

ID ranges by analysis lane: 001–099 cross-cutting (main session) · 100–199 core
contracts and hotspots · 200–299 upstream · 300–399 midstream · 400–499 read
path · 500–599 canonical substrate.

---

## 1. Distribution

| Category (task vocabulary) | Rows |
|---|---:|
| SILENT_DEFAULT | 43 |
| MISSING_STATE | 27 |
| MISSING_INVARIANT | 18 |
| DEAD | 13 |
| UNWIRED | 12 |
| IDENTITY | 11 |
| READ_PATH_WRITE | 5 |
| DUPLICATE_WRITER | 4 |
| UNTRACED | 3 |
| Other lane-emitted categories | 15 |

`SILENT_DEFAULT` being the largest category is consistent with the prior's §12.2
diagnosis: generic fallback helpers keep the pipeline running at the cost of
correctness. The 43 rows are the enumerated form of that claim.

---

## 2. UNWIRED — built correctly, never fires

The clearest instances, each with the evidence that establishes it:

- **GAP-003 — the Horizon Router loses 292 tickers.** 1,248 rows in;
  655 + 284 + 0 + 17 = **956** out; 292 appear in no horizon output file and
  `horizon_summary_*.json` accounts for none of them. The §14.5 invariant
  `input = passed + rejected + deferred` **fails** here. It **holds** at the
  Execution→EOD boundary, where all 1,248 are covered by
  `eod_dropoff_audit_*.csv`. GAP-501 records why: `canonical_data/worklist_gate.py`
  enforces the invariant in code, and it is wired at Discovery→Packages only.
- **GAP-004 — the 11–20d horizon is empty.** `horizon_11_20d_*.csv` has 0 data
  rows, so no ticker is routed to the 20-session hold — yet 20.0 is precisely
  the value the lifecycle uses as `remaining_hold_sessions` on 623 of 657 rows.
- **GAP-008 — the macro size multiplier is dropped at the last boundary.**
  `horizon_size_multiplier` propagates through options_intelligence,
  execution_v3_5, the horizon files and morning_candidates, and is **absent from
  `final_opportunity_book`** — the book the Lab actually reads.
- **GAP-301 — eight collected-and-discarded inputs.**
  `trigger_confirmation_engine.py:956-976` populates `bars_15m`,
  `live_spread_pct`, `live_option_mid`, `live_iv`, `session_minutes_elapsed`,
  `signal_price`, `structural_tier`, `scs_score`; no logic path reads any of them.
- **GAP-311 — trigger state does not cross the Execution contract.** No
  `trigger_`, `tce_` or `tle_` name appears anywhere in `execution_schema.py`.

## 3. DEAD — 13 rows, and one class worth naming

Beyond individually dead modules (`atheoretic_signals.py`,
`convergence_engine.py`, `signal_funnel.py`, `orchestrator/` package,
`ml_confidence_layer/`), two patterns recur:

- **Dead forks with a shared output directory.** `zero_dte_screener.py` and
  `short_swing_screener.py` at the repo root are newer "Sprint 3" copies whose
  looser gating (Phase D admitted, `POST_EARNINGS_MOMENTUM` bypass) exists
  **only** in the unreachable copy; the executing copies inside the packages
  retain the older gates. Both forks write into the same output directory as
  their live twin, so a manual root-level run silently overwrites the live
  lane's eligibility file. An operator reading the root file believes a
  screening policy that never runs.
- **Unreachable thresholds.** `atheoretic_signals.py` gates on `ath_score >= 50`
  where the score can only take `{0,30,40,60,70,100}` (GAP-324); its entire
  z-score apparatus is unreachable because `_history` is an in-process dict and
  a single-pass run never accumulates five observations (GAP-323).

## 4. IDENTITY — 11 rows, all one theme

Run date, completed session and quote timestamp are conflated:

- **`thesis_id` is keyed `TICKER:SIDE:RUN_DATE`.** 927 of 927 observations for
  the evidence run pair an 08-31 thesis_id against an 08-28 `quote_as_of`. **86
  tickers already hold more than one `thesis_id`; seven hold three.** The prior
  (§11.8) states this "can" happen; it has already happened totally.
- **GAP-002 — no run artefact is immutable.** At least six stages rewrite
  already-promoted artefacts in place, producing a 02:55:42–02:55:55 rewrite
  cluster over six files first produced between 01:06 and 02:55.
- **GAP-010** — `horizon_summary.json` stamps `as_of_utc` from the macro
  packet's generation time (2026-08-29) inside a 2026-08-31 run.
- **CON-354 / GAP-315** — `exit_theta_date` uses machine-local `date.today()`;
  `eil_data_mode` overwrites its own quote-fallback provenance label.

## 5. READ_PATH_WRITE — 5 rows

**GAP-001** is the measured one. `write_final_run_manifest` is reachable from
four sites in `intelligence-lab/intelligence_lab.py` (L346, L1945, L2527,
L2604), two of them load-path fallbacks. `final_run_manifest.json` has mtime
**10:02:11** against a run that closed at **02:56:41** — a delta of 7 h 05 min
30 s — and the file's own `created_at_utc` matches its mtime to the second, so it
was **rewritten, not touched**.

## 6. MISSING_INVARIANT — the calculators that accept what they should reject

- `scripts/data_contract_validator.py:183-188` tests only `is None` on the last
  ten bars, so `NaN`, empty strings and zero prices pass the null gate.
- `execution_schema.py:60` comments "STRATEGY WEIGHTS (must sum to 1.0)" with no
  assertion enforcing it.
- `scenario_router.py:217` exempts a row with **no** asymmetry data from the
  geometry veto, because the missing value defaults to 0.0 and fails the `> 0`
  precondition.
- `tools/msi_production_readiness.py:159-163` checks required book fields
  against the **union** of all rows' keys, so a field present on one row
  satisfies the check for every row.
- `tools/msi_reconcile.py:88-90` compares `governed_direction` as an opaque
  string, and `_text(None)` returns `""` — so two sides that are **both** blank,
  both `UNRESOLVED` or both `STRANGLE` reconcile as PASS. The check is
  agreement, not validity.

## 7. UNTRACED — 3 rows, stated rather than filled

- **GAP-007** — 127 of 604 live `.py` files are untracked by git, including the
  entire option-liquidity-lifecycle module set; no previous revision exists
  in-repo to establish when current behaviour was introduced.
- **GAP-502** — 20 of the 31 `canonical_data/` and `contracts/` files in Lane E
  are undescribed. The identity substrate is described at its load-bearing seams
  but not exhaustively; time-and-session stamping across `historical_prices.py`,
  `history_bridge.py`, `daily_adapter.py` and `bundle_freshness.py` is the most
  likely location of further IDENTITY findings.
- **GAP-322** — two modules named `scenario_builder` exist and
  `vanguard/layer3_execution` is on `sys.path`; which one binds at import
  depends on path order and is **not resolvable from source**.

## 8. What is genuinely sound

Recorded so the register is not read as uniformly negative:

- The dropped-ticker rule **holds** at Discovery→Packages, enforced by
  `canonical_data/worklist_gate.py` and corroborated by measurement: **zero
  tickers appear at any downstream stage that were not present upstream, across
  all eight measured boundaries**.
- **Zero duplicate tickers** in every one of the eight principal artefacts.
- The **Polygon-options-disabled** policy holds: no Polygon options path exists
  in `canonical_data/`, the OLM store hard-rejects a non-MarketData provider at
  two separate points, and the run recorded zero Polygon options fallbacks.
- `contracts/macro_regime_safety.py` **cannot** block a ticker or set its
  direction — verified against the load-bearing policy claim.
- `market_structure/` is the strongest module set audited: content-addressed
  identity excluding provenance fields from the hash, atomic content-addressed
  persistence, every degraded path **named** rather than defaulted, an
  `ADVISORY_ONLY` authority declaration that holds, and a parameter set that
  declares itself `PROPOSED_NOT_CALIBRATED` in its own output.
