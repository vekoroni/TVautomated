[CmdletBinding()]
param(
    [string]$RepositoryRoot = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence",
    [ValidateRange(1, 100)]
    [int]$MaxCandidates = 1,
    [switch]$ProcessNewestExisting
)

$ErrorActionPreference = "Stop"

$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$LabExport = Join-Path $RepositoryRoot "pipeline_interpreter\MA_Inputs\lab_export"
$Launcher = Join-Path $RepositoryRoot "run_shadow_automation.bat"
$StatePath = Join-Path $RepositoryRoot "pipeline_interpreter\automation_v2\lab_export_watcher_state.json"

if (-not (Test-Path -LiteralPath $LabExport -PathType Container)) {
    throw "Lab export directory not found: $LabExport"
}
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
    throw "Shadow launcher not found: $Launcher"
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return @{ processed = @{} }
    }
    try {
        $content = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        $processed = @{}
        if ($content.processed) {
            $content.processed.PSObject.Properties | ForEach-Object {
                $processed[$_.Name] = [string]$_.Value
            }
        }
        return @{ processed = $processed }
    }
    catch {
        throw "Watcher state is unreadable: $StatePath - $($_.Exception.Message)"
    }
}

function Write-State([hashtable]$State) {
    $parent = Split-Path -Parent $StatePath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    $temporary = "$StatePath.tmp"
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatePath -Force
}

function Wait-ForStableFile([string]$Path) {
    $previousLength = -1L
    $stableChecks = 0
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try {
                $item = Get-Item -LiteralPath $Path
                $stream = [IO.File]::Open($Path, 'Open', 'Read', 'None')
                $stream.Close()
                if ($item.Length -gt 0 -and $item.Length -eq $previousLength) {
                    $stableChecks++
                    if ($stableChecks -ge 2) { return $item }
                }
                else {
                    $stableChecks = 0
                    $previousLength = $item.Length
                }
            }
            catch {
                $stableChecks = 0
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "File did not finish copying within 30 seconds: $Path"
}

function Get-FileIdentity([IO.FileInfo]$File) {
    $hash = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash
    return "$($File.Length):$hash"
}

function Test-LabExport([IO.FileInfo]$File) {
    $rows = @(Import-Csv -LiteralPath $File.FullName)
    if ($rows.Count -eq 0) { throw "Lab export contains no rows." }

    $required = @("Ticker", "Verdict", "EV", "RR", "Priority_Rank", "Run_ID")
    $headers = @($rows[0].PSObject.Properties.Name)
    $missing = @($required | Where-Object { $_ -notin $headers })
    if ($missing.Count -gt 0) {
        throw "Lab export is missing columns: $($missing -join ', ')"
    }

    $runIds = @($rows | ForEach-Object { [string]$_.Run_ID } | Where-Object { $_ } | Sort-Object -Unique)
    if ($runIds.Count -ne 1) {
        throw "Expected exactly one nonblank Run_ID; found $($runIds.Count)."
    }

    $eligible = @($rows | Where-Object {
        $_.Verdict -eq "GO" -and
        [double]$_.EV -gt 0 -and
        [double]$_.RR -gt 0
    })

    return [pscustomobject]@{
        RunId = $runIds[0]
        Rows = $rows.Count
        Eligible = $eligible.Count
        Top = @($eligible | Sort-Object { [int]$_.Priority_Rank } | Select-Object -First $MaxCandidates -ExpandProperty Ticker)
    }
}

$state = Read-State
$queue = [Collections.Concurrent.ConcurrentQueue[string]]::new()
$queued = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

function Queue-File([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $name = [IO.Path]::GetFileName($Path)
    if ($name -notlike "avshunter_signals_*.csv") { return }
    if ($queued.Add($Path)) { $queue.Enqueue($Path) }
}

$watcher = [IO.FileSystemWatcher]::new($LabExport, "avshunter_signals_*.csv")
$watcher.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, Size, CreationTime'
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

$subscriptions = @(
    Register-ObjectEvent $watcher Created -Action { Queue-File $Event.SourceEventArgs.FullPath },
    Register-ObjectEvent $watcher Changed -Action { Queue-File $Event.SourceEventArgs.FullPath },
    Register-ObjectEvent $watcher Renamed -Action { Queue-File $Event.SourceEventArgs.FullPath }
)

if ($ProcessNewestExisting) {
    $existing = Get-ChildItem -LiteralPath $LabExport -Filter "avshunter_signals_*.csv" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($existing) { Queue-File $existing.FullName }
}

Write-Host "Watching: $LabExport" -ForegroundColor Cyan
Write-Host "Launcher: $Launcher"
Write-Host "Press Ctrl+C to stop."

try {
    while ($true) {
        $path = $null
        if (-not $queue.TryDequeue([ref]$path)) {
            Wait-Event -Timeout 1 | Out-Null
            continue
        }
        [void]$queued.Remove($path)

        try {
            $file = Wait-ForStableFile $path
            $identity = Get-FileIdentity $file
            if ($state.processed.ContainsKey($file.Name) -and $state.processed[$file.Name] -eq $identity) {
                Write-Host "Already processed: $($file.Name)" -ForegroundColor DarkGray
                continue
            }

            $check = Test-LabExport $file
            Write-Host "Detected: $($file.Name)" -ForegroundColor Green
            Write-Host "Run_ID=$($check.RunId) Rows=$($check.Rows) Eligible=$($check.Eligible)"
            Write-Host "Selected: $($check.Top -join ', ')"

            if ($check.Eligible -eq 0) {
                Write-Warning "No GO signals with positive EV and R:R; automation was not launched."
            }
            else {
                $process = Start-Process -FilePath "cmd.exe" `
                    -ArgumentList @('/c', ('"{0}" {1}' -f $Launcher, $MaxCandidates)) `
                    -WorkingDirectory $RepositoryRoot `
                    -Wait `
                    -PassThru
                Write-Host "Shadow launcher exited with code $($process.ExitCode)."
            }

            $state.processed[$file.Name] = $identity
            Write-State $state
        }
        catch {
            Write-Error "Failed to process '$path': $($_.Exception.Message)" -ErrorAction Continue
        }
    }
}
finally {
    $subscriptions | ForEach-Object { Unregister-Event -SubscriptionId $_.Id -ErrorAction SilentlyContinue }
    $watcher.Dispose()
}
