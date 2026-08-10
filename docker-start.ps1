[CmdletBinding()]
param(
    [ValidateSet('up','down','restart','ps','logs','config','seed','inspect','verify')]
    [string]$Action = 'up',
    [switch]$FollowLogs,
    [switch]$ValidateOnly,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.yml')
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compose = Join-Path $root 'docker-compose.yml'
if (!(Test-Path -LiteralPath $compose)) { throw "Missing Docker Compose file: $compose" }
if (!(Test-Path -LiteralPath $ConfigPath)) { throw "Missing YAML configuration: $ConfigPath" }

function Convert-Scalar([string]$Value) {
    $v = $Value.Trim()
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) { return $v.Substring(1, $v.Length-2) }
    if ($v -match '^(true|false)$') { return [bool]::Parse($v) }
    if ($v -match '^-?\d+$') { return [int]$v }
    return $v
}

function Read-Config([string]$Path) {
    $out = @{}
    $stack = @(@(-1, ''))
    foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $raw -replace "`t", '  '
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith('#')) { continue }
        $indent = $line.Length - $line.TrimStart().Length
        $text = $line.Trim()
        if ($text -notmatch '^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$') { throw "Invalid YAML mapping: $raw" }
        $key = $Matches[1]; $value = $Matches[2].Trim()
        while ($stack[-1][0] -ge $indent) { if ($stack.Count -gt 1) { $stack = $stack[0..($stack.Count-2)] } else { break } }
        $prefix = ($stack | Where-Object { $_[1] } | ForEach-Object { $_[1] }) -join '.'
        $full = if ($prefix) { "$prefix.$key" } else { $key }
        if ($value) { $out[$full] = Convert-Scalar $value }
        else { $stack += ,@($indent, $key) }
    }
    return $out
}

function Require($c, [string]$key) {
    if (!$c.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$c[$key])) { throw "Missing required config key: $key" }
    return $c[$key]
}
function Require-Bool($c, [string]$key) { $v=Require $c $key; if ($v -isnot [bool]) { throw "$key must be boolean" }; return $v }
function Require-Int($c, [string]$key, [int]$min, [int]$max) { $v=Require $c $key; if ($v -isnot [int] -or $v -lt $min -or $v -gt $max) { throw "$key must be an integer from $min to $max" }; return $v }
function Redact([string]$v) { if ($v.Length -le 4) { return '****' }; return $v.Substring(0,2)+'****'+$v.Substring($v.Length-2) }

$c = Read-Config $ConfigPath
$required = @('runtime.environment','runtime.image','runtime.platform','runtime.restart_policy','project.name','project.http_port','integration.app_name','integration.app_path','integration.install_on_site','integration.api_enabled','database.image','database.host','database.port','database.root_user','database.root_password','database.charset','database.collation','database.volume','redis.cache','redis.queue','redis.socketio','redis.cache_image','redis.queue_image','site.name','site.header','site.database_type','site.admin_password','locale.country','locale.timezone','locale.language','locale.currency','developer.mode','developer.allow_tests','developer.request_timeout','frontend.backend','frontend.websocket','frontend.upload_size','frontend.proxy_timeout','workers.short_command','workers.long_command','workers.scheduler_command','email.enabled','email.host','email.port','email.username','email.password','email.use_tls','storage.sites_volume','storage.logs_volume','storage.redis_queue_volume','storage.backup_enabled','storage.backup_volume','seed.enabled','seed.company_name','seed.company_abbr','seed.domain','seed.warehouse_name','credentials.production_like')
foreach ($key in $required) { [void](Require $c $key) }
[void](Require-Int $c 'project.http_port' 1 65535); [void](Require-Int $c 'database.port' 1 65535); [void](Require-Int $c 'developer.request_timeout' 1 3600); [void](Require-Int $c 'email.port' 1 65535)
foreach ($key in @('developer.mode','developer.allow_tests','integration.install_on_site','integration.api_enabled','email.enabled','email.use_tls','storage.backup_enabled','seed.enabled','credentials.production_like')) { [void](Require-Bool $c $key) }
if ($c['integration.app_name'] -notmatch '^[a-z][a-z0-9_]*$') { throw 'integration.app_name must be a Python package name' }
$integrationPath = Join-Path $root ([string]$c['integration.app_path'])
if (!(Test-Path -LiteralPath $integrationPath -PathType Container)) { throw "Integration app path does not exist: $integrationPath" }
if (!(Test-Path -LiteralPath (Join-Path $integrationPath ([string]$c['integration.app_name'])) -PathType Container)) { throw "Integration Python package does not exist under: $integrationPath" }
if ($c['site.database_type'] -notin @('mariadb','postgres')) { throw 'site.database_type must be mariadb or postgres' }
if ($c['runtime.environment'] -notin @('local','production-like')) { throw 'runtime.environment must be local or production-like' }
if ($c['credentials.production_like'] -and ($c['database.root_password'] -in @('admin','123','password','change-me-local-db') -or $c['site.admin_password'] -in @('admin','123','password','change-me-local-admin'))) { throw 'Default password is forbidden when credentials.production_like is true' }
if ($c['email.enabled'] -and ($c['email.host'] -eq 'smtp.example.local' -or $c['email.password'] -eq 'change-me')) { throw 'SMTP is enabled but still has placeholder credentials' }

$envMap = @{
    PROJECT_NAME=$c['project.name']; ERPNEXT_IMAGE=$c['runtime.image']; PLATFORM=$c['runtime.platform']; RESTART_POLICY=$c['runtime.restart_policy']; HTTP_PORT=$c['project.http_port']; INTEGRATION_APP=$c['integration.app_name']; INTEGRATION_APP_ENABLED=$c['integration.install_on_site']; INTEGRATION_API_ENABLED=$c['integration.api_enabled'];
    DB_IMAGE=$c['database.image']; DB_HOST=$c['database.host']; DB_PORT=$c['database.port']; DB_ROOT_USER=$c['database.root_user']; DB_ROOT_PASSWORD=$c['database.root_password']; DB_CHARSET=$c['database.charset']; DB_COLLATION=$c['database.collation']; DB_VOLUME=$c['database.volume'];
    REDIS_CACHE=$c['redis.cache']; REDIS_QUEUE=$c['redis.queue']; REDIS_SOCKETIO=$c['redis.socketio']; REDIS_CACHE_IMAGE=$c['redis.cache_image']; REDIS_QUEUE_IMAGE=$c['redis.queue_image']; REDIS_QUEUE_VOLUME=$c['storage.redis_queue_volume'];
    SITE_NAME=$c['site.name']; SITE_HEADER=$c['site.header']; ADMIN_PASSWORD=$c['site.admin_password']; DEVELOPER_MODE=$c['developer.mode']; ALLOW_TESTS=$c['developer.allow_tests']; REQUEST_TIMEOUT=$c['developer.request_timeout'];
    COUNTRY=$c['locale.country']; TIMEZONE=$c['locale.timezone']; LANGUAGE=$c['locale.language']; CURRENCY=$c['locale.currency']; FRONTEND_BACKEND=$c['frontend.backend']; FRONTEND_WEBSOCKET=$c['frontend.websocket']; FRONTEND_UPLOAD_SIZE=$c['frontend.upload_size']; FRONTEND_PROXY_TIMEOUT=$c['frontend.proxy_timeout'];
    SHORT_COMMAND=$c['workers.short_command']; LONG_COMMAND=$c['workers.long_command']; SCHEDULER_COMMAND=$c['workers.scheduler_command']; EMAIL_ENABLED=$c['email.enabled']; SMTP_HOST=$c['email.host']; SMTP_PORT=$c['email.port']; SMTP_USERNAME=$c['email.username']; SMTP_PASSWORD=$c['email.password']; SMTP_USE_TLS=$c['email.use_tls'];
    SITES_VOLUME=$c['storage.sites_volume']; LOGS_VOLUME=$c['storage.logs_volume']; BACKUP_VOLUME=$c['storage.backup_volume']; SEED_ENABLED=$c['seed.enabled']; COMPANY_NAME=$c['seed.company_name']; COMPANY_ABBR=$c['seed.company_abbr']; COMPANY_DOMAIN=$c['seed.domain']; WAREHOUSE_NAME=$c['seed.warehouse_name']
}
foreach ($entry in $envMap.GetEnumerator()) {
    # Frappe bench set-config parses -p values with Python ast.literal_eval,
    # so booleans must be emitted as Python True/False, not JSON true/false.
    $textValue = if ($entry.Value -is [bool]) { $entry.Value.ToString() } else { [string]$entry.Value }
    [Environment]::SetEnvironmentVariable($entry.Key, $textValue, 'Process')
}
Write-Host "Configuration valid: project=$($c['project.name']), image=$($c['runtime.image']), db_password=$(Redact $c['database.root_password']), admin_password=$(Redact $c['site.admin_password'])"

$composeArgs = @('compose','--project-name',$c['project.name'],'-f',$compose)
function Invoke-Compose([string[]]$extra) { & docker @composeArgs @extra; if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" } }
if ($ValidateOnly) { return }
if ($Action -eq 'config') { Invoke-Compose @('config','--quiet'); Write-Host 'Compose configuration valid (secrets omitted)'; return }
if ($Action -in @('up','restart','down','ps','logs','seed','inspect','verify')) {
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not available. Start Docker Desktop and retry.' }
}
switch ($Action) {
    'up' { Invoke-Compose @('config','--quiet'); Invoke-Compose @('up','-d'); Invoke-Compose @('ps') }
    'down' { Invoke-Compose @('down') }
    'restart' { Invoke-Compose @('down'); Invoke-Compose @('up','-d'); Invoke-Compose @('ps') }
    'ps' { Invoke-Compose @('ps','-a') }
    'logs' { Invoke-Compose ($(if($FollowLogs){@('logs','-f')}else{@('logs','--tail=100')})) }
    'seed' { Invoke-Compose @('run','--no-deps','--rm','seed') }
    'inspect' { Invoke-Compose @('exec','-T','backend','bench','--site',$c['site.name'],'execute','letron_api.api.runtime_snapshot') }
    'verify' {
        Invoke-Compose @('exec','-T','backend','bench','--site',$c['site.name'],'execute','letron_api.api.runtime_snapshot')
        $uri = "http://localhost:$($c['project.http_port'])/api/method/letron_api.api.health"
        $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -Method Get
        if ($response.StatusCode -ne 200 -or $response.Content -notmatch '"ok"\s*:\s*true') { throw "Health verification failed: $($response.StatusCode)" }
        Write-Host "HTTP health verified: $uri"
    }
}
