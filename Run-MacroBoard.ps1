# Build the standalone ETF macro board (read-only on AVSHUNTER data) and open it.
# Usage:  .\Run-MacroBoard.ps1            build latest and open
#         .\Run-MacroBoard.ps1 -NoOpen    build only
param([switch]$NoOpen)
Set-Location -Path $PSScriptRoot
$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if ($NoOpen) { & $python -m macro_board --refresh } else { & $python -m macro_board --refresh --open }
