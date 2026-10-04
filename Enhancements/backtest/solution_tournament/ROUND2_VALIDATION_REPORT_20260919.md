# AVSHUNTER solution tournament — Round 2 paired validation

**State:** Exploratory research only. Production was not changed.

## Paired comparison excluding explicit test/dirty runs

Each row compares the alternative with the recorded contract only where both have an exact future exit mark. This removes the coverage-selection bias in the raw Round 2 table.

| Horizon | Rule | Coverage | Paired n | Recorded ask→bid | Alternative ask→bid | Paired improvement | Alternative better | +100% recall |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | F1_TIGHTEST_SPREAD | 7495/7808 | 7009 | -39.94% | -23.94% | 16.01% | 73.05% | 24.14% |
| 1 | F2_NEAR_MONEY | 2122/7808 | 2018 | -20.62% | -11.89% | 8.73% | 68.58% | 10.34% |
| 1 | F3_DELTA_CORE | 2313/7808 | 2200 | -21.37% | -11.39% | 9.98% | 69.55% | 24.14% |
| 1 | F4_VALUE_COMPOSITE | 3611/7808 | 3424 | -25.32% | -12.34% | 12.98% | 74.91% | 20.69% |
| 1 | F5_CONVEX_SATELLITE | 0/7808 | 0 | n/a | n/a | n/a | n/a | 0.00% |
| 3 | F1_TIGHTEST_SPREAD | 6335/6642 | 5749 | -42.36% | -27.31% | 15.05% | 71.14% | 30.68% |
| 3 | F2_NEAR_MONEY | 1783/6642 | 1658 | -25.36% | -16.38% | 8.98% | 68.21% | 19.32% |
| 3 | F3_DELTA_CORE | 1953/6642 | 1814 | -25.52% | -16.18% | 9.35% | 68.58% | 26.14% |
| 3 | F4_VALUE_COMPOSITE | 3014/6642 | 2790 | -28.65% | -16.21% | 12.44% | 72.80% | 28.41% |
| 3 | F5_CONVEX_SATELLITE | 0/6642 | 0 | n/a | n/a | n/a | n/a | 0.00% |
| 5 | F1_TIGHTEST_SPREAD | 5237/5539 | 4519 | -46.87% | -30.85% | 16.02% | 71.83% | 35.78% |
| 5 | F2_NEAR_MONEY | 1403/5539 | 1243 | -29.97% | -17.95% | 12.01% | 72.81% | 21.10% |
| 5 | F3_DELTA_CORE | 1534/5539 | 1361 | -29.66% | -17.55% | 12.11% | 72.08% | 27.52% |
| 5 | F4_VALUE_COMPOSITE | 2366/5539 | 2080 | -33.05% | -18.09% | 14.96% | 76.06% | 32.11% |
| 5 | F5_CONVEX_SATELLITE | 0/5539 | 0 | n/a | n/a | n/a | n/a | 0.00% |

## Root-cause result

1. **The recorded selector is economically dominated on average by cleaner contracts.** Every executable alternative materially improves the paired ask-to-bid result. This confirms a contract-expression defect, not merely a reporting defect.
2. **No alternative creates positive expectancy.** Better geometry and spreads reduce the loss but do not overcome weak directional/timing edge and option richness.
3. **Mean improvement and convex-tail preservation conflict.** The near-money and delta-core rules improve the average most but retain only a minority of families containing +100% contracts. A single hard selector would sacrifice valuable convex opportunities.
4. **The convex-satellite hypothesis is not rejected; it is untestable in H.** Historical planned holds are 12–20 sessions, so the pre-registered hold≤5 condition never activates. It needs a population with genuine short-horizon thesis metadata.
5. **Some families have no executable member.** These should produce a named contract execution state while retaining the ticker thesis, rather than a false zero or thesis rejection.

## Research decision

Advance a two-lane expression design to Round 3, not a single replacement selector:

- **Core lane:** near-money/delta-core contract optimized for executable spread and stable delta.
- **Convex lane:** separately ranked satellite preserving fast-tail opportunity, activated only when horizon, volatility price, and quote evidence qualify.
- **Expression choice:** when options are rich, compare the permitted long-share expression for bullish theses; bearish theses remain option-or-no-trade because short shares are outside scope.

Round 3 must attribute outcomes to direction, IV, theta, spread, and timing, then validate the two-lane design on a larger certified history before any build recommendation.
