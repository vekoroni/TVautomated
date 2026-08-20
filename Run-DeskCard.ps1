param(
    [double]$IV, [int]$Days, [double]$Stop, [int]$Top,
    [switch]$Batch, [switch]$Csv,
    [ValidateSet("candidates","validated")][string]$Source
)
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"

$scriptArgs = @()
if ($Batch)  { $scriptArgs += "--batch" }
if ($Source) { $scriptArgs += @("--source", $Source) }
if ($Top)    { $scriptArgs += @("--top", $Top) }
if ($Csv)    { $scriptArgs += "--csv" }
if ($IV)     { $scriptArgs += @("--iv", $IV, "--days", $Days, "--stop", $Stop) }

python .\desk_card.py @scriptArgs
if ($LASTEXITCODE -eq 1) { Write-Host "DESK CARD FAILED - required input missing or unreadable" -ForegroundColor Red }
if ($LASTEXITCODE -eq 2) { Write-Host "DESK CARD DEGRADED - some inputs missing" -ForegroundColor Yellow }
