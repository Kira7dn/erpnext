[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    & uv run pytest -q
    if ($LASTEXITCODE -ne 0) { throw "pytest failed: $LASTEXITCODE" }
    & uv run ruff check staging_consumer.py lib apps/letron_api/letron_api tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed: $LASTEXITCODE" }
    & uv run ty check staging_consumer.py lib apps/letron_api/letron_api tests
    if ($LASTEXITCODE -ne 0) { throw "ty failed: $LASTEXITCODE" }
    & uv run python -m lib.api_generator validate
    if ($LASTEXITCODE -ne 0) { throw "contract validation failed: $LASTEXITCODE" }
    & uv run python -m lib.api_generator generate
    if ($LASTEXITCODE -ne 0) { throw "OpenAPI generation failed: $LASTEXITCODE" }
    & uv run python -m openapi_spec_validator contracts/generated/openapi.yaml
    if ($LASTEXITCODE -ne 0) { throw "OpenAPI validation failed: $LASTEXITCODE" }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw "git diff --check failed: $LASTEXITCODE" }
    & .\docker-start.ps1 -Action config
    & .\docker-start.ps1 -Action up
    & .\docker-start.ps1 -Action verify
    & uv run pytest tests/integration/test_extended_api_runtime.py -m integration -q
    if ($LASTEXITCODE -ne 0) { throw "Integration runtime or external delivery gate failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
