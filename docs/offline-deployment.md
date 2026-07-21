# 离线部署包

## 版本信息

- 文档版本：v0.1
- 日期：2026-07-21
- 适用场景：目标服务器没有互联网，已经安装 Ansys Electronics Desktop / HFSS，需要解压后直接运行 HFSS MCP 服务。

## 交付策略

离线部署不把 Python 运行时和第三方依赖直接提交到 git 历史中。仓库只维护可复现的打包脚本和部署说明，大体积压缩包作为 GitHub Release 附件交付。

这样做的原因是：Python 运行时、PyAEDT、gRPC、numpy、pywin32 等依赖体积较大，直接进入 git 会导致后续 clone、pull、回滚都变慢。Release 附件更适合交付二进制部署包。

## 包内容

离线包目录结构如下：

```text
hfss-agent-mcp-offline-win-x64/
  python/                 # 便携 Python 运行时
  app/src/                # MCP 服务源码
  scripts/                # AEDT 辅助脚本
  docs/                   # 部署和模块文档
  config.example.ps1      # 服务器配置模板
  start-server.ps1        # PowerShell 启动入口
  start-server.cmd        # cmd 启动入口
  requirements-lock.txt   # 构建时依赖锁定清单
  manifest.json           # 构建元数据
  README-OFFLINE.md       # 离线包快速说明
```

包内 Python 使用构建机当前已经验证通过的 Python 3.12.10，并复制当前 `.venv` 中的全部运行依赖。目标服务器不需要联网执行 `pip install`。

## 构建方式

在有网络、已经完成依赖安装和真实 HFSS 验证的开发机上运行：

```powershell
.\scripts\build_offline_bundle.ps1
```

默认产物：

```text
dist-offline\hfss-agent-mcp-offline-win-x64\
dist-offline\hfss-agent-mcp-offline-win-x64.zip
```

脚本会完成以下动作：

1. 复制当前 Python 运行时。
2. 复制当前虚拟环境 `site-packages`。
3. 复制项目源码、必要脚本和部署文档。
4. 生成 `config.example.ps1`、`start-server.ps1`、`manifest.json` 和 `requirements-lock.txt`。
5. 使用包内 Python 验证 `hfss_agent_mcp`、`mcp`、`pydantic`、`ansys.aedt.core` 可导入。
6. 生成 zip 压缩包。

## 服务器解压位置

没有强制目录要求，建议使用短路径，例如：

```text
C:\HFSSagent
D:\HFSSagent
```

不建议放在包含中文、空格、过深层级或同步盘的目录下。HFSS、PyAEDT 和脚本日志对路径兼容性较敏感，短路径更利于排查问题。

## 服务器配置

解压后复制配置模板：

```powershell
Copy-Item .\config.example.ps1 .\config.ps1
```

编辑 `config.ps1`，至少配置 HFSS/AEDT 可执行文件路径：

```powershell
$env:HFSS_AGENT_AEDT_EXECUTABLE = "D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe"
```

团队共享服务器建议保留以下配置：

```powershell
$env:HFSS_AGENT_BACKEND = "pyaedt"
$env:HFSS_AGENT_MCP_TRANSPORT = "streamable-http"
$env:HFSS_AGENT_MCP_HOST = "0.0.0.0"
$env:HFSS_AGENT_MCP_PORT = "8000"
$env:HFSS_AGENT_REQUIRE_CLIENT_ID = "true"
$env:HFSS_AGENT_OUTPUT_ROOT = "$PSScriptRoot\data"
$env:HFSS_AGENT_AUDIT_LOG = "$PSScriptRoot\data\audit\requests.jsonl"
$env:HFSS_AGENT_LOCK_TIMEOUT_SECONDS = "60"
```

## 启动方式

在解压目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

默认 MCP endpoint：

```text
http://<服务器IP>:8000/mcp
```

远程 Agent 不是通过浏览器“发现”服务，而是在各自工作机的 MCP client 配置中显式填写上述 URL。若启用了反向代理、VPN 或网关，应把 Agent 配置为代理后的 HTTPS 地址。

## 验证方式

离线包构建阶段必须至少通过包内 Python import 验证：

```powershell
.\python\python.exe -B -c "import hfss_agent_mcp, mcp, ansys.aedt.core; print('ok')"
```

目标服务器启动后，先让远程 Agent 调用：

```text
env_check
health_check
```

确认返回中：

- Python 可执行文件位于离线包 `python\python.exe`。
- `mcp`、`pydantic`、`ansys.aedt.core` 可用。
- `HFSS_AGENT_AEDT_EXECUTABLE` 指向真实存在的 AEDT/HFSS 可执行文件。
- 输出目录可写。

随后再执行真实 HFSS smoke test，例如 `connect_hfss`、`create_project`、`create_hfss_design`。

## 已知限制

1. 离线包面向 Windows + 本机 HFSS/AEDT；它不包含 HFSS 软件本体、license 或 Ansys 系统组件。
2. 该包复制的是当前构建机 Python 运行时和依赖，目标服务器应尽量使用相近的 Windows 架构与系统环境。
3. 若后续升级 PyAEDT、MCP SDK 或 Python 版本，需要重新构建并发布新的离线包。
4. 若目标服务器 HFSS 安装路径不同，只需修改 `config.ps1`，不需要重新打包。
