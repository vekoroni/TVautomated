<#
AVSHUNTER daily mini-automation (v3.2, 17 Oct 2026: option closes left to the post-close monitor, one writer; history in git). Nothing to edit: every date, run id and folder is read from the files.
Run from any PowerShell window:
    & C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 <step>

Steps
    status    (default) work out today's context and write data\scratch\workaround\today_context.json + .md
    evening   split chain for the newest pipeline run: ledger -> options -> hand-off -> comparison with the previous hand-off
              (finished run: builds now and reuses the run's chains from Phantom; running run: waits for Vanguard and the options stage)
    preopen   check yesterday's pre-close and ledger decisions, score yesterday, rebuild the macro board, measure Phantom coverage,
              re-apply the premium cap if it changed, refresh the comparison
    packs     build ticker packs: batch 1 of today's hand-off (-Batch 2 for batch 2, or -Tickers IGV NAT ...)
    board     rebuild the macro board (e.g. after CPI) and refresh today_context: re-tag money before more deep dives
    checktriage  check the scheduled triage's output (no credits): PASS / WARN / FAIL. Start the deep dives only on PASS or WARN
    preclose  collect the day's card decisions into order tickets, then run the pre-close trigger scan (about 20:10 UK)
    eod       end of day (after 21:00 UK): re-collect decisions, score today's ledger, list cards with no recorded order
              (option closes are written by the post-close monitor to monitor\option_closes.csv)
Options
    -Cap 3    change the premium cap (saved in day_settings.json and used from then on; default 5)
Every step ends by rewriting today_context.json, which the chat prompts read instead of placeholders.
#>
param(
    [Parameter(Position = 0)][ValidateSet('status', 'evening', 'preopen', 'packs', 'board', 'checktriage', 'preclose', 'eod')][string]$Step = 'status',
    [double]$Cap = 0,
    [int]$Batch = 1,
    [string[]]$Tickers
)
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path   # the repo root (this script lives in data\scratch\workaround)
Set-Location $Root
$W = 'data\scratch\workaround'
$Py = Join-Path $Root 'venv\Scripts\python.exe'
$Settings = Join-Path $W 'day_settings.json'

# ---------------------------------------------------------------- settings (premium cap)
$S = @{ cap = 5 }
if (Test-Path $Settings) { $j = Get-Content $Settings -Raw | ConvertFrom-Json; if ($j.cap) { $S.cap = [double]$j.cap } }
if ($Cap -gt 0) { $S.cap = $Cap; ($S | ConvertTo-Json) | Set-Content $Settings -Encoding UTF8; "Premium cap set to $Cap (saved)" }
$CapLabel = ([double]$S.cap).ToString('0.##', [Globalization.CultureInfo]::InvariantCulture)

function Get-LedgerDates {
    Get-ChildItem $W -Filter 'decision_ledger_*.csv' | ForEach-Object {
        if ($_.Name -match '^decision_ledger_(\d{4}-\d{2}-\d{2})\.csv$') { $Matches[1] } } | Sort-Object
}

function Get-Context {
    $run = Get-ChildItem 'data\output\runs' -Directory | Where-Object Name -match '^\d{8}_\d{6}$' | Sort-Object Name | Select-Object -Last 1
    $done = Test-Path (Join-Path $run.FullName 'final_run_manifest.json')
    $mode = if (Get-ChildItem (Join-Path $run.FullName 'morning_validation') -Filter 'morning_validated_trades_*.csv' -ErrorAction SilentlyContinue) { 'Morning' } else { 'Evening' }
    $receipt = Join-Path $W "thesis_handover_$($run.Name).json"
    $dates = @(Get-LedgerDates)
    $session = if (Test-Path $receipt) { (Get-Content $receipt -Raw | ConvertFrom-Json).decision_session } else { $dates | Select-Object -Last 1 }
    $prev = $dates | Where-Object { $_ -lt $session } | Select-Object -Last 1
    $split = Join-Path $W "handoff\split_${session}_cap$CapLabel"
    if (-not (Test-Path $split)) {   # the cap changed after the hand-off was built: point at the newest hand-off for the session
        $any = Get-ChildItem (Join-Path $W 'handoff') -Directory -Filter "split_${session}*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
        if ($any) { $split = $any.FullName.Substring($Root.Length + 1) }
    }
    $morning = Join-Path $W "handoff\morning_$session"
    $packs = Get-ChildItem 'data\scratch\ticker_packs' -Directory -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $board = Get-Item 'macro_board\output\etf_macro_board.html' -ErrorAction SilentlyContinue
    $boardBuilt = $null   # the board's own build time (BOARD.built_at_utc), not the file time (14 Oct: context said 10:22 after a 13:43 rebuild)
    if ($board) {
        $m = Select-String -Path $board.FullName -Pattern '"built_at_utc"\s*:\s*"([^"]+)"' -List -ErrorAction SilentlyContinue
        $boardBuilt = if ($m) { $m.Matches[0].Groups[1].Value } else { $board.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mmZ') + ' (file time)' }
    }
    $prompts = Join-Path $split "deep_dive_prompts_$session.md"
    $cards = Join-Path $split "cards_$session.csv"
    $tickets = Join-Path $split "order_tickets_$session.md"
    $pre = Get-ChildItem (Join-Path $W 'preclose') -Filter "preclose_${session}_*.md" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $preprev = Get-ChildItem (Join-Path $W 'preclose') -Filter "preclose_${prev}_*.md" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $cmp = Get-ChildItem $split -Filter 'compare_vs_*.md' -ErrorAction SilentlyContinue | Select-Object -Last 1
    $triage = Get-ChildItem $split -Filter 'batch*_triage_*.csv' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    # packs_ready: the newest pack folder is newer than the run and holds a pack for every hand-off batch-1 name (the scheduled triage's gate)
    $packsReady = $false; $packsMissing = @()
    if ($packs -and (Test-Path (Join-Path $split 'handoff.csv')) -and ($packs.Name -gt $run.Name)) {
        $b1 = @(Import-Csv (Join-Path $split 'handoff.csv') | Where-Object { $_.batch -eq '1' } | ForEach-Object { $_.ticker.ToUpper() })
        $packsMissing = @($b1 | Where-Object { -not (Test-Path (Join-Path $packs.FullName "$($_)_pack.zip")) })
        $packsReady = ($b1.Count -gt 0) -and ($packsMissing.Count -eq 0)
    }
    $chk = Join-Path $split "check_triage_$session.md"
    $chkVerdict = if (Test-Path $chk) { ((Get-Content $chk -TotalCount 1) -split ': ')[-1] } else { $null }
    [ordered]@{
        written_local       = (Get-Date).ToString('yyyy-MM-dd HH:mm')
        session             = $session
        previous_session    = $prev
        premium_cap         = [double]$S.cap
        run_id              = $run.Name
        run_state           = $(if ($done) { 'finished' } else { 'running' })
        run_mode            = $mode
        ledger              = "$W\decision_ledger_$session.csv"
        previous_ledger     = "$W\decision_ledger_$prev.csv"
        split_handoff       = $split
        split_handoff_built = (Test-Path (Join-Path $split 'handoff.csv'))
        split_triage_files  = @($triage)
        comparison          = $(if ($cmp) { Join-Path $split $cmp.Name } else { $null })
        morning_folder      = $(if (Test-Path $morning) { $morning } else { $null })
        packs_folder        = $(if ($packs) { "data\scratch\ticker_packs\$($packs.Name)" } else { $null })
        packs_ready         = $packsReady
        packs_missing       = @($packsMissing)
        triage_check        = $chkVerdict
        macro_board_built   = $boardBuilt
        deep_dive_prompts   = $(if (Test-Path $prompts) { $prompts } else { $null })   # null = B3 has not saved it yet
        cards               = $(if (Test-Path $cards) { $cards } else { $null })
        order_tickets       = $(if (Test-Path $tickets) { $tickets } else { $null })
        preclose_today      = $(if ($pre) { "$W\preclose\$($pre.Name)" } else { $null })
        preclose_previous   = $(if ($preprev) { "$W\preclose\$($preprev.Name)" } else { $null })
        lab_book            = "data\output\runs\$($run.Name)\intelligence_lab"
    }
}

function Write-Context {
    $c = Get-Context
    $c | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $W 'today_context.json') -Encoding UTF8
    $md = @('# AVSHUNTER today context', '') + ($c.GetEnumerator() | ForEach-Object { "- **$($_.Key)**: $($_.Value -join ', ')" })
    $md | Set-Content (Join-Path $W 'today_context.md') -Encoding UTF8
    Write-Host ''
    Write-Host 'today_context.json (read by the chat prompts)'
    $c.GetEnumerator() | ForEach-Object { Write-Host ('  {0,-20} {1}' -f $_.Key, ($_.Value -join ', ')) }
    return $c
}

function Invoke-Compare($c) {
    if ($c.split_handoff_built) { & $Py "$W\compare_split_handoffs.py" --today $c.split_handoff }
}

# ---------------------------------------------------------------- steps
switch ($Step) {

    'status' {
        $c = Write-Context
        if (-not $c.packs_ready) { "Packs not ready for the scheduled triage (missing: $($c.packs_missing -join ' ')): run avs_day.ps1 packs" }
        if ($c.split_triage_files.Count -and -not $c.triage_check) { 'Triage written but not checked: run avs_day.ps1 checktriage before the deep dives' }
        if ($c.split_triage_files.Count -and -not $c.deep_dive_prompts) { 'WARNING: triage exists but deep_dive_prompts_<session>.md is missing: B3 must save it' }
        if ($c.macro_board_built -like '*file time*') { 'Note: board build time read from the file time (BOARD.built_at_utc not found)' }
    }

    'evening' {
        $c = Get-Context
        "Run $($c.run_id) | $($c.run_mode) | $($c.run_state)"
        if (-not $env:MARKETDATA_API_KEY) { 'MarketData key not visible in this window: open a fresh PowerShell window and run again.'; break }
        $done = $c.run_state -eq 'finished'
        $receipt = "$W\thesis_handover_$($c.run_id).json"
        if (Test-Path $receipt) { "Ledger for run $($c.run_id) already built: reusing it" }
        else {
            if ($done) { & $Py "$W\build_thesis_ledger.py" --run $c.run_id } else { & $Py "$W\build_thesis_ledger.py" --run $c.run_id --wait }
            if ($LASTEXITCODE -ne 0) { "Ledger build failed (exit $LASTEXITCODE)"; break }
        }
        $c = Get-Context
        $out = "$W\handoff\split_$($c.session)_cap$CapLabel"
        "Hand-off is for session $($c.session), cap `$$CapLabel"
        if (Test-Path "$out\handoff.csv") { "Hand-off already built: $out" }
        else {
            if ($done) { & $Py "$W\avshunter_options_standalone.py" --ledger $c.ledger --reuse-phantom --workers 2 --max-premium $S.cap }
            else { & $Py "$W\avshunter_options_standalone.py" --ledger $c.ledger --wait-pipeline-options --workers 2 --max-premium $S.cap }
            if ($LASTEXITCODE -ne 0) { "Options tool failed (exit $LASTEXITCODE)"; break }
            & $Py "$W\build_mining_handoff.py" --ledger $c.ledger --out $out
            if ($LASTEXITCODE -ne 0) { "Hand-off build failed (exit $LASTEXITCODE)"; break }
        }
        $c = Write-Context
        Invoke-Compare $c
        $null = Write-Context
    }

    'preopen' {
        $c = Get-Context
        $p = $c.previous_session
        "== 1. Previous session ${p}: pre-close scan and recorded decisions"
        $scans = Get-ChildItem "$W\preclose" -Filter "preclose_${p}_*.csv" -ErrorAction SilentlyContinue
        if ($scans) {
            foreach ($s in $scans) {
                $hhmm = [int]($s.BaseName -split '_')[-1]
                $ok = if ($hhmm -ge 1930 -and $hhmm -le 2059) { 'OK (before the close)' } else { 'LATE or EARLY: could not drive a close entry' }
                "  $($s.Name)  $ok"
            }
        } else { "  NO PRE-CLOSE SCAN FOR ${p}: record that day's cards as MISSED or WATCH, not TRADE" }
        if (Test-Path $c.previous_ledger) {
            $L = Import-Csv $c.previous_ledger
            $D = @($L | Where-Object { $_.decision })
            "  Decisions recorded in the ledger: $($D.Count) of $($L.Count)"
            $D | Select-Object ledger_id, decision, contract_symbol, entry_premium | Format-Table -AutoSize | Out-String
            if ($D.Count -lt 2) { '  Few decisions recorded: run the end-of-day recording prompt (E1) for that session before trusting the comparison.' }
        }
        "== 2. Score the previous session"
        & $Py "$W\track_outcomes.py" $c.previous_ledger
        "== 3. Rebuild the macro board"
        & (Join-Path $Root 'Run-MacroBoard.ps1')
        "== 4. Phantom coverage"
        & $Py "$W\probe_chain_reuse.py"
        "== 5. Premium cap `$$CapLabel"
        $want = "$W\handoff\split_$($c.session)_cap$CapLabel"
        if (-not (Test-Path "$want\handoff.csv")) {
            $opt = Get-ChildItem 'data\scratch\options_intel' -Directory | Sort-Object Name | Select-Object -Last 1
            "  Cap changed: re-picking contracts from $($opt.Name) (saved chains, no credits)"
            & $Py "$W\avshunter_options_standalone.py" --ledger $c.ledger --offline-chain "$($opt.FullName)\chain_raw.csv.gz" --max-premium $S.cap
            if ($LASTEXITCODE -eq 0) { & $Py "$W\build_mining_handoff.py" --ledger $c.ledger --out $want }
        } else { "  Hand-off already at this cap: $want" }
        "== 6. Comparison with the previous hand-off (now with outcomes)"
        $c = Write-Context
        Invoke-Compare $c
        $null = Write-Context
    }

    'packs' {
        $c = Get-Context
        $list = $Tickers
        if (-not $list) {
            $cmdFile = Join-Path $c.split_handoff 'ticker_pack_command.txt'
            if (-not (Test-Path $cmdFile)) { "No ticker_pack_command.txt in $($c.split_handoff): run the evening step first"; break }
            $lines = Get-Content $cmdFile
            $i = [array]::IndexOf($lines, "# batch $Batch")
            if ($i -lt 0) { "No batch $Batch in $cmdFile"; break }
            $list = ($lines[$i + 1] -split 'ticker_pack.py')[1].Trim() -split '\s+'
        }
        "Building packs for $($list.Count) names: $($list -join ' ')"
        & $Py 'tools\ticker_pack.py' @list
        $null = Write-Context
    }

    'board' {
        & (Join-Path $Root 'Run-MacroBoard.ps1')
        $c = Write-Context
        "Board rebuilt ($($c.macro_board_built)). Before more deep dives: re-tag money for every triaged name against this build (TEVA 14 Oct: AGAINST became WITH after CPI)."
    }

    'checktriage' {
        $c = Get-Context
        & $Py "$W\check_triage.py" --folder $c.split_handoff --session $c.session
        $ok = $LASTEXITCODE -eq 0
        $c = Write-Context
        if ($ok) { "Triage check $($c.triage_check). Deep dives: open a new chat linked to this computer and type:  Run deep dive rank 1 from $($c.deep_dive_prompts)" }
        else { 'Triage check FAIL: do not start the deep dives. Fix the lines above (re-run the triage in a chat with the B3 prompt), then run checktriage again.' }
    }

    'preclose' {
        $c = Get-Context
        & $Py "$W\collect_decisions.py" --folder $c.split_handoff
        & $Py "$W\preclose_trigger_scan.py" --handoff $c.split_handoff
        $c = Write-Context
        "Order tickets: $($c.order_tickets)  <- every TRADE/WATCH card's order; place them or write why not, before 15:55 ET"
        "Attach $($c.preclose_today) and your pre-close macro report to the pre-close decision chat."
    }

    'eod' {
        $c = Get-Context
        & $Py "$W\collect_decisions.py" --folder $c.split_handoff
        & $Py "$W\track_outcomes.py" $c.ledger
        # Option closes: written by the post-close monitor (monitor\option_closes.csv); the local capture_option_closes.py
        # was retired from this step by ACK on 17 Oct 2026 so the file has one writer.
        $c = Write-Context
        if ($c.cards) {
            $open = @(Import-Csv $c.cards | Where-Object { $_.decision -in 'TRADE', 'ENTER', 'WATCH' -and -not $_.order_placed })
            "Cards with a decision but no recorded order: $($open.Count)"
            $open | Select-Object ticker, decision, contract | Format-Table -AutoSize | Out-String
            'For each: order_placed yes/no + fill or reason in decisions\<TICKER>.json (or tell the chat), then run the E1 recording prompt.'
        }
    }
}
