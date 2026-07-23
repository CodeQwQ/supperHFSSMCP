from __future__ import annotations

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINT = "http://127.0.0.1:8060/mcp"
AEDT_EXECUTABLE = Path(r"D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe")
EVIDENCE_DIR = Path("docs/测试报告/证据/修复-20260723")
STATE_PATH = EVIDENCE_DIR / "acceptance-state.json"


def wait_port(port: int, timeout_seconds: float = 180.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError(f"AEDT gRPC port {port} did not open: {last_error}")


def launch_aedt(port: int) -> dict[str, Any]:
    process = subprocess.Popen([str(AEDT_EXECUTABLE), "-grpcsrv", str(port)])
    wait_port(port)
    return {"pid": process.pid, "port": port}


def process_alive(pid: int) -> bool:
    return psutil.pid_exists(pid) and psutil.Process(pid).is_running()


def terminate_process(pid: int) -> None:
    if not psutil.pid_exists(pid):
        return
    process = psutil.Process(pid)
    for child in process.children(recursive=True):
        try:
            child.terminate()
        except psutil.Error:
            pass
    try:
        process.terminate()
    except psutil.Error:
        pass
    gone, alive = psutil.wait_procs([process], timeout=15)
    for item in alive:
        try:
            item.kill()
        except psutil.Error:
            pass


def parse_result(result: Any) -> dict[str, Any]:
    text = next(item.text for item in result.content if getattr(item, "text", None))
    return json.loads(text)


async def call(session: ClientSession, client_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    result = await session.call_tool(name, arguments, meta={"client_id": client_id})
    return {
        "tool": name,
        "arguments": arguments,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "response": parse_result(result),
    }


async def run_calls(client_id: str, calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    async with streamable_http_client(ENDPOINT) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return [await call(session, client_id, name, args) for name, args in calls]


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def phase_setup_gui() -> None:
    state = load_state()
    launch = launch_aedt(50121)
    calls = await run_calls(
        "acceptance-gui",
        [
            (
                "connect_hfss",
                {
                    "machine": "localhost",
                    "port": 50121,
                    "student_version": True,
                    "desktop_version": "2025.2",
                    "non_graphical": False,
                    "new_desktop": False,
                    "connect_timeout_seconds": 180,
                },
            ),
            ("create_hfss_design", {"design_name": "HFSS_GUI_Acceptance_20260723"}),
            ("create_dipole_antenna", {"name": "GuiDipole20260723", "frequency_ghz": 2.4}),
            ("create_simulation_setup", {"setup_name": "Setup1", "frequency_ghz": 2.4, "sweep_points": 21}),
            ("validate_design", {}),
            ("get_design_summary", {}),
        ],
    )
    session_id = calls[0]["response"]["data"]["session"]["session_id"]
    state["gui"] = {"launch": launch, "session_id": session_id, "calls": calls}
    save_state(state)
    print(json.dumps(state["gui"], ensure_ascii=False, indent=2))


async def phase_release_close() -> None:
    state = load_state()
    gui = state["gui"]
    pid = gui["launch"]["pid"]
    calls = await run_calls(
        "acceptance-gui",
        [("release_connection", {"session_id": gui["session_id"]})],
    )
    time.sleep(8)
    state["release_close"] = {
        "calls": calls,
        "pid": pid,
        "process_alive_after_release": process_alive(pid),
    }
    save_state(state)
    print(json.dumps(state["release_close"], ensure_ascii=False, indent=2))


async def phase_release_keep() -> None:
    state = load_state()
    launch = launch_aedt(50122)
    calls = await run_calls(
        "acceptance-keep",
        [
            (
                "connect_hfss",
                {
                    "machine": "localhost",
                    "port": 50122,
                    "student_version": True,
                    "desktop_version": "2025.2",
                    "non_graphical": False,
                    "new_desktop": False,
                    "connect_timeout_seconds": 180,
                },
            ),
            ("create_hfss_design", {"design_name": "HFSS_KeepWindow_20260723"}),
            ("create_dipole_antenna", {"name": "KeepDipole20260723", "frequency_ghz": 2.4}),
        ],
    )
    session_id = calls[0]["response"]["data"]["session"]["session_id"]
    release = await run_calls(
        "acceptance-keep",
        [("release_connection", {"session_id": session_id, "close_desktop": False})],
    )
    time.sleep(8)
    state["release_keep"] = {
        "launch": launch,
        "session_id": session_id,
        "calls": calls,
        "release": release,
        "process_alive_after_release": process_alive(launch["pid"]),
    }
    save_state(state)
    print(json.dumps(state["release_keep"], ensure_ascii=False, indent=2))


async def phase_invalid_validation() -> None:
    state = load_state()
    launch = launch_aedt(50123)
    calls = await run_calls(
        "acceptance-invalid",
        [
            (
                "connect_hfss",
                {
                    "machine": "localhost",
                    "port": 50123,
                    "student_version": True,
                    "desktop_version": "2025.2",
                    "non_graphical": False,
                    "new_desktop": False,
                    "connect_timeout_seconds": 180,
                },
            ),
            ("create_hfss_design", {"design_name": "HFSS_Invalid_20260723"}),
            ("create_simulation_setup", {"setup_name": "SetupInvalid", "frequency_ghz": 2.4, "sweep_points": 11}),
            ("run_simulation", {"setup_name": "SetupInvalid", "wait_for_completion": True}),
        ],
    )
    session_id = calls[0]["response"]["data"]["session"]["session_id"]
    release = await run_calls(
        "acceptance-invalid",
        [("release_connection", {"session_id": session_id})],
    )
    state["invalid_validation"] = {
        "launch": launch,
        "session_id": session_id,
        "calls": calls,
        "release": release,
    }
    save_state(state)
    print(json.dumps(state["invalid_validation"], ensure_ascii=False, indent=2))


async def phase_cleanup() -> None:
    state = load_state()
    for key in ("gui", "release_keep", "invalid_validation"):
        launch = state.get(key, {}).get("launch")
        if launch and process_alive(launch["pid"]):
            terminate_process(launch["pid"])
    state["cleanup"] = {"completed": True, "timestamp": time.time()}
    save_state(state)
    print(json.dumps(state["cleanup"], ensure_ascii=False, indent=2))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase")
    args = parser.parse_args()
    phases = {
        "setup_gui": phase_setup_gui,
        "release_close": phase_release_close,
        "release_keep": phase_release_keep,
        "invalid_validation": phase_invalid_validation,
        "cleanup": phase_cleanup,
    }
    if args.phase not in phases:
        raise SystemExit(f"Unknown phase {args.phase!r}. Choose one of {sorted(phases)}")
    await phases[args.phase]()


if __name__ == "__main__":
    asyncio.run(main())
