# AVSHUNTER - produce the macro inputs that used to come from the Colab notebooks, then
# rebuild the macro packet and the ETF macro board. Replaces: open Colab, run each notebook,
# download the files, copy them into dropbox\market_data.
#
# Run after the US close (16:15 ET); before it, Polygon daily/weekly bars are still forming.
# Every producer writes straight into dropbox\market_data and reads keys from the user
# environment or the repo .env (FRED_API_KEY, POLYGON_API_KEY, MARKETDATA_API_KEY;
# ANTHROPIC_API_KEY for build_macro_json.py).
#
# Usage:
#   .\Run-MacroInputs.ps1                  # producers -> FRED merge -> macro packet -> board
#   .\Run-MacroInputs.ps1 -PlanOnly        # list the steps and check the scripts exist; runs nothing
#   .\Run-MacroInputs.ps1 -WithGex         # also rebuild GEX from the stored chains first
#   .\Run-MacroInputs.ps1 -WithBonds       # also refresh bond_macro_state.json + auction calendar first
#   .\Run-MacroInputs.ps1 -SkipMacroJson   # skip build_macro_json.py (it calls the Anthropic API)
#   .\Run-MacroInputs.ps1 -SkipBoard       # skip the board rebuild
#   .\Run-MacroInputs.ps1 -AllowIntraday   # run before the close anyway (bars will be partial)
#
# Producers are independent: one failing does not stop the rest. The FRED monitor runs last of
# the producers because it merges their outputs into avsh_macro_master.csv. Exit code 1 if any
# step failed; the summary at the end lists each step, its exit code and duration.

param(
    [switch]$PlanOnly,
    [switch]$WithGex,
    [switch]$WithBonds,
    [switch]$SkipMacroJson,
    [switch]$SkipBoard,
    [switch]$AllowIntraday
)

$ErrorActionPreference = "Stop"
$repoRoot   = $PSScriptRoot
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
$colab      = Join-Path $repoRoot "Enhancements\colab"
$logDir     = Join-Path $repoRoot "logs\scheduled"

# -- Steps, in order -------------------------------------------------------------------------
$steps = @()
if ($WithGex)   { $steps += @{ Name = "GEX (stored chains)";     Script = Join-Path $repoRoot "scripts\build_local_gex.py"; Args = @() } }
if ($WithBonds) { $steps += @{ Name = "Bond macro + calendar";   Script = Join-Path $repoRoot "bond_macro_intelligence.py"; Args = @() } }
$steps += @(
    @{ Name = "VIX engine v4.1";             Script = Join-Path $colab "avshunter_vix_engine_v4_1.py";             Args = @() },
    @{ Name = "Daily regime model v1.8";     Script = Join-Path $colab "avshunter_daily_regime_model_v1_8.py";     Args = @() },
    @{ Name = "Market intelligence v5.4.3";  Script = Join-Path $colab "avshunter_market_intelligence_v5_4_3.py";  Args = @() },
    @{ Name = "Liquidity monitor v3.7";      Script = Join-Path $colab "avshunter_liquidity_monitor_v3_7.py";      Args = @() },
    @{ Name = "Macro module v2.8";           Script = Join-Path $colab "avshunter_macro_module_v2_8.py";           Args = @() },
    @{ Name = "Fung-Hsieh filter v1.4";      Script = Join-Path $colab "avshunter_fung_hsieh_filter_v1_4.py";      Args = @() },
    @{ Name = "FRED monitor v2.6 (+ merge)"; Script = Join-Path $colab "avshunter_fred_monitor_v2_6.py";           Args = @() }
)
if (-not $SkipMacroJson) { $steps += @{ Name = "Macro packet (build_macro_json)"; Script = Join-Path $repoRoot "build_macro_json.py"; Args = @("--force") } }
if (-not $SkipBoard)     { $steps += @{ Name = "ETF macro board";                  Script = Join-Path $repoRoot "Run-MacroBoard.ps1";  Args = @("-NoOpen") } }

# -- Plan ------------------------------------------------------------------------------------
if ($PlanOnly) {
    Write-Host "Run-MacroInputs plan (nothing is run):"
    $i = 0
    foreach ($s in $steps) {
        $i++
        $ok = if (Test-Path $s.Script) { "ok     " } else { "MISSING" }
        Write-Host ("  {0,2}. [{1}] {2,-34} {3} {4}" -f $i, $ok, $s.Name, (Split-Path $s.Script -Leaf), ($s.Args -join " "))
    }
    Write-Host ("  venv python: {0}" -f $(if (Test-Path $venvPython) { "ok" } else { "MISSING ($venvPython)" }))
    exit 0
}

# -- Run-time guard: US session must be closed -----------------------------------------------
$eastern = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), "Eastern Standard Time")
$isWeekday = $eastern.DayOfWeek -notin @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
$beforeClose = $isWeekday -and ($eastern.TimeOfDay -lt [TimeSpan]::new(16, 15, 0)) -and ($eastern.TimeOfDay -gt [TimeSpan]::new(4, 0, 0))
if ($beforeClose -and -not $AllowIntraday) {
    Write-Host (("[STOPPED] It is {0:HH:mm} ET on a weekday: today's bars are still forming. " -f $eastern) +
                "Run after 16:15 ET, or pass -AllowIntraday to run anyway.")
    exit 3
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("macro_inputs_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))
Start-Transcript -Path $logFile -Append | Out-Null

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
# The scripts print UTF-8. Windows PowerShell 5.1 decodes native output with the console code
# page (e.g. 850), which turned every check mark and box line into accented garbage; decode as UTF-8 for this run and
# restore the caller's setting afterwards. (Display and log only; the data files are UTF-8.)
$previousOutputEncoding = [Console]::OutputEncoding
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$results = @()
try {
    if (-not (Test-Path $venvPython)) {
        Write-Host "[ERROR] venv Python not found at $venvPython"
        exit 2
    }
    Set-Location $repoRoot
    Write-Host ("Run-MacroInputs started {0:yyyy-MM-dd HH:mm} local / {1:HH:mm} ET" -f (Get-Date), $eastern)

    foreach ($s in $steps) {
        Write-Host ""
        Write-Host ("=" * 78)
        Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $s.Name)
        Write-Host ("=" * 78)
        $started = Get-Date
        if (-not (Test-Path $s.Script)) {
            Write-Host "[MISSING] $($s.Script)"
            $code = 127
        } else {
            # Native stderr (yfinance warnings, tracebacks) must not abort the run, and Windows
            # PowerShell 5.1 only puts native output in the transcript when it passes through
            # the pipeline - so merge the streams, stringify, and send to the host.
            $ErrorActionPreference = "Continue"
            $global:LASTEXITCODE = 0
            try {
                if ($s.Script -like "*.ps1") {
                    & $s.Script @($s.Args) 2>&1 | ForEach-Object { "$_" } | Out-Host
                } else {
                    & $venvPython $s.Script @($s.Args) 2>&1 | ForEach-Object { "$_" } | Out-Host
                }
                $code = $LASTEXITCODE
                if ($null -eq $code) { $code = 0 }
            } catch {
                Write-Host "[ERROR] $($_.Exception.Message)"
                $code = 1
            }
            $ErrorActionPreference = "Stop"
        }
        $results += [pscustomobject]@{
            Step     = $s.Name
            Exit     = $code
            Status   = $(if ($code -eq 0) { "OK" } else { "FAILED" })
            Duration = "{0:mm\:ss}" -f ((Get-Date) - $started)
        }
    }

    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host "SUMMARY"
    Write-Host ("=" * 78)
    $results | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
    $failed = @($results | Where-Object { $_.Exit -ne 0 })
    if ($failed.Count -gt 0) {
        Write-Host ("[FAILED] {0} of {1} steps failed: {2}" -f $failed.Count, $results.Count, (($failed | ForEach-Object { $_.Step }) -join "; "))
        exit 1
    }
    Write-Host ("[COMPLETE] all {0} steps succeeded - log: {1}" -f $results.Count, $logFile)
    exit 0
} finally {
    Stop-Transcript | Out-Null
    try { [Console]::OutputEncoding = $previousOutputEncoding } catch { }
}
