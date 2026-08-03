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

## 接入 OCR/VLM sidecar

OCR/VLM 不需要安装到 MCP 的 Python 环境中。模型可以运行在独立 Python 环境、容器或另一台机器上，只要提供版本化 HTTP/JSON 接口即可。MCP 通过请求体传输文件摘要、扩展名和 Base64 文件内容，不依赖 sidecar 的本地路径。

在 `config.ps1` 中配置：

```powershell
$env:ANTENNA_INTELLIGENCE_PERCEPTION_ENDPOINT = "http://127.0.0.1:8020/extract"
$env:ANTENNA_INTELLIGENCE_PERCEPTION_TIMEOUT_SECONDS = "120"
# 可选：与 sidecar 约定的 Bearer token
# $env:ANTENNA_INTELLIGENCE_PERCEPTION_API_KEY = "your-token"
```

重启 MCP 后调用 `list_providers`，应看到 `http_perception` 为 `available`。MCP 本身不会导入 PyTorch、CUDA、OCR 或 VLM SDK。

### sidecar 请求协议

```json
{
  "protocol_version": "1",
  "input_digest": "64位小写SHA-256",
  "input_suffix": ".pdf",
  "content_base64": "..."
}
```

sidecar 返回：

```json
{
  "protocol_version": "1",
  "provider_id": "your-ocr-vlm-provider",
  "provider_version": "1.0.0",
  "evidence": []
}
```

`evidence` 中的每一项必须符合 `EvidenceItem` 结构，并且 `source.input_id` 必须等于请求中的 `input_digest`。模型版本、置信度、页码和图像区域应写入证据，不能只返回最终尺寸。

sidecar 建议只监听 `127.0.0.1:8020`；如果部署在另一台机器，应增加 TLS 或网络隔离，并使用 API key。模型文件、CUDA runtime 和 sidecar 依赖应作为独立离线包部署，不能让 MCP 运行时联网下载。
