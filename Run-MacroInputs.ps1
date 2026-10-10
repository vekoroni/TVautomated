# AVSHUNTER - produce the macro inputs that used to come from the Colab notebooks, then
# rebuild the macro packet and the ETF macro board. Replaces: open Colab, run each notebook,
# download the files, copy them into dropbox\market_data.
#
# Runs twice per US session:
#   PostClose  after the close (default start 16:30 ET, latest start 23:30 ET) - the evening
#              record, built after the evening pipeline has written the day's prices.
#   PreOpen    before the open (default start 08:35 ET, latest start 09:00 ET) - picks up the
#              overnight session (Asia, London/Europe, FX) and the 08:30 ET releases, and must
#              finish before the open and the morning pipeline.
# Task Scheduler runs in UK time while the targets are US times; the two clocks shift on
# different dates. Start the task early and let the runner wait: it converts -StartAtET to
# local time every run, so the clock-change weeks need no schedule edits.
#
# Every producer writes straight into dropbox\market_data and reads keys from the user
# environment or the repo .env (FRED_API_KEY, POLYGON_API_KEY, MARKETDATA_API_KEY;
# ANTHROPIC_API_KEY for build_macro_json.py). Each step receives AVSH_RUN_SESSION and
# AVSH_SESSION_CUTOFF: the last COMPLETED US session at the start time (repo xnys_calendar), so a
# pre-open run measures from the previous close and never treats a partial "today" bar (pre-market
# trades, overnight VIX) as a finished session. A PreOpen run stops (exit 6) when the cut-off
# cannot be computed; a PostClose run warns and runs uncut. AVSH_US_CLOSE_UTC is that session's
# close instant (13:00 ET on half days): the overnight capture measures from it.
#
# Usage:
#   .\Run-MacroInputs.ps1 -Session PostClose        # evening run (waits until 16:30 ET)
#   .\Run-MacroInputs.ps1 -Session PreOpen          # morning run (waits until 08:35 ET)
#   .\Run-MacroInputs.ps1                           # -Session Auto: PreOpen before 09:30 ET, else PostClose
#   .\Run-MacroInputs.ps1 -PlanOnly                 # show the session decision and steps; runs nothing
#   .\Run-MacroInputs.ps1 -StartAtET 08:45 -LatestStartET 09:05   # move the window
#   .\Run-MacroInputs.ps1 -PipelineWaitMinutes 45   # how long to wait for a running pipeline (default 30)
#   .\Run-MacroInputs.ps1 -Sequential               # producers one after another (v1 behaviour)
#   .\Run-MacroInputs.ps1 -WithGex / -WithBonds     # rebuild GEX / bond state first
#   .\Run-MacroInputs.ps1 -SkipMacroJson / -SkipBoard
#   .\Run-MacroInputs.ps1 -AllowIntraday            # allow a run during US regular hours (bars partial)
#   .\Run-MacroInputs.ps1 -ProducerTimeoutMinutes 45
#
# Before anything runs: (1) today must be an XNYS session (repo xnys_calendar; weekday US holidays
# exit 0 as SKIPPED). Weekends are different (ACK 10 Oct 2026): there is no US session, so the
# windows, the regular-hours guard and the skip do not apply - a weekend run starts at once, cuts at
# the last completed session (Friday) and is labelled OffSession, so the board files an off-session
# build and never overwrites Friday's scored evening record; (2) not during US regular hours 09:30-16:15 ET unless
# -AllowIntraday; (3) not after -LatestStartET (exit 4); wait until -StartAtET; (4) if
# intelligent_orchestrator.py or a backfill is running, wait up to -PipelineWaitMinutes
# (never past -LatestStartET) and stop with exit 5 if it is still running.
#
# Three phases:
#   1. setup (optional, in order): GEX from stored chains, bond state + auction calendar.
#   2. producers, IN PARALLEL: VIX engine, regime model, market intelligence, liquidity monitor,
#      macro module, Fung-Hsieh filter; each logs to logs\scheduled\macro_inputs_<time>\,
#      copied into the transcript one step at a time afterwards. -ProducerTimeoutMinutes
#      stops a producer that hangs.
#   3. merge and publish (in order): FRED monitor (merges the producers into
#      avsh_macro_master.csv), build_macro_json.py, the board.
# Exit codes: 0 done or skipped (not a session day), 1 a step failed, 2 venv missing,
# 3 refused during regular hours, 4 past the latest start, 5 pipeline still running,
# 6 PreOpen without a session cut-off (calendar check unavailable).

param(
    [ValidateSet("Auto", "PostClose", "PreOpen")]
    [string]$Session = "Auto",
    [string]$StartAtET = "",
    [string]$LatestStartET = "",
    [int]$PipelineWaitMinutes = 30,
    [switch]$PlanOnly,
    [switch]$Sequential,
    [switch]$WithGex,
    [switch]$WithBonds,
    [switch]$SkipMacroJson,
    [switch]$SkipBoard,
    [switch]$AllowIntraday,
    [int]$ProducerTimeoutMinutes = 60,
    [string]$NowET = ""          # testing only: pretend it is this US Eastern time, "yyyy-MM-dd HH:mm"
)

$ErrorActionPreference = "Stop"
$repoRoot   = $PSScriptRoot
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
$colab      = Join-Path $repoRoot "Enhancements\colab"
$logDir     = Join-Path $repoRoot "logs\scheduled"

$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$SessionDefaults = @{
    PostClose = @{ Start = "16:30"; Latest = "23:30" }
    PreOpen   = @{ Start = "08:35"; Latest = "09:00" }
}
$RegularOpen  = [TimeSpan]::new(9, 30, 0)
$RegularGuard = [TimeSpan]::new(16, 15, 0)     # after the close plus settlement of closing prints
$PreOpenWarn  = [TimeSpan]::new(9, 25, 0)
$PipelinePatterns = @("*intelligent_orchestrator.py*", "*backfill*")

function Get-NowET {
    if ($NowET) { return [DateTime]::ParseExact($NowET, "yyyy-MM-dd HH:mm", [Globalization.CultureInfo]::InvariantCulture) }
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $etZone)
}

function Get-ETOnDate([DateTime]$EtNow, [string]$HHmm) {
    $t = [TimeSpan]::ParseExact($HHmm, "hh\:mm", [Globalization.CultureInfo]::InvariantCulture)
    return $EtNow.Date + $t
}

function Test-XnysSession([DateTime]$Day) {
    # One owner of the US trading calendar: avshunter.shared.xnys_calendar.
    if (-not (Test-Path $venvPython)) { return $null }
    $code = "import sys; from datetime import date; from avshunter.shared.xnys_calendar import is_xnys_session as f; sys.exit(0 if f(date.fromisoformat(sys.argv[1])) else 3)"
    Push-Location $repoRoot
    try {
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $venvPython -c $code ($Day.ToString("yyyy-MM-dd")) 2>&1 | Out-Null
        $ErrorActionPreference = $prev
        if ($LASTEXITCODE -eq 0) { return $true }
        if ($LASTEXITCODE -eq 3) { return $false }
        return $null
    } finally { Pop-Location }
}

function Get-SessionCutoff([DateTime]$AtET) {
    # Last completed XNYS session at $AtET (US Eastern), "yyyy-MM-dd"; $null when unavailable.
    # Also sets $script:CutoffCloseUtc to that session's close instant ("yyyy-MM-ddTHH:mm:ssZ").
    $script:CutoffCloseUtc = $null
    if (-not (Test-Path $venvPython)) { return $null }
    $code = "import sys; from datetime import datetime; from zoneinfo import ZoneInfo; from avshunter.shared.xnys_calendar import session_state as s, session_bounds as b; d = s(datetime.fromisoformat(sys.argv[1]).replace(tzinfo=ZoneInfo(sys.argv[2])))[2]; print(d.isoformat(), b(d)[1].strftime('%Y-%m-%dT%H:%M:%SZ'))"
    Push-Location $repoRoot
    try {
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $out = & $venvPython -c $code ($AtET.ToString("yyyy-MM-ddTHH:mm:ss")) "America/New_York" 2>$null
        $ErrorActionPreference = $prev
        if ($LASTEXITCODE -ne 0) { return $null }
        $value = ("$out").Trim()
        if ($value -match '^(\d{4}-\d{2}-\d{2}) (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$') {
            $script:CutoffCloseUtc = $Matches[2]
            return $Matches[1]
        }
        return $null
    } finally { Pop-Location }
}

function Get-PipelineProcesses {
    $found = @()
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction Stop
        foreach ($p in $procs) {
            foreach ($pat in $PipelinePatterns) {
                if ($p.CommandLine -and $p.CommandLine -like $pat) { $found += $p; break }
            }
        }
    } catch { }
    return $found
}

function New-Step([string]$Key, [string]$Name, [string]$Script, [string[]]$Arguments = @()) {
    return @{ Key = $Key; Name = $Name; Script = $Script; Args = $Arguments }
}

# -- Session decision ---------------------------------------------------------------------------
$etNow = Get-NowET
if ($Session -eq "Auto") {
    $Session = if ($etNow.TimeOfDay -lt $RegularOpen) { "PreOpen" } else { "PostClose" }
}
if (-not $StartAtET)     { $StartAtET = $SessionDefaults[$Session].Start }
if (-not $LatestStartET) { $LatestStartET = $SessionDefaults[$Session].Latest }
$startAt  = Get-ETOnDate $etNow $StartAtET
$latestAt = Get-ETOnDate $etNow $LatestStartET
$startAtLocal = [TimeZoneInfo]::ConvertTime($startAt, $etZone, [TimeZoneInfo]::Local)
$isSessionDay = Test-XnysSession $etNow
# Weekends (ACK 10 Oct 2026): no US session, so no window, no regular-hours guard and no skip. The run
# measures from the last completed session and is labelled OffSession (producers print it; the board
# files an off-session build, never the scored evening record). Weekday XNYS holidays still skip.
$offSession = ($etNow.DayOfWeek -eq [DayOfWeek]::Saturday -or $etNow.DayOfWeek -eq [DayOfWeek]::Sunday) -and ($isSessionDay -ne $true)
$runLabel = if ($offSession) { "OffSession" } else { $Session }

# -- Steps --------------------------------------------------------------------------------------
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

# -- Plan ---------------------------------------------------------------------------------------
if ($PlanOnly) {
    Write-Host "Run-MacroInputs plan (nothing is run):"
    Write-Host ("  session        : {0}" -f $runLabel)
    Write-Host ("  now            : {0:yyyy-MM-dd HH:mm} ET{1}" -f $etNow, $(if ($NowET) { "  (simulated by -NowET)" } else { "" }))
    Write-Host ("  trading day    : {0}" -f $(if ($isSessionDay -eq $true) { "yes (XNYS session)" } elseif ($offSession) { "NO - weekend: off-session run (no window, no regular-hours guard)" } elseif ($isSessionDay -eq $false) { "NO - the run would be skipped" } else { "unknown (calendar check unavailable)" }))
    if ($offSession) { Write-Host "  start window   : none (weekend - starts immediately)" }
    else { Write-Host ("  start window   : {0:HH:mm} - {1:HH:mm} ET   (start = {2:HH:mm} local time)" -f $startAt, $latestAt, $startAtLocal) }
    Write-Host ("  board build    : {0}" -f $(if ($offSession) { "off-session (not the scored evening record)" } elseif ($Session -eq "PostClose") { "evening (the scored record)" } else { "morning (kept, not scored)" }))
    $planAt = if ($offSession -or $etNow -gt $startAt) { $etNow } else { $startAt }
    $planCutoff = Get-SessionCutoff $planAt
    Write-Host ("  session cut-off: {0}" -f $(if ($planCutoff) { "$planCutoff (last completed US session at {0:HH:mm} ET; later bars are not used; close $script:CutoffCloseUtc)" -f $planAt } elseif ($Session -eq "PreOpen" -or $offSession) { "UNAVAILABLE - the run would stop (exit 6)" } else { "UNAVAILABLE - the run would continue uncut" }))
    $running = @(Get-PipelineProcesses)
    Write-Host ("  pipeline now   : {0}" -f $(if ($running.Count) { "RUNNING (pid " + (($running | ForEach-Object { $_.ProcessId }) -join ", ") + ") - would wait up to $PipelineWaitMinutes min" } else { "not running" }))
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

# -- Guards before anything is written -----------------------------------------------------------
if ($isSessionDay -eq $false -and -not $offSession) {
    Write-Host ("[SKIPPED] {0:yyyy-MM-dd} is not a US trading session (weekend or XNYS holiday)." -f $etNow)
    exit 0
}
$inRegularHours = ($etNow.TimeOfDay -ge $RegularOpen) -and ($etNow.TimeOfDay -lt $RegularGuard)
if ($inRegularHours -and -not $AllowIntraday -and -not $offSession) {
    Write-Host (("[STOPPED] It is {0:HH:mm} ET, inside US regular hours (09:30-16:15): today's bars are still forming. " -f $etNow) +
                "Run PreOpen before 09:30 or PostClose after 16:15, or pass -AllowIntraday.")
    exit 3
}
if (-not $offSession -and $etNow -gt $latestAt) {
    Write-Host ("[SKIPPED] {0} run: it is {1:HH:mm} ET, after the latest start {2:HH:mm} ET (-LatestStartET)." -f $Session, $etNow, $latestAt)
    exit 4
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp = "{0:yyyyMMdd_HHmmss}" -f (Get-Date)
$logFile = Join-Path $logDir ("macro_inputs_{0}_{1}.log" -f $runLabel.ToLower(), $stamp)
$stepLogDir = Join-Path $logDir ("macro_inputs_{0}_{1}" -f $runLabel.ToLower(), $stamp)
New-Item -ItemType Directory -Path $stepLogDir -Force | Out-Null
Start-Transcript -Path $logFile -Append | Out-Null

# The variables below are set for the producers only. A manual run happens in the user's own
# PowerShell process, so they are saved here and restored on exit (9 Oct 2026: a PostClose run left
# AVSH_RUN_SESSION=PostClose behind and labelled the next morning's board build as the evening one).
$script:CallerEnv = @{}
foreach ($name in "PYTHONIOENCODING", "PYTHONUNBUFFERED", "AVSH_RUN_SESSION", "AVSH_SESSION_CUTOFF", "AVSH_US_CLOSE_UTC") {
    $script:CallerEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:AVSH_RUN_SESSION = $runLabel
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

function Wait-UntilET([DateTime]$TargetET, [string]$Why) {
    # Sleep in one-minute steps until $TargetET (US Eastern), logging every 15 minutes.
    $lastLog = [DateTime]::MinValue
    while ((Get-NowET) -lt $TargetET) {
        if ($NowET) { break }                                  # simulated time: never sleep
        if (((Get-Date) - $lastLog).TotalMinutes -ge 15) {
            Write-Host ("[WAIT] {0}: now {1:HH:mm} ET, waiting until {2:HH:mm} ET" -f $Why, (Get-NowET), $TargetET)
            $lastLog = Get-Date
        }
        Start-Sleep -Seconds 60
    }
}

$exitCode = 0
try {
  :run do {
    if (-not (Test-Path $venvPython)) {
        Write-Host "[ERROR] venv Python not found at $venvPython"
        $exitCode = 2
        break run
    }
    Set-Location $repoRoot
    if ($offSession) {
        Write-Host ("Run-MacroInputs OffSession (weekend): starts now, producers {0}" -f $(if ($Sequential) { "in order" } else { "in parallel" }))
    } else {
        Write-Host ("Run-MacroInputs {0}: start window {1:HH:mm}-{2:HH:mm} ET ({3:HH:mm} local), producers {4}" -f `
                    $Session, $startAt, $latestAt, $startAtLocal, $(if ($Sequential) { "in order" } else { "in parallel" }))
    }
    if ($isSessionDay -eq $null) { Write-Host "[WARN] trading-calendar check unavailable; continuing" }

    # 1. wait for the start time
    if (-not $offSession) { Wait-UntilET $startAt "start time" }

    # 2. wait for a running pipeline / backfill, never past the latest start
    $pipeDeadline = (Get-NowET).AddMinutes($PipelineWaitMinutes)
    if (-not $offSession -and $pipeDeadline -gt $latestAt) { $pipeDeadline = $latestAt }
    $running = @(Get-PipelineProcesses)
    while ($running.Count -gt 0) {
        $now = Get-NowET
        if ($now -ge $pipeDeadline -or $NowET) {
            Write-Host ("[STOPPED] pipeline / backfill still running (pid {0}) at {1:HH:mm} ET; not starting, so the two runs do not compete for the network, the price store and the API keys." -f `
                        (($running | ForEach-Object { $_.ProcessId }) -join ", "), $now)
            $exitCode = 5
            break run
        }
        Write-Host ("[WAIT] pipeline / backfill running (pid {0}); waiting, at most until {1:HH:mm} ET" -f `
                    (($running | ForEach-Object { $_.ProcessId }) -join ", "), $pipeDeadline)
        Start-Sleep -Seconds 60
        $running = @(Get-PipelineProcesses)
    }
    if (-not $offSession -and (Get-NowET) -gt $latestAt) {
        Write-Host ("[SKIPPED] it is {0:HH:mm} ET, after the latest start {1:HH:mm} ET." -f (Get-NowET), $latestAt)
        $exitCode = 4
        break run
    }

    # 3. session cut-off at the actual start time (not when the task woke up)
    $cutoff = Get-SessionCutoff (Get-NowET)
    if ($cutoff) {
        $env:AVSH_SESSION_CUTOFF = $cutoff
        $env:AVSH_US_CLOSE_UTC = $script:CutoffCloseUtc
        Write-Host ("[CUTOFF] last completed US session {0} (close {1}); bars dated after it are not used" -f $cutoff, $script:CutoffCloseUtc)
    } elseif ($Session -eq "PreOpen" -or $offSession) {
        Write-Host "[STOPPED] session cut-off unavailable (trading-calendar check failed); a PreOpen run without it would treat partial pre-market bars as a finished session."
        $exitCode = 6
        break run
    } else {
        Remove-Item Env:AVSH_SESSION_CUTOFF -ErrorAction SilentlyContinue
        Remove-Item Env:AVSH_US_CLOSE_UTC -ErrorAction SilentlyContinue
        Write-Host "[WARN] session cut-off unavailable; PostClose run continues uncut"
    }

    $runStarted = Get-Date
    Write-Host ("[START] {0} run at {1:yyyy-MM-dd HH:mm} ET  (per-step logs: {2})" -f $runLabel, (Get-NowET), $stepLogDir)

    foreach ($s in $setup) { Invoke-StepInline $s }
    if ($Sequential) {
        foreach ($s in $producers) { Invoke-StepInline $s }
    } else {
        Invoke-StepsParallel $producers $ProducerTimeoutMinutes
    }
    foreach ($s in $publish) { Invoke-StepInline $s }

    $finishedET = Get-NowET
    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host ("SUMMARY  {0} run  (total {1:hh\:mm\:ss}, finished {2:HH:mm} ET)" -f $runLabel, ((Get-Date) - $runStarted), $finishedET)
    Write-Host ("=" * 78)
    $script:results | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
    if (-not $offSession -and $Session -eq "PreOpen" -and $finishedET.TimeOfDay -ge $PreOpenWarn) {
        Write-Host ("[WARN] PreOpen run finished at {0:HH:mm} ET - after 09:25, close to the open and the morning pipeline." -f $finishedET)
    }
    $failed = @($script:results | Where-Object { $_.Exit -ne 0 })
    if ($failed.Count -gt 0) {
        Write-Host ("[FAILED] {0} of {1} steps failed: {2}" -f $failed.Count, $script:results.Count, (($failed | ForEach-Object { $_.Step }) -join "; "))
        $exitCode = 1
        break run
    }
    Write-Host ("[COMPLETE] {0} run: all {1} steps succeeded - log: {2}" -f $runLabel, $script:results.Count, $logFile)
  } while ($false)
} finally {
    Stop-Transcript | Out-Null
    try { [Console]::OutputEncoding = $previousOutputEncoding } catch { }
    foreach ($name in $script:CallerEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $script:CallerEnv[$name], "Process")   # $null removes it
    }
}
exit $exitCode
