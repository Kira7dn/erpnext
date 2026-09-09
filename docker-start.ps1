[CmdletBinding()]
param(
    [ValidateSet('up','reload','down','restart','ps','logs','config','bootstrap','inspect','verify','backup','backup-verify','config-validate','config-plan','config-apply','policy-validate','policy-export','policy-plan','policy-apply')]
    [string]$Action = 'up',
    [switch]$FollowLogs
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compose = Join-Path $root 'docker-compose.yml'
$configPath = Join-Path $root 'config/config.yaml'
$policyPath = Join-Path $root 'config/policy.yaml'
if ($env:LETRON_ACCEPTANCE -eq '1') {
    if (-not $env:LETRON_ACCEPTANCE_CONFIG_DIR) { throw 'LETRON_ACCEPTANCE_CONFIG_DIR is required in acceptance mode' }
    $configPath = Join-Path $env:LETRON_ACCEPTANCE_CONFIG_DIR 'config.yaml'
    $policyPath = Join-Path $env:LETRON_ACCEPTANCE_CONFIG_DIR 'policy.yaml'
}
if (!(Test-Path -LiteralPath $compose)) { throw "Missing Docker Compose file: $compose" }

$env:PYTHONPATH = (Join-Path $root 'apps/letron_api')
$env:PYTHONUTF8 = '1'

function Invoke-UvPython([string[]]$Arguments) {
    $output = & uv run python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python configuration command failed with exit code $LASTEXITCODE" }
    return $output
}

if ($Action -eq 'config-validate') {
    if (!(Test-Path -LiteralPath $configPath)) { throw "Missing config YAML: $configPath" }
    Write-Host (Invoke-UvPython @('-m','letron_api.system_config','validate','--path',$configPath))
    return
}
if ($Action -eq 'policy-validate') {
    if (!(Test-Path -LiteralPath $policyPath)) { throw "Missing policy YAML: $policyPath" }
    Write-Host (Invoke-UvPython @('-m','letron_api.policy','validate','--path',$policyPath))
    return
}

if (!(Test-Path -LiteralPath $configPath)) { throw "Missing config YAML: $configPath" }
if (!(Test-Path -LiteralPath $policyPath)) { throw "Missing policy YAML: $policyPath" }
$configValidation = Invoke-UvPython @('-m','letron_api.system_config','validate','--path',$configPath)
$policyValidation = Invoke-UvPython @('-m','letron_api.policy','validate','--path',$policyPath)
$bundleValidation = Invoke-UvPython @('-m','letron_api.system_config','bundle-validate','--config',$configPath,'--policy',$policyPath)
$environmentJson = Invoke-UvPython @('-m','letron_api.system_config','env','--path',$configPath,'--format','json')
$environment = $environmentJson | ConvertFrom-Json
foreach ($property in $environment.PSObject.Properties) {
    # Compose interpolation reads the current PowerShell process environment.
    # Write through Env: explicitly so values derived from config/config.yaml
    # are visible without copying runtime configuration into .env.
    Set-Item -Path ("Env:{0}" -f $property.Name) -Value ([string]$property.Value)
}
$envFile = Join-Path $root '.env'
if (Test-Path -LiteralPath $envFile) {
    Get-Content $envFile | ForEach-Object {
        $l = $_.Trim()
        if ($l -and -not $l.StartsWith('#') -and $l.Contains('=')) {
            $parts = $l.Split('=', 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim("'").Trim('"')
            if (-not [Environment]::GetEnvironmentVariable($k, 'Process')) {
                [Environment]::SetEnvironmentVariable($k, $v, 'Process')
            }
        }
    }
}

Write-Host $configValidation
Write-Host $policyValidation
Write-Host $bundleValidation
Write-Host "Configuration valid: project=$env:PROJECT_NAME, image=$env:ERPNEXT_IMAGE (secrets omitted)"

$composeArgs = @('compose','--project-name',$env:PROJECT_NAME,'-f',$compose)
function Invoke-Compose([string[]]$extra) {
    & docker @composeArgs @extra
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }
}

function Invoke-Readiness {
    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.api.health"
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -Method Get
            if ($response.StatusCode -eq 200 -and $response.Content -match '"ok"\s*:\s*true') {
                Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.system_config.audit')
                Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.api.runtime_snapshot')
                $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -Method Get
                if ($response.Content -notmatch '"restart_required"\s*:\s*false') { throw 'Runtime restart acknowledgement is stale' }
                Write-Host "HTTP health verified: $uri"
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    Invoke-Compose @('ps','-a')
    Invoke-Compose @('logs','--tail=80','backend')
    throw "Runtime did not reach zero-drift HTTP readiness within 180 seconds: $uri"
}

function Invoke-ReloadReadiness {
    # frappe.ping is protected by the gateway ingress policy. Use the public
    # integration health endpoint for a real unauthenticated readiness check.
    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.api.health"
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri $uri -Method Get
            if ($response.StatusCode -eq 200 -and $response.Content -match '"ok"\s*:\s*true') {
                Write-Host "Fast reload verified: $uri"
                return
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    Invoke-Compose @('ps','-a')
    Invoke-Compose @('logs','--tail=40','backend')
    throw "Fast reload did not become ready within 20 seconds: $uri"
}

if ($Action -eq 'config') {
    Invoke-Compose @('config','--quiet')
    Write-Host 'Compose, config and policy YAML are valid (secrets omitted)'
    return
}
if ($Action -in @('up','reload','restart','down','ps','logs','bootstrap','inspect','verify','backup','backup-verify','config-plan','config-apply','policy-export','policy-plan','policy-apply')) {
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not available. Start Docker Desktop and retry.' }
}

switch ($Action) {
    'up' {
        Invoke-Compose @('config','--quiet')
        Invoke-Compose @('up','-d','--remove-orphans')
        Invoke-Compose @('ps')
        Invoke-Readiness
    }
    'reload' {
        Invoke-Compose @('restart','backend')
        Invoke-Readiness
    }
    'down' { Invoke-Compose @('down') }
    'restart' { Invoke-Compose @('down'); Invoke-Compose @('up','-d'); Invoke-Compose @('ps'); Invoke-Readiness }
    'ps' { Invoke-Compose @('ps','-a') }
    'logs' { Invoke-Compose ($(if($FollowLogs){@('logs','-f')}else{@('logs','--tail=100')})) }
    'bootstrap' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.tenant_bootstrap.run') }
    'inspect' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.api.runtime_snapshot') }
    'config-plan' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.system_config.plan') }
    'config-apply' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.system_config.sync') }
    'policy-export' {
        $encoded = (& docker @composeArgs exec -T backend bench --site $env:SITE_NAME execute letron_api.policy.export_current_base64)
        if ($LASTEXITCODE -ne 0) { throw "Policy export failed with exit code $LASTEXITCODE" }
        try {
            $content = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($encoded -join '').Trim()))
        } catch {
            throw "Policy export returned invalid base64: $($_.Exception.Message)"
        }
        $temporaryPolicy = "$policyPath.tmp.$PID"
        try {
            [IO.File]::WriteAllText($temporaryPolicy, $content, [Text.UTF8Encoding]::new($false))
            Write-Host (Invoke-UvPython @('-m','letron_api.policy','validate','--path',$temporaryPolicy))
            Move-Item -LiteralPath $temporaryPolicy -Destination $policyPath -Force
        } finally {
            if (Test-Path -LiteralPath $temporaryPolicy) { Remove-Item -LiteralPath $temporaryPolicy -Force }
        }
        Write-Host "Exported native ERPNext business policy to $policyPath"
    }
    'policy-plan' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.policy.plan') }
    'policy-apply' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.policy.sync') }
    # Run the one-shot backup independently of the long-lived scheduled
    # service.  The scheduled service intentionally sleeps forever when
    # backup.enabled is false; waiting on that dependency here made the
    # acceptance gate appear hung instead of producing a backup result.
    'backup' {
        Invoke-Compose @('run','--rm','--no-deps','-e','BACKUP_ENABLED=True','-e','BACKUP_ONCE=True','backup')
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Syncing backup to AWS S3 (letron-erp-backups)..." -ForegroundColor Cyan
            uv run python scripts/backup_to_s3.py
        }
    }
    'backup-verify' { Invoke-Compose @('--profile','operations','run','--rm','--no-deps','backup-verify') }
    'verify' { Invoke-Readiness }
}
