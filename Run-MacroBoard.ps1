# Build the macro board with the configured data-only/AI publication policy.
param([switch]$NoOpen)
Set-Location -Path $PSScriptRoot
$python = Join-Path $PSScriptRoot 'venv/Scripts/python.exe'
$policy=Get-Content -Raw (Join-Path $PSScriptRoot 'config/macro_delivery_v1.json') | ConvertFrom-Json
$boardArgs=@('-m','macro_board','--refresh')
if($policy.publication_mode -eq 'DATA_ONLY'){$boardArgs+=@('--config',(Join-Path $PSScriptRoot 'data/macro/delivery/data_only_board_config.json'))}
if(-not $NoOpen){$boardArgs+='--open'}
& $python @boardArgs
exit $LASTEXITCODE
