# 天线设计信息 MCP 独立离线部署

## 服务地址

本包只包含天线设计信息 MCP，不包含 HFSS MCP。默认服务地址：

```text
http://<服务器地址>:8010/mcp
```

服务使用 `streamable-http`。

## 部署步骤

1. 将 `antenna-design-intelligence-mcp-offline-win-x64.zip` 解压到短路径，例如 `C:\AntennaIntelligenceMCP`。
2. 复制 `config.example.ps1` 为 `config.ps1`。
3. 配置输入目录和输出目录：

```powershell
$env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = "D:\AntennaInputs"
$env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = "D:\AntennaIntelligenceData"
```

4. 启动：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

5. 检查：

```powershell
.\health-check.ps1
```

6. 停止：

```powershell
.\stop-server.ps1
```

## 与 HFSS MCP 的关系

天线设计信息 MCP 部署在独立机器后，本地 Agent 同时配置两个 HTTP MCP 地址：

```text
天线设计信息 MCP：http://<信息服务地址>:8010/mcp
HFSS MCP：         http://<HFSS服务地址>:8000/mcp
```

Agent 先调用天线设计信息 MCP 获取带证据的 `AntennaDesignSpec`，再调用 HFSS MCP 完成建模、`validate_design`、仿真和结果读取。两个 MCP 不共享进程、文件或 Python 环境。

## 当前限制

首版不包含 OCR/VLM 模型。`list_providers` 会显示视觉 Provider 未配置；后续模型应作为可插拔 Provider 单独安装，不需要重新部署 HFSS MCP。
