param(
  [ValidateSet("discovery","premarket","evening")]
  [string]$Mode = "discovery"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- Hard anchors ----------
$REPO_ROOT   = Resolve-Path "$PSScriptRoot\.."
$DATA_DIR    = Join-Path $REPO_ROOT "data"
$OUT_DIR     = Join-Path $DATA_DIR "output"
$RUNS_DIR    = Join-Path $OUT_DIR "runs"
$REPORTS_DIR = Join-Path $REPO_ROOT "reports"
$RUN_REPORTS = Join-Path $REPORTS_DIR "runs"

# ---------- Canonical Python (LOCKED) ----------
$PYTHON = Join-Path $REPO_ROOT "venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON)) { throw "Python not found (venvnew): $PYTHON" }

# ---------- Canonical .env (PS loads; Python must NOT) ----------
$ENV_FILE = Join-Path $REPO_ROOT ".env"
if (-not (Test-Path $ENV_FILE)) { throw ".env missing at repo root: $ENV_FILE" }

Get-Content $ENV_FILE | ForEach-Object {
  if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
    $k = $matches[1].Trim()
    $v = $matches[2].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($k, $v)
  }
}

# ---------- Ensure required dirs ----------
New-Item -ItemType Directory -Force $RUNS_DIR     | Out-Null
New-Item -ItemType Directory -Force $RUN_REPORTS  | Out-Null

# ---------- Run identity ----------
$RUN_ID   = Get-Date -Format "yyyyMMdd_HHmmss"
$RUN_DIR  = Join-Path $RUNS_DIR $RUN_ID
$LOG_DIR  = Join-Path $RUN_REPORTS $RUN_ID
New-Item -ItemType Directory -Force $RUN_DIR | Out-Null
New-Item -ItemType Directory -Force $LOG_DIR | Out-Null

$TRANSCRIPT = Join-Path $LOG_DIR "execution_log.txt"
Start-Transcript -Path $TRANSCRIPT -Force | Out-Null

try {
  Write-Host "=== AVSHUNTER ORCHESTRATOR ==="
  Write-Host "Repo      : $REPO_ROOT"
  Write-Host "Run ID    : $RUN_ID"
  Write-Host "Mode      : $Mode"
  Write-Host "Python    : $PYTHON"
  Write-Host "Output dir: $OUT_DIR"
  Write-Host ""

  # ---------- Pre-flight validation ----------
  & (Join-Path $PSScriptRoot "validate-contract.ps1") -Phase "pre" -RepoRoot $REPO_ROOT -OutDir $OUT_DIR

  # ---------- Discovery (existing runner) ----------
  $DISCOVERY = Join-Path $REPO_ROOT "avshunter_discovery_ULTIMATE.py"
  if (-not (Test-Path $DISCOVERY)) { throw "Missing discovery runner: $DISCOVERY" }

  $UNIVERSE = Join-Path $DATA_DIR "universe\hybrid_universe_enhanced.csv"
  if (-not (Test-Path $UNIVERSE)) { throw "Universe missing: $UNIVERSE" }

  Write-Host ">>> Running discovery..."
  & $PYTHON $DISCOVERY --universe $UNIVERSE --output_dir $OUT_DIR --force-update --progress-every 100

  if ($LASTEXITCODE -ne 0) { throw "Discovery process failed (exit code $LASTEXITCODE)" }

  # ---------- Optional: premarket (if you want it wired now) ----------
  if ($Mode -eq "premarket" -or $Mode -eq "evening") {
    $PREMARKET = Join-Path $REPO_ROOT "premarket_intelligence_ULTIMATE.py"
    if (Test-Path $PREMARKET) {
      Write-Host ">>> Running premarket intelligence..."
      & $PYTHON $PREMARKET --input_dir $OUT_DIR --output_dir $OUT_DIR
      if ($LASTEXITCODE -ne 0) { throw "Premarket process failed (exit code $LASTEXITCODE)" }
    } else {
      Write-Host "Premarket script not found; skipping: $PREMARKET"
    }
  }

  # ---------- Post-run validation ----------
  & (Join-Path $PSScriptRoot "validate-contract.ps1") -Phase "post" -RepoRoot $REPO_ROOT -OutDir $OUT_DIR

  # ---------- Publish (creates run folder artefacts + latest.json) ----------
  & (Join-Path $PSScriptRoot "publish-contract.ps1") -RepoRoot $REPO_ROOT -OutDir $OUT_DIR -RunId $RUN_ID

  Write-Host ""
  Write-Host "✅ RUN COMPLETE: $RUN_ID"
}
catch {
  Write-Host ""
  Write-Host "❌ RUN FAILED: $RUN_ID"
  Write-Host $_.Exception.Message
  throw
}
finally {
  Stop-Transcript | Out-Null
}
