# ============================================================
# Audit_AVSHUNTER_CompleteFixList_20260521.ps1
# Code-level audit: verifies all 10 fix patterns are deployed.
# Run after each fix. Each check returns PASS or FAIL.
# ============================================================
param([string]$Fix = "ALL")

$BASE = Split-Path $MyInvocation.MyCommand.Path -Parent
$PASS = 0; $FAIL = 0; $results = @()

function Check($fixNum, $desc, $file, $pattern, $mustExist = $true) {
    $path = Join-Path $BASE $file
    if (-not (Test-Path $path)) {
        $results += [PSCustomObject]@{ Fix=$fixNum; Status="FAIL"; Desc=$desc; Detail="FILE NOT FOUND: $file" }
        $script:FAIL++
        return
    }
    $content = Get-Content $path -Raw -Encoding UTF8
    $found = $content -match $pattern
    $pass = ($mustExist -and $found) -or (-not $mustExist -and -not $found)
    $status = if ($pass) { "PASS" } else { "FAIL" }
    $detail = if ($pass) { "Pattern $(if($mustExist){'found'}else{'absent'}) as required" } else {
        if ($mustExist) { "MISSING pattern: $pattern" } else { "UNEXPECTED pattern still present: $pattern" }
    }
    $results += [PSCustomObject]@{ Fix=$fixNum; Status=$status; Desc=$desc; Detail=$detail }
    if ($pass) { $script:PASS++ } else { $script:FAIL++ }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  AVSHUNTER Fix Audit -- 20260521  (Fix: $Fix)" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# ── FIX 8: Single macro snapshot source of truth ─────────────────────────────
if ($Fix -eq "ALL" -or $Fix -eq "8") {
    Check 8 "morning_thesis_validator reads macro_snapshot.json" `
        "morning_thesis_validator.py" "macro_snapshot\.json"
    Check 8 "morning_thesis_validator labels evening_regime_state" `
        "morning_thesis_validator.py" "evening_regime_state"
    Check 8 "morning_thesis_validator labels macro_state_changed" `
        "morning_thesis_validator.py" "macro_state_changed"
    Check 8 "morning_thesis_validator labels morning_regime_state" `
        "morning_thesis_validator.py" "morning_regime_state"
}

# ── FIX 1: EOD_DIRECTION_CONFLICT_REVIEW must pass to morning validator ───────
if ($Fix -eq "ALL" -or $Fix -eq "1") {
    Check 1 "eod_candidate_engine: MITIGATED no longer returns EOD_DIRECTION_CONFLICT_REVIEW" `
        "eod_candidate_engine.py" `
        'return "EOD_DIRECTION_CONFLICT_REVIEW",\s*_str\(row,\s*"direction_conflict_reason"\)' $false
    Check 1 "eod_candidate_engine: MITIGATED_REQUIRES_CONFIRMATION returns EOD_TRIGGER_READY" `
        "eod_candidate_engine.py" `
        'MITIGATED_REQUIRES_CONFIRMATION[\s\S]{1,200}EOD_TRIGGER_READY'
    Check 1 "eod_candidate_engine: direction_conflict_flag set on candidate" `
        "eod_candidate_engine.py" "direction_conflict_flag"
    Check 1 "morning_thesis_validator: handles direction_conflict_flag" `
        "morning_thesis_validator.py" "direction_conflict_flag"
}

# ── FIX 5: Capital gate must not kill tickers when PSE is retired ─────────────
if ($Fix -eq "ALL" -or $Fix -eq "5") {
    # The initial unconditional gate (line ~1163) must be MANUAL not NO
    Check 5 "execution_intelligence_runner: EIL init sets capital_permission=MANUAL not NO" `
        "execution_intelligence_runner.py" 'capital_permission"\]\s*=\s*"MANUAL"'
    Check 5 "execution_intelligence_runner: PSE retired size_note present" `
        "execution_intelligence_runner.py" "PSE retired|PSE_RETIRED|size_note"
    Check 5 "eod_candidate_engine: default capital_permission not NO" `
        "eod_candidate_engine.py" `
        '_str\(row,\s*"capital_permission",\s*"NO"\)' $false
}

# ── FIX 7: Catalyst overlay must propagate end-to-end ────────────────────────
if ($Fix -eq "ALL" -or $Fix -eq "7") {
    Check 7 "intelligent_orchestrator: catalyst truth called before run_morning_validation in premarket" `
        "intelligent_orchestrator.py" `
        'run_catalyst_truth_layer[\s\S]{1,500}run_morning_validation'
    Check 7 "eod_candidate_engine: CATALYST_FIELDS carry-forward" `
        "eod_candidate_engine.py" "CATALYST_FIELDS|catalyst_carry_forward"
    Check 7 "morning_thesis_validator: EVENT_CONVEXITY_WATCH handling" `
        "morning_thesis_validator.py" "EVENT_CONVEXITY_WATCH"
}

# ── FIX 10: options_hard_vetoes must be populated in handoff ─────────────────
if ($Fix -eq "ALL" -or $Fix -eq "10") {
    Check 10 "options_intelligence: hard_vetoes population" `
        "scripts\avshunter_options_intelligence.py" "hard_vetoes|options_hard_vetoes"
    Check 10 "morning_thesis_validator: reads options_hard_vetoes" `
        "morning_thesis_validator.py" "options_hard_vetoes"
    Check 10 "morning_thesis_validator: EARNINGS_WITHIN_DTE handling" `
        "morning_thesis_validator.py" "EARNINGS_WITHIN_DTE"
}

# ── FIX 9: crowd_arrival_components must survive to morning validation ─────────
if ($Fix -eq "ALL" -or $Fix -eq "9") {
    Check 9 "morning_thesis_validator: PRESERVE_FIELDS with crowd_arrival_components" `
        "morning_thesis_validator.py" "crowd_arrival_components"
    Check 9 "morning_thesis_validator: starts morning_row from candidate (dict copy)" `
        "morning_thesis_validator.py" "morning_row\s*=\s*dict\(candidate\)|morning_row\.update\(|PRESERVE_FIELDS"
}

# ── FIX 2: WATCH_FOR_REGIME_FLIP must route to rolling watch lane ─────────────
if ($Fix -eq "ALL" -or $Fix -eq "2") {
    Check 2 "eod_candidate_engine: writes regime_watch CSV" `
        "eod_candidate_engine.py" "regime_watch"
    Check 2 "morning_thesis_validator: reads regime_watch CSV" `
        "morning_thesis_validator.py" "regime_watch"
    Check 2 "morning_thesis_validator: REGIME_WATCH status handling" `
        "morning_thesis_validator.py" "REGIME_WATCH"
}

# ── FIX 3: Discovery must route by horizon, not filter on alignment ───────────
if ($Fix -eq "ALL" -or $Fix -eq "3") {
    Check 3 "discovery: assign_discovery_horizon function exists" `
        "avshunter_discovery_ULTIMATE.py" "assign_discovery_horizon|horizon_bucket"
    Check 3 "discovery: three-horizon routing (1_5d, 6_10d, 11_20d)" `
        "avshunter_discovery_ULTIMATE.py" '1_5d|6_10d|11_20d'
    Check 3 "discovery: NO_SIGNAL_AT_ANY_HORIZON replaces blanket discard" `
        "avshunter_discovery_ULTIMATE.py" "NO_SIGNAL_AT_ANY_HORIZON"
}

# ── FIX 4: Options Intelligence must be horizon-aware + tiered gates ──────────
if ($Fix -eq "ALL" -or $Fix -eq "4") {
    Check 4 "options_intelligence: DTE_CONFIG with horizon buckets" `
        "scripts\avshunter_options_intelligence.py" "DTE_CONFIG|dte_config"
    Check 4 "options_intelligence: tiered contract review (REVIEW_SPREAD)" `
        "scripts\avshunter_options_intelligence.py" "REVIEW_SPREAD|contract_tier"
    Check 4 "options_intelligence: REVIEW_COMPOUND tier" `
        "scripts\avshunter_options_intelligence.py" "REVIEW_COMPOUND"
    Check 4 "options_intelligence: contract rejection log" `
        "scripts\avshunter_options_intelligence.py" "contract_rejection_log"
}

# ── FIX 6: Morning validator must output horizon-aware thesis fields ──────────
if ($Fix -eq "ALL" -or $Fix -eq "6") {
    Check 6 "morning_thesis_validator: thesis_still_valid field" `
        "morning_thesis_validator.py" "thesis_still_valid"
    Check 6 "morning_thesis_validator: feeds_interpreter field" `
        "morning_thesis_validator.py" "feeds_interpreter"
    Check 6 "morning_thesis_validator: tradeable_today field" `
        "morning_thesis_validator.py" "tradeable_today"
    Check 6 "morning_thesis_validator: morning_verdict field" `
        "morning_thesis_validator.py" "morning_verdict"
    Check 6 "morning_thesis_validator: macro not a hard gate (score_macro_for_horizon or macro_score)" `
        "morning_thesis_validator.py" "macro_score|score_macro_for_horizon|macro_state_changed"
}

# Summary
Write-Host ""
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray
$results | Format-Table -AutoSize Fix, Status, Desc
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

$total = $PASS + $FAIL
$colour = if ($FAIL -eq 0) { "Green" } else { "Yellow" }
Write-Host "Results: $PASS PASS / $FAIL FAIL  (of $total checks)" -ForegroundColor $colour

if ($Fix -ne "ALL") {
    $fixResults = $results | Where-Object { $_.Fix -eq $Fix }
    $fixFail = ($fixResults | Where-Object { $_.Status -eq "FAIL" }).Count
    if ($fixFail -eq 0) {
        Write-Host ""
        Write-Host "[PASS]  FIX $Fix" -ForegroundColor Green
        Write-Host ""
        exit 0
    } else {
        Write-Host ""
        Write-Host "[FAIL]  FIX $Fix  ($fixFail checks failed)" -ForegroundColor Red
        $results | Where-Object { $_.Fix -eq $Fix -and $_.Status -eq "FAIL" } | ForEach-Object { Write-Host "  FAIL: $($_.Desc)" -ForegroundColor Red }
        Write-Host ""
        exit 1
    }
}

if ($FAIL -eq 0) {
    Write-Host ""
    Write-Host "[PASS]  ALL 10 FIXES" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host ""
    Write-Host "[FAIL]  AUDIT INCOMPLETE -- $FAIL checks still failing" -ForegroundColor Red
    Write-Host ""
    exit 1
}
