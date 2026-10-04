# S-ACT Backtest and Stress Test Report — 2026-09-20

**State:** EXPLORATORY_NO_AUTHORITY — no production authority

## Scope

- Recorded direction and contract only: `D0_CURRENT|E0_RECORDED`.
- 19,989 horizon rows; 7,808 candidates; 8 sessions.
- Explicit TEST/dirty runs excluded.
- Target: option ask-to-bid return of at least 25%; top-quintile ranking evaluated out of sample by session.
- PCR remains unsigned positioning/activity evidence. No buyer/seller direction is inferred.

## Highest purged walk-forward screening results

| Trial | Status | AUC | Selected mean | Baseline mean | Session delta | t |
|---|---:|---:|---:|---:|---:|---:|
| S-ACT-9|H1|F50|STALE_OI_PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.740 | -0.209 | -0.412 | 0.201 | 9.48 |
| S-ACT-9|H1|F50|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.740 | -0.213 | -0.412 | 0.197 | 8.11 |
| S-ACT-9|H1|F10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.738 | -0.214 | -0.412 | 0.197 | 6.98 |
| S-ACT-9|H1|F1|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.728 | -0.221 | -0.412 | 0.191 | 8.30 |
| S-ACT-9|H1|F50|VOLUME_DROPOUT_10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.710 | -0.226 | -0.412 | 0.184 | 7.64 |
| S-ACT-9|H1|F50|VOLUME_DROPOUT_25|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.693 | -0.233 | -0.412 | 0.177 | 7.63 |
| S-ACT-5|H1|F50|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.722 | -0.235 | -0.412 | 0.175 | 7.93 |
| S-ACT-4|H1|F50|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.721 | -0.237 | -0.412 | 0.174 | 8.95 |
| S-ACT-7|H1|F50|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.715 | -0.238 | -0.412 | 0.174 | 6.46 |
| S-ACT-7|H1|F10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.715 | -0.245 | -0.412 | 0.167 | 6.15 |
| S-ACT-6|H1|F10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.715 | -0.244 | -0.412 | 0.166 | 6.70 |
| S-ACT-4|H1|F50|VOLUME_DROPOUT_10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.693 | -0.248 | -0.412 | 0.164 | 9.88 |
| S-ACT-6|H1|F50|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.717 | -0.246 | -0.412 | 0.163 | 6.37 |
| S-ACT-7|H1|F1|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.708 | -0.249 | -0.412 | 0.163 | 6.43 |
| S-ACT-4|H1|F50|STALE_OI_PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.717 | -0.249 | -0.412 | 0.162 | 10.28 |
| S-ACT-6|H1|F1|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.699 | -0.249 | -0.412 | 0.162 | 8.08 |
| S-ACT-4|H1|F50|VOLUME_DROPOUT_25|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.670 | -0.253 | -0.412 | 0.157 | 6.93 |
| S-ACT-4|H1|F10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.718 | -0.257 | -0.412 | 0.156 | 9.70 |
| S-ACT-5|H1|F10|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.704 | -0.254 | -0.412 | 0.155 | 7.05 |
| S-ACT-4|H1|F1|PURGED_WALK_FORWARD | RELATIVE_IMPROVEMENT_ONLY | 0.707 | -0.271 | -0.412 | 0.141 | 11.27 |

## Interpretation controls

- A relative screening improvement is not a monetisation result or a production promotion.
- The configurations share only eight source sessions and are not independent trials; PBO/deflated-Sharpe reliability cannot be claimed from configuration count.
- The primary temporal test is purged walk-forward: every training outcome ends before its test session begins.
- S-ACT-8 is deliberately not scored at the original entry time because next-session OI is future information.
- Results must be judged across denominator floors, stale-OI stress, spread widening, quote dropout, and market regimes.
- Any surviving alternative advances to the thesis-conditioned entry/path tournament; it does not change the current pipeline by itself.

## Causal decomposition

### S-ACT-9|H1|F50|PURGED_WALK_FORWARD

- Ask-to-bid mean: -21.3%; mid-to-mid mean: 1.9%.
- Mean quote-friction gap: 23.2%; median entry spread: 20.2%.
- Directional underlying positive: 49.9%.
- Mid-price gain but executable ask-to-bid loss: 21.6%.
- Direction right but executable ask-to-bid loss: 26.2%.

### S-ACT-9|H3|F50|PURGED_WALK_FORWARD

- Ask-to-bid mean: -32.8%; mid-to-mid mean: -8.3%.
- Mean quote-friction gap: 24.5%; median entry spread: 21.2%.
- Directional underlying positive: 42.0%.
- Mid-price gain but executable ask-to-bid loss: 13.2%.
- Direction right but executable ask-to-bid loss: 19.3%.

### S-ACT-6|H1|F50|PURGED_WALK_FORWARD

- Ask-to-bid mean: -24.6%; mid-to-mid mean: 2.3%.
- Mean quote-friction gap: 27.0%; median entry spread: 22.8%.
- Directional underlying positive: 52.2%.
- Mid-price gain but executable ask-to-bid loss: 23.6%.
- Direction right but executable ask-to-bid loss: 30.6%.

## Research conclusion

- Activity context contains relative ranking information, with printed volume and local expiry/moneyness structure stronger than delta-weighted OI alone.
- It does not solve monetisation by itself: every primary top-quintile alternative remains negative on executable ask-to-bid returns.
- The next registered test must combine activity evidence with contract-family choice, spread/limit-entry feasibility, and liquidity maturation while preserving the ticker thesis for human review.
