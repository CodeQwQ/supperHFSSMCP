from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.core.errors import InputValidationError
from hfss_agent_mcp.core.optimization import evaluate_candidate, optimize_candidates


class OptimizationLoopTests(unittest.TestCase):
    def test_candidates_are_evaluated_and_best_score_is_selected(self) -> None:
        values = ["1mm", "2mm", "3mm"]

        result = optimize_candidates(
            values,
            lambda value: evaluate_candidate(
                value,
                {
                    "sample_points": [
                        {"frequency_ghz": 2.4, "value_db": -18.0 if value == "2mm" else -8.0}
                    ]
                },
                target_frequency_ghz=2.4,
                threshold_db=-10.0,
            ),
        )

        self.assertEqual(result["best"]["value"], "2mm")
        self.assertTrue(result["best"]["passed"])
        self.assertEqual(len(result["evaluations"]), 3)

    def test_empty_candidates_are_rejected(self) -> None:
        with self.assertRaises(InputValidationError):
            optimize_candidates([], lambda value: {})

    def test_max_evaluations_bounds_the_loop(self) -> None:
        result = optimize_candidates(
            ["1mm", "2mm", "3mm"],
            lambda value: {"value": value, "score": 1.0, "passed": False},
            max_evaluations=2,
        )

        self.assertEqual(len(result["evaluations"]), 2)
        self.assertEqual(result["stopped_reason"], "max_evaluations")


if __name__ == "__main__":
    unittest.main()
