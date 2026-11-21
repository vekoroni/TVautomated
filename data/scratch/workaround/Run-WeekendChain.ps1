<#
Run-WeekendChain.ps1 (14 Nov 2026, ACK: start it and walk away; it must not stop part-way)
Unattended chain for an off-session (weekend) run:
  1. Run-MacroInputs.ps1 -Session PostClose  (weekend = OffSession, starts at once, cut-off = Friday)
     If a macro step fails, the packet is rebuilt (build_macro_json.py --force --health-exit-code)
     so the evening preflight sees one coherent publication.
  2. run_evening_scheduled.ps1 straight after (no gap, so the preflight SHA check holds).
     If it stops at the macro preflight (MACRO_PUBLICATION_...), the packet is rebuilt and the
     evening is retried once. That failure happens before Discovery, so the retry costs little.
  3. avs_day.ps1 evening, then avs_day.ps1 packs  (only when the evening finished OK; otherwise
     they would build on the previous run).
Keeps Windows awake while it runs (released when it ends). Progress log:
  logs\scheduled\weekend_chain_<time>.log  (each step also keeps its own log as usual)
Run:
  & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\Run-WeekendChain.ps1"
#>
$Root = 'C:\Users\ACKVerissimo\AVSHUNTER-Intelligence'
Set-Location $Root
$Py = Join-Path $Root 'venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs\scheduled'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$ChainLog = Join-Path $LogDir ('weekend_chain_{0:yyyyMMdd_HHmmss}.log' -f (Get-Date))

function Note([string]$Text) {
    $line = '{0:yyyy-MM-dd HH:mm:ss}  {1}' -f (Get-Date), $Text
    Write-Host $line -ForegroundColor Cyan
    Add-Content -Path $ChainLog -Value $line
}

function Rebuild-Packet {
    Set-Location $Root
    & $Py (Join-Path $Root 'build_macro_json.py') --force --health-exit-code | Out-Host
    Note ("packet rebuild exit {0} (0 = OK, 2 = degraded but usable)" -f $LASTEXITCODE)
}

function Run-Evening {
    Set-Location $Root
    $started = Get-Date
    # The orchestrator logs to stderr and appends to logs\orchestrator.log; read only what this run adds.
    $orchLog = Join-Path $Root 'logs\orchestrator.log'
    $offset = if (Test-Path $orchLog) { (Get-Item $orchLog).Length } else { 0 }
    & (Join-Path $Root 'run_evening_scheduled.ps1') | Out-Host
    $code = $LASTEXITCODE
    $minutes = ((Get-Date) - $started).TotalMinutes
    $macroStop = $false
    if (Test-Path $orchLog) {
        try {
            $fs = [System.IO.File]::Open($orchLog, 'Open', 'Read', 'ReadWrite')
            [void]$fs.Seek([int64]$offset, 'Begin')
            $tail = (New-Object System.IO.StreamReader($fs)).ReadToEnd()
            $fs.Close()
            $macroStop = $tail -match 'MACRO_PUBLICATION_(PREFLIGHT_FAILED|CHANGED_DURING_PREFLIGHT)|RUN_SCOPED_MACRO_FAILED'
        } catch { }
    }
    return [pscustomobject]@{ Code = $code; MacroStop = $macroStop; Minutes = [math]::Round($minutes, 1) }
}

# Keep the PC awake while the chain runs (cleared in finally). Does not stop a lid-close or a forced update restart.
try {
    Add-Type -Namespace AvsWin -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);' -ErrorAction Stop
    [void][AvsWin.Power]::SetThreadExecutionState([uint32]2147483649)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    $awake = $true
} catch { $awake = $false }

try {
    Note ("chain started; keep-awake {0}" -f $(if ($awake) { 'ON' } else { 'NOT SET - change the sleep setting by hand' }))

    Note '1/3 macro inputs (off-session on a weekend)'
    & (Join-Path $Root 'Run-MacroInputs.ps1') -Session PostClose
    $macroCode = $LASTEXITCODE
    Note ("macro exit {0}" -f $macroCode)
    if ($macroCode -ne 0) {
        Note 'macro did not finish cleanly: rebuilding the packet before the evening'
        Rebuild-Packet
    }

    Note '2/3 evening pipeline'
    $ev = Run-Evening
    Note ("evening exit {0} after {1} min; macro preflight stop: {2}" -f $ev.Code, $ev.Minutes, $ev.MacroStop)
    if ($ev.Code -ne 0 -and ($ev.MacroStop -or $ev.Minutes -lt 15)) {
        Note 'evening stopped early (macro preflight or before Discovery spend): rebuilding the packet and retrying once'
        Rebuild-Packet
        $ev = Run-Evening
        Note ("evening retry exit {0} after {1} min; macro preflight stop: {2}" -f $ev.Code, $ev.Minutes, $ev.MacroStop)
    }

    if ($ev.Code -eq 0) {
        Note '3/3 Lane B: avs_day.ps1 evening'
        & (Join-Path $Root 'data\scratch\workaround\avs_day.ps1') evening
        Note 'Lane B: avs_day.ps1 packs'
        & (Join-Path $Root 'data\scratch\workaround\avs_day.ps1') packs
        Note 'Lane B done'
    } else {
        Note 'evening did not finish OK: Lane B skipped (it would have built on the previous run). See the evening log.'
    }
} catch {
    Note ("chain error: {0}" -f $_.Exception.Message)
} finally {
    if ($awake) { [void][AvsWin.Power]::SetThreadExecutionState([uint32]2147483648) }   # ES_CONTINUOUS only: normal sleep again
    Set-Location $Root
    Note 'chain finished'
}
