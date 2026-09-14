[CmdletBinding()]
param(
    [ValidateSet('up','build','reload','tt99-sample','down','restart','ps','logs','config','init','migrate','bootstrap','inspect','verify','backup','backup-verify','config-validate','config-plan','config-apply','policy-validate','policy-export','policy-plan','policy-apply')]
    [string]$Action = 'up',
    [switch]$FollowLogs,
    [string]$SamplePath = 'fixtures/tt99/tt99-vnd-realistic.json',
    [switch]$CommitSample,
    [switch]$IssueSampleB09
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compose = Join-Path $root 'docker-compose.yml'
$configPath = Join-Path $root 'config/config.yaml'
$policyPath = Join-Path $root 'config/policy.yaml'
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
    Write-Host (Invoke-UvPython @('-m','letron_api.control.system_config','validate','--path',$configPath))
    return
}
if ($Action -eq 'policy-validate') {
    if (!(Test-Path -LiteralPath $policyPath)) { throw "Missing policy YAML: $policyPath" }
    Write-Host (Invoke-UvPython @('-m','letron_api.control.policy','validate','--path',$policyPath))
    return
}

if (!(Test-Path -LiteralPath $configPath)) { throw "Missing config YAML: $configPath" }
if (!(Test-Path -LiteralPath $policyPath)) { throw "Missing policy YAML: $policyPath" }
$configValidation = Invoke-UvPython @('-m','letron_api.control.system_config','validate','--path',$configPath)
$policyValidation = Invoke-UvPython @('-m','letron_api.control.policy','validate','--path',$policyPath)
$bundleValidation = Invoke-UvPython @('-m','letron_api.control.system_config','bundle-validate','--config',$configPath,'--policy',$policyPath)
$expectedConfig = ($configValidation -join "`n") | ConvertFrom-Json
$expectedPolicy = ($policyValidation -join "`n") | ConvertFrom-Json
$expectedConfigHash = [string]$expectedConfig.sha256
$expectedPolicyHash = [string]$expectedPolicy.sha256
$environmentJson = Invoke-UvPython @('-m','letron_api.control.system_config','env','--path',$configPath,'--format','json')
$environment = $environmentJson | ConvertFrom-Json
foreach ($property in $environment.PSObject.Properties) {
    # Compose interpolation reads the current PowerShell process environment.
    # Write through Env: explicitly so values derived from config/config.yaml
    # are visible without copying runtime configuration into .env.
    Set-Item -Path ("Env:{0}" -f $property.Name) -Value ([string]$property.Value)
}
$envFileNames = if ($env:NODE_ENV -eq 'production') { @('.env.production', '.env') } else { @('.env.local', '.env') }
foreach ($envFileName in $envFileNames) {
    $envFile = Join-Path $root $envFileName
    if (!(Test-Path -LiteralPath $envFile)) { continue }
    Get-Content -LiteralPath $envFile -Encoding utf8 | ForEach-Object {
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

function Test-InitComplete {
    $previousErrorAction = $ErrorActionPreference
    try {
        # Compose writes progress diagnostics to stderr even for a successful
        # probe.  Capture the process exit code without turning that progress
        # stream into a terminating PowerShell error.
        $ErrorActionPreference = 'Continue'
        & docker @composeArgs run --rm --no-deps --entrypoint bash backend-init -lc "test -f sites/$env:SITE_NAME/.letron-init-complete" 1>$null 2>$null
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    return $exitCode -eq 0
}

function Invoke-Init([switch]$Force) {
    if (-not $Force -and (Test-InitComplete)) {
        Write-Host "ERP site initialization already complete; skipping backend-init."
        return
    }
    $mutex = [Threading.Mutex]::new($false, 'Local\LetronERPBackendInit')
    $acquired = $false
    try {
        if (-not $mutex.WaitOne(0)) { throw 'Another ERP init/migration process is already running.' }
        $acquired = $true
        Invoke-Compose @('run','--rm','--no-deps','backend-init')
    } finally {
        if ($acquired) { try { $mutex.ReleaseMutex() } catch { } }
        $mutex.Dispose()
    }
}

function Invoke-Readiness {
    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.control.api.health"
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -Method Get
            if ($response.StatusCode -eq 200 -and $response.Content -match '"ok"\s*:\s*true') {
                Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.system_config.audit')
                Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.api.runtime_snapshot')
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

function Get-HealthState {
    param([int]$TimeoutSeconds = 3)

    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.control.api.health"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $requestTimeout = [Math]::Min(30, [Math]::Max(3, $TimeoutSeconds))
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec $requestTimeout -Uri $uri -Method Get
            if ($response.StatusCode -eq 200) {
                $payload = $response.Content | ConvertFrom-Json
                $message = if ($null -ne $payload.message) { $payload.message } else { $payload }
                if ($message.ok -eq $true) { return $message }
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $null
}

function Get-BackendProcessState {
    param([int]$TimeoutSeconds = 3)

    # Health is intentionally zero-drift and can return HTTP 500 while a
    # policy/config apply is still required.  Runtime info is the independent
    # process/readiness boundary needed before that apply can run.  The health
    # route is used here because the gateway explicitly permits it while
    # runtime_info remains protected.
    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.control.api.health"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $requestTimeout = [Math]::Min(30, [Math]::Max(3, $TimeoutSeconds)) * 1000
    do {
        $response = $null
        try {
            $request = [System.Net.HttpWebRequest]::Create($uri)
            $request.Method = 'GET'
            $request.Timeout = $requestTimeout
            $response = $request.GetResponse()
        } catch [System.Net.WebException] {
            # HTTP 4xx/5xx still proves that Gunicorn and the gateway handled
            # the request.  Only a missing response means process-not-ready.
            $response = $_.Exception.Response
        } catch { }
        if ($null -ne $response) {
            $statusCode = [int]$response.StatusCode
            $response.Close()
            return @{ http_status = $statusCode }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $null
}

function Invoke-ReloadReadiness {
    # frappe.ping is protected by the gateway ingress policy. Use the public
    # integration health endpoint for a real unauthenticated readiness check.
    # This is deliberately health-only. Full drift and metadata verification
    # belongs to Invoke-Readiness, used by up/verify, not every hot reload.
    $uri = "http://localhost:$env:HTTP_PORT/api/method/letron_api.control.api.health"
    $processState = Get-BackendProcessState -TimeoutSeconds 180
    if ($null -ne $processState) {
        $state = Get-HealthState -TimeoutSeconds 3
        if ($null -eq $state) {
            # A non-zero-drift health failure is expected while a changed
            # policy/config is waiting to be applied.  The caller must still
            # be able to reach the sync command.
            $state = @{ ok = $false; config = $null; policy = $null }
            Write-Host "HTTP backend process ready; zero-drift health is pending policy/config apply: $uri"
        } else {
            Write-Host "HTTP health verified for hot operation: $uri"
        }
        return $state
    }
    Invoke-Compose @('ps','-a')
    Invoke-Compose @('logs','--tail=40','backend')
    throw "Backend process did not become ready for hot operation within 180 seconds: $uri"
}

function Invoke-DesiredStateSyncIfChanged($health) {
    $configState = $health.config
    $policyState = $health.policy
    $configChanged = ($null -eq $configState) -or ($configState.sha256 -ne $expectedConfigHash) -or ($configState.status -ne 'in-sync')
    $policyChanged = ($null -eq $policyState) -or ($policyState.sha256 -ne $expectedPolicyHash) -or ($policyState.status -ne 'in-sync')

    if ($configChanged) {
        Write-Host 'Configuration source/runtime state differs; applying system config.'
        Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.system_config.sync')
    } else {
        Write-Host 'System config hash is current; skipping config sync.'
    }

    if ($policyChanged) {
        Write-Host 'Policy source/runtime state differs; applying business policy.'
        Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.policy.sync')
    } else {
        Write-Host 'Policy hash is current; skipping policy sync.'
    }
}

if ($Action -eq 'config') {
    Invoke-Compose @('config','--quiet')
    Write-Host 'Compose, config and policy YAML are valid (secrets omitted)'
    return
}
if ($Action -in @('up','build','reload','tt99-sample','restart','down','ps','logs','init','migrate','bootstrap','inspect','verify','backup','backup-verify','config-plan','config-apply','policy-export','policy-plan','policy-apply')) {
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not available. Start Docker Desktop and retry.' }
}

switch ($Action) {
    'build' {
        Invoke-Compose @('build','backend','lark-bot','openclaw-lark')
    }
    'up' {
        Invoke-Compose @('config','--quiet')
        Invoke-Compose @('up','-d','db','redis')
        Invoke-Init
        Invoke-Compose @('up','-d','--remove-orphans')
        Invoke-Compose @('ps')
        Invoke-Readiness
    }
    'init' { Invoke-Init -Force }
    'migrate' { Invoke-Init -Force }
    'reload' {
        $health = Invoke-ReloadReadiness
        Invoke-DesiredStateSyncIfChanged $health
        Invoke-Compose @('up','-d','--no-build','--force-recreate','backend')
        Invoke-Compose @('up','-d','--no-build','--force-recreate','lark-bot','openclaw-lark')
        Invoke-ReloadReadiness | Out-Null
    }
    'tt99-sample' {
        $sampleFile = Join-Path (Split-Path -Parent $configPath) $SamplePath
        if (!(Test-Path -LiteralPath $sampleFile)) { throw "Missing TT99 sample: $sampleFile" }
        $health = Invoke-ReloadReadiness
        Invoke-DesiredStateSyncIfChanged $health
        Invoke-Compose @('up','-d','--no-build','--force-recreate','backend')
        Invoke-ReloadReadiness | Out-Null
        $sampleMode = if ($CommitSample) { '1' } else { '0' }
        $issueMode = if ($IssueSampleB09) { '1' } else { '0' }
        Invoke-Compose @('exec','-T','-e',"LETRON_TT99_SAMPLE_PATH=$SamplePath",'-e',"LETRON_TT99_SAMPLE_COMMIT=$sampleMode",'-e',"LETRON_TT99_SAMPLE_ISSUE_B09=$issueMode",'backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.tt99_sample.apply')
    }
    'down' { Invoke-Compose @('down') }
    'restart' { Invoke-Compose @('down'); Invoke-Compose @('up','-d'); Invoke-Compose @('ps'); Invoke-Readiness }
    'ps' { Invoke-Compose @('ps','-a') }
    'logs' { Invoke-Compose ($(if($FollowLogs){@('logs','-f')}else{@('logs','--tail=100')})) }
    'bootstrap' { Invoke-ReloadReadiness; Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.policy.sync') }
    'inspect' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.api.runtime_snapshot') }
    'config-plan' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.system_config.plan') }
    'config-apply' { Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.system_config.sync') }
    'policy-export' {
        $encoded = (& docker @composeArgs exec -T backend bench --site $env:SITE_NAME execute letron_api.control.policy.export_current_base64)
        if ($LASTEXITCODE -ne 0) { throw "Policy export failed with exit code $LASTEXITCODE" }
        try {
            $content = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($encoded -join '').Trim()))
        } catch {
            throw "Policy export returned invalid base64: $($_.Exception.Message)"
        }
        $temporaryPolicy = "$policyPath.tmp.$PID"
        try {
            [IO.File]::WriteAllText($temporaryPolicy, $content, [Text.UTF8Encoding]::new($false))
            Write-Host (Invoke-UvPython @('-m','letron_api.control.policy','validate','--path',$temporaryPolicy))
            Move-Item -LiteralPath $temporaryPolicy -Destination $policyPath -Force
        } finally {
            if (Test-Path -LiteralPath $temporaryPolicy) { Remove-Item -LiteralPath $temporaryPolicy -Force }
        }
        Write-Host "Exported native ERPNext business policy to $policyPath"
    }
    # Policy operations need a long enough health wait after a recreate, but
    # do not need the expensive metadata/zero-drift snapshot before Bench.
    'policy-plan' { Invoke-ReloadReadiness | Out-Null; Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.policy.plan') }
    'policy-apply' { Invoke-ReloadReadiness | Out-Null; Invoke-Compose @('exec','-T','backend','bench','--site',$env:SITE_NAME,'execute','letron_api.control.policy.sync') }
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
