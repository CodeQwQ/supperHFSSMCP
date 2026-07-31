# 双 MCP Windows 离线部署

本项目的完整离线包同时包含两个独立的 MCP 服务：

- HFSS MCP：`http://<服务器地址>:8000/mcp`
- 天线设计信息 MCP：`http://<服务器地址>:8010/mcp`

两个服务由 `start-all.ps1` 启动，均使用 `streamable-http`，分别运行在独立 Python 进程中。`stop-all.ps1` 负责停止两个进程，`health-check.ps1` 负责检查进程和端点状态。

## 部署

1. 将 `hfss-agent-mcp-offline-win-x64-dual-http.zip` 解压到短路径，例如 `C:\HFSSagent`。
2. 复制 `config.example.ps1` 为 `config.ps1`。
3. 设置 `HFSS_AGENT_AEDT_EXECUTABLE`，或确保 AEDT 可执行文件已经在 PATH 中。
4. 根据服务器防火墙策略决定是否允许 8000 和 8010 端口的远程访问。
5. 执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-all.ps1
```

## 运维

```powershell
.\health-check.ps1
.\stop-all.ps1
```

日志位于 `logs`，HFSS 输出和审计文件位于 `data\hfss`，天线设计信息 MCP 的输入和提取产物位于 `data\antenna-inputs` 与 `data\antenna-intelligence`。

离线包自带 CPython 运行时和项目依赖，但不包含 Ansys Electronics Desktop、HFSS 工程、仿真结果或 OCR/VLM 模型。目标机仍需安装与当前项目兼容的 HFSS/AEDT。
