# 天线设计信息 MCP 独立离线包设计

## 目标

提供一个不包含 HFSS MCP 的 Windows x64 离线包，只启动天线设计信息 MCP，并通过 `streamable-http` 对外提供服务。

## 方案

复用项目 `.venv` 中已验证的可移植 CPython 和依赖，复制天线设计信息 MCP 的源码、中文资源和部署文档。包内提供单服务启动、停止和健康检查脚本，默认监听 `0.0.0.0:8010`。

## 边界

包不包含 HFSS MCP、AEDT/HFSS、OCR/VLM 模型、论文输入、提取产物和测试缓存。天线 MCP 当前仍保持无模型 Provider 的首版行为，后续模型可作为独立 Provider 添加。

## 验证

构建后使用包内 Python 导入天线 MCP、MCP 和 Pydantic；在本机启动服务，检查端口和 MCP 日志；运行健康检查与停止脚本；运行天线 MCP 的完整测试集；检查压缩包不含 HFSS 源码、模型或字节码缓存。
