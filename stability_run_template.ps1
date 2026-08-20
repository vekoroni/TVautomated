# AVSHUNTER Stability Runner (Run-dir atomic)
$run_id = (Get-Date).ToString("yyyyMMdd_HHmmss")
$run_dir = "data\output\runs\$run_id"

Write-Host "RUN_ID: $run_id"
Write-Host "RUN_DIR: $run_dir"

# 0) Refresh daily data first
python refresh_daily_data.py

# 1) Orchestrator
python intelligent_orchestrator.py --evening --run-id $run_id

# 2) Build packages
python scripts\build_packages_from_discovery.py --run-id $run_id

# 3) Inject macro
python scripts\inject_macro_into_packages.py --run-id $run_id

# 4) Backfill timeseries
python scripts\backfill_timeseries_into_packages.py --run-id $run_id

# 5) Validate packages (fail closed)
python scripts\validate_packages.py --packages_dir "$run_dir\packages" --fail_on_any

# 6) Run Vanguard
python scripts\run_vanguard_from_packages.py --run-id $run_id

# 7) Write manifest
python scripts\write_manifest.py --run_dir $run_dir --universe_in data\universe\hybrid_universe_enhanced.csv
