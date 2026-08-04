# Ollama Qwen2.5-VL 部署与 MCP 接入

本文适用于 Ollama 已运行在 Windows 11 虚拟机、天线设计信息 MCP 运行在另一台服务器的场景。

## 网络拓扑

```text
Agent
  │ HTTP MCP
  ▼
天线设计信息 MCP :8010
  │ HTTP
  ▼
Perception Sidecar :8020
  │ HTTP
  ▼
Windows 11 VM Ollama :11434
```

MCP 和 Sidecar 不安装 Ollama、PyTorch 或 CUDA。只有 Windows 11 虚拟机运行 Qwen2.5-VL。

## Ollama 端配置

确认模型存在：

```powershell
ollama list
ollama pull qwen2.5vl:7b
```

让 Ollama 监听虚拟机网卡，而不是只监听回环地址：

```powershell
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve
```

在虚拟机防火墙中只允许 MCP 服务器 IP 访问 TCP 11434。

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

## MCP 端配置

在离线包根目录复制配置：

```powershell
Copy-Item config.example.ps1 config.ps1
```

编辑 `config.ps1`：

```powershell
$env:PERCEPTION_PLUGIN_PATH = "$PSScriptRoot\plugins"
$env:PERCEPTION_VLM_ENGINE_MODULE = "ollama_vlm_plugin:create_engine"
$env:OLLAMA_API_ENDPOINT = "http://<Windows11虚拟机IP>:11434/api/chat"
$env:OLLAMA_VLM_MODEL = "qwen2.5vl:7b"
$env:OLLAMA_API_TIMEOUT_SECONDS = "300"
```

启动：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-all.ps1
.\health-check.ps1
```

查看 Sidecar 已加载的引擎：

```powershell
Invoke-RestMethod http://127.0.0.1:8020/model-info
```

应包含 `ollama_qwen2.5-vl-7b` 和 `image_understanding`。

## 输入限制

当前 Ollama Provider 直接处理 PNG、JPG、JPEG。PDF 会返回人工复核证据，提示先渲染成页面图片；不会把 PDF 当成图片提交，也不会生成未经模型确认的尺寸。

模型输出必须是 JSON。无法从图中确认的尺寸、介质参数、馈电位置必须写入 `unknowns`，由后续 Agent 决定是否需要人工补充。

## 故障定位

1. `model-info` 仍显示 `demo_perception`：检查 `PERCEPTION_PLUGIN_PATH` 和模块名。
2. Ollama connection refused：检查虚拟机 IP、`OLLAMA_HOST` 和 TCP 11434 防火墙。
3. 返回 `ollama_vlm_error`：查看 Sidecar 日志，确认模型名称和 Ollama `/api/chat` 可用。
4. 输出不是 JSON：保持 `format=json`，并检查模型是否确实为 `qwen2.5vl:7b`。

