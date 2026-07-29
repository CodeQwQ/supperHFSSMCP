from __future__ import annotations

import unittest

from antenna_design_intelligence_mcp.errors import DomainError


class ErrorTests(unittest.TestCase):
    def test_domain_error_is_transport_safe(self) -> None:
        error = DomainError("bad_input", "输入无效", {"field": "path"})
        self.assertEqual(
            error.to_payload(),
            {
                "success": False,
                "error": {"code": "bad_input", "message": "输入无效", "details": {"field": "path"}},
            },
        )


if __name__ == "__main__":
    unittest.main()
