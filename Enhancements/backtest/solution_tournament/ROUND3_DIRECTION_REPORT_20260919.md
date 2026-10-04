# AVSHUNTER solution tournament — Round 3 direction holdout

**State:** Exploratory research only. The sealed 2026 holdout has now been opened under the frozen protocol.

## Universe holdout result

| Horizon | Rule | Signed return | 90% CI | Hit rate | Market-adjusted | CALL mix | AUC |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | ALWAYS_CALL | -0.015% | -0.284%…0.261% | 50.030% | -0.017% | 100.000% | n/a |
| 1 | MOMENTUM_20 | -0.088% | -0.222%…0.053% | 48.110% | -0.032% | 54.130% | n/a |
| 1 | MEAN_REVERSION_5 | 0.170% | 0.019%…0.318% | 52.960% | 0.105% | 48.690% | n/a |
| 1 | SPY_REGIME | -0.317% | -0.574%…-0.061% | 44.210% | -0.002% | 61.510% | n/a |
| 1 | LOGISTIC_V1 | -0.167% | -0.422%…0.065% | 46.200% | 0.069% | 53.780% | 0.455455 |
| 1 | HGB_V1 | 0.092% | -0.159%…0.346% | 50.290% | 0.046% | 56.670% | 0.491461 |
| 3 | ALWAYS_CALL | 0.421% | -0.059%…0.902% | 51.720% | 0.136% | 100.000% | n/a |
| 3 | MOMENTUM_20 | -0.235% | -0.516%…0.046% | 47.850% | -0.149% | 54.120% | n/a |
| 3 | MEAN_REVERSION_5 | 0.244% | -0.070%…0.583% | 51.820% | 0.245% | 48.700% | n/a |
| 3 | SPY_REGIME | -0.647% | -1.117%…-0.199% | 42.900% | -0.060% | 61.500% | n/a |
| 3 | LOGISTIC_V1 | -0.037% | -0.316%…0.235% | 49.260% | 0.059% | 67.720% | 0.494125 |
| 3 | HGB_V1 | 0.360% | -0.102%…0.852% | 51.480% | 0.194% | 63.020% | 0.510164 |
| 5 | ALWAYS_CALL | 0.257% | -0.295%…0.837% | 50.640% | 0.139% | 100.000% | n/a |
| 5 | MOMENTUM_20 | -0.132% | -0.451%…0.183% | 48.750% | -0.054% | 55.150% | n/a |
| 5 | MEAN_REVERSION_5 | 0.011% | -0.340%…0.362% | 50.140% | 0.112% | 47.740% | n/a |
| 5 | SPY_REGIME | -0.339% | -0.898%…0.241% | 47.060% | -0.047% | 63.760% | n/a |
| 5 | LOGISTIC_V1 | 0.142% | -0.159%…0.452% | 51.000% | 0.089% | 74.630% | 0.51801 |
| 5 | HGB_V1 | 0.758% | 0.240%…1.259% | 55.120% | 0.204% | 60.100% | 0.555897 |

## Decision rule

A model advances only if its held-out result is consistently positive across horizons and improves on deterministic baselines without collapsing to one direction. No option-expression conclusion is inferred from this table.
