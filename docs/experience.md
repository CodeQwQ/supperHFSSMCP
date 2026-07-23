# 项目经验沉淀

## 版本信息

- 日期：2026-07-23
- 状态：最新

## 本次问题反思

本次暴露的问题不是单点 bug，而是测试策略和工程流程没有完全贴近真实 HFSS 使用方式。

第一，之前真实测试偏向“能通过 MCP 调用 HFSS”，但没有把“用户要看见 GUI 并接管鼠标操作”作为验收项。因此 `non_graphical=true` 的默认值没有被及时发现。后续只要涉及本地/服务器 HFSS 人机协作，必须把截图或窗口可见性作为验收证据之一。

第二，之前把 `release_connection` 理解成 MCP session record 的释放，忽略了用户语义中的“释放资源”。对闭源工程软件而言，释放资源通常包含保存工程、关闭工程、释放文件锁和退出进程。后续凡是工具名称涉及 close、release、disconnect，都必须明确区分“释放 agent 控制权”和“关闭外部软件进程”。

第三，之前对仿真流程的测试跳过了强制 validation gate，导致错误推迟到求解阶段，耗时更长且报错更模糊。后续 HFSS 标准流程必须是：建模、边界/激励、setup/sweep、validate、solve、read results。没有通过 validation，不进入 solve。

第四，之前的失败响应更关注 Python 异常，而不是 HFSS 原始消息。对 HFSS 这类闭源工程软件，真实诊断信息经常存在 AEDT message manager、solver log 或 PyAEDT logger 中。后续所有真实后端错误都要尽量携带原始软件消息。

第五，偶极子 workflow 的 mock 验证只检查对象数量和基础 recipe，没有检查“HFSS 求解必需边界”。后续天线 workflow 验收必须覆盖材料、边界、端口、求解区域、setup/sweep 和 validation 消息，而不是只看几何是否存在。

## 后续测试准则

1. 真实 HFSS 验收必须包含可视化证据：截图、工程路径、design 名称和对象列表。
2. 每个天线 workflow 至少有一个 validation smoke test，确认不会在求解前暴露基础建模错误。
3. 每次求解前都先执行 validation，并把 validation 结果返回给 agent。
4. 每个失败场景都要故意制造一次错误，确认 agent 能看到真实 HFSS 报错，而不是只看到通用失败。
5. 资源释放类工具必须测试两类语义：完全释放和保留 GUI 给人工接管。
6. 文档要记录最新行为，不保留已经被修复的旧限制作为当前事实。

## 2026-07-23 真实验收补充

1. 对闭源桌面软件，不能只相信 API 返回“released”。默认关闭类操作必须记录受控进程 PID，并验证进程确实退出；如果 API 成功但 PID 仍存活，要对受控 PID 做兜底处理并把结果返回。
2. PyAEDT 不同对象层的同名方法参数可能不同。`Desktop.release_desktop` 使用 `close_on_exit`，而 `Hfss.release_desktop` 使用 `close_desktop`。后端 adapter 应以当前对象签名为准，避免把 PyAEDT 内部日志错误伪装成业务成功。
3. 图形界面验收不能依赖普通全屏截图。窗口被遮挡时，普通截图会拍到前台窗口；应使用窗口句柄和系统窗口渲染接口直接捕捉 AEDT 窗口。
4. Student 版 AEDT 连续多实例测试时，保留 GUI 的测试会影响后续新实例连接时长。真实多用户服务器后续需要会话队列、独占锁或 broker，避免多个 agent 同时争抢 Student 版桌面资源。
5. 天线 workflow 的验收不能只看几何对象数量。最低验收集应包括：几何、材料、边界、端口、airbox、setup/sweep、validation 消息和资源释放结果。
