# PyAEDT 求解阶段保存工程失败

## 状态

- 状态：已修复并通过真实 HFSS 回归
- 发现日期：2026-07-20
- 影响模块：模块 5 仿真任务与模块 6 结果分析

## 问题现象

真实 MCP HTTP 链路可以连接 Student AEDT、建立 setup 和 frequency sweep，但调用 `run_simulation` 时返回失败。服务端真实 PyAEDT 日志显示失败发生在 `Hfss.analyze()` 内部的 `oproject.Save()`，因此没有产生可读取的 Solution Data，后续 S 参数、阻抗分析和报告导出均无法完成。

## 复现方式

1. 启动真实 `pyaedt + streamable-http` MCP Server。
2. 连接 Ansys Electronics Desktop Student 2025 R2 的真实 gRPC 会话。
3. 通过 MCP 创建唯一 setup 和 frequency sweep。
4. 调用 `run_simulation`，观察服务端 PyAEDT 日志及 job 状态。

相关真实证据：

- `outputs/verification/module6-rerun4/mcp-one-session-final.json`
- `outputs/verification/module6-rerun4/mcp-server-8034.stderr.log`
- `docs/测试报告/模块6-真实HFSS验证-2026-07-20-重测4.md`

## 原因分析

PyAEDT 1.2.0 的 `Hfss.analyze()` 会先调用 `save_project()`，再调用 `analyze_setup()`。当前服务连接的是已经打开的 Student AEDT 工程；在该真实 gRPC 会话中，保存工程这一步返回 AEDT API Error，导致求解尚未真正启动。此问题属于适配层把“保存工程”和“直接分析 setup”绑定在一起，不是 MCP HTTP 协议问题。

## 修改模块

- `src/hfss_agent_mcp/backends/pyaedt.py`
- `tests/test_pyaedt_backend.py`
- `docs/simulation.md`
- `docs/results.md`

## 计划改动

将适配器的 `run_simulation` 从 `Hfss.analyze(setup=...)` 改为直接调用 PyAEDT 的 `analyze_setup(name=..., blocking=True)`，让 AEDT 自己执行 setup 分析并避免适配层额外触发保存。增加单元回归测试，确保不会重新调用 `analyze()`；随后使用全新验证 Agent 在真实 HFSS 中确认求解和结果提取。

## 改动后验证

- 离线回归：48 项通过。
- 真实 HFSS：重测 10 求解完成，结果读取和报告导出通过。

## 参考

- [PyAEDT Hfss.analyze](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.analyze.html)
- [PyAEDT Hfss.analyze_setup](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.analyze_setup.html)
