# AVSHUNTER Solution Tournament — Round 1 validation

**State:** Exploratory research only. No production rule, authority, configuration, or database was changed.

## Question tested

Does the weak selected-contract result arise mainly from direction, from contract repricing, or from bid/ask friction? The same frozen candidates are measured ask-to-bid and mid-to-mid, then rechecked after excluding explicit test/dirty runs and on the small certified-run subset.

## Evidence integrity

- Frozen panel: `round1_panel.csv` (`22,273` horizon observations; SHA-256 `abcb5a1efd6f87fd4eb1de99d2a12a98a075898b775a6d6332e76e735eb06e05`).
- Candidate population: 9 sessions, 1,556 tickers.
- Certified sensitivity: 2 sessions across 2 runs. This is diagnostic, not inferential.
- Session-block bootstrap is used so thousands of correlated ticker rows are not mistaken for thousands of independent trials.

## Paired result

| Horizon | Current direction | Option ask→bid | Option mid→mid | Mean spread drag | ≤5% spread ask→bid |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.01% | -40.63% | -1.30% | 36.99% | -5.72% |
| 3 | -0.24% | -43.66% | -5.33% | 36.21% | -14.64% |
| 5 | -0.42% | -48.50% | -10.10% | 36.07% | -22.58% |

The spread drag is reported as `mid-to-mid minus ask-to-bid`; it measures how much quoted entry/exit friction worsens the selected contract result. It is not a promise that midpoint fills were achievable.

## Finding

1. **Execution friction is a first-order defect.** Tight-spread filtering materially improves the selected-contract return, and the paired mid-price comparison quantifies the portion attributable to quotes.
2. **Friction is not the whole defect.** The current direction signal is negative over three and five sessions in this sample, and mid-to-mid contract performance remains weak. A spread-only production fix would therefore be incomplete.
3. **The sample is not promotion-grade.** Only two sessions meet the current certified normal-completed-run standard. The older rows remain useful for failure localisation but cannot establish live expectancy.
4. **No tested route is accepted yet.** The least-bad alternatives are hypotheses for the next tournament round, not new pipeline authority.

## Decision

Do not build a production selector from Round 1. Advance to Round 2 with full contract-family re-selection, explicit no-quote exclusion, and opportunity-recall for large winners. In parallel, create a larger point-in-time candidate history from certified runs so direction and pricing models can be assessed independently.

## Round 2 tests

- Re-select every eligible contract in the same ticker/side/expiry family using only information available at the candidate timestamp.
- Compare executable-now, developing-liquidity, and no-quote states without discarding the ticker thesis.
- Attribute each loss to direction, IV repricing, theta, spread, or contract geometry.
- Measure whether the selector retained the contracts that later delivered +50%, +100%, +200%, and +500% returns.
- Compare the current signal with momentum, mean-reversion, and regime-conditioned alternatives on clean out-of-sample sessions.
