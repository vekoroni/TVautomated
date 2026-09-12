# DOI-5 Deterministic Scenario and Valuation Engine — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Result:** OFFLINE ACCEPTED  
**Next phase:** DOI-6 dynamic lifecycle and re-ranking

## Delivered

- A pure, provider-agnostic dividend-adjusted Black–Scholes implementation for
  deterministic long CALL and long PUT scenario arithmetic.
- XNYS-session early, middle and late evaluation instants using the existing
  governed exchange calendar, including weekends, holidays and early closes.
- A fixed 18-cell scenario grid per evaluable contract: governed target versus
  governed invalidation, crossed with three timings and contracted/base/expanded
  implied-volatility stresses.
- Explicit entry/exit friction, continuous dividend-yield, risk-free-rate,
  corporate-action and American-exercise disclosures.
- A versioned `ranking_score_uncalibrated`, calculated as median favourable
  scenario return plus worst adverse scenario return. It is a deterministic
  stress balance, not a probability, EV forecast or trade verdict.
- Exact-contract canonical observation persistence followed by immutable DOI
  assessment persistence with source dataset, quote and calculation lineage.
- Retention and assessment of two-sided, one-sided and no-quote DOI-4 family
  members. Missing positive ask suppresses return/utility only; it does not
  remove the contract or ticker opportunity.
- Compatibility with both canonical `implied_vol` and common IV aliases.
- Explicit separation of an upstream acquisition count from DOI-5's own zero
  provider-call count.

## Authority boundary

DOI-5 cannot change the governed CALL/PUT direction, invalidate a ticker
thesis, grant capital, execute a trade, or select the preferred contract. All
probability-shaped fields remain null and `probabilities_calibrated` remains
false. `expected_net_return`, `expected_downside` and
`expected_time_to_monetisation` remain null because the 18 scenarios have no
calibrated weights.

## Persistence defect found and repaired

The phase exposed an existing multi-contract lifecycle defect. After inserting
several exact contracts at the same provider quote timestamp,
`record_contract_observation()` returned `latest_observation(thesis)`, whose
ordering was ambiguous across those contracts. The following assessment then
correctly rejected the mismatched observation.

The writer now resolves and returns the immutable `observation_id` minted for
the inserted row. A public `contract_observation(observation_id)` reader and a
three-contract same-timestamp regression cover the boundary. No schema or
production database migration was required.

## Verification

| Check | Result |
|---|---:|
| DOI-5 focused arithmetic/persistence tests | 14/14 PASS |
| DOI-1 through DOI-5 plus lifecycle regression | 62/62 PASS |
| DOI authority-focused checks | 17/17 PASS |
| Three isolated CDS history checks | 3/3 PASS |
| Compilation | PASS |
| Production database writes | 0 |
| Provider calls in real-data rehearsal | 0 |

The complete `unittest` discovery executed 581 tests: 547 passed, three CDS
history tests failed in global order but passed 3/3 immediately in isolation,
and 31 pytest-dependent modules could not import because pytest is absent from
the active Python 3.14 environment. This is not presented as a clean global
regression. The active repository `venv` is also unusable because it references
a removed/blocked WindowsApps Python 3.13 executable. These are test-environment
and suite-isolation gaps, not DOI-5 acceptance failures, and remain visible.

## Real canonical-chain rehearsal

Frozen canonical MarketData chain:

- ticker: **A**;
- completed session: **2026-09-08**;
- dataset: `778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e`;
- source rows: **242**;
- governed CALL family candidates: **89**;
- assessed contracts: **89**;
- two-sided: **77**;
- one-sided retained: **12**;
- scenario values: **1,602**;
- utilities available: **89**;
- probability fields populated: **0**;
- authority violations: **0**;
- replayed observations reused: **89/89**;
- replayed assessments reused: **89/89**.

The rehearsal used a disposable control plane. Its 4% risk-free rate, 1%
dividend yield and 25 bp entry/exit friction were fixed test assumptions, not
claimed current market inputs. The source production registry and chain were
read only.

## Files

- `domain/deterministic_option_valuation.py`
- `canonical_data/dynamic_options_valuation.py`
- `canonical_data/option_liquidity_lifecycle.py`
- `canonical_data/__init__.py`
- `tests/test_dynamic_options_deterministic_valuation.py`
- `audit/doi/doi5_real_chain_rehearsal.py`
- `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`

## Promotion boundary

DOI-5 is deployed as an importable canonical application service and is
offline accepted. It deliberately does not replace the live legacy selector,
publish to the Intelligence Lab or choose a preferred contract. DOI-6 must add
material-change triggers, lifecycle re-evaluation, hysteresis and append-only
supersession before later DOI-9 ranking and DOI-10 UI integration. Production
acceptance remains DOI-11 after a completed-session and Morning Gate cycle.

