# PyAEDT 结果频率数组适配错误

## 状态

- 状态：已修复并通过真实 HFSS 回归
- 发现日期：2026-07-20
- 影响模块：模块 6 结果读取与分析

## 问题现象

真实 HFSS 求解完成后，`get_s_parameters` 曾返回 `The truth value of an array with more than one element is ambiguous`，导致 S 参数分析和报告导出无法继续。

## 原因与修改

PyAEDT `SolutionData.primary_sweep_values` 返回 array-like/NumPy 数组，适配器使用 `value or []` 进行空值判断，触发数组真值异常。`src/hfss_agent_mcp/backends/pyaedt.py` 已改为显式判断 `None` 后再转换为 `list`，并在 `tests/test_pyaedt_backend.py` 增加回归测试。

## 验证结果

- 离线测试：48 项通过。
- 真实 HFSS 重测 10：返回 101 个频率点，S 参数和阻抗均可读取，JSON 报告成功导出。
- 证据目录：`outputs/verification/module6-rerun10/`
