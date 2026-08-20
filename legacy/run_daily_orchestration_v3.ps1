# AVSHUNTER DAILY ORCHESTRATION SCRIPT v3.0 HYBRID (Windows PowerShell)
##############################################################################
# Purpose: Automated workflow for hybrid early-position + fast-execution system
#
# Schedule:
#   4:15 PM Daily - Run discovery + position lifecycle tracking
#   8:00 AM Daily - Run premarket intelligence
#
# Usage (PowerShell):
#   .\run_daily_orchestration_v3.ps1 evening
#   .\run_daily_orchestration_v3.ps1 premarket
#   .\run_daily_orchestration_v3.ps1 full
##############################################################################

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('evening','premarket','full','help')]
    [string]$Command
)

# Configuration
$PYTHON_CMD = "python"
$LOG_DIR = "data\logs"
$OUTPUT_DIR = "data\output"

# Create directories
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

# Color functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Timestamp
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

##############################################################################
# FUNCTION: Evening Workflow (4:15 PM)
##############################################################################
function Run-EveningWorkflow {
    Write-Info "=========================================="
    Write-Info "AVSHUNTER v3.0 HYBRID - EVENING WORKFLOW"
    Write-Info "Time: $(Get-Date)"
    Write-Info "=========================================="
    
    # Step 1: Discovery Scanner (Hybrid)
    Write-Info ""
    Write-Info "STEP 1: Running Hybrid Discovery Scanner..."
    Write-Info "------------------------------------------"
    Write-Info "Detecting: EARLY_POSITION + CONFIRMED_ENTRY + GRADUATED"
    
    try {
        & $PYTHON_CMD avshunter_discovery_v3_HYBRID.py `
            --log_level INFO `
            --progress-every 100 `
            2>&1 | Tee-Object -FilePath "$LOG_DIR\discovery_$TIMESTAMP.log"
        
        Write-Success "Discovery scan complete"
    }
    catch {
        Write-Error-Custom "Discovery scan failed!"
        Write-Error-Custom $_.Exception.Message
        exit 1
    }
    
    # Step 2: Position Lifecycle Tracker
    Write-Info ""
    Write-Info "STEP 2: Running Position Lifecycle Tracker..."
    Write-Info "------------------------------------------"
    Write-Info "Tracking: Active â†’ Add â†’ Exit progression"
    
    try {
        & $PYTHON_CMD position_lifecycle_tracker.py `
            2>&1 | Tee-Object -FilePath "$LOG_DIR\lifecycle_$TIMESTAMP.log"
        
        Write-Success "Position tracking complete"
    }
    catch {
        Write-Warning "Position tracking failed (may be first run)"
    }
    
    # Summary
    Write-Info ""
    Write-Info "=========================================="
    Write-Info "EVENING WORKFLOW COMPLETE"
    Write-Info "=========================================="
    
    # Count outputs
    $EARLY_FILE = Get-ChildItem -Path "$OUTPUT_DIR\early_position_candidates_*.csv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $CONFIRMED_FILE = Get-ChildItem -Path "$OUTPUT_DIR\confirmed_entry_signals_*.csv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $GRADUATED_FILE = Get-ChildItem -Path "$OUTPUT_DIR\graduated_positions_*.csv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $ACTIVE_FILE = Get-ChildItem -Path "$OUTPUT_DIR\active_positions_*.csv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    
    $EARLY_COUNT = if ($EARLY_FILE) { (Import-Csv $EARLY_FILE.FullName).Count } else { 0 }
    $CONFIRMED_COUNT = if ($CONFIRMED_FILE) { (Import-Csv $CONFIRMED_FILE.FullName).Count } else { 0 }
    $GRADUATED_COUNT = if ($GRADUATED_FILE) { (Import-Csv $GRADUATED_FILE.FullName).Count } else { 0 }
    $ACTIVE_COUNT = if ($ACTIVE_FILE) { (Import-Csv $ACTIVE_FILE.FullName).Count } else { 0 }
    
    Write-Info "Signals Generated:"
    Write-Info "  ðŸ‘€ EARLY_POSITION: $EARLY_COUNT (33% positions)"
    Write-Info "  ðŸš¨ CONFIRMED_ENTRY: $CONFIRMED_COUNT (100% positions)"
    Write-Info "  ðŸŽ“ GRADUATED: $GRADUATED_COUNT (early â†’ confirmed WINS!)"
    Write-Info "  ðŸ“Š ACTIVE TRACKING: $ACTIVE_COUNT positions"
    Write-Info ""
    Write-Info "Next: Run premarket workflow at 8:00 AM tomorrow"
    Write-Info "  .\run_daily_orchestration_v3.ps1 premarket"
    Write-Info "=========================================="
}

##############################################################################
# FUNCTION: Premarket Workflow (8:00 AM)
##############################################################################
function Run-PremarketWorkflow {
    Write-Info "=========================================="
    Write-Info "AVSHUNTER v3.0 HYBRID - PREMARKET WORKFLOW"
    Write-Info "Time: $(Get-Date)"
    Write-Info "=========================================="
    
    # Step 3: Premarket Intelligence
    Write-Info ""
    Write-Info "STEP 3: Generating Premarket Action List..."
    Write-Info "------------------------------------------"
    Write-Info "Prioritizing: EXIT â†’ ADD â†’ ENTER â†’ MONITOR"
    
    try {
        & $PYTHON_CMD premarket_intelligence_v3_HYBRID.py `
            --top 20 `
            2>&1 | Tee-Object -FilePath "$LOG_DIR\premarket_$TIMESTAMP.log"
        
        Write-Success "Premarket intelligence complete"
    }
    catch {
        Write-Error-Custom "Premarket intelligence failed!"
        Write-Error-Custom "Check that evening workflow ran successfully"
        Write-Error-Custom $_.Exception.Message
        exit 1
    }
    
    # Summary
    Write-Info ""
    Write-Info "=========================================="
    Write-Info "PREMARKET WORKFLOW COMPLETE"
    Write-Info "=========================================="
    
    # Find latest action list
    $LATEST_ACTIONS = Get-ChildItem -Path "$OUTPUT_DIR\premarket_actions_*.csv" -ErrorAction SilentlyContinue | 
                      Sort-Object LastWriteTime -Descending | 
                      Select-Object -First 1
    
    if ($LATEST_ACTIONS) {
        $ACTIONS_COUNT = (Import-Csv $LATEST_ACTIONS.FullName).Count
        
        Write-Info "Today's Actions: $ACTIONS_COUNT opportunities"
        Write-Info "File: $($LATEST_ACTIONS.Name)"
        Write-Info ""
        Write-Info "Priority Order:"
        Write-Info "  1. EXIT positions (target/time/fizzle)"
        Write-Info "  2. ADD to graduated (early entry wins!)"
        Write-Info "  3. ENTER confirmed setups (high probability)"
        Write-Info "  4. ENTER early positions (better price)"
        Write-Info "  5. MONITOR existing early positions"
    }
    else {
        Write-Warning "No action list generated"
    }
    
    Write-Info "=========================================="
}

##############################################################################
# FUNCTION: Full Workflow (Testing)
##############################################################################
function Run-FullWorkflow {
    Write-Info "=========================================="
    Write-Info "FULL WORKFLOW (TESTING)"
    Write-Info "=========================================="
    
    Run-EveningWorkflow
    
    Write-Info ""
    Write-Info "Waiting 3 seconds before premarket..."
    Start-Sleep -Seconds 3
    
    Run-PremarketWorkflow
    
    Write-Success "Full workflow complete!"
}

##############################################################################
# FUNCTION: Show Help
##############################################################################
function Show-Help {
    @"
AVSHUNTER Daily Orchestration Script v3.0 HYBRID (Windows)

HYBRID SYSTEM: Early Position (33%) + Confirmed Entry (100%) + Fast Execution (1-15 days)

Usage:
  .\run_daily_orchestration_v3.ps1 <command>

Commands:
  evening     Run evening workflow (4:15 PM)
              - Hybrid discovery (early + confirmed + graduated)
              - Position lifecycle tracking

  premarket   Run premarket workflow (8:00 AM)
              - Generate prioritized action list
              - EXIT â†’ ADD â†’ ENTER â†’ MONITOR

  full        Run complete workflow (testing)
              - Runs both evening and premarket

  help        Show this help message

Examples:
  .\run_daily_orchestration_v3.ps1 evening
  .\run_daily_orchestration_v3.ps1 premarket

Scheduling (Windows Task Scheduler):
  1. Open Task Scheduler
  2. Create Basic Task
  3. Name: AVSHUNTER v3.0 Evening
  4. Trigger: Daily at 4:15 PM
  5. Action: Start a program
     - Program: powershell.exe
     - Arguments: -File "C:\path\to\run_daily_orchestration_v3.ps1" evening
     - Start in: C:\path\to\avshunter

  Repeat for Premarket (8:00 AM)

Logs:
  Saved to: data\logs\

"@
}

##############################################################################
# MAIN
##############################################################################
switch ($Command) {
    'evening' {
        Run-EveningWorkflow
    }
    'premarket' {
        Run-PremarketWorkflow
    }
    'full' {
        Run-FullWorkflow
    }
    'help' {
        Show-Help
    }
}
