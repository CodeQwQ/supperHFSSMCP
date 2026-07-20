from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ALICE = "module8-alice"
BOB = "module8-bob"
PROBE_RELATIVE_PATH = "scripts/module8-shared-probe.json"


def as_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {str(key): as_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_json(item) for item in value]
    return value


def parsed_tool_result(result: Any) -> dict[str, Any]:
    raw = as_json(result)
    parsed_text: Any = None
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            parsed_text = json.loads(text)
        except json.JSONDecodeError:
            parsed_text = text
        break
    return {
        "is_error": bool(getattr(result, "isError", False)),
        "raw": raw,
        "parsed": parsed_text,
    }


async def timed_call(
    session: ClientSession,
    client_id: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_wall = time.time()
    started = time.perf_counter()
    result = await session.call_tool(
        tool,
        arguments or {},
        meta={"client_id": client_id},
    )
    finished = time.perf_counter()
    return {
        "client_id": client_id,
        "tool": tool,
        "request_meta": {"client_id": client_id},
        "started_epoch": started_wall,
        "duration_seconds": round(finished - started, 3),
        "result": parsed_tool_result(result),
    }


async def run(endpoint: str, grpc_port: int, output_root: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "endpoint": endpoint,
        "grpc_port": grpc_port,
        "output_root": str(output_root.resolve()),
        "client_api": "ClientSession.call_tool(name, arguments, meta={'client_id': ...})",
        "clients": [ALICE, BOB],
    }

    async with streamable_http_client(endpoint) as alice_transport:
        async with ClientSession(alice_transport[0], alice_transport[1]) as alice_session:
            alice_init = await alice_session.initialize()
            tools = await alice_session.list_tools()
            evidence["initialize"] = as_json(alice_init)
            evidence["tools_list"] = {
                "count": len(tools.tools),
                "names": [tool.name for tool in tools.tools],
            }

            evidence["alice_connect"] = await timed_call(
                alice_session,
                ALICE,
                "connect_hfss",
                {
                    "desktop_version": "2025.2",
                    "student_version": True,
                    "machine": "localhost",
                    "port": grpc_port,
                    "non_graphical": True,
                    "new_desktop": False,
                    "connect_timeout_seconds": 90,
                },
            )
            evidence["alice_project_info"] = await timed_call(
                alice_session,
                ALICE,
                "get_project_info",
            )
            evidence["alice_sessions"] = await timed_call(
                alice_session,
                ALICE,
                "list_aedt_sessions",
            )

            async with streamable_http_client(endpoint) as bob_transport:
                async with ClientSession(bob_transport[0], bob_transport[1]) as bob_session:
                    bob_init = await bob_session.initialize()
                    evidence["bob_initialize"] = as_json(bob_init)
                    evidence["bob_sessions"] = await timed_call(
                        bob_session,
                        BOB,
                        "list_aedt_sessions",
                    )

                    probe_arguments = {
                        "script_id": "aedt_probe",
                        "runner": "pyaedt",
                        "port": grpc_port,
                        "relative_output": PROBE_RELATIVE_PATH,
                    }
                    alice_arguments = {
                        **probe_arguments,
                        "arguments": {
                            "client_marker": ALICE,
                            "token": "MODULE8_ALICE_TOKEN_MUST_NOT_APPEAR",
                            "nested": {
                                "password": "MODULE8_ALICE_PASSWORD_MUST_NOT_APPEAR",
                                "authorization": "Bearer MODULE8_ALICE_AUTH_MUST_NOT_APPEAR",
                            },
                        },
                    }
                    bob_arguments = {
                        **probe_arguments,
                        "arguments": {
                            "client_marker": BOB,
                            "secret": "MODULE8_BOB_SECRET_MUST_NOT_APPEAR",
                            "authorization": "Bearer MODULE8_BOB_AUTH_MUST_NOT_APPEAR",
                        },
                    }

                    concurrent_started = time.time()
                    alice_probe, bob_probe = await asyncio.gather(
                        timed_call(
                            alice_session,
                            ALICE,
                            "run_automation_script",
                            alice_arguments,
                        ),
                        timed_call(
                            bob_session,
                            BOB,
                            "run_automation_script",
                            bob_arguments,
                        ),
                    )
                    evidence["concurrent_probe"] = {
                        "started_epoch": concurrent_started,
                        "wall_duration_seconds": round(time.time() - concurrent_started, 3),
                        "requests": [alice_probe, bob_probe],
                    }

    artifact_paths = {
        ALICE: output_root / "workspaces" / ALICE / PROBE_RELATIVE_PATH,
        BOB: output_root / "workspaces" / BOB / PROBE_RELATIVE_PATH,
    }
    evidence["artifacts"] = {}
    for client_id, path in artifact_paths.items():
        item: dict[str, Any] = {
            "path": str(path.resolve()),
            "exists": path.is_file(),
        }
        if path.is_file():
            item["size"] = path.stat().st_size
            item["payload"] = json.loads(path.read_text(encoding="utf-8"))
        evidence["artifacts"][client_id] = item

    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8043/mcp")
    parser.add_argument("--grpc-port", type=int, default=53387)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(r"E:\LLMproject\HFSSagent\outputs\module8-verification-20260720"),
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path(r"E:\LLMproject\HFSSagent\docs\测试报告\证据\模块8\mcp-http-results.json"),
    )
    args = parser.parse_args()
    result = asyncio.run(run(args.endpoint, args.grpc_port, args.output_root))
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
