from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FactStatus(str, Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class EvidenceKind(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    OPERATOR = "operator"


class ProviderHealth(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    page: int | None = Field(default=None, ge=1)
    region: tuple[float, float, float, float] | None = None
    quote: str = Field(min_length=1, max_length=4000)
    kind: EvidenceKind


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^e[0-9a-zA-Z_-]{1,63}$")
    source: SourceRef
    provider_id: str = Field(min_length=1, max_length=128)
    provider_version: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)
    observation: str = Field(min_length=1, max_length=4000)


class DimensionFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    semantic_role: str = Field(min_length=1, max_length=256)
    status: FactStatus
    value: float | None = None
    unit: Literal["mm", "um", "GHz", "MHz", "ohm", "ratio"] | None = None
    evidence_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> "DimensionFact":
        if self.status is FactStatus.CONFIRMED and (self.value is None or self.unit is None):
            raise ValueError("confirmed 尺寸必须同时提供数值和单位")
        if self.status is FactStatus.UNKNOWN and (self.value is not None or self.unit is not None):
            raise ValueError("unknown 尺寸不能提供数值或单位")
        return self


class PerformanceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    start_ghz: float | None = Field(default=None, gt=0)
    end_ghz: float | None = Field(default=None, gt=0)
    target_value: float | None = None
    target_unit: str | None = None
    status: FactStatus
    evidence_ids: list[str] = Field(min_length=1)


class MaterialFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["substrate", "conductor", "air", "other"]
    name: str | None = None
    relative_permittivity: float | None = Field(default=None, gt=0)
    loss_tangent: float | None = Field(default=None, ge=0)
    thickness_mm: float | None = Field(default=None, gt=0)
    status: FactStatus
    evidence_ids: list[str] = Field(min_length=1)


class GeometryRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    relation: str
    object: str
    status: FactStatus
    evidence_ids: list[str] = Field(min_length=1)


class UnresolvedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    reason: str
    required_before_hfss: bool = True
    suggested_question: str


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    observations: list[str] = Field(min_length=2)
    evidence_ids: list[str] = Field(min_length=2)


class AntennaDesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str = Field(min_length=1, max_length=128)
    input_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    antenna_family: str = Field(min_length=1, max_length=256)
    topology: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceItem] = Field(min_length=1)
    dimensions: list[DimensionFact] = Field(default_factory=list)
    targets: list[PerformanceTarget] = Field(default_factory=list)
    materials: list[MaterialFact] = Field(default_factory=list)
    geometry_relations: list[GeometryRelation] = Field(default_factory=list)
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_references(self) -> "AntennaDesignSpec":
        evidence_ids = {item.evidence_id for item in self.evidence}
        referenced: list[str] = []
        for item in self.dimensions:
            referenced.extend(item.evidence_ids)
        for item in self.targets:
            referenced.extend(item.evidence_ids)
        for item in self.materials:
            referenced.extend(item.evidence_ids)
        for item in self.geometry_relations:
            referenced.extend(item.evidence_ids)
        for item in self.contradictions:
            referenced.extend(item.evidence_ids)
        missing = sorted(set(referenced) - evidence_ids)
        if missing:
            raise ValueError(f"规格引用了不存在的证据: {', '.join(missing)}")
        return self
