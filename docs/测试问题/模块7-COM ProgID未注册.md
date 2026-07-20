# 模块 7 问题：Student AEDT 未注册预期 COM ProgID

## 状态

- 状态：已关闭，确认是当前 Student 环境限制
- 发现日期：2026-07-20
- 关联模块：模块 7，COM adapter

## 问题现象

真实 Agent 通过真实 streamable-http MCP 调用 `runner=com`，服务返回：

```text
Unable to attach to active AEDT COM application:
(-2147221005, '无效的类字符串', None, None)
```

## 真实复现证据

- `docs/测试报告/证据/模块7/mcp-http-full.json`
- `docs/测试报告/证据/模块7/03-runner-results.png`
- `docs/测试报告/证据/模块7/04-hfss-aedt-window.png`

## 原因分析

当前实现只尝试 `Ansoft.ElectronicsDesktop`。本机运行的是 Ansys Electronics Desktop Student 2025 R2，系统 COM 注册表中未发现该未版本化 ProgID；实测若干版本化 ProgID 也没有可附着对象。Student AEDT 的当前会话主要通过 gRPC 暴露。

## 影响范围

COM adapter 在当前 Student 安装上无法直接附着 AEDT；这不等同于 COM adapter 代码已被证明正确或错误，需要先支持版本化 ProgID/可配置 ProgID，并明确记录 Student 安装的真实能力边界。

## 需要修改

- `src/hfss_agent_mcp/backends/com.py`
- `src/hfss_agent_mcp/config.py`
- `docs/adapters.md`

## 修复要求

尝试按配置的 AEDT 版本构造版本化 ProgID，并提供清晰的候选 ProgID 错误信息；若 Student 安装确实没有 COM 注册，则返回可诊断的环境错误，并由真实验证报告标注为环境不支持，而不是伪造成功。

## 改动后验证

已增加可配置和版本化 ProgID 探测，并保留每个候选 ProgID 的原始错误。新的专职真实验收 agent 通过真实 MCP HTTP 复测确认：`Ansoft.ElectronicsDesktop` 和 `Ansoft.ElectronicsDesktop.2025.2` 均未注册，当前 Student 会话通过 gRPC 提供能力；native 和 Student bridge 路径已通过。后续部署到注册 COM 的 AEDT 版本时，可通过 `HFSS_AGENT_COM_PROGID` 显式配置。
