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
    $acceptanceAssets = Join-Path $acceptanceConfig 'assets'
    New-Item -ItemType Directory -Path $acceptanceAssets -Force | Out-Null
    Copy-Item -Path (Join-Path $root 'config/assets/*') -Destination $acceptanceAssets -Force
    # Acceptance must be disposable. Keep its site, Compose project, host
    # port, and named volumes separate from the tenant runtime.
    $acceptanceConfigPath = Join-Path $acceptanceConfig 'config.yaml'
    $acceptanceContent = Get-Content -LiteralPath $acceptanceConfigPath -Raw -Encoding UTF8
    $acceptanceContent = $acceptanceContent.Replace('name: erpnext, http_port: 8080', 'name: erpnext-acceptance, http_port: 8082')
    $acceptanceContent = $acceptanceContent.Replace('site: {name: frontend, header: frontend,', 'site: {name: acceptance.local, header: acceptance.local,')
    $acceptanceContent = $acceptanceContent.Replace('volume: db-data', 'volume: erpnext-acceptance-db-data')
    $acceptanceContent = $acceptanceContent.Replace('sites_volume: sites, logs_volume: logs, redis_queue_volume: redis-queue-data, backup_volume: backups', 'sites_volume: erpnext-acceptance-sites, logs_volume: erpnext-acceptance-logs, redis_queue_volume: erpnext-acceptance-redis-queue-data, backup_volume: erpnext-acceptance-backups')
    [IO.File]::WriteAllText($acceptanceConfigPath, $acceptanceContent, [Text.UTF8Encoding]::new($false))
    $acceptancePolicyPath = Join-Path $acceptanceConfig 'policy.yaml'
    $acceptancePolicyContent = Get-Content -LiteralPath $acceptancePolicyPath -Raw -Encoding UTF8
    # A clean site creates the standard English root cost center even when
    # the tenant policy was exported from a Vietnamese-labeled site.
    $acceptancePolicyContent = $acceptancePolicyContent.Replace('Chính - LTVN', 'Main - LTVN')
    [IO.File]::WriteAllText($acceptancePolicyPath, $acceptancePolicyContent, [Text.UTF8Encoding]::new($false))
    $env:LETRON_ACCEPTANCE = '1'
    $env:LETRON_ACCEPTANCE_CONFIG_DIR = $acceptanceConfig
    $env:LETRON_CONSUMER_PORT = '8092'
    & .\docker-start.ps1 -Action config
    & .\docker-start.ps1
    $inventorySummary = & docker exec erpnext-acceptance-backend-1 bash -lc "cd /home/frappe/frappe-bench && env/bin/python -m letron_api.policy_inventory --apps-root /home/frappe/frappe-bench/apps --scope /home/frappe/frappe-bench/contracts/policy-scope.yml --output /tmp/policy-inventory.json"
    if ($LASTEXITCODE -ne 0) { throw "policy scope scanner failed: $LASTEXITCODE" }
    $inventory = ($inventorySummary | Select-Object -Last 1) | ConvertFrom-Json
    foreach ($counter in @('unknown','schema_drift','scope_entries_missing_fingerprint','scope_sources_missing_from_native','managed_entries_without_acceptance')) {
        if ($inventory.$counter -ne 0) { throw "policy scope scanner ${counter}=$($inventory.$counter)" }
    }
    & .\docker-start.ps1 -Action verify
    & .\docker-start.ps1 -Action backup
    & .\docker-start.ps1 -Action backup-verify
    & uv run pytest -m integration -q
    if ($LASTEXITCODE -ne 0) { throw "Integration runtime or external delivery gate failed: $LASTEXITCODE" }
} finally {
    if ($env:LETRON_ACCEPTANCE -eq '1') {
        & docker compose --project-name erpnext-acceptance -f (Join-Path $root 'docker-compose.yml') -f (Join-Path $root 'docker-compose.acceptance.yml') down --volumes --remove-orphans *> $null
    }
    Remove-Item Env:LETRON_ACCEPTANCE -ErrorAction SilentlyContinue
    Remove-Item Env:LETRON_ACCEPTANCE_CONFIG_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:LETRON_CONSUMER_PORT -ErrorAction SilentlyContinue
    Pop-Location
}
