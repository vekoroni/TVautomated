# ============================================================================
# AVSHUNTER Enhanced Orchestrator - PowerShell Runner
# ============================================================================
# Runs the enhanced Python orchestrator with Crabel/Wyckoff features
#
# Usage:
#   .\run_enhanced_orchestrator.ps1
#   .\run_enhanced_orchestrator.ps1 -UniverseSize 1000
#   .\run_enhanced_orchestrator.ps1 -Verbose

param(
    [int]$UniverseSize = 1800,
    [switch]$Verbose = $false,
    [switch]$DryRun = $false
)

# Configuration
$ProjectRoot = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
$VenvPath = "$ProjectRoot\venv"
$PythonExe = "$VenvPath\Scripts\python.exe"
$OrchestratorScript = "$ProjectRoot\orchestrator_enhanced_complete.py"
$LogDir = "$ProjectRoot\logs"
$ReportsDir = "$ProjectRoot\reports"

# ============================================================================
# Pre-flight Checks
# ============================================================================

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "AVSHUNTER ENHANCED ORCHESTRATOR - PowerShell Runner" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Check if project directory exists
if (-not (Test-Path $ProjectRoot)) {
    Write-Host "[ERROR] Project directory not found: $ProjectRoot" -ForegroundColor Red
    Write-Host "Update `$ProjectRoot variable in this script" -ForegroundColor Yellow
    exit 1
}

Set-Location $ProjectRoot
Write-Host "[✓] Project directory: $ProjectRoot" -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path $VenvPath)) {
    Write-Host "[WARNING] Virtual environment not found: $VenvPath" -ForegroundColor Yellow
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    
    python -m venv venv
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[✓] Virtual environment created" -ForegroundColor Green
}

# Check if Python executable exists
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Python executable not found: $PythonExe" -ForegroundColor Red
    exit 1
}

Write-Host "[✓] Virtual environment: $VenvPath" -ForegroundColor Green

# Check if orchestrator script exists
if (-not (Test-Path $OrchestratorScript)) {
    Write-Host "[ERROR] Orchestrator script not found: $OrchestratorScript" -ForegroundColor Red
    Write-Host "Expected location: $OrchestratorScript" -ForegroundColor Yellow
    Write-Host "Did you copy orchestrator_enhanced_complete.py to the project root?" -ForegroundColor Yellow
    exit 1
}

Write-Host "[✓] Orchestrator script: $OrchestratorScript" -ForegroundColor Green

# Ensure directories exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "[✓] Created logs directory" -ForegroundColor Green
}

if (-not (Test-Path $ReportsDir)) {
    New-Item -ItemType Directory -Path $ReportsDir | Out-Null
    Write-Host "[✓] Created reports directory" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# Environment Setup
# ============================================================================

Write-Host "[SETUP] Activating virtual environment..." -ForegroundColor Cyan

# Activate virtual environment
$ActivateScript = "$VenvPath\Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
    Write-Host "[✓] Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Activate script not found, continuing..." -ForegroundColor Yellow
}

Write-Host ""

# ============================================================================
# Run Orchestrator
# ============================================================================

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\orchestrator_$Timestamp.log"

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "RUNNING ENHANCED ORCHESTRATOR" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Universe Size: $UniverseSize" -ForegroundColor White
Write-Host "Log File: $LogFile" -ForegroundColor White
Write-Host "Dry Run: $DryRun" -ForegroundColor White
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN] Would execute:" -ForegroundColor Yellow
    Write-Host "  $PythonExe $OrchestratorScript" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# Build Python command
$PythonArgs = @($OrchestratorScript)

# Execute orchestrator
Write-Host "[EXECUTING] Starting orchestrator..." -ForegroundColor Cyan
Write-Host ""

$StartTime = Get-Date

# Run Python orchestrator and capture output
if ($Verbose) {
    # Show all output in real-time
    & $PythonExe $PythonArgs 2>&1 | Tee-Object -FilePath $LogFile
} else {
    # Capture output to log, show summary only
    & $PythonExe $PythonArgs 2>&1 | Out-File -FilePath $LogFile
}

$ExitCode = $LASTEXITCODE
$EndTime = Get-Date
$Duration = $EndTime - $StartTime

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "ORCHESTRATOR COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

# ============================================================================
# Results Summary
# ============================================================================

if ($ExitCode -eq 0) {
    Write-Host "[✓] SUCCESS" -ForegroundColor Green
} else {
    Write-Host "[✗] FAILED with exit code: $ExitCode" -ForegroundColor Red
}

Write-Host "Duration: $($Duration.TotalSeconds) seconds" -ForegroundColor White
Write-Host "Log File: $LogFile" -ForegroundColor White

# Check for generated signals
$LatestSignals = Get-ChildItem $ReportsDir -Filter "signals_*.csv" | 
                 Sort-Object LastWriteTime -Descending | 
                 Select-Object -First 1

if ($LatestSignals) {
    Write-Host "Latest Signals: $($LatestSignals.FullName)" -ForegroundColor White
    
    # Count signals
    $SignalCount = (Import-Csv $LatestSignals.FullName).Count
    Write-Host "Signal Count: $SignalCount" -ForegroundColor $(if ($SignalCount -gt 0) { "Green" } else { "Yellow" })
    
    if ($SignalCount -gt 0) {
        Write-Host ""
        Write-Host "Top 5 Signals:" -ForegroundColor Cyan
        Import-Csv $LatestSignals.FullName | 
            Select-Object -First 5 ticker, pattern, grade, confidence, side |
            Format-Table -AutoSize
    }
} else {
    Write-Host "No signal files found in reports directory" -ForegroundColor Yellow
}

Write-Host ""

# Show tail of log if not verbose
if (-not $Verbose -and (Test-Path $LogFile)) {
    Write-Host "Last 20 lines of log:" -ForegroundColor Cyan
    Write-Host "-" * 80 -ForegroundColor Gray
    Get-Content $LogFile -Tail 20 | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
    Write-Host "-" * 80 -ForegroundColor Gray
    Write-Host ""
}

# ============================================================================
# Next Steps
# ============================================================================

if ($ExitCode -eq 0 -and $SignalCount -gt 0) {
    Write-Host "NEXT STEPS:" -ForegroundColor Cyan
    Write-Host "1. Review signals: $($LatestSignals.FullName)" -ForegroundColor White
    Write-Host "2. Apply options intelligence filters" -ForegroundColor White
    Write-Host "3. Pass to execution layer (v11.0)" -ForegroundColor White
    Write-Host ""
} elseif ($SignalCount -eq 0) {
    Write-Host "NO SIGNALS GENERATED" -ForegroundColor Yellow
    Write-Host "This may be normal depending on market regime" -ForegroundColor White
    Write-Host "Check log for regime detection: $LogFile" -ForegroundColor White
    Write-Host ""
}

# Exit with orchestrator's exit code
exit $ExitCode
