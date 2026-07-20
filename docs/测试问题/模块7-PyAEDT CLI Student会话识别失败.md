# 模块 7 问题：PyAEDT CLI 未识别 Student gRPC 会话

## 状态

- 状态：已关闭，真实复测通过
- 发现日期：2026-07-20
- 关联模块：模块 7，CLI runner

## 问题现象

真实 Agent 通过真实 streamable-http MCP 调用：

```json
{
  "script_id": "aedt_probe",
  "runner": "pyaedt",
  "port": 53387
}
```

MCP 已经通过 PyAEDT backend 连接到真实 Student 2025 R2 gRPC 会话，但 CLI 返回退出码 1，并输出：

```text
Failed to start new AEDT gRPC session on port 61297
```

未生成 JSON artifact。

## 真实复现证据

- `docs/测试报告/证据/模块7/mcp-http-full.json`
- `docs/测试报告/证据/模块7/03-runner-results.png`
- `outputs/verification-module7-20260720/scripts/logs/20260720T051044751255Z-pyaedt.log`

## 原因分析

当前 PyAEDT CLI 的 `run --ironpython --port` 内部创建 `Desktop(port=..., new_desktop=False)`，但该 CLI 入口没有把 Student 版本信息传入 Desktop。PyAEDT 因此无法把现有 Student 会话识别为目标会话，退化为启动新 AEDT 实例。

## 影响范围

在 Student 版本环境中，MCP 的 `runner=pyaedt` 不能可靠执行登记脚本；原生 AEDT CLI 和其他入口不受此问题直接影响。

## 需要修改

- `src/hfss_agent_mcp/backends/cli_runner.py`
- 必要时新增项目内固定的 PyAEDT Student bridge 脚本
- 更新 `docs/adapters.md`

## 修复要求

保持脚本登记和无任意代码执行边界不变；使用固定服务端 bridge 明确传入 `student_version=True`，再调用登记脚本，不把 agent 输入拼接为代码。

## 改动后验证

已增加固定 `pyaedt_student_bridge.py`，按端口解析 Student AEDT PID，并显式使用 `student_version=True`、`new_desktop=False` 和 Student gRPC 检测补丁。新的专职真实验收 agent 已通过真实 MCP HTTP 调用验证，artifact 包含 `Project14`、`HFSS_Module6_Verifier10`、`script_id` 和请求参数。
