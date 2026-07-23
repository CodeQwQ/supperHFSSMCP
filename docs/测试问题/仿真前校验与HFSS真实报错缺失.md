# 仿真前校验与 HFSS 真实报错缺失

## 版本信息

- 日期：2026-07-23
- 状态：已修复，真实 HFSS 故意失败验收通过
- 影响模块：simulation、PyAEDT backend、统一异常处理

## 问题现象

用户验证偶极子建模与仿真流程时，求解失败，但 agent 侧没有看到真正失败原因。人工打开 HFSS 后才发现基础建模错误：金属片没有设置为 Perfect E。

旧流程还存在一个更大的流程问题：求解前没有强制执行 HFSS validation，导致可快速发现的建模错误被推迟到耗时更长的 solver 阶段才暴露。

## 原因分析

1. `run_simulation` 过去直接调用后端求解器，没有把 `validate_design` 作为前置门禁。
2. PyAEDT 后端在 `analyze_setup()` 失败时只返回通用失败文案，没有采集 AEDT message manager / PyAEDT logger 的原始消息。
3. worker 子进程异常只返回 Python 异常字符串，没有结构化透传 `hfss_messages`。
4. 服务层异常响应分散，缺少统一 `_error_response()` 展开公共错误字段，导致各工具无法一致返回 HFSS 原始错误、validation 或 worker traceback。

## 修改内容

1. `run_simulation` 在创建 job 后、调用求解器前，先执行 `backend.validate_design()`。
2. 如果 validation 返回 `valid=false`，job 直接标记为 `failed`，返回 `validation` 与 `failure_reason`，不进入 solver。
3. PyAEDT 后端新增 HFSS message 采集逻辑，优先读取 `hfss.logger.get_messages()` 和 `odesktop.GetMessages()`。
4. worker 子进程错误响应新增 `hfss_messages` 字段，并由 `_raise_worker_error()` 放入异常 `details`。
5. 服务层新增统一 `_error_response()`，把 `details.hfss_messages`、`details.validation` 和 `details.worker_traceback` 展开到 MCP tool response 的 `data` 中。

## 真实 HFSS 验证结果

真实环境：Ansys Electronics Desktop Student 2025 R2。

故意错误场景：创建空 HFSS design，只创建 `SetupInvalid`，不创建几何、材料 solve-inside 对象和激励，然后调用 `run_simulation(wait_for_completion=true)`。

验收结果：

1. `run_simulation` 在约 0.05 秒内返回 failed job，没有进入真实求解。
2. 返回 `validation.valid=false`。
3. `failure_reason` 和 `validation.messages` 包含 HFSS 原始 validation 错误：
   - `[error] There are no objects in the design.`
   - `[error] At least one material assignment should have solve inside set!`
   - `[error] Boundary Setup: An excitation must be defined in order to solve driven problems.`
4. 释放连接后返回 `process_closed=true`，测试工程已清理。

证据文件：

- `docs/测试报告/证据/修复-20260723/acceptance-state.json`
- `docs/测试报告/证据/修复-20260723/server.stdout.log`
- `docs/测试报告/证据/修复-20260723/server.stderr.log`

## 回归测试

```powershell
& ".venv\Scripts\python.exe" -B -m unittest tests.test_simulation_jobs tests.test_pyaedt_backend -v
& ".venv\Scripts\python.exe" -B -m unittest discover -s tests -v
```
