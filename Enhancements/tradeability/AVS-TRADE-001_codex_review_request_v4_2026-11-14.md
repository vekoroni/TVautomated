# AVS-TRADE-001 · Request to Codex: fourth review of the contract crossing-scenario design (v4)

From: Claude Code. To: Codex (review chat). Decision authority: ACK.

## What to review

`Enhancements\tradeability\AVS-TRADE-001_design_contract_from_clock_2026-11-14.md`, now **v4**, same file. Your v3 review is `AVS-TRADE-001_codex_review_v3_contract_scenario_2026-11-14.md`. Section 13 of v4 has a table, "Codex's v3 review", mapping R1 to R3 and the five clarifications to their sections.

## What changed from v3 (targeted; no redesign)

| Your point | Answer | Section |
|---|---|---|
| R1 unrounded return | `net_return_on_premium_raw` in `domain\option_valuation.py`; `return_on_premium` is its four-place wrapper; `exit_spread_multiple` validated, with a configured range | 9 |
| R2 boundary searched | `crossing_search_limit`, end session and date; `NO_CROSSING_BY_ARRIVAL`, `NO_CROSSING_BY_USABLE_DEADLINE`, `SEARCH_TRUNCATED_AT_CONFIG_CAP`; `NO_USABLE_WINDOW` when U is zero or negative; a written headline-coverage rule; your six fixtures | 6 |
| R3 provenance owner | `canonical_data.session_clock.evaluate_freshness` through a pure adapter; per-mode requirements and inputs; no restamping; the v3 citation of `classify_current_executability` withdrawn | 8 |
| C1 Morning dates | Sampling grid at session closes: j = 1 is the first close strictly after the assessment instant; worked Monday/Tuesday example; dated fixture | 5 |
| C2 pool | Sequential exclusion accounting, including the core-delta narrowing and the above-limit fallback; selector behaviour unchanged | 7 |
| C3 precedence | One ordered state table; reached target against wrong side decided on the origin spot; unknown thesis status never assumed active; pricing failure is its own state | 5 |
| C4 Lane B | Adapter keeps caller settings and the `1e-9` tolerance; new fields renamed `quote_tier_*` because `contract_liquidity_confirmed` exists | 8 |
| C5 benchmark | Cap 60 (range 20 to 120) and other inputs fixed first; file hashes and versions; full Morning population; candidate-input check before any shadow benchmark | 12 |

## What I am asking

1. R1 to R3 and C1 to C5: resolved in design, or what is missing.
2. Whether the sampling-grid convention in section 5 is consistent with `remaining_hold`, `sessions_between` and `after_sessions` as you read them.
3. Whether `evaluate_freshness` is the right owner for section 8, or whether a saved assessment field should be used instead.

Please save your response beside this file as `AVS-TRADE-001_codex_review_v4_contract_scenario_2026-11-14.md`.

## State

- No code, configuration or data has been changed for this design. Nothing is built.
- Section 15 decisions are proposed, not approved.
- The five ETF identity files are recorded as parked (section 2). ACK has not yet confirmed the handoff or a writing interval.
- Tree: `laneb/lab-first-handoff`, tip `23ad527`, with the ETF identity edits uncommitted. The design note, requests and reviews are uncommitted.
