[CmdletBinding()]
param(
    [ValidateSet("up", "down", "restart", "ps", "logs")]
    [string]$Action = "up",
    [switch]$FollowLogs
)

$ErrorActionPreference = "Stop"
$workspaceRoot = $PSScriptRoot
$composeFile = Join-Path $workspaceRoot "docker-compose.yml"
$configFile = Join-Path $workspaceRoot "config.yml"

if (-not (Test-Path -LiteralPath $composeFile)) {
    throw "Missing Docker Compose file: $composeFile"
}
if (-not (Test-Path -LiteralPath $configFile)) {
    throw "Missing YAML configuration: $configFile"
}

function Read-FlatYaml {
    param([Parameter(Mandatory)][string]$Path)

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$') {
            throw "Unsupported config.yml line: $line"
        }

        $key = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "Config value cannot be empty: $key"
        }
        $values[$key] = $value
    }
    return $values
}

$config = Read-FlatYaml -Path $configFile
$required = @(
    "project_name",
    "erpnext_image",
    "platform",
    "http_port",
    "db_root_password",
    "admin_password",
    "restart_policy"
)
foreach ($key in $required) {
    if (-not $config.ContainsKey($key)) {
        throw "Missing required config key: $key"
    }
}

$env:ERPNEXT_IMAGE = $config.erpnext_image
$env:PLATFORM = $config.platform
$env:HTTP_PORT = $config.http_port
$env:DB_ROOT_PASSWORD = $config.db_root_password
$env:ADMIN_PASSWORD = $config.admin_password
$env:RESTART_POLICY = $config.restart_policy

$composeArgs = @("compose", "--project-name", $config.project_name, "-f", $composeFile)

function Invoke-DockerCompose {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed with exit code $LASTEXITCODE"
    }
}

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not available. Start Docker Desktop and retry."
}

switch ($Action) {
    "up" {
        Invoke-DockerCompose -Arguments @("config", "--quiet")
        Invoke-DockerCompose -Arguments @("up", "-d")
        Invoke-DockerCompose -Arguments @("ps")
    }
    "down" {
        Invoke-DockerCompose -Arguments @("down")
    }
    "restart" {
        Invoke-DockerCompose -Arguments @("down")
        Invoke-DockerCompose -Arguments @("up", "-d")
        Invoke-DockerCompose -Arguments @("ps")
    }
    "ps" {
        Invoke-DockerCompose -Arguments @("ps", "-a")
    }
    "logs" {
        $logArgs = if ($FollowLogs) { @("logs", "-f") } else { @("logs", "--tail=100") }
        Invoke-DockerCompose -Arguments $logArgs
    }
}
