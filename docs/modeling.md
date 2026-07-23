# 天线建模原子动作模块

## 版本信息

- 模块版本：v0.1
- 日期：2026-07-23
- 状态：已实现 mock 离线验证和 PyAEDT 后端适配入口

## 模块目标

建模原子动作模块为小模型提供一组可组合的 HFSS 建模积木。它补充模板 workflow 的不足：当 `create_patch_antenna` 或 `create_dipole_antenna` 不能覆盖用户结构时，agent 可以用显式工具创建 box、sheet、材料、边界和 lumped port，再进入标准 setup、validate、solve、results 流程。

该模块不接收任意 Python/VBScript，也不暴露完整 PyAEDT API。本轮只覆盖天线设计最小稳定集，确保小模型容易选择、容易恢复、容易被 validation gate 约束。

## MCP Tools

- `create_model_box`：创建 3D box。`origin_mm` 和 `size_mm` 都是 3 个数字，单位 mm。
- `create_model_sheet`：创建矩形 sheet。`orientation` 只允许 `XY`、`YZ`、`XZ`；`size_mm` 是 2 个数字，单位 mm。
- `set_object_material`：修改一个已存在对象的材料。
- `assign_perfect_e`：给明确对象名分配 Perfect E 边界。
- `assign_radiation_boundary`：给明确对象名分配 Radiation 边界。
- `create_lumped_port`：在已有 port sheet 上创建 lumped port 和积分线。
- `delete_model_objects`：删除明确命名的对象；不支持通配符和清空设计。

## 推荐调用顺序

```text
connect_hfss
create_project / open_project
create_hfss_design
create_model_box / create_model_sheet
set_object_material
assign_perfect_e
assign_radiation_boundary
create_lumped_port
create_simulation_setup / create_frequency_sweep
validate_design
run_simulation
analyze_s_parameters / export_result_report
release_connection
```

## 数据与验证规则

所有几何坐标和尺寸统一使用 mm。频率仍由 `create_simulation_setup` 和 sweep 工具管理。

创建 lumped port 时，`integration_start_mm` 和 `integration_end_mm` 必须落在 `sheet_name` 指定的 port sheet 平面内。真实 HFSS 会直接拒绝不在端口片上的积分线，原始错误通常类似 `both endpoints of port lines must lie on the port`。

mock 后端会把对象、边界、端口、变量、setup 和 sweep 写入 active design 状态，并在 `get_design_summary` 中返回 `object_details`、`boundaries`、`ports` 和 `variables`。模板 workflow 创建的边界和端口也会进入同一份状态。

mock validation 的最低通过条件：

1. 当前 design 中存在几何对象。
2. 至少创建一个 port。
3. 至少分配一个 radiation boundary。
4. 至少创建一个 setup。
5. 每个 setup 至少有一个 sweep。

validation 不通过时，`run_simulation` 不会进入后端求解。

## 已知限制

1. 本轮不支持 cylinder、polyline、boolean、阵列复制或 wave port。
2. PyAEDT 后端的 `get_design_summary` 稳定返回对象名；边界和端口详情在不同 AEDT/PyAEDT 版本中读取方式不统一，当前不伪造未知信息。
3. `delete_model_objects` 只接受显式对象名，恢复复杂误操作时建议新建 design 或从已保存工程重新打开。

## 验证

```powershell
& ".venv\Scripts\python.exe" -B -m unittest tests.test_modeling_atoms tests.test_mcp_registration tests.test_pyaedt_backend -v
```

真实 HFSS 验收时，应通过 MCP 原子工具创建一个最小可验证天线结构，执行 `validate_design`，确认返回真实 HFSS validation 消息，并按会话模块要求验证 GUI 可见性和资源释放语义。

2026-07-23 已通过一次真实 Student 2025 R2 smoke test：原子工具依次创建两个金属臂、一个 XY port sheet、airbox、Perfect E、Radiation、lumped port 和 setup，`validate_design` 返回 `Design validation check PASSED.`，`release_connection(save_project=false)` 返回 `process_closed=true`。
