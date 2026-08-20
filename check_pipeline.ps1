$log = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\logs\orchestrator.log"

if (-not (Test-Path $log)) {
    Write-Host "orchestrator.log not found - run the evening pipeline first" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "---------------------------------------------------" -ForegroundColor Cyan
Write-Host "  AVSHUNTER PIPELINE HEALTH CHECK" -ForegroundColor Cyan
Write-Host "---------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

@("Phase 4.6","Phase 8.5","Phase 9.5","Phase 9B","Phase 9C","Phase 10","latest.json","EDE","Actuarial Cache") | ForEach-Object {
    $match = Get-Content $log | Select-String $_ | Select-Object -Last 1
    if ($match) {
        Write-Host "  OK  $_ : $($match.Line.Trim())" -ForegroundColor Green
    } else {
        Write-Host "  MISSING  $_ : NOT FOUND IN LOG" -ForegroundColor Red
    }
}

Write-Host ""

$latest = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\latest.json"
if (Test-Path $latest) {
    $run = [System.IO.File]::ReadAllText($latest) | ConvertFrom-Json
    Write-Host "  Latest run : $($run.run_id)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "---------------------------------------------------" -ForegroundColor Cyan
Write-Host ""
