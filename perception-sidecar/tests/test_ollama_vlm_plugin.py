from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins"))
from ollama_vlm_plugin import OllamaVLMEngine  # noqa: E402


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class OllamaVLMEngineTests(unittest.TestCase):
    def test_extract_posts_image_and_returns_structured_evidence(self) -> None:
        response = _Response({"message": {"content": '{"antenna_type":"patch","unknowns":[]}'} })
        with patch("ollama_vlm_plugin.urllib.request.urlopen", return_value=response) as open_url:
            records = OllamaVLMEngine().extract("a" * 64, ".png", b"image")

        request = open_url.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen2.5vl:7b")
        self.assertEqual(payload["messages"][0]["images"], ["aW1hZ2U="])
        self.assertEqual(records[0]["observation"]["antenna_type"], "patch")
        self.assertEqual(records[0]["source"]["input_id"], "a" * 64)

    def test_pdf_returns_manual_review_without_calling_ollama(self) -> None:
        with patch("ollama_vlm_plugin.urllib.request.urlopen") as open_url:
            records = OllamaVLMEngine().extract("b" * 64, ".pdf", b"paper")

        open_url.assert_not_called()
        self.assertEqual(records[0]["confidence"], 0.0)
        self.assertIn("页面", records[0]["observation"])

    def test_invalid_json_is_reported_as_manual_review(self) -> None:
        response = _Response({"message": {"content": "not-json"}})
        with patch("ollama_vlm_plugin.urllib.request.urlopen", return_value=response):
            records = OllamaVLMEngine().extract("c" * 64, ".jpg", b"image")

        self.assertEqual(records[0]["confidence"], 0.0)
        self.assertIn("JSON", records[0]["observation"])


if __name__ == "__main__":
    unittest.main()
