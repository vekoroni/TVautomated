<#
AVSHUNTER daily mini-automation (v4.0, 12 Nov 2026: Lab-first hand-off, Lane B Fix B2/B6/B7: the evening step builds the hand-off from the Intelligence Lab's publication (build_lab_handoff.py), packs go to one folder per session, today_context points at the Lab review projection; -LegacyHandoff falls back to the old ledger -> options -> hand-off chain; v3.4, 20 Oct 2026: no step is a gate, FAIL and readiness lines are advisory (ACK); trade-guard store replay of every open ticker forecast after the evening and eod steps, mining\race_replay_store.py --batch; v3.3, 18 Oct 2026: strategy layer S1-S6 after the hand-off, S6 replay at eod; v3.2 17 Oct: option closes left to the post-close monitor, one writer; history in git). Nothing to edit: every date, run id and folder is read from the files.
Run from any PowerShell window:
    & C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 <step>

Steps
    status    (default) work out today's context and write data\scratch\workaround\today_context.json + .md
    evening   hand-off for the newest pipeline run, built from the Lab's publication: handoff\lab_<session>\ (every Lab field as it is,
              plus lb_ flags, order and batches). Also builds the decision ledger as the outcome record (no credits). Needs a COMPLETE
              Lab review projection. After the Lab republishes (the Morning run): avs_day.ps1 evening -Refresh
              With -LegacyHandoff: the old split chain (ledger -> options -> hand-off -> comparison with the previous hand-off)
    preopen   check yesterday's pre-close and ledger decisions, score yesterday, rebuild the macro board, measure Phantom coverage,
              re-apply the premium cap if it changed, refresh the comparison
    strategy  score every hand-off thesis on S1-S6 (strategy_layer.py): strategy_layer_<session>.csv/.md in the hand-off folder
              (the evening step runs it automatically; run it again after a cap change or a re-pick)
    packs     build ticker packs: batch 1 of today's hand-off (-Batch 2 for batch 2, or -Tickers IGV NAT ...). One folder per session
              (data\scratch\ticker_packs\<session>); each pack opens with the Lab card; refused if the Lab publication is not COMPLETE
    board     rebuild the macro board (e.g. after CPI) and refresh today_context: re-tag money before more deep dives
    checktriage  check the scheduled triage's output (no credits): PASS / WARN / FAIL. Start the deep dives only on PASS or WARN
    preclose  collect the day's card decisions into order tickets, then run the pre-close trigger scan (about 20:10 UK)
    guard     rerun hold-matched odds (target vs stop to each forecast's exit date) for every open row of mining\ticker_forecast_log.csv
              on the canonical price store: mining\guard_rerun_<last store bar>.csv (the evening and eod steps run it automatically)
    eod       end of day (after 21:00 UK): re-collect decisions, score today's ledger, S6 profit-capture replay, list cards with no recorded order
              (option closes are written by the post-close monitor to monitor\option_closes.csv)
Options
    -Cap 3    change the premium cap (saved in day_settings.json and used from then on; default 5)
    -LegacyHandoff   use the old hand-off chain from now on (saved in day_settings.json); -LabHandoff switches back (the default)
    -Refresh         with evening: rebuild the Lab hand-off after the Lab republished (the previous set is kept in _rev_<revision>)
Every step ends by rewriting today_context.json, which the chat prompts read instead of placeholders.
#>
param(
    [Parameter(Position = 0)][ValidateSet('status', 'evening', 'preopen', 'strategy', 'packs', 'board', 'checktriage', 'preclose', 'eod', 'guard')][string]$Step = 'status',
    [double]$Cap = 0,
    [int]$Batch = 1,
    [string[]]$Tickers,
    [switch]$LegacyHandoff,
    [switch]$LabHandoff,
    [switch]$Refresh
)
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path   # the repo root (this script lives in data\scratch\workaround)
Set-Location $Root
$W = 'data\scratch\workaround'
$Py = Join-Path $Root 'venv\Scripts\python.exe'
$Settings = Join-Path $W 'day_settings.json'

# ---------------------------------------------------------------- settings (premium cap)
$S = @{ cap = 5; handoff_source = 'LAB' }   # handoff_source: LAB (the Lab's publication, default since 12 Nov 2026) or LEGACY
if (Test-Path $Settings) {
    $j = Get-Content $Settings -Raw | ConvertFrom-Json
    if ($j.cap) { $S.cap = [double]$j.cap }
    if ($j.handoff_source -in 'LAB', 'LEGACY') { $S.handoff_source = [string]$j.handoff_source }
}
if ($Cap -gt 0) { $S.cap = $Cap; ($S | ConvertTo-Json) | Set-Content $Settings -Encoding UTF8; "Premium cap set to $Cap (saved)" }
if ($LegacyHandoff) { $S.handoff_source = 'LEGACY'; ($S | ConvertTo-Json) | Set-Content $Settings -Encoding UTF8; 'Hand-off source set to LEGACY (saved): ledger -> options -> hand-off. Switch back with -LabHandoff' }
elseif ($LabHandoff) { $S.handoff_source = 'LAB'; ($S | ConvertTo-Json) | Set-Content $Settings -Encoding UTF8; 'Hand-off source set to LAB (saved): the Intelligence Lab publication' }
$UseLab = $S.handoff_source -eq 'LAB'
$CapLabel = ([double]$S.cap).ToString('0.##', [Globalization.CultureInfo]::InvariantCulture)

function Format-Utc($v) {
    # Windows PowerShell 5.1 keeps ISO strings from ConvertFrom-Json; PowerShell 7 turns them into dates
    if ($v -is [datetime]) { return $v.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'+00:00'") }
    if ($null -eq $v) { return $null }
    return [string]$v
}

function Invoke-MacroContext($c) {
    # AVS-MACRO-TRIAGE-001 T3 (ACK 20 Nov 2026): join the board's per-ETF intelligence to this session's hand-off,
    # one row per name (triage_macro_context_<session>.csv). Intelligence for the triage; it never changes a rank.
    if (-not $UseLab) { 'Macro context reads the Lab hand-off (lb_ledger_id): not built for the legacy hand-off'; return }
    if (-not (Test-Path (Join-Path $c.handoff 'handoff.csv'))) { "No hand-off for $($c.session) yet: macro context not built"; return }
    & $Py -m macro_board.triage_context --handoff $c.handoff
    if ($LASTEXITCODE -ne 0) { "Macro context not written (exit $LASTEXITCODE): read the NOT WRITTEN line above; until it is, the triage has no board context for its macro columns" }
}

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
    # The Lab publication for the run (B7): the review projection manifest, its revision and state
    $labManifest = "data\output\runs\$($run.Name)\intelligence_lab\review_projection\manifest.json"
    $labRev = $null; $labState = 'MISSING'
    if (Test-Path $labManifest) {
        $lm = Get-Content $labManifest -Raw
        if ($lm -match '"revision"\s*:\s*"([0-9a-f]+)"') { $labRev = $Matches[1] }
        $labState = if ($lm -match '"publication_state"\s*:\s*"([A-Z_]+)"') { $Matches[1] } else { 'NO_STATE' }
    }
    # The Lab hand-off built for this run, if any (its receipt names the session and the revision it was built from)
    $labReceipt = $null
    foreach ($f in @(Get-ChildItem (Join-Path $W 'handoff') -Directory -Filter 'lab_*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
        $rf = Join-Path $f.FullName 'receipt.json'
        if (Test-Path $rf) { try { $r = Get-Content $rf -Raw | ConvertFrom-Json } catch { $r = $null }; if ($r -and $r.run_id -eq $run.Name) { $labReceipt = $r; break } }
    }
    $session = if ($UseLab -and $labReceipt) { $labReceipt.session }
               elseif (Test-Path $receipt) { (Get-Content $receipt -Raw | ConvertFrom-Json).decision_session }
               else { $dates | Select-Object -Last 1 }
    $prev = $dates | Where-Object { $_ -lt $session } | Select-Object -Last 1
    if ($UseLab) { $split = Join-Path $W "handoff\lab_$session" }
    else {
        $split = Join-Path $W "handoff\split_${session}_cap$CapLabel"
        if (-not (Test-Path $split)) {   # the cap changed after the hand-off was built: point at the newest hand-off for the session
            $any = Get-ChildItem (Join-Path $W 'handoff') -Directory -Filter "split_${session}*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
            if ($any) { $split = $any.FullName.Substring($Root.Length + 1) }
        }
    }
    $morning = Join-Path $W "handoff\morning_$session"
    # Packs (B6/B7): one folder per session, never replaced by a later batch. Before 12 Nov the folders were time stamps.
    $packs = Get-Item "data\scratch\ticker_packs\$session" -ErrorAction SilentlyContinue
    $sessionPacks = [bool]$packs
    if (-not $packs) { $packs = Get-ChildItem 'data\scratch\ticker_packs' -Directory -ErrorAction SilentlyContinue | Where-Object Name -match '^\d{8}_\d{6}$' | Sort-Object Name | Select-Object -Last 1 }
    $board = Get-Item 'macro_board\output\etf_macro_board.html' -ErrorAction SilentlyContinue
    $boardBuilt = $null   # the board's own build time (BOARD.built_at_utc), not the file time (14 Oct: context said 10:22 after a 13:43 rebuild)
    if ($board) {
        $m = Select-String -Path $board.FullName -Pattern '"built_at_utc"\s*:\s*"([^"]+)"' -List -ErrorAction SilentlyContinue
        $boardBuilt = if ($m) { $m.Matches[0].Groups[1].Value } else { $board.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mmZ') + ' (file time)' }
    }
    # Board macro context for the hand-off names (AVS-MACRO-TRIAGE-001 T3, ACK 20 Nov 2026): one row per ledger id,
    # written by macro_board.triage_context from the board's per-ETF intelligence; the triage fills its macro columns from it.
    $mcCsv = Join-Path $split "triage_macro_context_$session.csv"
    $mcJson = Join-Path $split "triage_macro_context_$session.json"
    $mcBuilt = $null; $mcNote = $null
    if ((Test-Path $mcCsv) -and (Test-Path $mcJson)) {
        try {
            $mj = Get-Content $mcJson -Raw | ConvertFrom-Json
            $mcBuilt = Format-Utc $mj.board.built_at_utc
            $mcNote = [string]$mj.board_session_note
        } catch { $mcNote = 'UNREADABLE' }
    }
    $prompts = Join-Path $split "deep_dive_prompts_$session.md"
    $promptsB1 = Join-Path $split "deep_dive_prompts_${session}_b1.md"   # batch 1 may be saved with _b1 (19 Nov 2026); unsuffixed wins
    if (-not (Test-Path $prompts) -and (Test-Path $promptsB1)) { $prompts = $promptsB1 }
    $strat = Join-Path $split "strategy_layer_$session.csv"
    $cards = Join-Path $split "cards_$session.csv"
    $tickets = Join-Path $split "order_tickets_$session.md"
    $pre = Get-ChildItem (Join-Path $W 'preclose') -Filter "preclose_${session}_*.md" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $preprev = Get-ChildItem (Join-Path $W 'preclose') -Filter "preclose_${prev}_*.md" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    $cmp = Get-ChildItem $split -Filter 'compare_vs_*.md' -ErrorAction SilentlyContinue | Select-Object -Last 1
    $triage = Get-ChildItem $split -Filter 'batch*_triage_*.csv' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    # packs_ready: computed per batch (B7). A batch is ready when the pack folder holds a pack for every name of the batch.
    # packs_ready (the scheduled triage's gate) stays the batch-1 answer; packs_ready_batches lists every ready batch.
    $packsReady = $false; $packsMissing = @(); $readyBatches = @(); $batchNames = @{}   # batch number -> tickers
    if (Test-Path (Join-Path $split 'handoff.csv')) {
        if ($UseLab) {   # the batch lists are the hand-off's pack command files (cheaper than reading 2,000 rows)
            foreach ($f in @(Get-ChildItem (Join-Path $split 'pack_commands') -Filter 'ticker_pack_command_*.txt' -ErrorAction SilentlyContinue)) {
                $n = [int]($f.BaseName -split '_')[-1]
                $line = Get-Content $f.FullName | Where-Object { $_ -match 'ticker_pack\.py' } | Select-Object -First 1
                if ($line) { $batchNames[$n] = @((($line -split 'ticker_pack\.py')[1] -split '--')[0].Trim() -split '\s+' | ForEach-Object { $_.ToUpper() }) }
            }
        } else {
            Import-Csv (Join-Path $split 'handoff.csv') | Group-Object batch | ForEach-Object { $batchNames[[int]$_.Name] = @($_.Group | ForEach-Object { $_.ticker.ToUpper() }) }
        }
    }
    if ($packs -and $batchNames.Count -and ($sessionPacks -or $packs.Name -gt $run.Name)) {
        foreach ($n in ($batchNames.Keys | Sort-Object)) {
            $miss = @($batchNames[$n] | Where-Object { -not (Test-Path (Join-Path $packs.FullName "$($_)_pack.zip")) })
            if ($miss.Count -eq 0) { $readyBatches += $n }
            if ($n -eq 1) { $packsMissing = $miss }
        }
        $packsReady = $readyBatches -contains 1
    } elseif ($batchNames.ContainsKey(1)) { $packsMissing = @($batchNames[1]) }
    $guard = Get-ChildItem (Join-Path $W 'mining') -Filter 'guard_rerun_*.csv' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
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
        handoff_source      = $S.handoff_source                                   # LAB = built from the Lab's publication; LEGACY = the old split chain
        handoff             = $split                                              # the hand-off folder (lab_<session> in LAB mode)
        split_handoff       = $split                                              # same folder: kept so existing prompts and scripts keep working
        split_handoff_built = (Test-Path (Join-Path $split 'handoff.csv'))
        handoff_lab_revision = $(if ($UseLab -and $labReceipt) { $labReceipt.lab_revision } else { $null })   # the Lab revision the hand-off was built from
        handoff_matches_lab = $(if ($UseLab -and $labReceipt) { $labReceipt.lab_revision -eq $labRev } else { $null })   # False = the Lab republished: evening -Refresh
        split_triage_files  = @($triage)
        comparison          = $(if ($cmp) { Join-Path $split $cmp.Name } else { $null })
        morning_folder      = $(if (Test-Path $morning) { $morning } else { $null })
        packs_folder        = $(if ($packs) { "data\scratch\ticker_packs\$($packs.Name)" } else { $null })
        packs_ready         = $packsReady                                         # batch 1 (the scheduled triage's gate)
        packs_ready_batches = @($readyBatches)                                    # every batch whose names all have a pack
        packs_missing       = @($packsMissing)                                    # batch 1 names without a pack
        triage_check        = $chkVerdict
        macro_board_built   = $boardBuilt
        macro_context       = $(if (Test-Path $mcCsv) { $mcCsv } else { $null })      # board macro context per hand-off name (by ledger_id)
        macro_context_built = $mcBuilt                                            # the board build it was joined from
        macro_context_note  = $mcNote                                             # MATCH / OLDER_BUILD / NEWER_BUILD against the session
        macro_context_current = $(if ($mcBuilt -and $boardBuilt) { $mcBuilt -eq $boardBuilt } else { $null })   # False = board rebuilt since: avs_day.ps1 board
        deep_dive_prompts   = $(if (Test-Path $prompts) { $prompts } else { $null })   # null = B3 has not saved it yet
        strategy_layer      = $(if (Test-Path $strat) { $strat } else { $null })       # null = avs_day.ps1 strategy has not run
        cards               = $(if (Test-Path $cards) { $cards } else { $null })
        order_tickets       = $(if (Test-Path $tickets) { $tickets } else { $null })
        preclose_today      = $(if ($pre) { "$W\preclose\$($pre.Name)" } else { $null })
        preclose_previous   = $(if ($preprev) { "$W\preclose\$($preprev.Name)" } else { $null })
        lab_book            = $labManifest                                        # the Lab review projection manifest (names the database and the card fields)
        lab_revision        = $labRev
        lab_publication_state = $labState
        guard_rerun         = $(if ($guard) { "$W\mining\$($guard.Name)" } else { $null })   # newest trade-guard store replay
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

function Invoke-Strategy($folder) {
    if (Test-Path (Join-Path $folder 'handoff.csv')) {
        & $Py "$W\strategy_layer.py" --folder $folder
        if ($LASTEXITCODE -ne 0) { "Strategy layer failed (exit $LASTEXITCODE): triage can run, cards will have no S1-S6 row" }
    }
}

function Invoke-Guard {
    # Trade guard (20 Oct 2026): store replay of every open forecast row; read-only on the price store and the log
    if (Test-Path "$W\mining\ticker_forecast_log.csv") {
        & $Py "$W\mining\race_replay_store.py" --batch
        if ($LASTEXITCODE -ne 0) { "Guard rerun failed (exit $LASTEXITCODE): cards keep their own odds; run avs_day.ps1 guard again" }
    } else { 'No mining\ticker_forecast_log.csv yet: guard rerun skipped' }
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
        if ($UseLab -and $c.split_handoff_built -and -not $c.macro_context) { 'No board macro context for this hand-off: run avs_day.ps1 packs (or avs_day.ps1 board) to build it' }
        elseif ($c.macro_context_current -eq $false) { "Board macro context is from the build of $($c.macro_context_built); the board was rebuilt at $($c.macro_board_built): run avs_day.ps1 board to refresh it" }
    }

    'evening' {
        $c = Get-Context
        "Run $($c.run_id) | $($c.run_mode) | $($c.run_state) | hand-off source $($c.handoff_source)"
        $done = $c.run_state -eq 'finished'
        if ($UseLab) {
            # Lab-first (12 Nov 2026, Fix B1/B2): the hand-off is the Lab's publication. No options tool, no credits.
            # The decision ledger is still built: it is the outcome record (track_outcomes, pre-close scan), no longer a hand-off source.
            $receipt = "$W\thesis_handover_$($c.run_id).json"
            if (Test-Path $receipt) { "Ledger for run $($c.run_id) already built (outcome record)" }
            elseif ($done) {
                & $Py "$W\build_thesis_ledger.py" --run $c.run_id
                if ($LASTEXITCODE -ne 0) { "Ledger build failed (exit $LASTEXITCODE): the hand-off is still built; outcome tracking for this session needs the ledger" }
            } else { 'Run still in progress: the ledger (outcome record) is built on the next evening step after it finishes' }
            $labArgs = @("$W\build_lab_handoff.py", '--run', $c.run_id)
            if ($Refresh) { $labArgs += '--refresh' }
            & $Py @labArgs
            if ($LASTEXITCODE -ne 0) { "Lab hand-off not built (exit $LASTEXITCODE): read the REFUSED line above. Fallback: avs_day.ps1 evening -LegacyHandoff"; $null = Write-Context; break }
            'Strategy layer and hand-off comparison read the old hand-off layout: not run on the Lab hand-off (see audit\laneb_fixB\99_report.md)'
            "== Board macro context for the hand-off names"
            Invoke-MacroContext (Get-Context)
            "== Trade guard: open forecasts on tonight's price store"
            Invoke-Guard
            $null = Write-Context
            break
        }
        if (-not $env:MARKETDATA_API_KEY) { 'MarketData key not visible in this window: open a fresh PowerShell window and run again.'; break }
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
        if (-not (Test-Path "$out\strategy_layer_$($c.session).csv")) { Invoke-Strategy $out } else { "Strategy layer already built: $out" }
        "== Trade guard: open forecasts on tonight's price store"
        Invoke-Guard
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
        if ($UseLab) { "  Lab hand-off: the cap is a flag (lb_over_cap), no contract is re-picked. After a cap change: avs_day.ps1 evening -Refresh" }
        elseif (-not (Test-Path "$want\handoff.csv")) {
            $opt = Get-ChildItem 'data\scratch\options_intel' -Directory | Sort-Object Name | Select-Object -Last 1
            "  Cap changed: re-picking contracts from $($opt.Name) (saved chains, no credits)"
            & $Py "$W\avshunter_options_standalone.py" --ledger $c.ledger --offline-chain "$($opt.FullName)\chain_raw.csv.gz" --max-premium $S.cap
            if ($LASTEXITCODE -eq 0) { & $Py "$W\build_mining_handoff.py" --ledger $c.ledger --out $want }
            if ($LASTEXITCODE -eq 0) { Invoke-Strategy $want }
        } else { "  Hand-off already at this cap: $want" }
        "== 6. Comparison with the previous hand-off (now with outcomes)"
        $c = Write-Context
        if (-not $UseLab) { Invoke-Compare $c } else { '  Comparison reads the old hand-off layout: not run on the Lab hand-off' }
        $null = Write-Context
    }

    'strategy' {
        $c = Get-Context
        if ($UseLab) { 'The strategy layer reads the old hand-off layout (<TICKER>_<SIDE>.json): not run on the Lab hand-off'; break }
        if (-not $c.split_handoff_built) { "No hand-off for $($c.session) yet: run avs_day.ps1 evening first"; break }
        Invoke-Strategy $c.split_handoff
        $c = Write-Context
        "Strategy layer: $($c.strategy_layer)  (read the .md beside it; checktriage turns its challenges into WARN lines)"
    }

    'packs' {
        $c = Get-Context
        $list = $Tickers
        if (-not $list) {
            if ($UseLab) {
                $cmdFile = Join-Path $c.handoff "pack_commands\ticker_pack_command_$Batch.txt"
                if (-not (Test-Path $cmdFile)) { "No batch $Batch in $($c.handoff)\pack_commands: run the evening step first"; break }
                $line = Get-Content $cmdFile | Where-Object { $_ -match 'ticker_pack\.py' } | Select-Object -First 1
                $list = (($line -split 'ticker_pack\.py')[1] -split '--')[0].Trim() -split '\s+'
            } else {
                $cmdFile = Join-Path $c.split_handoff 'ticker_pack_command.txt'
                if (-not (Test-Path $cmdFile)) { "No ticker_pack_command.txt in $($c.split_handoff): run the evening step first"; break }
                $lines = Get-Content $cmdFile
                $i = [array]::IndexOf($lines, "# batch $Batch")
                if ($i -lt 0) { "No batch $Batch in $cmdFile"; break }
                $list = ($lines[$i + 1] -split 'ticker_pack.py')[1].Trim() -split '\s+'
            }
        }
        "Building packs for $($list.Count) names into data\scratch\ticker_packs\$($c.session): $($list -join ' ')"
        & $Py 'tools\ticker_pack.py' @list --run $c.run_id --session $c.session
        if ($LASTEXITCODE -ne 0) { "Packs not built (exit $LASTEXITCODE): read the REFUSED line above" }
        # Board macro context (T3): built once per board build; later batches reuse it while it is current
        if ($c.macro_context_current) { "Board macro context current (board build $($c.macro_context_built)): $($c.macro_context)" }
        else { Invoke-MacroContext $c }
        $c = Write-Context
        "Packs ready for batches: $(if ($c.packs_ready_batches.Count) { $c.packs_ready_batches -join ', ' } else { 'none' })"
    }

    'guard' {
        Invoke-Guard
        $c = Write-Context
        "Guard rerun: $($c.guard_rerun)  (open it in the card chat; HOLD_MISMATCH and odds changes are judged there)"
    }

    'board' {
        & (Join-Path $Root 'Run-MacroBoard.ps1')
        Invoke-MacroContext (Get-Context)
        $c = Write-Context
        $changed = $null
        $mcJson = Join-Path $c.handoff "triage_macro_context_$($c.session).json"
        if ($c.macro_context_current -and (Test-Path $mcJson)) { try { $changed = (Get-Content $mcJson -Raw | ConvertFrom-Json).changed_money_tag } catch { } }
        if ($c.macro_context_current) {
            "Board rebuilt ($($c.macro_board_built)). Macro context refreshed: $(if ($null -ne $changed) { $changed } else { 'first build,' }) names changed money_tag ($($c.macro_context)). Triage rows written before this build: take money_tag from the file (checktriage flags differences)."
        } else {
            "Board rebuilt ($($c.macro_board_built)), but the macro context was not refreshed (see above): re-tag money for every triaged name against this build by hand (TEVA 14 Oct: AGAINST became WITH after CPI)."
        }
    }

    'checktriage' {
        $c = Get-Context
        if ($UseLab) { & $Py "$W\check_triage.py" --folder $c.handoff --session $c.session --all }
        else { & $Py "$W\check_triage.py" --folder $c.split_handoff --session $c.session }
        $ok = $LASTEXITCODE -eq 0
        $c = Write-Context
        if ($ok) { "Triage check $($c.triage_check). Deep dives: open a new chat linked to this computer and type:  Run deep dive rank 1 from $($c.deep_dive_prompts)" }
        else { "Triage check FAIL (advisory, not a gate): the deep dives can still run; each card carries the FAIL lines on its status strip. To fix: re-run the triage in a chat with the B3 prompt, then checktriage again. Any ticker without a triage row: use the 'Any ticker, any time' prompt in deep_dive_launcher.md." }
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
        Invoke-Guard
        & $Py "$W\strategy_layer.py" --s6-calibrate   # S6: replay every split hand-off contract, lessons\s6_capture_<date>.md
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
