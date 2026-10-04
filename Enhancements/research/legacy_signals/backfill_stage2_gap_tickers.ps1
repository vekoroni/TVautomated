# Stage 2 -- close the remaining live-pipeline IV gap (built 19 Sep 2026).
# 53 tickers still under the 20-sample floor F2's true IV percentile needs (median for the rest is already 60).
# Daily, 1 year, this small list only. Estimated ~13,000-14,000 credits, one sitting, well under any daily cap.
$ErrorActionPreference = 'Continue'
$tickers = Get-Content 'Enhancements\research\legacy_signals\_stage2_gap_tickers.txt'
for ($weekday = 0; $weekday -le 4; $weekday++) {
    venv\Scripts\python.exe scripts\run_phantom_backfill_parallel.py `
        --tickers $tickers --years 1 --weekday $weekday --credit-cap 5000 --execute
}
