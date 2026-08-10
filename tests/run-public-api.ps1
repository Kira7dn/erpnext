[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    & .\docker-start.ps1 -Action config
    & .\docker-start.ps1 -Action up
    & .\docker-start.ps1 -Action verify
    & uv run pytest tests/integration/test_public_api_runtime.py -m integration -q
} finally {
    Pop-Location
}
