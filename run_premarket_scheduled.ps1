# AVSHUNTER — scheduled wrapper for the morning validation step.
# Reads data\output\latest.json for the current run_id, then calls
# run_premarket.bat --run-id <run_id>, which runs
# intelligent_orchestrator.py --morning --run-id <run_id> with the
# same venv/env-var handling as running it by hand.
#
# Added 22-Sep-2026 so Windows Task Scheduler can run the morning step
# unattended, chained to whatever the evening step's run_id was.

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$latestPath = Join-Path $repoRoot "data\output\latest.json"
$logDir = Join-Path $repoRoot "logs\scheduled"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("premarket_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

Start-Transcript -Path $logFile -Append | Out-Null

try {
    if (-not (Test-Path $latestPath)) {
        Write-Error "[ERROR] $latestPath not found — has the evening (--evening) step run yet today?"
        exit 2
    }

    $latest = Get-Content $latestPath -Raw | ConvertFrom-Json
    $runId = $latest.run_id

    if ([string]::IsNullOrWhiteSpace($runId)) {
        Write-Error "[ERROR] run_id was empty/missing in $latestPath"
        exit 2
    }

    Write-Host "[INFO] Using run_id=$runId from $latestPath"
    & (Join-Path $repoRoot "run_premarket.bat") --run-id $runId
    $result = $LASTEXITCODE
    if ($result -ne 0) {
        Write-Host "[FAILED] run_premarket.bat exited with code $result"
    } else {
        Write-Host "[COMPLETE] Morning validation finished successfully (run_id=$runId)"
    }
    exit $result
} finally {
    Stop-Transcript | Out-Null
}
