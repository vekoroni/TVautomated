# PowerShell script to update discovery config for 40-bar data

# Create backup of existing config (if it exists)
if (Test-Path "config\discovery_config.json") {
    Write-Host "Backing up existing config..." -ForegroundColor Yellow
    Copy-Item "config\discovery_config.json" "config\discovery_config_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
}

# Create the optimized 40-bar config
$config = @{
    min_price = 5.0
    max_price = 500.0
    min_avg_volume_20 = 500000
    min_atr_pct_14 = 1.5
    min_rel_vol_1d = 1.2
    compression_max = 0.85
    extreme_compression = 0.6
    wyckoff_combo_min = 60.0
    wyckoff_only_min = 65.0
    wyckoff_only_grade_required = $true
    crabel_weight = 0.3
    wyckoff_weight = 0.5
    macro_weight = 0.2
    min_composite = 55.0
    use_macro_filter = $true
    block_risk_off = $true
    require_futures_align = $false
    macro_boost_aligned = 10.0
    min_bars = 30
    scan_bars = 40
    wyckoff_bars = 35
    macro_report_path = "data/daily/macro_intelligence_report.json"
    out_dir = "data/output"
}

# Ensure config directory exists
if (-not (Test-Path "config")) {
    New-Item -ItemType Directory -Path "config" | Out-Null
}

# Write config to file
$config | ConvertTo-Json -Depth 10 | Set-Content "config\discovery_config.json"

Write-Host "✅ Config updated successfully!" -ForegroundColor Green
Write-Host "   min_bars: 30 (was 60)" -ForegroundColor Cyan
Write-Host "   scan_bars: 40 (was 200)" -ForegroundColor Cyan
Write-Host "   wyckoff_bars: 35 (was 120)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Now run: python avshunter_discovery_scan_v2_0.py" -ForegroundColor Yellow
