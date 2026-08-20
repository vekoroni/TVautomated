param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$OutDir,
  [Parameter(Mandatory=$true)][string]$RunId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Latest-File([string]$dir, [string]$pattern) {
  return Get-ChildItem $dir -Filter $pattern |
         Sort-Object LastWriteTime -Descending |
         Select-Object -First 1
}

function Coerce-Value($v) {
  if ($null -eq $v) { return $null }
  $s = "$v".Trim()
  if ($s -eq "") { return $null }

  # numeric?
  if ($s -match '^-?\d+(\.\d+)?$') {
    if ($s -match '\.') { return [double]$s }
    return [int]$s
  }

  # boolean?
  if ($s -match '^(true|false)$') { return [bool]$s }

  return $s
}

$OUT_DIR   = $OutDir
$RUNS_DIR  = Join-Path $OUT_DIR "runs"
$RUN_DIR   = Join-Path $RUNS_DIR $RunId
New-Item -ItemType Directory -Force $RUN_DIR | Out-Null

# Locate latest timestamped artefacts
$sum = Latest-File $OUT_DIR "discovery_summary_ultimate_*.json"
$cnd = Latest-File $OUT_DIR "discovery_candidates_ultimate_*.csv"
$ear = Latest-File $OUT_DIR "early_positions_ultimate_*.csv"
$fin = Latest-File $OUT_DIR "final_watchlist_ultimate_*.csv"

if (-not $sum) { throw "Publish failed: missing discovery summary" }
if (-not $cnd) { throw "Publish failed: missing candidates CSV" }

# Copy stable names into run folder
Copy-Item $sum.FullName (Join-Path $RUN_DIR "discovery_summary.json") -Force
Copy-Item $cnd.FullName (Join-Path $RUN_DIR "discovery_candidates.csv") -Force

if ($ear) { Copy-Item $ear.FullName (Join-Path $RUN_DIR "early_positions.csv") -Force }
if ($fin) { Copy-Item $fin.FullName (Join-Path $RUN_DIR "final_watchlist.csv") -Force }

# Create JSON-first candidates from CSV (typed best-effort)
$csvRows = Import-Csv (Join-Path $RUN_DIR "discovery_candidates.csv")
$jsonRows = foreach ($r in $csvRows) {
  $obj = [ordered]@{}
  foreach ($p in $r.PSObject.Properties) {
    $obj[$p.Name] = Coerce-Value $p.Value
  }
  [pscustomobject]$obj
}
$jsonPath = Join-Path $RUN_DIR "discovery_candidates.json"
$jsonRows | ConvertTo-Json -Depth 6 | Out-File $jsonPath -Encoding utf8

# Optional: create JSON for early/final too (if they exist)
$ep = Join-Path $RUN_DIR "early_positions.csv"
if (Test-Path $ep) {
  $rows = Import-Csv $ep
  ($rows | ForEach-Object {
    $o=[ordered]@{}; $_.PSObject.Properties | ForEach-Object { $o[$_.Name]=Coerce-Value $_.Value }; [pscustomobject]$o
  }) | ConvertTo-Json -Depth 6 | Out-File (Join-Path $RUN_DIR "early_positions.json") -Encoding utf8
}

$fw = Join-Path $RUN_DIR "final_watchlist.csv"
if (Test-Path $fw) {
  $rows = Import-Csv $fw
  ($rows | ForEach-Object {
    $o=[ordered]@{}; $_.PSObject.Properties | ForEach-Object { $o[$_.Name]=Coerce-Value $_.Value }; [pscustomobject]$o
  }) | ConvertTo-Json -Depth 6 | Out-File (Join-Path $RUN_DIR "final_watchlist.json") -Encoding utf8
}

# Build run_manifest.json (PS-owned truth)
$manifest = @{
  run_id      = $RunId
  repo_root   = $RepoRoot
  out_dir     = $OutDir
  published_at = (Get-Date).ToString("s")
  artifacts   = @{
    discovery_summary        = "discovery_summary.json"
    candidates_json          = "discovery_candidates.json"
    candidates_csv           = "discovery_candidates.csv"
    early_positions_json     = (Test-Path (Join-Path $RUN_DIR "early_positions.json")) ? "early_positions.json" : $null
    early_positions_csv      = (Test-Path (Join-Path $RUN_DIR "early_positions.csv")) ? "early_positions.csv" : $null
    final_watchlist_json     = (Test-Path (Join-Path $RUN_DIR "final_watchlist.json")) ? "final_watchlist.json" : $null
    final_watchlist_csv      = (Test-Path (Join-Path $RUN_DIR "final_watchlist.csv")) ? "final_watchlist.csv" : $null
  }
}

$manifest | ConvertTo-Json -Depth 6 | Out-File (Join-Path $RUN_DIR "run_manifest.json") -Encoding utf8

# Schema version (locked)
$schemaVersion = "discovery=1.0.0"
$schemaVersion | Out-File (Join-Path $RUN_DIR "schema_version.txt") -Encoding ascii

# latest.json pointer (atomic write)
$latestObj = @{
  run_id        = $RunId
  run_dir       = $RUN_DIR
  schema_version = $schemaVersion
  published_at  = (Get-Date).ToString("s")
  artifacts     = @{
    run_manifest       = "run_manifest.json"
    discovery_summary  = "discovery_summary.json"
    candidates_json    = "discovery_candidates.json"
    candidates_csv     = "discovery_candidates.csv"
  }
}

$tmp = Join-Path $OUT_DIR "latest.tmp.json"
$latestObj | ConvertTo-Json -Depth 6 | Out-File $tmp -Encoding utf8
Move-Item $tmp (Join-Path $OUT_DIR "latest.json") -Force

Write-Host "✅ Published run: $RunId"
Write-Host "   Run dir : $RUN_DIR"
Write-Host "   Latest  : $(Join-Path $OUT_DIR "latest.json")"
