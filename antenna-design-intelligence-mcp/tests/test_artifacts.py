from __future__ import annotations

import unittest

from antenna_design_intelligence_mcp.artifacts import ArtifactStore

try:
    from .helpers import temp_workspace
except ImportError:  # unittest discover -s tests imports modules as top-level
    from helpers import temp_workspace


class ArtifactTests(unittest.TestCase):
    def test_artifact_round_trip_uses_opaque_id(self) -> None:
        with temp_workspace() as root:
            store = ArtifactStore(root / "out")
            artifact_id = store.write("spec", {"spec_id": "spec-1"})
            self.assertTrue(artifact_id.startswith("spec_"))
            self.assertEqual(store.read(artifact_id)["payload"]["spec_id"], "spec-1")

    def test_artifact_read_rejects_forged_identifier(self) -> None:
        with temp_workspace() as root:
            store = ArtifactStore(root / "out")
            with self.assertRaises(ValueError):
                store.read("../../secret")


if __name__ == "__main__":
    unittest.main()
