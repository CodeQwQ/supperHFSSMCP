from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINT = "http://127.0.0.1:8050/mcp"
CLIENT_ID = "module9-verifier"
EVIDENCE = Path(__file__).with_name("mcp-http-results.json")


def parse_result(result: Any) -> dict[str, Any]:
    text = next(item.text for item in result.content if getattr(item, "text", None))
    return json.loads(text)


async def call(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    result = await session.call_tool(name, arguments, meta={"client_id": CLIENT_ID})
    return {
        "tool": name,
        "arguments": arguments,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "response": parse_result(result),
    }


async def main() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "endpoint": ENDPOINT,
        "client_id": CLIENT_ID,
        "grpc_port": 53387,
        "client_api": "ClientSession.call_tool(..., meta={'client_id': CLIENT_ID})",
        "calls": [],
    }
    async with streamable_http_client(ENDPOINT) as (read, write, _):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            evidence["initialize"] = initialized.model_dump(mode="json")
            evidence["tools_list"] = {
                "count": len(tools.tools),
                "names": [tool.name for tool in tools.tools],
            }
            evidence["calls"].append(
                await call(
                    session,
                    "connect_hfss",
                    {
                        "machine": "localhost",
                        "port": 53387,
                        "student_version": True,
                        "desktop_version": "2025.2",
                        "non_graphical": True,
                        "new_desktop": False,
                        "connect_timeout_seconds": 60,
                    },
                )
            )
            evidence["calls"].append(
                await call(session, "create_hfss_design", {"design_name": "HFSS_Module9_VerifierDipole"})
            )
            evidence["calls"].append(
                await call(
                    session,
                    "create_dipole_antenna",
                    {"name": "Module9VerifierDipole", "frequency_ghz": 2.4},
                )
            )
            evidence["calls"].append(await call(session, "get_design_summary", {}))
            evidence["calls"].append(
                await call(
                    session,
                    "set_active_design",
                    {"design_name": "HFSS_Module9_OptPatch2"},
                )
            )
            evidence["calls"].append(
                await call(
                    session,
                    "set_design_variable",
                    {"name": "module9_verifier_var", "value": "1mm"},
                )
            )
            evidence["calls"].append(
                await call(
                    session,
                    "optimize_design_variable",
                    {
                        "variable_name": "module9_verifier_var",
                        "candidate_values": ["1mm"],
                        "setup_name": "Module9OptPatchSetup2",
                        "target_frequency_ghz": 2.4,
                        "expression": "dB(S(1,1))",
                        "threshold_db": -10.0,
                        "max_evaluations": 1,
                    },
                )
            )
    return evidence


if __name__ == "__main__":
    result = asyncio.run(main())
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
