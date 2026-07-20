from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.errors import ConfigurationError
from hfss_agent_mcp.core.security import SecurityError, SecurityManager, current_identity
from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.server import create_app


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-security-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_workspace_and_audit_are_separated_by_client_id(self) -> None:
        service = HfssService(
            MockHfssBackend(),
            output_root=self.tmp,
            config=ServerConfig(backend="mock", output_root=self.tmp),
        )
        app = create_app(
            ServerConfig(backend="mock", output_root=self.tmp),
            service=service,
        )

        async def call(client_id: str) -> dict:
            context = SimpleNamespace(client_id=client_id, request_id=f"connect-{client_id}")
            await app._tool_manager.call_tool(
                "connect_hfss",
                {},
                context=context,
                convert_result=True,
            )
            result = await app._tool_manager.call_tool(
                "create_project",
                {"project_name": "SharedName"},
                context=SimpleNamespace(client_id=client_id, request_id=f"request-{client_id}"),
                convert_result=True,
            )
            text = result[0].text if isinstance(result, list) else str(result)
            return json.loads(text)

        alice = asyncio.run(call("alice"))
        bob = asyncio.run(call("bob"))
        self.assertIn("workspaces\\alice", alice["data"]["project_path"])
        self.assertIn("workspaces\\bob", bob["data"]["project_path"])
        self.assertNotEqual(alice, bob)

        audit_path = self.tmp / "audit" / "requests.jsonl"
        records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["tool"] == "create_project"
        ]
        self.assertEqual(["alice", "bob"], [record["owner"] for record in records])
        self.assertEqual(["request-alice", "request-bob"], [record["request_id"] for record in records])

    def test_audit_redacts_secret_like_arguments(self) -> None:
        manager = SecurityManager(self.tmp)
        identity = manager.resolve(SimpleNamespace(client_id="alice", request_id="r1"))
        manager.record(
            identity=identity,
            tool_name="example",
            arguments={"token": "do-not-log", "nested": {"password": "hidden"}},
            status="ok",
            duration_seconds=0.01,
        )
        line = (self.tmp / "audit" / "requests.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("do-not-log", line)
        self.assertNotIn("hidden", line)
        self.assertIn("[REDACTED]", line)

    def test_require_client_id_rejects_anonymous_context(self) -> None:
        manager = SecurityManager(self.tmp, require_client_id=True)
        with self.assertRaises(SecurityError):
            manager.resolve(SimpleNamespace(client_id=None, request_id="r1"))

    def test_context_is_not_leaked_after_tool_call(self) -> None:
        service = HfssService(MockHfssBackend(), output_root=self.tmp)
        app = create_app(ServerConfig(backend="mock", output_root=self.tmp), service=service)

        async def call() -> None:
            await app._tool_manager.call_tool(
                "health_check",
                {},
                context=SimpleNamespace(client_id="alice", request_id="r1"),
                convert_result=True,
            )

        asyncio.run(call())
        self.assertIsNone(current_identity())

    def test_lock_timeout_must_be_positive(self) -> None:
        with self.assertRaises(ConfigurationError):
            SecurityManager(self.tmp, lock_timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
