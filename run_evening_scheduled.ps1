# AVSHUNTER — scheduled wrapper for the evening prep step (EOD_PREP).
# Calls intelligent_orchestrator.py --evening directly with the repo's
# venv Python, the same way ACK runs it by hand in PowerShell — no
# .bat wrapper, no extra env vars (confirmed 22-Sep-2026: not needed).

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "logs\scheduled"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("evening_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

Start-Transcript -Path $logFile -Append | Out-Null

try {
    if (-not (Test-Path $venvPython)) {
        Write-Error "[ERROR] venv Python not found at $venvPython"
        exit 2
    }

    Set-Location $repoRoot
    & $venvPython (Join-Path $repoRoot "intelligent_orchestrator.py") --evening
    $result = $LASTEXITCODE
    if ($result -ne 0) {
        Write-Host "[FAILED] Evening workflow exited with code $result"
    } else {
        Write-Host "[COMPLETE] Evening workflow finished successfully"
    }
    exit $result
} finally {
    Stop-Transcript | Out-Null
}
