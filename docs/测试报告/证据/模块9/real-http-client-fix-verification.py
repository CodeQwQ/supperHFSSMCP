from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINT = "http://127.0.0.1:8051/mcp"
CLIENT_ID = "module9-fix-verifier-independent"
GRPC_PORT = 53387
EVIDENCE = Path(__file__).with_name("mcp-http-results-fix-independent.json")


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


def finite_sample_points(data: dict[str, Any]) -> list[dict[str, Any]]:
    points = data.get("best", {}).get("analysis", {}).get("sample_points", [])
    return [
        point
        for point in points
        if math.isfinite(float(point["frequency_ghz"]))
        and math.isfinite(float(point["value_db"]))
    ]


async def main() -> dict[str, Any]:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    design_name = f"HFSS_Module9_FixIndependent_{suffix}"
    antenna_name = f"Module9FixIndependent_{suffix}"
    setup_name = f"Module9FixSetup_{suffix}"
    sweep_name = f"Module9FixSweep_{suffix}"
    variable_name = f"module9_fix_var_{suffix}"
    evidence: dict[str, Any] = {
        "endpoint": ENDPOINT,
        "client_id": CLIENT_ID,
        "grpc_port": GRPC_PORT,
        "client_api": "mcp.ClientSession + streamable_http_client",
        "fresh_names": {
            "design_name": design_name,
            "antenna_name": antenna_name,
            "setup_name": setup_name,
            "sweep_name": sweep_name,
            "variable_name": variable_name,
        },
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
                        "port": GRPC_PORT,
                        "student_version": True,
                        "desktop_version": "2025.2",
                        "non_graphical": True,
                        "new_desktop": False,
                        "connect_timeout_seconds": 60,
                    },
                )
            )
            evidence["calls"].append(
                await call(session, "create_hfss_design", {"design_name": design_name})
            )
            evidence["calls"].append(
                await call(
                    session,
                    "create_patch_antenna",
                    {"name": antenna_name, "frequency_ghz": 2.4},
                )
            )
            evidence["calls"].append(
                await call(
                    session,
                    "create_simulation_setup",
                    {
                        "setup_name": setup_name,
                        "frequency_ghz": 2.4,
                        "sweep_name": sweep_name,
                        "sweep_start_ghz": 2.2,
                        "sweep_stop_ghz": 2.6,
                        "sweep_points": 3,
                        "max_passes": 1,
                        "min_passes": 1,
                    },
                )
            )
            evidence["calls"].append(
                await call(
                    session,
                    "set_design_variable",
                    {"name": variable_name, "value": "1mm"},
                )
            )
            evidence["calls"].append(
                await call(
                    session,
                    "optimize_design_variable",
                    {
                        "variable_name": variable_name,
                        "candidate_values": ["1mm"],
                        "setup_name": setup_name,
                        "sweep_name": sweep_name,
                        "target_frequency_ghz": 2.4,
                        "expression": "dB(S(1,1))",
                        "threshold_db": -10.0,
                        "max_evaluations": 1,
                    },
                )
            )
    optimize = evidence["calls"][-1]["response"]
    data = optimize.get("data", {})
    evidence["verification"] = {
        "outer_status": optimize.get("status"),
        "business_status": data.get("status", "ok"),
        "simulation_status": data.get("best", {}).get("simulation", {}).get("status"),
        "sample_points": finite_sample_points(data),
        "all_sample_points_finite": bool(finite_sample_points(data))
        and len(finite_sample_points(data))
        == len(data.get("best", {}).get("analysis", {}).get("sample_points", [])),
        "has_best": data.get("best") is not None,
        "has_evaluations": bool(data.get("evaluations")),
        "evaluation_count": data.get("evaluation_count"),
        "candidate_passed": data.get("best", {}).get("passed"),
    }
    return evidence


if __name__ == "__main__":
    result = asyncio.run(main())
    EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
