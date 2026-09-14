[CmdletBinding()]
param(
    [switch]$Commit,
    [switch]$IssueB09,
    [string]$SamplePath = 'fixtures/tt99/tt99-vnd-realistic.json'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sample = Join-Path (Join-Path $root 'config') $SamplePath
if (!(Test-Path -LiteralPath $sample)) { throw "Missing TT99 sample: $sample" }

# The launcher loads config-derived Compose environment, synchronizes policy,
# verifies the backend, and passes the fixture path into the mounted config
# directory inside backend. Dry-run/rollback is the default; use -Commit only
# for an explicitly disposable acceptance site.
& (Join-Path $root 'docker-start.ps1') -Action tt99-sample -SamplePath $SamplePath -CommitSample:$Commit -IssueSampleB09:$IssueB09
if ($LASTEXITCODE -ne 0) { throw "TT99 sample apply failed with exit code $LASTEXITCODE" }
