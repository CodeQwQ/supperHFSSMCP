# 天线设计信息理解 MCP

这是独立于 HFSS MCP 的离线优先服务。它只负责把本地论文/截图整理为带证据的 `AntennaDesignSpec`，不连接 AEDT、不创建 HFSS 几何，也不运行仿真。

## 首版能力

- 检查受控输入根目录下的 PDF/PNG/JPG 文件并计算摘要；
- 通过开发/测试用 `VerificationEvidenceProvider` 读取人工核对证据；
- 输出 confirmed、inferred、conflicting、unknown 状态和来源引用；
- 通过 MCP resources 提供中文提取工作手册；
- 不下载、不打包 OCR/VLM，不需要 GPU。

## 运行

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m antenna_design_intelligence_mcp list-tools
python -m antenna_design_intelligence_mcp run --transport stdio
```

先复制并修改 `config.example.ps1`。共享 HTTP 服务使用 `streamable-http`，并确保输入目录只读、输出目录独立。

## 推荐调用顺序

`inspect_input → list_providers → extract_document_evidence → extract_antenna_design_spec`

拿到规格后，本地 agent 才能读取现有 HFSS MCP 的 resources，补齐端口、边界、airbox 和 setup；HFSS 建模后必须先 `validate_design`，通过后才求解。

## 测试

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```
