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
#   .\Run-MacroInputs.ps1                  # producers (in parallel) -> FRED merge -> macro packet -> board
#   .\Run-MacroInputs.ps1 -PlanOnly        # list the steps and check the scripts exist; runs nothing
#   .\Run-MacroInputs.ps1 -Sequential      # run the producers one after another (the v1 behaviour)
#   .\Run-MacroInputs.ps1 -WithGex         # also rebuild GEX from the stored chains first
#   .\Run-MacroInputs.ps1 -WithBonds       # also refresh bond_macro_state.json + auction calendar first
#   .\Run-MacroInputs.ps1 -SkipMacroJson   # skip build_macro_json.py (it calls the Anthropic API)
#   .\Run-MacroInputs.ps1 -SkipBoard       # skip the board rebuild
#   .\Run-MacroInputs.ps1 -AllowIntraday   # run before the close anyway (bars will be partial)
#   .\Run-MacroInputs.ps1 -ProducerTimeoutMinutes 45   # stop a producer that runs longer (default 60)
#
# Three phases:
#   1. setup (optional, in order): GEX from stored chains, bond state + auction calendar - the
#      macro module reads both, so they finish before the producers start.
#   2. producers, IN PARALLEL: VIX engine, regime model, market intelligence, liquidity monitor,
#      macro module, Fung-Hsieh filter. They write different files and do not read each other's
#      outputs. Each writes its own log under logs\scheduled\macro_inputs_<time>\; the logs are
#      copied into the main transcript one step at a time once all have finished, so output
#      never interleaves. A producer still running after -ProducerTimeoutMinutes is stopped.
#   3. merge and publish (in order): FRED monitor (merges the producers' outputs into
#      avsh_macro_master.csv, so it must run after them), build_macro_json.py, the board.
# One failing step does not stop the rest. Exit code 1 if any step failed; the summary lists
# each step, its exit code and duration.

param(
    [switch]$PlanOnly,
    [switch]$Sequential,
    [switch]$WithGex,
    [switch]$WithBonds,
    [switch]$SkipMacroJson,
    [switch]$SkipBoard,
    [switch]$AllowIntraday,
    [int]$ProducerTimeoutMinutes = 60
)

$ErrorActionPreference = "Stop"
$repoRoot   = $PSScriptRoot
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
$colab      = Join-Path $repoRoot "Enhancements\colab"
$logDir     = Join-Path $repoRoot "logs\scheduled"

function New-Step([string]$Key, [string]$Name, [string]$Script, [string[]]$Arguments = @()) {
    return @{ Key = $Key; Name = $Name; Script = $Script; Args = $Arguments }
}

# -- Steps -------------------------------------------------------------------------------------
$setup = @()
if ($WithGex)   { $setup += New-Step "gex"   "GEX (stored chains)"   (Join-Path $repoRoot "scripts\build_local_gex.py") }
if ($WithBonds) { $setup += New-Step "bonds" "Bond macro + calendar" (Join-Path $repoRoot "bond_macro_intelligence.py") }

$producers = @(
    (New-Step "vix"     "VIX engine v4.1"            (Join-Path $colab "avshunter_vix_engine_v4_1.py")),
    (New-Step "regime"  "Daily regime model v1.8"    (Join-Path $colab "avshunter_daily_regime_model_v1_8.py")),
    (New-Step "mi"      "Market intelligence v5.4.3" (Join-Path $colab "avshunter_market_intelligence_v5_4_3.py")),
    (New-Step "liq"     "Liquidity monitor v3.7"     (Join-Path $colab "avshunter_liquidity_monitor_v3_7.py")),
    (New-Step "macro"   "Macro module v2.8"          (Join-Path $colab "avshunter_macro_module_v2_8.py")),
    (New-Step "fh"      "Fung-Hsieh filter v1.4"     (Join-Path $colab "avshunter_fung_hsieh_filter_v1_4.py"))
)

$publish = @( (New-Step "fred" "FRED monitor v2.6 (+ merge)" (Join-Path $colab "avshunter_fred_monitor_v2_6.py")) )
if (-not $SkipMacroJson) { $publish += New-Step "packet" "Macro packet (build_macro_json)" (Join-Path $repoRoot "build_macro_json.py") @("--force") }
if (-not $SkipBoard)     { $publish += New-Step "board"  "ETF macro board"                  (Join-Path $repoRoot "Run-MacroBoard.ps1")  @("-NoOpen") }

# -- Plan --------------------------------------------------------------------------------------
if ($PlanOnly) {
    Write-Host "Run-MacroInputs plan (nothing is run):"
    $i = 0
    $phases = @(
        @{ Label = "setup, in order"; Steps = $setup },
        @{ Label = $(if ($Sequential) { "producers, in order (-Sequential)" } else { "producers, in parallel (timeout $ProducerTimeoutMinutes min each)" }); Steps = $producers },
        @{ Label = "merge and publish, in order"; Steps = $publish }
    )
    foreach ($phase in $phases) {
        if ($phase.Steps.Count -eq 0) { continue }
        Write-Host ("  -- {0}" -f $phase.Label)
        foreach ($s in $phase.Steps) {
            $i++
            $ok = if (Test-Path $s.Script) { "ok     " } else { "MISSING" }
            Write-Host ("  {0,2}. [{1}] {2,-34} {3} {4}" -f $i, $ok, $s.Name, (Split-Path $s.Script -Leaf), ($s.Args -join " "))
        }
    }
    Write-Host ("  venv python: {0}" -f $(if (Test-Path $venvPython) { "ok" } else { "MISSING ($venvPython)" }))
    exit 0
}

# -- Run-time guard: US session must be closed -------------------------------------------------
$eastern = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), "Eastern Standard Time")
$isWeekday = $eastern.DayOfWeek -notin @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
$beforeClose = $isWeekday -and ($eastern.TimeOfDay -lt [TimeSpan]::new(16, 15, 0)) -and ($eastern.TimeOfDay -gt [TimeSpan]::new(4, 0, 0))
if ($beforeClose -and -not $AllowIntraday) {
    Write-Host (("[STOPPED] It is {0:HH:mm} ET on a weekday: today's bars are still forming. " -f $eastern) +
                "Run after 16:15 ET, or pass -AllowIntraday to run anyway.")
    exit 3
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp = "{0:yyyyMMdd_HHmmss}" -f (Get-Date)
$logFile = Join-Path $logDir ("macro_inputs_{0}.log" -f $stamp)
$stepLogDir = Join-Path $logDir ("macro_inputs_{0}" -f $stamp)
New-Item -ItemType Directory -Path $stepLogDir -Force | Out-Null
Start-Transcript -Path $logFile -Append | Out-Null

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
# The scripts print UTF-8. Windows PowerShell 5.1 decodes native output with the console code
# page (e.g. 850), which turned every check mark and box line into accented garbage; decode as
# UTF-8 for this run and restore the caller's setting afterwards. (Display and log only.)
$previousOutputEncoding = [Console]::OutputEncoding
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$script:results = @()

function Write-Header([string]$Name, [string]$Note = "") {
    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host ("[{0:HH:mm:ss}] {1}{2}" -f (Get-Date), $Name, $(if ($Note) { "  ($Note)" } else { "" }))
    Write-Host ("=" * 78)
}

function Add-Result($Step, [int]$Code, [TimeSpan]$Elapsed, [string]$Mode) {
    $script:results += [pscustomobject]@{
        Step     = $Step.Name
        Mode     = $Mode
        Exit     = $Code
        Status   = $(if ($Code -eq 0) { "OK" } elseif ($Code -eq 124) { "TIMEOUT" } else { "FAILED" })
        Duration = "{0:hh\:mm\:ss}" -f $Elapsed
    }
}

function Invoke-StepInline($Step) {
    # One step in this console: output streamed through the host so the transcript keeps it.
    Write-Header $Step.Name
    $started = Get-Date
    if (-not (Test-Path $Step.Script)) {
        Write-Host "[MISSING] $($Step.Script)"
        Add-Result $Step 127 ((Get-Date) - $started) "in order"
        return
    }
    # Native stderr (yfinance warnings, tracebacks) must not abort the run, and Windows
    # PowerShell 5.1 only puts native output in the transcript when it passes through the
    # pipeline - so merge the streams, stringify, and send to the host.
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    try {
        if ($Step.Script -like "*.ps1") {
            & $Step.Script @($Step.Args) 2>&1 | ForEach-Object { "$_" } | Out-Host
        } else {
            & $venvPython $Step.Script @($Step.Args) 2>&1 | ForEach-Object { "$_" } | Out-Host
        }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        Write-Host "[ERROR] $($_.Exception.Message)"
        $code = 1
    }
    $ErrorActionPreference = "Stop"
    Add-Result $Step $code ((Get-Date) - $started) "in order"
}

function Invoke-StepsParallel($Steps, [int]$TimeoutMinutes) {
    # Start every producer, wait for all (each with a time limit), then copy each step's log
    # into the transcript in the original order.
    Write-Header ("Producers in parallel: {0}" -f (($Steps | ForEach-Object { $_.Name }) -join ", "))
    $runs = @()
    foreach ($s in $Steps) {
        $out = Join-Path $stepLogDir ("{0}.stdout.log" -f $s.Key)
        $err = Join-Path $stepLogDir ("{0}.stderr.log" -f $s.Key)
        if (-not (Test-Path $s.Script)) {
            $runs += [pscustomobject]@{ Step = $s; Proc = $null; Out = $out; Err = $err; Started = (Get-Date); Code = 127; Note = "MISSING $($s.Script)" }
            continue
        }
        $argList = @('"' + $s.Script + '"') + @($s.Args)
        $p = Start-Process -FilePath $venvPython -ArgumentList $argList -WorkingDirectory $repoRoot `
                           -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $null = $p.Handle     # Windows PowerShell 5.1: hold the handle so ExitCode is readable later
        Write-Host ("  started {0,-28} pid {1}" -f $s.Name, $p.Id)
        $runs += [pscustomobject]@{ Step = $s; Proc = $p; Out = $out; Err = $err; Started = (Get-Date); Code = $null; Note = "" }
    }
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    foreach ($r in $runs) {
        if ($null -eq $r.Proc) { continue }
        $remaining = [int][Math]::Max(0, ($deadline - (Get-Date)).TotalMilliseconds)
        if ($r.Proc.WaitForExit($remaining)) {
            $r.Proc.WaitForExit()                 # flush redirected output
            $r.Code = $r.Proc.ExitCode
            if ($null -eq $r.Code) { $r.Code = 1 }
        } else {
            try { $r.Proc.Kill() } catch { }
            $r.Code = 124
            $r.Note = "stopped after $TimeoutMinutes min (-ProducerTimeoutMinutes)"
        }
        $ended = if ($r.Proc.HasExited) { $r.Proc.ExitTime } else { Get-Date }
        Write-Host ("  finished {0,-27} exit {1,-4} after {2:mm\:ss}" -f $r.Step.Name, $r.Code, ($ended - $r.Started))
        $r | Add-Member -NotePropertyName Elapsed -NotePropertyValue ($ended - $r.Started)
    }
    foreach ($r in $runs) {
        Write-Header $r.Step.Name "ran in parallel"
        if ($r.Note) { Write-Host "[$($r.Note)]" }
        foreach ($path in @($r.Out, $r.Err)) {
            if (Test-Path $path) {
                $text = Get-Content -Path $path -Encoding UTF8
                if ($text) {
                    if ($path -eq $r.Err) { Write-Host "--- stderr ---" }
                    $text | ForEach-Object { Write-Host $_ }
                }
            }
        }
        $elapsed = if ($r.PSObject.Properties["Elapsed"]) { $r.Elapsed } else { [TimeSpan]::Zero }
        Add-Result $r.Step ([int]$r.Code) $elapsed "parallel"
    }
}

try {
    if (-not (Test-Path $venvPython)) {
        Write-Host "[ERROR] venv Python not found at $venvPython"
        exit 2
    }
    Set-Location $repoRoot
    $runStarted = Get-Date
    Write-Host ("Run-MacroInputs started {0:yyyy-MM-dd HH:mm} local / {1:HH:mm} ET  (producers: {2})" -f `
                (Get-Date), $eastern, $(if ($Sequential) { "in order" } else { "in parallel" }))
    Write-Host ("Per-step logs: {0}" -f $stepLogDir)

    foreach ($s in $setup) { Invoke-StepInline $s }
    if ($Sequential) {
        foreach ($s in $producers) { Invoke-StepInline $s }
    } else {
        Invoke-StepsParallel $producers $ProducerTimeoutMinutes
    }
    foreach ($s in $publish) { Invoke-StepInline $s }

    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host ("SUMMARY  (total {0:hh\:mm\:ss})" -f ((Get-Date) - $runStarted))
    Write-Host ("=" * 78)
    $script:results | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
    $failed = @($script:results | Where-Object { $_.Exit -ne 0 })
    if ($failed.Count -gt 0) {
        Write-Host ("[FAILED] {0} of {1} steps failed: {2}" -f $failed.Count, $script:results.Count, (($failed | ForEach-Object { $_.Step }) -join "; "))
        exit 1
    }
    Write-Host ("[COMPLETE] all {0} steps succeeded - log: {1}" -f $script:results.Count, $logFile)
    exit 0
} finally {
    Stop-Transcript | Out-Null
    try { [Console]::OutputEncoding = $previousOutputEncoding } catch { }
}
