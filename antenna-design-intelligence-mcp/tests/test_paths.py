from __future__ import annotations

import unittest
from pathlib import Path

from antenna_design_intelligence_mcp.errors import DomainError
from antenna_design_intelligence_mcp.paths import PathPolicy

try:
    from .helpers import temp_workspace
except ImportError:  # unittest discover -s tests imports modules as top-level
    from helpers import temp_workspace


class PathTests(unittest.TestCase):
    def test_input_outside_allowed_root_is_rejected(self) -> None:
        with temp_workspace() as root:
            secret = root / "secret.pdf"
            secret.write_bytes(b"pdf")
            policy = PathPolicy(input_roots=(root / "inputs",), output_root=root / "out")
            with self.assertRaises(DomainError) as error:
                policy.resolve_input(secret)
            self.assertEqual(error.exception.code, "input_path_outside_allowed_roots")

    def test_input_requires_supported_suffix_and_size_limit(self) -> None:
        with temp_workspace() as root:
            bad = root / "inputs" / "notes.txt"
            bad.write_bytes(b"text")
            policy = PathPolicy(input_roots=(root / "inputs",), output_root=root / "out")
            with self.assertRaises(DomainError) as error:
                policy.resolve_input(bad)
            self.assertEqual(error.exception.code, "unsupported_input_type")

    def test_output_name_rejects_path_traversal(self) -> None:
        with temp_workspace() as root:
            policy = PathPolicy(input_roots=(root / "inputs",), output_root=root / "out")
            with self.assertRaises(DomainError) as error:
                policy.resolve_output("../escape")
            self.assertEqual(error.exception.code, "invalid_artifact_id")


if __name__ == "__main__":
    unittest.main()
