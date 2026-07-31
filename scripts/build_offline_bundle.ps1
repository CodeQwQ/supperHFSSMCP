param(
    [string]$OutputRoot = "",
    [string]$BundleName = "hfss-agent-mcp-offline-win-x64",
    [string]$PythonBase = "",
    [string]$VenvPath = "",
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$PathValue)
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Assert-ChildPath {
    param(
        [string]$Parent,
        [string]$Child
    )
    $parentFull = Resolve-FullPath $Parent
    $childFull = Resolve-FullPath $Child
    if (-not $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside expected root. Parent=$parentFull Child=$childFull"
    }
}

$RepoRoot = Resolve-FullPath (Join-Path $PSScriptRoot "..")
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "dist-offline"
}
$OutputRoot = Resolve-FullPath $OutputRoot

if (-not $VenvPath) {
    $VenvPath = Join-Path $RepoRoot ".venv"
}
$VenvPath = Resolve-FullPath $VenvPath
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python not found: $VenvPython"
}

if (-not $PythonBase) {
    $PythonBase = & $VenvPython -c "import sys; print(sys.base_prefix)"
}
$PythonBase = Resolve-FullPath $PythonBase
if (-not (Test-Path -LiteralPath (Join-Path $PythonBase "python.exe"))) {
    throw "Python runtime not found: $PythonBase"
}

$VenvSitePackages = Join-Path $VenvPath "Lib\site-packages"
if (-not (Test-Path -LiteralPath $VenvSitePackages)) {
    throw "Virtual environment site-packages not found: $VenvSitePackages"
}

$BundleRoot = Join-Path $OutputRoot $BundleName
$RuntimeRoot = Join-Path $BundleRoot "python"
$AppRoot = Join-Path $BundleRoot "app"
$AntennaAppRoot = Join-Path $AppRoot "antenna-design-intelligence-mcp"
$DocsRoot = Join-Path $BundleRoot "docs"
$ScriptsRoot = Join-Path $BundleRoot "scripts"

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Assert-ChildPath -Parent $OutputRoot -Child $BundleRoot
if (Test-Path -LiteralPath $BundleRoot) {
    Remove-Item -LiteralPath $BundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $BundleRoot, $AppRoot, $AntennaAppRoot, $DocsRoot, $ScriptsRoot | Out-Null

Write-Host "Copying Python runtime from $PythonBase"
Copy-Item -LiteralPath $PythonBase -Destination $RuntimeRoot -Recurse -Force

$RuntimeSitePackages = Join-Path $RuntimeRoot "Lib\site-packages"
if (Test-Path -LiteralPath $RuntimeSitePackages) {
    Remove-Item -LiteralPath $RuntimeSitePackages -Recurse -Force
}
Write-Host "Copying Python packages from $VenvSitePackages"
Copy-Item -LiteralPath $VenvSitePackages -Destination $RuntimeSitePackages -Recurse -Force

Write-Host "Copying application source"
Copy-Item -LiteralPath (Join-Path $RepoRoot "src") -Destination (Join-Path $AppRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "pyproject.toml") -Destination $AppRoot -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "antenna-design-intelligence-mcp\src") -Destination (Join-Path $AntennaAppRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "antenna-design-intelligence-mcp\pyproject.toml") -Destination $AntennaAppRoot -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "antenna-design-intelligence-mcp\README.md") -Destination $AntennaAppRoot -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "antenna-design-intelligence-mcp\docs") -Destination $AntennaAppRoot -Recurse -Force

$DocFiles = @(
    "architecture.md",
    "deployment.md",
    "environment.md",
    "project.md",
    "session.md",
    "pyaedt.md",
    "patch.md",
    "simulation.md",
    "results.md",
    "adapters.md",
    "antenna-workflows.md",
    "modeling.md",
    "optimization.md",
    "offline-deployment.md",
    "dual-mcp-offline-deployment.md"
)
foreach ($doc in $DocFiles) {
    $source = Join-Path (Join-Path $RepoRoot "docs") $doc
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $DocsRoot -Force
    }
}

$HelperScripts = @("aedt_probe.py", "pyaedt_student_bridge.py")
foreach ($helper in $HelperScripts) {
    $source = Join-Path (Join-Path $RepoRoot "scripts") $helper
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $ScriptsRoot -Force
    }
}

$ConfigExample = @'
# Copy this file to config.ps1 and edit it on the offline HFSS server.
$env:HFSS_AGENT_BACKEND = "pyaedt"
$env:HFSS_AGENT_MCP_TRANSPORT = "streamable-http"
$env:HFSS_AGENT_MCP_HOST = "0.0.0.0"
$env:HFSS_AGENT_MCP_PORT = "8000"
$env:HFSS_AGENT_REQUIRE_CLIENT_ID = "true"
$env:HFSS_AGENT_OUTPUT_ROOT = "$PSScriptRoot\data"
$env:HFSS_AGENT_AUDIT_LOG = "$PSScriptRoot\data\audit\requests.jsonl"
$env:HFSS_AGENT_LOCK_TIMEOUT_SECONDS = "60"

# Required on the target server unless ansysedt.exe is already on PATH.
# Example for Student 2025 R2:
# $env:HFSS_AGENT_AEDT_EXECUTABLE = "D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe"

# Independent antenna design intelligence MCP
$env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http"
$env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0"
$env:ANTENNA_INTELLIGENCE_PORT = "8010"
$env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = "$PSScriptRoot\data\antenna-inputs"
$env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = "$PSScriptRoot\data\antenna-intelligence"
$env:ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER = "false"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "config.example.ps1") -Value $ConfigExample -Encoding UTF8

$StartServer = @'
param(
    [string]$Backend = "",
    [string]$Transport = "",
    [string]$HostName = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "python\python.exe"
$AppSrc = Join-Path $Root "app\src"
$Config = Join-Path $Root "config.ps1"

if (Test-Path -LiteralPath $Config) {
    . $Config
}

if ($Backend) { $env:HFSS_AGENT_BACKEND = $Backend }
if ($Transport) { $env:HFSS_AGENT_MCP_TRANSPORT = $Transport }
if ($HostName) { $env:HFSS_AGENT_MCP_HOST = $HostName }
if ($Port -gt 0) { $env:HFSS_AGENT_MCP_PORT = [string]$Port }

if (-not $env:HFSS_AGENT_BACKEND) { $env:HFSS_AGENT_BACKEND = "pyaedt" }
if (-not $env:HFSS_AGENT_MCP_TRANSPORT) { $env:HFSS_AGENT_MCP_TRANSPORT = "streamable-http" }
if (-not $env:HFSS_AGENT_MCP_HOST) { $env:HFSS_AGENT_MCP_HOST = "0.0.0.0" }
if (-not $env:HFSS_AGENT_MCP_PORT) { $env:HFSS_AGENT_MCP_PORT = "8000" }
if (-not $env:HFSS_AGENT_OUTPUT_ROOT) { $env:HFSS_AGENT_OUTPUT_ROOT = (Join-Path $Root "data") }
if (-not $env:HFSS_AGENT_AUDIT_LOG) { $env:HFSS_AGENT_AUDIT_LOG = (Join-Path $env:HFSS_AGENT_OUTPUT_ROOT "audit\requests.jsonl") }
if (-not $env:HFSS_AGENT_LOCK_TIMEOUT_SECONDS) { $env:HFSS_AGENT_LOCK_TIMEOUT_SECONDS = "60" }

$env:PYTHONPATH = $AppSrc

Write-Host "HFSS Agent MCP offline bundle"
Write-Host "Endpoint: http://$($env:HFSS_AGENT_MCP_HOST):$($env:HFSS_AGENT_MCP_PORT)/mcp"
Write-Host "Backend:  $($env:HFSS_AGENT_BACKEND)"
Write-Host "Python:   $Python"
Write-Host "App:      $AppSrc"
if (-not $env:HFSS_AGENT_AEDT_EXECUTABLE) {
    Write-Warning "HFSS_AGENT_AEDT_EXECUTABLE is not set. env_check will warn and pyaedt backend may not launch AEDT."
}

& $Python -B -m hfss_agent_mcp run `
    --backend $env:HFSS_AGENT_BACKEND `
    --transport $env:HFSS_AGENT_MCP_TRANSPORT `
    --host $env:HFSS_AGENT_MCP_HOST `
    --port $env:HFSS_AGENT_MCP_PORT
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-server.ps1") -Value $StartServer -Encoding UTF8

$StartAll = @'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "python\python.exe"
$Config = Join-Path $Root "config.ps1"
$StateDir = Join-Path $Root "data\runtime"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $StateDir, $LogDir | Out-Null
if (Test-Path -LiteralPath $Config) { . $Config }

if (-not $env:HFSS_AGENT_BACKEND) { $env:HFSS_AGENT_BACKEND = "pyaedt" }
if (-not $env:HFSS_AGENT_MCP_TRANSPORT) { $env:HFSS_AGENT_MCP_TRANSPORT = "streamable-http" }
if (-not $env:HFSS_AGENT_MCP_HOST) { $env:HFSS_AGENT_MCP_HOST = "0.0.0.0" }
if (-not $env:HFSS_AGENT_MCP_PORT) { $env:HFSS_AGENT_MCP_PORT = "8000" }
if (-not $env:HFSS_AGENT_OUTPUT_ROOT) { $env:HFSS_AGENT_OUTPUT_ROOT = (Join-Path $Root "data\hfss") }
if (-not $env:HFSS_AGENT_AUDIT_LOG) { $env:HFSS_AGENT_AUDIT_LOG = (Join-Path $env:HFSS_AGENT_OUTPUT_ROOT "audit\requests.jsonl") }
if (-not $env:ANTENNA_INTELLIGENCE_TRANSPORT) { $env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http" }
if (-not $env:ANTENNA_INTELLIGENCE_HOST) { $env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0" }
if (-not $env:ANTENNA_INTELLIGENCE_PORT) { $env:ANTENNA_INTELLIGENCE_PORT = "8010" }
if (-not $env:ANTENNA_INTELLIGENCE_INPUT_ROOTS) { $env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = (Join-Path $Root "data\antenna-inputs") }
if (-not $env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT) { $env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = (Join-Path $Root "data\antenna-intelligence") }

function Start-McpProcess {
    param([string]$Name, [string]$AppSrc, [string]$Module, [string[]]$Arguments)
    $stdout = Join-Path $LogDir ($Name + ".stdout.log")
    $stderr = Join-Path $LogDir ($Name + ".stderr.log")
    $env:PYTHONPATH = $AppSrc
    $process = Start-Process -FilePath $Python -ArgumentList (@("-B", "-m", $Module, "run") + $Arguments) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    if ($Name -eq "hfss") {
        $hostName = $env:HFSS_AGENT_MCP_HOST
        $port = $env:HFSS_AGENT_MCP_PORT
    } else {
        $hostName = $env:ANTENNA_INTELLIGENCE_HOST
        $port = $env:ANTENNA_INTELLIGENCE_PORT
    }
    return [ordered]@{ name = $Name; pid = $process.Id; endpoint = "http://$hostName`:$port/mcp" }
}

$hfss = Start-McpProcess -Name "hfss" -AppSrc (Join-Path $Root "app\src") -Module "hfss_agent_mcp" -Arguments @("--backend", $env:HFSS_AGENT_BACKEND, "--transport", $env:HFSS_AGENT_MCP_TRANSPORT, "--host", $env:HFSS_AGENT_MCP_HOST, "--port", $env:HFSS_AGENT_MCP_PORT)
$antenna = Start-McpProcess -Name "antenna-intelligence" -AppSrc (Join-Path $Root "app\antenna-design-intelligence-mcp\src") -Module "antenna_design_intelligence_mcp" -Arguments @("--transport", $env:ANTENNA_INTELLIGENCE_TRANSPORT, "--host", $env:ANTENNA_INTELLIGENCE_HOST, "--port", $env:ANTENNA_INTELLIGENCE_PORT)
@($hfss, $antenna) | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StateDir "pids.json") -Encoding UTF8
Write-Host "HFSS MCP: http://$($env:HFSS_AGENT_MCP_HOST):$($env:HFSS_AGENT_MCP_PORT)/mcp (PID $($hfss.pid))"
Write-Host "Antenna MCP: http://$($env:ANTENNA_INTELLIGENCE_HOST):$($env:ANTENNA_INTELLIGENCE_PORT)/mcp (PID $($antenna.pid))"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-all.ps1") -Value $StartAll -Encoding UTF8

$StopAll = @'
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$State = Join-Path $Root "data\runtime\pids.json"
if (-not (Test-Path -LiteralPath $State)) { Write-Host "No runtime state file found."; exit 0 }
$items = Get-Content -Raw -LiteralPath $State | ConvertFrom-Json
foreach ($item in @($items)) {
    if ($item.pid) { Stop-Process -Id ([int]$item.pid) -Force -ErrorAction SilentlyContinue }
}
Remove-Item -LiteralPath $State -Force -ErrorAction SilentlyContinue
Write-Host "Both MCP processes stopped."
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "stop-all.ps1") -Value $StopAll -Encoding UTF8

$HealthCheck = @'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$State = Join-Path $Root "data\runtime\pids.json"
if (-not (Test-Path -LiteralPath $State)) { Write-Error "Services are not started."; exit 1 }
$items = Get-Content -Raw -LiteralPath $State | ConvertFrom-Json
$failed = $false
foreach ($item in @($items)) {
    $p = Get-Process -Id ([int]$item.pid) -ErrorAction SilentlyContinue
    if ($null -eq $p) { Write-Host "$($item.name): stopped"; $failed = $true } else { Write-Host "$($item.name): running (PID $($item.pid)) $($item.endpoint)" }
}
if ($failed) { exit 1 }
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "health-check.ps1") -Value $HealthCheck -Encoding UTF8

$StartCmd = @'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-all.cmd") -Value $StartCmd -Encoding ASCII

$Readme = @'
# HFSS Agent + Antenna Intelligence MCP Offline Bundle

This package contains two independent MCP HTTP services for offline Windows HFSS servers.

## Services

- HFSS MCP: `http://<server-ip>:8000/mcp`
- Antenna design intelligence MCP: `http://<server-ip>:8010/mcp`

Both use `streamable-http` and run as separate processes.

## First Run

1. Extract to a short path such as `C:\HFSSagent`.
2. Copy `config.example.ps1` to `config.ps1` and set the AEDT executable path.
3. Run `start-all.ps1` (or `start-all.cmd`).
4. Check with `health-check.ps1`; stop with `stop-all.ps1`.

The `python` directory is a portable CPython runtime with offline dependencies. Ansys Electronics Desktop/HFSS must still be installed on the target machine.
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "README-OFFLINE.md") -Value $Readme -Encoding UTF8

& $VenvPython -m pip freeze |
    Where-Object { $_ -notmatch "^-e " } |
    Set-Content -LiteralPath (Join-Path $BundleRoot "requirements-lock.txt") -Encoding ASCII

$Commit = "unknown"
try {
    $Commit = (git -C $RepoRoot rev-parse HEAD).Trim()
} catch {
    $Commit = "unknown"
}

$Manifest = [ordered]@{
    name = "hfss-agent-mcp-offline"
    bundle_name = $BundleName
    build_time_utc = (Get-Date).ToUniversalTime().ToString("o")
    git_commit = $Commit
    platform = "windows-x64"
    python_base = $PythonBase
    python_version = (& (Join-Path $RuntimeRoot "python.exe") -c "import platform; print(platform.python_version())").Trim()
    app_entry = [ordered]@{
        hfss = "python\python.exe -B -m hfss_agent_mcp run"
        antenna_intelligence = "python\python.exe -B -m antenna_design_intelligence_mcp run"
    }
    endpoints = [ordered]@{
        hfss = "http://<server-ip>:8000/mcp"
        antenna_intelligence = "http://<server-ip>:8010/mcp"
    }
    requires = @(
        "Windows server or workstation",
        "Ansys Electronics Desktop / HFSS installed locally",
        "HFSS_AGENT_AEDT_EXECUTABLE configured when ansysedt.exe is not on PATH"
    )
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BundleRoot "manifest.json") -Encoding UTF8

Write-Host "Removing Python bytecode caches"
$CacheDirs = @(Get-ChildItem -LiteralPath $BundleRoot -Recurse -Directory -Force -Filter "__pycache__")
foreach ($dir in $CacheDirs) {
    Remove-Item -LiteralPath $dir.FullName -Recurse -Force
}
$BytecodeFiles = @(Get-ChildItem -LiteralPath $BundleRoot -Recurse -File -Force | Where-Object {
        $_.Extension -in @(".pyc", ".pyo")
    })
foreach ($file in $BytecodeFiles) {
    Remove-Item -LiteralPath $file.FullName -Force
}

$BundlePython = Join-Path $RuntimeRoot "python.exe"
$env:PYTHONPATH = (Join-Path $AppRoot "src") + ";" + (Join-Path $AntennaAppRoot "src")
Write-Host "Validating bundled Python imports"
& $BundlePython -B -c "import sys; import hfss_agent_mcp; import antenna_design_intelligence_mcp; import mcp; import pydantic; import ansys.aedt.core; print(sys.version.split()[0]); print('imports-ok')"
if ($LASTEXITCODE -ne 0) {
    throw "Bundled Python import validation failed."
}

if (-not $NoZip) {
    $ZipPath = Join-Path $OutputRoot ($BundleName + ".zip")
    Assert-ChildPath -Parent $OutputRoot -Child $ZipPath
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Write-Host "Creating archive $ZipPath"
    Compress-Archive -LiteralPath $BundleRoot -DestinationPath $ZipPath -Force
    Write-Host "Archive created: $ZipPath"
}

Write-Host "Offline bundle root: $BundleRoot"
