from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64

from antenna_design_intelligence_mcp.models import ExtractionRequest
from antenna_design_intelligence_mcp.providers.registry import ProviderRegistry
from antenna_design_intelligence_mcp.providers.verification import VerificationEvidenceProvider
from antenna_design_intelligence_mcp.providers.http import HTTPPerceptionProvider


class ProviderTests(unittest.TestCase):
    def test_http_provider_sends_versioned_json_without_model_sdk(self) -> None:
        received: dict[str, object] = {}
        digest = "b" * 64

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                received.update(json.loads(self.rfile.read(length)))
                body = json.dumps(
                    {
                        "protocol_version": "1",
                        "provider_id": "test-perception",
                        "provider_version": "0.1.0",
                        "evidence": [
                            {
                                "evidence_id": "e1",
                                "source": {
                                    "input_id": digest,
                                    "page": 1,
                                    "quote": "5.8 GHz",
                                    "kind": "text",
                                },
                                "provider_id": "test-perception",
                                "provider_version": "0.1.0",
                                "confidence": 0.9,
                                "observation": "工作频段为 5.8 GHz。",
                            }
                        ],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = HTTPPerceptionProvider(
                endpoint=f"http://127.0.0.1:{server.server_port}/extract",
                timeout_seconds=5,
            )
            records = provider.extract(
                ExtractionRequest(
                    input_digest=digest,
                    input_suffix=".png",
                    content_base64=base64.b64encode(b"image-bytes").decode("ascii"),
                )
            )
            self.assertEqual(records[0].provider_id, "test-perception")
            self.assertEqual(received["protocol_version"], "1")
            self.assertEqual(received["input_digest"], digest)
            self.assertEqual(received["content_base64"], base64.b64encode(b"image-bytes").decode("ascii"))
        finally:
            server.shutdown()
            server.server_close()

    def test_default_registry_reports_verification_provider_unavailable(self) -> None:
        records = ProviderRegistry(enable_verification=False, output_root=Path("outputs")).list_status()
        self.assertEqual(records[0]["provider_id"], "verification_evidence")
        self.assertEqual(records[0]["health"], "unavailable")
        self.assertEqual(records[0]["provider_kind"], "verification")
        self.assertEqual(records[0]["capabilities"], ["manual_evidence"])

    def test_registry_reports_configured_http_perception_provider(self) -> None:
        records = ProviderRegistry(
            enable_verification=False,
            output_root=Path("outputs"),
            perception_endpoint="http://127.0.0.1:8020/extract",
        ).list_status()
        perception = next(item for item in records if item["provider_id"] == "http_perception")
        self.assertEqual(perception["health"], "available")
        self.assertIn("ocr", perception["capabilities"])

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
