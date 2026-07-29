from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from antenna_design_intelligence_mcp.artifacts import ArtifactStore
from antenna_design_intelligence_mcp.paths import PathPolicy
from antenna_design_intelligence_mcp.providers.registry import ProviderRegistry
from antenna_design_intelligence_mcp.service import IntelligenceService


class ServiceTests(unittest.TestCase):
    def test_extract_spec_preserves_confirmed_facts_and_unknown_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            outputs = root / "outputs"
            inputs.mkdir()
            paper = inputs / "scenario3.pdf"
            paper.write_bytes(b"synthetic paper fixture")
            policy = PathPolicy((inputs,), outputs)
            artifacts = ArtifactStore(outputs)
            registry = ProviderRegistry(enable_verification=False, output_root=outputs)
            service = IntelligenceService(policy, artifacts, registry)

            inspected = service.inspect_input(str(paper))
            input_id = inspected["input_id"]
            verification_dir = outputs / "verification-evidence"
            verification_dir.mkdir()
            (verification_dir / f"{input_id}.json").write_text(
                json.dumps(
                    {
                        "input_digest": input_id,
                        "evidence": [
                            {
                                "evidence_id": "e1",
                                "source": {"input_id": input_id, "page": 9, "quote": "5.725-5.825 GHz", "kind": "text"},
                                "provider_id": "verification_evidence",
                                "provider_version": "0.1.0",
                                "confidence": 1.0,
                                "observation": "工作频段为 5.725-5.825 GHz。",
                            },
                            {
                                "evidence_id": "e2",
                                "source": {"input_id": input_id, "page": 9, "quote": "epsilon r = 4.6, tan delta = 0.001", "kind": "text"},
                                "provider_id": "verification_evidence",
                                "provider_version": "0.1.0",
                                "confidence": 1.0,
                                "observation": "基板相对介电常数 εr = 4.6，损耗角正切 tanδ = 0.001。",
                            },
                            {
                                "evidence_id": "e3",
                                "source": {"input_id": input_id, "page": 9, "quote": "12.9 mm", "kind": "figure"},
                                "provider_id": "verification_evidence",
                                "provider_version": "0.1.0",
                                "confidence": 1.0,
                                "observation": "两天线中心距为 12.9 mm。",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry = ProviderRegistry(enable_verification=True, output_root=outputs)
            service = IntelligenceService(policy, artifacts, registry)
            evidence = service.extract_document_evidence(input_id)
            result = service.extract_antenna_design_spec(evidence["artifact_id"])

            spec = result["spec"]
            self.assertEqual(spec["targets"][0]["start_ghz"], 5.725)
            self.assertEqual(spec["targets"][0]["end_ghz"], 5.825)
            self.assertEqual(spec["materials"][0]["relative_permittivity"], 4.6)
            self.assertEqual(spec["dimensions"][0]["value"], 12.9)
            self.assertTrue(any(item["field_name"] == "port_integration_line" for item in spec["unresolved_fields"]))


if __name__ == "__main__":
    unittest.main()
