from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINT = "http://127.0.0.1:8042/mcp"
OUT = Path(r"E:\LLMproject\HFSSagent\docs\测试报告\证据\模块7-重测")
GRPC_PORTS = (53387, 53388)
REQUEST_ID = "module7-retest"


def decode(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []) or []:
        item_text = getattr(item, "text", None)
        if isinstance(item_text, str):
            try:
                parsed = json.loads(item_text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {"_raw": repr(result)}


def save_json(name: str, value: Any) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {
        "verification": "module7-real-hfss-retest",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
        "transport": "streamable-http",
        "client_python": os.path.abspath(os.sys.executable),
        "aedt": {
            "product": "Ansys Electronics Desktop Student 2025 R2",
            "candidate_grpc_ports": list(GRPC_PORTS),
        },
        "request_policy": {
            "ordinary_request_timeout_seconds": 30,
            "runner_request_timeout_seconds": 90,
        },
        "request_id": REQUEST_ID,
        "calls": [],
    }

    async with streamable_http_client(ENDPOINT) as (read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            init = await asyncio.wait_for(session.initialize(), timeout=30)
            evidence["initialize"] = {
                "protocol_version": getattr(init, "protocolVersion", None),
                "server_info": repr(getattr(init, "serverInfo", None)),
                "http_session_id": get_session_id(),
            }
            save_json("01-initialize.json", evidence["initialize"])

            listed = await asyncio.wait_for(session.list_tools(), timeout=30)
            tool_names = sorted(tool.name for tool in listed.tools)
            tools_record = {"count": len(tool_names), "tool_names": tool_names}
            evidence["tools_list"] = tools_record
            save_json("02-tools-list.json", tools_record)

            async def call(name: str, arguments: dict[str, Any], timeout: float, filename: str) -> dict[str, Any]:
                record: dict[str, Any] = {"tool": name, "arguments": arguments, "timeout_seconds": timeout}
                try:
                    result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=timeout)
                    record["response"] = decode(result)
                    record["is_error"] = getattr(result, "isError", None)
                    record["ok"] = True
                except asyncio.TimeoutError:
                    record["ok"] = False
                    record["error"] = "asyncio.TimeoutError"
                except Exception as exc:
                    record["ok"] = False
                    record["error"] = repr(exc)
                    record["traceback"] = traceback.format_exc()
                evidence["calls"].append(record)
                save_json(filename, record)
                return record

            scripts = await call("list_automation_scripts", {}, 30, "03-list-automation-scripts.json")
            evidence["registered_scripts"] = scripts.get("response", {}).get("data", {})

            connected_port: int | None = None
            for port in GRPC_PORTS:
                connected = await call(
                    "connect_hfss",
                    {
                        "student_version": True,
                        "desktop_version": "2025.2",
                        "machine": "localhost",
                        "port": port,
                        "non_graphical": False,
                        "new_desktop": False,
                        "owner": "module7-retest",
                        "connect_timeout_seconds": 30,
                    },
                    30,
                    f"04-connect-hfss-{port}.json",
                )
                if connected.get("ok") and connected.get("response", {}).get("status") == "ok":
                    connected_port = port
                    evidence["connected_session"] = connected["response"].get("data", {})
                    break
            evidence["selected_grpc_port"] = connected_port

            common_arguments = {"request_id": REQUEST_ID}
            runner_args = {
                "pyaedt": {
                    "script_id": "aedt_probe",
                    "runner": "pyaedt",
                    "operation": "script",
                    "port": 53387,
                    "arguments": common_arguments,
                    "relative_output": "scripts/module7-pyaedt-retest.json",
                },
                "native": {
                    "script_id": "aedt_probe",
                    "runner": "native",
                    "operation": "script",
                    "arguments": common_arguments,
                    "relative_output": "scripts/module7-native-retest.json",
                },
                "com": {
                    "script_id": "aedt_probe",
                    "runner": "com",
                    "operation": "script",
                    "arguments": common_arguments,
                    "relative_output": "scripts/module7-com-retest.json",
                },
            }
            for runner in ("pyaedt", "native", "com"):
                await call(
                    "run_automation_script",
                    runner_args[runner],
                    90,
                    f"05-runner-{runner}.json",
                )

    evidence["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save_json("mcp-http-full-module7-retest.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
