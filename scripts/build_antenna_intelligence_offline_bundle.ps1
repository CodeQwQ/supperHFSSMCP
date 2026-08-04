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
$PerceptionAppRoot = Join-Path $AppRoot "perception"
$DocsRoot = Join-Path $BundleRoot "docs"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Assert-ChildPath $OutputRoot $BundleRoot
if (Test-Path -LiteralPath $BundleRoot) { Remove-Item -LiteralPath $BundleRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BundleRoot, $AppRoot, $PerceptionAppRoot, $DocsRoot | Out-Null

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
$PerceptionRoot = Join-Path $RepoRoot "perception-sidecar"
Copy-Item -LiteralPath (Join-Path $PerceptionRoot "src") -Destination (Join-Path $PerceptionAppRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PerceptionRoot "pyproject.toml") -Destination $PerceptionAppRoot -Force
Copy-Item -LiteralPath (Join-Path $PerceptionRoot "README.md") -Destination $PerceptionAppRoot -Force
Copy-Item -LiteralPath (Join-Path $PerceptionRoot "plugins") -Destination (Join-Path $BundleRoot "plugins") -Recurse -Force

$DocFiles = @("antenna-intelligence-offline-deployment.md", "ollama-vlm-deployment.md")
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

$env:ANTENNA_INTELLIGENCE_PERCEPTION_ENDPOINT = "http://127.0.0.1:8020/extract"
$env:ANTENNA_INTELLIGENCE_PERCEPTION_TIMEOUT_SECONDS = "120"
# $env:ANTENNA_INTELLIGENCE_PERCEPTION_API_KEY = "replace-me"

# Local OCR/VLM sidecar (the package includes a demo engine).
$env:PERCEPTION_HOST = "127.0.0.1"
$env:PERCEPTION_PORT = "8020"
$env:PERCEPTION_PLUGIN_PATH = "$PSScriptRoot\plugins"
# Configure real engines with package.module:create_engine.
# $env:PERCEPTION_OCR_ENGINE_MODULE = "your_ocr_plugin:create_engine"
$env:PERCEPTION_VLM_ENGINE_MODULE = "ollama_vlm_plugin:create_engine"
$env:OLLAMA_API_ENDPOINT = "http://127.0.0.1:11434/api/chat"
$env:OLLAMA_VLM_MODEL = "qwen2.5vl:7b"
$env:OLLAMA_API_TIMEOUT_SECONDS = "300"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "config.example.ps1") -Value $Config -Encoding UTF8

$Start = @'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "python\python.exe"
$McpSrc = Join-Path $Root "app\src"
$PerceptionSrc = Join-Path $Root "app\perception\src"
$Config = Join-Path $Root "config.ps1"
$StateDir = Join-Path $Root "data\runtime"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $StateDir, $LogDir | Out-Null
if (Test-Path -LiteralPath $Config) { . $Config }
if (-not $env:ANTENNA_INTELLIGENCE_TRANSPORT) { $env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http" }
if (-not $env:ANTENNA_INTELLIGENCE_HOST) { $env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0" }
if (-not $env:ANTENNA_INTELLIGENCE_PORT) { $env:ANTENNA_INTELLIGENCE_PORT = "8010" }
if (-not $env:PERCEPTION_HOST) { $env:PERCEPTION_HOST = "127.0.0.1" }
if (-not $env:PERCEPTION_PORT) { $env:PERCEPTION_PORT = "8020" }
if (-not $env:PERCEPTION_PLUGIN_PATH) { $env:PERCEPTION_PLUGIN_PATH = (Join-Path $Root "plugins") }
$env:PYTHONPATH = $PerceptionSrc + ";" + $env:PERCEPTION_PLUGIN_PATH
$perceptionOut = Join-Path $LogDir "perception.stdout.log"
$perceptionErr = Join-Path $LogDir "perception.stderr.log"
$perception = Start-Process -FilePath $Python -ArgumentList @("-B", "-m", "antenna_perception_sidecar") -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $perceptionOut -RedirectStandardError $perceptionErr -PassThru
$env:PYTHONPATH = $McpSrc
$mcpOut = Join-Path $LogDir "mcp.stdout.log"
$mcpErr = Join-Path $LogDir "mcp.stderr.log"
$mcp = Start-Process -FilePath $Python -ArgumentList @("-B", "-m", "antenna_design_intelligence_mcp", "run", "--transport", $env:ANTENNA_INTELLIGENCE_TRANSPORT, "--host", $env:ANTENNA_INTELLIGENCE_HOST, "--port", $env:ANTENNA_INTELLIGENCE_PORT) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $mcpOut -RedirectStandardError $mcpErr -PassThru
@(@{name="perception"; pid=$perception.Id; port=[int]$env:PERCEPTION_PORT}, @{name="mcp"; pid=$mcp.Id; port=[int]$env:ANTENNA_INTELLIGENCE_PORT}) | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StateDir "pids.json") -Encoding UTF8
Write-Host "Perception sidecar: http://$($env:PERCEPTION_HOST):$($env:PERCEPTION_PORT) (PID $($perception.Id))"
Write-Host "Antenna MCP: http://$($env:ANTENNA_INTELLIGENCE_HOST):$($env:ANTENNA_INTELLIGENCE_PORT)/mcp (PID $($mcp.Id))"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-all.ps1") -Value $Start -Encoding UTF8
Set-Content -LiteralPath (Join-Path $BundleRoot "start-server.ps1") -Value '$Root = Split-Path -Parent $MyInvocation.MyCommand.Path; & (Join-Path $Root "start-all.ps1")' -Encoding UTF8

$Stop = @'
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$State = Join-Path $Root "data\runtime\pids.json"
if (Test-Path -LiteralPath $State) {
    $items = Get-Content -Raw -LiteralPath $State | ConvertFrom-Json
    foreach ($item in @($items)) { Stop-Process -Id ([int]$item.pid) -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $State -Force -ErrorAction SilentlyContinue
}
Write-Host "Perception sidecar and antenna MCP stopped."
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "stop-all.ps1") -Value $Stop -Encoding UTF8
Set-Content -LiteralPath (Join-Path $BundleRoot "stop-server.ps1") -Value '$Root = Split-Path -Parent $MyInvocation.MyCommand.Path; & (Join-Path $Root "stop-all.ps1")' -Encoding UTF8

$Health = @'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$State = Join-Path $Root "data\runtime\pids.json"
if (-not (Test-Path -LiteralPath $State)) { Write-Error "Services are not started."; exit 1 }
$items = Get-Content -Raw -LiteralPath $State | ConvertFrom-Json
$failed = $false
foreach ($item in @($items)) {
    $process = Get-Process -Id ([int]$item.pid) -ErrorAction SilentlyContinue
    $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port ([int]$item.port) -InformationLevel Quiet
    if ($null -eq $process -or -not $tcp) { Write-Host "$($item.name): failed"; $failed = $true } else { Write-Host "$($item.name): running (PID $($item.pid), port $($item.port))" }
}
if ($failed) { exit 1 }
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "health-check.ps1") -Value $Health -Encoding UTF8

$Cmd = @'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
'@
Set-Content -LiteralPath (Join-Path $BundleRoot "start-all.cmd") -Value $Cmd -Encoding ASCII

$Readme = @'
# Antenna Design Intelligence MCP Offline Bundle

This standalone package contains only the antenna design intelligence MCP.

- Endpoint: `http://<server-ip>:8010/mcp`
- Transport: `streamable-http`
- Start: `start-all.ps1` or `start-all.cmd` (starts MCP and sidecar)
- Stop: `stop-all.ps1`
- Health: `health-check.ps1`

The package includes portable CPython, the protocol sidecar, the Ollama HTTP VLM plugin, and offline dependencies. It does not include HFSS MCP, AEDT/HFSS, Ollama, model weights, input papers, or generated artifacts. Configure `OLLAMA_API_ENDPOINT` and `OLLAMA_VLM_MODEL` in `config.ps1`, then start Ollama separately. See `docs/antenna-intelligence-offline-deployment.md`.
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
    entries = [ordered]@{
        mcp = "python\python.exe -B -m antenna_design_intelligence_mcp run"
        perception = "python\python.exe -B -m antenna_perception_sidecar"
    }
    endpoints = [ordered]@{
        mcp = "http://<server-ip>:8010/mcp"
        perception = "http://127.0.0.1:8020"
    }
    requires = @("Windows x64", "No network at runtime", "HFSS MCP is deployed separately")
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BundleRoot "manifest.json") -Encoding UTF8

Get-ChildItem -LiteralPath $BundleRoot -Recurse -Directory -Force -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $BundleRoot -Recurse -File -Force | Where-Object { $_.Extension -in @(".pyc", ".pyo") } | Remove-Item -Force

$BundlePython = Join-Path $RuntimeRoot "python.exe"
$env:PYTHONPATH = (Join-Path $AppRoot "src") + ";" + (Join-Path $PerceptionAppRoot "src")
Write-Host "Validating standalone antenna MCP imports"
& $BundlePython -B -c "import antenna_design_intelligence_mcp, antenna_perception_sidecar, mcp, pydantic; print('imports-ok')"
if ($LASTEXITCODE -ne 0) { throw "Standalone antenna MCP import validation failed." }

if (-not $NoZip) {
    $ZipPath = Join-Path $OutputRoot ($BundleName + ".zip")
    Assert-ChildPath $OutputRoot $ZipPath
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Compress-Archive -LiteralPath $BundleRoot -DestinationPath $ZipPath -Force
    Write-Host "Archive created: $ZipPath"
}
Write-Host "Standalone bundle root: $BundleRoot"
