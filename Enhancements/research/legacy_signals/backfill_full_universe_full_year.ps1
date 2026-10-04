# Full-universe, full-year daily option-chain backfill (built 19 Sep 2026 for ACK, replaces the narrower
# 760-ticker targeted backfill for research purposes -- that one stays useful for re-scoring the 1,786 legacy
# recommendations; this one exists to give the Intelligence Audit / IV-LAG research (Enhancements/backtest/
# SCENARIO_REGISTER_20260919.md) a genuine daily, unbiased series across the whole market, not just Fridays.
#
# SCOPE
#   Universe : data\universe\polygon_liquid_universe.csv (3,320 tickers -- the broadest list in the repo;
#              this is a research backfill, not a live-run universe change, so no pipeline behaviour is affected).
#   Range    : trailing 1 year from whenever each line is run (run_phantom_backfill_parallel.py applies its
#              own 7-day provider-availability safety lag; no fixed end date, so this script stays correct
#              however many times it is re-run).
#   Days     : all five weekdays (0=Mon .. 4=Fri). Phantom already holds ~1 year of FRIDAY (weekday 4) chains
#              for most of this universe (the weekly snapshots the IV catch-up used on 19 Sep); those pairs are
#              skipped automatically (query_key dedup against backfill_audit) and cost nothing to re-request.
#              Mon-Thu are the real gap this fills.
#
# COST (measured ~1 credit per ticker-session, scripts\backfill_audit)
#   New (Mon-Thu) ticker-sessions : ~4 x 3,320 x ~52 weeks       ~= 690,000 credits
#   Friday gap-fill (new/relisted tickers only; most are skipped) ~= 20,000-35,000 credits
#   TOTAL ESTIMATE                                                ~= 700,000-725,000 credits
#   (No $-per-credit figure is recorded in this repo; this is a credit count only.)
#
# THIS IS NOT A ONE-SITTING JOB. Each line below is capped at 18,000 credits (5 lines x 18,000 = 90,000/day,
# safely under the governed market_data.daily_credit_budget of 100,000 even if every line runs back-to-back).
# At that pace the full backfill needs roughly EIGHT runs of this script (720,000 / 90,000 ~= 8) spread across
# weekends -- never on a day a pipeline (evening/morning) is running, per standing instruction. Re-running this
# same script is always safe: already-captured ticker-date pairs are skipped for free, so each run simply
# continues where the last one stopped. Preview any line without spending credits by dropping ' --execute'.
# When repeated runs stop reporting new credits spent, the backfill is complete.

$ErrorActionPreference = 'Continue'
$universe = 'data\universe\polygon_liquid_universe.csv'
$cap = 18000

for ($weekday = 0; $weekday -le 4; $weekday++) {
    Write-Host "=== weekday $weekday ($(('Mon','Tue','Wed','Thu','Fri')[$weekday])) ==="
    venv\Scripts\python.exe scripts\run_phantom_backfill_parallel.py `
        --universe-path $universe `
        --years 1 `
        --weekday $weekday `
        --credit-cap $cap `
        --execute
}
