# Stage 3 -- daily coverage for the research-relevant core (built 19 Sep 2026).
# 1,671 tickers: the union of every ticker that appeared as a Discovery candidate across the last 8 archived
# runs. This is the population the Intelligence Audit / IV-LAG family (SCENARIO_REGISTER_20260919.md) and near-
# term live candidates actually need at daily resolution -- the other ~1,647 tickers in the full liquid universe
# have not been candidates recently and are deferred to Stage 4 (low priority, no measured value yet).
# All 5 weekdays x 1 year. ~350,000 credits, ~4 runs at the capped rate below, spread across weekends.
# Re-running is always safe: already-captured pairs are skipped for free.
$ErrorActionPreference = 'Continue'
$universe = 'Enhancements\research\legacy_signals\_stage3_core_universe.csv'
$cap = 18000
for ($weekday = 0; $weekday -le 4; $weekday++) {
    Write-Host "=== weekday $weekday ($(('Mon','Tue','Wed','Thu','Fri')[$weekday])) ==="
    venv\Scripts\python.exe scripts\run_phantom_backfill_parallel.py `
        --universe-path $universe --years 1 --weekday $weekday --credit-cap $cap --execute
}
