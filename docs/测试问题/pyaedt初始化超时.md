# PyAEDT 初始化超时导致连接请求阻塞

## 版本信息

- 日期：2026-07-09
- 状态：已完成第二阶段修复；真实新建 Desktop 首次 Project/Design 初始化仍作为限制继续跟踪
- 关联模块：Session Manager、PyAEDT Backend、运行配置
- 关联测试：`tests/test_connection_timeout.py`、`tests/test_pyaedt_backend.py`

## 问题现象

在真实环境 Ansys Electronics Desktop Student 2025 R2 中，MCP 服务可以启动，`health_check` 可以返回，工具列表也能正常暴露；但是调用 `connect_hfss` 进入 PyAEDT 后端时，`ansys.aedt.core.Hfss(...)` 初始化会长时间不返回。

直接绕过 MCP，在 Python 脚本中调用 `Hfss(version="2025.2", student_version=True, ...)` 时，行为会随调用方式不同而变化：主线程直接调用可以成功；线程或 MCP 同步 tool 间接调用时，容易卡在 PyAEDT/AEDT 会话初始化层。这说明问题不在 MCP 工具注册或 HTTP transport，而在 PyAEDT Student 初始化与调用线程/进程模型的组合。

## 原因分析

第一阶段定位到原有连接流程是同步调用：

```text
connect_hfss -> HfssService._connect_session -> backend.connect -> PyAEDT Hfss(...)
```

当 `Hfss(...)` 不返回时，MCP tool 调用也无法返回，Session Manager 也没有机会记录该连接尝试失败。这个问题说明模块 2 需要从“只记录成功连接”升级为“记录连接尝试、连接失败和失败原因”。

第二阶段进一步定位到两个更具体的根因：

1. PyAEDT 1.2.0 在 Windows Student 版场景下，`launch_aedt()` 等待 `is_grpc_session_active(port)`，但该检测默认不包含 `ansysedtsv.exe` Student 进程。实际现象是 AEDT 已经以 `ansysedtsv.exe -grpcsrv <port>` 启动并监听端口，但 PyAEDT 仍认为 gRPC session 未激活。
2. 在线程中执行 `Hfss(...)` 会让 Student 版初始化卡在默认 Project/Design 创建阶段。FastMCP 的同步 tool 和原先的线程超时 worker 都可能让 PyAEDT 落到非主线程执行，因此单纯用线程做超时会把问题从“服务请求卡住”转移成“PyAEDT 初始化卡在 design 插入后”。

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
   - 为 Student 版 gRPC 启动检测增加临时补丁。
   - 将默认 PyAEDT 调用迁移到独立 worker 子进程，让真实 PyAEDT 对象运行在 worker 主线程，并由父进程负责超时终止。
4. `src/hfss_agent_mcp/config.py`
   - 增加 `connect_timeout_seconds` 配置，支持环境变量 `HFSS_AGENT_CONNECT_TIMEOUT_SECONDS`。
5. `src/hfss_agent_mcp/tools/session.py`
   - `connect_hfss` 暴露 `connect_timeout_seconds` 参数。

## 已完成改动

- 新增 `ConnectionSpec.connect_timeout_seconds`。
- 新增 `ServerConfig.connect_timeout_seconds`，默认 60 秒。
- `SessionRecord.status` 支持 `connecting` 和 `failed`。
- 连接失败时在 `SessionRecord.metadata.failure_reason` 中记录原因。
- 第一阶段 PyAEDT 后端使用 daemon 线程 worker 执行 `Hfss(...)` 初始化，并在超时时返回 `SessionError`。
- `connect_hfss` 失败响应包含 `data.session`，agent 可以直接看到失败 session。
- PyAEDT 后端默认通过 `_PyAedtWorkerClient` 调用独立 worker 子进程。
- worker 内部关闭线程超时，避免真实 `Hfss(...)` 在非主线程中执行。
- Student 版连接初始化期间临时补充 `active_sessions(student_version=True, non_graphical=None)` 端口检测。

## 验证结果

已新增并通过以下专项测试：

```powershell
& "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest tests.test_connection_timeout tests.test_pyaedt_backend -v
```

测试覆盖：

- PyAEDT `Hfss(...)` 初始化超过超时时间后快速返回受控 `SessionError`。
- `connect_hfss` 超时后 session 状态为 `failed`。
- 失败原因写入 `metadata.failure_reason`。
- Student 版 gRPC 检测补丁可以识别 Student `ansysedtsv.exe` 端口。
- 默认 PyAEDT backend 会通过 worker 进程执行真实连接。
- worker 内部连接会移除线程超时，让父进程通过进程超时控制风险。

已执行第一阶段真实 MCP smoke test：

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

已执行第二阶段真实 MCP smoke test：

```text
connect_hfss(
  student_version=true,
  desktop_version="2025.2",
  machine="localhost",
  port=55469,
  connect_timeout_seconds=30
)
```

验证结果：

- 通过真实 MCP streamable-http 服务调用。
- 返回 `status="ok"`。
- 返回工程 `Project1`、design `HFSS_FIF`。
- 随后调用 `get_project_info()` 返回 `status="ok"`，证明连接后的后续工具调用可继续通过 worker 使用真实 PyAEDT 会话。
- 对 `connect_hfss(new_desktop=true, connect_timeout_seconds=60)` 的真实测试可以在 60 秒后返回结构化 `SessionError`，不再拖死 MCP 服务。

## 当前限制

当前已经解决“PyAEDT 初始化卡住会拖死 MCP 请求”的服务稳定性问题，并证明 MCP 可以连接真实 Student AEDT 既有 gRPC 会话。尚未完全解决的是“由 MCP 请求直接 `new_desktop=true` 新建 AEDT 后首次 Project/Design 初始化”的稳定成功问题。后续建议把 `launch_aedt` 升级为真实 AEDT 进程/端口管理工具，让 agent 先获得明确 gRPC 端口，再调用 `connect_hfss(port=...)` 绑定会话；必要时继续补充 COM/CLI adapter 作为 PyAEDT 初始化缺口的兜底。
