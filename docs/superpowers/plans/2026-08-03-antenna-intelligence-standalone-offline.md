# 天线设计信息 MCP 独立离线包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** 构建并发布只包含天线设计信息 MCP 的 Windows x64 HTTP 离线包。

**Architecture:** 使用现有可移植 CPython 和离线依赖，复制独立 MCP 源码；PowerShell 脚本只管理一个 `streamable-http` 进程，默认端口 8010。

**Tech Stack:** PowerShell 5.1、CPython 3.12、FastMCP、ZIP、GitHub Release。

---

### Task 1: 添加独立构建脚本

**Files:**
- Create: `scripts/build_antenna_intelligence_offline_bundle.ps1`

- [ ] 复制运行时、site-packages、天线 MCP 源码和中文部署文档。
- [ ] 生成配置、启动、停止、健康检查脚本。
- [ ] 验证包内 Python 导入并生成 manifest。

### Task 2: 构建并检查包

**Files:**
- Generated: `dist-offline/antenna-design-intelligence-mcp-offline-win-x64.zip`
- Generated: `dist-offline/antenna-design-intelligence-mcp-offline-win-x64.zip.sha256`

- [ ] 构建 ZIP。
- [ ] 检查压缩包不包含 HFSS 源码、模型和字节码缓存。
- [ ] 启动 HTTP 服务，验证端口、健康检查和停止脚本。

### Task 3: 发布

- [ ] 运行天线 MCP 测试集。
- [ ] 创建新的 GitHub Release 并上传 ZIP 与校验文件。
