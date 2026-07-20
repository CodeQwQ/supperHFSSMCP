# 真实贴片建模导致 PyAEDT 工作进程失效

## 状态

已复现，等待生产代码修复和新的真实 HFSS 验证。

## 发现日期

2026-07-20

## 问题现象

在真实 Ansys Electronics Desktop Student 2025 R2 的 gRPC 会话中，连接到空的 Terminal 设计后，通过 MCP 创建新的 DrivenModal 设计并调用 `create_patch_antenna`，服务返回：

```text
object of type 'int' has no len()
```

随后同一 PyAEDT worker 的 `get_project_info`、`validate_design`、`create_simulation_setup`、`run_simulation` 和结果读取调用均失败。模块 6 无法获得真实 SolutionData。

## 复现证据

- MCP URL：`http://127.0.0.1:8037/mcp`
- 完整响应：`E:\LLMproject\HFSSagent\outputs\verification\module6-rerun7\mcp-http-full.json`
- Server 日志：`E:\LLMproject\HFSSagent\outputs\verification\module6-rerun7\mcp-server-8037.stderr.log`
- 验证报告：`docs/测试报告/模块6-真实HFSS验证-2026-07-20-重测7.md`

## 影响模块

- 模块 3：真实 PyAEDT 连接与会话生命周期
- 模块 4：贴片天线建模 workflow
- 模块 5：真实仿真任务
- 模块 6：结果读取与分析

## 初步原因

`create_hfss_design` 的响应显示请求的 `DrivenModal` 被返回为 `Modal`，且新设计对象数为 0。随后高层贴片建模 workflow 在真实 PyAEDT/AEDT 组合中触发 `int has no len()`，导致 worker 后续无法继续使用。需要定位具体失败的 PyAEDT 建模调用，并确认设计类型、端口类型和几何创建 API 在 Student 2025 R2 中的兼容性。

## 修复要求

1. 在真实 Student AEDT 会话中定位触发 `len(int)` 的具体建模语句。
2. 修复设计类型映射，确保请求 `DrivenModal` 后真实 HFSS design 不是 Terminal 或不兼容的 Modal 类型。
3. 将贴片 workflow 拆分为可独立观测的几何、材料、边界和 lumped port 操作，并保留真实错误上下文。
4. 修复后使用新的验证 Agent，在单个 MCP ClientSession 中重新完成模块 6 全流程。

## 改动后验证

尚未修复，当前重测 7 结论为 **FAIL/BLOCKED**。
## 重测 8（2026-07-20）

本次使用全新启动的 `streamable-http` MCP 服务（8038）和单个 MCP `ClientSession`，连接真实 HFSS Student gRPC `localhost:53387`。`create_hfss_design` 能够定位 `HFSS_Module6_Verifier8`，但 `create_patch_antenna` 在 Radiation boundary 创建阶段失败：

```text
Failed to create boundary radiation Module6PatchVerifier8_radiation
```

服务端参数为：

```text
name = Module6PatchVerifier8_radiation
props = {'Objects': ['Module6PatchVerifier8_airbox'], 'IsFssReference': False, 'IsForPML': False}
```

失败后 `get_project_info`、`validate_design`、`create_simulation_setup` 和 `run_simulation` 分别出现 `GetTopDesignList`、`GetMessages`、`HfssConstants.default_solution` 和 `GetRegistryString` 错误。没有真实求解，也没有 S 参数点。

证据：

- 报告：`docs/测试报告/模块6-真实HFSS验证-2026-07-20-重测8.md`
- 完整 MCP 响应：`E:\LLMproject\HFSSagent\outputs\verification\module6-rerun8\mcp-http-full.json`
- Server 日志：`E:\LLMproject\HFSSagent\outputs\verification\module6-rerun8\mcp-server-8038.stdout.log`

重测 10 已使用最新端口片和单端口 assignment 修复通过真实 HFSS 验收；本问题状态更新为 **已修复**。证据位于 `outputs/verification/module6-rerun10/`，真实求解、S 参数读取和报告导出均成功。
