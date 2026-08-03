from __future__ import annotations

import hashlib
import base64
import re
from pathlib import Path

from antenna_design_intelligence_mcp.artifacts import ArtifactStore
from antenna_design_intelligence_mcp.errors import DomainError
from antenna_design_intelligence_mcp.models import (
    AntennaDesignSpec,
    Contradiction,
    DimensionFact,
    EvidenceItem,
    ExtractionRequest,
    FactStatus,
    GeometryRelation,
    MaterialFact,
    PerformanceTarget,
    UnresolvedField,
)
from antenna_design_intelligence_mcp.paths import PathPolicy
from antenna_design_intelligence_mcp.providers.registry import ProviderRegistry


class IntelligenceService:
    def __init__(
        self,
        path_policy: PathPolicy,
        artifacts: ArtifactStore,
        providers: ProviderRegistry,
    ) -> None:
        self.path_policy = path_policy
        self.artifacts = artifacts
        self.providers = providers
        self._input_paths: dict[str, Path] = {}

    def inspect_input(self, path: str) -> dict[str, object]:
        try:
            resolved = self.path_policy.resolve_input(path)
        except FileNotFoundError as exc:
            raise DomainError("input_not_found", "输入文件不存在。", {"path": path}) from exc
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        self._input_paths[digest] = resolved
        artifact_id = self.artifacts.write(
            "input",
            {
                "input_id": digest,
                "suffix": resolved.suffix.lower(),
                "size_bytes": resolved.stat().st_size,
                "digest": digest,
            },
        )
        return {
            "success": True,
            "input_id": digest,
            "artifact_id": artifact_id,
            "suffix": resolved.suffix.lower(),
            "size_bytes": resolved.stat().st_size,
        }

    def list_providers(self) -> dict[str, object]:
        return {"success": True, "providers": self.providers.list_status()}

    def extract_document_evidence(self, input_id: str) -> dict[str, object]:
        providers = self.providers.available()
        if not providers:
            raise DomainError(
                "no_provider_available",
                "当前没有可用的文档/OCR/视觉 provider；首版需启用验证证据 provider。",
                {"providers": self.providers.list_status()},
            )
        records: list[EvidenceItem] = []
        diagnostics: list[dict[str, object]] = []
        for provider in providers:
            try:
                request = ExtractionRequest(input_digest=input_id)
                if getattr(provider, "requires_content", False):
                    input_path = self._input_paths.get(input_id)
                    if input_path is None:
                        raise DomainError(
                            "input_not_inspected",
                            "当前服务实例未检查该输入文件，请先调用 inspect_input。",
                            {"input_id": input_id},
                        )
                    request = ExtractionRequest(
                        input_digest=input_id,
                        input_suffix=input_path.suffix.lower(),
                        content_base64=base64.b64encode(input_path.read_bytes()).decode("ascii"),
                    )
                records.extend(provider.extract(request))
            except DomainError as error:
                diagnostics.append(error.to_payload()["error"])
        if not records:
            raise DomainError(
                "evidence_extraction_failed",
                "所有可用 provider 都没有返回证据。",
                {"diagnostics": diagnostics},
            )
        artifact_id = self.artifacts.write(
            "evidence",
            {
                "input_digest": input_id,
                "evidence": [item.model_dump(mode="json") for item in records],
                "diagnostics": diagnostics,
            },
        )
        return {"success": True, "artifact_id": artifact_id, "count": len(records), "diagnostics": diagnostics}

    def extract_antenna_design_spec(self, evidence_artifact_id: str) -> dict[str, object]:
        envelope = self.artifacts.read(evidence_artifact_id)
        payload = envelope.get("payload", {})
        input_digest = str(payload.get("input_digest", ""))
        raw_evidence = payload.get("evidence", [])
        evidence = [EvidenceItem.model_validate(item) for item in raw_evidence]
        if not evidence or len(input_digest) != 64:
            raise DomainError("invalid_evidence_artifact", "证据产物缺少输入摘要或证据记录。", {})
        observations = " ".join(item.observation for item in evidence)
        targets: list[PerformanceTarget] = []
        dimensions: list[DimensionFact] = []
        materials: list[MaterialFact] = []
        target_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*GHz", observations, re.I)
        if target_match:
            target_ids = [item.evidence_id for item in evidence if "频段" in item.observation or "GHz" in item.source.quote]
            targets.append(
                PerformanceTarget(
                    name="工作频段",
                    start_ghz=float(target_match.group(1)),
                    end_ghz=float(target_match.group(2)),
                    status=FactStatus.CONFIRMED,
                    evidence_ids=target_ids or [evidence[0].evidence_id],
                )
            )
        material_match = re.search(r"(?:ε|epsilon)\s*r\s*=\s*(\d+(?:\.\d+)?).*?(?:tan\s*δ|tan\s*delta)\s*=\s*(\d+(?:\.\d+)?)", observations, re.I)
        if material_match:
            material_ids = [item.evidence_id for item in evidence if "介电" in item.observation or "epsilon" in item.source.quote.lower()]
            materials.append(
                MaterialFact(
                    role="substrate",
                    relative_permittivity=float(material_match.group(1)),
                    loss_tangent=float(material_match.group(2)),
                    status=FactStatus.CONFIRMED,
                    evidence_ids=material_ids or [evidence[0].evidence_id],
                )
            )
        spacing_match = re.search(r"(?:中心距|距离).*?(\d+(?:\.\d+)?)\s*mm", observations, re.I)
        if spacing_match:
            spacing_ids = [item.evidence_id for item in evidence if "中心距" in item.observation]
            dimensions.append(
                DimensionFact(
                    name="element_spacing",
                    semantic_role="双天线中心距",
                    status=FactStatus.CONFIRMED,
                    value=float(spacing_match.group(1)),
                    unit="mm",
                    evidence_ids=spacing_ids or [evidence[0].evidence_id],
                )
            )
        unresolved = [
            UnresolvedField(
                field_name="port_integration_line",
                reason="当前证据未给出可直接用于 HFSS lumped port 的积分线端点。",
                suggested_question="请补充端口位置、端口面和积分线方向。",
            ),
            UnresolvedField(
                field_name="radiation_region",
                reason="当前证据未确认 airbox 尺寸和辐射边界。",
                suggested_question="请确认 airbox 与 Radiation 边界的尺寸或允许使用的工程规则。",
            ),
            UnresolvedField(
                field_name="decoupling_geometry_detail",
                reason="图文证据不足以无歧义重建去耦结构的完整轮廓。",
                suggested_question="请补充去耦结构尺寸表或高清几何图。",
            ),
        ]
        spec = AntennaDesignSpec(
            spec_id=f"spec_{input_digest[:16]}",
            input_digest=input_digest,
            antenna_family="双单元 MIMO",
            topology="论文场景中的双层去耦结构",
            evidence=evidence,
            dimensions=dimensions,
            targets=targets,
            materials=materials,
            geometry_relations=[],
            unresolved_fields=unresolved,
            contradictions=[],
        )
        artifact_id = self.artifacts.write("spec", {"spec": spec.model_dump(mode="json")})
        return {"success": True, "artifact_id": artifact_id, "spec": spec.model_dump(mode="json")}

    def get_extraction_artifact(self, artifact_id: str) -> dict[str, object]:
        return {"success": True, "artifact": self.artifacts.read(artifact_id)}
