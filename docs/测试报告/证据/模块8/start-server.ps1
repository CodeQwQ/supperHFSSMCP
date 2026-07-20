$ErrorActionPreference = "Stop"

$projectRoot = "E:\LLMproject\HFSSagent"
$runtimeRoot = Join-Path $projectRoot "outputs\module8-verification-20260720"

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:HFSS_AGENT_BACKEND = "pyaedt"
$env:HFSS_AGENT_MCP_TRANSPORT = "streamable-http"
$env:HFSS_AGENT_MCP_HOST = "127.0.0.1"
$env:HFSS_AGENT_MCP_PORT = "8043"
$env:HFSS_AGENT_REQUIRE_CLIENT_ID = "true"
$env:HFSS_AGENT_OUTPUT_ROOT = $runtimeRoot
$env:HFSS_AGENT_AUDIT_LOG = Join-Path $runtimeRoot "audit\requests.jsonl"
$env:HFSS_AGENT_LOCK_TIMEOUT_SECONDS = "120"
$env:HFSS_AGENT_CONNECT_TIMEOUT_SECONDS = "90"
$env:HFSS_AGENT_CLI_TIMEOUT_SECONDS = "180"
$env:HFSS_AGENT_AEDT_EXECUTABLE = "D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe"

Set-Location $projectRoot
& ".venv\Scripts\python.exe" -B -m hfss_agent_mcp run `
    --backend pyaedt `
    --transport streamable-http `
    --host 127.0.0.1 `
    --port 8043

