# AVSHUNTER Stability Runner (Run-dir atomic)
# Run from repo root: AVSHUNTER-Intelligence

$run_id = (Get-Date).ToString("yyyyMMdd_HHmmss")
$run_dir = "data\output\runs\$run_id"

Write-Host "RUN_ID: $run_id"
Write-Host "RUN_DIR: $run_dir"

# 0) Create run skeleton + pin latest.json
python intelligent_orchestrator.py --evening --run-id $run_id

# 1) Build packages from run-scoped discovery outputs (macro_snapshot.json must exist in run_dir)
python scripts\build_packages_from_discovery.py --run-id $run_id

# 2) Validate packages (fail-closed) - adjust path if you place validator elsewhere
python scripts\validate_packages.py --packages_dir "$run_dir\packages" --fail_on_any

# 3) Run Vanguard from packages
python scripts\run_vanguard_from_packages.py --run-id $run_id

# 4) Write manifest (optional)
python scripts\write_manifest.py --run_dir $run_dir --universe_in data\universe\hybrid_universe_enhanced.csv
