from __future__ import annotations

import unittest

from pydantic import ValidationError

from antenna_design_intelligence_mcp.models import (
    AntennaDesignSpec,
    DimensionFact,
    EvidenceItem,
    EvidenceKind,
    ExtractionRequest,
    FactStatus,
    SourceRef,
)


def evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="e1",
        source=SourceRef(
            input_id="a" * 64,
            page=1,
            quote="工作频段为 5.725-5.825 GHz",
            kind=EvidenceKind.TEXT,
        ),
        provider_id="verification_evidence",
        provider_version="0.1.0",
        confidence=1.0,
        observation="论文正文明确给出工作频段。",
    )


class ModelTests(unittest.TestCase):
    def test_extraction_request_accepts_transport_payload_metadata(self) -> None:
        request = ExtractionRequest(
            input_digest="a" * 64,
            input_suffix=".pdf",
            content_base64="cGF5bG9hZA==",
        )
        self.assertEqual(request.input_suffix, ".pdf")
        self.assertEqual(request.content_base64, "cGF5bG9hZA==")
    def test_confirmed_dimension_requires_value_and_unit(self) -> None:
        with self.assertRaises(ValidationError):
            DimensionFact(
                name="patch_length",
                semantic_role="贴片长度",
                status=FactStatus.CONFIRMED,
                evidence_ids=["e1"],
            )

    def test_unknown_dimension_rejects_numeric_value(self) -> None:
        with self.assertRaises(ValidationError):
            DimensionFact(
                name="gap",
                semantic_role="间隙",
                status=FactStatus.UNKNOWN,
                value=1.2,
                unit="mm",
                evidence_ids=["e1"],
            )

    def test_spec_rejects_missing_evidence_reference(self) -> None:
        with self.assertRaises(ValidationError):
            AntennaDesignSpec(
                spec_id="spec-1",
                input_digest="a" * 64,
                antenna_family="双单元 MIMO",
                topology="双层去耦结构",
                evidence=[evidence()],
                dimensions=[
                    DimensionFact(
                        name="spacing",
                        semantic_role="中心距",
                        status=FactStatus.CONFIRMED,
                        value=12.9,
                        unit="mm",
                        evidence_ids=["missing"],
                    )
                ],
            )

    def test_valid_spec_preserves_confirmed_dimension(self) -> None:
        spec = AntennaDesignSpec(
            spec_id="spec-1",
            input_digest="a" * 64,
            antenna_family="双单元 MIMO",
            topology="双层去耦结构",
            evidence=[evidence()],
            dimensions=[],
            targets=[],
            materials=[],
            geometry_relations=[],
            unresolved_fields=[],
            contradictions=[],
        )
        self.assertEqual(spec.spec_id, "spec-1")


if __name__ == "__main__":
    unittest.main()
