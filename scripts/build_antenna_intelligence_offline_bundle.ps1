param(
    [string]$OutputRoot = "",
    [string]$BundleName = "antenna-design-intelligence-mcp-offline-win-x64",
    [string]$PythonBase = "",
    [string]$VenvPath = "",
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath { param([string]$Value) [IO.Path]::GetFullPath($Value) }
function Assert-ChildPath {
    param([string]$Parent, [string]$Child)
    $parentFull = Resolve-FullPath $Parent
    $childFull = Resolve-FullPath $Child
    if (-not $childFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside output root: $childFull"
    }
}

$RepoRoot = Resolve-FullPath (Join-Path $PSScriptRoot "..")
if (-not $OutputRoot) { $OutputRoot = Join-Path $RepoRoot "dist-offline" }
$OutputRoot = Resolve-FullPath $OutputRoot
if (-not $VenvPath) { $VenvPath = Join-Path $RepoRoot ".venv" }
$VenvPath = Resolve-FullPath $VenvPath
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Virtual environment Python not found: $VenvPython" }
if (-not $PythonBase) { $PythonBase = & $VenvPython -c "import sys; print(sys.base_prefix)" }
$PythonBase = Resolve-FullPath $PythonBase
if (-not (Test-Path -LiteralPath (Join-Path $PythonBase "python.exe"))) { throw "Python runtime not found: $PythonBase" }
$VenvSitePackages = Join-Path $VenvPath "Lib\site-packages"
if (-not (Test-Path -LiteralPath $VenvSitePackages)) { throw "site-packages not found: $VenvSitePackages" }

$BundleRoot = Join-Path $OutputRoot $BundleName
$RuntimeRoot = Join-Path $BundleRoot "python"
$AppRoot = Join-Path $BundleRoot "app"
$DocsRoot = Join-Path $BundleRoot "docs"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Assert-ChildPath $OutputRoot $BundleRoot
if (Test-Path -LiteralPath $BundleRoot) { Remove-Item -LiteralPath $BundleRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BundleRoot, $AppRoot, $DocsRoot | Out-Null

Write-Host "Copying portable Python runtime"
Copy-Item -LiteralPath $PythonBase -Destination $RuntimeRoot -Recurse -Force
$RuntimeSitePackages = Join-Path $RuntimeRoot "Lib\site-packages"
if (Test-Path -LiteralPath $RuntimeSitePackages) { Remove-Item -LiteralPath $RuntimeSitePackages -Recurse -Force }
Copy-Item -LiteralPath $VenvSitePackages -Destination $RuntimeSitePackages -Recurse -Force

Write-Host "Copying antenna intelligence MCP"
$SourceRoot = Join-Path $RepoRoot "antenna-design-intelligence-mcp"
Copy-Item -LiteralPath (Join-Path $SourceRoot "src") -Destination (Join-Path $AppRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $SourceRoot "pyproject.toml") -Destination $AppRoot -Force
Copy-Item -LiteralPath (Join-Path $SourceRoot "README.md") -Destination $AppRoot -Force

$DocFiles = @("antenna-intelligence-offline-deployment.md")
foreach ($doc in $DocFiles) {
    $source = Join-Path (Join-Path $RepoRoot "docs") $doc
    if (-not (Test-Path -LiteralPath $source)) { throw "Required document not found: $source" }
    Copy-Item -LiteralPath $source -Destination $DocsRoot -Force
}

$Config = @'
# Copy this file to config.ps1 and edit it on the offline server.
$env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http"
$env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0"
$env:ANTENNA_INTELLIGENCE_PORT = "8010"
$env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = "$PSScriptRoot\data\inputs"
$env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = "$PSScriptRoot\data\outputs"
$env:ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER = "false"
$env:ANTENNA_INTELLIGENCE_MAX_INPUT_BYTES = "52428800"

# Optional model-independent OCR/VLM HTTP sidecar.
# $env:ANTENNA_INTELLIGENCE_PERCEPTION_ENDPOINT = "http://127.0.0.1:8020/extract"
# $env:ANTENNA_INTELLIGENCE_PERCEPTION_TIMEOUT_SECONDS = "120"
# $env:ANTENNA_INTELLIGENCE_PERCEPTION_API_KEY = "replace-me"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "config.example.ps1") -Value $Config -Encoding UTF8

$Start = @'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "python\python.exe"
$AppSrc = Join-Path $Root "app\src"
$Config = Join-Path $Root "config.ps1"
$StateDir = Join-Path $Root "data\runtime"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $StateDir, $LogDir | Out-Null
if (Test-Path -LiteralPath $Config) { . $Config }
if (-not $env:ANTENNA_INTELLIGENCE_TRANSPORT) { $env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http" }
if (-not $env:ANTENNA_INTELLIGENCE_HOST) { $env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0" }
if (-not $env:ANTENNA_INTELLIGENCE_PORT) { $env:ANTENNA_INTELLIGENCE_PORT = "8010" }
if (-not $env:ANTENNA_INTELLIGENCE_INPUT_ROOTS) { $env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = (Join-Path $Root "data\inputs") }
if (-not $env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT) { $env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = (Join-Path $Root "data\outputs") }
$env:PYTHONPATH = $AppSrc
$stdout = Join-Path $LogDir "server.stdout.log"
$stderr = Join-Path $LogDir "server.stderr.log"
$process = Start-Process -FilePath $Python -ArgumentList @("-B", "-m", "antenna_design_intelligence_mcp", "run", "--transport", $env:ANTENNA_INTELLIGENCE_TRANSPORT, "--host", $env:ANTENNA_INTELLIGENCE_HOST, "--port", $env:ANTENNA_INTELLIGENCE_PORT) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $StateDir "pid.txt") -Encoding ASCII
Write-Host "Antenna intelligence MCP started: http://$($env:ANTENNA_INTELLIGENCE_HOST):$($env:ANTENNA_INTELLIGENCE_PORT)/mcp (PID $($process.Id))"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-server.ps1") -Value $Start -Encoding UTF8

$Stop = @'
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "data\runtime\pid.txt"
if (Test-Path -LiteralPath $PidFile) {
    $pidValue = [int](Get-Content -Raw -LiteralPath $PidFile)
    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Antenna intelligence MCP stopped."
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "stop-server.ps1") -Value $Stop -Encoding UTF8

$Health = @'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "data\runtime\pid.txt"
if (-not (Test-Path -LiteralPath $PidFile)) { Write-Error "Service is not started."; exit 1 }
$pidValue = [int](Get-Content -Raw -LiteralPath $PidFile)
$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($null -eq $process) { Write-Error "Service process is not running."; exit 1 }
$port = if ($env:ANTENNA_INTELLIGENCE_PORT) { [int]$env:ANTENNA_INTELLIGENCE_PORT } else { 8010 }
$tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet
if (-not $tcp) { Write-Error "Service process is running but port is not listening."; exit 1 }
Write-Host "Antenna intelligence MCP is running (PID $pidValue, port $port)."
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "health-check.ps1") -Value $Health -Encoding UTF8

$Cmd = @'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start-server.ps1"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-server.cmd") -Value $Cmd -Encoding ASCII

$Readme = @'
# Antenna Design Intelligence MCP Offline Bundle

This standalone package contains only the antenna design intelligence MCP.

- Endpoint: `http://<server-ip>:8010/mcp`
- Transport: `streamable-http`
- Start: `start-server.ps1` or `start-server.cmd`
- Stop: `stop-server.ps1`
- Health: `health-check.ps1`

The package includes portable CPython and offline dependencies. It does not include HFSS MCP, AEDT/HFSS, OCR/VLM models, input papers, or generated artifacts. See `docs/antenna-intelligence-offline-deployment.md`.
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "README-OFFLINE.md") -Value $Readme -Encoding UTF8

& $VenvPython -m pip freeze | Where-Object { $_ -notmatch "^-e " } | Set-Content -LiteralPath (Join-Path $BundleRoot "requirements-lock.txt") -Encoding ASCII
$Commit = "unknown"
try { $Commit = (git -C $RepoRoot rev-parse HEAD).Trim() } catch { }
$Manifest = [ordered]@{
    name = "antenna-design-intelligence-mcp-offline"
    bundle_name = $BundleName
    build_time_utc = (Get-Date).ToUniversalTime().ToString("o")
    git_commit = $Commit
    platform = "windows-x64"
    python_version = (& (Join-Path $RuntimeRoot "python.exe") -c "import platform; print(platform.python_version())").Trim()
    entry = "python\python.exe -B -m antenna_design_intelligence_mcp run"
    endpoint = "http://<server-ip>:8010/mcp"
    requires = @("Windows x64", "No network at runtime", "HFSS MCP is deployed separately")
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BundleRoot "manifest.json") -Encoding UTF8

Get-ChildItem -LiteralPath $BundleRoot -Recurse -Directory -Force -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $BundleRoot -Recurse -File -Force | Where-Object { $_.Extension -in @(".pyc", ".pyo") } | Remove-Item -Force

$BundlePython = Join-Path $RuntimeRoot "python.exe"
$env:PYTHONPATH = Join-Path $AppRoot "src"
Write-Host "Validating standalone antenna MCP imports"
& $BundlePython -B -c "import antenna_design_intelligence_mcp, mcp, pydantic; print('imports-ok')"
if ($LASTEXITCODE -ne 0) { throw "Standalone antenna MCP import validation failed." }

if (-not $NoZip) {
    $ZipPath = Join-Path $OutputRoot ($BundleName + ".zip")
    Assert-ChildPath $OutputRoot $ZipPath
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Compress-Archive -LiteralPath $BundleRoot -DestinationPath $ZipPath -Force
    Write-Host "Archive created: $ZipPath"
}
Write-Host "Standalone bundle root: $BundleRoot"
