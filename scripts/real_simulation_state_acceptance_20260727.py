from __future__ import annotations

import argparse
import asyncio
import ctypes
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
import win32con
import win32gui
import win32process
import win32ui


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "http://127.0.0.1:8063/mcp"
AEDT_EXECUTABLE = Path(r"D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe")
EVIDENCE_DIR = ROOT / "docs" / "测试报告" / "证据" / "仿真状态-20260727"
STATE_PATH = EVIDENCE_DIR / "state.json"


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
    raise RuntimeError(f"Port {port} did not open: {last_error}")


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
    _, alive = psutil.wait_procs([process], timeout=15)
    for item in alive:
        try:
            item.kill()
        except psutil.Error:
            pass


def save_state(state: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def process_tree_pids(pid: int) -> set[int]:
    pids = {pid}
    if not psutil.pid_exists(pid):
        return pids
    try:
        process = psutil.Process(pid)
        pids.update(child.pid for child in process.children(recursive=True))
    except psutil.Error:
        pass
    return pids


def find_window_for_process(pid: int) -> tuple[int, str]:
    candidates: list[tuple[int, str]] = []
    pids = process_tree_pids(pid)

    def visit(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
        if window_pid not in pids:
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        candidates.append((hwnd, title))

    win32gui.EnumWindows(visit, None)
    if not candidates:
        raise RuntimeError(f"No visible AEDT window was found for process tree rooted at PID {pid}.")
    candidates.sort(key=lambda item: ("Ansys" not in item[1], "Electronics" not in item[1], item[1]))
    return candidates[0]


def screenshot_window(pid: int, label: str) -> dict[str, Any]:
    path = EVIDENCE_DIR / f"{label}.bmp"
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    hwnd, title = find_window_for_process(pid)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"AEDT window has invalid bounds: {(left, top, right, bottom)}")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    memory_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    memory_dc.SelectObject(bitmap)
    try:
        result = ctypes.windll.user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 0)
        if result != 1:
            raise RuntimeError(f"PrintWindow failed for AEDT window {hwnd}.")
        bitmap.SaveBitmapFile(memory_dc, str(path))
    finally:
        try:
            win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass
        try:
            memory_dc.DeleteDC()
        except Exception:
            pass
        try:
            src_dc.DeleteDC()
        except Exception:
            pass
        try:
            win32gui.DeleteObject(bitmap.GetHandle())
        except Exception:
            pass
    return {
        "path": str(path),
        "hwnd": hwnd,
        "title": title,
        "bounds": [left, top, right, bottom],
    }


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


async def run_acceptance() -> None:
    state: dict[str, Any] = {"started_at": time.time(), "endpoint": ENDPOINT}
    launch = launch_aedt(50163)
    state["launch"] = launch
    save_state(state)
    client_id = "real-simulation-state-20260727"
    session_id: str | None = None
    try:
        async with streamable_http_client(ENDPOINT) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                calls: list[dict[str, Any]] = []
                setup_calls = [
                    (
                        "connect_hfss",
                        {
                            "machine": "localhost",
                            "port": 50163,
                            "student_version": True,
                            "desktop_version": "2025.2",
                            "non_graphical": False,
                            "new_desktop": False,
                            "connect_timeout_seconds": 180,
                        },
                    ),
                    ("create_hfss_design", {"design_name": "HFSS_RealSolve_State_20260727"}),
                    ("create_dipole_antenna", {"name": "RealSolveDipole20260727", "frequency_ghz": 2.4}),
                    (
                        "create_simulation_setup",
                        {
                            "setup_name": "SetupRealSolve20260727",
                            "frequency_ghz": 2.4,
                            "sweep_start_ghz": 2.35,
                            "sweep_stop_ghz": 2.45,
                            "sweep_points": 3,
                            "max_passes": 1,
                            "min_passes": 1,
                        },
                    ),
                ]
                for name, args in setup_calls:
                    calls.append(await call(session, client_id, name, args))
                    save_state({**state, "calls": calls})
                session_id = calls[0]["response"]["data"]["session"]["session_id"]
                state["session_id"] = session_id
                state["before_validation_screenshot"] = screenshot_window(launch["pid"], "01-before-validation")
                validation = await call(session, client_id, "validate_design", {})
                calls.append(validation)
                state["after_validation_screenshot"] = screenshot_window(launch["pid"], "02-after-validation")
                save_state({**state, "calls": calls})

                simulation_task = asyncio.create_task(
                    call(session, client_id, "run_simulation", {"setup_name": "SetupRealSolve20260727"})
                )
                simulation_screenshots: list[dict[str, Any]] = []
                while not simulation_task.done():
                    simulation_screenshots.append(
                        screenshot_window(launch["pid"], f"03-simulation-running-{len(simulation_screenshots) + 1:02d}")
                    )
                    save_state({**state, "calls": calls, "simulation_screenshots": simulation_screenshots})
                    await asyncio.sleep(1.0)
                simulation = await simulation_task
                calls.append(simulation)
                state["after_simulation_screenshot"] = screenshot_window(launch["pid"], "04-after-simulation")
                state["calls"] = calls
                state["simulation_screenshots"] = simulation_screenshots
                save_state(state)
                release = await call(
                    session,
                    client_id,
                    "release_connection",
                    {"session_id": session_id, "save_project": False},
                )
                state["release"] = release
                save_state(state)
    finally:
        time.sleep(3)
        state["process_alive_after_release"] = process_alive(launch["pid"])
        if state["process_alive_after_release"]:
            terminate_process(launch["pid"])
            state["forced_cleanup"] = True
            state["process_alive_after_cleanup"] = process_alive(launch["pid"])
        save_state(state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    asyncio.run(run_acceptance())


if __name__ == "__main__":
    main()
