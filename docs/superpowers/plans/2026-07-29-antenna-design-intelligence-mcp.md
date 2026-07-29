# 天线设计信息理解 MCP 实施计划

> **面向执行 agent：** 必须逐项执行并使用复选框跟踪；执行前使用 `executing-plans` 流程。每项先写失败测试，再写最小实现，再运行测试。

**目标：** 在项目新子目录中交付独立、离线优先、无模型依赖的 MCP 服务，将本地论文/截图的可溯源证据转换为 `AntennaDesignSpec`，供本地 agent 规划现有 HFSS MCP 工具调用。

**架构：** 新服务位于 `antenna-design-intelligence-mcp/`，拥有独立 Python 包、配置、输出根目录和 MCP 入口。核心层只认识统一的证据和规格 schema；`VerificationEvidenceProvider` 是首版唯一可执行 provider，用于开发验证，不进行 OCR/VLM 推理。未来的 Docling、PaddleOCR、MinerU 与 VLM provider 仅通过相同接口接入。

**技术栈：** Python 3.10+、MCP Python SDK、Pydantic 2、标准库 `unittest`；首版不新增大模型、OCR、GPU 或网络依赖。

---

## 目录与职责

```text
antenna-design-intelligence-mcp/
  pyproject.toml                                  # 独立包与依赖声明
  README.md                                       # 中文快速运行说明
  config.example.ps1                              # Windows 离线配置模板
  src/antenna_design_intelligence_mcp/
    __init__.py
    __main__.py                                   # python -m 入口
    cli.py                                        # run/list-tools 命令
    config.py                                     # 环境变量到不可变配置
    server.py                                     # FastMCP 应用组装
    models.py                                     # Pydantic schema
    errors.py                                     # 可序列化领域错误
    paths.py                                      # 输入/输出路径约束
    artifacts.py                                  # 受控 JSON 产物仓库
    service.py                                    # 编排与规格生成
    providers/
      __init__.py
      base.py                                     # Provider 协议
      registry.py                                 # 注册与健康状态
      verification.py                             # 仅开发/测试的受控证据 provider
    tools/
      __init__.py
      extraction.py                               # 五个 MCP tool
      registry.py                                 # tool 注册
    resources/
      extraction-workflow.md                      # 给小模型的中文工作手册
      antenna-spec-fields.md                      # 字段、证据和状态定义
  tests/
    __init__.py
    helpers.py                                    # 临时根目录和样例证据
    test_paths.py
    test_models.py
    test_artifacts.py
    test_providers.py
    test_service.py
    test_mcp_registration.py
    test_cli.py
  docs/
    模块说明.md
    部署指南.md
    验收报告.md
```

根项目只新增该子目录和 `docs/` 下的模块交付文档；不修改 `src/hfss_agent_mcp/`，不把外部论文、模型、缓存、虚拟环境或 HFSS 结果纳入 Git。

### 任务 1：建立独立服务骨架与可执行入口

**文件：**

- 新建：`antenna-design-intelligence-mcp/pyproject.toml`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/__init__.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/__main__.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/cli.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_cli.py`

- [ ] **步骤 1：编写 CLI 的失败测试。**

```python
class CliTests(unittest.TestCase):
    def test_list_tools_exits_zero_and_lists_inspection_tool(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "antenna_design_intelligence_mcp", "list-tools"],
            text=True, capture_output=True, check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("inspect_input", completed.stdout.splitlines())
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
Set-Location antenna-design-intelligence-mcp
python -m unittest tests.test_cli -v
```

预期：失败，提示 `No module named antenna_design_intelligence_mcp`。

- [ ] **步骤 3：写入最小包与 CLI。**

`pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "antenna-design-intelligence-mcp"
version = "0.1.0"
description = "Offline-first evidence extraction MCP for antenna design."
requires-python = ">=3.10"
dependencies = ["mcp>=1.20,<2", "pydantic>=2,<3"]

[project.scripts]
antenna-design-intelligence-mcp = "antenna_design_intelligence_mcp.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

`__main__.py`：

```python
from antenna_design_intelligence_mcp.cli import main

raise SystemExit(main())
```

`cli.py` 先实现 `list-tools` 和 `run` 两个子命令；`list-tools` 使用 `asyncio.run(create_app().list_tools())` 打印 tool 名称，`run` 调用 `create_app().run(transport=config.transport)`。

- [ ] **步骤 4：运行测试确认通过。**

运行：

```powershell
$env:PYTHONPATH="$PWD\src"
python -m unittest tests.test_cli -v
```

预期：通过；`python -m antenna_design_intelligence_mcp list-tools` 退出码为 0。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/pyproject.toml antenna-design-intelligence-mcp/src antenna-design-intelligence-mcp/tests/test_cli.py
git commit -m "feat: scaffold antenna intelligence MCP"
```

### 任务 2：定义证据、规格和错误 schema

**文件：**

- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/models.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/errors.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_models.py`

- [ ] **步骤 1：写入失败测试。**

```python
class ModelTests(unittest.TestCase):
    def test_confirmed_dimension_requires_value_and_unit(self) -> None:
        with self.assertRaises(ValidationError):
            DimensionFact(name="patch_length", semantic_role="贴片长度", status="confirmed", evidence_ids=["e1"])

    def test_unknown_dimension_rejects_a_numeric_value(self) -> None:
        with self.assertRaises(ValidationError):
            DimensionFact(name="gap", semantic_role="间隙", status="unknown", value=1.2, unit="mm", evidence_ids=["e1"])
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_models -v
```

预期：失败，提示 `DimensionFact` 未定义。

- [ ] **步骤 3：实现 schema。**

在 `models.py` 定义以下 `str, Enum`：`FactStatus(confirmed, inferred, conflicting, unknown)`、`EvidenceKind(text, table, figure, operator)`、`ProviderHealth(available, unavailable, degraded)`。

定义以下 Pydantic 模型和字段：

```python
class SourceRef(BaseModel):
    input_id: str
    page: int | None = Field(default=None, ge=1)
    region: tuple[float, float, float, float] | None = None
    quote: str = Field(min_length=1, max_length=4000)
    kind: EvidenceKind

class EvidenceItem(BaseModel):
    evidence_id: str
    source: SourceRef
    provider_id: str
    provider_version: str
    confidence: float = Field(ge=0, le=1)
    observation: str = Field(min_length=1, max_length=4000)

class DimensionFact(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    semantic_role: str
    status: FactStatus
    value: float | None = None
    unit: Literal["mm", "um", "GHz", "MHz", "ohm", "ratio"] | None = None
    evidence_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> "DimensionFact":
        if self.status is FactStatus.confirmed and (self.value is None or self.unit is None):
            raise ValueError("confirmed 尺寸必须同时提供数值和单位")
        if self.status is FactStatus.unknown and (self.value is not None or self.unit is not None):
            raise ValueError("unknown 尺寸不能提供数值或单位")
        return self
```

再定义 `PerformanceTarget`、`MaterialFact`、`GeometryRelation`、`UnresolvedField` 和 `AntennaDesignSpec`。`AntennaDesignSpec` 至少包含 `spec_id`、`antenna_family`、`topology`、`evidence`、`dimensions`、`materials`、`targets`、`geometry_relations`、`unresolved_fields`、`contradictions` 与 `input_digest`。所有被引用的 `evidence_ids` 必须在 `evidence` 中存在；否则 model validator 抛错。

`errors.py` 定义 `DomainError(code: str, message: str, details: dict[str, object])`，并暴露 `to_payload()`，返回 `{"success": False, "error": {...}}`。

- [ ] **步骤 4：运行 schema 测试。**

运行：

```powershell
python -m unittest tests.test_models -v
```

预期：通过；确认状态与未知状态均严格受约束。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/models.py antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/errors.py antenna-design-intelligence-mcp/tests/test_models.py
git commit -m "feat: add evidence backed antenna spec schema"
```

### 任务 3：实现配置、路径隔离与受控产物仓库

**文件：**

- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/config.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/paths.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/artifacts.py`
- 新建：`antenna-design-intelligence-mcp/tests/helpers.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_paths.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_artifacts.py`

- [ ] **步骤 1：写入失败测试。**

```python
class PathTests(unittest.TestCase):
    def test_input_outside_allowed_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy = PathPolicy(input_roots=(root / "inputs",), output_root=root / "out")
            with self.assertRaises(DomainError) as error:
                policy.resolve_input(root / "secret.pdf")
            self.assertEqual(error.exception.code, "input_path_outside_allowed_roots")

class ArtifactTests(unittest.TestCase):
    def test_artifact_round_trip_uses_opaque_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = ArtifactStore(Path(raw) / "out")
            artifact_id = store.write("spec", {"spec_id": "spec-1"})
            self.assertTrue(artifact_id.startswith("spec_"))
            self.assertEqual(store.read(artifact_id)["payload"]["spec_id"], "spec-1")
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_paths tests.test_artifacts -v
```

预期：失败，提示 `PathPolicy` 与 `ArtifactStore` 未定义。

- [ ] **步骤 3：实现最小安全存储。**

`ServerConfig.from_env()` 必须读取以下变量并提供安全默认值：

```text
ANTENNA_INTELLIGENCE_NAME=antenna-design-intelligence-mcp
ANTENNA_INTELLIGENCE_TRANSPORT=stdio
ANTENNA_INTELLIGENCE_HOST=127.0.0.1
ANTENNA_INTELLIGENCE_PORT=8010
ANTENNA_INTELLIGENCE_INPUT_ROOTS=<项目>/inputs
ANTENNA_INTELLIGENCE_OUTPUT_ROOT=<项目>/outputs
ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER=false
ANTENNA_INTELLIGENCE_MAX_INPUT_BYTES=52428800
```

`PathPolicy.resolve_input()` 必须 `resolve(strict=True)`、检查输入文件、后缀仅允许 `.pdf/.png/.jpg/.jpeg`、大小不超过配置值，并逐个使用 `path.is_relative_to(root)` 判断受限根目录。`resolve_output()` 只接受服务内部生成的文件名，拒绝绝对路径、`..` 与路径分隔符。

`ArtifactStore.write(kind, payload)` 必须生成 `f"{kind}_{uuid4().hex}"`，将 `{artifact_id, kind, created_at, payload}` 原子写入 `<output_root>/artifacts/<artifact_id>.json`；`read()` 用正则 `^[a-z][a-z0-9_]{1,31}_[a-f0-9]{32}$` 校验 ID，读取前调用 `resolve_output()`。

- [ ] **步骤 4：运行安全和存储测试。**

运行：

```powershell
python -m unittest tests.test_paths tests.test_artifacts -v
```

预期：通过，目录逃逸和伪造 artifact ID 都返回结构化领域错误。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/{config.py,paths.py,artifacts.py} antenna-design-intelligence-mcp/tests/{helpers.py,test_paths.py,test_artifacts.py}
git commit -m "feat: add isolated inputs and extraction artifacts"
```

### 任务 4：实现可插拔 provider 注册表与无模型验证 provider

**文件：**

- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/providers/__init__.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/providers/base.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/providers/registry.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/providers/verification.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_providers.py`

- [ ] **步骤 1：写入失败测试。**

```python
class ProviderTests(unittest.TestCase):
    def test_default_registry_reports_verification_provider_unavailable(self) -> None:
        records = ProviderRegistry(enable_verification=False).list_status()
        self.assertEqual(records, [{"provider_id": "verification_evidence", "health": "unavailable"}])

    def test_enabled_verification_provider_rejects_missing_evidence(self) -> None:
        provider = VerificationEvidenceProvider(output_root=Path(tempfile.mkdtemp()))
        with self.assertRaises(DomainError) as error:
            provider.extract(ExtractionRequest(input_digest="a" * 64))
        self.assertEqual(error.exception.code, "verification_evidence_not_found")
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_providers -v
```

预期：失败，提示 provider 类未定义。

- [ ] **步骤 3：实现 provider 合约。**

`base.py` 定义：

```python
class EvidenceProvider(Protocol):
    provider_id: str
    provider_version: str
    def status(self) -> ProviderStatus: ...
    def extract(self, request: ExtractionRequest) -> list[EvidenceItem]: ...
```

同一文件定义 `ExtractionRequest(input_digest: str)` 与 `ProviderStatus(provider_id: str, health: ProviderHealth, message: str)` 两个 Pydantic 模型。

`VerificationEvidenceProvider` 只从受控 JSON 文件 `<output_root>/verification-evidence/<input_digest>.json` 读取 `EvidenceItem` 列表，且只有 `enable_verification=True` 时才可用。其 `extract()` 必须验证请求的 `input_digest` 等于文件内摘要；没有文件时返回 `verification_evidence_not_found`。它绝不读取任意客户端路径、绝不调用网络、OCR 或 VLM。

`ProviderRegistry` 永远登记 `verification_evidence`；禁用时返回 `ProviderHealth.unavailable` 与说明“首版未配置 OCR/VLM”。增加 `register(provider)`，为未来 provider 保留扩展点，但拒绝重复 `provider_id`。

- [ ] **步骤 4：运行 provider 测试。**

运行：

```powershell
python -m unittest tests.test_providers -v
```

预期：通过；默认服务可启动且明确没有视觉推理能力。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/providers antenna-design-intelligence-mcp/tests/test_providers.py
git commit -m "feat: add model-free verification evidence provider"
```

### 任务 5：实现服务编排与规格生成

**文件：**

- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/service.py`
- 新建：`antenna-design-intelligence-mcp/tests/test_service.py`

- [ ] **步骤 1：写入失败测试。**

```python
def test_extract_spec_preserves_confirmed_fact_and_unknown_gap(service: IntelligenceService, paper: Path) -> None:
    inspected = service.inspect_input(str(paper))
    evidence = service.extract_document_evidence(inspected["input_id"])
    result = service.extract_antenna_design_spec(evidence["artifact_id"])
    spec = result["spec"]
    assert spec["targets"][0]["start_ghz"] == 5.725
    assert any(item["status"] == "unknown" for item in spec["unresolved_fields"])
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_service -v
```

预期：失败，提示 `IntelligenceService` 未定义。

- [ ] **步骤 3：实现固定职责的服务方法。**

实现以下方法，所有方法成功返回 `{"success": True, ...}`，预期领域错误返回 `DomainError.to_payload()`：

```python
def inspect_input(self, path: str) -> dict[str, object]: ...
def list_providers(self) -> dict[str, object]: ...
def extract_document_evidence(self, input_id: str) -> dict[str, object]: ...
def extract_antenna_design_spec(self, evidence_artifact_id: str) -> dict[str, object]: ...
def get_extraction_artifact(self, artifact_id: str) -> dict[str, object]: ...
```

`inspect_input()` 用 SHA-256 计算摘要，以摘要为 `input_id`；只把 `{input_id, suffix, size_bytes, digest}` 写入 `input` artifact，不保存论文内容。

`extract_document_evidence()` 读取 input artifact，调用已启用 provider，并将证据列表存为 `evidence` artifact。没有可用 provider 时返回 `no_provider_available`，同时包含 `list_providers()` 状态。

`extract_antenna_design_spec()` 读取证据 artifact，并只做确定性合并：相同语义字段、相同数值和单位合成 `confirmed`；相同字段有不同值生成 `conflicting` 与 contradiction；仅文字描述但无数值生成 `unknown` unresolved field。不可从证据判断的馈电、端口积分线、airbox 和边界必须加入 unresolved fields。服务不得猜测任何尺寸。

测试样例只在临时输出目录中写入脱敏的 `VerificationEvidenceProvider` JSON，模拟场景三中已确认的工作带宽、`εr`、`tanδ`、12.9 mm 中心距，并至少保留“去耦结构精确轮廓”和“端口积分线”两个 unknown 字段。

- [ ] **步骤 4：运行服务测试。**

运行：

```powershell
python -m unittest tests.test_service -v
```

预期：通过；confirmed、conflicting 与 unknown 都可被区分并带证据 ID。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/service.py antenna-design-intelligence-mcp/tests/test_service.py
git commit -m "feat: orchestrate evidence into antenna specifications"
```

### 任务 6：暴露 MCP tools、resources 和服务应用

**文件：**

- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/tools/__init__.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/tools/extraction.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/tools/registry.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/server.py`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/resources/extraction-workflow.md`
- 新建：`antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/resources/antenna-spec-fields.md`
- 新建：`antenna-design-intelligence-mcp/tests/test_mcp_registration.py`

- [ ] **步骤 1：编写 MCP 注册失败测试。**

```python
def test_expected_tools_are_registered() -> None:
    tools = asyncio.run(create_app(test_config()).list_tools())
    assert {tool.name for tool in tools} == {
        "inspect_input", "list_providers", "extract_document_evidence",
        "extract_antenna_design_spec", "get_extraction_artifact",
    }
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_mcp_registration -v
```

预期：失败，提示 `create_app` 未定义。

- [ ] **步骤 3：实现 tool 层。**

`server.create_app()` 使用：

```python
FastMCP(
    name=config.name,
    instructions=(
        "从本地论文或截图提取带证据的天线设计规格。"
        "不得把 inferred 或 unknown 字段直接用于 HFSS 建模；"
        "建模后必须使用 HFSS MCP 的 validate_design，再运行求解。"
    ),
    host=config.host,
    port=config.port,
)
```

`tools/extraction.py` 的 `register(mcp, service)` 为五个服务方法注册同名 tool；参数仅为 `path`、`input_id`、`artifact_id` 等字符串，不暴露文件根目录、provider 对象、模型名或任意命令。tool 函数捕获 `DomainError` 并返回其 payload，其他异常返回 `{success: False, error: {code: "internal_error", message: "服务内部错误"}}`，完整 traceback 只写服务器日志。

两个中文 resource 必须明确推荐序列：`inspect_input → list_providers → extract_document_evidence → extract_antenna_design_spec → 审核 unknown/conflicting → 读取 HFSS MCP resources → 建模 → validate_design → solve → results`；并说明首版没有 OCR/VLM、如何解读证据状态和何时要求用户补充资料。

- [ ] **步骤 4：运行 MCP 注册测试和手动清单。**

运行：

```powershell
python -m unittest tests.test_mcp_registration -v
$env:PYTHONPATH="$PWD\src"
python -m antenna_design_intelligence_mcp list-tools
```

预期：测试通过；命令恰好输出五个 tool 名称。

- [ ] **步骤 5：提交。**

```powershell
git add antenna-design-intelligence-mcp/src/antenna_design_intelligence_mcp/{server.py,tools,resources} antenna-design-intelligence-mcp/tests/test_mcp_registration.py
git commit -m "feat: expose antenna evidence MCP tools and resources"
```

### 任务 7：补齐中文文档、离线部署模板与全量离线验证

**文件：**

- 新建：`antenna-design-intelligence-mcp/README.md`
- 新建：`antenna-design-intelligence-mcp/config.example.ps1`
- 新建：`antenna-design-intelligence-mcp/docs/模块说明.md`
- 新建：`antenna-design-intelligence-mcp/docs/部署指南.md`
- 新建：`antenna-design-intelligence-mcp/docs/验收报告.md`

- [ ] **步骤 1：补充文档检查测试。**

```python
def test_deployment_guide_declares_no_bundled_model() -> None:
    guide = (ROOT / "docs" / "部署指南.md").read_text(encoding="utf-8")
    assert "首版不包含 OCR/VLM 模型" in guide
    assert "ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER" in guide
```

- [ ] **步骤 2：运行测试确认失败。**

运行：

```powershell
python -m unittest tests.test_cli.DeploymentDocumentTests -v
```

预期：失败，提示部署指南不存在。

- [ ] **步骤 3：编写部署和模块文档。**

`config.example.ps1` 必须只设置以下变量：

```powershell
$env:ANTENNA_INTELLIGENCE_TRANSPORT = "streamable-http"
$env:ANTENNA_INTELLIGENCE_HOST = "0.0.0.0"
$env:ANTENNA_INTELLIGENCE_PORT = "8010"
$env:ANTENNA_INTELLIGENCE_INPUT_ROOTS = "D:\AntennaInputs"
$env:ANTENNA_INTELLIGENCE_OUTPUT_ROOT = "D:\AntennaIntelligenceData"
$env:ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER = "false"
```

`部署指南.md` 必须说明：首版不包含 OCR/VLM 模型；复制配置模板、设置输入/输出目录、使用 `python -m antenna_design_intelligence_mcp list-tools` 与 `run` 启动的方式；如何检查 `list_providers` 返回未配置视觉 provider；未来模型的放置目录、SHA-256 校验、离线安装、provider 配置、健康检查、禁用与回滚框架。不得编造未选定模型的下载地址或命令。

`模块说明.md` 记录目标、边界、核心接口、数据流、验证方式和限制；`验收报告.md` 记录场景三验证输入仅在外部只读目录使用、确认的字段、未知字段、HFSS `validate_design`/solver/资源释放证据位置和结果状态。

- [ ] **步骤 4：执行全量离线验证。**

运行：

```powershell
Set-Location antenna-design-intelligence-mcp
$env:PYTHONPATH="$PWD\src"
python -m unittest discover -s tests -v
python -m antenna_design_intelligence_mcp list-tools
```

预期：所有测试通过，且服务在 `ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER=false` 时仍可启动和列出 tools。

- [ ] **步骤 5：进行真实 HFSS 组合验收。**

使用外部论文场景三的人工核对证据，调用新 MCP 生成规格。由独立 agent 读取其中的 `confirmed`/`unknown` 状态后，仅使用已确认的前置事实调用真实 HFSS MCP；它必须调用 `validate_design`，验证通过后才调用 `run_simulation`，并立即记录 solver 任务状态与原始诊断。若缺少端口、积分线、精确几何或辐射区域，验收结果应为“需要补充/工程假设”，不能把不完整规格伪造为可复现成功。

将真实验收证据写入 `antenna-design-intelligence-mcp/docs/验收报告.md`，但不复制论文、HFSS 工程、模型、日志或大结果文件到 Git。

- [ ] **步骤 6：提交。**

```powershell
git add antenna-design-intelligence-mcp/README.md antenna-design-intelligence-mcp/config.example.ps1 antenna-design-intelligence-mcp/docs antenna-design-intelligence-mcp/tests/test_cli.py
git commit -m "docs: add offline deployment and acceptance guide"
```

## 计划自检

- 设计约束覆盖：独立子目录、provider 可插拔、无模型首版、证据状态、路径隔离、MCP tools/resources、中文文档、场景三、真实 HFSS `validate_design` 门禁和离线部署均有对应任务。
- 未实现范围：没有任何任务下载模型、调用云端、复制外部论文、自动控制 HFSS 或绕过校验门禁。
- 接口一致性：五个 MCP tool 与 `IntelligenceService` 的五个同名方法一一对应；所有 artifact 都由 `ArtifactStore` 的不透明 ID 读取。
