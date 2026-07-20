# PyAEDT 设计校验接口不兼容

## 状态

- 状态：已修复并通过真实 HFSS 回归
- 发现日期：2026-07-20
- 影响模块：模块 5 仿真前校验

## 问题现象

真实 MCP HTTP 调用 `validate_design` 时，PyAEDT worker 返回：`Hfss object has no attribute validate_design`。因此服务虽然能完成连接和 setup/sweep 创建，但无法在求解前给出真实的 HFSS 设计校验结果。

## 原因分析

当前安装的 PyAEDT 版本为 1.2.0，HFSS 暴露的是 `validate_full_design()` 和底层 `validate_simple()`，并不存在项目适配器调用的 `validate_design()`。

## 修改内容

- `src/hfss_agent_mcp/backends/pyaedt.py` 改为调用 `validate_full_design()`。
- 返回统一的 `valid`、`errors`、`warnings`、`messages` 和 `raw_result` 字段。
- `tests/test_pyaedt_backend.py` 增加真实 API 形状的回归测试。

## 验证

- 离线回归：45 项通过。
- 真实 HFSS 回归：重测 10 的 `validate_design` 在 setup/sweep 创建后返回 `valid=true`。

## 参考

- [PyAEDT Hfss.validate_full_design](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.validate_full_design.html)
