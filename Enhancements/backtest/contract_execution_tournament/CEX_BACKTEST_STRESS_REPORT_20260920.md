# CEX Contract and Execution Backtest/Stress Report — 2026-09-20

**State:** `EXPLORATORY_NO_AUTHORITY` — adaptive evidence, not production acceptance

| Trial | Status | Coverage | Ask→bid | Limit25* | Mid entry* | Spread+50 | Hit ≥25% |
|---|---|---:|---:|---:|---:|---:|---:|
| CEX-2-1.0|H1 | REJECTED_OR_INCONCLUSIVE | 90.5% | -32.9% | -29.4% | -24.7% | -41.7% | 3.0% |
| CEX-2-0.5|H1 | REJECTED_OR_INCONCLUSIVE | 98.1% | -33.6% | -30.0% | -25.2% | -42.6% | 3.1% |
| CEX-2-0.25|H1 | REJECTED_OR_INCONCLUSIVE | 99.4% | -33.9% | -30.3% | -25.5% | -43.0% | 3.1% |
| CEX-1|H1 | REJECTED_OR_INCONCLUSIVE | 99.5% | -34.0% | -30.4% | -25.6% | -43.1% | 3.1% |
| CEX-3|H1 | REJECTED_OR_INCONCLUSIVE | 99.5% | -34.2% | -30.5% | -25.7% | -43.4% | 3.6% |
| CEX-2-1.0|H5 | REJECTED_OR_INCONCLUSIVE | 91.4% | -35.0% | -31.5% | -26.9% | -43.6% | 7.5% |
| CEX-7|H5 | REJECTED_OR_INCONCLUSIVE | 100.0% | -35.3% | -31.8% | -27.5% | -44.0% | 7.8% |
| CEX-1|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -35.3% | -31.7% | -27.0% | -44.1% | 7.9% |
| CEX-2-0.25|H5 | REJECTED_OR_INCONCLUSIVE | 98.0% | -35.4% | -31.7% | -27.0% | -44.1% | 7.9% |
| CEX-3|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -35.4% | -31.8% | -27.0% | -44.2% | 7.9% |
| CEX-2-0.5|H5 | REJECTED_OR_INCONCLUSIVE | 97.3% | -35.5% | -32.0% | -27.4% | -44.2% | 7.8% |
| CEX-5|H1 | REJECTED_OR_INCONCLUSIVE | 99.6% | -35.9% | -31.9% | -26.7% | -45.7% | 4.0% |
| CEX-4|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -36.0% | -32.3% | -27.5% | -44.8% | 8.0% |
| CEX-5|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -36.5% | -32.8% | -28.0% | -45.4% | 8.0% |
| CEX-6-M05|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -36.6% | -32.9% | -28.1% | -45.6% | 8.1% |
| CEX-4|H1 | REJECTED_OR_INCONCLUSIVE | 99.6% | -36.9% | -32.8% | -27.4% | -47.0% | 4.3% |
| CEX-2-1.0|H3 | REJECTED_OR_INCONCLUSIVE | 90.4% | -37.3% | -34.1% | -30.0% | -45.7% | 6.1% |
| CEX-6-M10|H5 | REJECTED_OR_INCONCLUSIVE | 98.1% | -37.3% | -33.4% | -28.4% | -46.5% | 8.1% |
| CEX-7|H1 | REJECTED_OR_INCONCLUSIVE | 100.0% | -37.4% | -33.4% | -28.3% | -47.4% | 4.5% |
| CEX-6-M05|H1 | REJECTED_OR_INCONCLUSIVE | 99.6% | -37.6% | -33.4% | -27.8% | -47.9% | 4.3% |
| CEX-2-0.5|H3 | REJECTED_OR_INCONCLUSIVE | 97.9% | -38.1% | -34.8% | -30.6% | -46.8% | 6.1% |
| CEX-6-M10|H1 | REJECTED_OR_INCONCLUSIVE | 99.6% | -38.3% | -33.9% | -28.2% | -48.8% | 4.2% |
| CEX-2-0.25|H3 | REJECTED_OR_INCONCLUSIVE | 99.1% | -38.4% | -35.2% | -30.9% | -47.1% | 6.2% |
| CEX-1|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -38.5% | -35.3% | -31.1% | -47.2% | 6.2% |
| CEX-3|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -38.8% | -35.6% | -31.3% | -47.6% | 6.8% |
| CEX-7|H3 | REJECTED_OR_INCONCLUSIVE | 100.0% | -40.3% | -36.8% | -32.4% | -49.7% | 7.4% |
| CEX-4|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -41.1% | -37.5% | -32.8% | -50.6% | 7.6% |
| CEX-0|H1 | REJECTED_OR_INCONCLUSIVE | 97.6% | -41.2% | -36.3% | -30.0% | -52.2% | 3.9% |
| CEX-5|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -41.4% | -37.7% | -32.9% | -51.0% | 7.3% |
| CEX-0|H5 | REJECTED_OR_INCONCLUSIVE | 92.0% | -41.9% | -37.4% | -31.5% | -52.0% | 7.1% |
| CEX-6-M05|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -42.1% | -38.3% | -33.5% | -51.8% | 7.6% |
| CEX-6-M10|H3 | REJECTED_OR_INCONCLUSIVE | 99.4% | -43.0% | -39.1% | -34.1% | -52.8% | 7.4% |
| CEX-0|H3 | REJECTED_OR_INCONCLUSIVE | 96.8% | -46.0% | -41.7% | -36.0% | -56.4% | 7.0% |

*Conditional on a hypothetical limit fill; not evidence that the order would have filled.*

## Governance conclusion

A result is only a replication candidate when executable ask-to-bid and 50%-wider-spread means are positive with session-level consistency. Tickers without a qualifying contract remain monitored; they are not invalidated.
