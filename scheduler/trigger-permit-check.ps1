# Dispatches the "Permit Check (fast)" GitHub Actions workflow.
# Run by Windows Task Scheduler on the local "server" box at a precise time.
# See scheduler/README.md for setup.

#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$Repo     = 'JeffreyMichel/trailgate'
$Workflow = 'permit-check.yml'
$Ref      = 'main'

$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ('trigger-{0}.log' -f (Get-Date -Format 'yyyy-MM'))
$now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'

function Log([string]$msg) { "$now  $msg" | Add-Content -Encoding utf8 $log }

# --- locate gh ---------------------------------------------------------------
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    foreach ($p in @(
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\gh.exe"
    )) { if (Test-Path $p) { $gh = $p; break } }
}
if (-not $gh) { Log 'ERROR  gh CLI not found on PATH'; exit 1 }

# --- auth token ------------------------------------------------------------
# Prefer an explicit GH_TOKEN / GITHUB_TOKEN, then a local file
# (scheduler/gh_token.txt, git-ignored). A fine-grained PAT with
# "Actions: Read and write" on the trailgate repo is enough.
#
# If none is set we fall through to gh's own stored auth (`gh auth login`).
# That works for interactive runs; for the unattended scheduled task the token
# file is more reliable, since the S4U task may not reach the credential store.
if (-not $env:GH_TOKEN -and $env:GITHUB_TOKEN) { $env:GH_TOKEN = $env:GITHUB_TOKEN }
if (-not $env:GH_TOKEN) {
    $tokenFile = Join-Path $PSScriptRoot 'gh_token.txt'
    if (Test-Path $tokenFile) { $env:GH_TOKEN = (Get-Content -Raw $tokenFile).Trim() }
}
if (-not $env:GH_TOKEN) {
    & $gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Log 'ERROR  no GH_TOKEN, no gh_token.txt, and gh is not logged in'; exit 1 }
    Log 'NOTE  no explicit token; using gh stored auth'
}

# --- dispatch ------------------------------------------------------------
try {
    $out = & $gh workflow run $Workflow -R $Repo --ref $Ref 2>&1
    if ($LASTEXITCODE -ne 0) { Log "ERROR  gh exit $LASTEXITCODE : $out"; exit 1 }
    Log "OK  dispatched $Workflow @ $Ref"
} catch {
    Log "ERROR  $_"
    exit 1
}
