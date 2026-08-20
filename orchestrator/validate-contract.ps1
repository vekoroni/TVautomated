param(
  [Parameter(Mandatory=$true)][ValidateSet("pre","post")] [string]$Phase,
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$OutDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Path([string]$p, [string]$msg) {
  if (-not (Test-Path $p)) { throw $msg }
}

# Core directories
$DATA_DIR  = Join-Path $RepoRoot "data"
$UNIVERSE  = Join-Path $DATA_DIR "universe\hybrid_universe_enhanced.csv"

Require-Path $UNIVERSE "Universe file missing: $UNIVERSE"
Require-Path $OutDir   "Output dir missing: $OutDir"

# Pre-flight checks
if ($Phase -eq "pre") {
  $rows = (Import-Csv $UNIVERSE).Count
  if ($rows -lt 3000) { throw "Universe too small ($rows). Expected >= 3000." }
  return
}

# Post-run checks: ensure a discovery summary exists and is sane
$summary = Get-ChildItem $OutDir -Filter "discovery_summary_ultimate_*.json" |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 1

if (-not $summary) { throw "No discovery summary found in $OutDir (expected discovery_summary_ultimate_*.json)" }

$summaryObj = Get-Content $summary.FullName -Raw | ConvertFrom-Json

# Required keys (minimum)
$requiredKeys = @("universe_size","total_candidates","tier_counts")
foreach ($k in $requiredKeys) {
  if (-not ($summaryObj.PSObject.Properties.Name -contains $k)) {
    throw "Summary missing required key: $k ($($summary.FullName))"
  }
}

# Sanity checks
$u = [int]$summaryObj.universe_size
$c = [int]$summaryObj.total_candidates
if ($u -le 0) { throw "Summary universe_size invalid: $u" }
if ($c -lt 0) { throw "Summary total_candidates invalid: $c" }

# Ratio gates (your orchestrator doctrine: 15–25% expected)
$ratio = $c / [double]$u
if ($ratio -lt 0.01) { throw ("Candidate ratio absurdly low: {0:P2}. Likely pipeline break." -f $ratio) }

# We do NOT hard-block if >25% yet; we log it. (Discovery can be wide in transition.)
if ($ratio -gt 0.35) {
  Write-Host ("⚠ Candidate ratio very high: {0:P2}. May be thresholds too loose or data issue." -f $ratio)
}

# Candidates CSV existence (timestamped is fine pre-publish)
$cand = Get-ChildItem $OutDir -Filter "discovery_candidates_ultimate_*.csv" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

if (-not $cand) { throw "No candidates CSV found in $OutDir (expected discovery_candidates_ultimate_*.csv)" }

# Minimal schema check: ticker must exist
$head = Import-Csv $cand.FullName | Select-Object -First 1
if (-not ($head.PSObject.Properties.Name -contains "ticker")) {
  throw "Candidates CSV missing required column 'ticker': $($cand.FullName)"
}
