# 天线设计信息提取工作手册

## 推荐序列

按以下顺序调用本 MCP：

`inspect_input → list_providers → extract_document_evidence → extract_antenna_design_spec → 审核 unknown/conflicting → 读取 HFSS MCP resources → 建模 → validate_design → solve → results`

首版不包含 OCR/VLM。`list_providers` 返回 `verification_evidence` 未配置时，不能声称已经识别了截图或论文图像。开发验证可启用人工核对证据 provider，但其输出只证明编排和 schema，不证明视觉模型准确率。

## 交接 HFSS MCP 的规则

- 只有 `confirmed` 字段可以直接进入论文复现输入。
- `inferred` 字段必须由 agent 记录工程假设后才能使用。
- `unknown` 和 `conflicting` 字段必须先补充资料或向用户提问。
- 建模必须覆盖材料、金属/辐射边界、端口和积分线、airbox、setup/sweep。
- HFSS 必须先调用 `validate_design`；校验未通过不得调用求解。
- 求解后读取真实 job 状态和原始 HFSS 诊断，不能只依据 Python 返回成功。
