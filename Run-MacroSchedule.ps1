$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$logDir = Join-Path $PSScriptRoot 'logs/scheduled'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ('macro_schedule_' + (Get-Date -Format 'yyyyMMdd') + '.log')
& (Join-Path $PSScriptRoot 'venv/Scripts/python.exe') -B (Join-Path $PSScriptRoot 'scripts/scheduled_macro_builds.py') --execute 2>&1 | ForEach-Object { $_.ToString() } | Out-File -LiteralPath $logFile -Append -Encoding utf8
exit $LASTEXITCODE
