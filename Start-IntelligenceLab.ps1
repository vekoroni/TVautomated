# Start the Lab with the repository's governed runtime. The Lab-local venv
# does not necessarily contain the advisory Interpreter's provider SDK.
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
$lab = Join-Path $PSScriptRoot 'intelligence-lab\intelligence_lab.py'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $lab)) {
    throw 'AVSHUNTER main venv or Intelligence Lab entry point is missing.'
}
Push-Location $PSScriptRoot
try {
    & $python -c 'import flask, flask_cors, anthropic'
    if ($LASTEXITCODE -ne 0) {
        throw 'Lab runtime preflight failed: Flask or Anthropic SDK is unavailable.'
    }
    & $python $lab
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
