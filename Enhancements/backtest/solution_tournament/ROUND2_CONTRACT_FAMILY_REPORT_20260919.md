# AVSHUNTER solution tournament — Round 2 contract-family result

**State:** Exploratory research only. No production code, authority, configuration, or database was changed.

## Executable results excluding explicit test/dirty runs

| Horizon | Rule | Selected / opportunities | Ask→bid mean | Mid→mid mean | Hit rate | +100% oracle recall |
|---:|---|---:|---:|---:|---:|---:|
| 1 | F0_RECORDED | 7259/7808 | -40.74% | 0.99% | 10.99% | 51.72% |
| 1 | F1_TIGHTEST_SPREAD | 7495/7808 | -24.53% | 0.39% | 13.68% | 24.14% |
| 1 | F2_NEAR_MONEY | 2122/7808 | -11.73% | 0.50% | 26.04% | 10.34% |
| 1 | F3_DELTA_CORE | 2313/7808 | -11.31% | 0.46% | 26.51% | 24.14% |
| 1 | F4_VALUE_COMPOSITE | 3611/7808 | -12.26% | 0.49% | 23.38% | 20.69% |
| 1 | F5_CONVEX_SATELLITE | 0/7808 | n/a | n/a | n/a | 0.00% |
| 3 | F0_RECORDED | 6093/6642 | -43.14% | -1.68% | 15.01% | 63.64% |
| 3 | F1_TIGHTEST_SPREAD | 6335/6642 | -28.10% | -2.28% | 17.76% | 30.68% |
| 3 | F2_NEAR_MONEY | 1783/6642 | -16.21% | -3.59% | 28.53% | 19.32% |
| 3 | F3_DELTA_CORE | 1953/6642 | -16.02% | -3.79% | 29.03% | 26.14% |
| 3 | F4_VALUE_COMPOSITE | 3014/6642 | -16.08% | -2.85% | 27.56% | 28.41% |
| 3 | F5_CONVEX_SATELLITE | 0/6642 | n/a | n/a | n/a | 0.00% |
| 5 | F0_RECORDED | 4990/5539 | -47.82% | -7.45% | 14.96% | 68.81% |
| 5 | F1_TIGHTEST_SPREAD | 5237/5539 | -31.39% | -5.54% | 18.82% | 35.78% |
| 5 | F2_NEAR_MONEY | 1403/5539 | -17.61% | -5.46% | 28.09% | 21.10% |
| 5 | F3_DELTA_CORE | 1534/5539 | -16.98% | -5.25% | 28.85% | 27.52% |
| 5 | F4_VALUE_COMPOSITE | 2366/5539 | -17.58% | -4.73% | 27.52% | 32.11% |
| 5 | F5_CONVEX_SATELLITE | 0/5539 | n/a | n/a | n/a | 0.00% |

## Interpretation rules

- The oracle is an upper bound using future knowledge and cannot be traded.
- A low recall rate means the rule discarded right-tail contracts even if its mean improved.
- No apparent winner is eligible for production until repeated on a larger certified history and held-out sessions.
