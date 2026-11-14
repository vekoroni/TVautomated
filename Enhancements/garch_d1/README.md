# GARCH D1 cumulative-window repair — 13 November 2026

## Scope and authority

Approved by ACK: fix D1 and test using saved data; no providers or pipeline run.
Governing references: behavioural specification section 11 and method note 04,
section 2. This is arithmetic integrity, not forecast calibration or evidence of
profitable option returns. Lane B and expiry selection remain with Claude.

## Repair

- The legacy-named 1–5, 6–10 and 11–20 fields now mean cumulative one-sigma
  percentages to trading sessions 5, 10 and 20.
- Reuse the canonical volatility-budget calculation: annual volatility times
  sqrt(sessions / 252). Remove subtraction of standard deviations and the
  calendar-day 5/7 conversion from these checkpoint outputs.
- Keep the external field names, with explicit cumulative/session metadata.
- The shared reader prefers canonical fractions, reads marked cumulative aliases
  without summing them again, and retains old unmarked incremental-row semantics.
- Do not change HAR/GARCH fitting, fallback ordering, volatility guards, confidence,
  IV tailwind, history integrity, model authority, or any historical publication.

## Evidence

`test_garch_d1_cumulative_windows.py`: before repair, 14 failed / 4 passed;
after repair, 18 passed. Covers HAR and GARCH stand-ins, bounds, EWMA, ATR,
missing inputs and old/new reader compatibility.

Offline regression totals: **116 passed, 1 skipped**, across eight files:

| Test file | Passed | Skipped |
|---|---:|---:|
| test_garch_d1_cumulative_windows.py | 18 | 0 |
| test_layer3_volatility_integrity.py | 28 | 0 |
| test_layer3_volatility_leftovers.py | 27 | 0 |
| test_layer3_garch_fallback.py | 5 | 1 |
| test_avs_int001_scenario_horizon_parity.py | 20 | 0 |
| test_avs_fix_002_runtime_adapters.py | 4 | 0 |
| test_layer3_price_history_integrity.py | 7 | 0 |
| test_realised_volatility.py | 7 | 0 |

The optional real-arch test is skipped because arch is absent; the GARCH path
is covered by stand-ins. Existing NumPy empty-slice warnings remain unchanged.
Regression commands use `-B`, `-p no:cacheprovider`, the network-blocking plugin
`-p Enhancements.garch_d1.offline_guard`, one test file per process, and a short
temporary directory outside live data.

`SAVED_REPLAY_20261113.json`: 2,800 saved forecasts, 2,799 finite. Old aliases
non-cumulative on 2,799; corrected aliases non-cumulative on zero. The existing
R17 verifier rule passes on the replayed finite rows. This does not certify the
whole historical run or its trade eligibility. One missing forecast remains
unassessed.

81 price-history replays: nine tickers, three as-of dates (20 October,
6 November, 12 November), three history lengths. HAR-RV 27, EWMA 27, ATR 27.
Every non-move result field matches the in-memory pre-fix calculation. SQLite
opened mode=ro/query_only and promptly closed. DB/WAL metadata/header hashes
and saved forecast metadata/header hash unchanged. No live output rewritten.

SPY, 12 November, 261 bars: annual forecast unchanged at 0.14384420385273813.
Old percentages: 1.712431, 0.709312, 1.003119. Corrected cumulative session
percentages: 2.026176, 2.865445, 4.052351.

## Remaining Codex work: dependency order, not authorization to build it here

1. Morning timing/late-start pricing stop (#2). Offline boundary tests first;
   acceptance on five real sessions remains a separate forward check.
2. Live-entry quote contract/freshness enforcement (#3). Saved stale/missing/
   crossed quote tests first; actual sub-60-second live acceptance cannot be
   proved by saved data alone and is not run here.
3. Option monetisation/valuation publication (#7): separate observed A12 first
   profit from a forecast; preserve costs, IV stress, failures and unassessed
   rows. A 90% population target must never be met using fabricated evidence.
4. Pipeline contract coverage/liquidity/economics (#5), initially shadow only.
   Do not activate a selector before validation or change Claude's expiry policy.
5. Publish ordered alternatives with complete quote/economic lineage (#6),
   compatible with the same selection evaluation. ACTIVE remains a later gate.
6. Publish the in-window/watch flag (#8) from the agreed clock. Distinguish
   monetisation n from underlying arrival. Keep longer-horizon names visible;
   no hidden restriction of 1–n-session trades. Ranking changes require an
   explicit policy, not a Lab-side re-ranking.

Items 1, 9 and 10 in ACK's list are Lane B/user work, not implemented here.
QQQ enhancements remain a separate workstream. No commit or push performed.
