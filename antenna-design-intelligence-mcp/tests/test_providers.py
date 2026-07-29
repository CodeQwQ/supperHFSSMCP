from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from antenna_design_intelligence_mcp.models import ExtractionRequest
from antenna_design_intelligence_mcp.providers.registry import ProviderRegistry
from antenna_design_intelligence_mcp.providers.verification import VerificationEvidenceProvider


class ProviderTests(unittest.TestCase):
    def test_default_registry_reports_verification_provider_unavailable(self) -> None:
        records = ProviderRegistry(enable_verification=False, output_root=Path("outputs")).list_status()
        self.assertEqual(records[0]["provider_id"], "verification_evidence")
        self.assertEqual(records[0]["health"], "unavailable")

    def test_enabled_verification_provider_rejects_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            provider = VerificationEvidenceProvider(output_root=Path(raw))
            with self.assertRaises(ValueError) as error:
                provider.extract(ExtractionRequest(input_digest="a" * 64))
            self.assertEqual(error.exception.code, "verification_evidence_not_found")

    def test_enabled_provider_reads_only_digest_named_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output_root = Path(raw)
            digest = "a" * 64
            fixture_dir = output_root / "verification-evidence"
            fixture_dir.mkdir()
            fixture = {
                "input_digest": digest,
                "evidence": [
                    {
                        "evidence_id": "e1",
                        "source": {
                            "input_id": digest,
                            "page": 1,
                            "quote": "5.725-5.825 GHz",
                            "kind": "text",
                        },
                        "provider_id": "verification_evidence",
                        "provider_version": "0.1.0",
                        "confidence": 1.0,
                        "observation": "人工核对的场景三工作带宽。",
                    }
                ],
            }
            (fixture_dir / f"{digest}.json").write_text(
                json.dumps(fixture, ensure_ascii=False), encoding="utf-8"
            )
            provider = VerificationEvidenceProvider(output_root=output_root)
            records = provider.extract(ExtractionRequest(input_digest=digest))
            self.assertEqual(records[0].source.page, 1)
            self.assertEqual(records[0].provider_id, "verification_evidence")


if __name__ == "__main__":
    unittest.main()
