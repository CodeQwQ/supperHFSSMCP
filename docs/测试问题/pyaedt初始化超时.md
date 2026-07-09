# PyAEDT 初始化超时导致连接请求阻塞

## 版本信息

- 日期：2026-07-09
- 状态：已完成第一阶段修复
- 关联模块：Session Manager、PyAEDT Backend、运行配置
- 关联测试：`tests/test_connection_timeout.py`

## 问题现象

在真实环境 Ansys Electronics Desktop Student 2025 R2 中，MCP 服务可以启动，`health_check` 可以返回，工具列表也能正常暴露；但是调用 `connect_hfss` 进入 PyAEDT 后端时，`ansys.aedt.core.Hfss(...)` 初始化会长时间不返回。

直接绕过 MCP，在 Python 脚本中调用 `Hfss(version="2025.2", student_version=True, ...)` 也会卡在初始化阶段。这说明阻塞点位于 PyAEDT/AEDT 会话初始化层，而不是 MCP 工具注册或 HTTP transport。

## 原因分析

原有连接流程是同步调用：

```text
connect_hfss -> HfssService._connect_session -> backend.connect -> PyAEDT Hfss(...)
```

当 `Hfss(...)` 不返回时，MCP tool 调用也无法返回，Session Manager 也没有机会记录该连接尝试失败。这个问题说明模块 2 需要从“只记录成功连接”升级为“记录连接尝试、连接失败和失败原因”。

## 影响范围

- 团队成员调用 `connect_hfss` 时可能长时间没有反馈。
- MCP server 的该次请求会被后端初始化拖住。
- agent 无法通过 `get_session_info` 查询失败原因。
- 后续真实 HFSS smoke test 难以稳定自动化。

## 需要修改的模块

1. `src/hfss_agent_mcp/core/session.py`
   - 增加 `connecting`、`failed` 状态。
   - 增加失败原因记录。
2. `src/hfss_agent_mcp/core/service.py`
   - `connect_hfss` 先创建连接尝试 session，再调用 backend。
   - 后端失败时返回带失败 session 的结构化错误。
3. `src/hfss_agent_mcp/backends/pyaedt.py`
   - 为 `Hfss(...)` 初始化增加可配置超时。
   - 超时后抛出受控 `SessionError`。
4. `src/hfss_agent_mcp/config.py`
   - 增加 `connect_timeout_seconds` 配置，支持环境变量 `HFSS_AGENT_CONNECT_TIMEOUT_SECONDS`。
5. `src/hfss_agent_mcp/tools/session.py`
   - `connect_hfss` 暴露 `connect_timeout_seconds` 参数。

## 已完成改动

- 新增 `ConnectionSpec.connect_timeout_seconds`。
- 新增 `ServerConfig.connect_timeout_seconds`，默认 60 秒。
- `SessionRecord.status` 支持 `connecting` 和 `failed`。
- 连接失败时在 `SessionRecord.metadata.failure_reason` 中记录原因。
- PyAEDT 后端使用 daemon worker 执行 `Hfss(...)` 初始化，并在超时时返回 `SessionError`。
- `connect_hfss` 失败响应包含 `data.session`，agent 可以直接看到失败 session。

## 验证结果

已新增并通过以下专项测试：

```powershell
& "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest tests.test_connection_timeout -v
```

测试覆盖：

- PyAEDT `Hfss(...)` 初始化超过超时时间后快速返回受控 `SessionError`。
- `connect_hfss` 超时后 session 状态为 `failed`。
- 失败原因写入 `metadata.failure_reason`。

已执行真实 MCP smoke test：

```powershell
$env:PYTHONPATH="E:\LLMproject\HFSSagent\src"
$env:HFSS_AGENT_AEDT_EXECUTABLE="D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe"
$env:HFSS_AGENT_CONNECT_TIMEOUT_SECONDS="2"
& "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m hfss_agent_mcp run --backend pyaedt --transport streamable-http --host 127.0.0.1 --port 8016
```

MCP client 调用：

```text
connect_hfss(student_version=true, non_graphical=false, new_desktop=true, connect_timeout_seconds=2)
```

验证结果：

- 调用耗时约 2.3 秒后返回，没有继续无限阻塞。
- 返回 `status="error"`。
- 返回 `data.error_type="SessionError"`。
- 返回 `data.session.status="failed"`。
- 返回 `data.session.metadata.failure_reason="PyAEDT HFSS initialization timed out after 2 seconds."`。

## 当前限制

本次修复解决的是“初始化卡住不能拖死 MCP 请求”的服务稳定性问题，并没有证明 PyAEDT Student 版真实会话已经能成功初始化。真实 HFSS 完整闭环仍需要继续校准 PyAEDT Student 版连接方式，或在后续模块中补充 COM/CLI adapter。
