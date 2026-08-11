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
    & uv run python -m lib.api_generator check
    if ($LASTEXITCODE -ne 0) { throw "Committed OpenAPI handoff check failed: $LASTEXITCODE" }
    foreach ($spec in @('contracts/openapi/public.yaml','contracts/openapi/control-plane.yaml')) {
        & uv run python -m openapi_spec_validator $spec
        if ($LASTEXITCODE -ne 0) { throw "OpenAPI validation failed for ${spec}: $LASTEXITCODE" }
    }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw "git diff --check failed: $LASTEXITCODE" }
    $acceptanceConfig = Join-Path $root '.cache/acceptance-config'
    New-Item -ItemType Directory -Path $acceptanceConfig -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'tests/fixtures/config.acceptance.yaml') -Destination (Join-Path $acceptanceConfig 'config.yaml') -Force
    Copy-Item -LiteralPath (Join-Path $root 'config/policy.yaml') -Destination (Join-Path $acceptanceConfig 'policy.yaml') -Force
    $env:LETRON_ACCEPTANCE = '1'
    $env:LETRON_ACCEPTANCE_CONFIG_DIR = $acceptanceConfig
    & .\docker-start.ps1 -Action config
    & .\docker-start.ps1
    & .\docker-start.ps1 -Action verify
    & .\docker-start.ps1 -Action backup
    & .\docker-start.ps1 -Action backup-verify
    & uv run pytest -m integration -q
    if ($LASTEXITCODE -ne 0) { throw "Integration runtime or external delivery gate failed: $LASTEXITCODE" }
} finally {
    Remove-Item Env:LETRON_ACCEPTANCE -ErrorAction SilentlyContinue
    Remove-Item Env:LETRON_ACCEPTANCE_CONFIG_DIR -ErrorAction SilentlyContinue
    Pop-Location
}
