from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.core.models import DipoleAntennaSpec
from hfss_agent_mcp.workflows.dipole import build_dipole_antenna


class DipoleWorkflowTests(unittest.TestCase):
    def test_build_dipole_recipe_contains_two_arms_gap_port_and_radiation(self) -> None:
        recipe = build_dipole_antenna(
            DipoleAntennaSpec(name="Dipole", frequency_ghz=2.4)
        )

        self.assertEqual(recipe["antenna_type"], "dipole")
        self.assertEqual(recipe["materials"]["conductor"], "copper")
        roles = {item["role"] for item in recipe["geometry"]}
        self.assertTrue({"arm_positive", "arm_negative", "port", "airbox"} <= roles)
        boundary_types = {item["boundary_type"] for item in recipe["boundaries"]}
        self.assertIn("radiation", boundary_types)
        self.assertIn("perfect_e", boundary_types)
        self.assertEqual(recipe["ports"][0]["port_type"], "lumped")

    def test_dipole_recipe_assigns_perfecte_to_both_metal_arms(self) -> None:
        recipe = build_dipole_antenna(
            DipoleAntennaSpec(name="Dipole", frequency_ghz=2.4)
        )

        perfect_e = next(
            item for item in recipe["boundaries"] if item["boundary_type"] == "perfect_e"
        )

        self.assertEqual("Dipole_perfect_e", perfect_e["name"])
        self.assertEqual(
            ("Dipole_arm_negative", "Dipole_arm_positive"),
            tuple(perfect_e["objects"]),
        )

    def test_dipole_dimensions_are_derived_from_frequency(self) -> None:
        recipe = build_dipole_antenna(
            DipoleAntennaSpec(
                name="Dipole",
                frequency_ghz=1.0,
                arm_length_mm=75.0,
                arm_width_mm=2.0,
                gap_mm=1.0,
            )
        )

        self.assertEqual(recipe["dimensions_mm"]["arm_length_mm"], 75.0)
        self.assertEqual(recipe["dimensions_mm"]["gap_mm"], 1.0)
        self.assertGreater(recipe["dimensions_mm"]["airbox_margin_mm"], 0.0)


if __name__ == "__main__":
    unittest.main()
