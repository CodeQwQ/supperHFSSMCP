from __future__ import annotations

import base64
import json
import threading
import unittest
from http.client import HTTPConnection

from antenna_perception_sidecar.engine import DemoEngine
from antenna_perception_sidecar.server import create_server


class SidecarProtocolTests(unittest.TestCase):
    def test_demo_engine_is_usable_without_model_runtime(self) -> None:
        engine = DemoEngine()
        records = engine.extract("a" * 64, ".png", b"image")
        self.assertEqual(records[0]["source"]["input_id"], "a" * 64)

    def test_http_extract_returns_versioned_evidence(self) -> None:
        server = create_server("127.0.0.1", 0, DemoEngine())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            body = json.dumps(
                {
                    "protocol_version": "1",
                    "input_digest": "b" * 64,
                    "input_suffix": ".pdf",
                    "content_base64": base64.b64encode(b"paper").decode("ascii"),
                }
            )
            conn.request("POST", "/extract", body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["protocol_version"], "1")
            self.assertTrue(payload["evidence"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
